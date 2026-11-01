from django.conf import settings
from django.db import models
from django.db.models.signals import post_delete, pre_save
from django.dispatch import receiver
from django.utils.dateparse import parse_date
from django.utils.text import slugify

if "cloudinary_storage" in settings.INSTALLED_APPS:
    from cloudinary_storage.storage import RawMediaCloudinaryStorage

    project_plan_storage = RawMediaCloudinaryStorage()
else:
    project_plan_storage = None


def _user_folder(user, category):
    username = slugify(getattr(user, "username", "usuario")) or "usuario"
    return f"usuarios/{username}/{category}/"


def project_image_upload_to(instance, filename):
    return _user_folder(instance.owner, "proyectos") + filename


def project_plan_upload_to(instance, filename):
    return _user_folder(instance.project.owner, "planos") + filename


def report_cover_upload_to(instance, filename):
    return _user_folder(instance.project.owner, "portadas") + filename


def entry_image_upload_to(instance, filename):
    return _user_folder(instance.entry.report.project.owner, "evidencias") + filename


def material_signature_upload_to(instance, filename):
    return _user_folder(instance.report.project.owner, "firmas-recepcion") + filename


def material_receipt_logo_upload_to(instance, filename):
    return _user_folder(instance.report.project.owner, "logos-recepcion") + filename


def material_receipt_photo_upload_to(instance, filename):
    return _user_folder(instance.receipt.report.project.owner, "fotos-recepcion") + filename


def site_logo_upload_to(instance, filename):
    return "sitio/logos/" + filename


def profile_image_upload_to(instance, filename):
    return _user_folder(instance.user, "perfil") + filename


def mobility_receipt_upload_to(instance, filename):
    date_value = getattr(instance, "date", None)
    if isinstance(date_value, str):
        date_value = parse_date(date_value)
    if date_value is None:
        return "movilidad/" + filename
    return f"movilidad/{date_value:%Y/%m}/" + filename


class ReportProject(models.Model):
    owner = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="owned_projects")
    company_name = models.CharField(max_length=200, default="VDC CONSTRUCCIONES SAC")
    project_name = models.CharField(max_length=200, blank=True)
    project_location = models.CharField(max_length=200, blank=True)
    project_image = models.FileField(upload_to=project_image_upload_to, blank=True, null=True)
    slug = models.SlugField(max_length=220, unique=True, blank=True)
    report_title = models.CharField(max_length=200, default="REPORTE FOTOGRÁFICO DE OBRA")
    for_whom = models.CharField(max_length=200, blank=True)
    from_whom = models.CharField(max_length=200, blank=True)
    responsible_companies = models.JSONField(default=list, blank=True)
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


class ProjectPlan(models.Model):
    project = models.ForeignKey(ReportProject, on_delete=models.CASCADE, related_name="plans")
    name = models.CharField(max_length=200, blank=True)
    file = models.FileField(upload_to=project_plan_upload_to, storage=project_plan_storage)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at", "-id"]

    def __str__(self):
        return self.name or self.file.name.rsplit("/", 1)[-1]


class ProjectPlanMarker(models.Model):
    plan = models.ForeignKey(ProjectPlan, on_delete=models.CASCADE, related_name="markers")
    page = models.PositiveIntegerField(default=1)
    x = models.FloatField()
    y = models.FloatField()
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["page", "created_at", "id"]


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
    TYPE_EQUIPMENT = "equipos"
    TYPE_MATERIAL_RECEIPT = "materiales"
    TYPE_CHOICES = [
        (TYPE_PROGRESS, "Reporte de avances"),
        (TYPE_INCIDENT, "Reporte de incidencia"),
        (TYPE_EQUIPMENT, "Recepción y entrega de equipos"),
        (TYPE_MATERIAL_RECEIPT, "Recepción de materiales"),
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
    cover_image = models.FileField(upload_to=report_cover_upload_to, blank=True, null=True)
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
    item_name = models.CharField(max_length=200, blank=True)
    building_location = models.CharField(max_length=120, blank=True)
    quantity = models.PositiveIntegerField(default=1)
    unit = models.CharField(max_length=40, blank=True)
    condition = models.CharField(max_length=80, blank=True)
    status = models.CharField(max_length=50)
    incident_date = models.DateField(null=True, blank=True)
    responsible_company = models.CharField(max_length=200, blank=True)
    plan_id = models.PositiveIntegerField(null=True, blank=True)
    plan_x = models.FloatField(null=True, blank=True)
    plan_y = models.FloatField(null=True, blank=True)
    description = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["id"]

    def __str__(self):
        return f"{self.front} · {self.status}"


class MaterialReceipt(models.Model):
    report = models.OneToOneField(ProjectReport, on_delete=models.CASCADE, related_name="material_receipt")
    act_number = models.CharField(max_length=80, blank=True)
    receipt_date = models.DateField(null=True, blank=True)
    supplier = models.CharField(max_length=200, blank=True)
    delivery_note = models.CharField(max_length=120, blank=True)
    delivered_by = models.CharField(max_length=200, blank=True)
    delivered_dni = models.CharField(max_length=30, blank=True)
    delivered_position = models.CharField(max_length=100, blank=True)
    received_by = models.CharField(max_length=200, blank=True)
    received_dni = models.CharField(max_length=30, blank=True)
    received_position = models.CharField(max_length=100, blank=True)
    verified_by = models.CharField(max_length=200, blank=True)
    verified_dni = models.CharField(max_length=30, blank=True)
    verified_position = models.CharField(max_length=100, blank=True)
    conformity = models.CharField(max_length=20, blank=True)
    observations = models.TextField(blank=True)
    signature_delivered = models.FileField(upload_to=material_signature_upload_to, blank=True, null=True)
    signature_received = models.FileField(upload_to=material_signature_upload_to, blank=True, null=True)
    signature_verified = models.FileField(upload_to=material_signature_upload_to, blank=True, null=True)
    delivered_signed_on = models.DateField(null=True, blank=True)
    received_signed_on = models.DateField(null=True, blank=True)
    verified_signed_on = models.DateField(null=True, blank=True)
    company_logo = models.FileField(upload_to=material_receipt_logo_upload_to, blank=True, null=True)
    word_document = models.FileField(upload_to="actas-materiales/word/", blank=True, null=True)
    word_source_hash = models.CharField(max_length=64, blank=True)
    word_document_key = models.CharField(max_length=64, blank=True)
    share_token = models.CharField(max_length=64, unique=True, null=True, blank=True)
    delivered_share_password = models.CharField(max_length=128, blank=True)
    verified_share_password = models.CharField(max_length=128, blank=True)
    received_share_password = models.CharField(max_length=128, blank=True)
    share_access_version = models.PositiveIntegerField(default=1)
    share_password_failed_attempts = models.PositiveSmallIntegerField(default=0)
    share_password_locked_until = models.DateTimeField(null=True, blank=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"Acta de recepción · {self.report}"


class MaterialReceiptPhoto(models.Model):
    receipt = models.ForeignKey(MaterialReceipt, on_delete=models.CASCADE, related_name="photos")
    image = models.FileField(upload_to=material_receipt_photo_upload_to)
    sort_order = models.PositiveIntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["sort_order", "id"]


class EntryImage(models.Model):
    entry = models.ForeignKey(ReportEntry, on_delete=models.CASCADE, related_name="images")
    image = models.FileField(upload_to=entry_image_upload_to)
    sort_order = models.PositiveIntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["sort_order", "id"]


class SiteBranding(models.Model):
    logo_image = models.FileField(upload_to=site_logo_upload_to, blank=True, null=True)
    site_name = models.CharField(max_length=120, default="Site Audit Pro")
    site_subtitle = models.CharField(max_length=200, default="Control visual de obra")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Branding del sitio"
        verbose_name_plural = "Branding del sitio"

    def __str__(self):
        return self.site_name or "Branding del sitio"


class MobilityExpense(models.Model):
    STATUS_PENDING = "pendiente"
    STATUS_PAID = "pagado"
    STATUS_CHOICES = [
        (STATUS_PENDING, "Pendiente"),
        (STATUS_PAID, "Pagado"),
    ]

    date = models.DateField("fecha")
    amount = models.DecimalField("monto", max_digits=10, decimal_places=2)
    paid_amount = models.DecimalField("pagado", max_digits=10, decimal_places=2, default=0)
    transport = models.CharField("movilidad", max_length=80, blank=True)
    origin = models.CharField("origen", max_length=120, blank=True)
    destination = models.CharField("destino", max_length=120, blank=True)
    status = models.CharField("estado", max_length=20, choices=STATUS_CHOICES, default=STATUS_PENDING)
    receipt = models.FileField("evidencia", upload_to=mobility_receipt_upload_to, blank=True, null=True)
    notes = models.CharField("observación", max_length=250, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["date", "id"]

    @property
    def due_amount(self):
        return max(self.amount - self.paid_amount, 0)

    def sync_status_from_payment(self):
        self.paid_amount = max(self.paid_amount, 0)
        if self.paid_amount >= self.amount:
            self.paid_amount = self.amount
            self.status = self.STATUS_PAID
        else:
            self.status = self.STATUS_PENDING
        return self.status

    def __str__(self):
        return f"{self.date} · S/ {self.amount}"


class UserProfile(models.Model):
    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="profile")
    profile_image = models.FileField(upload_to=profile_image_upload_to, blank=True, null=True)
    is_approved = models.BooleanField(default=False)
    approved_at = models.DateTimeField(null=True, blank=True)
    approved_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="approved_profiles",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        status = "aprobado" if self.is_approved else "pendiente"
        return f"{self.user.username} · {status}"


def _delete_file(file_field):
    if file_field and getattr(file_field, "name", None):
        storage = file_field.storage
        name = file_field.name
        try:
            if storage.exists(name):
                storage.delete(name)
        except Exception:
            # File cleanup must not prevent deleting the database record.
            pass


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


@receiver(post_delete, sender=ReportProject)
def delete_project_image_on_delete(sender, instance, **kwargs):
    _delete_file(instance.project_image)


@receiver(pre_save, sender=ReportProject)
def delete_project_image_on_replace(sender, instance, **kwargs):
    if not instance.pk:
        return
    previous = sender.objects.filter(pk=instance.pk).only("project_image").first()
    if previous and previous.project_image and previous.project_image != instance.project_image:
        _delete_file(previous.project_image)


@receiver(post_delete, sender=ProjectPlan)
def delete_project_plan_on_delete(sender, instance, **kwargs):
    _delete_file(instance.file)


@receiver(post_delete, sender=UserProfile)
def delete_profile_image_on_delete(sender, instance, **kwargs):
    _delete_file(instance.profile_image)


@receiver(post_delete, sender=SiteBranding)
def delete_site_branding_logo_on_delete(sender, instance, **kwargs):
    _delete_file(instance.logo_image)


@receiver(pre_save, sender=SiteBranding)
def delete_site_branding_logo_on_replace(sender, instance, **kwargs):
    if not instance.pk:
        return
    previous = sender.objects.filter(pk=instance.pk).only("logo_image").first()
    if previous and previous.logo_image and previous.logo_image != instance.logo_image:
        _delete_file(previous.logo_image)


@receiver(pre_save, sender=UserProfile)
def delete_profile_image_on_replace(sender, instance, **kwargs):
    if not instance.pk:
        return
    previous = sender.objects.filter(pk=instance.pk).only("profile_image").first()
    if previous and previous.profile_image and previous.profile_image != instance.profile_image:
        _delete_file(previous.profile_image)


@receiver(post_delete, sender=EntryImage)
def delete_entry_image_on_delete(sender, instance, **kwargs):
    _delete_file(instance.image)


@receiver(post_delete, sender=MaterialReceiptPhoto)
def delete_material_receipt_photo_on_delete(sender, instance, **kwargs):
    _delete_file(instance.image)


@receiver(post_delete, sender=MobilityExpense)
def delete_mobility_receipt_on_delete(sender, instance, **kwargs):
    _delete_file(instance.receipt)


@receiver(pre_save, sender=EntryImage)
def delete_entry_image_on_replace(sender, instance, **kwargs):
    if not instance.pk:
        return
    previous = sender.objects.filter(pk=instance.pk).only("image").first()
    if previous and previous.image and previous.image != instance.image:
        _delete_file(previous.image)


@receiver(post_delete, sender=MaterialReceipt)
def delete_material_signatures_on_delete(sender, instance, **kwargs):
    _delete_file(instance.signature_delivered)
    _delete_file(instance.signature_received)
    _delete_file(instance.signature_verified)
    _delete_file(instance.company_logo)


@receiver(pre_save, sender=MaterialReceipt)
def delete_material_signatures_on_replace(sender, instance, **kwargs):
    if not instance.pk:
        return
    previous = sender.objects.filter(pk=instance.pk).first()
    if not previous:
        return
    for field_name in ("signature_delivered", "signature_received", "signature_verified", "company_logo"):
        old_file = getattr(previous, field_name)
        if old_file and old_file != getattr(instance, field_name):
            _delete_file(old_file)
