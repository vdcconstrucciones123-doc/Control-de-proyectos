import os
import tempfile
from decimal import Decimal

from django.core.management import call_command
from django.test import TestCase
from django.urls import reverse
from django.contrib.auth.models import User
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import override_settings

from report_app.models import EntryImage, MobilityExpense, ProjectMembership, ProjectReport, ReportEntry, ReportFront, ReportMembership, ReportProject, UserProfile


class HomeViewTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="aldo", password="ClaveSegura123")
        self.client.force_login(self.user)

    def test_panel_principal_renders_the_dashboard(self):
        response = self.client.get(reverse("panel_principal"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Site Audit Pro Lite")
        self.assertContains(response, "Proyectos")
        self.assertContains(response, "Nuevo proyecto")

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

        self.assertRedirects(response, reverse("registration_pending"))
        self.assertTrue(User.objects.filter(username="cliente1").exists())

    def test_pending_user_cannot_login_until_approved(self):
        User.objects.create_user(username="pendiente", password="ClaveSegura123")

        response = self.client.post(reverse("login"), {
            "username": "pendiente",
            "password": "ClaveSegura123",
        })

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "pendiente de aprobación")


class MobilityViewTests(TestCase):
    def test_public_mobility_pages_do_not_require_login(self):
        self.assertEqual(self.client.get(reverse("mobility_entry")).status_code, 200)
        self.assertEqual(self.client.get(reverse("mobility_preview")).status_code, 200)

    def test_public_mobility_entry_is_saved_with_receipt(self):
        receipt = SimpleUploadedFile("yape.png", b"fake-image", content_type="image/png")

        response = self.client.post(reverse("mobility_entry"), {
            "date": "2026-08-10",
            "amount": "12.80",
            "status": "pendiente",
            "receipt": receipt,
        })

        self.assertRedirects(response, reverse("mobility_entry"))
        expense = MobilityExpense.objects.get()
        self.assertEqual(expense.amount, Decimal("12.80"))
        self.assertEqual(expense.transport, "")
        self.assertEqual(expense.origin, "")
        self.assertEqual(expense.destination, "")
        self.assertTrue(expense.receipt.name)

    def test_public_form_has_no_mobility_origin_destination_fields(self):
        response = self.client.get(reverse("mobility_entry"))

        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, "Movilidad")
        self.assertNotContains(response, "Origen")
        self.assertNotContains(response, "Destino")

    def test_preview_is_compact_and_has_no_entry_link(self):
        response = self.client.get(reverse("mobility_preview"))

        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, "Ingresar movilidad")
        self.assertContains(response, "Control de movilidad")

    def test_preview_shows_paid_pending_and_total(self):
        MobilityExpense.objects.create(date="2026-08-10", amount="12.80", status=MobilityExpense.STATUS_PAID, paid_amount="12.80")
        MobilityExpense.objects.create(date="2026-08-11", amount="8.20", status=MobilityExpense.STATUS_PENDING, paid_amount="0.00")

        response = self.client.get(reverse("mobility_preview"))

        self.assertContains(response, "S/ 21.00")
        self.assertContains(response, "S/ 12.80")
        self.assertContains(response, "S/ 8.20")

    def test_partial_payment_is_applied_to_oldest_pending_expenses(self):
        first = MobilityExpense.objects.create(date="2026-08-10", amount="12.80", status=MobilityExpense.STATUS_PENDING, paid_amount="0.00")
        second = MobilityExpense.objects.create(date="2026-08-11", amount="12.90", status=MobilityExpense.STATUS_PENDING, paid_amount="0.00")
        third = MobilityExpense.objects.create(date="2026-08-12", amount="8.30", status=MobilityExpense.STATUS_PENDING, paid_amount="0.00")

        response = self.client.post(reverse("mobility_entry"), {
            "payment_amount": "25.00",
        })

        self.assertRedirects(response, reverse("mobility_entry"))
        first.refresh_from_db()
        second.refresh_from_db()
        third.refresh_from_db()
        self.assertEqual(first.paid_amount, Decimal("12.80"))
        self.assertEqual(first.status, MobilityExpense.STATUS_PAID)
        self.assertEqual(second.paid_amount, Decimal("12.20"))
        self.assertEqual(second.status, MobilityExpense.STATUS_PENDING)
        self.assertEqual(third.paid_amount, Decimal("0.00"))
        self.assertEqual(third.status, MobilityExpense.STATUS_PENDING)

    def test_preview_uses_pending_balance_for_due_amounts(self):
        MobilityExpense.objects.create(date="2026-08-10", amount="12.80", status=MobilityExpense.STATUS_PAID, paid_amount="12.80")
        MobilityExpense.objects.create(date="2026-08-11", amount="8.20", status=MobilityExpense.STATUS_PENDING, paid_amount="2.00")

        response = self.client.get(reverse("mobility_preview"))

        self.assertContains(response, "S/ 21.00")
        self.assertContains(response, "S/ 12.80")
        self.assertContains(response, "S/ 6.20")

    def test_preview_includes_receipt_link_for_verification(self):
        receipt = SimpleUploadedFile("yape.png", b"fake-image", content_type="image/png")
        expense = MobilityExpense.objects.create(
            date="2026-08-10",
            amount="12.80",
            status=MobilityExpense.STATUS_PENDING,
            receipt=receipt,
        )

        response = self.client.get(reverse("mobility_preview"))

        self.assertContains(response, "Evidencia")
        self.assertContains(response, reverse("mobility_receipt", args=[expense.id]))

    def test_dates_show_weekday_abbreviation(self):
        MobilityExpense.objects.create(
            date="2026-08-10",
            amount="12.80",
            status=MobilityExpense.STATUS_PENDING,
        )

        entry_response = self.client.get(reverse("mobility_entry"))
        preview_response = self.client.get(reverse("mobility_preview"))

        self.assertContains(entry_response, "(lun)")
        self.assertContains(preview_response, "(lun)")

    def test_existing_mobility_can_be_deleted_from_entry_list(self):
        expense = MobilityExpense.objects.create(
            date="2026-08-10",
            amount="12.80",
            status=MobilityExpense.STATUS_PENDING,
        )

        response = self.client.post(reverse("mobility_entry"), {
            "expense_id": expense.id,
            "action": "delete",
        })

        self.assertRedirects(response, reverse("mobility_entry"))
        self.assertFalse(MobilityExpense.objects.filter(pk=expense.id).exists())

    def test_editing_existing_mobility_updates_the_same_record(self):
        receipt = SimpleUploadedFile("older.png", b"old-bytes", content_type="image/png")
        expense = MobilityExpense.objects.create(
            date="2026-08-10",
            amount="12.80",
            status=MobilityExpense.STATUS_PENDING,
            notes="Antes",
            receipt=receipt,
        )

        response = self.client.post(reverse("mobility_entry"), {
            "expense_id": expense.id,
            "date": "2026-08-12",
            "amount": "45.50",
            "status": MobilityExpense.STATUS_PAID,
            "notes": "Actualizado",
        })

        self.assertRedirects(response, reverse("mobility_entry"))
        self.assertEqual(MobilityExpense.objects.count(), 1)
        expense.refresh_from_db()
        self.assertEqual(expense.amount, Decimal("45.50"))
        self.assertEqual(expense.status, MobilityExpense.STATUS_PAID)
        self.assertEqual(expense.notes, "Actualizado")
        self.assertTrue(expense.receipt.name)

    def test_edit_form_displays_saved_amount(self):
        expense = MobilityExpense.objects.create(
            date="2026-08-10",
            amount="12.80",
            status=MobilityExpense.STATUS_PENDING,
        )

        response = self.client.get(reverse("mobility_entry") + f"?edit={expense.id}")

        self.assertContains(response, 'id="amount"')
        self.assertContains(response, 'value="12.80"')

    def test_cancel_button_only_appears_while_editing(self):
        expense = MobilityExpense.objects.create(
            date="2026-08-10",
            amount="12.80",
            status=MobilityExpense.STATUS_PENDING,
        )

        edit_response = self.client.get(reverse("mobility_entry") + f"?edit={expense.id}")
        new_response = self.client.get(reverse("mobility_entry"))

        self.assertContains(edit_response, "Cancelar")
        self.assertNotContains(new_response, "Cancelar")

    def test_receipt_view_has_return_link(self):
        receipt = SimpleUploadedFile("yape.png", b"fake-image", content_type="image/png")
        expense = MobilityExpense.objects.create(
            date="2026-08-10",
            amount="12.80",
            status=MobilityExpense.STATUS_PENDING,
            receipt=receipt,
        )

        response = self.client.get(reverse("mobility_receipt", args=[expense.id]))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Regresar")
        self.assertContains(response, expense.receipt.url)

    def test_receipt_view_returns_to_preview_when_opened_from_preview(self):
        receipt = SimpleUploadedFile("yape.png", b"fake-image", content_type="image/png")
        expense = MobilityExpense.objects.create(
            date="2026-08-10",
            amount="12.80",
            status=MobilityExpense.STATUS_PENDING,
            receipt=receipt,
        )

        response = self.client.get(reverse("mobility_receipt", args=[expense.id]) + "?from=preview")

        self.assertContains(response, f'href="{reverse("mobility_preview")}"')


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
        UserProfile.objects.filter(user__in=[self.owner, self.editor, self.viewer]).update(is_approved=True)
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
        self.assertEqual(payload[0]["sharedByUsername"], self.owner.username)
        self.assertEqual({member["username"] for member in payload[0]["members"]}, {"owner", "viewer"})

    def test_owner_sees_all_project_recipients(self):
        project = ReportProject.objects.create(owner=self.owner, company_name="VDC", project_name="Proyecto Destinatarios")
        ProjectMembership.objects.create(project=project, user=self.viewer, role=ProjectMembership.ROLE_VIEWER)

        response = self.client.get(reverse("project_collection_api"))

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            {member["username"] for member in response.json()["projects"][0]["members"]},
            {"owner", "viewer"},
        )

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

    def test_owner_can_share_single_report(self):
        project = ReportProject.objects.create(owner=self.owner, company_name="VDC", project_name="Proyecto Reporte")
        report = ProjectReport.objects.create(project=project, title="Reporte 1")

        response = self.client.post(
            reverse("report_members_api", args=[project.slug, report.id]),
            data='{"username":"viewer","role":"viewer"}',
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 200)
        membership = ReportMembership.objects.get(report=report, user=self.viewer)
        self.assertEqual(membership.role, ProjectMembership.ROLE_VIEWER)

    def test_report_shared_user_sees_only_shared_report(self):
        project = ReportProject.objects.create(owner=self.owner, company_name="VDC", project_name="Proyecto Filtrado")
        visible_report = ProjectReport.objects.create(project=project, title="Reporte Visible")
        ProjectReport.objects.create(project=project, title="Reporte Oculto")
        ReportMembership.objects.create(report=visible_report, user=self.viewer, role=ProjectMembership.ROLE_VIEWER)
        self.client.force_login(self.viewer)

        response = self.client.get(reverse("project_collection_api"))

        self.assertEqual(response.status_code, 200)
        payload = response.json()["projects"]
        self.assertEqual(len(payload), 1)
        self.assertEqual(len(payload[0]["reports"]), 1)
        self.assertEqual(payload[0]["reports"][0]["title"], "Reporte Visible")

    def test_viewer_cannot_edit_shared_project_or_report(self):
        project = ReportProject.objects.create(owner=self.owner, company_name="VDC", project_name="Proyecto Solo Lectura")
        report = ProjectReport.objects.create(project=project, title="Reporte Lectura")
        front = ReportFront.objects.create(report=report, name="Frente 1")
        ProjectMembership.objects.create(project=project, user=self.viewer, role=ProjectMembership.ROLE_VIEWER)
        self.client.force_login(self.viewer)

        update_project_response = self.client.patch(
            reverse("project_detail_api", args=[project.slug]),
            data='{"companyName":"VDC","projectName":"No permitido","projectLocation":"Lima"}',
            content_type="application/json",
        )
        update_report_response = self.client.post(
            reverse("project_report_update_api", args=[project.slug, report.id]),
            data={
                "reportType": "avances",
                "reportTitle": "No permitido",
            },
        )
        create_entry_response = self.client.post(
            reverse("report_entries_api", args=[project.slug, report.id]),
            data={
                "frontId": str(front.id),
                "status": "Pendiente",
                "desc": "Intento de edición",
            },
        )

        self.assertEqual(update_project_response.status_code, 403)
        self.assertEqual(update_report_response.status_code, 403)
        self.assertEqual(create_entry_response.status_code, 403)


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
