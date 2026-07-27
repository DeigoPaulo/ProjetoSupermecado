from django.apps import AppConfig


class EstoqueConfig(AppConfig):
    name = "apps.estoque"

    def ready(self):
        from . import signals  # noqa: F401