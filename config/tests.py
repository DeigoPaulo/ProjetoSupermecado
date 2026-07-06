from django.test import SimpleTestCase

from . import settings


class MediaUrlsTests(SimpleTestCase):
    def test_media_url_usa_caminho_absoluto(self):
        self.assertEqual(settings.MEDIA_URL, "/media/")
