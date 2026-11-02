import json
import hashlib
import logging
import math
import secrets
import zipfile
from io import BytesIO
from decimal import Decimal, InvalidOperation
from datetime import datetime, timedelta
from functools import wraps
from base64 import b64decode
from binascii import Error as Base64DecodeError
from html import escape as escape_html
from pathlib import Path
from urllib.parse import urlencode, urlparse

import requests
from django.conf import settings
from django.contrib.auth import login
from django.contrib.auth.hashers import check_password, make_password
from django.contrib.auth.decorators import login_required
from django.contrib.auth.models import User
from django.contrib.auth.views import LoginView, redirect_to_login
from django.contrib.staticfiles import finders
from django.core import signing
from django.core.files.base import ContentFile
from django.core.files.uploadedfile import SimpleUploadedFile
from django.db import transaction
from django.db.models import Prefetch, Q
from django.http import Http404, HttpResponse, HttpResponseBadRequest, JsonResponse
from django.middleware.csrf import get_token
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.urls import reverse
from django.views.decorators.csrf import csrf_exempt, ensure_csrf_cookie
from django.views.decorators.http import require_http_methods

from .forms import ProjectForm, ReportMetaForm, ReportTypeForm, SignUpForm
from .models import (
    EntryImage,
    MaterialReceipt,
    MaterialReceiptPhoto,
    MobilityExpense,
    ProjectMembership,
    ProjectPlan,
    ProjectPlanMarker,
    ProjectReport,
    PublicReportShare,
    ReportEntry,
    ReportFront,
    ReportMembership,
    ReportProject,
    SiteBranding,
    UserProfile,
)

ROLE_LABELS = dict(ProjectMembership.ROLE_CHOICES)
PROGRESS_ENTRY_STATUSES = {"En proceso", "Terminado", "Pendiente", "Observado"}
INCIDENT_ENTRY_STATUSES = {"Abierto", "Cerrado", "Borrador"}
MATERIAL_CONDITIONS = {"Conforme", "Observado", "Dañado", "Pendiente"}
MAX_PUBLIC_IMAGE_PIXELS = 20_000_000
MATERIAL_RECEIPT_SHARE_SIGNERS = {
    "delivered": {
        "label": "ENTREGA – UNIVERSIDAD DE LIMA",
        "password_field": "delivered_share_password",
        "name_field": "delivered_by",
        "dni_field": "delivered_dni",
        "position_field": "delivered_position",
        "signature_field": "signature_delivered",
        "signed_on_field": "delivered_signed_on",
    },
    "verified": {
        "label": "VALIDA - VDC",
        "password_field": "verified_share_password",
        "name_field": "verified_by",
        "dni_field": "verified_dni",
        "position_field": "verified_position",
        "signature_field": "signature_verified",
        "signed_on_field": "verified_signed_on",
    },
    "received": {
        "label": "RECIBE / VALIDA - COSAPI",
        "password_field": "received_share_password",
        "name_field": "received_by",
        "dni_field": "received_dni",
        "position_field": "received_position",
        "signature_field": "signature_received",
        "signed_on_field": "received_signed_on",
    },
}
MATERIAL_RECEIPT_SIGNING_ORDER = ("delivered", "verified", "received")
logger = logging.getLogger(__name__)


def _coerce_decimal(value):
    if value is None:
        return Decimal("0")
    try:
        return Decimal(str(value).replace(",", ".").strip())
    except (InvalidOperation, TypeError, ValueError):
        return Decimal("0")


def _apply_partial_payment(payment_amount):
    payment_total = _coerce_decimal(payment_amount)
    if payment_total <= 0:
        raise ValueError("El abono debe ser mayor a cero.")

    remaining = payment_total
    expenses = list(MobilityExpense.objects.all().order_by("date", "id"))
    for expense in expenses:
        if remaining <= 0:
            break
        if expense.amount <= expense.paid_amount:
            expense.sync_status_from_payment()
            expense.save(update_fields=["paid_amount", "status", "updated_at"])
            continue

        available = expense.amount - expense.paid_amount
        applied = min(remaining, available)
        expense.paid_amount += applied
        remaining -= applied
        expense.sync_status_from_payment()
        expense.save(update_fields=["paid_amount", "status", "updated_at"])

    return payment_total - remaining


def mobility_expenses(request):
    expenses = MobilityExpense.objects.all()
    editing_id = request.GET.get("edit") or request.POST.get("expense_id")
    expense_to_edit = None
    if editing_id:
        expense_to_edit = get_object_or_404(MobilityExpense, pk=editing_id)

    form_values = request.POST if request.method == "POST" else None

    if request.method == "POST":
        payment_amount_value = (request.POST.get("payment_amount") or "").strip()
        if payment_amount_value:
            try:
                _apply_partial_payment(payment_amount_value)
            except ValueError as exc:
                return render(request, "report_app/mobility_entry.html", {
                    "expenses": expenses,
                    "expense_to_edit": expense_to_edit,
                    "form_values": form_values,
                    "error": str(exc),
                }, status=400)
            return redirect("mobility_entry")

        if request.POST.get("action") == "delete":
            expense_to_delete = get_object_or_404(MobilityExpense, pk=request.POST.get("expense_id"))
            expense_to_delete.delete()
            return redirect("mobility_entry")

        date = _coerce_date(request.POST.get("date"))
        amount_text = (request.POST.get("amount") or "").replace(",", ".").strip()
        try:
            amount = Decimal(amount_text)
        except InvalidOperation:
            amount = Decimal("0")
        if not date or amount <= 0:
            return render(request, "report_app/mobility_entry.html", {
                "expenses": expenses,
                "expense_to_edit": expense_to_edit,
                "form_values": form_values,
                "error": "Ingresa una fecha y un monto mayor que cero.",
            }, status=400)

        selected_status = request.POST.get("status") if request.POST.get("status") in dict(MobilityExpense.STATUS_CHOICES) else MobilityExpense.STATUS_PENDING
        current_paid = expense_to_edit.paid_amount if expense_to_edit else Decimal("0")
        payload = {
            "date": date,
            "amount": amount,
            "paid_amount": amount if selected_status == MobilityExpense.STATUS_PAID else min(current_paid, amount),
            "transport": "",
            "origin": "",
            "destination": "",
            "status": selected_status,
            "notes": (request.POST.get("notes") or "").strip(),
        }
        receipt = request.FILES.get("receipt")
        if receipt is not None:
            payload["receipt"] = receipt

        if expense_to_edit:
            for key, value in payload.items():
                setattr(expense_to_edit, key, value)
            expense_to_edit.sync_status_from_payment()
            expense_to_edit.save()
        else:
            expense = MobilityExpense.objects.create(**payload)
            expense.sync_status_from_payment()
            expense.save(update_fields=["paid_amount", "status", "updated_at"])
        return redirect("mobility_entry")

    return render(request, "report_app/mobility_entry.html", {
        "expenses": expenses,
        "expense_to_edit": expense_to_edit,
        "form_values": form_values,
        "form_date": expense_to_edit.date.isoformat() if expense_to_edit else "",
        "form_amount": format(expense_to_edit.amount, ".2f") if expense_to_edit else "",
        "form_status": expense_to_edit.status if expense_to_edit else "",
        "form_notes": expense_to_edit.notes if expense_to_edit else "",
        "total": sum((expense.amount for expense in expenses), Decimal("0")),
        "total_paid": sum((expense.paid_amount for expense in expenses), Decimal("0")),
        "total_pending": sum((expense.due_amount for expense in expenses), Decimal("0")),
    })


def mobility_preview(request):
    expenses = MobilityExpense.objects.all().order_by("date", "id")
    for expense in expenses:
        expense.sync_status_from_payment()
        if expense.pk:
            expense.save(update_fields=["paid_amount", "status", "updated_at"])
    return render(request, "report_app/mobility_preview.html", {
        "expenses": expenses,
        "total": sum((expense.amount for expense in expenses), Decimal("0")),
        "total_paid": sum((expense.paid_amount for expense in expenses), Decimal("0")),
        "total_pending": sum((expense.due_amount for expense in expenses), Decimal("0")),
        "compact": True,
    })


def mobility_receipt(request, expense_id):
    expense = get_object_or_404(MobilityExpense, pk=expense_id)
    if not expense.receipt:
        return redirect("mobility_entry")
    return_to_preview = request.GET.get("from") == "preview"
    return render(request, "report_app/mobility_receipt.html", {
        "expense": expense,
        "is_pdf": expense.receipt.name.lower().endswith(".pdf"),
        "return_url": reverse("mobility_preview" if return_to_preview else "mobility_entry"),
    })


def _project_queryset_for_user(user):
    return ReportProject.objects.filter(
        Q(owner=user) | Q(memberships__user=user) | Q(reports__memberships__user=user)
    ).select_related("owner").prefetch_related(
        "memberships__user",
        Prefetch("plans", queryset=ProjectPlan.objects.prefetch_related("markers")),
        Prefetch(
            "reports",
            queryset=ProjectReport.objects.prefetch_related(
                "memberships__user",
                "fronts",
                "material_receipt__photos",
                Prefetch("entries", queryset=ReportEntry.objects.prefetch_related("images", "front")),
            ),
        ),
    ).distinct()


def _project_role_for_user(project, user):
    if project.owner_id == user.id:
        return ProjectMembership.ROLE_ADMIN
    membership = project.memberships.filter(user=user).first()
    return membership.role if membership else None


def _pick_most_restrictive_role(*roles):
    order = {
        ProjectMembership.ROLE_VIEWER: 1,
        ProjectMembership.ROLE_EDITOR: 2,
        ProjectMembership.ROLE_ADMIN: 3,
    }
    valid_roles = [role for role in roles if role in order]
    if not valid_roles:
        return None
    return min(valid_roles, key=lambda role: order[role])


def _effective_project_role_for_user(project, user):
    project_role = _project_role_for_user(project, user)
    if project_role:
        return project_role
    report_roles = [
        membership.role
        for membership in ReportMembership.objects.filter(report__project=project, user=user)
    ]
    if report_roles:
        return _pick_most_restrictive_role(*report_roles)
    return None


def _can_edit_project(project, user):
    if project.owner_id == user.id:
        return True
    role = _project_role_for_user(project, user)
    return role in {ProjectMembership.ROLE_ADMIN, ProjectMembership.ROLE_EDITOR}


def _can_share_project(project, user):
    return project.owner_id == user.id


def _serialize_project_members(project):
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


def _report_role_for_user(report, user):
    project_role = _project_role_for_user(report.project, user)
    if project_role:
        return project_role
    membership = report.memberships.filter(user=user).first()
    return membership.role if membership else None


def _can_edit_report(report, user):
    return _report_role_for_user(report, user) in {ProjectMembership.ROLE_ADMIN, ProjectMembership.ROLE_EDITOR}


def _can_share_report(report, user):
    return _report_role_for_user(report, user) == ProjectMembership.ROLE_ADMIN


def _user_can_access_report(report, user):
    return _report_role_for_user(report, user) is not None


def _serialize_report_members(report):
    members = []
    if report.project.owner_id:
      members.append({
          "username": report.project.owner.username,
          "role": ProjectMembership.ROLE_ADMIN,
          "isOwner": True,
      })
    for membership in report.memberships.select_related("user").all():
        members.append({
            "username": membership.user.username,
            "role": membership.role,
            "isOwner": False,
        })
    return members


def _parse_json(request):
    try:
        return json.loads(request.body.decode("utf-8") or "{}")
    except json.JSONDecodeError:
        return None


@login_required
@require_http_methods(["GET", "POST"])
def profile_api(request):
    profile, _ = UserProfile.objects.get_or_create(user=request.user)
    if request.method == "POST":
        request.user.first_name = (request.POST.get("firstName") or "").strip()
        request.user.last_name = (request.POST.get("lastName") or "").strip()
        request.user.save(update_fields=["first_name", "last_name"])
        if request.FILES.get("profilePhoto"):
            profile.profile_image = request.FILES["profilePhoto"]
            profile.save(update_fields=["profile_image"])
    return JsonResponse({
        "firstName": request.user.first_name,
        "lastName": request.user.last_name,
        "username": request.user.username,
        "email": request.user.email,
        "profileImage": profile.profile_image.url if profile.profile_image else "",
    })


def _request_data(request):
    if request.content_type and request.content_type.startswith("application/json"):
        return _parse_json(request)
    return request.POST


def _validate_public_report_images(uploaded_images, max_count=10):
    if len(uploaded_images) > max_count:
        return f"Puedes subir hasta {max_count} fotos por vez."

    from PIL import Image, UnidentifiedImageError

    allowed_formats = {"JPEG", "PNG", "WEBP"}
    for uploaded_image in uploaded_images:
        if not (uploaded_image.content_type or "").startswith("image/") or uploaded_image.size > 5 * 1024 * 1024:
            return "Cada foto debe ser una imagen de hasta 5 MB."
        try:
            image = Image.open(uploaded_image)
            if image.width * image.height > MAX_PUBLIC_IMAGE_PIXELS:
                return "La foto tiene demasiada resolución."
            image.verify()
        except (UnidentifiedImageError, OSError, Image.DecompressionBombError):
            return "Una de las fotos seleccionadas no es una imagen válida."
        if image.format not in allowed_formats:
            return "Las fotos deben estar en formato PNG, JPEG o WebP."
        uploaded_image.seek(0)
    return None


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


def _load_static_text(relative_path):
    absolute_path = finders.find(relative_path)
    if not absolute_path:
        return ""
    try:
        return Path(absolute_path).read_text(encoding="utf-8")
    except OSError:
        return ""


def _pdf_export_styles():
    bootstrap_utilities = """
    @page { size: A4; margin: 1.5mm; }
    html, body { margin: 0; padding: 0; background: #ffffff; }
    body { font-family: Arial, sans-serif; }
    .badge { display: inline-block; padding: 0.45em 0.8em; font-size: 0.85em; font-weight: 700; line-height: 1; text-align: center; white-space: nowrap; vertical-align: baseline; border-radius: 999px; }
    .bg-primary { background: #0d6efd !important; color: #ffffff !important; }
    .bg-success { background: #198754 !important; color: #ffffff !important; }
    .bg-secondary { background: #6c757d !important; color: #ffffff !important; }
    .bg-warning { background: #ffc107 !important; color: #111111 !important; }
    .text-dark { color: #111111 !important; }
    .pdf-export-shell { width: 207mm; margin: 0 auto; padding: 0; background: #ffffff; }
    .pdf-export-shell .report-container { width: 100% !important; max-width: none !important; margin: 0 !important; padding: 0 !important; border: none !important; border-radius: 0 !important; box-shadow: none !important; }
    .pdf-export-shell .report-page,
    .pdf-export-shell .report-cover,
    .pdf-export-shell .report-secondary-page,
    .pdf-export-shell .report-front-page { width: 100% !important; min-height: 294mm !important; height: 294mm !important; margin: 0 !important; page-break-after: always !important; break-after: page !important; page-break-inside: avoid !important; break-inside: avoid !important; }
    .pdf-export-shell .report-page:last-child { page-break-after: auto !important; break-after: auto !important; margin-bottom: 0 !important; }
    .pdf-export-shell .report-info-page-content { align-items: stretch !important; }
    .pdf-export-shell .report-info-page-content .secondary-head,
    .pdf-export-shell .report-info-page-content .secondary-photo-wrap,
    .pdf-export-shell .report-info-page-content .secondary-meta-row { width: 100% !important; max-width: none !important; }
    .pdf-export-shell .report-entry-body { grid-template-columns: minmax(0, 0.9fr) minmax(0, 1.1fr) !important; }
    .pdf-export-shell .report-entry-text,
    .pdf-export-shell .report-entry-desc,
    .pdf-export-shell .report-section-body,
    .pdf-export-shell .report-section-subtitle,
    .pdf-export-shell .report-list-items,
    .pdf-export-shell .report-list-items li,
    .pdf-export-shell .report-subsection-title { overflow-wrap: anywhere !important; word-break: break-word !important; }
    .pdf-export-shell .report-entry-images { justify-items: center !important; }
    .pdf-export-shell .report-entry-image-frame { width: 100% !important; max-height: 112mm !important; }
    .pdf-export-shell .thumb { max-width: 100% !important; max-height: 112mm !important; }
    """
    return "\n".join([
        bootstrap_utilities,
        _load_static_text("report_app/theme.css"),
        _load_static_text("report_app/styles.css"),
    ])


def _build_pdf_export_document(report_html, base_url):
    return f"""<!doctype html>
<html lang=\"es\">
<head>
  <meta charset=\"utf-8\">
  <meta name=\"viewport\" content=\"width=device-width, initial-scale=1\">
    <base href=\"{base_url}\">
  <style>{_pdf_export_styles()}</style>
</head>
<body>
  <div class=\"pdf-export-shell\">
    <div class=\"report-container\">{report_html}</div>
  </div>
</body>
</html>"""


def _sanitize_pdf_filename(value):
    raw = str(value or "reporte").strip() or "reporte"
    safe = "".join(character if character.isalnum() or character in {"-", "_", "."} else "_" for character in raw)
    return safe if safe.lower().endswith(".pdf") else f"{safe}.pdf"


def _linearize_pdf(pdf_bytes):
    import pikepdf

    optimized_output = BytesIO()
    with pikepdf.open(BytesIO(pdf_bytes)) as document:
        document.save(
            optimized_output,
            linearize=True,
            compress_streams=True,
            recompress_flate=True,
            object_stream_mode=pikepdf.ObjectStreamMode.generate,
        )
    return optimized_output.getvalue()


def _serialize_entry(entry):
    return {
        "id": entry.id,
        "frontId": entry.front_id,
        "itemName": entry.item_name or "",
        "buildingLocation": entry.building_location or "",
        "quantity": entry.quantity or 1,
        "unit": entry.unit or "",
        "condition": entry.condition or "",
        "status": entry.status,
        "incidentDate": entry.incident_date.isoformat() if entry.incident_date else "",
        "responsibleCompany": entry.responsible_company or "",
        "planId": entry.plan_id,
        "planX": entry.plan_x,
        "planY": entry.plan_y,
        "desc": entry.description,
        "imageItems": [
            {
                "id": image.id,
                "url": image.image.url,
                "name": image.image.name.rsplit("/", 1)[-1],
            }
            for image in entry.images.all()
            if image.image
        ],
        "images": [image.image.url for image in entry.images.all() if image.image],
        "ts": entry.updated_at.isoformat(),
    }


def _serialize_material_receipt(report):
    empty_receipt = {
        "actNumber": "",
        "receiptDate": "",
        "deliveryLocation": "",
        "supplier": "",
        "deliveryNote": "",
        "deliveredBy": "",
        "deliveredDni": "",
        "deliveredPosition": "",
        "receivedBy": "",
        "receivedDni": "",
        "receivedPosition": "",
        "verifiedBy": "",
        "verifiedDni": "",
        "verifiedPosition": "",
        "conformity": "",
        "observations": "",
        "companyLogo": "",
        "photos": [],
        "shareConfigured": False,
        "signedOn": {"delivered": "", "received": "", "verified": ""},
        "signatures": {"delivered": "", "received": "", "verified": ""},
    }
    if report.report_type != ProjectReport.TYPE_MATERIAL_RECEIPT:
        return empty_receipt
    receipt = getattr(report, "material_receipt", None)
    if not receipt:
        return empty_receipt
    return {
        "actNumber": receipt.act_number,
        "receiptDate": receipt.receipt_date.isoformat() if receipt.receipt_date else "",
        "deliveryLocation": receipt.delivery_location,
        "supplier": receipt.supplier,
        "deliveryNote": receipt.delivery_note,
        "deliveredBy": receipt.delivered_by,
        "deliveredDni": receipt.delivered_dni,
        "deliveredPosition": receipt.delivered_position,
        "receivedBy": receipt.received_by,
        "receivedDni": receipt.received_dni,
        "receivedPosition": receipt.received_position,
        "verifiedBy": receipt.verified_by,
        "verifiedDni": receipt.verified_dni,
        "verifiedPosition": receipt.verified_position,
        "conformity": receipt.conformity,
        "observations": receipt.observations,
        "companyLogo": receipt.company_logo.url if receipt.company_logo else "",
        "photos": [
            {"id": photo.pk, "url": photo.image.url, "name": photo.image.name.rsplit("/", 1)[-1]}
            for photo in receipt.photos.all()
        ],
        "shareConfigured": bool(
            receipt.share_token
            and all(getattr(receipt, signer["password_field"]) for signer in MATERIAL_RECEIPT_SHARE_SIGNERS.values())
        ),
        "signedOn": {
            "delivered": receipt.delivered_signed_on.isoformat() if receipt.delivered_signed_on else "",
            "received": receipt.received_signed_on.isoformat() if receipt.received_signed_on else "",
            "verified": receipt.verified_signed_on.isoformat() if receipt.verified_signed_on else "",
        },
        "signatures": {
            "delivered": receipt.signature_delivered.url if receipt.signature_delivered else "",
            "received": receipt.signature_received.url if receipt.signature_received else "",
            "verified": receipt.signature_verified.url if receipt.signature_verified else "",
        },
    }


def _serialize_report(report, user):
    role = _report_role_for_user(report, user)
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
        "materialReceipt": _serialize_material_receipt(report),
        "canRemoveSharedReceiptSignatures": report.project.owner_id == user.id,
        "fronts": [{"id": front.id, "name": front.name} for front in report.fronts.all()],
        "entries": [_serialize_entry(entry) for entry in report.entries.all()],
        "autoMergeDup": report.auto_merge_dup,
        "combineByStatus": report.combine_by_status,
        "editingEntryId": None,
        "showIssueForm": False,
        "showPreviewMode": False,
        "metaComplete": True,
        "currentFrontId": None,
        "accessRole": role,
        "canEdit": _can_edit_report(report, user),
        "canShare": _can_share_report(report, user),
        "members": _serialize_report_members(report),
    }


def _project_plan_url(project, plan):
    return reverse("project_plan_file_api", kwargs={"project_slug": project.slug, "plan_id": plan.id})


def _serialize_project(project, user):
    role = _effective_project_role_for_user(project, user)
    is_owner = project.owner_id == user.id
    can_edit = _can_edit_project(project, user)
    can_share = is_owner
    visible_reports = [report for report in project.reports.all() if _user_can_access_report(report, user)]
    owner_display = project.owner.get_full_name().strip() or project.owner.username
    return {
        "id": project.id,
        "dbId": project.id,
        "slug": project.slug,
        "companyName": project.company_name,
        "projectName": project.project_name,
        "projectLocation": project.project_location,
        "projectImage": project.project_image.url if project.project_image else "",
        "plans": [{
            "id": plan.id,
            "name": plan.name or plan.file.name.rsplit("/", 1)[-1],
            "url": _project_plan_url(project, plan),
            "createdAt": plan.created_at.isoformat(),
            "markers": [{"id": marker.id, "page": marker.page, "x": marker.x, "y": marker.y} for marker in plan.markers.all()],
        } for plan in project.plans.all()],
        "reportTitle": project.report_title,
        "forWhom": project.for_whom,
        "fromWhom": project.from_whom,
        "responsibleCompanies": project.responsible_companies or [],
        "ownerUsername": project.owner.username,
        "ownerDisplayName": owner_display,
        "sharedByUsername": None if is_owner else project.owner.username,
        "sharedByDisplayName": None if is_owner else owner_display,
        "accessRole": role,
        "accessRoleLabel": ROLE_LABELS.get(role, ""),
        "canEdit": can_edit,
        "canShare": can_share,
        "canDelete": is_owner,
        "isOwned": is_owner,
        "members": _serialize_project_members(project),
        "reports": [_serialize_report(report, user) for report in visible_reports],
    }


def _get_project_or_404(user, slug):
    return get_object_or_404(_project_queryset_for_user(user), slug=slug)


def _get_report_or_404(project, report_id):
    return get_object_or_404(project.reports.all(), pk=report_id)


def _get_user_report_or_404(project, user, report_id):
    report = _get_report_or_404(project, report_id)
    if not _user_can_access_report(report, user):
        raise Http404()
    return report


PUBLIC_REPORT_SHARE_SESSION_TOKEN = "public_report_share_token"
PUBLIC_REPORT_SHARE_SESSION_VERSION = "public_report_share_version"


def _public_report_share_for_request(request):
    token = request.session.get(PUBLIC_REPORT_SHARE_SESSION_TOKEN)
    version = request.session.get(PUBLIC_REPORT_SHARE_SESSION_VERSION)
    if not token or version is None:
        return None

    share = PublicReportShare.objects.select_related("report__project").filter(
        token=token,
        is_active=True,
        access_version=version,
    ).first()
    if share is None:
        request.session.pop(PUBLIC_REPORT_SHARE_SESSION_TOKEN, None)
        request.session.pop(PUBLIC_REPORT_SHARE_SESSION_VERSION, None)
    return share


def _report_access_required(view):
    @wraps(view)
    def wrapped(request, *args, **kwargs):
        if not request.user.is_authenticated and not _public_report_share_for_request(request):
            return redirect_to_login(request.get_full_path())
        return view(request, *args, **kwargs)
    return wrapped


def _private_no_store(response):
    response["Cache-Control"] = "private, no-store"
    return response


def _report_access_for_request(request, project_slug, report_id):
    share = None if request.user.is_authenticated else _public_report_share_for_request(request)
    if share:
        if share.report.project.slug != project_slug or share.report_id != report_id:
            raise Http404()
        return share.report.project, share.report, True
    if not request.user.is_authenticated:
        raise Http404()
    project = _get_project_or_404(request.user, project_slug)
    report = _get_user_report_or_404(project, request.user, report_id)
    return project, report, False


def _serialize_public_report_project(share):
    project = share.report.project
    owner_display = project.owner.get_full_name().strip() or project.owner.username
    report_data = _serialize_report(share.report, project.owner)
    report_data["members"] = []
    report_data["canShare"] = False
    report_data["canEdit"] = True
    report_data["accessRole"] = ProjectMembership.ROLE_EDITOR
    linked_plan_ids = share.report.entries.exclude(plan_id__isnull=True).values_list("plan_id", flat=True).distinct()
    plans = project.plans.filter(pk__in=linked_plan_ids).prefetch_related("markers")
    return {
        "id": project.id,
        "dbId": project.id,
        "slug": project.slug,
        "companyName": project.company_name,
        "projectName": project.project_name,
        "projectLocation": project.project_location,
        "projectImage": project.project_image.url if project.project_image else "",
        "plans": [{
            "id": plan.id,
            "name": plan.name or plan.file.name.rsplit("/", 1)[-1],
            "url": _project_plan_url(project, plan),
            "createdAt": plan.created_at.isoformat(),
            "markers": [{"id": marker.id, "page": marker.page, "x": marker.x, "y": marker.y} for marker in plan.markers.all()],
        } for plan in plans],
        "reportTitle": project.report_title,
        "forWhom": project.for_whom,
        "fromWhom": project.from_whom,
        "responsibleCompanies": project.responsible_companies or [],
        "ownerUsername": project.owner.username,
        "ownerDisplayName": owner_display,
        "sharedByUsername": project.owner.username,
        "sharedByDisplayName": owner_display,
        "accessRole": ProjectMembership.ROLE_EDITOR,
        "accessRoleLabel": ROLE_LABELS[ProjectMembership.ROLE_EDITOR],
        "canEdit": True,
        "canShare": False,
        "canDelete": False,
        "isOwned": False,
        "members": [],
        "reports": [report_data],
    }


def _get_site_branding():
    return SiteBranding.objects.order_by("-updated_at", "-created_at").first()


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


def home(request, project_slug=None, report_id=None, front_id=None, new_report=False, new_project=False, edit_project=False):
    public_share = None
    if not request.user.is_authenticated:
        public_share = _public_report_share_for_request(request)
        if not public_share:
            return redirect_to_login(request.get_full_path())
        if (
            public_share.report.project.slug != project_slug
            or public_share.report_id != report_id
        ):
            raise Http404()

    context = {
        "project_form": ProjectForm(),
        "report_form": ReportMetaForm(),
        "report_type_form": ReportTypeForm(),
        "site_branding": _get_site_branding(),
        "report_id": report_id,
        "front_id": front_id,
        "new_report": new_report,
        "new_project": new_project,
        "edit_project": edit_project,
        "public_share": public_share,
    }
    if project_slug:
        context["project_slug"] = project_slug
    response = render(request, "report_app/home.html", context)
    return _private_no_store(response) if public_share else response


@require_http_methods(["GET", "POST"])
@ensure_csrf_cookie
def public_report_share(request, share_token):
    share = get_object_or_404(
        PublicReportShare.objects.select_related("report__project"),
        token=share_token,
        is_active=True,
    )

    if request.method == "POST":
        if share.locked_until and share.locked_until > timezone.now():
            return _private_no_store(render(request, "report_app/public_report_share.html", {
                "site_branding": _get_site_branding(),
                "share_token": share_token,
                "error": "Se alcanzó el límite de intentos. Prueba nuevamente más tarde.",
                "locked": True,
            }, status=429))

        password = request.POST.get("password", "")
        if not check_password(password, share.password_hash):
            share.failed_attempts += 1
            if share.failed_attempts >= 5:
                share.failed_attempts = 0
                share.locked_until = timezone.now() + timedelta(minutes=15)
            share.save(update_fields=["failed_attempts", "locked_until", "updated_at"])
            return _private_no_store(render(request, "report_app/public_report_share.html", {
                "site_branding": _get_site_branding(),
                "share_token": share_token,
                "error": "La contraseña no es correcta.",
            }, status=401))

        share.failed_attempts = 0
        share.locked_until = None
        share.save(update_fields=["failed_attempts", "locked_until", "updated_at"])
        request.session.cycle_key()
        request.session[PUBLIC_REPORT_SHARE_SESSION_TOKEN] = share.token
        request.session[PUBLIC_REPORT_SHARE_SESSION_VERSION] = share.access_version
        return redirect("reporte_detail", project_slug=share.report.project.slug, report_id=share.report_id)

    existing_share = _public_report_share_for_request(request)
    if existing_share and existing_share.pk == share.pk:
        return redirect("reporte_detail", project_slug=share.report.project.slug, report_id=share.report_id)
    return _private_no_store(render(request, "report_app/public_report_share.html", {
        "site_branding": _get_site_branding(),
        "share_token": share_token,
    }))


def panel(request, new_project=False):
    if not request.user.is_authenticated:
        share = _public_report_share_for_request(request)
        if share:
            return redirect(
                "reporte_detail",
                project_slug=share.report.project.slug,
                report_id=share.report_id,
            )
        return redirect_to_login(request.get_full_path())
    return home(request, new_project=new_project)


def legacy_project_root(request):
    if not request.user.is_authenticated:
        share = _public_report_share_for_request(request)
        if share:
            return redirect(
                "reporte_detail",
                project_slug=share.report.project.slug,
                report_id=share.report_id,
            )
        return redirect_to_login(request.get_full_path())
    return redirect("panel_principal")


def root_redirect(request):
    if not request.user.is_authenticated:
        share = _public_report_share_for_request(request)
        if share:
            return redirect(
                "reporte_detail",
                project_slug=share.report.project.slug,
                report_id=share.report_id,
            )
        return redirect("login")
    return redirect("panel_principal")


def register(request):
    if request.user.is_authenticated:
        profile = getattr(request.user, "profile", None)
        if profile and profile.is_approved:
            return redirect("panel_principal")
        return redirect("registration_pending")

    form = SignUpForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        user = form.save()
        UserProfile.objects.update_or_create(user=user, defaults={"is_approved": False})
        login(request, user)
        return redirect("registration_pending")
    return render(request, "registration/register.html", {"form": form, "site_branding": _get_site_branding()})


def registration_pending(request):
    if not request.user.is_authenticated:
        return redirect("login")
    profile = getattr(request.user, "profile", None)
    if request.user.is_superuser or (profile and profile.is_approved):
        return redirect("panel_principal")
    return render(request, "registration/pending.html", {"site_branding": _get_site_branding()})


class CustomLoginView(LoginView):
    template_name = "registration/login.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["site_branding"] = _get_site_branding()
        return context

    def form_valid(self, form):
        user = form.get_user()
        profile = getattr(user, "profile", None)
        if not user.is_superuser and (profile is None or not profile.is_approved):
            form.add_error(None, "Tu cuenta está pendiente de aprobación. Te avisaremos cuando puedas entrar.")
            return self.form_invalid(form)
        return super().form_valid(form)


@require_http_methods(["GET", "POST"])
def project_collection_api(request):
    if not request.user.is_authenticated:
        share = _public_report_share_for_request(request)
        if not share:
            return redirect_to_login(request.get_full_path())
        if request.method != "GET":
            return JsonResponse({"error": "Inicia sesión para continuar."}, status=403)
        return _private_no_store(JsonResponse({"projects": [_serialize_public_report_project(share)]}))

    profile = getattr(request.user, "profile", None)
    if not request.user.is_superuser and profile and not profile.is_approved:
        return JsonResponse({"error": "Tu cuenta está pendiente de aprobación."}, status=403)

    if request.method == "GET":
        projects = [_serialize_project(project, request.user) for project in _project_queryset_for_user(request.user)]
        return JsonResponse({"projects": projects})

    payload = _request_data(request)
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
        project_image=request.FILES.get("projectPhoto"),
        report_title=(payload.get("reportTitle") or "REPORTE FOTOGRÁFICO DE OBRA").strip() or "REPORTE FOTOGRÁFICO DE OBRA",
        for_whom=(payload.get("forWhom") or "").strip(),
        from_whom=(payload.get("fromWhom") or "").strip(),
    )
    project = _get_project_or_404(request.user, project.slug)
    return JsonResponse({"project": _serialize_project(project, request.user)}, status=201)


@login_required
@require_http_methods(["GET", "POST"])
def project_responsibles_api(request, project_slug):
    project = _get_project_or_404(request.user, project_slug)
    if request.method == "POST":
        if not _can_edit_project(project, request.user):
            return JsonResponse({"error": "No tienes permisos para agregar responsables."}, status=403)
        payload = _request_data(request)
        if payload is None:
            return HttpResponseBadRequest("Datos inválidos")
        name = (payload.get("name") or "").strip()
        if not name:
            return JsonResponse({"error": "El nombre del responsable es obligatorio."}, status=400)
        companies = list(project.responsible_companies or [])
        if any(item.get("name", "").strip().lower() == name.lower() for item in companies):
            return JsonResponse({"error": "Ese responsable ya está en la lista."}, status=400)
        next_id = max([item.get("id", 0) for item in companies], default=0) + 1
        companies.append({"id": next_id, "name": name})
        project.responsible_companies = companies
        project.save(update_fields=["responsible_companies"])
        return JsonResponse({"responsibleCompanies": companies}, status=201)
    return JsonResponse({"responsibleCompanies": project.responsible_companies or []})


@login_required
@require_http_methods(["DELETE"])
def project_responsible_detail_api(request, project_slug, responsible_id):
    project = _get_project_or_404(request.user, project_slug)
    if not _can_edit_project(project, request.user):
        return JsonResponse({"error": "No tienes permisos para eliminar responsables."}, status=403)
    companies = [item for item in (project.responsible_companies or []) if item.get("id") != responsible_id]
    project.responsible_companies = companies
    project.save(update_fields=["responsible_companies"])
    return JsonResponse({"responsibleCompanies": companies})


@login_required
@require_http_methods(["POST"])
def project_plans_api(request, project_slug):
    project = _get_project_or_404(request.user, project_slug)
    if request.method == "POST":
        if not _can_edit_project(project, request.user):
            return JsonResponse({"error": "No tienes permisos para subir planos."}, status=403)
        plan_file = request.FILES.get("planFile")
        if not plan_file:
            return JsonResponse({"error": "Selecciona un archivo PDF."}, status=400)
        if not plan_file.name.lower().endswith(".pdf"):
            return JsonResponse({"error": "Solo se permiten archivos PDF."}, status=400)
        plan = ProjectPlan.objects.create(
            project=project,
            name=(request.POST.get("name") or plan_file.name).strip(),
            file=plan_file,
        )
        return JsonResponse({"plan": {
            "id": plan.id,
            "name": plan.name or plan.file.name.rsplit("/", 1)[-1],
            "url": _project_plan_url(project, plan),
            "createdAt": plan.created_at.isoformat(),
        }}, status=201)


@require_http_methods(["GET"])
def project_plan_file_api(request, project_slug, plan_id):
    if request.user.is_authenticated:
        project = _get_project_or_404(request.user, project_slug)
    else:
        share = _public_report_share_for_request(request)
        if not share:
            return redirect_to_login(request.get_full_path())
        if share.report.project.slug != project_slug:
            raise Http404()
        project = share.report.project
        if not share.report.entries.filter(plan_id=plan_id).exists():
            raise Http404()
    plan = get_object_or_404(project.plans, pk=plan_id)
    try:
        if getattr(settings, "USE_CLOUDINARY", False):
            import cloudinary.api
            from cloudinary.utils import base_api_url, now, sign_request

            resource = cloudinary.api.resource(
                plan.file.name,
                resource_type="raw",
                type="upload",
            )
            download_params = sign_request(
                {"asset_id": resource["asset_id"], "timestamp": now()}, {}
            )
            download_url = f"{base_api_url('asset/download')}?{urlencode(download_params)}"
            cloudinary_response = requests.get(download_url, timeout=30)
            cloudinary_response.raise_for_status()
            file_content = cloudinary_response.content
        else:
            plan_file = plan.file.open("rb")
            file_content = plan_file.read()
            plan_file.close()
    except Exception:
        logger.exception("No se pudo descargar el plano %s del proyecto %s", plan_id, project.slug)
        return JsonResponse({"error": "El archivo del plano no está disponible en el almacenamiento."}, status=404)

    filename = (plan.name or Path(plan.file.name).name).replace('"', "")
    response = HttpResponse(file_content, content_type="application/pdf")
    response["Content-Disposition"] = f'inline; filename="{filename}"'
    response["Content-Length"] = str(len(file_content))
    response["X-Content-Type-Options"] = "nosniff"
    return response if request.user.is_authenticated else _private_no_store(response)


@login_required
@require_http_methods(["DELETE"])
def project_plan_detail_api(request, project_slug, plan_id):
    project = _get_project_or_404(request.user, project_slug)
    if not _can_edit_project(project, request.user):
        return JsonResponse({"error": "No tienes permisos para eliminar planos."}, status=403)
    plan = get_object_or_404(project.plans, pk=plan_id)
    plan.delete()
    return JsonResponse({"ok": True})


@login_required
@require_http_methods(["DELETE"])
def project_plan_marker_detail_api(request, project_slug, plan_id, marker_id):
    project = _get_project_or_404(request.user, project_slug)
    if not _can_edit_project(project, request.user):
        return JsonResponse({"error": "No tienes permisos para eliminar puntos."}, status=403)
    marker = get_object_or_404(ProjectPlanMarker, pk=marker_id, plan__project=project, plan_id=plan_id)
    marker.delete()
    return JsonResponse({"ok": True})


@login_required
@require_http_methods(["POST"])
def project_plan_markers_api(request, project_slug, plan_id):
    project = _get_project_or_404(request.user, project_slug)
    plan = get_object_or_404(project.plans, pk=plan_id)
    if not _can_edit_project(project, request.user):
        return JsonResponse({"error": "No tienes permisos para colocar puntos."}, status=403)
    payload = _parse_json(request)
    if payload is None:
        return HttpResponseBadRequest("JSON inválido")
    marker = ProjectPlanMarker.objects.create(
        plan=plan,
        page=max(1, int(payload.get("page") or 1)),
        x=max(0, min(1, float(payload.get("x") or 0))),
        y=max(0, min(1, float(payload.get("y") or 0))),
    )
    return JsonResponse({"marker": {"id": marker.id, "page": marker.page, "x": marker.x, "y": marker.y}}, status=201)


@login_required
@require_http_methods(["POST"])
def project_report_export_pdf_real_api(request, project_slug, report_id):
    project = _get_project_or_404(request.user, project_slug)
    report = _get_user_report_or_404(project, request.user, report_id)
    payload = _request_data(request)
    if payload is None:
        return HttpResponseBadRequest("JSON inválido")

    report_html = (payload.get("html") or "").strip()
    if not report_html:
        return JsonResponse({"error": "No hay contenido del reporte para exportar."}, status=400)

    filename = _sanitize_pdf_filename(payload.get("fileName") or report.title or f"reporte-{report.id}")

    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        return JsonResponse({"error": "Playwright no está instalado. Ejecuta: pip install playwright && playwright install chromium"}, status=500)

    base_url = request.build_absolute_uri("/")
    document_html = _build_pdf_export_document(report_html, base_url)

    try:
        with sync_playwright() as pw:
            browser = pw.chromium.launch(args=[
                "--no-sandbox",
                "--disable-setuid-sandbox",
                "--disable-dev-shm-usage",
                "--disable-gpu",
            ])
            try:
                page = browser.new_page(viewport={"width": 794, "height": 1123})
                if request.get_host() != "testserver":
                    page.goto(base_url, wait_until="domcontentloaded")
                page.set_content(document_html, wait_until="load")
                page.emulate_media(media="screen")
                page.wait_for_function("() => Array.from(document.images).every(i => i.complete)", timeout=10000)
                page.evaluate("""async () => {
                for (const image of document.images) {
                    if (!image.naturalWidth || !image.naturalHeight) continue;
                    const sourceUrl = new URL(image.currentSrc, location.href);
                    if (sourceUrl.protocol !== 'data:' && sourceUrl.origin !== location.origin) continue;

                    const response = await fetch(image.currentSrc);
                    if (!response.ok) throw new Error(`No se pudo optimizar una imagen del reporte (${response.status}).`);
                    const source = await response.blob();
                    if (source.size < 80 * 1024 && Math.max(image.naturalWidth, image.naturalHeight) <= 1600) continue;

                    const bitmap = await createImageBitmap(source);
                    const scale = Math.min(1, 1600 / Math.max(bitmap.width, bitmap.height));
                    const canvas = document.createElement('canvas');
                    canvas.width = Math.max(1, Math.round(bitmap.width * scale));
                    canvas.height = Math.max(1, Math.round(bitmap.height * scale));
                    const context = canvas.getContext('2d');
                    context.fillStyle = '#ffffff';
                    context.fillRect(0, 0, canvas.width, canvas.height);
                    context.drawImage(bitmap, 0, 0, canvas.width, canvas.height);
                    bitmap.close();

                    const optimized = await new Promise(resolve => canvas.toBlob(resolve, 'image/jpeg', 0.74));
                    if (!optimized) throw new Error('No se pudo comprimir una imagen del reporte.');
                    if (optimized.size < source.size) {
                        image.src = URL.createObjectURL(optimized);
                        await image.decode();
                    }
                }
            }""")
                pdf_bytes = page.pdf(
                    format="A4",
                    print_background=True,
                    prefer_css_page_size=True,
                    margin={"top": "1.5mm", "right": "1.5mm", "bottom": "1.5mm", "left": "1.5mm"},
                )
            finally:
                browser.close()
    except Exception as error:
        return JsonResponse({"error": f"No se pudo generar el PDF real: {error}"}, status=500)

    try:
        pdf_bytes = _linearize_pdf(pdf_bytes)
    except Exception as error:
        logger.exception("No se pudo preparar la visualización rápida del PDF del reporte %s", report.id)
        return JsonResponse({"error": f"No se pudo optimizar la apertura del PDF: {error}"}, status=500)

    response = HttpResponse(pdf_bytes, content_type="application/pdf")
    response["Content-Disposition"] = f'attachment; filename="{filename}"'
    return response


@login_required
@require_http_methods(["POST", "PATCH", "DELETE"])
def project_detail_api(request, project_slug):
    project = _get_project_or_404(request.user, project_slug)

    if request.method == "DELETE":
        if project.owner_id != request.user.id:
            return JsonResponse({"error": "Solo el propietario puede eliminar el proyecto."}, status=403)
        project.delete()
        return JsonResponse({"ok": True})

    if not _can_edit_project(project, request.user):
        return JsonResponse({"error": "No tienes permisos para editar este proyecto."}, status=403)

    payload = _request_data(request)
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
    if payload.get("clearProjectImage") in {True, "true", "1", 1}:
        if project.project_image:
            project.project_image.delete(save=False)
        project.project_image = None
    if request.FILES.get("projectPhoto"):
        project.project_image = request.FILES["projectPhoto"]
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
    return JsonResponse({"members": _serialize_project_members(project)})


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
    if report.report_type == ProjectReport.TYPE_MATERIAL_RECEIPT:
        MaterialReceipt.objects.get_or_create(report=report)
    project = _get_project_or_404(request.user, project.slug)
    report = _get_user_report_or_404(project, request.user, report.id)
    return JsonResponse({"report": _serialize_report(report, request.user)}, status=201)


@_report_access_required
@require_http_methods(["POST"])
def project_report_update_api(request, project_slug, report_id):
    project, report, is_public_share = _report_access_for_request(request, project_slug, report_id)
    if not is_public_share and not _can_edit_report(report, request.user):
        return JsonResponse({"error": "No tienes permisos para editar este reporte."}, status=403)

    if is_public_share and request.FILES.get("coverPhoto"):
        image_error = _validate_public_report_images([request.FILES["coverPhoto"]], max_count=1)
        if image_error:
            return JsonResponse({"error": image_error}, status=400)

    payload = _request_data(request)
    if payload is None:
        return HttpResponseBadRequest("Datos inválidos")
    _apply_report_payload(report, payload, request.FILES)
    report.save()
    if report.report_type == ProjectReport.TYPE_MATERIAL_RECEIPT:
        MaterialReceipt.objects.get_or_create(report=report)
    serializer_user = project.owner if is_public_share else request.user
    serialized_report = _serialize_report(report, serializer_user)
    if is_public_share:
        serialized_report.update({
            "members": [],
            "canShare": False,
            "canEdit": True,
            "accessRole": ProjectMembership.ROLE_EDITOR,
        })
    return JsonResponse({"report": serialized_report})


@login_required
@require_http_methods(["GET", "POST", "DELETE"])
def public_report_share_api(request, project_slug, report_id):
    project = _get_project_or_404(request.user, project_slug)
    report = _get_user_report_or_404(project, request.user, report_id)
    if not _can_share_report(report, request.user):
        return JsonResponse({"error": "Solo un administrador del reporte puede crear este enlace."}, status=403)

    share = PublicReportShare.objects.filter(report=report).first()
    if request.method == "GET":
        share_url = ""
        if share and share.is_active:
            share_url = request.build_absolute_uri(reverse(
                "public_report_share",
                kwargs={"share_token": share.token},
            ))
        return JsonResponse({"configured": bool(share and share.is_active), "shareUrl": share_url})

    if request.method == "DELETE":
        if share and share.is_active:
            share.is_active = False
            share.access_version += 1
            share.save(update_fields=["is_active", "access_version", "updated_at"])
        return JsonResponse({"configured": False})

    payload = _parse_json(request)
    if payload is None:
        return HttpResponseBadRequest("JSON inválido")
    password = str(payload.get("password") or "")
    if len(password) < 8:
        return JsonResponse({"error": "La contraseña debe tener al menos 8 caracteres."}, status=400)
    if len(password) > 128:
        return JsonResponse({"error": "La contraseña no puede superar 128 caracteres."}, status=400)

    if share is None:
        share = PublicReportShare(
            report=report,
            token=secrets.token_urlsafe(32),
            password_hash=make_password(password),
        )
    else:
        if not share.is_active:
            share.token = secrets.token_urlsafe(32)
        share.password_hash = make_password(password)
        share.is_active = True
        share.access_version += 1
        share.failed_attempts = 0
        share.locked_until = None
    share.save()
    return JsonResponse({
        "configured": True,
        "shareUrl": request.build_absolute_uri(reverse(
            "public_report_share",
            kwargs={"share_token": share.token},
        )),
    })


@_report_access_required
@require_http_methods(["POST"])
def material_receipt_api(request, project_slug, report_id):
    project, report, is_public_share = _report_access_for_request(request, project_slug, report_id)
    if report.report_type != ProjectReport.TYPE_MATERIAL_RECEIPT:
        return JsonResponse({"error": "Este reporte no es un acta de recepción de materiales."}, status=400)
    if not is_public_share and not _can_edit_report(report, request.user):
        return JsonResponse({"error": "No tienes permisos para editar esta acta."}, status=403)

    payload = _request_data(request)
    if payload is None:
        return HttpResponseBadRequest("Datos inválidos")

    receipt, _ = MaterialReceipt.objects.get_or_create(report=report)
    text_fields = {
        "actNumber": ("act_number", 80),
        "deliveryLocation": ("delivery_location", 200),
        "supplier": ("supplier", 200),
        "deliveryNote": ("delivery_note", 120),
        "deliveredBy": ("delivered_by", 200),
        "deliveredDni": ("delivered_dni", 30),
        "deliveredPosition": ("delivered_position", 100),
        "receivedBy": ("received_by", 200),
        "receivedDni": ("received_dni", 30),
        "receivedPosition": ("received_position", 100),
        "verifiedBy": ("verified_by", 200),
        "verifiedDni": ("verified_dni", 30),
        "verifiedPosition": ("verified_position", 100),
        "conformity": ("conformity", 20),
        "observations": ("observations", None),
    }
    for payload_key, (field_name, max_length) in text_fields.items():
        if payload_key in payload:
            value = (payload.get(payload_key) or "").strip()
            if max_length and len(value) > max_length:
                return JsonResponse({"error": f"El campo {payload_key} supera el máximo de {max_length} caracteres."}, status=400)
            if payload_key == "conformity" and value not in {"", "conforme", "observado", "parcial"}:
                return JsonResponse({"error": "La conformidad seleccionada no es válida."}, status=400)
            setattr(receipt, field_name, value)

    if "receiptDate" in payload:
        date_value = (payload.get("receiptDate") or "").strip()
        try:
            receipt.receipt_date = datetime.strptime(date_value, "%Y-%m-%d").date() if date_value else None
        except ValueError:
            return JsonResponse({"error": "La fecha de recepción no es válida."}, status=400)

    signature_payload_keys = ("signatureDelivered", "signatureVerified", "signatureReceived")
    shared_signature_changes = [
        payload_key for payload_key in signature_payload_keys
        if request.FILES.get(payload_key)
        or payload.get(f"clear{payload_key[0].upper()}{payload_key[1:]}") in {True, "true", "1", 1}
    ]
    if _material_receipt_share_configured(receipt) and shared_signature_changes and not is_public_share:
        if report.project.owner_id != request.user.id:
            return JsonResponse({
                "error": "Solo quien creó el proyecto puede agregar, cambiar o quitar firmas del acta compartida."
            }, status=403)

    signature_fields = {
        "signatureDelivered": (
            "signature_delivered",
            "delivered_signed_on",
            ("delivered_by", "delivered_dni", "delivered_position"),
        ),
        "signatureReceived": (
            "signature_received",
            "received_signed_on",
            ("received_by", "received_dni", "received_position"),
        ),
        "signatureVerified": (
            "signature_verified",
            "verified_signed_on",
            ("verified_by", "verified_dni", "verified_position"),
        ),
    }
    for payload_key, (field_name, signed_on_field, identity_fields) in signature_fields.items():
        uploaded_file = request.FILES.get(payload_key)
        if uploaded_file:
            if not (uploaded_file.content_type or "").startswith("image/") or uploaded_file.size > 5 * 1024 * 1024:
                return JsonResponse({"error": "Cada firma debe ser una imagen de hasta 5 MB."}, status=400)
            from PIL import Image, UnidentifiedImageError

            try:
                image = Image.open(uploaded_file)
                if image.width * image.height > MAX_PUBLIC_IMAGE_PIXELS:
                    return JsonResponse({"error": "La firma tiene demasiada resolución."}, status=400)
                image.verify()
            except (UnidentifiedImageError, OSError, Image.DecompressionBombError):
                return JsonResponse({"error": "El archivo de firma no contiene una imagen válida."}, status=400)
            if image.format not in {"JPEG", "PNG", "WEBP"}:
                return JsonResponse({"error": "La firma debe estar en formato PNG, JPEG o WebP."}, status=400)
            uploaded_file.seek(0)
            old_file = getattr(receipt, field_name)
            if old_file:
                old_file.delete(save=False)
            setattr(receipt, field_name, uploaded_file)
            setattr(receipt, signed_on_field, timezone.localdate())
        elif payload.get(f"clear{payload_key[0].upper()}{payload_key[1:]}") in {True, "true", "1", 1}:
            old_file = getattr(receipt, field_name)
            if old_file:
                old_file.delete(save=False)
            setattr(receipt, field_name, None)
            setattr(receipt, signed_on_field, None)
            for identity_field in identity_fields:
                setattr(receipt, identity_field, "")

    company_logo = request.FILES.get("companyLogo")
    if company_logo:
        if not (company_logo.content_type or "").startswith("image/") or company_logo.size > 5 * 1024 * 1024:
            return JsonResponse({"error": "El logo debe ser una imagen de hasta 5 MB."}, status=400)
        from PIL import Image, UnidentifiedImageError

        try:
            image = Image.open(company_logo)
            if image.width * image.height > MAX_PUBLIC_IMAGE_PIXELS:
                return JsonResponse({"error": "El logo tiene demasiada resolución."}, status=400)
            image.verify()
        except (UnidentifiedImageError, OSError, Image.DecompressionBombError):
            return JsonResponse({"error": "El archivo del logo no contiene una imagen válida."}, status=400)
        if image.format not in {"JPEG", "PNG", "WEBP"}:
            return JsonResponse({"error": "El logo debe estar en formato PNG, JPEG o WebP."}, status=400)
        company_logo.seek(0)
        if receipt.company_logo:
            receipt.company_logo.delete(save=False)
        receipt.company_logo = company_logo
    elif payload.get("clearCompanyLogo") in {True, "true", "1", 1}:
        if receipt.company_logo:
            receipt.company_logo.delete(save=False)
        receipt.company_logo = None

    receipt.save()
    report.material_receipt = receipt
    return JsonResponse({"materialReceipt": _serialize_material_receipt(report)})


@_report_access_required
@require_http_methods(["GET", "POST"])
def material_receipt_photos_api(request, project_slug, report_id):
    _, report, is_public_share = _report_access_for_request(request, project_slug, report_id)
    if report.report_type != ProjectReport.TYPE_MATERIAL_RECEIPT:
        return JsonResponse({"error": "Este reporte no es un acta de recepción de materiales."}, status=400)

    if request.method == "GET":
        receipt = MaterialReceipt.objects.filter(report=report).first()
        photos = [
            {"id": photo.pk, "url": photo.image.url, "name": photo.image.name.rsplit("/", 1)[-1]}
            for photo in receipt.photos.all()
        ] if receipt else []
        response = JsonResponse({"photos": photos})
        return _private_no_store(response) if is_public_share else response
    if not is_public_share and not _can_edit_report(report, request.user):
        return JsonResponse({"error": "No tienes permisos para editar este reporte."}, status=403)
    receipt, _ = MaterialReceipt.objects.get_or_create(report=report)

    uploaded_photos = request.FILES.getlist("photos")
    if not uploaded_photos:
        return JsonResponse({"error": "Selecciona al menos una foto."}, status=400)
    if len(uploaded_photos) > 20:
        return JsonResponse({"error": "Puedes subir hasta 20 fotos por vez."}, status=400)

    from PIL import Image, UnidentifiedImageError

    valid_formats = {"JPEG", "PNG", "WEBP"}
    for uploaded_photo in uploaded_photos:
        if not (uploaded_photo.content_type or "").startswith("image/") or uploaded_photo.size > 5 * 1024 * 1024:
            return JsonResponse({"error": "Cada foto debe ser una imagen de hasta 5 MB."}, status=400)
        try:
            image = Image.open(uploaded_photo)
            if image.width * image.height > MAX_PUBLIC_IMAGE_PIXELS:
                return JsonResponse({"error": "Una foto tiene demasiada resolución."}, status=400)
            image.verify()
        except (UnidentifiedImageError, OSError, Image.DecompressionBombError):
            return JsonResponse({"error": "Una de las fotos seleccionadas no es una imagen válida."}, status=400)
        if image.format not in valid_formats:
            return JsonResponse({"error": "Las fotos deben estar en formato PNG, JPEG o WebP."}, status=400)
        uploaded_photo.seek(0)

    sort_order = receipt.photos.order_by("-sort_order", "-id").values_list("sort_order", flat=True).first()
    sort_order = (sort_order or 0) + 1
    for index, uploaded_photo in enumerate(uploaded_photos):
        MaterialReceiptPhoto.objects.create(
            receipt=receipt,
            image=uploaded_photo,
            sort_order=sort_order + index,
        )
    return JsonResponse({"photos": _serialize_material_receipt(report)["photos"]}, status=201)


@_report_access_required
@require_http_methods(["DELETE"])
def material_receipt_photo_detail_api(request, project_slug, report_id, photo_id):
    _, report, is_public_share = _report_access_for_request(request, project_slug, report_id)
    if report.report_type != ProjectReport.TYPE_MATERIAL_RECEIPT:
        return JsonResponse({"error": "Este reporte no es un acta de recepción de materiales."}, status=400)
    if not is_public_share and not _can_edit_report(report, request.user):
        return JsonResponse({"error": "No tienes permisos para editar este reporte."}, status=403)

    receipt = get_object_or_404(MaterialReceipt, report=report)
    photo = get_object_or_404(receipt.photos.all(), pk=photo_id)
    photo.delete()
    report.refresh_from_db()
    return JsonResponse({"photos": _serialize_material_receipt(report)["photos"]})


def _material_receipt_word_source_hash(receipt):
    source = {
        "report": {
            "title": receipt.report.title,
            "project": receipt.report.project.project_name,
            "location": receipt.report.project.project_location,
        },
        "receipt": {
            field: getattr(receipt, field)
            for field in (
                "act_number", "receipt_date", "supplier", "delivery_note", "delivered_by",
                "delivered_dni", "delivered_position", "received_by", "received_dni",
                "received_position", "verified_by", "verified_dni", "verified_position",
                "conformity", "observations", "company_logo", "signature_delivered",
                "signature_received", "signature_verified", "delivered_signed_on",
                "received_signed_on", "verified_signed_on",
            )
        },
        "entries": list(
            receipt.report.entries.order_by("id").values(
                "id", "item_name", "unit", "quantity", "description",
            )
        ),
    }
    encoded = json.dumps(source, sort_keys=True, ensure_ascii=False, default=str).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _save_material_receipt_word_document(receipt, source_hash):
    from .word_editor import build_material_receipt_docx

    previous_name = receipt.word_document.name if receipt.word_document else ""
    document_bytes = build_material_receipt_docx(receipt)
    receipt.word_document.save(
        f"acta-materiales-{receipt.pk}.docx",
        ContentFile(document_bytes),
        save=False,
    )
    receipt.word_source_hash = source_hash
    receipt.word_document_key = secrets.token_urlsafe(24)
    receipt.save(update_fields=["word_document", "word_source_hash", "word_document_key", "updated_at"])
    if previous_name and previous_name != receipt.word_document.name:
        receipt.word_document.storage.delete(previous_name)


def _onlyoffice_configuration():
    document_server_url = getattr(settings, "ONLYOFFICE_DOCUMENT_SERVER_URL", "").rstrip("/")
    jwt_secret = getattr(settings, "ONLYOFFICE_JWT_SECRET", "")
    return document_server_url, jwt_secret


@login_required
@require_http_methods(["GET"])
def material_receipt_word_editor(request, project_slug, report_id):
    project = _get_project_or_404(request.user, project_slug)
    report = _get_user_report_or_404(project, request.user, report_id)
    if report.report_type != ProjectReport.TYPE_MATERIAL_RECEIPT:
        raise Http404()
    if not _can_edit_report(report, request.user):
        return HttpResponse("No tienes permisos para editar esta acta.", status=403)

    document_server_url, jwt_secret = _onlyoffice_configuration()
    if not document_server_url or not jwt_secret:
        return render(request, "report_app/material_receipt_word_editor.html", {
            "configured": False,
            "project": project,
            "report": report,
        })

    receipt, _ = MaterialReceipt.objects.get_or_create(report=report)
    source_hash = _material_receipt_word_source_hash(receipt)
    if not receipt.word_document or receipt.word_source_hash != source_hash:
        _save_material_receipt_word_document(receipt, source_hash)
    elif not receipt.word_document_key:
        receipt.word_document_key = secrets.token_urlsafe(24)
        receipt.save(update_fields=["word_document_key", "updated_at"])

    document_access = signing.dumps(
        {"receipt_id": receipt.pk},
        salt="material-receipt-word-download",
        compress=True,
    )
    callback_access = signing.dumps(
        {"receipt_id": receipt.pk, "document_key": receipt.word_document_key},
        salt="material-receipt-word-callback",
        compress=True,
    )
    document_url = request.build_absolute_uri(
        f"{reverse('material_receipt_word_download')}?{urlencode({'token': document_access})}"
    )
    callback_url = request.build_absolute_uri(
        f"{reverse('material_receipt_word_callback')}?{urlencode({'token': callback_access})}"
    )
    config = {
        "documentType": "word",
        "document": {
            "fileType": "docx",
            "key": receipt.word_document_key,
            "title": f"Acta {receipt.act_number or receipt.pk} - {project.project_name}.docx"[:128],
            "url": document_url,
            "permissions": {"edit": True, "download": True, "print": True},
        },
        "editorConfig": {
            "mode": "edit",
            "lang": "es",
            "callbackUrl": callback_url,
            "user": {
                "id": str(request.user.pk),
                "name": request.user.get_full_name() or request.user.get_username(),
            },
            "customization": {"forcesave": True, "compactHeader": True},
        },
    }
    import jwt

    config["token"] = jwt.encode(config, jwt_secret, algorithm="HS256")
    return render(request, "report_app/material_receipt_word_editor.html", {
        "configured": True,
        "document_server_url": document_server_url,
        "editor_config": config,
        "project": project,
        "report": report,
    })


@require_http_methods(["GET"])
def material_receipt_word_download(request):
    try:
        token_data = signing.loads(
            request.GET.get("token", ""),
            salt="material-receipt-word-download",
            max_age=60 * 60 * 12,
        )
    except signing.BadSignature:
        raise Http404()
    receipt = get_object_or_404(
        MaterialReceipt.objects.select_related("report"),
        pk=token_data.get("receipt_id"),
    )
    if not receipt.word_document:
        raise Http404()
    with receipt.word_document.open("rb") as document_file:
        response = HttpResponse(
            document_file.read(),
            content_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        )
    response["Content-Disposition"] = f'attachment; filename="acta-materiales-{receipt.pk}.docx"'
    response["Cache-Control"] = "private, no-store"
    return response


@csrf_exempt
@require_http_methods(["POST"])
def material_receipt_word_callback(request):
    document_server_url, jwt_secret = _onlyoffice_configuration()
    if not document_server_url or not jwt_secret:
        return JsonResponse({"error": 1}, status=503)
    try:
        payload = json.loads(request.body)
    except (json.JSONDecodeError, UnicodeDecodeError):
        return HttpResponseBadRequest("JSON inválido")

    auth_header = request.headers.get("Authorization", "")
    token = auth_header.removeprefix("Bearer ").strip() if auth_header.startswith("Bearer ") else payload.get("token", "")
    if not token:
        return JsonResponse({"error": 1}, status=403)
    import jwt

    try:
        jwt.decode(token, jwt_secret, algorithms=["HS256"])
        callback_access = signing.loads(
            request.GET.get("token", ""),
            salt="material-receipt-word-callback",
            max_age=60 * 60 * 24,
        )
    except (jwt.InvalidTokenError, signing.BadSignature):
        return JsonResponse({"error": 1}, status=403)

    receipt = get_object_or_404(MaterialReceipt, pk=callback_access.get("receipt_id"))
    if (
        not receipt.word_document
        or callback_access.get("document_key") != receipt.word_document_key
        or payload.get("key") != receipt.word_document_key
    ):
        return JsonResponse({"error": 0})

    status = payload.get("status")
    if status in {2, 6}:
        download_url = payload.get("url")
        parsed_download_url = urlparse(download_url or "")
        parsed_server_url = urlparse(document_server_url)
        if (
            parsed_download_url.scheme not in {"http", "https"}
            or parsed_download_url.hostname != parsed_server_url.hostname
        ):
            logger.warning("ONLYOFFICE returned an unexpected document URL for receipt %s", receipt.pk)
            return JsonResponse({"error": 1}, status=400)
        try:
            response = requests.get(download_url, timeout=(5, 30), stream=True)
            response.raise_for_status()
            document_bytes = bytearray()
            for chunk in response.iter_content(chunk_size=64 * 1024):
                document_bytes.extend(chunk)
                if len(document_bytes) > 25 * 1024 * 1024:
                    return JsonResponse({"error": 1}, status=413)
        except requests.RequestException:
            logger.exception("Could not retrieve the edited Word document for receipt %s", receipt.pk)
            return JsonResponse({"error": 1}, status=502)
        try:
            with zipfile.ZipFile(BytesIO(document_bytes)) as archive:
                if "[Content_Types].xml" not in archive.namelist() or archive.testzip():
                    raise zipfile.BadZipFile("Invalid DOCX archive")
        except (zipfile.BadZipFile, OSError):
            logger.warning("ONLYOFFICE returned an invalid DOCX for receipt %s", receipt.pk)
            return JsonResponse({"error": 1}, status=400)
        receipt.word_document.save(
            f"acta-materiales-{receipt.pk}-{receipt.word_document_key}.docx",
            ContentFile(bytes(document_bytes)),
            save=True,
        )
    elif status not in {1, 4}:
        logger.warning("ONLYOFFICE callback returned status %s for receipt %s", status, receipt.pk)
        return JsonResponse({"error": 1})
    return JsonResponse({"error": 0})


def _next_material_receipt_signer(receipt):
    for signer_key in MATERIAL_RECEIPT_SIGNING_ORDER:
        if not getattr(receipt, MATERIAL_RECEIPT_SHARE_SIGNERS[signer_key]["signature_field"]):
            return signer_key
    return None


def _material_receipt_share_configured(receipt):
    return bool(
        receipt.share_token
        and all(getattr(receipt, signer["password_field"]) for signer in MATERIAL_RECEIPT_SHARE_SIGNERS.values())
    )


@login_required
@require_http_methods(["GET", "POST"])
def material_receipt_share_api(request, project_slug, report_id):
    project = _get_project_or_404(request.user, project_slug)
    report = _get_user_report_or_404(project, request.user, report_id)
    if report.report_type != ProjectReport.TYPE_MATERIAL_RECEIPT:
        return JsonResponse({"error": "Este reporte no es un acta de recepción de materiales."}, status=400)
    if not _can_share_report(report, request.user):
        return JsonResponse({"error": "Solo un administrador del reporte puede compartir el acta."}, status=403)

    receipt, _ = MaterialReceipt.objects.get_or_create(report=report)
    if request.method == "GET":
        share_url = ""
        if _material_receipt_share_configured(receipt):
            share_url = request.build_absolute_uri(reverse(
                "material_receipt_share",
                kwargs={"share_token": receipt.share_token},
            ))
        return JsonResponse({
            "shareUrl": share_url,
            "configured": _material_receipt_share_configured(receipt),
        })

    payload = _parse_json(request)
    if payload is None:
        return HttpResponseBadRequest("Datos inválidos")
    password_fields = {
        "delivered": "delivered_share_password",
        "verified": "verified_share_password",
        "received": "received_share_password",
    }
    new_passwords = {}
    for signer_key, field_name in password_fields.items():
        password = str(payload.get(signer_key) or "")
        if len(password) < 8:
            return JsonResponse({
                "error": f"La contraseña para {MATERIAL_RECEIPT_SHARE_SIGNERS[signer_key]['label']} debe tener al menos 8 caracteres."
            }, status=400)
        if len(password) > 128:
            return JsonResponse({"error": "Las contraseñas no pueden superar 128 caracteres."}, status=400)
        new_passwords[field_name] = make_password(password)

    if not receipt.share_token:
        receipt.share_token = secrets.token_urlsafe(32)
    for field_name, password_hash in new_passwords.items():
        setattr(receipt, field_name, password_hash)
    receipt.share_password_failed_attempts = 0
    receipt.share_password_locked_until = None
    receipt.share_access_version += 1
    receipt.save(update_fields=[
        "share_token",
        *new_passwords.keys(),
        "share_access_version",
        "share_password_failed_attempts",
        "share_password_locked_until",
        "updated_at",
    ])
    share_url = request.build_absolute_uri(reverse(
        "material_receipt_share",
        kwargs={"share_token": receipt.share_token},
    ))
    return JsonResponse({"shareUrl": share_url, "configured": True})


def _validate_receipt_signature(uploaded_file):
    if not uploaded_file:
        return "Agrega una firma dibujándola o seleccionando una imagen."
    if not (uploaded_file.content_type or "").startswith("image/") or uploaded_file.size > 5 * 1024 * 1024:
        return "La firma debe ser una imagen de hasta 5 MB."
    from PIL import Image, UnidentifiedImageError

    try:
        image = Image.open(uploaded_file)
        if image.width * image.height > MAX_PUBLIC_IMAGE_PIXELS:
            return "La firma tiene demasiada resolución."
        image.verify()
    except (UnidentifiedImageError, OSError, Image.DecompressionBombError):
        return "El archivo de firma no contiene una imagen válida."
    if image.format not in {"JPEG", "PNG", "WEBP"}:
        return "La firma debe estar en formato PNG, JPEG o WebP."
    uploaded_file.seek(0)
    return ""


@ensure_csrf_cookie
@require_http_methods(["GET", "POST"])
def material_receipt_share(request, share_token):
    receipt = get_object_or_404(
        MaterialReceipt.objects.select_related("report__project").prefetch_related(
            "report__entries",
            "photos",
        ),
        share_token=share_token,
    )
    if not _material_receipt_share_configured(receipt):
        raise Http404

    report = receipt.report
    share_session_key = f"material_receipt_signer:{share_token}"
    identity_session_key = f"material_receipt_identity:{share_token}"
    reauth_session_key = f"material_receipt_reauth_signer:{share_token}"
    observations_saved_key = f"material_receipt_observations_saved:{share_token}"
    signer_key = request.session.get(share_session_key, "")
    signer_identity = request.session.get(identity_session_key, {})
    reauth_signer_key = request.session.get(reauth_session_key, "")
    session_version_key = f"material_receipt_share_version:{share_token}"
    if request.session.get(session_version_key) != receipt.share_access_version:
        signer_key = ""
        signer_identity = {}
        reauth_signer_key = ""
        request.session.pop(share_session_key, None)
        request.session.pop(identity_session_key, None)
        request.session.pop(reauth_session_key, None)
    if signer_key not in MATERIAL_RECEIPT_SHARE_SIGNERS:
        signer_key = ""
        request.session.pop(share_session_key, None)
    if not isinstance(signer_identity, dict):
        signer_identity = {}
        request.session.pop(identity_session_key, None)
        request.session.pop(reauth_session_key, None)
        reauth_signer_key = ""
    if reauth_signer_key not in MATERIAL_RECEIPT_SHARE_SIGNERS or not signer_identity:
        reauth_signer_key = ""
        request.session.pop(reauth_session_key, None)
    message = ""
    identity_input = {
        "signer": reauth_signer_key,
        **(signer_identity if reauth_signer_key else {}),
    }

    if request.method == "POST":
        action = request.POST.get("action")
        if action == "logout":
            if signer_key not in MATERIAL_RECEIPT_SHARE_SIGNERS:
                message = "Tu sesión ya está cerrada."
            else:
                request.session[reauth_session_key] = signer_key
                request.session.pop(share_session_key, None)
                return redirect("material_receipt_share", share_token=share_token)
        elif action == "authenticate":
            requested_signer = request.POST.get("signer", "")
            use_saved_identity = (
                requested_signer == reauth_signer_key
                and reauth_signer_key in MATERIAL_RECEIPT_SHARE_SIGNERS
                and bool(signer_identity)
            )
            saved_identity = signer_identity if use_saved_identity else {}
            signer_key = ""
            request.session.pop(share_session_key, None)
            identity_input = {
                "signer": requested_signer,
                "name": (request.POST.get("name") or saved_identity.get("name") or "").strip(),
                "dni": (request.POST.get("dni") or saved_identity.get("dni") or "").strip(),
                "position": (request.POST.get("position") or saved_identity.get("position") or "").strip(),
            }
            signer = MATERIAL_RECEIPT_SHARE_SIGNERS.get(requested_signer)
            password = request.POST.get("password", "")
            now = timezone.now()
            if not all(identity_input.values()):
                message = (
                    "Completa tu nombre, DNI y cargo para ingresar al acta."
                    if not use_saved_identity
                    else "No se pudieron recuperar tus datos. Ingresa nuevamente tu nombre, DNI y cargo."
                )
            elif len(identity_input["name"]) > 200 or len(identity_input["dni"]) > 30 or len(identity_input["position"]) > 100:
                message = "Revisa la longitud del nombre, DNI o cargo."
            else:
                with transaction.atomic():
                    locked_receipt = MaterialReceipt.objects.select_for_update().get(pk=receipt.pk)
                    if locked_receipt.share_password_locked_until and locked_receipt.share_password_locked_until > now:
                        message = "Se realizaron varios intentos. Espera 15 minutos antes de volver a intentarlo."
                    elif signer and check_password(password, getattr(locked_receipt, signer["password_field"])):
                        locked_receipt.share_password_failed_attempts = 0
                        locked_receipt.share_password_locked_until = None
                        locked_receipt.save(update_fields=[
                            "share_password_failed_attempts",
                            "share_password_locked_until",
                            "updated_at",
                        ])
                        signer_key = requested_signer
                        signer_identity = identity_input
                        request.session[share_session_key] = signer_key
                        request.session[identity_session_key] = signer_identity
                        request.session[session_version_key] = locked_receipt.share_access_version
                        request.session.pop(reauth_session_key, None)
                    else:
                        locked_receipt.share_password_failed_attempts += 1
                        if locked_receipt.share_password_failed_attempts >= 5:
                            locked_receipt.share_password_failed_attempts = 0
                            locked_receipt.share_password_locked_until = now + timedelta(minutes=15)
                            message = "Se realizaron varios intentos. Espera 15 minutos antes de volver a intentarlo."
                        else:
                            message = "La contraseña no es válida para el responsable seleccionado."
                        locked_receipt.save(update_fields=[
                            "share_password_failed_attempts",
                            "share_password_locked_until",
                            "updated_at",
                        ])
                        if not use_saved_identity:
                            request.session.pop(identity_session_key, None)
                            request.session.pop(reauth_session_key, None)
            if signer_key and not message:
                return redirect("material_receipt_share", share_token=share_token)
        elif action == "sign":
            signer = MATERIAL_RECEIPT_SHARE_SIGNERS.get(signer_key)
            if not signer:
                message = "Ingresa la contraseña que corresponde a tu sección antes de firmar."
            else:
                with transaction.atomic():
                    locked_receipt = MaterialReceipt.objects.select_for_update().get(pk=receipt.pk)
                    next_signer = _next_material_receipt_signer(locked_receipt)
                    if getattr(locked_receipt, signer["signature_field"]):
                        message = "Esta sección ya fue firmada y no se puede volver a firmar."
                    elif next_signer != signer_key:
                        current_label = MATERIAL_RECEIPT_SHARE_SIGNERS[next_signer]["label"] if next_signer else ""
                        message = f"Debes esperar a que firme primero: {current_label}."
                    else:
                        name = (signer_identity.get("name") or "").strip()
                        dni = (signer_identity.get("dni") or "").strip()
                        position = (signer_identity.get("position") or "").strip()
                        if not name or not dni or not position:
                            message = "Vuelve a ingresar tu contraseña, nombre, DNI y cargo para firmar."
                        elif len(name) > 200 or len(dni) > 30 or len(position) > 100:
                            message = "Revisa la longitud del nombre, DNI o cargo."
                        else:
                            uploaded_signature = request.FILES.get("signature")
                            signature_data = request.POST.get("signatureData", "")
                            if not uploaded_signature and signature_data:
                                try:
                                    header, encoded = signature_data.split(",", 1)
                                    if header not in {
                                        "data:image/png;base64",
                                        "data:image/jpeg;base64",
                                        "data:image/webp;base64",
                                    } or len(encoded) > 7 * 1024 * 1024:
                                        raise ValueError
                                    image_bytes = b64decode(encoded, validate=True)
                                    extension = {"png": "png", "jpeg": "jpg", "webp": "webp"}[header.split("/")[1].split(";")[0]]
                                    uploaded_signature = SimpleUploadedFile(
                                        f"firma-{signer_key}.{extension}",
                                        image_bytes,
                                        content_type=f"image/{'jpeg' if extension == 'jpg' else extension}",
                                    )
                                except (ValueError, Base64DecodeError, KeyError):
                                    message = "No se pudo leer la firma. Vuelve a dibujarla o cargarla."
                            signature_error = _validate_receipt_signature(uploaded_signature)
                            if not message and signature_error:
                                message = signature_error
                            if not message:
                                setattr(locked_receipt, signer["name_field"], name)
                                setattr(locked_receipt, signer["dni_field"], dni)
                                setattr(locked_receipt, signer["position_field"], position)
                                setattr(locked_receipt, signer["signature_field"], uploaded_signature)
                                setattr(locked_receipt, signer["signed_on_field"], timezone.localdate())
                                locked_receipt.save()
                                receipt = locked_receipt
                if not message:
                    return redirect("material_receipt_share", share_token=share_token)
        elif action == "update_observations":
            signer = MATERIAL_RECEIPT_SHARE_SIGNERS.get(signer_key)
            if not signer:
                message = "Ingresa la contraseña que corresponde a tu sección antes de editar las observaciones."
            else:
                comment = (request.POST.get("observations") or "").strip()
                conformity = request.POST.get("conformity")
                if len(comment) > 10000:
                    message = "El comentario no puede superar los 10000 caracteres."
                elif conformity is not None and (
                    signer_key != "received"
                    or conformity not in {"conforme", "observado", "parcial"}
                ):
                    message = "Solo la persona que recibe puede seleccionar una conformidad válida."
                else:
                    with transaction.atomic():
                        locked_receipt = MaterialReceipt.objects.select_for_update().get(pk=receipt.pk)
                        next_signer = _next_material_receipt_signer(locked_receipt)
                        if getattr(locked_receipt, signer["signature_field"]):
                            message = "Ya firmaste esta sección y no puedes editar las observaciones."
                        elif next_signer != signer_key:
                            current_label = MATERIAL_RECEIPT_SHARE_SIGNERS[next_signer]["label"] if next_signer else ""
                            message = f"Solo puedes editar las observaciones cuando llegue tu turno de firma. Responsable pendiente: {current_label}."
                        else:
                            observations = locked_receipt.observations.strip()
                            if comment:
                                commenter = (signer_identity.get("name") or signer["label"]).strip()
                                new_observations = "\n".join(
                                    value for value in (observations, f"{commenter}: {comment}") if value
                                )
                                if len(new_observations) > 10000:
                                    message = "El comentario supera el máximo permitido junto con los comentarios anteriores."
                            else:
                                new_observations = observations
                            update_fields = ["updated_at"]
                            if conformity is not None:
                                locked_receipt.conformity = conformity
                                update_fields.append("conformity")
                            if not message:
                                locked_receipt.observations = new_observations
                                update_fields.append("observations")
                                locked_receipt.save(update_fields=update_fields)
                                receipt = locked_receipt
                                request.session[observations_saved_key] = True
                    if not message:
                        return redirect("material_receipt_share", share_token=share_token)
        else:
            message = "La solicitud no es válida."

    receipt.refresh_from_db()
    next_signer = _next_material_receipt_signer(receipt)
    signed_status = [
        {
            "key": key,
            "label": signer["label"],
            "signed": bool(getattr(receipt, signer["signature_field"])),
            "signedOn": getattr(receipt, signer["signed_on_field"]),
            "signature": getattr(receipt, signer["signature_field"]).url if getattr(receipt, signer["signature_field"]) else "",
            "name": getattr(receipt, signer["name_field"]),
            "dni": getattr(receipt, signer["dni_field"]),
            "position": getattr(receipt, signer["position_field"]),
            "canSign": bool(signer_key == key and signer_key == next_signer),
        }
        for key, signer in MATERIAL_RECEIPT_SHARE_SIGNERS.items()
    ]
    signer = MATERIAL_RECEIPT_SHARE_SIGNERS.get(signer_key)
    is_signed = bool(signer and getattr(receipt, signer["signature_field"]))
    signer_name = getattr(receipt, signer["name_field"]) if is_signed and signer else signer_identity.get("name", "")
    signer_dni = getattr(receipt, signer["dni_field"]) if is_signed and signer else signer_identity.get("dni", "")
    signer_position = getattr(receipt, signer["position_field"]) if is_signed and signer else signer_identity.get("position", "")
    can_sign = bool(signer and signer_key == next_signer and not is_signed)
    can_edit_observations = can_sign
    signer_waiting_for = (
        MATERIAL_RECEIPT_SHARE_SIGNERS[next_signer]["label"]
        if signer and not is_signed and next_signer and signer_key != next_signer
        else ""
    )
    template = "report_app/material_receipt_shared_act.html" if signer_key else "report_app/material_receipt_share.html"
    entries = list(report.entries.all().order_by("id"))
    shared_preview = None
    if signer_key:
        shared_preview = {
            "project": {
                "id": report.project_id,
                "slug": report.project.slug,
                "projectName": report.project.project_name,
                "projectLocation": report.project.project_location,
            },
            "report": {
                "id": report.pk,
                "type": report.report_type,
                "title": report.title,
                "week": report.week or "",
                "date": report.report_date.isoformat() if report.report_date else "",
                "forWhom": report.for_whom,
                "fromWhom": report.from_whom,
                "materialReceipt": _serialize_material_receipt(report),
                "entries": [
                    {
                        "id": entry.pk,
                        "itemName": entry.item_name or "",
                        "unit": entry.unit or "",
                        "quantity": entry.quantity or 1,
                        "desc": entry.description or "",
                    }
                    for entry in entries
                ],
            },
            "signerKey": signer_key,
            "canSign": can_sign,
            "canEditObservations": can_edit_observations,
            "csrfToken": get_token(request),
        }
    response = render(request, template, {
        "report": report,
        "project": report.project,
        "receipt": receipt,
        "share_token": share_token,
        "entries": entries,
        "blank_rows": range(max(len(entries), 1) + 1, 7),
        "signers": signed_status,
        "signer": signer,
        "signer_key": signer_key,
        "signer_name": signer_name,
        "signer_dni": signer_dni,
        "signer_position": signer_position,
        "identity_input": identity_input,
        "reauth_required": bool(reauth_signer_key),
        "reauth_signer_label": MATERIAL_RECEIPT_SHARE_SIGNERS[reauth_signer_key]["label"] if reauth_signer_key else "",
        "next_signer": MATERIAL_RECEIPT_SHARE_SIGNERS[next_signer]["label"] if next_signer else "",
        "next_signer_key": next_signer or "",
        "is_signed": is_signed,
        "can_sign": can_sign,
        "can_edit_observations": can_edit_observations,
        "observations_saved": request.session.pop(observations_saved_key, False),
        "signer_waiting_for": signer_waiting_for,
        "all_signed": next_signer is None,
        "shared_preview": shared_preview,
        "message": message,
    }, status=429 if receipt.share_password_locked_until and receipt.share_password_locked_until > timezone.now() else 200)
    response["Cache-Control"] = "no-store, private"
    response["X-Robots-Tag"] = "noindex, nofollow, noarchive"
    return response


@require_http_methods(["GET"])
def material_receipt_shared_pdf(request, share_token):
    receipt = get_object_or_404(
        MaterialReceipt.objects.select_related("report__project").prefetch_related("report__entries"),
        share_token=share_token,
    )
    if not _material_receipt_share_configured(receipt) or _next_material_receipt_signer(receipt):
        return render(
            request,
            "report_app/material_receipt_pdf_unavailable.html",
            {"share_token": share_token},
            status=403,
        )
    share_session_key = f"material_receipt_signer:{share_token}"
    session_version_key = f"material_receipt_share_version:{share_token}"
    if (
        request.session.get(share_session_key) not in MATERIAL_RECEIPT_SHARE_SIGNERS
        or request.session.get(session_version_key) != receipt.share_access_version
    ):
        return redirect("material_receipt_share", share_token=share_token)
    report = receipt.report

    from reportlab.lib import colors
    from reportlab.lib.enums import TA_CENTER
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
    from reportlab.lib.units import mm
    from reportlab.platypus import Image as PdfImage, KeepTogether, PageBreak, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

    output = BytesIO()
    page_width, page_height = A4
    document = SimpleDocTemplate(
        output,
        pagesize=A4,
        rightMargin=13 * mm,
        leftMargin=13 * mm,
        topMargin=13 * mm,
        bottomMargin=15 * mm,
        title="Acta de entrega de materiales",
    )
    styles = getSampleStyleSheet()
    title_style = ParagraphStyle("ReceiptTitle", parent=styles["Title"], fontName="Helvetica-Bold", fontSize=13, leading=16, alignment=TA_CENTER, textColor=colors.HexColor("#28599c"))
    body_style = ParagraphStyle("ReceiptBody", parent=styles["BodyText"], fontName="Helvetica", fontSize=8, leading=10)
    small_style = ParagraphStyle("ReceiptSmall", parent=body_style, fontSize=7, leading=9)
    header_style = ParagraphStyle("ReceiptHeader", parent=small_style, fontName="Helvetica-Bold", textColor=colors.white, alignment=TA_CENTER)
    signer_title_style = ParagraphStyle("ReceiptSignerTitle", parent=small_style, fontName="Helvetica-Bold", textColor=colors.HexColor("#28599c"), alignment=TA_CENTER)

    def safe_paragraph(value, style=body_style, markup=False):
        content = str(value or "") if markup else escape_html(str(value or "")).replace("\n", "<br/>")
        return Paragraph(content, style)

    def image_flowable(file_field, max_width, max_height):
        if not file_field:
            return ""
        from PIL import Image

        max_pixels = (max(1, round(max_width / 72 * 150)), max(1, round(max_height / 72 * 150)))
        with file_field.open("rb") as image_file:
            with Image.open(image_file) as image:
                image = image.convert("RGB")
                image.thumbnail(max_pixels, Image.Resampling.LANCZOS)
                image_data = BytesIO()
                image.save(image_data, format="JPEG", quality=76, optimize=True, progressive=True)
        image_data.seek(0)
        return PdfImage(image_data, width=max_width, height=max_height, kind="proportional")

    story = []
    def build_header():
        logo = image_flowable(receipt.company_logo, 27 * mm, 17 * mm)
        header = Table(
            [[logo, safe_paragraph("ACTA DE ENTREGA Y RECEPCIÓN DE MATERIALES", title_style),
              safe_paragraph(f"<b>N.°:</b> {escape_html(receipt.act_number or '—')}<br/><b>Fecha:</b> {escape_html(receipt.receipt_date.strftime('%d/%m/%Y') if receipt.receipt_date else '—')}", small_style, markup=True)]],
            colWidths=[35 * mm, 105 * mm, 44 * mm],
        )
        header.setStyle(TableStyle([
            ("BOX", (0, 0), (-1, -1), 0.7, colors.black),
            ("INNERGRID", (0, 0), (-1, -1), 0.5, colors.black),
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ("ALIGN", (0, 0), (-1, -1), "CENTER"),
            ("LEFTPADDING", (0, 0), (-1, -1), 4),
            ("RIGHTPADDING", (0, 0), (-1, -1), 4),
            ("TOPPADDING", (0, 0), (-1, -1), 6),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
        ]))
        return header

    story.extend([build_header(), Spacer(1, 5 * mm)])
    story.append(safe_paragraph(
        f"Proyecto: <b>{escape_html(report.project.project_name or '—')}</b> "
        f"&nbsp;&nbsp; Ubicación: <b>{escape_html(report.project.project_location or '—')}</b>",
        body_style,
        markup=True,
    ))
    story.append(Spacer(1, 3 * mm))
    table_data = [[
        safe_paragraph("N.°", header_style),
        safe_paragraph("Descripción", header_style),
        safe_paragraph("Und.", header_style),
        safe_paragraph("Cantidad", header_style),
        safe_paragraph("Observaciones", header_style),
    ]]
    for index, entry in enumerate(report.entries.all().order_by("id"), 1):
        table_data.append([
            safe_paragraph(str(index), small_style),
            safe_paragraph(entry.item_name, small_style),
            safe_paragraph(entry.unit, small_style),
            safe_paragraph(str(entry.quantity), small_style),
            safe_paragraph(entry.description, small_style),
        ])
    if len(table_data) == 1:
        table_data.append([safe_paragraph(str(i), small_style) for i in ("1", "", "", "", "")])
    materials_table = Table(table_data, colWidths=[10 * mm, 65 * mm, 17 * mm, 23 * mm, 69 * mm], repeatRows=1)
    materials_table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#28599c")),
        ("GRID", (0, 0), (-1, -1), 0.5, colors.black),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("ALIGN", (0, 0), (0, -1), "CENTER"),
        ("ALIGN", (2, 0), (3, -1), "CENTER"),
        ("LEFTPADDING", (0, 0), (-1, -1), 4),
        ("RIGHTPADDING", (0, 0), (-1, -1), 4),
        ("TOPPADDING", (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
    ]))
    story.extend([materials_table, Spacer(1, 5 * mm)])
    conformity = {
        "conforme": "Recibido conforme",
        "observado": "Recibido con observaciones",
        "parcial": "Entrega parcial",
    }.get(receipt.conformity, "Sin especificar")
    closing = [
        safe_paragraph("<b>CONFORMIDAD DE RECEPCIÓN</b>", body_style, markup=True),
        safe_paragraph(f"Resultado: <b>{escape_html(conformity)}</b>", body_style, markup=True),
        safe_paragraph(f"Observaciones: {escape_html(receipt.observations or '—').replace(chr(10), '<br/>')}", body_style, markup=True),
        Spacer(1, 4 * mm),
        safe_paragraph("<b>FIRMAS DE RESPONSABILIDAD</b>", body_style, markup=True),
    ]
    signer_cells = []
    for signer_key in MATERIAL_RECEIPT_SIGNING_ORDER:
        signer_data = MATERIAL_RECEIPT_SHARE_SIGNERS[signer_key]
        signature = image_flowable(getattr(receipt, signer_data["signature_field"]), 48 * mm, 17 * mm)
        signed_on = getattr(receipt, signer_data["signed_on_field"])
        details = [
            safe_paragraph(signer_data["label"], signer_title_style),
            signature or Spacer(1, 17 * mm),
            safe_paragraph(f"Nombre: {getattr(receipt, signer_data['name_field'])}", small_style),
            safe_paragraph(f"DNI: {getattr(receipt, signer_data['dni_field'])}", small_style),
            safe_paragraph(f"Cargo: {getattr(receipt, signer_data['position_field'])}", small_style),
            safe_paragraph(f"Fecha: {signed_on.strftime('%d/%m/%Y') if signed_on else '—'}", small_style),
        ]
        signer_cells.append(details)
    signatures_table = Table([signer_cells], colWidths=[61 * mm, 61 * mm, 62 * mm])
    signatures_table.setStyle(TableStyle([
        ("BOX", (0, 0), (-1, -1), 0.6, colors.black),
        ("INNERGRID", (0, 0), (-1, -1), 0.5, colors.black),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("ALIGN", (0, 0), (-1, -1), "CENTER"),
        ("LEFTPADDING", (0, 0), (-1, -1), 4),
        ("RIGHTPADDING", (0, 0), (-1, -1), 4),
        ("TOPPADDING", (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
    ]))
    story.append(KeepTogether([*closing, signatures_table]))

    receipt_photos = list(receipt.photos.all())
    for photo_page_index in range(0, len(receipt_photos), 4):
        page_photos = receipt_photos[photo_page_index:photo_page_index + 4]
        story.extend([
            PageBreak(),
            build_header(),
            Spacer(1, 5 * mm),
            safe_paragraph("VALIDACIÓN FOTOGRÁFICA", title_style),
            Spacer(1, 4 * mm),
        ])
        photo_cells = []
        for photo_index in range(4):
            absolute_index = photo_page_index + photo_index
            if photo_index < len(page_photos):
                photo_image = image_flowable(page_photos[photo_index].image, 80 * mm, 84 * mm)
                cell_content = [
                    safe_paragraph(f"FOTO {absolute_index + 1}", signer_title_style),
                    Spacer(1, 2 * mm),
                    photo_image,
                ]
            else:
                cell_content = [
                    safe_paragraph(f"FOTO {absolute_index + 1}", signer_title_style),
                    Spacer(1, 2 * mm),
                    Spacer(1, 84 * mm),
                ]
            photo_cells.append(cell_content)
        photo_grid = Table(
            [[photo_cells[0], photo_cells[1]], [photo_cells[2], photo_cells[3]]],
            colWidths=[86 * mm, 86 * mm],
            rowHeights=[100 * mm, 100 * mm],
        )
        photo_grid.setStyle(TableStyle([
            ("BOX", (0, 0), (-1, -1), 0.7, colors.HexColor("#8793a3")),
            ("INNERGRID", (0, 0), (-1, -1), 0.7, colors.HexColor("#8793a3")),
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ("ALIGN", (0, 0), (-1, -1), "CENTER"),
            ("LEFTPADDING", (0, 0), (-1, -1), 3),
            ("RIGHTPADDING", (0, 0), (-1, -1), 3),
            ("TOPPADDING", (0, 0), (-1, -1), 3),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
        ]))
        story.append(photo_grid)

    def draw_page_number(pdf_canvas, doc):
        pdf_canvas.saveState()
        pdf_canvas.setFont("Helvetica", 8)
        pdf_canvas.setFillColor(colors.HexColor("#64748b"))
        pdf_canvas.drawCentredString(page_width / 2, 8 * mm, f"Acta {receipt.act_number or ''} · Página {doc.page}")
        pdf_canvas.restoreState()

    document.build(story, onFirstPage=draw_page_number, onLaterPages=draw_page_number)
    response = HttpResponse(output.getvalue(), content_type="application/pdf")
    response["Content-Disposition"] = f'attachment; filename="acta-materiales-{receipt.pk}.pdf"'
    response["Cache-Control"] = "no-store, private"
    return response


@login_required
@require_http_methods(["GET"])
def material_receipt_template_pdf(request):
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4
    from reportlab.pdfgen import canvas

    output = BytesIO()
    pdf = canvas.Canvas(output, pagesize=A4)
    form = pdf.acroForm
    page_width, page_height = A4
    margin = 30

    def field(name, x, y, width, height=17, multiline=False, border_style="solid"):
        form.textfield(
            name=name,
            x=x,
            y=y,
            width=width,
            height=height,
            borderStyle=border_style,
            borderWidth=0.5,
            borderColor=colors.HexColor("#64748b"),
            fillColor=colors.white if border_style == "solid" else None,
            textColor=colors.HexColor("#111827"),
            fontName="Helvetica",
            fontSize=8,
            forceBorder=True,
            fieldFlags="multiline" if multiline else "",
        )

    pdf.setTitle("Acta de entrega de materiales - Formato Universidad de Lima")
    blue = colors.HexColor("#28599c")
    line = colors.HexColor("#111111")
    left = margin
    right = page_width - margin
    total_width = right - left
    header_top = page_height - 26
    header_bottom = header_top - 56
    brand_width = 124
    details_width = 110
    brand_right = left + brand_width
    details_left = right - details_width
    header_center = (brand_right + details_left) / 2

    pdf.setStrokeColor(line)
    pdf.setLineWidth(0.8)
    pdf.rect(left, header_bottom, total_width, header_top - header_bottom, fill=0, stroke=1)
    pdf.line(brand_right, header_bottom, brand_right, header_top)
    pdf.line(details_left, header_bottom, details_left, header_top)

    logo_x = left + 22
    logo_y = header_bottom + 28
    pdf.setFillColor(colors.HexColor("#ef6c25"))
    for angle in range(0, 360, 45):
        radians = math.radians(angle)
        pdf.circle(logo_x + math.cos(radians) * 7, logo_y + math.sin(radians) * 7, 3.2, fill=1, stroke=0)
    pdf.circle(logo_x, logo_y, 2.4, fill=1, stroke=0)
    pdf.setFillColor(line)
    pdf.setFont("Helvetica", 7)
    pdf.drawString(left + 43, logo_y + 3, "UNIVERSIDAD")
    pdf.drawString(left + 43, logo_y - 6, "DE LIMA")

    center_width = details_left - brand_right
    first_row_height = 17
    second_row_height = 19
    pdf.setFillColor(blue)
    pdf.rect(brand_right, header_top - first_row_height, center_width, first_row_height, fill=1, stroke=0)
    pdf.setFillColor(line)
    for y in (header_top - first_row_height, header_top - first_row_height - second_row_height):
        pdf.line(brand_right, y, details_left, y)
    pdf.setFillColor(colors.white)
    pdf.setFont("Helvetica-Bold", 8)
    pdf.drawCentredString(header_center, header_top - 11.5, "FORMATO – ACTA DE ENTREGA DE MATERIALES")
    pdf.setFillColor(line)
    pdf.setFont("Helvetica", 7.5)
    pdf.drawCentredString(header_center, header_top - first_row_height - 13, "CONTROL DE ENTREGA Y RECEPCIÓN")
    pdf.drawCentredString(header_center, header_bottom + 5.5, "ÁREA DE ALMACÉN / LOGÍSTICA / PROYECTO")

    code_row_bottom = header_top - 18
    version_row_bottom = header_top - 34
    pdf.line(details_left, code_row_bottom, right, code_row_bottom)
    pdf.line(details_left, version_row_bottom, right, version_row_bottom)
    pdf.setFont("Helvetica", 7)
    pdf.drawString(details_left + 4, header_top - 11, "Código:")
    field("numero_acta", details_left + 34, header_top - 15, details_width - 39, 11)
    pdf.drawString(details_left + 4, code_row_bottom - 11, "Versión: 01")
    pdf.drawString(details_left + 4, version_row_bottom - 10, "Fecha:")
    field("fecha", details_left + 31, version_row_bottom - 13, details_width - 36, 10)
    pdf.setFont("Helvetica-Bold", 7)
    pdf.drawString(details_left + 4, header_bottom + 4, "Página: 1 de 1")

    pdf.setFillColor(blue)
    pdf.setFont("Helvetica-Bold", 13)
    pdf.drawCentredString(page_width / 2, 731, "ACTA DE ENTREGA DE MATERIALES")
    pdf.setFillColor(line)
    pdf.setFont("Helvetica", 7.5)
    pdf.drawString(left + 10, 712, "Por medio de la presente, se deja constancia de la entrega y recepción de los materiales que se detallan a continuación,")
    pdf.drawString(left + 10, 700, "realizada en fecha")
    field("fecha_entrega", left + 76, 696, 90, 12, border_style="underlined")
    pdf.drawString(left + 170, 700, ", en")
    field("ubicacion", left + 184, 696, right - left - 194, 12, border_style="underlined")

    pdf.setFillColor(blue)
    pdf.setFont("Helvetica-Bold", 8)
    pdf.drawString(left + 7, 678, "DETALLE DE LOS MATERIALES ENTREGADOS")

    column_widths = [27, 245, 51, 51, total_width - 374]
    labels = ["N.°", "DESCRIPCIÓN DEL MATERIAL", "UNIDAD", "CANTIDAD", "OBSERVACIONES"]
    x_positions = [left]
    for width in column_widths:
        x_positions.append(x_positions[-1] + width)
    table_top = 665
    header_height = 26
    material_row_height = 25
    content_offset = 0
    table_bottom = table_top - header_height - material_row_height * 6
    pdf.setFillColor(blue)
    pdf.rect(left, table_top - header_height, total_width, header_height, fill=1, stroke=0)
    pdf.setFillColor(colors.white)
    pdf.setFont("Helvetica-Bold", 6.5)
    for index, label in enumerate(labels):
        pdf.drawString(x_positions[index] + 3, table_top - 16, label)
    pdf.setStrokeColor(line)
    pdf.setLineWidth(0.65)
    for x in x_positions:
        pdf.line(x, table_top, x, table_bottom)
    for row in range(7):
        y = table_top - header_height - row * material_row_height
        pdf.line(left, y, right, y)
    for row in range(6):
        row_top = table_top - header_height - row * material_row_height
        pdf.setFillColor(line)
        pdf.setFont("Helvetica", 7)
        pdf.drawCentredString((x_positions[0] + x_positions[1]) / 2, row_top - material_row_height / 2 - 2, str(row + 1))
        multiline_height = material_row_height - 8
        multiline_y = row_top - material_row_height + 4
        single_line_y = row_top - (material_row_height + 17) / 2
        field(
            f"material_{row + 1}_descripcion",
            x_positions[1] + 2,
            multiline_y,
            column_widths[1] - 4,
            multiline_height,
            multiline=True,
        )
        field(
            f"material_{row + 1}_unidad",
            x_positions[2] + 2,
            single_line_y,
            column_widths[2] - 4,
            17,
        )
        field(
            f"material_{row + 1}_cantidad",
            x_positions[3] + 2,
            single_line_y,
            column_widths[3] - 4,
            17,
        )
        field(
            f"material_{row + 1}_observaciones",
            x_positions[4] + 2,
            multiline_y,
            column_widths[4] - 4,
            multiline_height,
            multiline=True,
        )

    pdf.setFillColor(blue)
    pdf.setFont("Helvetica-Bold", 8)
    pdf.drawString(left, 468 - content_offset, "CONFORMIDAD DE RECEPCIÓN")
    pdf.setFillColor(line)
    pdf.setFont("Helvetica", 7.5)
    pdf.drawString(left, 453 - content_offset, "La persona que recibe declara haber verificado los materiales y las cantidades detalladas, dejando constancia del resultado de la")
    pdf.drawString(left, 442 - content_offset, "recepción:")
    options = [
        ("conforme", "Recibido conforme", left),
        ("observado", "Recibido con observaciones", left + 112),
        ("parcial", "Entrega parcial", left + 278),
    ]
    for name, label, x in options:
        form.checkbox(name=name, x=x, y=423 - content_offset, size=8, buttonStyle="check", borderWidth=0.7, forceBorder=True)
        pdf.setFont("Helvetica-Bold", 7)
        pdf.drawString(x + 11, 425 - content_offset, label)
    pdf.setFont("Helvetica-Bold", 7.5)
    pdf.drawString(left, 407 - content_offset, "Observaciones (faltantes, daños, diferencias u otros):")
    field(
        "observaciones_generales",
        left,
        373 - content_offset,
        total_width,
        30,
        multiline=True,
        border_style="underlined",
    )

    signature_width = total_width / 3
    signers = [
        ("entrega", "ENTREGA – UNIVERSIDAD DE LIMA"),
        ("valida_vdc", "VALIDA - VDC"),
        ("recibe_cosapi", "RECIBE / VALIDA - COSAPI"),
    ]
    table_top = 335 - content_offset
    heading_height = 16
    signature_height = 42
    row_height = 18
    table_bottom = table_top - heading_height - signature_height - row_height * 3
    pdf.setFillColor(colors.white)
    pdf.setStrokeColor(line)
    pdf.setLineWidth(0.7)
    pdf.rect(left, table_bottom, total_width, table_top - table_bottom, fill=0, stroke=1)
    for index, (key, label) in enumerate(signers):
        x = left + index * signature_width
        if index:
            pdf.line(x, table_bottom, x, table_top)
        pdf.setFillColor(colors.HexColor("#e7edf5"))
        pdf.rect(x, table_top - heading_height, signature_width, heading_height, fill=1, stroke=0)
        pdf.setFillColor(line)
        pdf.setFont("Helvetica-Bold", 6.5)
        pdf.drawString(x + 5, table_top - 11, label)
        row_top = table_top - heading_height - signature_height
        pdf.line(x, row_top, x + signature_width, row_top)
        name_top = row_top - row_height
        pdf.line(x, name_top, x + signature_width, name_top)
        dni_top = name_top - row_height
        pdf.line(x, dni_top, x + signature_width, dni_top)
        date_top = dni_top - row_height
        form.textfield(
            name=f"{key}_firma",
            x=x + 5,
            y=row_top + 3,
            width=signature_width - 10,
            height=signature_height - 7,
            borderStyle="solid",
            borderWidth=0,
            fillColor=colors.white,
            textColor=line,
            fontName="Helvetica",
            fontSize=8,
            forceBorder=False,
        )
        pdf.setFillColor(line)
        pdf.setFont("Helvetica", 6.5)
        pdf.drawString(x + 5, row_top - 12, "Nombre:")
        field(f"{key}_nombre", x + 36, row_top - 15, signature_width - 42, 12, border_style="underlined")
        pdf.drawString(x + 5, name_top - 12, "DNI:")
        field(f"{key}_dni", x + 24, name_top - 15, 54, 12, border_style="underlined")
        pdf.drawString(x + 84, name_top - 12, "Cargo:")
        field(f"{key}_cargo", x + 113, name_top - 15, signature_width - 119, 12, border_style="underlined")
        pdf.drawString(x + 5, dni_top - 12, "Fecha:")
        field(f"{key}_fecha", x + 35, dni_top - 15, signature_width - 42, 12, border_style="underlined")

    pdf.setFont("Helvetica", 7)
    pdf.setFillColor(colors.HexColor("#475569"))
    pdf.drawCentredString(page_width / 2, 36, "Complete los campos editables antes de guardar o imprimir.")
    pdf.save()
    response = HttpResponse(output.getvalue(), content_type="application/pdf")
    response["Content-Disposition"] = 'attachment; filename="Acta_Entrega_Materiales_Editable.pdf"'
    return response


@login_required
@require_http_methods(["GET"])
def material_receipt_report_fillable_pdf(request, project_slug, report_id):
    project = _get_project_or_404(request.user, project_slug)
    report = _get_user_report_or_404(project, request.user, report_id)
    if report.report_type != ProjectReport.TYPE_MATERIAL_RECEIPT:
        raise Http404()
    receipt = MaterialReceipt.objects.filter(report=report).prefetch_related("photos").first()
    template_response = material_receipt_template_pdf(request)
    if not receipt or not receipt.photos.all():
        template_response["Content-Disposition"] = (
            f'attachment; filename="Acta_Entrega_Materiales_{report.pk}_Editable.pdf"'
        )
        return template_response

    from PIL import Image
    from pikepdf import Pdf, Rectangle
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.utils import ImageReader
    from reportlab.pdfgen import canvas

    photos = list(receipt.photos.all())
    photo_page_count = (len(photos) + 3) // 4
    total_pages = photo_page_count + 1
    page_width, page_height = A4
    margin = 30
    total_width = page_width - 2 * margin
    photo_pdf_buffer = BytesIO()
    photo_pdf = canvas.Canvas(photo_pdf_buffer, pagesize=A4)
    blue = colors.HexColor("#28599c")
    line = colors.HexColor("#111111")
    brand_width = 124
    details_width = 110
    brand_right = margin + brand_width
    details_left = page_width - margin - details_width
    center_width = details_left - brand_right
    header_top = page_height - 26
    header_bottom = header_top - 56

    def optimized_image(file_field, max_size):
        image_buffer = BytesIO()
        with file_field.open("rb") as source:
            with Image.open(source) as image:
                image = image.convert("RGB")
                image.thumbnail(max_size, Image.Resampling.LANCZOS)
                image.save(image_buffer, format="JPEG", quality=78, optimize=True)
        image_buffer.seek(0)
        return ImageReader(image_buffer)

    def draw_header(page_number):
        photo_pdf.setStrokeColor(line)
        photo_pdf.setLineWidth(0.8)
        photo_pdf.rect(margin, header_bottom, total_width, header_top - header_bottom, fill=0, stroke=1)
        photo_pdf.line(brand_right, header_bottom, brand_right, header_top)
        photo_pdf.line(details_left, header_bottom, details_left, header_top)
        if receipt.company_logo:
            photo_pdf.drawImage(
                optimized_image(receipt.company_logo, (600, 300)),
                margin + 10,
                header_bottom + 8,
                width=brand_width - 20,
                height=header_top - header_bottom - 16,
                preserveAspectRatio=True,
                anchor="c",
                mask="auto",
            )
        else:
            logo_x = margin + 22
            logo_y = header_bottom + 28
            photo_pdf.setFillColor(colors.HexColor("#ef6c25"))
            for angle in range(0, 360, 45):
                radians = math.radians(angle)
                photo_pdf.circle(
                    logo_x + math.cos(radians) * 7,
                    logo_y + math.sin(radians) * 7,
                    3.2,
                    fill=1,
                    stroke=0,
                )
            photo_pdf.circle(logo_x, logo_y, 2.4, fill=1, stroke=0)
            photo_pdf.setFillColor(line)
            photo_pdf.setFont("Helvetica", 7)
            photo_pdf.drawString(margin + 43, logo_y + 3, "UNIVERSIDAD")
            photo_pdf.drawString(margin + 43, logo_y - 6, "DE LIMA")

        photo_pdf.setFillColor(blue)
        photo_pdf.rect(brand_right, header_top - 17, center_width, 17, fill=1, stroke=0)
        photo_pdf.setFillColor(colors.white)
        photo_pdf.setFont("Helvetica-Bold", 8)
        photo_pdf.drawCentredString(
            brand_right + center_width / 2,
            header_top - 11.5,
            "FORMATO – ACTA DE ENTREGA DE MATERIALES",
        )
        photo_pdf.setFillColor(line)
        photo_pdf.setFont("Helvetica", 7.5)
        photo_pdf.drawCentredString(
            brand_right + center_width / 2,
            header_top - 30,
            "CONTROL DE ENTREGA Y RECEPCIÓN",
        )
        photo_pdf.drawCentredString(
            brand_right + center_width / 2,
            header_bottom + 5.5,
            "ÁREA DE ALMACÉN / LOGÍSTICA / PROYECTO",
        )
        photo_pdf.line(details_left, header_top - 18, page_width - margin, header_top - 18)
        photo_pdf.line(details_left, header_top - 34, page_width - margin, header_top - 34)
        photo_pdf.setFont("Helvetica", 7)
        photo_pdf.drawString(details_left + 4, header_top - 11, f"Código: {receipt.act_number or '—'}")
        photo_pdf.drawString(details_left + 4, header_top - 27, "Versión: 01")
        photo_pdf.drawString(details_left + 4, header_top - 44, f"Fecha: {receipt.receipt_date.strftime('%d/%m/%Y') if receipt.receipt_date else '—'}")
        photo_pdf.setFont("Helvetica-Bold", 7)
        photo_pdf.drawString(
            details_left + 4,
            header_bottom + 4,
            f"Página: {page_number} de {total_pages}",
        )

    grid_left = margin
    grid_width = total_width
    grid_top = header_bottom - 30
    grid_bottom = 154
    gap = 14
    slot_width = (grid_width - gap) / 2
    slot_height = (grid_top - grid_bottom - gap) / 2

    signer_width = total_width / len(MATERIAL_RECEIPT_SHARE_SIGNERS)
    signer_bottom = 28
    signer_height = 112
    signer_header_height = 16
    signer_signature_height = 42
    signer_row_height = 18
    signer_keys = list(MATERIAL_RECEIPT_SHARE_SIGNERS)

    def draw_photo_signatures():
        for signer_index, signer_key in enumerate(signer_keys):
            signer = MATERIAL_RECEIPT_SHARE_SIGNERS[signer_key]
            x = margin + signer_index * signer_width
            photo_pdf.setStrokeColor(line)
            photo_pdf.setLineWidth(0.7)
            table_top = signer_bottom + signer_height
            table_bottom = table_top - signer_header_height - signer_signature_height - signer_row_height * 3
            photo_pdf.rect(x, table_bottom, signer_width, table_top - table_bottom, fill=0, stroke=1)
            photo_pdf.setFillColor(colors.HexColor("#e7edf5"))
            photo_pdf.rect(
                x,
                table_top - signer_header_height,
                signer_width,
                signer_header_height,
                fill=1,
                stroke=0,
            )
            photo_pdf.setFillColor(blue)
            photo_pdf.setFont("Helvetica-Bold", 6.5)
            photo_pdf.drawString(x + 5, table_top - 11, signer["label"])
            signature_top = table_top - signer_header_height
            row_top = signature_top - signer_signature_height
            name_top = row_top - signer_row_height
            dni_top = name_top - signer_row_height
            date_top = dni_top - signer_row_height
            photo_pdf.setStrokeColor(line)
            photo_pdf.line(x, row_top, x + signer_width, row_top)
            photo_pdf.line(x, name_top, x + signer_width, name_top)
            photo_pdf.line(x, dni_top, x + signer_width, dni_top)
            photo_pdf.line(x, date_top, x + signer_width, date_top)
            signature = getattr(receipt, signer["signature_field"])
            if signature:
                photo_pdf.drawImage(
                    optimized_image(signature, (600, 300)),
                    x + 7,
                    row_top + 3,
                    width=signer_width - 14,
                    height=signer_signature_height - 7,
                    preserveAspectRatio=True,
                    anchor="c",
                    mask="auto",
                )
            photo_pdf.setFillColor(line)
            photo_pdf.setFont("Helvetica", 6.5)
            photo_pdf.drawString(x + 5, row_top - 12, "Nombre:")
            photo_pdf.drawString(x + 5, name_top - 12, "DNI:")
            photo_pdf.drawString(x + 84, name_top - 12, "Cargo:")
            photo_pdf.drawString(x + 5, dni_top - 12, "Fecha:")

            def draw_field_value(value, field_x, field_y, field_width):
                text = str(value or "").replace("\n", " ")
                clip = photo_pdf.beginPath()
                clip.rect(field_x, field_y, field_width, 12)
                photo_pdf.saveState()
                photo_pdf.clipPath(clip, stroke=0, fill=0)
                photo_pdf.drawString(field_x, field_y + 3, text)
                photo_pdf.restoreState()

            draw_field_value(
                getattr(receipt, signer["name_field"]),
                x + 36,
                row_top - 15,
                signer_width - 42,
            )
            draw_field_value(
                getattr(receipt, signer["dni_field"]),
                x + 24,
                name_top - 15,
                54,
            )
            draw_field_value(
                getattr(receipt, signer["position_field"]),
                x + 113,
                name_top - 15,
                signer_width - 119,
            )
            signed_on = getattr(receipt, signer["signed_on_field"])
            draw_field_value(
                signed_on.strftime("%d/%m/%Y") if signed_on else "",
                x + 35,
                dni_top - 15,
                signer_width - 42,
            )

    for photo_page_index in range(photo_page_count):
        draw_header(photo_page_index + 2)
        photo_pdf.setFillColor(blue)
        photo_pdf.setFont("Helvetica-Bold", 13)
        photo_pdf.drawCentredString(page_width / 2, header_bottom - 19, "VALIDACIÓN FOTOGRÁFICA")
        for slot_index in range(4):
            photo_index = photo_page_index * 4 + slot_index
            column = slot_index % 2
            row = slot_index // 2
            x = grid_left + column * (slot_width + gap)
            y = grid_bottom + (1 - row) * (slot_height + gap)
            photo_pdf.setStrokeColor(colors.HexColor("#8793a3"))
            photo_pdf.setLineWidth(0.8)
            photo_pdf.rect(x, y, slot_width, slot_height, fill=0, stroke=1)
            photo_pdf.setFillColor(blue)
            photo_pdf.setFont("Helvetica-Bold", 8)
            photo_pdf.drawCentredString(x + slot_width / 2, y + slot_height - 14, f"FOTO {photo_index + 1}")
            if photo_index < len(photos):
                photo_pdf.drawImage(
                    optimized_image(photos[photo_index].image, (1200, 1200)),
                    x + 7,
                    y + 7,
                    width=slot_width - 14,
                    height=slot_height - 27,
                    preserveAspectRatio=True,
                    anchor="c",
                    mask="auto",
                )
            else:
                photo_pdf.setFillColor(colors.HexColor("#8793a3"))
                photo_pdf.setFont("Helvetica", 9)
                photo_pdf.drawCentredString(x + slot_width / 2, y + slot_height / 2, "Espacio disponible")
        photo_pdf.setFillColor(blue)
        photo_pdf.setFont("Helvetica-Bold", 8)
        photo_pdf.drawCentredString(
            page_width / 2,
            signer_bottom + signer_height + 5,
            "FIRMAS DE RESPONSABILIDAD",
        )
        draw_photo_signatures()
        photo_pdf.showPage()
    photo_pdf.save()
    photo_pdf_buffer.seek(0)

    template_buffer = BytesIO(template_response.content)
    output = BytesIO()
    with Pdf.open(template_buffer) as fillable_pdf, Pdf.open(photo_pdf_buffer) as photos_pdf:
        if len(photos):
            page_number_overlay_buffer = BytesIO()
            page_number_overlay = canvas.Canvas(page_number_overlay_buffer, pagesize=A4)
            page_number_overlay.setFillColor(colors.white)
            page_number_overlay.rect(margin + 2, header_bottom + 2, 100, 11, fill=1, stroke=0)
            page_number_overlay.setFillColor(line)
            page_number_overlay.setFont("Helvetica-Bold", 7)
            page_number_overlay.drawString(margin + 4, header_bottom + 4, f"Página: 1 de {total_pages}")
            page_number_overlay.save()
            page_number_overlay_buffer.seek(0)
            with Pdf.open(page_number_overlay_buffer) as overlay_pdf:
                fillable_pdf.pages[0].add_overlay(overlay_pdf.pages[0], Rectangle(0, 0, page_width, page_height))
        fillable_pdf.pages.extend(photos_pdf.pages)
        fillable_pdf.save(output)

    response = HttpResponse(output.getvalue(), content_type="application/pdf")
    response["Content-Disposition"] = (
        f'attachment; filename="Acta_Entrega_Materiales_{report.pk}_Editable.pdf"'
    )
    response["Cache-Control"] = "private, no-store"
    return response


@login_required
@require_http_methods(["DELETE"])
def project_report_detail_api(request, project_slug, report_id):
    project = _get_project_or_404(request.user, project_slug)
    report = _get_user_report_or_404(project, request.user, report_id)
    if not _can_edit_report(report, request.user):
        return JsonResponse({"error": "No tienes permisos para eliminar este reporte."}, status=403)
    report.delete()
    return JsonResponse({"ok": True})


@login_required
@require_http_methods(["POST"])
def report_members_api(request, project_slug, report_id):
    project = _get_project_or_404(request.user, project_slug)
    report = _get_user_report_or_404(project, request.user, report_id)
    if not _can_share_report(report, request.user):
        return JsonResponse({"error": "No tienes permisos para compartir este reporte."}, status=403)

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

    ReportMembership.objects.update_or_create(
        report=report,
        user=invitee,
        defaults={"role": role},
    )
    project = _get_project_or_404(request.user, project.slug)
    report = _get_user_report_or_404(project, request.user, report.id)
    return JsonResponse({"members": _serialize_report_members(report)})


@_report_access_required
@require_http_methods(["POST"])
def report_fronts_api(request, project_slug, report_id):
    _, report, is_public_share = _report_access_for_request(request, project_slug, report_id)
    if not is_public_share and not _can_edit_report(report, request.user):
        return JsonResponse({"error": "No tienes permisos para editar este reporte."}, status=403)

    payload = _parse_json(request)
    if payload is None:
        return HttpResponseBadRequest("JSON inválido")
    name = (payload.get("name") or "").strip()
    if not name:
        return JsonResponse({"error": "El nombre del frente es obligatorio."}, status=400)

    front = ReportFront.objects.create(report=report, name=name, sort_order=report.fronts.count())
    return JsonResponse({"front": {"id": front.id, "name": front.name}}, status=201)


@_report_access_required
@require_http_methods(["POST", "DELETE"])
def report_front_detail_api(request, project_slug, report_id, front_id):
    _, report, is_public_share = _report_access_for_request(request, project_slug, report_id)
    front = get_object_or_404(report.fronts.all(), pk=front_id)

    if request.method == "POST":
        if not is_public_share and not _can_edit_report(report, request.user):
            return JsonResponse({"error": "No tienes permisos para editar frentes en este reporte."}, status=403)
        payload = _parse_json(request)
        if payload is None:
            return HttpResponseBadRequest("JSON inválido")
        name = (payload.get("name") or "").strip()
        if not name:
            return JsonResponse({"error": "El nombre del frente es obligatorio."}, status=400)
        front.name = name
        front.save(update_fields=["name"])
        return JsonResponse({"front": {"id": front.id, "name": front.name}})

    if not is_public_share and not _can_edit_report(report, request.user):
        return JsonResponse({"error": "No tienes permisos para eliminar frentes en este reporte."}, status=403)
    front.delete()
    return JsonResponse({"ok": True})


@_report_access_required
@require_http_methods(["POST"])
def report_entries_api(request, project_slug, report_id):
    project, report, is_public_share = _report_access_for_request(request, project_slug, report_id)
    if not is_public_share and not _can_edit_report(report, request.user):
        return JsonResponse({"error": "No tienes permisos para crear issues en este reporte."}, status=403)
    if is_public_share:
        image_limit = 1 if report.report_type in {ProjectReport.TYPE_EQUIPMENT, ProjectReport.TYPE_MATERIAL_RECEIPT} else 10
        image_error = _validate_public_report_images(request.FILES.getlist("images"), max_count=image_limit)
        if image_error:
            return JsonResponse({"error": image_error}, status=400)

    payload = _request_data(request)
    if payload is None:
        return HttpResponseBadRequest("Datos inválidos")
    front_id = payload.get("frontId")
    status = (payload.get("status") or "").strip()
    description = (payload.get("desc") or "").strip()
    item_name = (payload.get("itemName") or payload.get("item_name") or "").strip()
    building_location = (payload.get("buildingLocation") or payload.get("building_location") or "").strip()
    incident_date = None
    incident_date_value = (payload.get("incidentDate") or payload.get("incident_date") or "").strip()
    if incident_date_value:
        try:
            incident_date = datetime.strptime(incident_date_value, "%Y-%m-%d").date()
        except ValueError:
            return JsonResponse({"error": "La fecha del issue no es válida."}, status=400)
    responsible_company = (payload.get("responsibleCompany") or "").strip()
    try:
        plan_id = int(payload.get("planId")) if payload.get("planId") else None
        plan_x = float(payload.get("planX")) if payload.get("planX") not in (None, "") else None
        plan_y = float(payload.get("planY")) if payload.get("planY") not in (None, "") else None
    except (TypeError, ValueError):
        return JsonResponse({"error": "La ubicación del plano no es válida."}, status=400)
    if plan_id is not None:
        plan = get_object_or_404(project.plans.all(), pk=plan_id)
        if plan_x is None or plan_y is None or not (0 <= plan_x <= 1 and 0 <= plan_y <= 1):
            return JsonResponse({"error": "Selecciona un punto válido dentro del plano."}, status=400)
        if not building_location:
            point_count = report.entries.filter(plan_id=plan_id, plan_x__isnull=False, plan_y__isnull=False).count()
            building_location = f"Punto {point_count + 1}"
    try:
        quantity = int(payload.get("quantity") or 1)
    except (TypeError, ValueError):
        quantity = 1
    quantity = max(1, quantity)

    if report.report_type in {ProjectReport.TYPE_EQUIPMENT, ProjectReport.TYPE_MATERIAL_RECEIPT}:
        if not item_name:
            return JsonResponse({"error": "El nombre del material o equipo es obligatorio."}, status=400)
        if not status:
            return JsonResponse({"error": "El estado o condición es obligatorio."}, status=400)
        if report.report_type == ProjectReport.TYPE_MATERIAL_RECEIPT:
            condition = (payload.get("condition") or status).strip()
            if status not in MATERIAL_CONDITIONS or condition not in MATERIAL_CONDITIONS:
                return JsonResponse({"error": "El estado del material no es válido."}, status=400)
            if len(item_name) > 200 or len(payload.get("unit") or "") > 40:
                return JsonResponse({"error": "La descripción o unidad del material supera el máximo permitido."}, status=400)
        if not front_id:
            front = report.fronts.order_by("sort_order", "id").first()
            if not front:
                front_name = "Materiales" if report.report_type == ProjectReport.TYPE_MATERIAL_RECEIPT else "Equipos"
                front = ReportFront.objects.create(report=report, name=front_name, sort_order=0)
            front_id = front.id
        else:
            front = get_object_or_404(report.fronts.all(), pk=front_id)
        new_images = request.FILES.getlist("images")
        if len(new_images) > 1:
            return JsonResponse({"error": "Solo se permite una foto por equipo."}, status=400)
        entry = ReportEntry.objects.create(
            report=report,
            front=front,
            item_name=item_name,
            building_location=building_location,
            quantity=quantity,
            unit=(payload.get("unit") or "").strip(),
            condition=(payload.get("condition") or status).strip(),
            status=status,
            description=description,
        )
        for index, image in enumerate(new_images):
            EntryImage.objects.create(entry=entry, image=image, sort_order=index)
        entry = ReportEntry.objects.prefetch_related("images").get(pk=entry.pk)
        return JsonResponse({"entry": _serialize_entry(entry)}, status=201)

    if not front_id or not status:
        return JsonResponse({"error": "Frente y estado son obligatorios."}, status=400)
    allowed_statuses = INCIDENT_ENTRY_STATUSES if report.report_type == ProjectReport.TYPE_INCIDENT else PROGRESS_ENTRY_STATUSES
    if status not in allowed_statuses:
        return JsonResponse({"error": "El estado no corresponde al tipo de reporte."}, status=400)
    if report.report_type == ProjectReport.TYPE_INCIDENT and not incident_date:
        return JsonResponse({"error": "La fecha del issue es obligatoria para una incidencia."}, status=400)
    front = get_object_or_404(report.fronts.all(), pk=front_id)
    entry = ReportEntry.objects.create(
        report=report, front=front, status=status, description=description,
        incident_date=incident_date, responsible_company=responsible_company,
        plan_id=plan_id, plan_x=plan_x, plan_y=plan_y,
    )
    for index, image in enumerate(request.FILES.getlist("images")):
        EntryImage.objects.create(entry=entry, image=image, sort_order=index)
    entry = ReportEntry.objects.prefetch_related("images").get(pk=entry.pk)
    return JsonResponse({"entry": _serialize_entry(entry)}, status=201)


@_report_access_required
@require_http_methods(["POST", "DELETE"])
def report_entry_detail_api(request, project_slug, report_id, entry_id):
    project, report, is_public_share = _report_access_for_request(request, project_slug, report_id)
    entry = get_object_or_404(report.entries.prefetch_related("images"), pk=entry_id)
    if not is_public_share and not _can_edit_report(report, request.user):
        return JsonResponse({"error": "No tienes permisos para modificar este issue."}, status=403)

    if request.method == "DELETE":
        entry.delete()
        return JsonResponse({"ok": True})

    payload = _request_data(request)
    if payload is None:
        return HttpResponseBadRequest("Datos inválidos")
    if is_public_share:
        image_limit = 1 if report.report_type in {ProjectReport.TYPE_EQUIPMENT, ProjectReport.TYPE_MATERIAL_RECEIPT} else 10
        image_error = _validate_public_report_images(request.FILES.getlist("images"), max_count=image_limit)
        if image_error:
            return JsonResponse({"error": image_error}, status=400)
    front_id = payload.get("frontId") or entry.front_id
    status = (payload.get("status") or entry.status).strip()
    description = (payload.get("desc") or entry.description or "").strip()
    item_name = (payload.get("itemName") or payload.get("item_name") or entry.item_name or "").strip()
    if "buildingLocation" in payload:
        building_location = (payload.get("buildingLocation") or "").strip()
    elif "building_location" in payload:
        building_location = (payload.get("building_location") or "").strip()
    else:
        building_location = (entry.building_location or "").strip()
    incident_date = entry.incident_date
    incident_date_value = (payload.get("incidentDate") or payload.get("incident_date") or "").strip()
    if incident_date_value:
        try:
            incident_date = datetime.strptime(incident_date_value, "%Y-%m-%d").date()
        except ValueError:
            return JsonResponse({"error": "La fecha del issue no es válida."}, status=400)
    responsible_company = (payload.get("responsibleCompany") if payload.get("responsibleCompany") is not None else entry.responsible_company or "").strip()
    try:
        plan_id = int(payload.get("planId")) if payload.get("planId") else None
        plan_x = float(payload.get("planX")) if payload.get("planX") not in (None, "") else None
        plan_y = float(payload.get("planY")) if payload.get("planY") not in (None, "") else None
    except (TypeError, ValueError):
        return JsonResponse({"error": "La ubicación del plano no es válida."}, status=400)
    if plan_id is not None:
        get_object_or_404(project.plans.all(), pk=plan_id)
        if plan_x is None or plan_y is None or not (0 <= plan_x <= 1 and 0 <= plan_y <= 1):
            return JsonResponse({"error": "Selecciona un punto válido dentro del plano."}, status=400)
        if not building_location:
            point_count = report.entries.exclude(pk=entry.pk).filter(plan_id=plan_id, plan_x__isnull=False, plan_y__isnull=False).count()
            building_location = f"Punto {point_count + 1}"
    try:
        quantity = int(payload.get("quantity") if payload.get("quantity") is not None else entry.quantity or 1)
    except (TypeError, ValueError):
        quantity = entry.quantity or 1
    quantity = max(1, quantity)

    if report.report_type in {ProjectReport.TYPE_EQUIPMENT, ProjectReport.TYPE_MATERIAL_RECEIPT}:
        if not item_name:
            return JsonResponse({"error": "El nombre del material o equipo es obligatorio."}, status=400)
        if not status:
            return JsonResponse({"error": "El estado o condición es obligatorio."}, status=400)
        if report.report_type == ProjectReport.TYPE_MATERIAL_RECEIPT:
            condition = (payload.get("condition") or status).strip()
            if status not in MATERIAL_CONDITIONS or condition not in MATERIAL_CONDITIONS:
                return JsonResponse({"error": "El estado del material no es válido."}, status=400)
            if len(item_name) > 200 or len(payload.get("unit") or entry.unit or "") > 40:
                return JsonResponse({"error": "La descripción o unidad del material supera el máximo permitido."}, status=400)
        entry.item_name = item_name
        entry.building_location = building_location
        entry.quantity = quantity
        entry.unit = (payload.get("unit") if payload.get("unit") is not None else entry.unit or "").strip()
        entry.condition = (payload.get("condition") if payload.get("condition") is not None else status).strip()
        entry.status = status
        entry.description = description
        if front_id:
            entry.front = get_object_or_404(report.fronts.all(), pk=front_id)
        entry.save()
        replace_images = str(payload.get("replaceImages", "false")).lower() in {"1", "true", "yes"}
        new_images = request.FILES.getlist("images")
        if len(new_images) > 1:
            return JsonResponse({"error": "Solo se permite una foto por equipo."}, status=400)
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

    entry.front = get_object_or_404(report.fronts.all(), pk=front_id)
    allowed_statuses = INCIDENT_ENTRY_STATUSES if report.report_type == ProjectReport.TYPE_INCIDENT else PROGRESS_ENTRY_STATUSES
    if status not in allowed_statuses:
        return JsonResponse({"error": "El estado no corresponde al tipo de reporte."}, status=400)
    entry.status = status
    entry.description = description
    if report.report_type == ProjectReport.TYPE_INCIDENT and not incident_date:
        return JsonResponse({"error": "La fecha del issue es obligatoria para una incidencia."}, status=400)
    entry.incident_date = incident_date
    entry.responsible_company = responsible_company
    entry.building_location = building_location
    entry.plan_id = plan_id
    entry.plan_x = plan_x
    entry.plan_y = plan_y
    entry.save()

    replace_images = str(payload.get("replaceImages", "false")).lower() in {"1", "true", "yes"}
    remove_image_ids_raw = payload.get("removeImageIds") or "[]"
    try:
        remove_image_ids = [int(image_id) for image_id in json.loads(remove_image_ids_raw)]
    except (TypeError, ValueError, json.JSONDecodeError):
        return JsonResponse({"error": "La lista de fotos a eliminar no es válida."}, status=400)
    new_images = request.FILES.getlist("images")
    if replace_images and entry.images.exists():
        entry.images.all().delete()
    elif remove_image_ids:
        entry.images.filter(pk__in=remove_image_ids).delete()
    if new_images:
        if replace_images:
            entry.images.all().delete()
        next_order = entry.images.count()
        for index, image in enumerate(new_images, start=next_order):
            EntryImage.objects.create(entry=entry, image=image, sort_order=index)

    entry = ReportEntry.objects.prefetch_related("images").get(pk=entry.pk)
    return JsonResponse({"entry": _serialize_entry(entry)})
