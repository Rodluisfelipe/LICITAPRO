import json
from decimal import Decimal

from django.contrib import messages
from django.core.paginator import Paginator
from django.db.models import Q
from django.http import HttpResponseBadRequest, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST
from django_fsm import TransitionNotAllowed

from procesos import services
from procesos.filters import ProcesoFilter
from procesos.forms import ProcesoForm
from procesos.models import Proceso
from social.forms import ActividadForm
from social.models import Actividad
from social.services import linea_de_tiempo

POR_PAGINA = 50

ORDENAMIENTOS_VALIDOS = {
    "numero_proceso",
    "-numero_proceso",
    "entidad__nombre",
    "-entidad__nombre",
    "estado",
    "-estado",
    "fecha_cierre",
    "-fecha_cierre",
    "responsable__first_name",
    "-responsable__first_name",
    "presupuesto_oficial",
    "-presupuesto_oficial",
}

# Columnas por defecto del kanban: solo el camino activo. Descartado,
# adjudicado y no_adjudicado son desenlaces — se acceden con ?todos=1.
COLUMNAS_KANBAN_DEFECTO = [
    Proceso.Estado.DETECTADO, Proceso.Estado.EN_EVALUACION, Proceso.Estado.APTO,
    Proceso.Estado.EN_PREPARACION, Proceso.Estado.PRESENTADO,
]


def lista_procesos(request):
    vista = request.GET.get("vista") or (
        request.user.vista_preferida if request.user.is_authenticated else "kanban"
    )
    if vista == "lista":
        return _vista_lista(request)
    return _vista_kanban(request)


def _vista_kanban(request):
    incluir_todos = request.GET.get("todos") == "1"
    columnas_estados = list(Proceso.Estado.values) if incluir_todos else COLUMNAS_KANBAN_DEFECTO

    qs = services.procesos_con_metricas().filter(estado__in=columnas_estados)
    termino = request.GET.get("q", "").strip()
    if termino:
        qs = qs.filter(Q(numero_proceso__icontains=termino) | Q(objeto__icontains=termino))

    procesos = list(qs.order_by("fecha_cierre"))
    for proceso in procesos:
        proceso.transiciones_json = json.dumps(services.transiciones_disponibles(proceso))

    por_estado = {estado: [] for estado in columnas_estados}
    for proceso in procesos:
        por_estado[proceso.estado].append(proceso)

    columnas = []
    for estado in columnas_estados:
        items = por_estado[estado]
        criticos = sum(1 for p in items if p.dias_para_cierre is not None and p.dias_para_cierre <= 3)
        prontos = sum(
            1 for p in items if p.dias_para_cierre is not None and 3 < p.dias_para_cierre <= 7
        )
        columnas.append({
            "valor": estado,
            "etiqueta": Proceso.Estado(estado).label,
            "procesos": items,
            "contador": len(items),
            "presupuesto_total": sum((p.presupuesto_oficial or Decimal(0)) for p in items),
            "criticos": criticos,
            "prontos": prontos,
            "normales": len(items) - criticos - prontos,
        })

    contexto = {"columnas": columnas, "vista_actual": "kanban", "incluir_todos": incluir_todos}
    return render(request, "procesos/kanban.html", contexto)


def _vista_lista(request):
    filtro = ProcesoFilter(
        request.GET,
        queryset=Proceso.objects.select_related("entidad", "responsable"),
    )

    orden = request.GET.get("orden", "-fecha_cierre")
    if orden not in ORDENAMIENTOS_VALIDOS:
        orden = "-fecha_cierre"

    paginador = Paginator(filtro.qs.order_by(orden), POR_PAGINA)
    pagina = paginador.get_page(request.GET.get("pagina"))

    contexto = {"filtro": filtro, "pagina": pagina, "orden": orden, "vista_actual": "lista"}

    if request.htmx:
        return render(request, "procesos/partials/tabla_procesos.html#tabla_procesos", contexto)
    return render(request, "procesos/lista.html", contexto)


@require_POST
def mover_kanban(request, pk, estado_destino):
    """Drop del drag&drop: el servidor decide si la transición existe —
    el cliente nunca inventa un nombre de transición, solo dice a qué
    columna soltó la tarjeta."""
    proceso = get_object_or_404(Proceso, pk=pk)
    nombre_transicion = services.transiciones_disponibles(proceso).get(estado_destino)
    if not nombre_transicion:
        return JsonResponse(
            {"ok": False, "error": "Esa transición ya no es válida para el estado actual."}, status=409,
        )

    accion = getattr(services, nombre_transicion)
    try:
        if nombre_transicion == "descartar":
            accion(proceso, request.user, motivo=request.POST.get("motivo", "Descartado desde el tablero."))
        else:
            accion(proceso, request.user)
    except TransitionNotAllowed:
        return JsonResponse(
            {"ok": False, "error": "Esa transición ya no es válida para el estado actual."}, status=409,
        )
    return JsonResponse({"ok": True, "estado": proceso.estado})


def detalle_proceso(request, pk):
    proceso = get_object_or_404(
        Proceso.objects.select_related("entidad", "responsable", "fechas_verificadas_por"),
        pk=pk,
    )

    if request.method == "POST":
        form = ProcesoForm(request.POST, instance=proceso)
        if form.is_valid():
            form.save()
            messages.success(request, "Proceso actualizado.")
            return redirect("procesos:detalle", pk=pk)
        messages.error(request, "Revisa los campos del formulario.")
    else:
        form = ProcesoForm(instance=proceso)

    contexto = {
        "proceso": proceso,
        "form": form,
        "estado_ui": services.estado_disponible(proceso),
        "requisitos": proceso.requisitos_vigentes.select_related("version_origen"),
        "actividades": proceso.actividades.select_related("asignado_a"),
        "linea_tiempo": linea_de_tiempo(proceso),
        "form_actividad": ActividadForm(
            initial={"asignado_a": request.user, "tipo": Actividad.Tipo.TAREA},
        ),
        "tab_inicial": request.GET.get("tab", "requisitos"),
    }
    return render(request, "procesos/detalle.html", contexto)


@require_POST
def transicionar_proceso(request, pk, transicion):
    if transicion not in services.TRANSICIONES_VALIDAS:
        return HttpResponseBadRequest("Transición desconocida.")

    proceso = get_object_or_404(Proceso, pk=pk)
    accion = getattr(services, transicion)
    try:
        if transicion == "descartar":
            accion(proceso, request.user, motivo=request.POST.get("motivo", ""))
        else:
            accion(proceso, request.user)
    except TransitionNotAllowed:
        messages.error(request, "Esa transición ya no es válida para el estado actual del proceso.")
    return redirect("procesos:detalle", pk=pk)


@require_POST
def verificar_fechas(request, pk):
    proceso = get_object_or_404(Proceso, pk=pk)
    services.verificar_fechas(proceso, request.user)
    messages.success(request, "Fechas y cifras marcadas como verificadas.")
    return redirect("procesos:detalle", pk=pk)
