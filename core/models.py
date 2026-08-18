import unicodedata
import uuid

from django.conf import settings
from django.contrib.auth.models import AbstractUser
from django.contrib.postgres.indexes import GinIndex
from django.db import models
from django.db.models import Q
from pgvector.django import HnswIndex, VectorField

from procesos.permisos import ETIQUETA_POR_CODENAME

EMBEDDING_DIMS = 1024  # BGE-M3 / Qwen3-Embedding-0.6B


class TimeStamped(models.Model):
    """Auditoría mínima en todas las tablas. django-auditlog cubre el detalle."""
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    creado_en = models.DateTimeField(auto_now_add=True, db_index=True)
    actualizado_en = models.DateTimeField(auto_now=True)
    creado_por = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True,
        on_delete=models.SET_NULL, related_name="+",
    )

    class Meta:
        abstract = True


class Origen(models.TextChoices):
    """Quién produjo el dato. Crítico: nunca confundir extracción de IA con
    verificación humana."""
    MANUAL = "manual", "Capturado manualmente"
    IMPORTADO = "importado", "Importado de Excel"
    SECOP = "secop", "API SECOP II"
    IA = "ia", "Extraído por IA"
    REGLA = "regla", "Regla determinista"


class Usuario(AbstractUser):
    class Tema(models.TextChoices):
        CLARO = "claro", "Claro"
        OSCURO = "oscuro", "Oscuro"

    class Densidad(models.TextChoices):
        COMPACTA = "compacta", "Compacta"
        NORMAL = "normal", "Normal"
        COMODA = "comoda", "Cómoda"

    class Vista(models.TextChoices):
        KANBAN = "kanban", "Kanban"
        LISTA = "lista", "Lista"

    cargo = models.CharField(max_length=120, blank=True)
    activo_comercial = models.BooleanField(default=True)

    # --- preferencias de interfaz. Se renderizan como atributos en <html>
    # desde el servidor (nunca vía JS al cargar) para que no haya parpadeo.
    tema = models.CharField(max_length=10, choices=Tema.choices, default=Tema.CLARO)
    densidad = models.CharField(max_length=10, choices=Densidad.choices, default=Densidad.NORMAL)
    vista_preferida = models.CharField(max_length=10, choices=Vista.choices, default=Vista.KANBAN)

    class Meta(AbstractUser.Meta):
        # `class Meta(AbstractUser.Meta)` extiende en vez de reemplazar —
        # `abstract` nunca se hereda (Django lo resetea a False a propósito
        # en subclases concretas), así que esto no vuelve abstracto a Usuario.
        # De paso corrige verbose_name: AbstractUser lo trae en inglés y
        # nunca se había sobreescrito.
        verbose_name = "usuario"
        verbose_name_plural = "usuarios"
        permissions = [("gestionar_usuarios", ETIQUETA_POR_CODENAME["gestionar_usuarios"])]


class Entidad(TimeStamped):
    """Entidad contratante. Autocompletado vía pg_trgm sobre nombre y NIT."""

    class Orden(models.TextChoices):
        NACIONAL = "nacional", "Nacional"
        DEPARTAMENTAL = "departamental", "Departamental"
        MUNICIPAL = "municipal", "Municipal"
        DESCENTRALIZADA = "descentralizada", "Descentralizada"
        MIXTA = "mixta", "Economía mixta"

    nombre = models.CharField(max_length=300)
    nombre_normalizado = models.CharField(
        max_length=300, db_index=True,
        help_text="Minúsculas, sin tildes. Para deduplicar en el importador.",
    )
    nit = models.CharField(max_length=20, blank=True, db_index=True)
    orden = models.CharField(max_length=20, choices=Orden.choices, blank=True)
    sector = models.CharField(max_length=120, blank=True)
    departamento = models.CharField(max_length=80, blank=True)
    municipio = models.CharField(max_length=120, blank=True)
    sitio_web = models.URLField(blank=True)
    notas = models.TextField(blank=True, help_text="Historial de relación con la entidad.")

    class Meta:
        verbose_name_plural = "Entidades"
        indexes = [
            GinIndex(fields=["nombre_normalizado"], name="idx_entidad_trgm",
                     opclasses=["gin_trgm_ops"]),
        ]
        constraints = [
            models.UniqueConstraint(
                fields=["nit"], condition=~Q(nit=""), name="uq_entidad_nit",
            ),
        ]
        permissions = [("gestionar_entidades", ETIQUETA_POR_CODENAME["gestionar_entidades"])]

    def __str__(self):
        return self.nombre

    def save(self, *args, **kwargs):
        self.nombre_normalizado = self.normalizar(self.nombre)
        super().save(*args, **kwargs)

    @staticmethod
    def normalizar(texto: str) -> str:
        sin_tildes = unicodedata.normalize("NFKD", texto).encode("ascii", "ignore").decode("ascii")
        return sin_tildes.lower()


class CodigoUNSPSC(models.Model):
    """Catálogo UNSPSC embebido una sola vez. El LLM elige entre candidatos
    recuperados por similitud — nunca genera códigos de memoria."""

    codigo = models.CharField(max_length=10, primary_key=True)
    nombre = models.CharField(max_length=300)
    nivel = models.PositiveSmallIntegerField(help_text="1=Segmento 2=Familia 3=Clase 4=Producto")
    padre = models.ForeignKey("self", null=True, blank=True,
                              on_delete=models.PROTECT, related_name="hijos")
    embedding = VectorField(dimensions=EMBEDDING_DIMS, null=True)
    es_habitual = models.BooleanField(
        default=False, help_text="Marcado por el equipo: códigos en los que la empresa compite.",
    )

    class Meta:
        verbose_name = "Código UNSPSC"
        verbose_name_plural = "Códigos UNSPSC"
        indexes = [
            HnswIndex(name="idx_unspsc_emb", fields=["embedding"],
                      m=16, ef_construction=64, opclasses=["vector_cosine_ops"]),
        ]

    def __str__(self):
        return f"{self.codigo} — {self.nombre}"
