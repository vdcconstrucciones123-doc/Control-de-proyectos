import os
import json
import tempfile
from io import BytesIO
from decimal import Decimal
from urllib.parse import urlsplit

from django.core.management import call_command
from django.test import Client, TestCase
from django.urls import reverse
from django.contrib.auth.models import User
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import override_settings
from django.utils import timezone
from PIL import Image

from report_app.models import EntryImage, MaterialReceipt, MaterialReceiptPhoto, MobilityExpense, ProjectMembership, ProjectReport, PublicReportShare, ReportEntry, ReportFront, ReportMembership, ReportProject, UserProfile


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


@override_settings(MEDIA_ROOT=tempfile.mkdtemp())
class MaterialReceiptViewTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="materiales", password="test-password-123")
        UserProfile.objects.update_or_create(user=self.user, defaults={"is_approved": True})
        self.client.force_login(self.user)
        self.project = ReportProject.objects.create(owner=self.user, project_name="Obra de prueba")

    def test_word_editor_requires_edit_permission(self):
        report = ProjectReport.objects.create(
            project=self.project,
            report_type=ProjectReport.TYPE_MATERIAL_RECEIPT,
            title="Acta de recepción",
        )
        viewer = User.objects.create_user(username="lector", password="ClaveSegura123")
        UserProfile.objects.update_or_create(user=viewer, defaults={"is_approved": True})
        ProjectMembership.objects.create(
            project=self.project,
            user=viewer,
            role=ProjectMembership.ROLE_VIEWER,
        )
        self.client.force_login(viewer)

        response = self.client.get(
            reverse("material_receipt_word_editor", args=[self.project.slug, report.id])
        )

        self.assertEqual(response.status_code, 403)

    @override_settings(ONLYOFFICE_DOCUMENT_SERVER_URL="", ONLYOFFICE_JWT_SECRET="")
    def test_word_editor_explains_when_document_server_is_not_configured(self):
        report = ProjectReport.objects.create(
            project=self.project,
            report_type=ProjectReport.TYPE_MATERIAL_RECEIPT,
            title="Acta de recepción",
        )

        response = self.client.get(
            reverse("material_receipt_word_editor", args=[self.project.slug, report.id])
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Falta conectar el servidor de documentos")
        self.assertContains(response, "ONLYOFFICE_DOCUMENT_SERVER_URL")

    @override_settings(
        ONLYOFFICE_DOCUMENT_SERVER_URL="https://docs.example.com",
        ONLYOFFICE_JWT_SECRET="test-onlyoffice-secret-with-at-least-32-bytes",
    )
    def test_word_editor_generates_and_serves_a_signed_docx(self):
        report = ProjectReport.objects.create(
            project=self.project,
            report_type=ProjectReport.TYPE_MATERIAL_RECEIPT,
            title="Acta de recepción",
        )
        receipt = MaterialReceipt.objects.create(
            report=report,
            act_number="AR-001",
            supplier="Proveedor de prueba",
        )
        front = ReportFront.objects.create(report=report, name="Materiales")
        ReportEntry.objects.create(
            report=report,
            front=front,
            item_name="Cemento",
            unit="bolsa",
            quantity=4,
            status="Conforme",
            description="Entrega completa",
        )

        response = self.client.get(
            reverse("material_receipt_word_editor", args=[self.project.slug, report.id])
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "DocsAPI.DocEditor")
        receipt.refresh_from_db()
        self.assertTrue(receipt.word_document)
        from django.core import signing

        download_token = signing.dumps(
            {"receipt_id": receipt.pk},
            salt="material-receipt-word-download",
            compress=True,
        )
        download = self.client.get(
            reverse("material_receipt_word_download"),
            {"token": download_token},
        )
        self.assertEqual(download.status_code, 200)
        self.assertEqual(
            download["Content-Type"],
            "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        )
        from docx import Document

        document = Document(BytesIO(download.content))
        document_text = "\n".join(
            paragraph.text for paragraph in document.paragraphs
        ) + "\n" + "\n".join(
            cell.text for table in document.tables for row in table.rows for cell in row.cells
        )
        self.assertIn("AR-001", document_text)
        self.assertIn("Proveedor de prueba", document_text)
        self.assertIn("Cemento", document_text)

    @override_settings(
        ONLYOFFICE_DOCUMENT_SERVER_URL="https://docs.example.com",
        ONLYOFFICE_JWT_SECRET="test-onlyoffice-secret-with-at-least-32-bytes",
    )
    def test_word_editor_callback_saves_only_valid_jwt_docx(self):
        import jwt
        from django.core import signing
        from unittest.mock import Mock, patch
        from urllib.parse import urlencode
        from report_app.word_editor import build_material_receipt_docx

        report = ProjectReport.objects.create(
            project=self.project,
            report_type=ProjectReport.TYPE_MATERIAL_RECEIPT,
            title="Acta de recepción",
        )
        receipt = MaterialReceipt.objects.create(
            report=report,
            word_document_key="test-document-key",
        )
        original_docx = build_material_receipt_docx(receipt)
        receipt.word_document.save(
            "acta-inicial.docx",
            SimpleUploadedFile(
                "acta-inicial.docx",
                original_docx,
                content_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            ),
        )
        callback_token = signing.dumps(
            {"receipt_id": receipt.pk, "document_key": receipt.word_document_key},
            salt="material-receipt-word-callback",
            compress=True,
        )
        callback_url = (
            reverse("material_receipt_word_callback")
            + "?"
            + urlencode({"token": callback_token})
        )
        callback_jwt = jwt.encode(
            {"key": receipt.word_document_key},
            "test-onlyoffice-secret-with-at-least-32-bytes",
            algorithm="HS256",
        )
        download_response = Mock()
        download_response.iter_content.return_value = [original_docx]

        with patch("report_app.views.requests.get", return_value=download_response) as download:
            response = self.client.post(
                callback_url,
                data=json.dumps({
                    "key": receipt.word_document_key,
                    "status": 2,
                    "url": "https://docs.example.com/download/document",
                }),
                content_type="application/json",
                HTTP_AUTHORIZATION=f"Bearer {callback_jwt}",
            )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"error": 0})
        download.assert_called_once()
        receipt.refresh_from_db()
        with receipt.word_document.open("rb") as saved_document:
            self.assertEqual(saved_document.read(), original_docx)

    @override_settings(
        ONLYOFFICE_DOCUMENT_SERVER_URL="https://docs.example.com",
        ONLYOFFICE_JWT_SECRET="test-onlyoffice-secret-with-at-least-32-bytes",
    )
    def test_word_editor_callback_rejects_missing_jwt(self):
        response = self.client.post(
            reverse("material_receipt_word_callback"),
            data=json.dumps({"key": "document", "status": 2}),
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 403)

    def test_receipt_type_shows_editable_form_and_signature_tools(self):
        response = self.client.get(reverse("reporte_nuevo", args=[self.project.slug]))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'data-report-type="materiales"')
        self.assertContains(response, 'id="receiptActNumber"')
        self.assertContains(response, 'id="receiptCompanyLogoFile"')
        self.assertContains(response, 'id="materialEntryFields" class="row g-2 d-none"')
        self.assertContains(response, 'class="mb-2 js-equipment-only"')
        self.assertNotContains(response, 'id="receiptSignatureReceived"')
        self.assertNotContains(response, 'id="receiptDeliveredDni"')
        self.assertNotContains(response, 'id="receiptSupplier"')
        self.assertNotContains(response, 'id="receiptDeliveryNote"')
        self.assertNotContains(response, 'id="receiptConformity"')
        self.assertNotContains(response, 'id="receiptObservations"')
        self.assertContains(response, "datos y firmas de cada responsable se completan directamente en la vista previa")
        self.assertContains(response, 'id="saveMaterialReceiptPreviewBtn"')
        self.assertContains(response, "Guardar datos del acta")
        self.assertContains(response, 'id="materialReceiptPhotoFiles"')
        self.assertNotContains(response, "4 por página al final del PDF exportado")
        self.assertContains(response, 'id="materialReceiptSignatureDialog"')
        self.assertContains(response, "Insertar firma")
        self.assertContains(response, "Descargar PDF rellenable")
        self.assertContains(response, '<option value="real" selected>PDF optimizado con texto seleccionable</option>')

    def test_existing_receipt_report_keeps_fillable_pdf_download(self):
        report = ProjectReport.objects.create(
            project=self.project,
            report_type=ProjectReport.TYPE_MATERIAL_RECEIPT,
            title="Acta de recepción",
        )

        response = self.client.get(
            reverse("reporte_detail", args=[self.project.slug, report.id])
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Descargar PDF rellenable")
        self.assertContains(
            response,
            reverse("material_receipt_report_fillable_pdf", args=[self.project.slug, report.id]),
        )
        self.assertNotContains(response, "Descargar Word editable")

    def test_pdf_linearization_preserves_text_and_enables_fast_web_view(self):
        from pikepdf import Pdf
        from reportlab.pdfgen import canvas
        from report_app.views import _linearize_pdf

        source = BytesIO()
        document = canvas.Canvas(source)
        document.drawString(40, 800, "Texto seleccionable de prueba")
        document.showPage()
        document.save()

        optimized = _linearize_pdf(source.getvalue())
        with Pdf.open(BytesIO(optimized)) as pdf:
            self.assertTrue(pdf.is_linearized)
            self.assertEqual(len(pdf.pages), 1)
            self.assertIn(b"Texto seleccionable de prueba", bytes(pdf.pages[0].Contents.read_bytes()))

    def test_real_pdf_export_is_linearized_and_keeps_text_selectable(self):
        from pikepdf import Pdf

        report = ProjectReport.objects.create(
            project=self.project,
            report_type=ProjectReport.TYPE_MATERIAL_RECEIPT,
            title="Acta de prueba",
        )
        response = self.client.post(
            reverse("project_report_export_pdf_real_api", args=[self.project.slug, report.id]),
            data=json.dumps({
                "html": '<div class="report-page report-secondary-page"><h1>Acta de prueba</h1><p>Texto seleccionable en Chrome</p></div>',
                "fileName": "acta-prueba.pdf",
            }),
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 200, response.content[:500])
        self.assertEqual(response["Content-Type"], "application/pdf")
        with Pdf.open(BytesIO(response.content)) as pdf:
            self.assertTrue(pdf.is_linearized)
            self.assertEqual(len(pdf.pages), 1)
            content = bytes(pdf.pages[0].Contents.read_bytes())
            self.assertIn(b"Tj", content)
            self.assertIn("/Font", pdf.pages[0].Resources)
            self.assertNotIn("/XObject", pdf.pages[0].Resources)

    def test_creating_material_report_creates_receipt_data(self):
        response = self.client.post(
            reverse("project_reports_api", args=[self.project.slug]),
            data={"reportType": "materiales", "reportTitle": "Acta de recepción"},
        )

        self.assertEqual(response.status_code, 201)
        report = ProjectReport.objects.get(project=self.project)
        self.assertEqual(report.report_type, ProjectReport.TYPE_MATERIAL_RECEIPT)
        self.assertTrue(MaterialReceipt.objects.filter(report=report).exists())
        self.assertEqual(response.json()["report"]["materialReceipt"]["signatures"], {
            "delivered": "",
            "received": "",
            "verified": "",
        })

    def test_existing_reports_serialize_without_receipt_data(self):
        ProjectReport.objects.create(project=self.project, title="Reporte existente")

        response = self.client.get(reverse("project_collection_api"))

        self.assertEqual(response.status_code, 200)
        report_data = response.json()["projects"][0]["reports"][0]
        self.assertEqual(report_data["materialReceipt"]["actNumber"], "")

    def test_receipt_api_saves_fields_and_uploaded_signature(self):
        report = ProjectReport.objects.create(
            project=self.project,
            report_type=ProjectReport.TYPE_MATERIAL_RECEIPT,
            title="Acta de recepción",
        )
        image_buffer = BytesIO()
        Image.new("RGB", (4, 4), "black").save(image_buffer, format="PNG")
        response = self.client.post(
            reverse("material_receipt_api", args=[self.project.slug, report.id]),
            data={
                "actNumber": "AR-001",
                "receiptDate": "2026-10-31",
                "supplier": "Proveedor de prueba",
                "deliveredBy": "Responsable de entrega",
                "deliveredDni": "12345678",
                "deliveredPosition": "Almacenero",
                "receivedDni": "87654321",
                "receivedPosition": "Residente",
                "verifiedDni": "11223344",
                "verifiedPosition": "Supervisor",
                "conformity": "parcial",
                "signatureReceived": SimpleUploadedFile("firma.png", image_buffer.getvalue(), content_type="image/png"),
                "companyLogo": SimpleUploadedFile("logo.png", image_buffer.getvalue(), content_type="image/png"),
            },
        )

        self.assertEqual(response.status_code, 200)
        receipt = MaterialReceipt.objects.get(report=report)
        self.assertEqual(receipt.act_number, "AR-001")
        self.assertEqual(str(receipt.receipt_date), "2026-10-31")
        self.assertEqual(receipt.delivered_by, "Responsable de entrega")
        self.assertEqual(receipt.delivered_dni, "12345678")
        self.assertEqual(receipt.delivered_position, "Almacenero")
        self.assertEqual(receipt.received_dni, "87654321")
        self.assertEqual(receipt.received_position, "Residente")
        self.assertEqual(receipt.verified_dni, "11223344")
        self.assertEqual(receipt.verified_position, "Supervisor")
        self.assertEqual(receipt.conformity, "parcial")
        self.assertTrue(receipt.signature_received.name)
        self.assertTrue(response.json()["materialReceipt"]["signatures"]["received"])
        self.assertEqual(receipt.received_signed_on, timezone.localdate())
        self.assertEqual(response.json()["materialReceipt"]["signedOn"]["received"], timezone.localdate().isoformat())
        self.assertTrue(receipt.company_logo.name)
        self.assertTrue(response.json()["materialReceipt"]["companyLogo"])

        clear_response = self.client.post(
            reverse("material_receipt_api", args=[self.project.slug, report.id]),
            data={"clearCompanyLogo": "true"},
        )

        self.assertEqual(clear_response.status_code, 200)
        receipt.refresh_from_db()
        self.assertFalse(receipt.company_logo)
        self.assertEqual(clear_response.json()["materialReceipt"]["companyLogo"], "")

        clear_signature_response = self.client.post(
            reverse("material_receipt_api", args=[self.project.slug, report.id]),
            data={"clearSignatureReceived": "true"},
        )

        self.assertEqual(clear_signature_response.status_code, 200)
        receipt.refresh_from_db()
        self.assertFalse(receipt.signature_received)
        self.assertIsNone(receipt.received_signed_on)

    def test_project_creator_can_clear_shared_signature_and_signer_identity(self):
        report = ProjectReport.objects.create(
            project=self.project,
            report_type=ProjectReport.TYPE_MATERIAL_RECEIPT,
            title="Acta de recepción",
        )
        receipt = MaterialReceipt.objects.create(
            report=report,
            share_token="shared-signature-reset",
            delivered_share_password="hashed-delivered",
            verified_share_password="hashed-verified",
            received_share_password="hashed-received",
            received_by="Responsable que firmó",
            received_dni="12345678",
            received_position="Residente",
            received_signed_on=timezone.localdate(),
            signature_received=SimpleUploadedFile(
                "firma-recibido.png",
                self._receipt_signature_png(),
                content_type="image/png",
            ),
        )
        receipt_url = reverse("material_receipt_api", args=[self.project.slug, report.id])

        replacement_response = self.client.post(
            receipt_url,
            data={
                "signatureReceived": SimpleUploadedFile(
                    "firma-recibido-actualizada.png",
                    self._receipt_signature_png(),
                    content_type="image/png",
                ),
            },
        )

        self.assertEqual(replacement_response.status_code, 200)
        receipt.refresh_from_db()
        self.assertTrue(receipt.signature_received.name.endswith("firma-recibido-actualizada.png"))
        self.assertTrue(replacement_response.json()["materialReceipt"]["signatures"]["received"])

        response = self.client.post(receipt_url, data={"clearSignatureReceived": "true"})

        self.assertEqual(response.status_code, 200)
        receipt.refresh_from_db()
        self.assertFalse(receipt.signature_received)
        self.assertIsNone(receipt.received_signed_on)
        self.assertEqual(receipt.received_by, "")
        self.assertEqual(receipt.received_dni, "")
        self.assertEqual(receipt.received_position, "")
        self.assertEqual(response.json()["materialReceipt"]["signatures"]["received"], "")
        self.assertEqual(response.json()["materialReceipt"]["signedOn"]["received"], "")
        self.assertEqual(response.json()["materialReceipt"]["receivedBy"], "")
        self.assertEqual(response.json()["materialReceipt"]["receivedDni"], "")
        self.assertEqual(response.json()["materialReceipt"]["receivedPosition"], "")

        editor = User.objects.create_user(username="editor-firma", password="test-password")
        UserProfile.objects.update_or_create(user=editor, defaults={"is_approved": True})
        ProjectMembership.objects.create(
            project=self.project,
            user=editor,
            role=ProjectMembership.ROLE_EDITOR,
        )
        receipt.received_by = "Responsable que firmó"
        receipt.received_dni = "12345678"
        receipt.received_position = "Residente"
        receipt.received_signed_on = timezone.localdate()
        receipt.signature_received = SimpleUploadedFile(
            "firma-recibido.png",
            self._receipt_signature_png(),
            content_type="image/png",
        )
        receipt.save()
        self.client.force_login(editor)

        editor_response = self.client.post(receipt_url, data={"clearSignatureReceived": "true"})

        self.assertEqual(editor_response.status_code, 403)
        receipt.refresh_from_db()
        self.assertTrue(receipt.signature_received)
        self.assertEqual(receipt.received_by, "Responsable que firmó")

    def test_project_owner_can_update_conformity_and_observations_with_share_active(self):
        report = ProjectReport.objects.create(
            project=self.project,
            report_type=ProjectReport.TYPE_MATERIAL_RECEIPT,
            title="Acta de recepción",
        )
        MaterialReceipt.objects.create(
            report=report,
            share_token="shared-conformity-update",
            delivered_share_password="hashed-delivered",
            verified_share_password="hashed-verified",
            received_share_password="hashed-received",
        )

        response = self.client.post(
            reverse("material_receipt_api", args=[self.project.slug, report.id]),
            data={"conformity": "observado", "observations": "El empaque llegó dañado."},
        )

        self.assertEqual(response.status_code, 200)
        receipt = MaterialReceipt.objects.get(report=report)
        self.assertEqual(receipt.conformity, "observado")
        self.assertEqual(receipt.observations, "El empaque llegó dañado.")
        self.assertEqual(response.json()["materialReceipt"]["conformity"], "observado")
        self.assertEqual(response.json()["materialReceipt"]["observations"], "El empaque llegó dañado.")

    def test_shared_act_passes_photos_to_the_shared_preview_renderer(self):
        from django.contrib.auth.hashers import make_password

        report = ProjectReport.objects.create(
            project=self.project,
            report_type=ProjectReport.TYPE_MATERIAL_RECEIPT,
            title="Acta de recepción",
        )
        receipt = MaterialReceipt.objects.create(
            report=report,
            share_token="shared-photo-pages",
            delivered_share_password=make_password("entrega-123"),
            verified_share_password=make_password("valida-123"),
            received_share_password=make_password("recibe-123"),
        )
        photo = MaterialReceiptPhoto.objects.create(
            receipt=receipt,
            image=SimpleUploadedFile(
                "foto-validacion.png",
                self._receipt_signature_png(),
                content_type="image/png",
            ),
        )
        share_path = reverse("material_receipt_share", args=[receipt.share_token])

        self.client.post(
            share_path,
            data={
                "action": "authenticate",
                "signer": "delivered",
                "password": "entrega-123",
                "name": "Persona que entrega",
                "dni": "11111111",
                "position": "Almacenero",
            },
        )
        response = self.client.get(share_path)

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'id="previewCanvas"')
        self.assertContains(response, 'id="previewScaleShell"')
        self.assertContains(response, 'id="reportContainer"')
        self.assertContains(response, '"url": "' + photo.image.url + '"')
        self.assertEqual(
            response.context["shared_preview"]["report"]["materialReceipt"]["photos"][0]["url"],
            photo.image.url,
        )
        self.assertContains(response, 'report_app/app.js')
        self.assertNotContains(response, 'class="materials-receipt-photo-slot')

    def test_shared_signing_order_reopens_after_owner_clears_signatures(self):
        from django.contrib.auth.hashers import make_password
        from django.test import Client
        from report_app.views import MATERIAL_RECEIPT_SHARE_SIGNERS

        report = ProjectReport.objects.create(
            project=self.project,
            report_type=ProjectReport.TYPE_MATERIAL_RECEIPT,
            title="Acta de recepción",
        )
        receipt = MaterialReceipt.objects.create(
            report=report,
            share_token="shared-signature-order-reset",
            delivered_share_password=make_password("entrega-123"),
            verified_share_password=make_password("valida-123"),
            received_share_password=make_password("recibe-123"),
        )
        image_bytes = self._receipt_signature_png()
        for key, name, dni, position in (
            ("delivered", "Persona que entrega", "11111111", "Almacenero"),
            ("verified", "Persona que valida", "22222222", "Supervisor"),
            ("received", "Persona que recibe", "33333333", "Residente"),
        ):
            signer = MATERIAL_RECEIPT_SHARE_SIGNERS[key]
            setattr(receipt, signer["name_field"], name)
            setattr(receipt, signer["dni_field"], dni)
            setattr(receipt, signer["position_field"], position)
            getattr(receipt, signer["signature_field"]).save(
                f"firma-{key}.png",
                SimpleUploadedFile(f"firma-{key}.png", image_bytes, content_type="image/png"),
                save=False,
            )
        receipt.save()

        share_path = reverse("material_receipt_share", args=[receipt.share_token])
        receipt_api = reverse("material_receipt_api", args=[self.project.slug, report.id])
        signer_clients = {}
        for key, password, name, dni, position in (
            ("delivered", "entrega-123", "Persona que entrega", "11111111", "Almacenero"),
            ("verified", "valida-123", "Persona que valida", "22222222", "Supervisor"),
            ("received", "recibe-123", "Persona que recibe", "33333333", "Residente"),
        ):
            client = Client()
            login_response = client.post(
                share_path,
                data={
                    "action": "authenticate",
                    "signer": key,
                    "password": password,
                    "name": name,
                    "dni": dni,
                    "position": position,
                },
            )
            self.assertEqual(login_response.status_code, 302)
            signer_clients[key] = client

        def sign_as(key):
            return signer_clients[key].post(
                share_path,
                data={
                    "action": "sign",
                    "signature": SimpleUploadedFile(
                        f"nueva-firma-{key}.png",
                        image_bytes,
                        content_type="image/png",
                    ),
                },
            )

        def assert_can_sign(key):
            response = signer_clients[key].get(share_path)
            self.assertContains(response, 'id="receiptSignatureCanvas"')

        self.assertEqual(self.client.post(receipt_api, data={"clearSignatureReceived": "true"}).status_code, 200)
        assert_can_sign("received")
        self.assertEqual(sign_as("received").status_code, 302)

        reset_middle_and_last = self.client.post(
            receipt_api,
            data={"clearSignatureVerified": "true", "clearSignatureReceived": "true"},
        )
        self.assertEqual(reset_middle_and_last.status_code, 200)
        assert_can_sign("verified")
        self.assertContains(signer_clients["received"].get(share_path), "Podrás firmar cuando termine VALIDA")
        self.assertEqual(sign_as("verified").status_code, 302)
        assert_can_sign("received")
        self.assertEqual(sign_as("received").status_code, 302)

        reset_all = self.client.post(
            receipt_api,
            data={
                "clearSignatureDelivered": "true",
                "clearSignatureVerified": "true",
                "clearSignatureReceived": "true",
            },
        )
        self.assertEqual(reset_all.status_code, 200)
        receipt.refresh_from_db()
        self.assertFalse(receipt.signature_delivered)
        self.assertFalse(receipt.signature_verified)
        self.assertFalse(receipt.signature_received)
        assert_can_sign("delivered")
        blocked_verified = sign_as("verified")
        self.assertContains(blocked_verified, "Debes esperar a que firme primero")
        self.assertEqual(sign_as("delivered").status_code, 302)
        assert_can_sign("verified")
        self.assertContains(signer_clients["received"].get(share_path), "Podrás firmar cuando termine VALIDA")
        self.assertEqual(sign_as("verified").status_code, 302)
        assert_can_sign("received")
        self.assertEqual(sign_as("received").status_code, 302)

    def test_receipt_api_rejects_invalid_company_logo(self):
        report = ProjectReport.objects.create(
            project=self.project,
            report_type=ProjectReport.TYPE_MATERIAL_RECEIPT,
            title="Acta de recepción",
        )
        response = self.client.post(
            reverse("material_receipt_api", args=[self.project.slug, report.id]),
            data={"companyLogo": SimpleUploadedFile("logo.txt", b"no es imagen", content_type="image/png")},
        )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["error"], "El archivo del logo no contiene una imagen válida.")

    def test_receipt_photos_save_in_order_and_can_be_removed(self):
        report = ProjectReport.objects.create(
            project=self.project,
            report_type=ProjectReport.TYPE_MATERIAL_RECEIPT,
            title="Acta de recepción",
        )
        photos_url = reverse("material_receipt_photos_api", args=[self.project.slug, report.id])
        image_bytes = self._receipt_signature_png()
        response = self.client.post(
            photos_url,
            data={
                "photos": [
                    SimpleUploadedFile(f"validacion-{index}.png", image_bytes, content_type="image/png")
                    for index in range(1, 6)
                ],
            },
        )

        self.assertEqual(response.status_code, 201)
        self.assertEqual(len(response.json()["photos"]), 5)
        self.assertEqual(
            [photo["name"] for photo in response.json()["photos"]],
            [f"validacion-{index}.png" for index in range(1, 6)],
        )
        self.assertEqual(MaterialReceiptPhoto.objects.filter(receipt__report=report).count(), 5)

        first_photo = MaterialReceiptPhoto.objects.filter(receipt__report=report).first()
        image_path = first_photo.image.path
        delete_response = self.client.delete(
            reverse(
                "material_receipt_photo_detail_api",
                args=[self.project.slug, report.id, first_photo.id],
            )
        )

        self.assertEqual(delete_response.status_code, 200)
        self.assertEqual(len(delete_response.json()["photos"]), 4)
        self.assertFalse(os.path.exists(image_path))

    def test_receipt_photos_reject_invalid_image_files(self):
        report = ProjectReport.objects.create(
            project=self.project,
            report_type=ProjectReport.TYPE_MATERIAL_RECEIPT,
            title="Acta de recepción",
        )
        response = self.client.post(
            reverse("material_receipt_photos_api", args=[self.project.slug, report.id]),
            data={
                "photos": SimpleUploadedFile(
                    "no-es-imagen.png",
                    b"contenido no valido",
                    content_type="image/png",
                ),
            },
        )

        self.assertEqual(response.status_code, 400)
        self.assertFalse(MaterialReceiptPhoto.objects.filter(receipt__report=report).exists())

    def test_receipt_viewer_cannot_upload_photos(self):
        report = ProjectReport.objects.create(
            project=self.project,
            report_type=ProjectReport.TYPE_MATERIAL_RECEIPT,
            title="Acta de recepción",
        )
        viewer = User.objects.create_user(username="lector-fotos", password="ClaveSegura123")
        UserProfile.objects.update_or_create(user=viewer, defaults={"is_approved": True})
        ProjectMembership.objects.create(
            project=self.project,
            user=viewer,
            role=ProjectMembership.ROLE_VIEWER,
        )
        self.client.force_login(viewer)

        response = self.client.post(
            reverse("material_receipt_photos_api", args=[self.project.slug, report.id]),
            data={
                "photos": SimpleUploadedFile(
                    "validacion.png",
                    self._receipt_signature_png(),
                    content_type="image/png",
                ),
            },
        )

        self.assertEqual(response.status_code, 403)
        self.assertFalse(MaterialReceiptPhoto.objects.filter(receipt__report=report).exists())

    def test_material_entries_keep_unit_and_condition(self):
        report = ProjectReport.objects.create(
            project=self.project,
            report_type=ProjectReport.TYPE_MATERIAL_RECEIPT,
            title="Acta de recepción",
        )
        response = self.client.post(
            reverse("report_entries_api", args=[self.project.slug, report.id]),
            data={
                "itemName": "Cemento",
                "unit": "bolsa",
                "quantity": "4",
                "condition": "Conforme",
                "status": "Conforme",
            },
        )

        self.assertEqual(response.status_code, 201)
        entry = ReportEntry.objects.get(report=report)
        self.assertEqual(entry.unit, "bolsa")
        self.assertEqual(entry.condition, "Conforme")
        self.assertEqual(response.json()["entry"]["quantity"], 4)

    def test_receipt_api_rejects_invalid_date(self):
        report = ProjectReport.objects.create(
            project=self.project,
            report_type=ProjectReport.TYPE_MATERIAL_RECEIPT,
            title="Acta de recepción",
        )
        response = self.client.post(
            reverse("material_receipt_api", args=[self.project.slug, report.id]),
            data={"receiptDate": "fecha incorrecta"},
        )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["error"], "La fecha de recepción no es válida.")

    def test_share_configuration_requires_separate_passwords_and_owner_access(self):
        report = ProjectReport.objects.create(
            project=self.project,
            report_type=ProjectReport.TYPE_MATERIAL_RECEIPT,
            title="Acta de recepción",
        )
        share_url = reverse("material_receipt_share_api", args=[self.project.slug, report.id])
        payload = {"delivered": "entrega-123", "verified": "valida-123", "received": "recibe-123"}
        response = self.client.post(share_url, data=json.dumps(payload), content_type="application/json")

        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json()["configured"])
        self.assertIn("/acta/compartida/", response.json()["shareUrl"])
        receipt = MaterialReceipt.objects.get(report=report)
        self.assertNotEqual(receipt.delivered_share_password, payload["delivered"])
        self.assertNotEqual(receipt.verified_share_password, payload["verified"])
        self.assertNotEqual(receipt.received_share_password, payload["received"])

        get_response = self.client.get(share_url)
        self.assertEqual(get_response.status_code, 200)
        self.assertEqual(get_response.json()["shareUrl"], response.json()["shareUrl"])

        invalid_response = self.client.post(
            share_url,
            data=json.dumps({"delivered": "short", "verified": "valida-123", "received": "recibe-123"}),
            content_type="application/json",
        )
        self.assertEqual(invalid_response.status_code, 400)

    def test_public_signing_requires_password_and_enforces_order_and_one_time_signature(self):
        report = ProjectReport.objects.create(
            project=self.project,
            report_type=ProjectReport.TYPE_MATERIAL_RECEIPT,
            title="Acta de recepción",
        )
        front = ReportFront.objects.create(report=report, name="Materiales")
        ReportEntry.objects.create(
            report=report,
            front=front,
            item_name="Cemento",
            quantity=4,
            unit="bolsa",
            status="Conforme",
            description="Sin daños",
        )
        for index in range(12):
            ReportEntry.objects.create(
                report=report,
                front=front,
                item_name=f"Material {index + 2}",
                quantity=1,
                unit="und",
                status="Conforme",
            )
        setup_response = self.client.post(
            reverse("material_receipt_share_api", args=[self.project.slug, report.id]),
            data=json.dumps({"delivered": "entrega-123", "verified": "valida-123", "received": "recibe-123"}),
            content_type="application/json",
        )
        self.assertEqual(setup_response.status_code, 200)
        share_path = urlsplit(setup_response.json()["shareUrl"]).path
        receipt = MaterialReceipt.objects.get(report=report)
        self.client.logout()

        initial_page = self.client.get(share_path)
        self.assertEqual(initial_page.status_code, 200)
        self.assertNotContains(initial_page, "Materiales registrados")
        self.assertNotContains(initial_page, "Cemento")
        unavailable_pdf = self.client.get(reverse("material_receipt_shared_pdf", args=[receipt.share_token]))
        self.assertEqual(unavailable_pdf.status_code, 403)
        self.assertTemplateUsed(unavailable_pdf, "report_app/material_receipt_pdf_unavailable.html")
        self.assertContains(
            unavailable_pdf,
            "El PDF estará disponible cuando los tres responsables hayan firmado.",
            status_code=403,
        )
        self.assertContains(unavailable_pdf, reverse("material_receipt_share", args=[receipt.share_token]), status_code=403)
        invalid_password = self.client.post(
            share_path,
            data={
                "action": "authenticate",
                "signer": "delivered",
                "password": "no-es-correcta",
                "name": "Persona que entrega",
                "dni": "11111111",
                "position": "Almacenero",
            },
        )
        self.assertContains(invalid_password, "La contraseña no es válida")
        self.assertNotContains(invalid_password, "Cemento")

        missing_identity = self.client.post(
            share_path,
            data={"action": "authenticate", "signer": "delivered", "password": "entrega-123"},
        )
        self.assertContains(missing_identity, "Completa tu nombre, DNI y cargo")
        self.assertNotContains(missing_identity, "Cemento")

        received_login = self.client.post(
            share_path,
            data={
                "action": "authenticate",
                "signer": "received",
                "password": "recibe-123",
                "name": "Persona que recibe",
                "dni": "33333333",
                "position": "Residente",
            },
        )
        self.assertEqual(received_login.status_code, 302)
        received_page = self.client.get(share_path)
        self.assertContains(received_page, "Tu acceso está validado")
        self.assertTemplateUsed(received_page, "report_app/material_receipt_shared_act.html")
        self.assertContains(received_page, 'id="previewCanvas"')
        self.assertContains(received_page, 'id="previewScaleShell"')
        self.assertContains(received_page, 'id="reportContainer"')
        self.assertContains(received_page, 'id="sharedReceiptPreviewData"')
        self.assertContains(received_page, "html2canvas@1.4.1/dist/html2canvas.min.js")
        self.assertContains(received_page, "jspdf/2.5.1/jspdf.umd.min.js")
        self.assertContains(received_page, 'id="sharedPdfPending"')
        self.assertContains(received_page, "PDF pendiente: 3 firmas")
        self.assertNotContains(received_page, reverse("material_receipt_shared_pdf", args=[receipt.share_token]))
        self.assertNotContains(received_page, "Revisa y firma tu sección. Al guardar, quedará firmada.")
        self.assertNotContains(received_page, "VALIDACIÓN FOTOGRÁFICA")
        self.assertContains(received_page, "Cemento")
        self.assertEqual(received_page.context["shared_preview"]["signerKey"], "received")
        self.assertFalse(received_page.context["shared_preview"]["canSign"])
        self.assertNotContains(received_page, "Materiales registrados")
        self.assertNotContains(received_page, 'id="receiptSignatureCanvas"')
        self.assertNotContains(received_page, 'name="observations"')
        self.assertNotContains(received_page, 'name="conformity"')
        unauthorized_observations = self.client.post(
            share_path,
            data={"action": "update_observations", "observations": "Comentario sin turno"},
        )
        self.assertContains(unauthorized_observations, "cuando llegue tu turno de firma")
        receipt = MaterialReceipt.objects.get(report=report)
        self.assertEqual(receipt.observations, "")
        blocked_signature = self.client.post(
            share_path,
            data={
                "action": "sign",
                "signature": SimpleUploadedFile("firma.png", self._receipt_signature_png(), content_type="image/png"),
            },
        )
        self.assertContains(blocked_signature, "Debes esperar a que firme primero")
        receipt = MaterialReceipt.objects.get(report=report)
        self.assertFalse(receipt.signature_received)

        delivered_login = self.client.post(
            share_path,
            data={
                "action": "authenticate",
                "signer": "delivered",
                "password": "entrega-123",
                "name": "Persona que entrega",
                "dni": "11111111",
                "position": "Almacenero",
            },
        )
        self.assertEqual(delivered_login.status_code, 302)
        delivered_page = self.client.get(share_path)
        self.assertContains(delivered_page, 'id="receiptSignatureCanvas"')
        self.assertEqual(delivered_page.context["shared_preview"]["signerKey"], "delivered")
        self.assertTrue(delivered_page.context["shared_preview"]["canEditObservations"])
        self.assertNotContains(delivered_page, 'name="conformity"')
        unauthorized_conformity = self.client.post(
            share_path,
            data={
                "action": "update_observations",
                "observations": "Faltan dos bolsas de cemento.",
                "conformity": "parcial",
            },
        )
        self.assertContains(unauthorized_conformity, "Solo la persona que recibe")
        receipt = MaterialReceipt.objects.get(report=report)
        self.assertEqual(receipt.conformity, "")
        observations_response = self.client.post(
            share_path,
            data={"action": "update_observations", "observations": "Faltan dos bolsas de cemento."},
        )
        self.assertEqual(observations_response.status_code, 302)
        observations_page = self.client.get(share_path)
        self.assertContains(observations_page, "Observaciones guardadas en el acta.")
        self.assertContains(observations_page, "Faltan dos bolsas de cemento.")
        receipt.refresh_from_db()
        self.assertEqual(receipt.observations, "Persona que entrega: Faltan dos bolsas de cemento.")
        logout_response = self.client.post(share_path, data={"action": "logout"})
        self.assertEqual(logout_response.status_code, 302)
        password_only_page = self.client.get(share_path)
        self.assertContains(password_only_page, "Vuelve a ingresar la contraseña")
        self.assertContains(password_only_page, 'name="password"')
        self.assertNotContains(password_only_page, 'name="name"')
        self.assertNotContains(password_only_page, 'name="dni"')
        self.assertNotContains(password_only_page, 'name="position"')
        self.assertNotContains(password_only_page, "Faltan dos bolsas de cemento.")
        reauth_response = self.client.post(
            share_path,
            data={"action": "authenticate", "signer": "delivered", "password": "entrega-123"},
        )
        self.assertEqual(reauth_response.status_code, 302)
        reauthenticated_page = self.client.get(share_path)
        self.assertEqual(reauthenticated_page.context["signer_name"], "Persona que entrega")
        self.assertEqual(reauthenticated_page.context["signer_dni"], "11111111")
        self.assertEqual(reauthenticated_page.context["signer_position"], "Almacenero")
        delivered_response = self.client.post(
            share_path,
            data={
                "action": "sign",
                "signature": SimpleUploadedFile("entrega.png", self._receipt_signature_png(), content_type="image/png"),
            },
        )
        self.assertEqual(delivered_response.status_code, 302)
        receipt.refresh_from_db()
        self.assertEqual(receipt.delivered_by, "Persona que entrega")
        self.assertEqual(receipt.delivered_signed_on, timezone.localdate())
        signed_delivered_page = self.client.get(share_path)
        self.assertNotContains(
            signed_delivered_page,
            "Esta sección ya fue firmada. Puedes revisar el acta, pero no volver a firmar.",
        )
        signed_observations_response = self.client.post(
            share_path,
            data={"action": "update_observations", "observations": "Cambio después de firmar"},
        )
        self.assertContains(signed_observations_response, "Ya firmaste esta sección")
        receipt.refresh_from_db()
        self.assertEqual(receipt.observations, "Persona que entrega: Faltan dos bolsas de cemento.")

        self.client.post(
            share_path,
            data={
                "action": "authenticate",
                "signer": "verified",
                "password": "valida-123",
                "name": "Persona que valida",
                "dni": "22222222",
                "position": "Supervisor",
            },
        )
        verified_comment_response = self.client.post(
            share_path,
            data={
                "action": "update_observations",
                "observations": "El embalaje llegó dañado.",
            },
        )
        self.assertEqual(verified_comment_response.status_code, 302)
        receipt.refresh_from_db()
        self.assertEqual(
            receipt.observations,
            "Persona que entrega: Faltan dos bolsas de cemento.\nPersona que valida: El embalaje llegó dañado.",
        )
        verified_response = self.client.post(
            share_path,
            data={
                "action": "sign",
                "signature": SimpleUploadedFile("valida.png", self._receipt_signature_png(), content_type="image/png"),
            },
        )
        self.assertEqual(verified_response.status_code, 302)
        receipt.refresh_from_db()
        self.assertTrue(receipt.signature_verified)

        self.client.post(
            share_path,
            data={
                "action": "authenticate",
                "signer": "received",
                "password": "recibe-123",
                "name": "Persona que recibe",
                "dni": "33333333",
                "position": "Residente",
            },
        )
        received_turn_page = self.client.get(share_path)
        self.assertEqual(received_turn_page.context["shared_preview"]["signerKey"], "received")
        self.assertTrue(received_turn_page.context["shared_preview"]["canSign"])
        conformity_response = self.client.post(
            share_path,
            data={
                "action": "update_observations",
                "observations": "El empaque llegó dañado.",
                "conformity": "observado",
            },
        )
        self.assertEqual(conformity_response.status_code, 302)
        receipt.refresh_from_db()
        self.assertEqual(receipt.conformity, "observado")
        self.assertEqual(
            receipt.observations,
            "Persona que entrega: Faltan dos bolsas de cemento.\n"
            "Persona que valida: El embalaje llegó dañado.\n"
            "Persona que recibe: El empaque llegó dañado.",
        )
        received_response = self.client.post(
            share_path,
            data={
                "action": "sign",
                "signature": SimpleUploadedFile("recibe.png", self._receipt_signature_png(), content_type="image/png"),
            },
        )
        self.assertEqual(received_response.status_code, 302)
        receipt.refresh_from_db()
        self.assertEqual(receipt.received_by, "Persona que recibe")
        all_signed_page = self.client.get(share_path)
        self.assertContains(all_signed_page, 'id="downloadSharedReceiptPdfBtn"')
        self.assertNotContains(
            all_signed_page,
            reverse("material_receipt_shared_pdf", args=[receipt.share_token]),
        )
        self.assertNotContains(all_signed_page, 'id="sharedPdfPending"')
        downloaded_receipt = all_signed_page.context["shared_preview"]["report"]["materialReceipt"]
        self.assertEqual(downloaded_receipt["deliveredBy"], "Persona que entrega")
        self.assertEqual(downloaded_receipt["deliveredDni"], "11111111")
        self.assertEqual(downloaded_receipt["deliveredPosition"], "Almacenero")
        self.assertEqual(downloaded_receipt["verifiedBy"], "Persona que valida")
        self.assertEqual(downloaded_receipt["verifiedDni"], "22222222")
        self.assertEqual(downloaded_receipt["verifiedPosition"], "Supervisor")
        self.assertEqual(downloaded_receipt["receivedBy"], "Persona que recibe")
        self.assertEqual(downloaded_receipt["receivedDni"], "33333333")
        self.assertEqual(downloaded_receipt["receivedPosition"], "Residente")
        signed_conformity_response = self.client.post(
            share_path,
            data={
                "action": "update_observations",
                "observations": "Cambio después de firmar",
                "conformity": "conforme",
            },
        )
        self.assertContains(signed_conformity_response, "Ya firmaste esta sección")
        receipt.refresh_from_db()
        self.assertEqual(receipt.conformity, "observado")
        self.assertEqual(
            receipt.observations,
            "Persona que entrega: Faltan dos bolsas de cemento.\n"
            "Persona que valida: El embalaje llegó dañado.\n"
            "Persona que recibe: El empaque llegó dañado.",
        )

        MaterialReceiptPhoto.objects.create(
            receipt=receipt,
            image=SimpleUploadedFile(
                "foto-validacion.png",
                self._receipt_signature_png(),
                content_type="image/png",
            ),
        )
        download_response = self.client.get(reverse("material_receipt_shared_pdf", args=[receipt.share_token]))
        self.assertEqual(download_response.status_code, 200)
        self.assertEqual(download_response["Content-Type"], "application/pdf")
        self.assertTrue(download_response.content.startswith(b"%PDF"))
        from pikepdf import Pdf

        with Pdf.open(BytesIO(download_response.content)) as shared_pdf:
            self.assertGreaterEqual(len(shared_pdf.pages), 2)

        self.client.post(
            share_path,
            data={
                "action": "authenticate",
                "signer": "delivered",
                "password": "entrega-123",
                "name": "Otro nombre",
                "dni": "99999999",
                "position": "Otro cargo",
            },
        )
        resign_response = self.client.post(
            share_path,
            data={
                "action": "sign",
                "signature": SimpleUploadedFile("otra.png", self._receipt_signature_png(), content_type="image/png"),
            },
        )
        self.assertContains(resign_response, "Esta sección ya fue firmada")
        receipt.refresh_from_db()
        self.assertEqual(receipt.delivered_by, "Persona que entrega")
        logout_response = self.client.post(share_path, data={"action": "logout"})
        self.assertEqual(logout_response.status_code, 302)
        access_page = self.client.get(share_path)
        self.assertContains(access_page, "Vuelve a ingresar la contraseña")
        self.assertContains(access_page, "3 DE 3 FIRMAS")
        self.assertContains(access_page, "descargar el PDF como imagen de la vista previa")
        self.assertNotContains(access_page, reverse("material_receipt_shared_pdf", args=[receipt.share_token]))
        self.client.logout()
        self.assertRedirects(
            self.client.get(reverse("material_receipt_shared_pdf", args=[receipt.share_token])),
            share_path,
        )

    def _receipt_signature_png(self):
        image_buffer = BytesIO()
        Image.new("RGB", (4, 4), "black").save(image_buffer, format="PNG")
        return image_buffer.getvalue()

    def test_fillable_receipt_template_contains_acroform_fields(self):
        response = self.client.get(reverse("material_receipt_template_pdf"))

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["Content-Type"], "application/pdf")
        self.assertIn(b"/AcroForm", response.content)
        self.assertIn(b"numero_acta", response.content)
        self.assertIn(b"fecha_entrega", response.content)
        self.assertIn(b"material_6_observaciones", response.content)
        self.assertNotIn(b"material_1_estado", response.content)
        self.assertIn(b"entrega_firma", response.content)
        self.assertIn(b"valida_vdc_dni", response.content)
        self.assertIn(b"recibe_cosapi_cargo", response.content)
        self.assertIn(b"parcial", response.content)

    def test_report_fillable_pdf_appends_photo_pages_and_preserves_form(self):
        from pikepdf import Pdf

        report = ProjectReport.objects.create(
            project=self.project,
            report_type=ProjectReport.TYPE_MATERIAL_RECEIPT,
            title="Acta de recepción",
        )
        receipt = MaterialReceipt.objects.create(report=report, act_number="AR-005")
        receipt.delivered_by = "Persona entrega"
        receipt.verified_by = "Persona valida"
        receipt.received_by = "Persona recibe"
        receipt.delivered_dni = "12345678"
        receipt.delivered_position = "Almacenero"
        receipt.verified_dni = "23456789"
        receipt.verified_position = "Supervisor"
        receipt.received_dni = "34567890"
        receipt.received_position = "Residente"
        receipt.save()
        image_bytes = self._receipt_signature_png()
        for field_name in ("signature_delivered", "signature_verified", "signature_received"):
            getattr(receipt, field_name).save(
                f"{field_name}.png",
                SimpleUploadedFile(
                    f"{field_name}.png",
                    image_bytes,
                    content_type="image/png",
                ),
                save=True,
            )
        for index in range(5):
            MaterialReceiptPhoto.objects.create(
                receipt=receipt,
                image=SimpleUploadedFile(
                    f"validacion-{index + 1}.png",
                    image_bytes,
                    content_type="image/png",
                ),
                sort_order=index,
            )

        response = self.client.get(
            reverse(
                "material_receipt_report_fillable_pdf",
                args=[self.project.slug, report.id],
            )
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["Content-Type"], "application/pdf")
        with Pdf.open(BytesIO(response.content)) as pdf:
            self.assertEqual(len(pdf.pages), 3)
            self.assertIn("/AcroForm", pdf.Root)
            self.assertTrue(pdf.pages[0].get("/Annots"))
            for photo_page in pdf.pages[1:]:
                page_content = photo_page.Contents.read_bytes()
                self.assertIn(b"FIRMAS DE RESPONSABILIDAD", page_content)
                self.assertIn(b"Nombre:", page_content)
                self.assertIn(b"DNI:", page_content)
                self.assertIn(b"Cargo:", page_content)
                self.assertIn(b"Fecha:", page_content)
                self.assertIn(b"Persona entrega", page_content)
                self.assertIn(b"12345678", page_content)
                self.assertIn(b"Almacenero", page_content)
                self.assertIn(b"Persona valida", page_content)
                self.assertIn(b"23456789", page_content)
                self.assertIn(b"Supervisor", page_content)
                self.assertIn(b"Persona recibe", page_content)
                self.assertIn(b"34567890", page_content)
                self.assertIn(b"Residente", page_content)
                self.assertIn(b"Persona entrega", page_content)
                self.assertIn(b"Persona valida", page_content)
                self.assertIn(b"Persona recibe", page_content)


class PublicReportSharingTests(TestCase):
    def setUp(self):
        self.owner = User.objects.create_user(username="public-share-owner", password="owner-password")
        UserProfile.objects.update_or_create(user=self.owner, defaults={"is_approved": True})
        self.project = ReportProject.objects.create(
            owner=self.owner,
            company_name="VDC",
            project_name="Proyecto para compartir",
        )
        self.report = ProjectReport.objects.create(
            project=self.project,
            title="Reporte compartido",
            report_type=ProjectReport.TYPE_PROGRESS,
        )
        self.other_report = ProjectReport.objects.create(
            project=self.project,
            title="Reporte privado",
        )

    def _create_share(self):
        self.client.force_login(self.owner)
        response = self.client.post(
            reverse("public_report_share_api", args=[self.project.slug, self.report.id]),
            data=json.dumps({"password": "reporte-seguro-123"}),
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 200)
        share = PublicReportShare.objects.get(report=self.report)
        self.client.logout()
        return share, response.json()["shareUrl"]

    def _open_public_report(self, share_url):
        path = urlsplit(share_url).path
        password_page = self.client.get(path)
        self.assertEqual(password_page.status_code, 200)
        return self.client.post(path, {"password": "reporte-seguro-123"})

    @staticmethod
    def _png_upload():
        image_buffer = BytesIO()
        Image.new("RGB", (4, 4), color="blue").save(image_buffer, format="PNG")
        return SimpleUploadedFile("evidencia.png", image_buffer.getvalue(), content_type="image/png")

    def test_password_share_is_limited_to_one_report_and_allows_photo_edits(self):
        share, share_url = self._create_share()

        invalid_password = self.client.post(
            urlsplit(share_url).path,
            {"password": "incorrecta"},
        )
        self.assertEqual(invalid_password.status_code, 401)
        access_response = self._open_public_report(share_url)
        self.assertEqual(access_response.status_code, 302)
        self.assertEqual(
            access_response["Location"],
            reverse("reporte_detail", args=[self.project.slug, self.report.id]),
        )

        page_response = self.client.get(access_response["Location"])
        self.assertEqual(page_response.status_code, 200)
        self.assertContains(page_response, 'data-public-report-share="true"')

        shared_report_url = reverse("reporte_detail", args=[self.project.slug, self.report.id])
        for route_name in ("root", "panel_principal", "proyecto"):
            response = self.client.get(reverse(route_name))
            self.assertRedirects(response, shared_report_url, fetch_redirect_response=False)
        self.assertEqual(
            self.client.get(reverse("proyecto_detail", args=[self.project.slug])).status_code,
            404,
        )
        self.assertEqual(
            self.client.get(reverse("reporte_detail", args=[self.project.slug, self.other_report.id])).status_code,
            404,
        )

        projects_response = self.client.get(reverse("project_collection_api"))
        self.assertEqual(projects_response.status_code, 200)
        projects = projects_response.json()["projects"]
        self.assertEqual(len(projects), 1)
        self.assertEqual([report["id"] for report in projects[0]["reports"]], [self.report.id])
        self.assertEqual(projects[0]["reports"][0]["members"], [])

        update_response = self.client.post(
            reverse("project_report_update_api", args=[self.project.slug, self.report.id]),
            {"reportTitle": "Reporte actualizado por enlace"},
        )
        self.assertEqual(update_response.status_code, 200)
        self.report.refresh_from_db()
        self.assertEqual(self.report.title, "Reporte actualizado por enlace")

        front = ReportFront.objects.create(report=self.report, name="Frente público")
        image = self._png_upload()
        entry_response = self.client.post(
            reverse("report_entries_api", args=[self.project.slug, self.report.id]),
            {
                "frontId": str(front.id),
                "status": "Pendiente",
                "desc": "Registro agregado desde el enlace",
                "images": image,
            },
        )
        self.assertEqual(entry_response.status_code, 201)
        entry = ReportEntry.objects.get(report=self.report)
        self.assertEqual(entry.images.count(), 1)

        other_report_response = self.client.post(
            reverse("project_report_update_api", args=[self.project.slug, self.other_report.id]),
            {"reportTitle": "No permitido"},
        )
        self.assertEqual(other_report_response.status_code, 404)

    def test_material_receipt_public_share_allows_signature_upload(self):
        self.report.report_type = ProjectReport.TYPE_MATERIAL_RECEIPT
        self.report.save(update_fields=["report_type"])
        receipt = MaterialReceipt.objects.create(report=self.report)
        share, share_url = self._create_share()
        access_response = self._open_public_report(share_url)
        self.assertEqual(access_response.status_code, 302)

        signature_response = self.client.post(
            reverse("material_receipt_api", args=[self.project.slug, self.report.id]),
            {
                "deliveredBy": "Firmante de prueba",
                "deliveredDni": "12345678",
                "deliveredPosition": "Responsable",
                "signatureDelivered": self._png_upload(),
            },
        )

        self.assertEqual(signature_response.status_code, 200)
        receipt.refresh_from_db()
        self.assertTrue(receipt.signature_delivered)
        self.assertEqual(receipt.delivered_by, "Firmante de prueba")
        self.assertEqual(receipt.delivered_dni, "12345678")

    @override_settings(MEDIA_ROOT=tempfile.mkdtemp())
    def test_material_receipt_share_hides_only_receipt_meta_and_keeps_preview_features(self):
        self.report.report_type = ProjectReport.TYPE_MATERIAL_RECEIPT
        self.report.save(update_fields=["report_type"])
        MaterialReceipt.objects.create(report=self.report)
        _, share_url = self._create_share()
        access_response = self._open_public_report(share_url)
        self.assertEqual(access_response.status_code, 302)

        page_response = self.client.get(access_response["Location"])
        self.assertEqual(page_response.status_code, 200)
        self.assertContains(page_response, "materialReceiptPhotoFiles")
        self.assertContains(page_response, "Vista previa del reporte")
        self.assertContains(page_response, 'id="equipmentName"')
        self.assertNotContains(page_response, "N.° de acta")
        self.assertNotContains(page_response, "Fecha de recepción")
        self.assertNotContains(page_response, "Logo de la empresa para el encabezado")
        self.assertNotContains(page_response, "La conformidad y los datos y firmas")

        self.assertContains(page_response, 'id="materialReceiptPhotoFiles"')
        self.assertContains(page_response, 'id="saveMaterialReceiptPreviewBtn"')
        self.assertContains(page_response, 'id="downloadPublicReceiptPdfBtn"')
        self.assertNotContains(page_response, "Sube las fotos que necesites.")
        self.assertNotContains(page_response, "Todavía no hay fotos.")

        photo_url = reverse("material_receipt_photos_api", args=[self.project.slug, self.report.id])
        upload_response = self.client.post(photo_url, {"photos": self._png_upload()})
        self.assertEqual(upload_response.status_code, 201)
        self.assertEqual(MaterialReceiptPhoto.objects.filter(receipt__report=self.report).count(), 1)

        receipt_update_response = self.client.post(
            reverse("material_receipt_api", args=[self.project.slug, self.report.id]),
            {"actNumber": "Acta actualizada", "deliveryLocation": "Almacén central"},
        )
        self.assertEqual(receipt_update_response.status_code, 200)
        receipt = MaterialReceipt.objects.get(report=self.report)
        self.assertEqual(receipt.act_number, "Acta actualizada")
        self.assertEqual(receipt.delivery_location, "Almacén central")
        self.assertEqual(receipt_update_response.json()["materialReceipt"]["deliveryLocation"], "Almacén central")

        signatures_response = self.client.post(
            reverse("material_receipt_api", args=[self.project.slug, self.report.id]),
            {
                "deliveredBy": "Responsable 1",
                "verifiedBy": "Responsable 2",
                "receivedBy": "Responsable 3",
                "signatureDelivered": self._png_upload(),
                "signatureVerified": self._png_upload(),
                "signatureReceived": self._png_upload(),
            },
        )
        self.assertEqual(signatures_response.status_code, 200)
    def test_owner_can_revoke_a_public_report_share(self):
        share, share_url = self._create_share()
        access_response = self._open_public_report(share_url)
        self.assertEqual(access_response.status_code, 302)

        owner_client = Client()
        owner_client.force_login(self.owner)
        revoke_response = owner_client.delete(
            reverse("public_report_share_api", args=[self.project.slug, self.report.id])
        )

        self.assertEqual(revoke_response.status_code, 200)
        share.refresh_from_db()
        self.assertFalse(share.is_active)
        self.assertEqual(self.client.get(urlsplit(share_url).path).status_code, 404)
