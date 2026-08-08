from django.contrib.auth import views as auth_views
from django.urls import path
from . import views

urlpatterns = [
    path("acceso/", auth_views.LoginView.as_view(template_name="registration/login.html"), name="login"),
    path("salir/", auth_views.LogoutView.as_view(), name="logout"),
    path("registro/", views.register, name="register"),
    path("api/projects/", views.project_collection_api, name="project_collection_api"),
    path("api/projects/<slug:project_slug>/", views.project_detail_api, name="project_detail_api"),
    path("api/projects/<slug:project_slug>/members/", views.project_members_api, name="project_members_api"),
    path("api/projects/<slug:project_slug>/reports/", views.project_reports_api, name="project_reports_api"),
    path("api/projects/<slug:project_slug>/reports/<int:report_id>/members/", views.report_members_api, name="report_members_api"),
    path("api/projects/<slug:project_slug>/reports/<int:report_id>/", views.project_report_detail_api, name="project_report_detail_api"),
    path("api/projects/<slug:project_slug>/reports/<int:report_id>/update/", views.project_report_update_api, name="project_report_update_api"),
    path("api/projects/<slug:project_slug>/reports/<int:report_id>/fronts/", views.report_fronts_api, name="report_fronts_api"),
    path("api/projects/<slug:project_slug>/reports/<int:report_id>/fronts/<int:front_id>/", views.report_front_detail_api, name="report_front_detail_api"),
    path("api/projects/<slug:project_slug>/reports/<int:report_id>/entries/", views.report_entries_api, name="report_entries_api"),
    path("api/projects/<slug:project_slug>/reports/<int:report_id>/entries/<int:entry_id>/", views.report_entry_detail_api, name="report_entry_detail_api"),
    # Redirige la raíz al panel principal
    path("", views.root_redirect, name="root"),
    # Panel principal (dashboard)
    path("panel-principal/", views.panel, name="panel_principal"),
    # Formulario exclusivo para crear un nuevo proyecto
    path("panel-principal/proyecto/nuevo/", views.panel, {"new_project": True}, name="proyecto_nuevo"),
    # Ruta para abrir directamente la vista de proyecto (sin slug)
    path("proyecto/", views.home, name="proyecto"),
    # Ruta con slug legible: /proyecto/<slug>/ (ej: /proyecto/proyecto1/)
    path("proyecto/<slug:project_slug>/", views.home, name="proyecto_detail"),
    # Ruta para editar los datos generales de un proyecto existente
    path("proyecto/<slug:project_slug>/editar/", views.home, {"edit_project": True}, name="proyecto_editar"),
    # Ruta para crear un nuevo reporte dentro del proyecto
    path("proyecto/<slug:project_slug>/reporte/nuevo/", views.home, {"new_report": True}, name="reporte_nuevo"),
    # Ruta para abrir un reporte existente dentro del proyecto
    path("proyecto/<slug:project_slug>/reporte/<int:report_id>/", views.home, name="reporte_detail"),
    # Ruta para abrir el detalle de un frente dentro de un reporte existente
    path("proyecto/<slug:project_slug>/reporte/<int:report_id>/frente/<int:front_id>/", views.home, name="frente_detail"),
]
