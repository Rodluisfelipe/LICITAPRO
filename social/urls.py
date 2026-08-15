from django.urls import path

from social import views

app_name = "social"

urlpatterns = [
    path("usuarios/autocompletar/", views.autocompletar_usuarios, name="autocompletar_usuarios"),
    path("procesos/<uuid:proceso_id>/comentarios/", views.comentar, name="comentar"),
    path("procesos/<uuid:proceso_id>/actividades/", views.crear_actividad, name="crear_actividad"),
]
