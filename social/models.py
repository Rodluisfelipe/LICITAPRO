from django.conf import settings
from django.db import models
from django.utils import timezone

from core.models import TimeStamped
from procesos.models import Proceso


class Comentario(TimeStamped):
    """Comentario contextual al proceso. Reemplaza el chat interno: es lo que
    hace que Odoo se sienta ordenado."""

    proceso = models.ForeignKey(Proceso, on_delete=models.CASCADE, related_name="comentarios")
    autor = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="comentarios",
    )
    cuerpo = models.TextField()
    menciones = models.ManyToManyField(
        settings.AUTH_USER_MODEL,
        blank=True,
        related_name="comentarios_mencionado",
    )
    responde_a = models.ForeignKey(
        "self",
        null=True,
        blank=True,
        on_delete=models.CASCADE,
        related_name="respuestas",
    )
    adjunto = models.FileField(upload_to="comentarios/%Y/%m/", blank=True)

    class Meta:
        ordering = ["creado_en"]

    def __str__(self):
        return f"{self.autor} — {self.cuerpo[:50]}"


class Actividad(TimeStamped):
    """El 'programar seguimiento' de Odoo."""

    class Tipo(models.TextChoices):
        LLAMADA = "llamada", "Llamada"
        REUNION = "reunion", "Reunión"
        TAREA = "tarea", "Tarea"
        REVISION = "revision", "Revisión de documentos"
        ENVIO = "envio", "Envío / radicación"

    proceso = models.ForeignKey(Proceso, on_delete=models.CASCADE, related_name="actividades")
    tipo = models.CharField(max_length=20, choices=Tipo.choices, default=Tipo.TAREA)
    titulo = models.CharField(max_length=200)
    notas = models.TextField(blank=True)
    asignado_a = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="actividades",
    )
    vence_en = models.DateTimeField(db_index=True)
    completada_en = models.DateTimeField(null=True, blank=True)
    evento_calendar_id = models.CharField(
        max_length=200,
        blank=True,
        help_text="ID en Google Calendar si se sincroniza.",
    )

    class Meta:
        verbose_name_plural = "Actividades"
        ordering = ["vence_en"]

    def __str__(self):
        return f"{self.titulo} ({self.proceso.numero_proceso})"

    @property
    def vencida(self) -> bool:
        return self.completada_en is None and self.vence_en < timezone.now()


class Alerta(TimeStamped):
    class Tipo(models.TextChoices):
        CIERRE_PROXIMO = "cierre_proximo", "Cierre próximo"
        NUEVA_ADENDA = "nueva_adenda", "Nueva adenda publicada"
        ANALISIS_LISTO = "analisis_listo", "Análisis de IA listo"
        RIESGO_ALTO = "riesgo_alto", "Riesgo alto detectado"
        MENCION = "mencion", "Te mencionaron"
        ASIGNACION = "asignacion", "Proceso asignado"
        NO_CUMPLE = "no_cumple", "Requisito crítico no cumplido"

    proceso = models.ForeignKey(Proceso, on_delete=models.CASCADE, related_name="alertas")
    destinatario = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="alertas",
    )
    tipo = models.CharField(max_length=20, choices=Tipo.choices)
    titulo = models.CharField(max_length=200)
    cuerpo = models.TextField(blank=True)
    leida_en = models.DateTimeField(null=True, blank=True)
    email_enviado_en = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-creado_en"]
        indexes = [models.Index(fields=["destinatario", "leida_en"])]

    def __str__(self):
        return f"{self.titulo} → {self.destinatario}"
