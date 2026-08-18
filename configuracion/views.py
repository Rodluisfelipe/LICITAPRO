from django.contrib import messages
from django.contrib.auth.decorators import permission_required
from django.contrib.auth.models import Group, Permission
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from configuracion.forms import PerfilForm
from configuracion.models import PerfilInfo
from core.models import Usuario
from procesos.permisos import CATALOGO_PERMISOS, ETIQUETA_POR_CODENAME, PERFILES_DE_ARRANQUE

CODENAMES_VALIDOS = set(ETIQUETA_POR_CODENAME.keys())


def _codenames_validos(lista_bruta):
    """Nunca se confía en lo que mande el navegador: se filtra contra el
    catálogo real antes de tocar Permission."""
    return [c for c in lista_bruta if c in CODENAMES_VALIDOS]


def _permisos_por_codename(codenames):
    return Permission.objects.filter(
        codename__in=codenames, content_type__app_label__in=("procesos", "core"),
    )


def _usuario_perderia_gestion_usuarios(usuario, grupo_a_quitar) -> bool:
    """True si, al sacar a `usuario` de `grupo_a_quitar`, se quedaría sin
    ningún grupo que le dé gestionar_usuarios."""
    if not grupo_a_quitar.permissions.filter(codename="gestionar_usuarios").exists():
        return False
    le_queda_por_otro_grupo = (
        Usuario.objects.filter(pk=usuario.pk)
        .exclude(groups=grupo_a_quitar)
        .filter(groups__permissions__codename="gestionar_usuarios")
        .exists()
    )
    return not le_queda_por_otro_grupo


@permission_required("core.gestionar_usuarios", raise_exception=True)
def perfiles_lista(request):
    grupos = Group.objects.all().order_by("name")
    filas = [
        {
            "grupo": grupo,
            "descripcion": grupo.info.descripcion if hasattr(grupo, "info") else "",
            "num_usuarios": Usuario.objects.filter(groups=grupo).count(),
            "es_de_arranque": grupo.name in PERFILES_DE_ARRANQUE,
        }
        for grupo in grupos
    ]
    return render(request, "configuracion/perfiles_lista.html", {"filas": filas})


@permission_required("core.gestionar_usuarios", raise_exception=True)
def perfil_crear(request):
    if request.method == "POST":
        form = PerfilForm(request.POST)
        if form.is_valid():
            nombre = form.cleaned_data["nombre"]
            if Group.objects.filter(name__iexact=nombre).exists():
                form.add_error("nombre", "Ya existe un perfil con ese nombre.")
            else:
                grupo = Group.objects.create(name=nombre)
                PerfilInfo.objects.create(grupo=grupo, descripcion=form.cleaned_data["descripcion"])
                codenames = _codenames_validos(request.POST.getlist("permisos"))
                grupo.permissions.set(_permisos_por_codename(codenames))
                messages.success(request, f"Perfil «{grupo.name}» creado.")
                return redirect("configuracion:perfil_detalle", pk=grupo.pk)
    else:
        form = PerfilForm()

    contexto = {
        "form": form, "catalogo": CATALOGO_PERMISOS, "codenames_actuales": set(), "es_nuevo": True,
    }
    return render(request, "configuracion/perfil_form.html", contexto)


@permission_required("core.gestionar_usuarios", raise_exception=True)
def perfil_detalle(request, pk):
    grupo = get_object_or_404(Group, pk=pk)
    es_de_arranque = grupo.name in PERFILES_DE_ARRANQUE

    if request.method == "POST":
        form = PerfilForm(request.POST)
        if form.is_valid():
            nombre = form.cleaned_data["nombre"]
            if Group.objects.exclude(pk=grupo.pk).filter(name__iexact=nombre).exists():
                form.add_error("nombre", "Ya existe un perfil con ese nombre.")
            else:
                grupo.name = nombre
                grupo.save(update_fields=["name"])
                info, _creado = PerfilInfo.objects.get_or_create(grupo=grupo)
                info.descripcion = form.cleaned_data["descripcion"]
                info.save(update_fields=["descripcion"])
                codenames = _codenames_validos(request.POST.getlist("permisos"))
                grupo.permissions.set(_permisos_por_codename(codenames))
                messages.success(request, "Perfil actualizado.")
                return redirect("configuracion:perfil_detalle", pk=grupo.pk)
    else:
        form = PerfilForm(
            initial={
                "nombre": grupo.name,
                "descripcion": grupo.info.descripcion if hasattr(grupo, "info") else "",
            },
        )

    usuarios_asignados = Usuario.objects.filter(groups=grupo).order_by("first_name", "username")
    otros_usuarios = (
        Usuario.objects.exclude(groups=grupo).filter(is_active=True).order_by("first_name", "username")
    )

    contexto = {
        "grupo": grupo,
        "form": form,
        "catalogo": CATALOGO_PERMISOS,
        "codenames_actuales": set(grupo.permissions.values_list("codename", flat=True)),
        "es_nuevo": False,
        "es_de_arranque": es_de_arranque,
        "usuarios_asignados": usuarios_asignados,
        "otros_usuarios": otros_usuarios,
    }
    return render(request, "configuracion/perfil_form.html", contexto)


@permission_required("core.gestionar_usuarios", raise_exception=True)
@require_POST
def perfil_eliminar(request, pk):
    grupo = get_object_or_404(Group, pk=pk)

    if grupo.name in PERFILES_DE_ARRANQUE:
        messages.error(request, f"«{grupo.name}» es un perfil de arranque y no se puede eliminar.")
        return redirect("configuracion:perfil_detalle", pk=pk)

    num_usuarios = Usuario.objects.filter(groups=grupo).count()
    if num_usuarios:
        messages.error(
            request,
            f"«{grupo.name}» tiene {num_usuarios} usuario(s) asignado(s) — "
            "quítalos antes de eliminar el perfil.",
        )
        return redirect("configuracion:perfil_detalle", pk=pk)

    nombre = grupo.name
    grupo.delete()
    messages.success(request, f"Perfil «{nombre}» eliminado.")
    return redirect("configuracion:perfiles_lista")


@permission_required("core.gestionar_usuarios", raise_exception=True)
@require_POST
def perfil_agregar_usuario(request, pk):
    grupo = get_object_or_404(Group, pk=pk)
    usuario = get_object_or_404(Usuario, pk=request.POST.get("usuario_id"))
    usuario.groups.add(grupo)
    messages.success(request, f"{usuario} agregado a «{grupo.name}».")
    return redirect("configuracion:perfil_detalle", pk=pk)


@permission_required("core.gestionar_usuarios", raise_exception=True)
@require_POST
def perfil_quitar_usuario(request, pk, usuario_id):
    grupo = get_object_or_404(Group, pk=pk)
    usuario = get_object_or_404(Usuario, pk=usuario_id)

    if usuario == request.user and _usuario_perderia_gestion_usuarios(usuario, grupo):
        messages.error(request, "No puedes quitarte a ti mismo el permiso de administrar usuarios.")
        return redirect("configuracion:perfil_detalle", pk=pk)

    usuario.groups.remove(grupo)
    messages.success(request, f"{usuario} quitado de «{grupo.name}».")
    return redirect("configuracion:perfil_detalle", pk=pk)


@permission_required("core.gestionar_usuarios", raise_exception=True)
def usuarios_lista(request):
    usuarios = Usuario.objects.all().order_by("first_name", "username").prefetch_related("groups")
    grupos = Group.objects.all().order_by("name")
    return render(request, "configuracion/usuarios_lista.html", {"usuarios": usuarios, "grupos": grupos})


@permission_required("core.gestionar_usuarios", raise_exception=True)
@require_POST
def usuario_cambiar_perfil(request, pk):
    usuario = get_object_or_404(Usuario, pk=pk)
    grupo_id = request.POST.get("grupo_id") or None
    nuevo_grupo = get_object_or_404(Group, pk=grupo_id) if grupo_id else None

    if usuario == request.user:
        tendria_gestion = bool(
            nuevo_grupo and nuevo_grupo.permissions.filter(codename="gestionar_usuarios").exists(),
        )
        if not tendria_gestion:
            messages.error(request, "No puedes quitarte a ti mismo el permiso de administrar usuarios.")
            return render(
                request, "configuracion/partials/fila_usuario.html",
                {"usuario": usuario, "grupos": Group.objects.all().order_by("name")},
            )

    usuario.groups.set([nuevo_grupo] if nuevo_grupo else [])

    return render(
        request, "configuracion/partials/fila_usuario.html",
        {"usuario": usuario, "grupos": Group.objects.all().order_by("name")},
    )


@permission_required("core.gestionar_usuarios", raise_exception=True)
@require_POST
def usuario_alternar_activo(request, pk):
    usuario = get_object_or_404(Usuario, pk=pk)

    if usuario == request.user:
        messages.error(request, "No puedes desactivarte a ti mismo.")
        return redirect("configuracion:usuarios_lista")

    usuario.is_active = not usuario.is_active
    usuario.save(update_fields=["is_active"])
    messages.success(request, f"{usuario} {'activado' if usuario.is_active else 'desactivado'}.")
    return redirect("configuracion:usuarios_lista")
