from django.urls import path
from . import views

urlpatterns = [
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
