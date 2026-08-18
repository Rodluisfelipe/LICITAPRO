import pytest

from core.tests.factories import EntidadFactory, UsuarioFactory, usuario_comercial
from procesos.models import Proceso
from procesos.tests.factories import ProcesoFactory


@pytest.mark.django_db
def test_lista_procesos_filtra_por_estado(client):
    client.force_login(usuario_comercial())
    entidad = EntidadFactory()
    detectado = ProcesoFactory(entidad=entidad, estado=Proceso.Estado.DETECTADO)
    apto = ProcesoFactory(entidad=entidad)
    apto.iniciar_evaluacion()
    apto.marcar_apto()
    apto.save()

    respuesta = client.get("/procesos/", {"vista": "lista", "estado": Proceso.Estado.APTO})

    assert respuesta.status_code == 200
    procesos_en_pagina = list(respuesta.context["pagina"].object_list)
    assert procesos_en_pagina == [apto]
    assert detectado not in procesos_en_pagina


@pytest.mark.django_db
def test_orden_invalido_en_querystring_no_rompe_y_usa_default(client):
    client.force_login(usuario_comercial())
    ProcesoFactory()

    respuesta = client.get(
        "/procesos/", {"vista": "lista", "orden": "objeto; DROP TABLE procesos_proceso;"},
    )

    assert respuesta.status_code == 200
    assert respuesta.context["orden"] == "-fecha_cierre"


@pytest.mark.django_db
def test_detalle_proceso_renderiza_statusbar_form_tabs_y_chatter(client):
    from social.tests.factories import ActividadFactory, ComentarioFactory

    proceso = ProcesoFactory(numero_proceso="PROC-9999")
    ComentarioFactory(proceso=proceso, cuerpo="Un comentario visible en el chatter")
    ActividadFactory(proceso=proceso, titulo="Actividad visible en la pestaña")
    client.force_login(usuario_comercial())

    respuesta = client.get(f"/procesos/{proceso.pk}/")

    assert respuesta.status_code == 200
    contenido = respuesta.content.decode()
    assert "Un comentario visible en el chatter" in contenido
    assert "Actividad visible en la pestaña" in contenido
    assert "PROC-9999" in contenido


@pytest.mark.django_db
def test_transicion_valida_desde_el_statusbar_avanza_el_estado(client):
    proceso = ProcesoFactory(estado=Proceso.Estado.DETECTADO)
    client.force_login(usuario_comercial())

    respuesta = client.post(f"/procesos/{proceso.pk}/transicion/iniciar_evaluacion/")

    assert respuesta.status_code == 302
    proceso_guardado = Proceso.objects.get(pk=proceso.pk)
    assert proceso_guardado.estado == Proceso.Estado.EN_EVALUACION


@pytest.mark.django_db
def test_transicion_no_disponible_no_rompe_y_deja_el_estado_intacto(client):
    # detectado -> presentar no es una transición válida (hay que pasar por
    # evaluación, apto, preparación primero). El servicio debe absorber el
    # TransitionNotAllowed en vez de tumbar la vista con un 500.
    proceso = ProcesoFactory(estado=Proceso.Estado.DETECTADO)
    client.force_login(usuario_comercial())

    respuesta = client.post(f"/procesos/{proceso.pk}/transicion/presentar/")

    assert respuesta.status_code == 302
    assert Proceso.objects.get(pk=proceso.pk).estado == Proceso.Estado.DETECTADO


@pytest.mark.django_db
def test_transicion_desconocida_devuelve_400(client):
    proceso = ProcesoFactory()
    client.force_login(UsuarioFactory())

    respuesta = client.post(f"/procesos/{proceso.pk}/transicion/eliminar_todo/")

    assert respuesta.status_code == 400


@pytest.mark.django_db
def test_descartar_desde_statusbar_guarda_motivo_enviado_por_post(client):
    proceso = ProcesoFactory(estado=Proceso.Estado.DETECTADO)
    client.force_login(usuario_comercial())

    respuesta = client.post(
        f"/procesos/{proceso.pk}/transicion/descartar/", {"motivo": "No cumplimos experiencia"},
    )

    assert respuesta.status_code == 302
    proceso_guardado = Proceso.objects.get(pk=proceso.pk)
    assert proceso_guardado.estado == Proceso.Estado.DESCARTADO
    assert proceso_guardado.motivo_descarte == "No cumplimos experiencia"


@pytest.mark.django_db
def test_verificar_fechas_llena_por_y_en(client):
    proceso = ProcesoFactory()
    usuario = usuario_comercial()
    client.force_login(usuario)
    assert proceso.fechas_verificadas_por is None

    respuesta = client.post(f"/procesos/{proceso.pk}/verificar-fechas/")

    assert respuesta.status_code == 302
    proceso_guardado = Proceso.objects.get(pk=proceso.pk)
    assert proceso_guardado.fechas_verificadas_por == usuario
    assert proceso_guardado.fechas_verificadas_en is not None


@pytest.mark.django_db
def test_procesos_sin_vista_en_querystring_muestra_kanban_por_defecto(client):
    client.force_login(usuario_comercial())
    ProcesoFactory(estado=Proceso.Estado.DETECTADO)

    respuesta = client.get("/procesos/")

    assert respuesta.status_code == 200
    assert "columnas" in respuesta.context
    assert "pagina" not in respuesta.context


@pytest.mark.django_db
def test_kanban_agrupa_procesos_por_columna_de_estado(client):
    client.force_login(usuario_comercial())
    detectado = ProcesoFactory(estado=Proceso.Estado.DETECTADO)
    en_evaluacion = ProcesoFactory(estado=Proceso.Estado.DETECTADO)
    en_evaluacion.iniciar_evaluacion()
    en_evaluacion.save()

    respuesta = client.get("/procesos/?vista=kanban")

    columnas_por_valor = {c["valor"]: c for c in respuesta.context["columnas"]}
    assert detectado in columnas_por_valor["detectado"]["procesos"]
    assert en_evaluacion in columnas_por_valor["en_evaluacion"]["procesos"]
    assert detectado not in columnas_por_valor["en_evaluacion"]["procesos"]


@pytest.mark.django_db
def test_mover_kanban_ejecuta_la_transicion_valida(client):
    proceso = ProcesoFactory(estado=Proceso.Estado.DETECTADO)
    client.force_login(usuario_comercial())

    respuesta = client.post(f"/procesos/{proceso.pk}/mover/en_evaluacion/")

    assert respuesta.status_code == 200
    assert respuesta.json() == {"ok": True, "estado": "en_evaluacion"}
    assert Proceso.objects.get(pk=proceso.pk).estado == Proceso.Estado.EN_EVALUACION


@pytest.mark.django_db
def test_mover_kanban_a_columna_invalida_no_cambia_el_estado(client):
    # detectado -> presentado no es una transición directa de la FSM.
    proceso = ProcesoFactory(estado=Proceso.Estado.DETECTADO)
    client.force_login(UsuarioFactory())

    respuesta = client.post(f"/procesos/{proceso.pk}/mover/presentado/")

    assert respuesta.status_code == 409
    assert respuesta.json()["ok"] is False
    assert Proceso.objects.get(pk=proceso.pk).estado == Proceso.Estado.DETECTADO
