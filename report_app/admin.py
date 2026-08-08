from django.contrib import admin

from .models import EntryImage, ProjectMembership, ProjectReport, ReportEntry, ReportFront, ReportProject


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