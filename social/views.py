from django.contrib import messages
from django.http import HttpResponseBadRequest
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.views.decorators.http import require_POST

from procesos.models import Proceso
from social import services
from social.forms import ActividadForm


def autocompletar_usuarios(request):
    if "q" not in request.GET:
        usuarios = []
    else:
        usuarios = services.buscar_usuarios_mencionables(request.GET["q"])
    return render(request, "social/partials/sugerencias_mencion.html", {"usuarios": usuarios})


@require_POST
def comentar(request, proceso_id):
    proceso = get_object_or_404(Proceso, pk=proceso_id)
    cuerpo = request.POST.get("cuerpo", "").strip()
    if not cuerpo:
        return HttpResponseBadRequest("El comentario no puede estar vacío.")

    comentario = services.publicar_comentario(
        proceso,
        request.user,
        cuerpo,
        adjunto=request.FILES.get("adjunto", ""),
    )
    evento = {"tipo": "comentario", "cuando": comentario.creado_en, "obj": comentario}
    return render(request, "social/partials/evento_timeline.html", {"evento": evento})


@require_POST
def crear_actividad(request, proceso_id):
    proceso = get_object_or_404(Proceso, pk=proceso_id)
    form = ActividadForm(request.POST)
    if form.is_valid():
        services.programar_actividad(
            proceso,
            asignado_a=form.cleaned_data["asignado_a"],
            tipo=form.cleaned_data["tipo"],
            titulo=form.cleaned_data["titulo"],
            vence_en=form.cleaned_data["vence_en"],
            notas=form.cleaned_data["notas"],
        )
        messages.success(request, "Actividad programada.")
    else:
        messages.error(request, "Revisa los datos de la actividad.")
    return redirect(f"{reverse('procesos:detalle', args=[proceso_id])}?tab=actividades")
