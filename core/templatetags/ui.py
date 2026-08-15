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


CIRCUNFERENCIA_ANILLO = 88


@register.filter
def offset_anillo(puntaje) -> str:
    """stroke-dashoffset de anillo_ajuste: 88 (vacío) si no hay puntaje.
    Formateado a mano (no round() crudo): LANGUAGE_CODE=es-co hace que
    Django renderice floats con coma decimal ("17,6"), inválido en un
    atributo SVG. f-string siempre usa punto, sin importar el locale."""
    if puntaje is None:
        return str(CIRCUNFERENCIA_ANILLO)
    valor = CIRCUNFERENCIA_ANILLO - (puntaje / 100 * CIRCUNFERENCIA_ANILLO)
    return f"{valor:.1f}"


@register.filter
def banda_ajuste(puntaje) -> str:
    """Clase CSS de anillo_ajuste/badge según el puntaje de IA."""
    if puntaje is None:
        return "a-nulo"
    if puntaje >= 75:
        return "a-alto"
    if puntaje >= 45:
        return "a-medio"
    return "a-bajo"


@register.filter
def porcentaje(parte, total) -> str:
    """% de `parte` sobre `total`, para anchos (width:…%) de
    barra_cumplimiento y tablero__distribucion. Ver nota en offset_anillo:
    string con punto decimal a propósito, nunca un float crudo."""
    if not total:
        return "0"
    return f"{parte / total * 100:.2f}"


_SEVERIDAD_POR_RANGO = {3: "alta", 2: "media", 1: "baja"}


@register.filter
def rango_a_severidad(rango) -> str:
    """Traduce el `riesgo_rango` anotado (0-3) de vuelta a la etiqueta de
    severidad, para semaforo_riesgo."""
    return _SEVERIDAD_POR_RANGO.get(rango, "")


@register.filter
def a_porcentaje(fraccion) -> int:
    """0.82 -> 82, para confianza_ia (0-1) mostrada como %."""
    if fraccion is None:
        return 0
    return round(fraccion * 100)
