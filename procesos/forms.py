from django import forms

from core.models import Usuario
from procesos.models import Proceso


class ProcesoForm(forms.ModelForm):
    responsable = forms.ModelChoiceField(
        queryset=Usuario.objects.filter(activo_comercial=True).order_by("first_name"),
        required=False,
    )

    class Meta:
        model = Proceso
        fields = [
            "numero_proceso",
            "entidad",
            "objeto",
            "modalidad",
            "url_secop",
            "presupuesto_oficial",
            "moneda",
            "plazo_ejecucion_dias",
            "fecha_publicacion",
            "fecha_limite_observaciones",
            "fecha_cierre",
            "fecha_adjudicacion",
            "responsable",
        ]
        widgets = {
            "objeto": forms.Textarea(attrs={"rows": 3}),
            "fecha_publicacion": forms.DateInput(format="%Y-%m-%d", attrs={"type": "date"}),
            "fecha_adjudicacion": forms.DateInput(format="%Y-%m-%d", attrs={"type": "date"}),
            "fecha_limite_observaciones": forms.DateTimeInput(
                format="%Y-%m-%dT%H:%M",
                attrs={"type": "datetime-local"},
            ),
            "fecha_cierre": forms.DateTimeInput(
                format="%Y-%m-%dT%H:%M",
                attrs={"type": "datetime-local"},
            ),
        }
