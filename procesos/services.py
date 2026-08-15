from auditlog.context import set_actor
from django.db.models import Max

from procesos.models import Proceso, Requisito, VersionDocumental


def _confirmar_transicion(proceso: Proceso, usuario) -> Proceso:
    with set_actor(usuario):
        proceso.save()
    return proceso


def iniciar_evaluacion(proceso: Proceso, usuario) -> Proceso:
    proceso.iniciar_evaluacion()
    return _confirmar_transicion(proceso, usuario)


def descartar(proceso: Proceso, usuario, motivo: str) -> Proceso:
    proceso.descartar(motivo)
    return _confirmar_transicion(proceso, usuario)


def marcar_apto(proceso: Proceso, usuario) -> Proceso:
    proceso.marcar_apto()
    return _confirmar_transicion(proceso, usuario)


def iniciar_preparacion(proceso: Proceso, usuario) -> Proceso:
    proceso.iniciar_preparacion()
    return _confirmar_transicion(proceso, usuario)


def presentar(proceso: Proceso, usuario) -> Proceso:
    proceso.presentar()
    return _confirmar_transicion(proceso, usuario)


def adjudicar(proceso: Proceso, usuario) -> Proceso:
    proceso.adjudicar()
    return _confirmar_transicion(proceso, usuario)


def perder(proceso: Proceso, usuario) -> Proceso:
    proceso.perder()
    return _confirmar_transicion(proceso, usuario)


def suspender(proceso: Proceso, usuario) -> Proceso:
    proceso.suspender()
    return _confirmar_transicion(proceso, usuario)


def crear_version(proceso: Proceso, tipo: str, fecha=None) -> VersionDocumental:
    """Crea la siguiente versión documental del proceso. `secuencia` se
    calcula sola: 0 para el documento inicial, +1 por cada versión posterior."""
    ultima = proceso.versiones.aggregate(Max("secuencia"))["secuencia__max"]
    siguiente_secuencia = 0 if ultima is None else ultima + 1
    return VersionDocumental.objects.create(
        proceso=proceso, tipo=tipo, secuencia=siguiente_secuencia, fecha_publicacion=fecha,
    )


def derogar_requisito(
    requisito_viejo: Requisito, datos_nuevos: dict, version: VersionDocumental,
) -> Requisito:
    """Crea un requisito nuevo que deroga `requisito_viejo`. Nunca modifica el
    viejo: los `Requisito` son inmutables (ver invariante 1 de CLAUDE.md)."""
    return Requisito.objects.create(
        proceso=requisito_viejo.proceso,
        version_origen=version,
        reemplaza=requisito_viejo,
        **datos_nuevos,
    )


def requisitos_vigentes_en(proceso: Proceso, version: VersionDocumental):
    """Requisitos vigentes tal como estaban publicados en `version`: los
    introducidos hasta esa versión (inclusive) que ninguna versión hasta esa
    misma versión haya derogado. Permite reconstruir el estado histórico del
    pliego en cualquier punto de la secuencia."""
    return Requisito.objects.filter(
        proceso=proceso, version_origen__secuencia__lte=version.secuencia,
    ).exclude(
        reemplazado_por__version_origen__secuencia__lte=version.secuencia,
    )
