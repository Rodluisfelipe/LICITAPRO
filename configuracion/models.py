from django.contrib.auth.models import Group
from django.db import models


class PerfilInfo(models.Model):
    """Extiende django.contrib.auth.Group con lo que la interfaz de
    perfiles necesita y Group no trae de fábrica. Group no se puede
    modificar directamente (es de django.contrib.auth), así que esto vive
    en una tabla aparte, 1:1."""

    grupo = models.OneToOneField(Group, on_delete=models.CASCADE, related_name="info")
    descripcion = models.TextField(blank=True)

    class Meta:
        verbose_name = "Información de perfil"
        verbose_name_plural = "Información de perfiles"

    def __str__(self):
        return self.grupo.name
