from django import template

register = template.Library()


@register.simple_tag
def siguiente_orden(orden_actual: str, campo: str) -> str:
    """Alterna asc/desc para el link de una columna ordenable de una tabla."""
    if orden_actual == campo:
        return f"-{campo}"
    return campo


@register.simple_tag
def flecha_orden(orden_actual: str, campo: str) -> str:
    if orden_actual == campo:
        return "▲"
    if orden_actual == f"-{campo}":
        return "▼"
    return ""
