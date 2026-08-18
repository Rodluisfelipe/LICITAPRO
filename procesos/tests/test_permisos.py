import pytest
from django.contrib.auth.models import Group, Permission

from core.tests.factories import UsuarioFactory, usuario_comercial
from procesos import services
from procesos.models import Proceso
from procesos.permisos import crear_perfiles_de_arranque
from procesos.tests.factories import ProcesoFactory


def _usuario_consulta():
    """El perfil Consulta trae `ver_todos` a propósito (según el
    contrato: "Consulta ve_procesos y ver_todos" — es de solo lectura de
    TODO el equipo, no de "solo lo mío"). Para ver/mover, no para ambas."""
    usuario = UsuarioFactory()
    usuario.groups.add(Group.objects.get(name="Consulta"))
    return usuario


def _usuario_sin_ver_todos():
    """Solo ver_procesos, sin ver_todos ni ningún perfil de arranque —
    para aislar el comportamiento de alcance por responsable/seguidor."""
    usuario = UsuarioFactory()
    usuario.user_permissions.add(
        Permission.objects.get(codename="ver_procesos", content_type__app_label="procesos"),
    )
    return usuario


@pytest.mark.django_db
def test_consulta_recibe_403_en_transicionar_proceso(client):
    proceso = ProcesoFactory(estado=Proceso.Estado.DETECTADO)
    client.force_login(_usuario_consulta())

    respuesta = client.post(f"/procesos/{proceso.pk}/transicion/iniciar_evaluacion/")

    assert respuesta.status_code == 403
    assert Proceso.objects.get(pk=proceso.pk).estado == Proceso.Estado.DETECTADO


@pytest.mark.django_db
def test_consulta_recibe_403_en_mover_kanban(client):
    """Prueba explícita de que la protección no es solo visual: un POST
    directo al endpoint, sin pasar por el drag&drop, también se rechaza."""
    proceso = ProcesoFactory(estado=Proceso.Estado.DETECTADO)
    client.force_login(_usuario_consulta())

    respuesta = client.post(f"/procesos/{proceso.pk}/mover/en_evaluacion/")

    assert respuesta.status_code == 403
    assert Proceso.objects.get(pk=proceso.pk).estado == Proceso.Estado.DETECTADO


@pytest.mark.django_db
def test_sin_ver_todos_procesos_con_metricas_devuelve_solo_los_propios():
    usuario = _usuario_sin_ver_todos()
    propio = ProcesoFactory(responsable=usuario)
    seguido = ProcesoFactory()
    seguido.seguidores.add(usuario)
    ajeno = ProcesoFactory()

    visibles = set(services.procesos_con_metricas(usuario=usuario).values_list("pk", flat=True))

    assert visibles == {propio.pk, seguido.pk}
    assert ajeno.pk not in visibles


@pytest.mark.django_db
def test_con_ver_todos_procesos_con_metricas_devuelve_todo():
    usuario = usuario_comercial()  # Comercial incluye ver_todos
    ProcesoFactory()
    ProcesoFactory()

    assert services.procesos_con_metricas(usuario=usuario).count() == 2


@pytest.mark.django_db
def test_sin_ver_todos_detalle_de_proceso_ajeno_da_404(client):
    usuario = _usuario_sin_ver_todos()
    ajeno = ProcesoFactory()  # ni responsable ni seguidor de `usuario`
    client.force_login(usuario)

    respuesta = client.get(f"/procesos/{ajeno.pk}/")

    assert respuesta.status_code == 404


@pytest.mark.django_db
def test_sin_ver_todos_detalle_de_proceso_propio_funciona(client):
    usuario = _usuario_sin_ver_todos()
    propio = ProcesoFactory(responsable=usuario)
    client.force_login(usuario)

    respuesta = client.get(f"/procesos/{propio.pk}/")

    assert respuesta.status_code == 200


@pytest.mark.django_db
def test_sin_gestionar_usuarios_get_a_configuracion_perfiles_da_403(client):
    client.force_login(usuario_comercial())  # Comercial no tiene gestionar_usuarios

    respuesta = client.get("/configuracion/perfiles/")

    assert respuesta.status_code == 403


@pytest.mark.django_db
def test_crear_perfiles_de_arranque_es_idempotente():
    crear_perfiles_de_arranque()
    grupo = Group.objects.get(name="Comercial")
    permisos_originales = set(grupo.permissions.values_list("codename", flat=True))

    # Un administrador personaliza el perfil desde la interfaz después...
    grupo.permissions.remove(*grupo.permissions.filter(codename="mover_etapa"))

    # ...y la migración/función se vuelve a llamar (re-deploy, test suite
    # que la ejecuta de nuevo, etc.) — no debe pisar la personalización.
    crear_perfiles_de_arranque()

    grupo.refresh_from_db()
    permisos_despues = set(grupo.permissions.values_list("codename", flat=True))
    assert permisos_despues == permisos_originales - {"mover_etapa"}
    assert Group.objects.filter(name="Comercial").count() == 1


@pytest.mark.django_db
def test_administrador_no_puede_desactivarse_a_si_mismo(client):
    admin = UsuarioFactory()
    admin.groups.add(Group.objects.get(name="Administrador"))
    client.force_login(admin)

    respuesta = client.post(f"/configuracion/usuarios/{admin.pk}/activo/")

    assert respuesta.status_code == 302
    admin.refresh_from_db()
    assert admin.is_active is True
