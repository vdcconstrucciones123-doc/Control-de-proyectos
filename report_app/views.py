import json
from datetime import datetime

from django.contrib.auth import login
from django.contrib.auth.decorators import login_required
from django.contrib.auth.models import User
from django.db.models import Prefetch, Q
from django.http import HttpResponseBadRequest, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_http_methods

from .forms import ProjectForm, ReportMetaForm, ReportTypeForm, SignUpForm
from .models import EntryImage, ProjectMembership, ProjectReport, ReportEntry, ReportFront, ReportProject


def _project_queryset_for_user(user):
    return ReportProject.objects.filter(
        Q(owner=user) | Q(memberships__user=user)
    ).select_related("owner").prefetch_related(
        "memberships__user",
        Prefetch(
            "reports",
            queryset=ProjectReport.objects.prefetch_related(
                "fronts",
                Prefetch("entries", queryset=ReportEntry.objects.prefetch_related("images", "front")),
            ),
        ),
    ).distinct()


def _project_role_for_user(project, user):
    if project.owner_id == user.id:
        return ProjectMembership.ROLE_ADMIN
    membership = project.memberships.filter(user=user).first()
    return membership.role if membership else None


def _can_edit_project(project, user):
    return _project_role_for_user(project, user) in {ProjectMembership.ROLE_ADMIN, ProjectMembership.ROLE_EDITOR}


def _can_share_project(project, user):
    return project.owner_id == user.id


def _parse_json(request):
    try:
        return json.loads(request.body.decode("utf-8") or "{}")
    except json.JSONDecodeError:
        return None


def _request_data(request):
    if request.content_type and request.content_type.startswith("application/json"):
        return _parse_json(request)
    return request.POST


def _coerce_date(value):
    if not value:
        return None
    if isinstance(value, datetime):
        return value.date()
    if hasattr(value, "year") and hasattr(value, "month"):
        return value
    try:
        return datetime.strptime(str(value), "%Y-%m-%d").date()
    except ValueError:
        return None


def _coerce_list(value):
    if value in (None, ""):
        return []
    if isinstance(value, list):
        return value
    if isinstance(value, str):
        try:
            parsed = json.loads(value)
            if isinstance(parsed, list):
                return [str(item).strip() for item in parsed if str(item).strip()]
        except json.JSONDecodeError:
            return [item.strip() for item in value.splitlines() if item.strip()]
    return []


def _serialize_members(project):
    members = [{
        "username": project.owner.username,
        "role": ProjectMembership.ROLE_ADMIN,
        "isOwner": True,
    }]
    for membership in project.memberships.select_related("user").all():
        members.append({
            "username": membership.user.username,
            "role": membership.role,
            "isOwner": False,
        })
    return members


def _serialize_entry(entry):
    return {
        "id": entry.id,
        "frontId": entry.front_id,
        "status": entry.status,
        "desc": entry.description,
        "images": [image.image.url for image in entry.images.all() if image.image],
        "ts": entry.updated_at.isoformat(),
    }


def _serialize_report(report):
    return {
        "id": report.id,
        "type": report.report_type,
        "title": report.title,
        "week": report.week or "",
        "date": report.report_date.isoformat() if report.report_date else "",
        "laborDateFrom": report.labor_date_from.isoformat() if report.labor_date_from else "",
        "laborDateTo": report.labor_date_to.isoformat() if report.labor_date_to else "",
        "forWhom": report.for_whom,
        "fromWhom": report.from_whom,
        "objectiveText": report.objective_text,
        "analysisText": report.analysis_text,
        "conclusionText": report.conclusion_text,
        "recommendationText": report.recommendation_text,
        "conclusionItems": report.conclusion_items or [],
        "recommendationItems": report.recommendation_items or [],
        "coverImage": report.cover_image.url if report.cover_image else "",
        "fronts": [{"id": front.id, "name": front.name} for front in report.fronts.all()],
        "entries": [_serialize_entry(entry) for entry in report.entries.all()],
        "autoMergeDup": report.auto_merge_dup,
        "combineByStatus": report.combine_by_status,
        "editingEntryId": None,
        "showIssueForm": False,
        "showPreviewMode": False,
        "metaComplete": True,
        "currentFrontId": None,
    }


def _serialize_project(project, user):
    role = _project_role_for_user(project, user)
    can_edit = role in {ProjectMembership.ROLE_ADMIN, ProjectMembership.ROLE_EDITOR}
    can_share = role == ProjectMembership.ROLE_ADMIN
    return {
        "id": project.id,
        "dbId": project.id,
        "slug": project.slug,
        "companyName": project.company_name,
        "projectName": project.project_name,
        "projectLocation": project.project_location,
        "reportTitle": project.report_title,
        "forWhom": project.for_whom,
        "fromWhom": project.from_whom,
        "ownerUsername": project.owner.username,
        "accessRole": role,
        "canEdit": can_edit,
        "canShare": can_share,
        "canDelete": project.owner_id == user.id,
        "isOwned": project.owner_id == user.id,
        "members": _serialize_members(project),
        "reports": [_serialize_report(report) for report in project.reports.all()],
    }


def _get_project_or_404(user, slug):
    return get_object_or_404(_project_queryset_for_user(user), slug=slug)


def _get_report_or_404(project, report_id):
    return get_object_or_404(project.reports.all(), pk=report_id)


def _apply_report_payload(report, payload, files=None):
    report_type = (payload.get("reportType") or payload.get("type") or report.report_type or ProjectReport.TYPE_PROGRESS).strip()
    if report_type not in dict(ProjectReport.TYPE_CHOICES):
        report_type = ProjectReport.TYPE_PROGRESS
    report.report_type = report_type
    report.title = (payload.get("reportTitle") or payload.get("title") or report.title or "REPORTE FOTOGRÁFICO DE OBRA").strip()
    report.week = (payload.get("reportWeek") or payload.get("week") or report.week or "").strip()
    report.report_date = _coerce_date(payload.get("reportDate") or payload.get("date"))
    report.labor_date_from = _coerce_date(payload.get("laborDateFrom"))
    report.labor_date_to = _coerce_date(payload.get("laborDateTo"))
    report.for_whom = (payload.get("forWhom") or "").strip()
    report.from_whom = (payload.get("fromWhom") or "").strip()
    report.objective_text = (payload.get("objectiveText") or "").strip()
    report.analysis_text = (payload.get("analysisText") or "").strip()
    report.conclusion_text = (payload.get("conclusionText") or "").strip()
    report.recommendation_text = (payload.get("recommendationText") or "").strip()
    report.conclusion_items = _coerce_list(payload.get("conclusionItems"))
    report.recommendation_items = _coerce_list(payload.get("recommendationItems"))
    report.auto_merge_dup = str(payload.get("autoMergeDup", report.auto_merge_dup)).lower() in {"1", "true", "yes"}
    report.combine_by_status = str(payload.get("combineByStatus", report.combine_by_status)).lower() in {"1", "true", "yes"}
    if payload.get("clearCover") in {True, "true", "1", 1}:
        if report.cover_image:
            report.cover_image.delete(save=False)
        report.cover_image = None
    if files and files.get("coverPhoto"):
        report.cover_image = files["coverPhoto"]


@login_required
def home(request, project_slug=None, report_id=None, front_id=None, new_report=False, new_project=False, edit_project=False):
    context = {
        "project_form": ProjectForm(),
        "report_form": ReportMetaForm(),
        "report_type_form": ReportTypeForm(),
        "report_id": report_id,
        "front_id": front_id,
        "new_report": new_report,
        "new_project": new_project,
        "edit_project": edit_project,
    }
    if project_slug:
        context["project_slug"] = project_slug
    return render(request, "report_app/home.html", context)


@login_required
def panel(request, new_project=False):
    return home(request, new_project=new_project)


def root_redirect(request):
    if not request.user.is_authenticated:
        return redirect("login")
    return redirect("panel_principal")


def register(request):
    if request.user.is_authenticated:
        return redirect("panel_principal")

    form = SignUpForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        user = form.save()
        login(request, user)
        return redirect("panel_principal")
    return render(request, "registration/register.html", {"form": form})


@login_required
@require_http_methods(["GET", "POST"])
def project_collection_api(request):
    if request.method == "GET":
        projects = [_serialize_project(project, request.user) for project in _project_queryset_for_user(request.user)]
        return JsonResponse({"projects": projects})

    payload = _parse_json(request)
    if payload is None:
        return HttpResponseBadRequest("JSON inválido")

    project_name = (payload.get("projectName") or "").strip()
    if not project_name:
        return JsonResponse({"error": "El nombre del proyecto es obligatorio."}, status=400)

    project = ReportProject.objects.create(
        owner=request.user,
        company_name=(payload.get("companyName") or "VDC CONSTRUCCIONES SAC").strip() or "VDC CONSTRUCCIONES SAC",
        project_name=project_name,
        project_location=(payload.get("projectLocation") or "").strip(),
        report_title=(payload.get("reportTitle") or "REPORTE FOTOGRÁFICO DE OBRA").strip() or "REPORTE FOTOGRÁFICO DE OBRA",
        for_whom=(payload.get("forWhom") or "").strip(),
        from_whom=(payload.get("fromWhom") or "").strip(),
    )
    project = _get_project_or_404(request.user, project.slug)
    return JsonResponse({"project": _serialize_project(project, request.user)}, status=201)


@login_required
@require_http_methods(["PATCH", "DELETE"])
def project_detail_api(request, project_slug):
    project = _get_project_or_404(request.user, project_slug)

    if request.method == "DELETE":
        if project.owner_id != request.user.id:
            return JsonResponse({"error": "Solo el propietario puede eliminar el proyecto."}, status=403)
        project.delete()
        return JsonResponse({"ok": True})

    if not _can_edit_project(project, request.user):
        return JsonResponse({"error": "No tienes permisos para editar este proyecto."}, status=403)

    payload = _parse_json(request)
    if payload is None:
        return HttpResponseBadRequest("JSON inválido")
    project_name = (payload.get("projectName") or "").strip()
    if not project_name:
        return JsonResponse({"error": "El nombre del proyecto es obligatorio."}, status=400)

    project.company_name = (payload.get("companyName") or project.company_name).strip() or "VDC CONSTRUCCIONES SAC"
    project.project_name = project_name
    project.project_location = (payload.get("projectLocation") or "").strip()
    project.report_title = (payload.get("reportTitle") or project.report_title).strip() or project.report_title
    project.for_whom = (payload.get("forWhom") or project.for_whom).strip()
    project.from_whom = (payload.get("fromWhom") or project.from_whom).strip()
    project.save()
    project = _get_project_or_404(request.user, project.slug)
    return JsonResponse({"project": _serialize_project(project, request.user)})


@login_required
@require_http_methods(["POST"])
def project_members_api(request, project_slug):
    project = _get_project_or_404(request.user, project_slug)
    if not _can_share_project(project, request.user):
        return JsonResponse({"error": "Solo el propietario puede compartir el proyecto."}, status=403)

    payload = _parse_json(request)
    if payload is None:
        return HttpResponseBadRequest("JSON inválido")

    username = (payload.get("username") or "").strip()
    role = (payload.get("role") or ProjectMembership.ROLE_VIEWER).strip()
    if not username:
        return JsonResponse({"error": "Debes indicar el usuario a invitar."}, status=400)
    if role not in dict(ProjectMembership.ROLE_CHOICES):
        return JsonResponse({"error": "Rol no válido."}, status=400)

    invitee = get_object_or_404(User, username=username)
    if invitee.id == project.owner_id:
        return JsonResponse({"error": "El propietario ya tiene acceso total."}, status=400)

    ProjectMembership.objects.update_or_create(
        project=project,
        user=invitee,
        defaults={"role": role},
    )
    project = _get_project_or_404(request.user, project.slug)
    return JsonResponse({"members": _serialize_members(project)})


@login_required
@require_http_methods(["POST"])
def project_reports_api(request, project_slug):
    project = _get_project_or_404(request.user, project_slug)
    if not _can_edit_project(project, request.user):
        return JsonResponse({"error": "No tienes permisos para crear reportes en este proyecto."}, status=403)

    payload = _request_data(request)
    if payload is None:
        return HttpResponseBadRequest("Datos inválidos")

    report = ProjectReport(project=project)
    _apply_report_payload(report, payload, request.FILES)
    report.save()
    project = _get_project_or_404(request.user, project.slug)
    report = _get_report_or_404(project, report.id)
    return JsonResponse({"report": _serialize_report(report)}, status=201)


@login_required
@require_http_methods(["POST"])
def project_report_update_api(request, project_slug, report_id):
    project = _get_project_or_404(request.user, project_slug)
    report = _get_report_or_404(project, report_id)
    if not _can_edit_project(project, request.user):
        return JsonResponse({"error": "No tienes permisos para editar este reporte."}, status=403)

    payload = _request_data(request)
    if payload is None:
        return HttpResponseBadRequest("Datos inválidos")
    _apply_report_payload(report, payload, request.FILES)
    report.save()
    return JsonResponse({"report": _serialize_report(report)})


@login_required
@require_http_methods(["DELETE"])
def project_report_detail_api(request, project_slug, report_id):
    project = _get_project_or_404(request.user, project_slug)
    report = _get_report_or_404(project, report_id)
    if not _can_edit_project(project, request.user):
        return JsonResponse({"error": "No tienes permisos para eliminar este reporte."}, status=403)
    report.delete()
    return JsonResponse({"ok": True})


@login_required
@require_http_methods(["POST"])
def report_fronts_api(request, project_slug, report_id):
    project = _get_project_or_404(request.user, project_slug)
    report = _get_report_or_404(project, report_id)
    if not _can_edit_project(project, request.user):
        return JsonResponse({"error": "No tienes permisos para editar este reporte."}, status=403)

    payload = _parse_json(request)
    if payload is None:
        return HttpResponseBadRequest("JSON inválido")
    name = (payload.get("name") or "").strip()
    if not name:
        return JsonResponse({"error": "El nombre del frente es obligatorio."}, status=400)

    front = ReportFront.objects.create(report=report, name=name, sort_order=report.fronts.count())
    return JsonResponse({"front": {"id": front.id, "name": front.name}}, status=201)


@login_required
@require_http_methods(["DELETE"])
def report_front_detail_api(request, project_slug, report_id, front_id):
    project = _get_project_or_404(request.user, project_slug)
    report = _get_report_or_404(project, report_id)
    if not _can_edit_project(project, request.user):
        return JsonResponse({"error": "No tienes permisos para eliminar frentes en este reporte."}, status=403)
    front = get_object_or_404(report.fronts.all(), pk=front_id)
    front.delete()
    return JsonResponse({"ok": True})


@login_required
@require_http_methods(["POST"])
def report_entries_api(request, project_slug, report_id):
    project = _get_project_or_404(request.user, project_slug)
    report = _get_report_or_404(project, report_id)
    if not _can_edit_project(project, request.user):
        return JsonResponse({"error": "No tienes permisos para crear issues en este reporte."}, status=403)

    payload = _request_data(request)
    if payload is None:
        return HttpResponseBadRequest("Datos inválidos")
    front_id = payload.get("frontId")
    status = (payload.get("status") or "").strip()
    description = (payload.get("desc") or "").strip()
    if not front_id or not status:
        return JsonResponse({"error": "Frente y estado son obligatorios."}, status=400)
    front = get_object_or_404(report.fronts.all(), pk=front_id)
    entry = ReportEntry.objects.create(report=report, front=front, status=status, description=description)
    for index, image in enumerate(request.FILES.getlist("images")):
        EntryImage.objects.create(entry=entry, image=image, sort_order=index)
    entry = ReportEntry.objects.prefetch_related("images").get(pk=entry.pk)
    return JsonResponse({"entry": _serialize_entry(entry)}, status=201)


@login_required
@require_http_methods(["POST", "DELETE"])
def report_entry_detail_api(request, project_slug, report_id, entry_id):
    project = _get_project_or_404(request.user, project_slug)
    report = _get_report_or_404(project, report_id)
    entry = get_object_or_404(report.entries.prefetch_related("images"), pk=entry_id)
    if not _can_edit_project(project, request.user):
        return JsonResponse({"error": "No tienes permisos para modificar este issue."}, status=403)

    if request.method == "DELETE":
        entry.delete()
        return JsonResponse({"ok": True})

    payload = _request_data(request)
    if payload is None:
        return HttpResponseBadRequest("Datos inválidos")
    front_id = payload.get("frontId") or entry.front_id
    status = (payload.get("status") or entry.status).strip()
    description = (payload.get("desc") or entry.description or "").strip()
    entry.front = get_object_or_404(report.fronts.all(), pk=front_id)
    entry.status = status
    entry.description = description
    entry.save()

    replace_images = str(payload.get("replaceImages", "false")).lower() in {"1", "true", "yes"}
    new_images = request.FILES.getlist("images")
    if replace_images and entry.images.exists():
        entry.images.all().delete()
    if new_images:
        if replace_images:
            entry.images.all().delete()
        next_order = entry.images.count()
        for index, image in enumerate(new_images, start=next_order):
            EntryImage.objects.create(entry=entry, image=image, sort_order=index)

    entry = ReportEntry.objects.prefetch_related("images").get(pk=entry.pk)
    return JsonResponse({"entry": _serialize_entry(entry)})
