from django.contrib.postgres.search import TrigramSimilarity
from django.db.models import QuerySet

from core.models import Entidad

UMBRAL_SIMILITUD_ENTIDAD = 0.1


def buscar_entidades(termino: str, limite: int = 10) -> QuerySet[Entidad]:
    """Autocompletado de entidades por similitud pg_trgm sobre nombre_normalizado."""
    termino_normalizado = Entidad.normalizar(termino)
    return (
        Entidad.objects.annotate(
            similitud=TrigramSimilarity("nombre_normalizado", termino_normalizado),
        )
        .filter(similitud__gt=UMBRAL_SIMILITUD_ENTIDAD)
        .order_by("-similitud")[:limite]
    )
