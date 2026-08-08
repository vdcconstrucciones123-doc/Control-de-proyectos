from django import forms
import datetime

class ProjectForm(forms.Form):
    company_name = forms.CharField(
        label="Nombre de la empresa",
        initial="VDC CONSTRUCCIONES SAC",
        widget=forms.TextInput(attrs={
            "class": "form-control",
            "id": "companyName",
            "placeholder": "Ej: VDC CONSTRUCCIONES SAC",
        }),
    )
    project_name = forms.CharField(
        label="Nombre del Proyecto",
        required=True,
        widget=forms.TextInput(attrs={
            "class": "form-control",
            "id": "projectName",
            "placeholder": "Ej: UNIFAMILIAR",
        }),
    )
    project_location = forms.CharField(
        label="Ubicación",
        required=False,
        widget=forms.TextInput(attrs={
            "class": "form-control",
            "id": "projectLocation",
            "placeholder": "Ej: Urb. Los Olivos, Lima",
        }),
    )


class ReportMetaForm(forms.Form):
    project_name = forms.CharField(
        label="Proyecto",
        required=False,
        widget=forms.TextInput(attrs={
            "class": "form-control",
            "id": "metadataProjectName",
            "readonly": "readonly",
        }),
    )
    report_type = forms.ChoiceField(
        label="Tipo de reporte",
        choices=[
            ("", "Selecciona un tipo"),
            ("avances", "Reporte de avances"),
            ("incidencia", "Reporte de incidencia"),
        ],
        widget=forms.Select(attrs={
            "class": "form-select",
            "id": "metadataReportType",
            "disabled": "disabled",
        }),
        required=False,
    )
    report_title = forms.CharField(
        label="Título del reporte",
        initial="REPORTE FOTOGRÁFICO DE OBRA",
        widget=forms.TextInput(attrs={
            "class": "form-control",
            "id": "reportTitle",
            "placeholder": "Ej: REPORTE FOTOGRÁFICO DE OBRA",
        }),
    )
    report_week = forms.CharField(
        label="Semana",
        required=False,
        widget=forms.TextInput(attrs={
            "class": "form-control",
            "id": "reportWeek",
            "placeholder": "Ej: 8",
        }),
    )
    report_date = forms.DateField(
        label="Fecha del reporte",
        required=False,
        widget=forms.DateInput(attrs={
            "class": "form-control",
            "id": "reportDate",
            "type": "date",
        }),
    )
    cover_photo = forms.FileField(
        label="Foto de portada (opcional)",
        required=False,
        widget=forms.ClearableFileInput(attrs={
            "class": "form-control",
            "id": "coverPhotoInput",
            "accept": "image/*",
        }),
    )
    objective_text = forms.CharField(
        label="1. Objetivo",
        required=False,
        widget=forms.Textarea(attrs={
            "class": "form-control",
            "id": "objectiveText",
            "rows": 2,
            "placeholder": "Describa el objetivo del reporte",
        }),
    )
    analysis_text = forms.CharField(
        label="2. Análisis: avances de la semana",
        required=False,
        widget=forms.Textarea(attrs={
            "class": "form-control",
            "id": "analysisText",
            "rows": 4,
            "placeholder": "Describa los avances, actividades y observaciones de la semana",
        }),
    )
    labor_date_from = forms.DateField(
        label="Del",
        required=False,
        widget=forms.DateInput(attrs={
            "class": "form-control",
            "id": "laborDateFrom",
            "type": "date",
        }),
    )
    labor_date_to = forms.DateField(
        label="Al",
        required=False,
        widget=forms.DateInput(attrs={
            "class": "form-control",
            "id": "laborDateTo",
            "type": "date",
        }),
    )
    for_whom = forms.CharField(
        label="Solicitado por",
        required=False,
        widget=forms.TextInput(attrs={
            "class": "form-control",
            "id": "forWhom",
            "placeholder": "Ej: Arquitecta Estela",
        }),
    )
    from_whom = forms.CharField(
        label="Responsable",
        required=False,
        widget=forms.TextInput(attrs={
            "class": "form-control",
            "id": "fromWhom",
            "placeholder": "Ej: Ing. Aldo / Arquitecta Estela",
        }),
    )


class ReportTypeForm(forms.Form):
    report_type = forms.ChoiceField(
        label="Tipo de reporte",
        choices=[
            ("", "Selecciona un tipo"),
            ("avances", "Reporte de avances"),
            ("incidencia", "Reporte de incidencia"),
        ],
        widget=forms.Select(attrs={
            "class": "form-select",
            "id": "selectReportType",
        }),
        required=True,
    )
