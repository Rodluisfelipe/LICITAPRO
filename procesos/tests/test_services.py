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
