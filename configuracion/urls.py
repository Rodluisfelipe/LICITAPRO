from django.urls import path

from configuracion import views

app_name = "configuracion"

urlpatterns = [
    path("perfiles/", views.perfiles_lista, name="perfiles_lista"),
    path("perfiles/nuevo/", views.perfil_crear, name="perfil_crear"),
    path("perfiles/<int:pk>/", views.perfil_detalle, name="perfil_detalle"),
    path("perfiles/<int:pk>/eliminar/", views.perfil_eliminar, name="perfil_eliminar"),
    path(
        "perfiles/<int:pk>/usuarios/agregar/",
        views.perfil_agregar_usuario,
        name="perfil_agregar_usuario",
    ),
    path(
        "perfiles/<int:pk>/usuarios/<int:usuario_id>/quitar/",
        views.perfil_quitar_usuario,
        name="perfil_quitar_usuario",
    ),
    path("usuarios/", views.usuarios_lista, name="usuarios_lista"),
    path("usuarios/<int:pk>/perfil/", views.usuario_cambiar_perfil, name="usuario_cambiar_perfil"),
    path("usuarios/<int:pk>/activo/", views.usuario_alternar_activo, name="usuario_alternar_activo"),
]
