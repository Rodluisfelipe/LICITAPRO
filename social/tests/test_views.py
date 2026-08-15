import pytest

from core.tests.factories import UsuarioFactory
from procesos.tests.factories import ProcesoFactory
from social.models import Actividad, Comentario


@pytest.mark.django_db
def test_comentar_crea_comentario_y_devuelve_fragmento(client):
    proceso = ProcesoFactory()
    autor = UsuarioFactory()
    client.force_login(autor)

    respuesta = client.post(f"/social/procesos/{proceso.pk}/comentarios/", {"cuerpo": "Todo listo"})

    assert respuesta.status_code == 200
    assert Comentario.objects.filter(proceso=proceso, autor=autor, cuerpo="Todo listo").exists()
    assert b"Todo listo" in respuesta.content


@pytest.mark.django_db
def test_comentar_vacio_devuelve_400_y_no_crea_nada(client):
    proceso = ProcesoFactory()
    client.force_login(UsuarioFactory())

    respuesta = client.post(f"/social/procesos/{proceso.pk}/comentarios/", {"cuerpo": "   "})

    assert respuesta.status_code == 400
    assert not Comentario.objects.exists()


@pytest.mark.django_db
def test_crear_actividad_programa_seguimiento(client):
    proceso = ProcesoFactory()
    asignado = UsuarioFactory(activo_comercial=True)
    client.force_login(UsuarioFactory())

    respuesta = client.post(
        f"/social/procesos/{proceso.pk}/actividades/",
        {
            "tipo": Actividad.Tipo.LLAMADA,
            "titulo": "Llamar a la entidad",
            "vence_en": "2026-09-01T10:00",
            "asignado_a": asignado.pk,
            "notas": "",
        },
    )

    assert respuesta.status_code == 302
    assert Actividad.objects.filter(proceso=proceso, titulo="Llamar a la entidad").exists()
