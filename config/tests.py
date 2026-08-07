from django.test import Client, SimpleTestCase
from django.urls import reverse

from . import settings


class MediaUrlsTests(SimpleTestCase):
    def test_media_url_usa_caminho_absoluto(self):
        self.assertEqual(settings.MEDIA_URL, "/media/")


class CsrfFailureTests(SimpleTestCase):
    def test_token_invalido_exibe_recuperacao_sem_detalhes_tecnicos(self):
        client = Client(enforce_csrf_checks=True)

        response = client.post(
            reverse("login"),
            {
                "username": "usuario-inexistente",
                "password": "senha-invalida",
                "csrfmiddlewaretoken": "token-invalido",
            },
        )

        self.assertEqual(response.status_code, 403)
        self.assertContains(response, "Abrir login", status_code=403)
        self.assertContains(response, "Nenhuma altera", status_code=403)
        self.assertNotContains(response, "CSRF token from POST incorrect", status_code=403)
