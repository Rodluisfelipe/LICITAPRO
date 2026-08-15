from django.urls import path

from core import views

app_name = "core"

urlpatterns = [
    path("entidades/", views.entidades, name="entidades"),
    path("entidades/autocompletar/", views.entidades_autocompletar, name="entidades_autocompletar"),
]
