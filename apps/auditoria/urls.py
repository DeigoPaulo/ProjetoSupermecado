from django.urls import path

from . import views

app_name = "auditoria"

urlpatterns = [
    path("", views.logs, name="logs"),
    path("exportar.csv", views.logs_csv, name="logs_csv"),
]
