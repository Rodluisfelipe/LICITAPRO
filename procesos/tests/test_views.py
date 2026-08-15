import pytest

from core.tests.factories import EntidadFactory
from procesos.models import Proceso
from procesos.tests.factories import ProcesoFactory


@pytest.mark.django_db
def test_lista_procesos_filtra_por_estado(client):
    entidad = EntidadFactory()
    detectado = ProcesoFactory(entidad=entidad, estado=Proceso.Estado.DETECTADO)
    apto = ProcesoFactory(entidad=entidad)
    apto.iniciar_evaluacion()
    apto.marcar_apto()
    apto.save()

    respuesta = client.get("/procesos/", {"estado": Proceso.Estado.APTO})

    assert respuesta.status_code == 200
    procesos_en_pagina = list(respuesta.context["pagina"].object_list)
    assert procesos_en_pagina == [apto]
    assert detectado not in procesos_en_pagina


@pytest.mark.django_db
def test_orden_invalido_en_querystring_no_rompe_y_usa_default(client):
    ProcesoFactory()

    respuesta = client.get("/procesos/", {"orden": "objeto; DROP TABLE procesos_proceso;"})

    assert respuesta.status_code == 200
    assert respuesta.context["orden"] == "-fecha_cierre"
