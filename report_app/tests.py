import os
import tempfile

from django.core.management import call_command
from django.test import TestCase
from django.urls import reverse
from django.contrib.auth.models import User
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import override_settings

from report_app.models import EntryImage, ProjectMembership, ProjectReport, ReportEntry, ReportFront, ReportProject


class HomeViewTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="aldo", password="ClaveSegura123")
        self.client.force_login(self.user)

    def test_panel_principal_renders_the_dashboard(self):
        response = self.client.get(reverse("panel_principal"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Site Audit Pro Lite")
        self.assertContains(response, "Crea tu proyecto")
        self.assertContains(response, "Exportar PDF")

    def test_new_project_route_enables_project_form_mode(self):
        response = self.client.get(reverse("proyecto_nuevo"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'window.INIT_NEW_PROJECT = true;')

    def test_project_detail_injects_the_project_slug(self):
        response = self.client.get(reverse("proyecto_detail", args=["proyecto-demo"]))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'window.INIT_PROJECT_SLUG = "proyecto-demo";')
        self.assertContains(response, "Crear reporte")

    def test_edit_project_route_enables_edit_mode(self):
        response = self.client.get(reverse("proyecto_editar", args=["proyecto-demo"]))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'window.INIT_PROJECT_SLUG = "proyecto-demo";')
        self.assertContains(response, 'window.INIT_EDIT_PROJECT = true;')

    def test_new_report_route_renders_project_report_page(self):
        response = self.client.get(reverse("reporte_nuevo", args=["proyecto-demo"]))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'window.INIT_PROJECT_SLUG = "proyecto-demo";')
        self.assertContains(response, 'window.INIT_NEW_REPORT = true;')

    def test_existing_report_route_injects_report_id(self):
        response = self.client.get(reverse("reporte_detail", args=["proyecto-demo", 123]))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'window.INIT_REPORT_ID = "123";')
        self.assertContains(response, 'window.INIT_NEW_REPORT = false;')

    def test_front_detail_route_renders_the_report_page(self):
        response = self.client.get(reverse("frente_detail", args=["proyecto-demo", 123, 456]))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'window.INIT_REPORT_ID = "123";')


class AuthViewTests(TestCase):
    def test_root_redirects_anonymous_user_to_login(self):
        response = self.client.get(reverse("root"))

        self.assertEqual(response.status_code, 302)
        self.assertRedirects(response, reverse("login"))

    def test_login_page_renders(self):
        response = self.client.get(reverse("login"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Iniciar sesión")

    def test_register_creates_user_and_redirects(self):
        response = self.client.post(reverse("register"), {
            "username": "cliente1",
            "first_name": "Cliente",
            "last_name": "Uno",
            "email": "cliente1@example.com",
            "password1": "ClaveSegura123!",
            "password2": "ClaveSegura123!",
        })

        self.assertRedirects(response, reverse("panel_principal"))
        self.assertTrue(User.objects.filter(username="cliente1").exists())


class AdminBootstrapCommandTests(TestCase):
    def test_command_creates_or_updates_admin_from_env(self):
        env = {
            "DJANGO_SUPERUSER_USERNAME": "renderadmin",
            "DJANGO_SUPERUSER_EMAIL": "renderadmin@example.com",
            "DJANGO_SUPERUSER_PASSWORD": "ClaveSegura123!",
        }
        original = {key: os.environ.get(key) for key in env}
        try:
            os.environ.update(env)
            call_command("ensure_admin_user")

            user = User.objects.get(username="renderadmin")
            self.assertEqual(user.email, "renderadmin@example.com")
            self.assertTrue(user.is_staff)
            self.assertTrue(user.is_superuser)
            self.assertTrue(user.check_password("ClaveSegura123!"))
        finally:
            for key, value in original.items():
                if value is None:
                    os.environ.pop(key, None)
                else:
                    os.environ[key] = value


class ProjectApiTests(TestCase):
    def setUp(self):
        self.owner = User.objects.create_user(username="owner", password="ClaveSegura123")
        self.editor = User.objects.create_user(username="editor", password="ClaveSegura123")
        self.viewer = User.objects.create_user(username="viewer", password="ClaveSegura123")
        self.client.force_login(self.owner)

    def test_owner_can_create_project(self):
        response = self.client.post(
            reverse("project_collection_api"),
            data='{"companyName":"VDC","projectName":"Proyecto Centro","projectLocation":"Lima"}',
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 201)
        payload = response.json()["project"]
        self.assertEqual(payload["projectName"], "Proyecto Centro")
        self.assertTrue(ReportProject.objects.filter(project_name="Proyecto Centro", owner=self.owner).exists())

    def test_owner_can_share_project_with_editor(self):
        project = ReportProject.objects.create(owner=self.owner, company_name="VDC", project_name="Proyecto Norte")

        response = self.client.post(
            reverse("project_members_api", args=[project.slug]),
            data='{"username":"editor","role":"editor"}',
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 200)
        membership = ProjectMembership.objects.get(project=project, user=self.editor)
        self.assertEqual(membership.role, ProjectMembership.ROLE_EDITOR)

    def test_shared_user_sees_project_in_collection(self):
        project = ReportProject.objects.create(owner=self.owner, company_name="VDC", project_name="Proyecto Compartido")
        ProjectMembership.objects.create(project=project, user=self.viewer, role=ProjectMembership.ROLE_VIEWER)
        self.client.force_login(self.viewer)

        response = self.client.get(reverse("project_collection_api"))

        self.assertEqual(response.status_code, 200)
        payload = response.json()["projects"]
        self.assertEqual(len(payload), 1)
        self.assertEqual(payload[0]["slug"], project.slug)
        self.assertFalse(payload[0]["canShare"])

    def test_editor_can_update_project_but_not_share(self):
        project = ReportProject.objects.create(owner=self.owner, company_name="VDC", project_name="Proyecto Edit")
        ProjectMembership.objects.create(project=project, user=self.editor, role=ProjectMembership.ROLE_EDITOR)
        self.client.force_login(self.editor)

        patch_response = self.client.patch(
            reverse("project_detail_api", args=[project.slug]),
            data='{"companyName":"VDC","projectName":"Proyecto Editado","projectLocation":"Cusco"}',
            content_type="application/json",
        )
        share_response = self.client.post(
            reverse("project_members_api", args=[project.slug]),
            data='{"username":"viewer","role":"viewer"}',
            content_type="application/json",
        )

        self.assertEqual(patch_response.status_code, 200)
        project.refresh_from_db()
        self.assertEqual(project.project_name, "Proyecto Editado")
        self.assertEqual(share_response.status_code, 403)


@override_settings(MEDIA_ROOT=tempfile.mkdtemp())
class ReportStorageLifecycleTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="storage", password="ClaveSegura123")
        self.client.force_login(self.user)
        self.project = ReportProject.objects.create(owner=self.user, company_name="VDC", project_name="Proyecto Storage")

    def test_cover_replacement_deletes_previous_file(self):
        report = ProjectReport.objects.create(
            project=self.project,
            title="Reporte",
            cover_image=SimpleUploadedFile("cover1.jpg", b"first-image", content_type="image/jpeg"),
        )
        old_path = report.cover_image.path

        response = self.client.post(
            reverse("project_report_update_api", args=[self.project.slug, report.id]),
            data={
                "reportType": "avances",
                "reportTitle": "Reporte",
                "reportWeek": "1",
                "coverPhoto": SimpleUploadedFile("cover2.jpg", b"second-image", content_type="image/jpeg"),
            },
        )

        self.assertEqual(response.status_code, 200)
        report.refresh_from_db()
        self.assertFalse(os.path.exists(old_path))
        self.assertTrue(report.cover_image.name.endswith("cover2.jpg"))

    def test_entry_delete_removes_image_file(self):
        report = ProjectReport.objects.create(project=self.project, title="Reporte")
        front = ReportFront.objects.create(report=report, name="Frente 1")
        entry = ReportEntry.objects.create(report=report, front=front, status="Pendiente", description="Desc")
        image = EntryImage.objects.create(
            entry=entry,
            image=SimpleUploadedFile("issue.jpg", b"issue-image", content_type="image/jpeg"),
        )
        image_path = image.image.path

        response = self.client.delete(
            reverse("report_entry_detail_api", args=[self.project.slug, report.id, entry.id])
        )

        self.assertEqual(response.status_code, 200)
        self.assertFalse(os.path.exists(image_path))
        self.assertFalse(EntryImage.objects.filter(pk=image.pk).exists())
