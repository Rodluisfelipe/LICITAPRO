import pytest
from django.contrib.auth.models import Group, Permission

from core.models import Entidad, Origen
from core.tests.factories import EntidadFactory, UsuarioFactory, usuario_comercial
from procesos.models import Proceso
from procesos.tests.factories import ProcesoFactory


def _usuario_solo_crear_procesos():
    """crear_procesos sin gestionar_entidades — Comercial trae ambos, así
    que para aislar la exigencia de gestionar_entidades hace falta un
    usuario con un permiso suelto, sin perfil de arranque."""
    usuario = UsuarioFactory()
    usuario.user_permissions.add(
        Permission.objects.get(codename="crear_procesos", content_type__app_label="procesos"),
    )
    return usuario


@pytest.mark.django_db
def test_crear_proceso_sin_permiso_da_403(client):
    client.force_login(UsuarioFactory())

    respuesta = client.get("/procesos/nuevo/")

    assert respuesta.status_code == 403


@pytest.mark.django_db
def test_crear_proceso_con_permiso_entra_con_origen_manual_y_sin_fechas_verificadas(client):
    entidad = EntidadFactory()
    client.force_login(usuario_comercial())

    respuesta = client.post("/procesos/nuevo/", data={
        "objeto": "Interventoría de obra vial",
        "entidad": entidad.pk,
        "numero_proceso": "PROC-0001",
        "modalidad": Proceso.Modalidad.LICITACION,
        "moneda": "COP",
    })

    proceso = Proceso.objects.get(numero_proceso="PROC-0001")
    assert respuesta.status_code == 302
    assert respuesta.url == f"/procesos/{proceso.pk}/"
    assert proceso.origen == Origen.MANUAL
    assert proceso.estado == Proceso.Estado.DETECTADO
    assert proceso.fechas_verificadas_por is None


@pytest.mark.django_db
def test_crear_proceso_con_entidad_nueva_requiere_gestionar_entidades(client):
    """Un usuario con crear_procesos pero sin gestionar_entidades no puede
    colar una entidad nueva por el formulario: sin entidad seleccionada,
    el proceso no se crea."""
    client.force_login(_usuario_solo_crear_procesos())

    respuesta = client.post("/procesos/nuevo/", data={
        "objeto": "Suministro de dotación",
        "numero_proceso": "PROC-0002",
        "modalidad": Proceso.Modalidad.MINIMA_CUANTIA,
        "moneda": "COP",
        "nueva_entidad-nombre": "Entidad Colada",
        "nueva_entidad-nit": "900123456-1",
    })

    assert respuesta.status_code == 200
    assert not Proceso.objects.filter(numero_proceso="PROC-0002").exists()
    assert not Entidad.objects.filter(nombre="Entidad Colada").exists()


@pytest.mark.django_db
def test_crear_proceso_con_gestionar_entidades_crea_entidad_en_linea(client):
    usuario = UsuarioFactory()
    usuario.groups.add(Group.objects.get(name="Administrador"))
    client.force_login(usuario)

    respuesta = client.post("/procesos/nuevo/", data={
        "objeto": "Suministro de dotación",
        "numero_proceso": "PROC-0003",
        "modalidad": Proceso.Modalidad.MINIMA_CUANTIA,
        "moneda": "COP",
        "nueva_entidad-nombre": "Entidad Nueva SAS",
        "nueva_entidad-nit": "900987654-1",
        "nueva_entidad-orden": Entidad.Orden.MUNICIPAL,
    })

    proceso = Proceso.objects.get(numero_proceso="PROC-0003")
    entidad_creada = Entidad.objects.get(nombre="Entidad Nueva SAS")
    assert respuesta.status_code == 302
    assert proceso.entidad_id == entidad_creada.pk


@pytest.mark.django_db
def test_filtro_combinado_estado_y_entidad(client):
    entidad_buscada = EntidadFactory(nombre="Alcaldía de Prueba")
    coincide = ProcesoFactory(estado=Proceso.Estado.APTO, entidad=entidad_buscada)
    ProcesoFactory(estado=Proceso.Estado.APTO)
    ProcesoFactory(estado=Proceso.Estado.DETECTADO, entidad=entidad_buscada)
    client.force_login(usuario_comercial())

    respuesta = client.get(f"/procesos/?vista=lista&estado=apto&entidad={entidad_buscada.pk}")

    assert list(respuesta.context["pagina"].object_list) == [coincide]
