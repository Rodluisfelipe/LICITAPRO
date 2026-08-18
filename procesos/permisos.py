"""Catálogo explícito de permisos de negocio.

Fuente única de verdad: los `Meta.permissions` de los modelos (procesos.Proceso,
core.Entidad, core.Usuario) y la interfaz de /configuracion/perfiles/ leen de
acá — nunca se muestra un codename a un administrador no técnico, siempre la
etiqueta en español de este catálogo.

Cada entrada es (app_label, codename, etiqueta). Agrupado por módulo para que
la matriz de checkboxes de la interfaz los presente ordenados.
"""

CATALOGO_PERMISOS = {
    "Procesos": [
        ("procesos", "ver_procesos", "Ver procesos"),
        ("procesos", "crear_procesos", "Crear procesos manualmente"),
        ("procesos", "editar_procesos", "Editar datos de un proceso"),
        ("procesos", "eliminar_procesos", "Eliminar procesos"),
        ("procesos", "mover_etapa", "Mover procesos entre etapas del flujo"),
        ("procesos", "descartar_procesos", "Descartar procesos"),
        ("procesos", "verificar_fechas", "Marcar datos como verificados"),
        ("procesos", "ver_todos", "Ver procesos de todo el equipo"),
    ],
    "Entidades": [
        ("core", "gestionar_entidades", "Crear y editar entidades contratantes"),
    ],
    "Importación": [
        ("procesos", "importar_procesos", "Importar desde Excel"),
    ],
    "Administración": [
        ("core", "gestionar_usuarios", "Administrar perfiles y usuarios"),
    ],
}

# {codename: etiqueta} — para traducir en la interfaz sin recorrer el catálogo.
ETIQUETA_POR_CODENAME = {
    codename: etiqueta
    for permisos_modulo in CATALOGO_PERMISOS.values()
    for _app, codename, etiqueta in permisos_modulo
}

# Nombres de los tres perfiles de arranque — no se pueden eliminar desde la
# interfaz (ver configuracion/views.py).
PERFILES_DE_ARRANQUE = ["Administrador", "Comercial", "Consulta"]

# El perfil Administrador recibe el catálogo completo.
PERMISOS_ADMINISTRADOR = list(ETIQUETA_POR_CODENAME.keys())

PERMISOS_COMERCIAL = [
    "ver_procesos", "crear_procesos", "editar_procesos", "mover_etapa",
    "descartar_procesos", "verificar_fechas", "importar_procesos",
    "gestionar_entidades", "ver_todos",
]

PERMISOS_CONSULTA = ["ver_procesos", "ver_todos"]

PERFILES_INICIALES = {
    "Administrador": PERMISOS_ADMINISTRADOR,
    "Comercial": PERMISOS_COMERCIAL,
    "Consulta": PERMISOS_CONSULTA,
}


def permiso_requerido_para_transicion(nombre_transicion: str) -> str:
    """`descartar` tiene su propio permiso de negocio; el resto de
    transiciones del flujo (incluida `suspender`) caen bajo mover_etapa."""
    if nombre_transicion == "descartar":
        return "procesos.descartar_procesos"
    return "procesos.mover_etapa"


def crear_perfiles_de_arranque():
    """Crea los tres Groups de arranque (Administrador/Comercial/Consulta)
    con sus permisos iniciales.

    Idempotente de verdad: si el grupo YA existe — porque esto ya corrió
    antes, o porque un administrador lo tocó desde la interfaz después —
    no le vuelve a asignar permisos. Solo se asignan permisos en el
    momento de creación, nunca se pisan cambios posteriores. Se llama
    desde la data migration de procesos y directo desde los tests."""
    from django.contrib.auth.models import Group, Permission

    for nombre, codenames in PERFILES_INICIALES.items():
        grupo, creado = Group.objects.get_or_create(name=nombre)
        if not creado:
            continue
        permisos = Permission.objects.filter(
            codename__in=codenames, content_type__app_label__in=("procesos", "core"),
        )
        grupo.permissions.set(permisos)
