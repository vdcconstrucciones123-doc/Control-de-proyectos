from django.shortcuts import render, redirect
from .forms import ProjectForm, ReportMetaForm, ReportTypeForm


def home(request, project_slug=None, report_id=None, front_id=None, new_report=False, new_project=False, edit_project=False):
    project_form = ProjectForm()
    report_form = ReportMetaForm()
    report_type_form = ReportTypeForm()
    # Pasar el slug a la plantilla por si es necesario en el futuro
    context = {
        "project_form": project_form,
        "report_form": report_form,
        "report_type_form": report_type_form,
        "report_id": report_id,
        "front_id": front_id,
        "new_report": new_report,
        "new_project": new_project,
        "edit_project": edit_project,
    }
    if project_slug:
        context['project_slug'] = project_slug
    return render(request, "report_app/home.html", context)


def panel(request, new_project=False):
    """Panel principal: reutiliza la misma plantilla de `home`.
    Reservado para la URL `/panel-principal/`.
    """
    return home(request, new_project=new_project)


def root_redirect(request):
    """Redirige la raíz del sitio al panel principal.
    Evita usar espacios en la URL; usamos `panel-principal`.
    """
    return redirect('panel_principal')
