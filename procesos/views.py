from django.core.paginator import Paginator
from django.shortcuts import render

from procesos.filters import ProcesoFilter
from procesos.models import Proceso

POR_PAGINA = 50

ORDENAMIENTOS_VALIDOS = {
    "numero_proceso", "-numero_proceso",
    "entidad__nombre", "-entidad__nombre",
    "estado", "-estado",
    "fecha_cierre", "-fecha_cierre",
    "responsable__first_name", "-responsable__first_name",
    "presupuesto_oficial", "-presupuesto_oficial",
}


def lista_procesos(request):
    filtro = ProcesoFilter(
        request.GET,
        queryset=Proceso.objects.select_related("entidad", "responsable"),
    )

    orden = request.GET.get("orden", "-fecha_cierre")
    if orden not in ORDENAMIENTOS_VALIDOS:
        orden = "-fecha_cierre"

    paginador = Paginator(filtro.qs.order_by(orden), POR_PAGINA)
    pagina = paginador.get_page(request.GET.get("pagina"))

    contexto = {"filtro": filtro, "pagina": pagina, "orden": orden}

    if request.htmx:
        return render(request, "procesos/partials/tabla_procesos.html#tabla_procesos", contexto)
    return render(request, "procesos/lista.html", contexto)
