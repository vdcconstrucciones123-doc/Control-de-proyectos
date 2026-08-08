from django.test import TestCase
from django.urls import reverse


class HomeViewTests(TestCase):
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
