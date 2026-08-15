import pytest

from core.tests.factories import UsuarioFactory
from procesos.tests.factories import ProcesoFactory
from social import services
from social.models import Alerta, Comentario


@pytest.mark.django_db
def test_publicar_comentario_con_mencion_crea_alerta_al_destinatario():
    proceso = ProcesoFactory()
    autor = UsuarioFactory(username="ana")
    mencionado = UsuarioFactory(username="carlos")

    comentario = services.publicar_comentario(proceso, autor, "Revisa esto @carlos por favor")

    assert comentario.menciones.get() == mencionado
    alerta = Alerta.objects.get()
    assert alerta.destinatario == mencionado
    assert alerta.tipo == Alerta.Tipo.MENCION
    assert alerta.proceso == proceso


@pytest.mark.django_db
def test_publicar_comentario_no_crea_alerta_por_automencion_ni_usuario_inexistente():
    proceso = ProcesoFactory()
    autor = UsuarioFactory(username="ana")

    comentario = services.publicar_comentario(
        proceso,
        autor,
        "Nota para mí @ana, y @nadie_existe también",
    )

    assert comentario.menciones.count() == 0
    assert not Alerta.objects.exists()
    assert Comentario.objects.filter(pk=comentario.pk).exists()
