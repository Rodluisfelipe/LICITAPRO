from django.shortcuts import render

from core.services import buscar_entidades


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
