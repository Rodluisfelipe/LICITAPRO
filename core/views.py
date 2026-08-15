from django.http import HttpResponse
from django.shortcuts import render
from django.views.decorators.http import require_POST

from core.models import Usuario
from core.services import buscar_entidades

CAMPOS_PREFERENCIA = {
    "tema": set(Usuario.Tema.values),
    "densidad": set(Usuario.Densidad.values),
    "vista_preferida": set(Usuario.Vista.values),
}


def entidades(request):
    return render(request, "core/entidades.html", {"entidades": []})


def entidades_autocompletar(request):
    termino = request.GET.get("q", "").strip()
    entidades_encontradas = buscar_entidades(termino) if termino else []
    return render(
        request,
        "core/partials/resultados_entidades.html#resultados_entidades",
        {"entidades": entidades_encontradas},
    )


@require_POST
def actualizar_preferencias(request):
    """Persiste tema/densidad/vista_preferida en segundo plano. El DOM ya
    se actualizó al instante en el cliente antes de este POST."""
    if not request.user.is_authenticated:
        return HttpResponse(status=204)
    campo = request.POST.get("campo")
    valor = request.POST.get("valor")
    if campo in CAMPOS_PREFERENCIA and valor in CAMPOS_PREFERENCIA[campo]:
        setattr(request.user, campo, valor)
        request.user.save(update_fields=[campo])
    return HttpResponse(status=204)
