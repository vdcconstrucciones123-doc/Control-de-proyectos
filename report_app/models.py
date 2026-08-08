from django.db import models


class ReportProject(models.Model):
    company_name = models.CharField(max_length=200, default="VDC CONSTRUCCIONES SAC")
    project_name = models.CharField(max_length=200, blank=True)
    project_location = models.CharField(max_length=200, blank=True)
    report_title = models.CharField(max_length=200, default="REPORTE FOTOGRÁFICO DE OBRA")
    for_whom = models.CharField(max_length=200, blank=True)
    from_whom = models.CharField(max_length=200, blank=True)

    def __str__(self):
        return self.project_name or self.company_name
