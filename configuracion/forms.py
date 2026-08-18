from django import forms


class PerfilForm(forms.Form):
    """Nombre + descripción del perfil. Los permisos se manejan aparte en
    la vista (matriz de checkboxes agrupada por módulo, no un campo de
    formulario genérico) — ver configuracion/views.py."""

    nombre = forms.CharField(max_length=150, label="Nombre")
    descripcion = forms.CharField(
        label="Descripción", required=False, widget=forms.Textarea(attrs={"rows": 2}),
    )
