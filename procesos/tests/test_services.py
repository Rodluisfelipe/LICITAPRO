import pytest
from django_fsm import TransitionNotAllowed

from core.tests.factories import UsuarioFactory
from procesos import services
from procesos.models import Proceso, Requisito, VersionDocumental
from procesos.tests.factories import ProcesoFactory, RequisitoFactory, VersionDocumentalFactory


@pytest.mark.django_db
def test_transicion_invalida_lanza_transitionnotallowed():
    proceso = ProcesoFactory()  # estado por defecto: DETECTADO
    usuario = UsuarioFactory()

    with pytest.raises(TransitionNotAllowed):
        services.presentar(proceso, usuario)


@pytest.mark.django_db
def test_descartar_guarda_motivo():
    proceso = ProcesoFactory()  # estado por defecto: DETECTADO
    usuario = UsuarioFactory()

    services.descartar(proceso, usuario, motivo="Presupuesto insuficiente para la empresa.")

    # FSMField(protected=True) no admite refresh_from_db() sobre la misma
    # instancia: su descriptor bloquea el setattr interno. Se relee aparte.
    proceso_guardado = Proceso.objects.get(pk=proceso.pk)
    assert proceso_guardado.estado == Proceso.Estado.DESCARTADO
    assert proceso_guardado.motivo_descarte == "Presupuesto insuficiente para la empresa."


@pytest.mark.django_db
def test_crear_version_calcula_secuencia_siguiente():
    proceso = ProcesoFactory()

    v1 = services.crear_version(proceso, tipo=VersionDocumental.Tipo.DEFINITIVO)
    v2 = services.crear_version(proceso, tipo=VersionDocumental.Tipo.ADENDA)

    assert v1.secuencia == 0
    assert v2.secuencia == 1


@pytest.mark.django_db
def test_requisito_derogado_no_aparece_en_requisitos_vigentes():
    proceso = ProcesoFactory()
    v1 = VersionDocumentalFactory(proceso=proceso, secuencia=0)
    v2 = VersionDocumentalFactory(proceso=proceso, secuencia=1)
    viejo = RequisitoFactory(proceso=proceso, version_origen=v1, descripcion="Umbral original")

    nuevo = services.derogar_requisito(
        viejo, {"tipo": viejo.tipo, "numeral": viejo.numeral, "descripcion": "Umbral corregido"}, v2,
    )

    vigentes = list(proceso.requisitos_vigentes)
    assert nuevo in vigentes
    assert viejo not in vigentes
    # el viejo sigue existiendo en la base, solo dejó de estar vigente
    assert Requisito.objects.filter(pk=viejo.pk).exists()


@pytest.mark.django_db
def test_requisitos_vigentes_en_version_1_devuelve_el_requisito_viejo():
    proceso = ProcesoFactory()
    v1 = VersionDocumentalFactory(proceso=proceso, secuencia=0)
    v2 = VersionDocumentalFactory(proceso=proceso, secuencia=1)
    viejo = RequisitoFactory(proceso=proceso, version_origen=v1)

    nuevo = services.derogar_requisito(
        viejo, {"tipo": viejo.tipo, "numeral": viejo.numeral, "descripcion": "Nueva versión"}, v2,
    )

    vigentes_en_v1 = list(services.requisitos_vigentes_en(proceso, v1))
    vigentes_en_v2 = list(services.requisitos_vigentes_en(proceso, v2))

    assert vigentes_en_v1 == [viejo]
    assert vigentes_en_v2 == [nuevo]


@pytest.mark.django_db
def test_declarar_desierto_desde_presentado():
    proceso = ProcesoFactory(estado=Proceso.Estado.DETECTADO)
    usuario = UsuarioFactory()
    proceso.iniciar_evaluacion()
    proceso.marcar_apto()
    proceso.iniciar_preparacion()
    proceso.presentar()
    proceso.save()

    services.declarar_desierto(proceso, usuario)

    assert Proceso.objects.get(pk=proceso.pk).estado == Proceso.Estado.DESIERTO


@pytest.mark.django_db
def test_estado_disponible_marca_solo_la_transicion_inmediata_como_alcanzable():
    # Desde EN_EVALUACION la FSM solo permite un paso: apto o descartado.
    # presentado/adjudicado deben verse como futuro, no como alcanzables.
    proceso = ProcesoFactory(estado=Proceso.Estado.DETECTADO)
    proceso.iniciar_evaluacion()
    proceso.save()

    estado_ui = services.estado_disponible(proceso)

    etapas_por_valor = {etapa["valor"]: etapa for etapa in estado_ui["pipeline"]}
    assert etapas_por_valor["apto"]["transicion"] == "marcar_apto"
    assert etapas_por_valor["presentado"]["transicion"] is None
    assert etapas_por_valor["detectado"]["completada"] is True
    assert {lateral["transicion"] for lateral in estado_ui["laterales"]} == {
        "descartar",
        "suspender",
    }


@pytest.mark.django_db
def test_verificar_fechas_registra_usuario_y_momento():
    proceso = ProcesoFactory()
    usuario = UsuarioFactory()

    services.verificar_fechas(proceso, usuario)

    proceso_guardado = Proceso.objects.get(pk=proceso.pk)
    assert proceso_guardado.fechas_verificadas_por == usuario
    assert proceso_guardado.fechas_verificadas_en is not None


@pytest.mark.django_db
def test_encadenar_tres_versiones_deja_un_solo_requisito_vigente():
    proceso = ProcesoFactory()
    v1 = VersionDocumentalFactory(proceso=proceso, secuencia=0)
    v2 = VersionDocumentalFactory(proceso=proceso, secuencia=1)
    v3 = VersionDocumentalFactory(proceso=proceso, secuencia=2)

    r1 = RequisitoFactory(proceso=proceso, version_origen=v1, numeral="3.1")
    r2 = services.derogar_requisito(
        r1, {"tipo": r1.tipo, "numeral": r1.numeral, "descripcion": "Segunda versión"}, v2,
    )
    r3 = services.derogar_requisito(
        r2, {"tipo": r2.tipo, "numeral": r2.numeral, "descripcion": "Tercera versión"}, v3,
    )

    vigentes = list(proceso.requisitos_vigentes)
    assert vigentes == [r3]
    assert Requisito.objects.filter(proceso=proceso).count() == 3


@pytest.mark.django_db
def test_procesos_con_metricas_riesgo_rango_no_se_confunde_con_orden_alfabetico():
    from procesos.tests.factories import RiesgoFactory

    # "alta" < "baja" < "media" alfabéticamente, así que un Max() ingenuo
    # sobre el CharField reportaría "media" como el peor cuando en
    # realidad "alta" es más severo. riesgo_rango debe devolver 3 (alta).
    proceso = ProcesoFactory()
    RiesgoFactory(proceso=proceso, severidad="media")
    RiesgoFactory(proceso=proceso, severidad="alta")

    resultado = services.procesos_con_metricas().get(pk=proceso.pk)

    assert resultado.riesgo_rango == 3


@pytest.mark.django_db
def test_procesos_con_metricas_ignora_riesgo_descartado_por_usuario():
    from procesos.tests.factories import RiesgoFactory

    proceso = ProcesoFactory()
    RiesgoFactory(proceso=proceso, severidad="alta", descartado_por_usuario=True)

    resultado = services.procesos_con_metricas().get(pk=proceso.pk)

    assert resultado.riesgo_rango in (0, None)


@pytest.mark.django_db
def test_procesos_con_metricas_cuenta_cumplimiento_de_requisitos_vigentes():
    proceso = ProcesoFactory()
    v1 = VersionDocumentalFactory(proceso=proceso, secuencia=0)
    RequisitoFactory(proceso=proceso, version_origen=v1, cumplimiento=Requisito.Cumplimiento.CUMPLE)
    RequisitoFactory(proceso=proceso, version_origen=v1, cumplimiento=Requisito.Cumplimiento.CUMPLE)
    RequisitoFactory(
        proceso=proceso, version_origen=v1, cumplimiento=Requisito.Cumplimiento.POR_VERIFICAR,
    )
    RequisitoFactory(proceso=proceso, version_origen=v1, cumplimiento=Requisito.Cumplimiento.NO_APLICA)

    resultado = services.procesos_con_metricas().get(pk=proceso.pk)

    assert resultado.req_cumple == 2
    assert resultado.req_pendiente == 1
    # no_aplica no cuenta en el total: 2 cumple + 1 pendiente = 3, no 4.
    assert resultado.req_total == 3
