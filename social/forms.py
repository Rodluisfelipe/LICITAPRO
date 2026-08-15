from django import forms

from core.models import Usuario
from social.models import Actividad


class ActividadForm(forms.ModelForm):
    asignado_a = forms.ModelChoiceField(
        queryset=Usuario.objects.filter(activo_comercial=True).order_by("first_name"),
    )

    class Meta:
        model = Actividad
        fields = ["tipo", "titulo", "vence_en", "asignado_a", "notas"]
        widgets = {
            "vence_en": forms.DateTimeInput(
                format="%Y-%m-%dT%H:%M",
                attrs={"type": "datetime-local"},
            ),
            "notas": forms.Textarea(attrs={"rows": 2}),
        }
