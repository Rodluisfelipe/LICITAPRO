from auditlog.context import set_actor
from django.db.models import Case, Count, IntegerField, Max, Q, When
from django.utils import timezone

from procesos.models import Proceso, Requisito, VersionDocumental

TRANSICIONES_VALIDAS = {
    "iniciar_evaluacion",
    "descartar",
    "marcar_apto",
    "iniciar_preparacion",
    "presentar",
    "adjudicar",
    "perder",
    "declarar_desierto",
    "suspender",
}


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


def declarar_desierto(proceso: Proceso, usuario) -> Proceso:
    proceso.declarar_desierto()
    return _confirmar_transicion(proceso, usuario)


def suspender(proceso: Proceso, usuario) -> Proceso:
    proceso.suspender()
    return _confirmar_transicion(proceso, usuario)


def verificar_fechas(proceso: Proceso, usuario) -> Proceso:
    """Marca como verificadas por un humano las fechas y cifras críticas del
    proceso (invariante 3 de CLAUDE.md: fecha_cierre, presupuesto_oficial...).
    Es un solo par de campos para todo el proceso, no uno por campo."""
    proceso.fechas_verificadas_por = usuario
    proceso.fechas_verificadas_en = timezone.now()
    with set_actor(usuario):
        proceso.save()
    return proceso


def transiciones_disponibles(proceso: Proceso) -> dict[str, str]:
    """{estado_destino: nombre_transicion} alcanzables AHORA desde el estado
    actual, según la FSM. Pura introspección de `@transition` — no consulta
    la base de datos, así que es segura de llamar por cada tarjeta de un
    queryset ya materializado (kanban) sin romper el presupuesto de queries."""
    return {t.target: t.name for t in proceso.get_available_estado_transitions()}


def estado_disponible(proceso: Proceso) -> dict:
    """Compone los datos que necesita el statusbar: la posición del proceso
    en el camino feliz (`ETAPAS_PIPELINE`) y qué transiciones son alcanzables
    ahora mismo desde `estado`, según la FSM — no todo el resto del pipeline,
    solo el siguiente paso que la máquina de estados permite."""
    transiciones = transiciones_disponibles(proceso)

    try:
        posicion_actual = Proceso.ETAPAS_PIPELINE.index(proceso.estado)
    except ValueError:
        posicion_actual = None

    pipeline = [
        {
            "valor": valor,
            "etiqueta": Proceso.Estado(valor).label,
            "es_actual": valor == proceso.estado,
            "completada": posicion_actual is not None and indice < posicion_actual,
            "transicion": transiciones.get(valor),
        }
        for indice, valor in enumerate(Proceso.ETAPAS_PIPELINE)
    ]

    laterales = [
        {"valor": valor, "transicion": nombre, "etiqueta": Proceso.Estado(valor).label}
        for valor, nombre in transiciones.items()
        if valor not in Proceso.ETAPAS_PIPELINE
    ]

    return {
        "pipeline": pipeline,
        "laterales": laterales,
        "fuera_de_pipeline": posicion_actual is None,
    }


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


def procesos_con_metricas():
    """Un solo queryset anotado para tablero (kanban) y lista: cumplimiento
    de requisitos vigentes y severidad máxima de riesgo activo, sin una
    consulta por tarjeta/fila.

    `riesgo_max` NO se anota como `Max("riesgos__severidad")`: sobre un
    CharField eso ordena alfabéticamente ("media" > "alta" > "baja"), lo que
    reportaría un riesgo medio como "peor" que uno alto en cuanto ambos
    coexistan. Se anota un rango numérico vía Case/When y se traduce de
    vuelta con el filtro `rango_a_severidad`."""
    vigentes = Q(requisitos__reemplazado_por__isnull=True)
    return Proceso.objects.select_related("entidad", "responsable").annotate(
        req_cumple=Count("requisitos", filter=vigentes & Q(requisitos__cumplimiento="cumple")),
        req_parcial=Count("requisitos", filter=vigentes & Q(requisitos__cumplimiento="parcial")),
        req_no=Count(
            "requisitos",
            filter=vigentes & Q(requisitos__cumplimiento__in=["no_cumple", "subsanable"]),
        ),
        req_pendiente=Count(
            "requisitos", filter=vigentes & Q(requisitos__cumplimiento="por_verificar"),
        ),
        req_total=Count("requisitos", filter=vigentes & ~Q(requisitos__cumplimiento="no_aplica")),
        riesgo_rango=Max(
            Case(
                When(riesgos__severidad="alta", then=3),
                When(riesgos__severidad="media", then=2),
                When(riesgos__severidad="baja", then=1),
                default=0,
                output_field=IntegerField(),
            ),
            filter=Q(riesgos__descartado_por_usuario=False),
        ),
    )
