import json
from decimal import Decimal

from django.contrib import messages
from django.contrib.auth.decorators import permission_required
from django.core.exceptions import PermissionDenied
from django.core.paginator import Paginator
from django.db import transaction
from django.db.models import Q
from django.http import HttpResponseBadRequest, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST
from django_fsm import TransitionNotAllowed

from core.forms import EntidadForm
from core.models import Entidad, Origen, Usuario
from procesos import services
from procesos.filters import ProcesoFilter
from procesos.forms import ProcesoForm
from procesos.models import Proceso
from procesos.permisos import permiso_requerido_para_transicion
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

ETIQUETA_POR_FACETA = {
    "q": "Buscar", "estado": "Estado", "entidad": "Entidad", "modalidad": "Modalidad",
    "responsable": "Responsable", "fecha_cierre_desde": "Cierre desde", "fecha_cierre_hasta": "Cierre hasta",
}


def _facetas_activas(request):
    """Filtros con valor en la URL, en formato listo para pintar como chips
    removibles: etiqueta + valor legible + querystring sin ese filtro."""
    facetas = []
    for campo, etiqueta in ETIQUETA_POR_FACETA.items():
        valor = request.GET.get(campo)
        if not valor:
            continue
        texto_valor = valor
        if campo == "estado":
            texto_valor = dict(Proceso.Estado.choices).get(valor, valor)
        elif campo == "modalidad":
            texto_valor = dict(Proceso.Modalidad.choices).get(valor, valor)
        elif campo == "entidad":
            entidad = Entidad.objects.filter(pk=valor).first()
            texto_valor = entidad.nombre if entidad else valor
        elif campo == "responsable":
            responsable = Usuario.objects.filter(pk=valor).first()
            texto_valor = (responsable.get_full_name() or responsable.username) if responsable else valor
        restante = request.GET.copy()
        restante.pop(campo)
        facetas.append({
            "etiqueta": etiqueta, "valor": texto_valor, "querystring_sin_esta": restante.urlencode(),
        })
    return facetas


@permission_required("procesos.ver_procesos", raise_exception=True)
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

    qs = services.procesos_con_metricas(usuario=request.user).filter(estado__in=columnas_estados)
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

    contexto = {
        "columnas": columnas,
        "vista_actual": "kanban",
        "incluir_todos": incluir_todos,
        "puede_mover_etapa": request.user.has_perm("procesos.mover_etapa"),
        "tablero_vacio": not termino and not services.procesos_con_metricas(usuario=request.user).exists(),
    }
    return render(request, "procesos/kanban.html", contexto)


def _vista_lista(request):
    filtro = ProcesoFilter(
        request.GET,
        queryset=services.procesos_con_metricas(usuario=request.user),
    )

    orden = request.GET.get("orden", "-fecha_cierre")
    if orden not in ORDENAMIENTOS_VALIDOS:
        orden = "-fecha_cierre"

    paginador = Paginator(filtro.qs.order_by(orden), POR_PAGINA)
    pagina = paginador.get_page(request.GET.get("pagina"))
    facetas_activas = _facetas_activas(request)

    contexto = {
        "filtro": filtro,
        "pagina": pagina,
        "orden": orden,
        "vista_actual": "lista",
        "facetas_activas": facetas_activas,
        "hay_procesos_sin_filtrar": services.procesos_con_metricas(usuario=request.user).exists(),
    }

    if request.htmx:
        return render(request, "procesos/partials/tabla_procesos.html#tabla_procesos", contexto)
    return render(request, "procesos/lista.html", contexto)


@permission_required("procesos.crear_procesos", raise_exception=True)
def crear_proceso(request):
    puede_crear_entidad = request.user.has_perm("core.gestionar_entidades")
    form_entidad = None

    if request.method == "POST":
        quiere_entidad_nueva = puede_crear_entidad and bool(
            request.POST.get("nueva_entidad-nombre", "").strip(),
        )
        datos = request.POST.copy()

        with transaction.atomic():
            if quiere_entidad_nueva:
                form_entidad = EntidadForm(request.POST, prefix="nueva_entidad")
                if form_entidad.is_valid():
                    datos["entidad"] = form_entidad.save().pk
                else:
                    form = ProcesoForm(datos)
                    form.is_valid()
                    transaction.set_rollback(True)
                    return render(request, "procesos/crear.html", {
                        "form": form, "form_entidad": form_entidad,
                        "puede_crear_entidad": puede_crear_entidad,
                    })

            form = ProcesoForm(datos)
            if form.is_valid():
                proceso = form.save(commit=False)
                proceso.origen = Origen.MANUAL
                proceso.save()
                messages.success(request, "Proceso creado.")
                return redirect("procesos:detalle", pk=proceso.pk)
            transaction.set_rollback(True)

        messages.error(request, "Revisa los campos del formulario.")
        if puede_crear_entidad and form_entidad is None:
            form_entidad = EntidadForm(prefix="nueva_entidad")
    else:
        form = ProcesoForm()
        if puede_crear_entidad:
            form_entidad = EntidadForm(prefix="nueva_entidad")

    contexto = {"form": form, "form_entidad": form_entidad, "puede_crear_entidad": puede_crear_entidad}
    return render(request, "procesos/crear.html", contexto)


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

    permiso = permiso_requerido_para_transicion(nombre_transicion)
    if not request.user.has_perm(permiso):
        return JsonResponse(
            {"ok": False, "error": "No tienes permiso para mover procesos."}, status=403,
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


@permission_required("procesos.ver_procesos", raise_exception=True)
def detalle_proceso(request, pk):
    # El mismo queryset con alcance de ver_todos que usan kanban/lista: sin
    # ese permiso, un proceso ajeno ni siquiera existe para el ORM — 404,
    # no 403, para no revelar que el proceso existe.
    proceso = get_object_or_404(
        services.procesos_con_metricas(usuario=request.user).select_related("fechas_verificadas_por"),
        pk=pk,
    )

    if request.method == "POST":
        if not request.user.has_perm("procesos.editar_procesos"):
            raise PermissionDenied
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

    if not request.user.has_perm(permiso_requerido_para_transicion(transicion)):
        raise PermissionDenied

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


@permission_required("procesos.verificar_fechas", raise_exception=True)
@require_POST
def verificar_fechas(request, pk):
    proceso = get_object_or_404(Proceso, pk=pk)
    services.verificar_fechas(proceso, request.user)
    messages.success(request, "Fechas y cifras marcadas como verificadas.")
    return redirect("procesos:detalle", pk=pk)
