from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as DjangoUserAdmin
from django.contrib.auth.models import User
from django.utils import timezone

from .models import EntryImage, ProjectMembership, ProjectReport, ReportEntry, ReportFront, ReportProject, SiteBranding, UserProfile


class UserProfileInline(admin.StackedInline):
    model = UserProfile
    fk_name = "user"
    can_delete = False
    extra = 0
    readonly_fields = ("approved_at", "approved_by", "created_at")


class UserAdmin(DjangoUserAdmin):
    inlines = [UserProfileInline]
    list_display = ("username", "email", "first_name", "last_name", "is_staff", "approval_status")
    list_filter = DjangoUserAdmin.list_filter + ("profile__is_approved",)

    @admin.display(description="Aprobación")
    def approval_status(self, obj):
        profile = getattr(obj, "profile", None)
        if not profile:
            return "Sin perfil"
        return "Aprobado" if profile.is_approved else "Pendiente"

    actions = ["approve_selected_users"]

    @admin.action(description="Aprobar usuarios seleccionados")
    def approve_selected_users(self, request, queryset):
        for user in queryset:
            profile, _ = UserProfile.objects.get_or_create(user=user)
            profile.is_approved = True
            profile.approved_at = timezone.now()
            profile.approved_by = request.user
            profile.save(update_fields=["is_approved", "approved_at", "approved_by"])


admin.site.unregister(User)
admin.site.register(User, UserAdmin)


@admin.register(UserProfile)
class UserProfileAdmin(admin.ModelAdmin):
    list_display = ("user", "is_approved", "approved_by", "approved_at", "created_at")
    list_filter = ("is_approved",)
    search_fields = ("user__username", "user__email")
    actions = ["approve_profiles"]

    @admin.action(description="Aprobar cuentas seleccionadas")
    def approve_profiles(self, request, queryset):
        queryset.update(is_approved=True, approved_at=timezone.now(), approved_by=request.user)


@admin.register(SiteBranding)
class SiteBrandingAdmin(admin.ModelAdmin):
    list_display = ("site_name", "site_subtitle", "updated_at")
    search_fields = ("site_name", "site_subtitle")
    fields = ("site_name", "site_subtitle", "logo_image")


class ProjectMembershipInline(admin.TabularInline):
    model = ProjectMembership
    extra = 0


class ReportFrontInline(admin.TabularInline):
    model = ReportFront
    extra = 0


class ReportEntryInline(admin.TabularInline):
    model = ReportEntry
    extra = 0


@admin.register(ReportProject)
class ReportProjectAdmin(admin.ModelAdmin):
    list_display = ("project_name", "company_name", "owner", "slug", "updated_at")
    search_fields = ("project_name", "company_name", "slug", "owner__username")
    inlines = [ProjectMembershipInline]


@admin.register(ProjectMembership)
class ProjectMembershipAdmin(admin.ModelAdmin):
    list_display = ("project", "user", "role", "created_at")
    search_fields = ("project__project_name", "user__username")


@admin.register(ProjectReport)
class ProjectReportAdmin(admin.ModelAdmin):
    list_display = ("title", "project", "report_type", "report_date", "updated_at")
    search_fields = ("title", "project__project_name")
    inlines = [ReportFrontInline, ReportEntryInline]


@admin.register(ReportFront)
class ReportFrontAdmin(admin.ModelAdmin):
    list_display = ("name", "report", "sort_order")
    search_fields = ("name", "report__title", "report__project__project_name")


@admin.register(ReportEntry)
class ReportEntryAdmin(admin.ModelAdmin):
    list_display = ("id", "report", "front", "status", "updated_at")
    search_fields = ("description", "report__title", "front__name")


@admin.register(EntryImage)
class EntryImageAdmin(admin.ModelAdmin):
    list_display = ("id", "entry", "sort_order", "created_at")
