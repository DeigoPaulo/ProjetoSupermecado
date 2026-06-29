from django.urls import path

from . import views

app_name = "promocoes"

urlpatterns = [
    path("", views.PromocaoListView.as_view(), name="lista"),
    path("nova/", views.PromocaoCreateView.as_view(), name="nova"),
    path("<int:pk>/editar/", views.PromocaoUpdateView.as_view(), name="editar"),
]
