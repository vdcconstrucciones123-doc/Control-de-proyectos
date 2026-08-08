from django.conf import settings
from django.db import models
from django.db.models.signals import post_delete, pre_save
from django.dispatch import receiver
from django.utils.text import slugify


class ReportProject(models.Model):
    owner = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="owned_projects")
    company_name = models.CharField(max_length=200, default="VDC CONSTRUCCIONES SAC")
    project_name = models.CharField(max_length=200, blank=True)
    project_location = models.CharField(max_length=200, blank=True)
    slug = models.SlugField(max_length=220, unique=True, blank=True)
    report_title = models.CharField(max_length=200, default="REPORTE FOTOGRÁFICO DE OBRA")
    for_whom = models.CharField(max_length=200, blank=True)
    from_whom = models.CharField(max_length=200, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["project_name", "id"]

    def save(self, *args, **kwargs):
        if not self.slug:
            base_slug = slugify(self.project_name or self.company_name or "proyecto")[:200] or "proyecto"
            slug = base_slug
            suffix = 2
            while ReportProject.objects.exclude(pk=self.pk).filter(slug=slug).exists():
                slug = f"{base_slug}-{suffix}"
                suffix += 1
            self.slug = slug
        super().save(*args, **kwargs)

    def __str__(self):
        return self.project_name or self.company_name


class ProjectMembership(models.Model):
    ROLE_VIEWER = "viewer"
    ROLE_EDITOR = "editor"
    ROLE_ADMIN = "admin"
    ROLE_CHOICES = [
        (ROLE_VIEWER, "Lector"),
        (ROLE_EDITOR, "Editor"),
        (ROLE_ADMIN, "Administrador"),
    ]

    project = models.ForeignKey(ReportProject, on_delete=models.CASCADE, related_name="memberships")
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="project_memberships")
    role = models.CharField(max_length=20, choices=ROLE_CHOICES, default=ROLE_VIEWER)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ("project", "user")
        ordering = ["project_id", "user__username"]

    def __str__(self):
        return f"{self.project} · {self.user} · {self.role}"


class ProjectReport(models.Model):
    TYPE_PROGRESS = "avances"
    TYPE_INCIDENT = "incidencia"
    TYPE_CHOICES = [
        (TYPE_PROGRESS, "Reporte de avances"),
        (TYPE_INCIDENT, "Reporte de incidencia"),
    ]

    project = models.ForeignKey(ReportProject, on_delete=models.CASCADE, related_name="reports")
    report_type = models.CharField(max_length=20, choices=TYPE_CHOICES, default=TYPE_PROGRESS)
    title = models.CharField(max_length=200, default="REPORTE FOTOGRÁFICO DE OBRA")
    week = models.CharField(max_length=50, blank=True)
    report_date = models.DateField(null=True, blank=True)
    labor_date_from = models.DateField(null=True, blank=True)
    labor_date_to = models.DateField(null=True, blank=True)
    for_whom = models.CharField(max_length=200, blank=True)
    from_whom = models.CharField(max_length=200, blank=True)
    objective_text = models.TextField(blank=True)
    analysis_text = models.TextField(blank=True)
    conclusion_text = models.TextField(blank=True)
    recommendation_text = models.TextField(blank=True)
    conclusion_items = models.JSONField(default=list, blank=True)
    recommendation_items = models.JSONField(default=list, blank=True)
    cover_image = models.FileField(upload_to="report_covers/", blank=True, null=True)
    auto_merge_dup = models.BooleanField(default=False)
    combine_by_status = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["id"]

    def __str__(self):
        return self.title or f"Reporte {self.pk}"


class ReportMembership(models.Model):
    report = models.ForeignKey(ProjectReport, on_delete=models.CASCADE, related_name="memberships")
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="report_memberships")
    role = models.CharField(max_length=20, choices=ProjectMembership.ROLE_CHOICES, default=ProjectMembership.ROLE_VIEWER)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ("report", "user")
        ordering = ["report_id", "user__username"]

    def __str__(self):
        return f"{self.report} · {self.user} · {self.role}"


class ReportFront(models.Model):
    report = models.ForeignKey(ProjectReport, on_delete=models.CASCADE, related_name="fronts")
    name = models.CharField(max_length=200)
    sort_order = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ["sort_order", "id"]

    def __str__(self):
        return self.name


class ReportEntry(models.Model):
    report = models.ForeignKey(ProjectReport, on_delete=models.CASCADE, related_name="entries")
    front = models.ForeignKey(ReportFront, on_delete=models.CASCADE, related_name="entries")
    status = models.CharField(max_length=50)
    description = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["id"]

    def __str__(self):
        return f"{self.front} · {self.status}"


class EntryImage(models.Model):
    entry = models.ForeignKey(ReportEntry, on_delete=models.CASCADE, related_name="images")
    image = models.FileField(upload_to="report_entries/")
    sort_order = models.PositiveIntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["sort_order", "id"]


def _delete_file(file_field):
    if file_field and getattr(file_field, "name", None):
        storage = file_field.storage
        name = file_field.name
        if storage.exists(name):
            storage.delete(name)


@receiver(post_delete, sender=ProjectReport)
def delete_report_cover_on_delete(sender, instance, **kwargs):
    _delete_file(instance.cover_image)


@receiver(pre_save, sender=ProjectReport)
def delete_report_cover_on_replace(sender, instance, **kwargs):
    if not instance.pk:
        return
    previous = sender.objects.filter(pk=instance.pk).only("cover_image").first()
    if previous and previous.cover_image and previous.cover_image != instance.cover_image:
        _delete_file(previous.cover_image)


@receiver(post_delete, sender=EntryImage)
def delete_entry_image_on_delete(sender, instance, **kwargs):
    _delete_file(instance.image)


@receiver(pre_save, sender=EntryImage)
def delete_entry_image_on_replace(sender, instance, **kwargs):
    if not instance.pk:
        return
    previous = sender.objects.filter(pk=instance.pk).only("image").first()
    if previous and previous.image and previous.image != instance.image:
        _delete_file(previous.image)
