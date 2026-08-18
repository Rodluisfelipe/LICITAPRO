from django.urls import path

from core import views

app_name = "core"

urlpatterns = [
    path("entidades/", views.entidades, name="entidades"),
    path("entidades/autocompletar/", views.entidades_autocompletar, name="entidades_autocompletar"),
    path("entidades/seleccionar/", views.entidades_seleccionar, name="entidades_seleccionar"),
    path("preferencias/", views.actualizar_preferencias, name="actualizar_preferencias"),
]
