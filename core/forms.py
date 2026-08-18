from django import forms

from core.models import Entidad


class EntidadForm(forms.ModelForm):
    class Meta:
        model = Entidad
        fields = ["nombre", "nit", "orden", "departamento", "municipio", "sitio_web"]
