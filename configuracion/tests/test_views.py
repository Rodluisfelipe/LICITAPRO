import pytest
from django.contrib.auth.models import Group

from core.tests.factories import UsuarioFactory, usuario_comercial
from procesos.permisos import PERFILES_DE_ARRANQUE


def _admin():
    usuario = UsuarioFactory()
    usuario.groups.add(Group.objects.get(name="Administrador"))
    return usuario


@pytest.mark.django_db
def test_perfiles_lista_muestra_los_tres_de_arranque(client):
    client.force_login(_admin())

    respuesta = client.get("/configuracion/perfiles/")

    assert respuesta.status_code == 200
    nombres = {fila["grupo"].name for fila in respuesta.context["filas"]}
    assert nombres == set(PERFILES_DE_ARRANQUE)


@pytest.mark.django_db
def test_crear_perfil_desde_la_interfaz(client):
    client.force_login(_admin())

    respuesta = client.post(
        "/configuracion/perfiles/nuevo/",
        {
            "nombre": "Auditoría",
            "descripcion": "Solo lectura para el equipo de auditoría externa.",
            "permisos": ["ver_procesos"],
        },
    )

    assert respuesta.status_code == 302
    grupo = Group.objects.get(name="Auditoría")
    assert grupo.info.descripcion == "Solo lectura para el equipo de auditoría externa."
    assert list(grupo.permissions.values_list("codename", flat=True)) == ["ver_procesos"]


@pytest.mark.django_db
def test_editar_perfil_quita_un_permiso(client):
    client.force_login(_admin())
    grupo = Group.objects.get(name="Comercial")
    permisos_antes = list(grupo.permissions.values_list("codename", flat=True))
    assert "mover_etapa" in permisos_antes

    permisos_sin_mover = [p for p in permisos_antes if p != "mover_etapa"]
    respuesta = client.post(
        f"/configuracion/perfiles/{grupo.pk}/",
        {"nombre": "Comercial", "descripcion": "", "permisos": permisos_sin_mover},
    )

    assert respuesta.status_code == 302
    grupo.refresh_from_db()
    assert "mover_etapa" not in grupo.permissions.values_list("codename", flat=True)


@pytest.mark.django_db
def test_no_se_puede_eliminar_un_perfil_de_arranque(client):
    client.force_login(_admin())
    grupo = Group.objects.get(name="Consulta")

    respuesta = client.post(f"/configuracion/perfiles/{grupo.pk}/eliminar/")

    assert respuesta.status_code == 302
    assert Group.objects.filter(pk=grupo.pk).exists()


@pytest.mark.django_db
def test_no_se_puede_eliminar_un_perfil_con_usuarios_asignados(client):
    client.force_login(_admin())
    grupo = Group.objects.create(name="Con gente")
    usuario_comercial().groups.add(grupo)

    respuesta = client.post(f"/configuracion/perfiles/{grupo.pk}/eliminar/")

    assert respuesta.status_code == 302
    assert Group.objects.filter(pk=grupo.pk).exists()


@pytest.mark.django_db
def test_eliminar_perfil_vacio_y_no_de_arranque_funciona(client):
    client.force_login(_admin())
    grupo = Group.objects.create(name="Vacío")

    respuesta = client.post(f"/configuracion/perfiles/{grupo.pk}/eliminar/")

    assert respuesta.status_code == 302
    assert not Group.objects.filter(pk=grupo.pk).exists()


@pytest.mark.django_db
def test_agregar_y_quitar_usuario_de_un_perfil(client):
    client.force_login(_admin())
    grupo = Group.objects.get(name="Consulta")
    usuario = UsuarioFactory()

    respuesta = client.post(
        f"/configuracion/perfiles/{grupo.pk}/usuarios/agregar/", {"usuario_id": usuario.pk},
    )
    assert respuesta.status_code == 302
    assert grupo in usuario.groups.all()

    respuesta = client.post(f"/configuracion/perfiles/{grupo.pk}/usuarios/{usuario.pk}/quitar/")
    assert respuesta.status_code == 302
    usuario.refresh_from_db()
    assert grupo not in usuario.groups.all()


@pytest.mark.django_db
def test_usuario_cambiar_perfil_via_htmx(client):
    client.force_login(_admin())
    usuario = UsuarioFactory()
    grupo = Group.objects.get(name="Comercial")

    respuesta = client.post(
        f"/configuracion/usuarios/{usuario.pk}/perfil/", {"grupo_id": grupo.pk},
    )

    assert respuesta.status_code == 200
    usuario.refresh_from_db()
    assert list(usuario.groups.all()) == [grupo]


@pytest.mark.django_db
def test_admin_no_puede_quitarse_a_si_mismo_gestionar_usuarios_por_perfil_unico(client):
    admin = _admin()
    client.force_login(admin)
    grupo_sin_gestion = Group.objects.get(name="Comercial")

    respuesta = client.post(
        f"/configuracion/usuarios/{admin.pk}/perfil/", {"grupo_id": grupo_sin_gestion.pk},
    )

    assert respuesta.status_code == 200
    admin.refresh_from_db()
    # Sigue en Administrador — el cambio se rechazó.
    assert admin.groups.filter(name="Administrador").exists()


@pytest.mark.django_db
def test_admin_no_puede_quitarse_a_si_mismo_de_su_unico_grupo_con_gestion(client):
    admin = _admin()
    client.force_login(admin)
    grupo_admin = Group.objects.get(name="Administrador")

    respuesta = client.post(
        f"/configuracion/perfiles/{grupo_admin.pk}/usuarios/{admin.pk}/quitar/",
    )

    assert respuesta.status_code == 302
    admin.refresh_from_db()
    assert grupo_admin in admin.groups.all()


@pytest.mark.django_db
def test_desactivar_y_reactivar_un_usuario(client):
    client.force_login(_admin())
    usuario = usuario_comercial()
    assert usuario.is_active is True

    respuesta = client.post(f"/configuracion/usuarios/{usuario.pk}/activo/")
    assert respuesta.status_code == 302
    usuario.refresh_from_db()
    assert usuario.is_active is False

    respuesta = client.post(f"/configuracion/usuarios/{usuario.pk}/activo/")
    usuario.refresh_from_db()
    assert usuario.is_active is True


@pytest.mark.django_db
def test_comercial_recibe_403_en_todo_configuracion(client):
    client.force_login(usuario_comercial())  # Comercial no tiene gestionar_usuarios

    assert client.get("/configuracion/perfiles/").status_code == 403
    assert client.get("/configuracion/usuarios/").status_code == 403
