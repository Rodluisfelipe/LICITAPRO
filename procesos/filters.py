import django_filters
from django.db.models import Q

from core.models import Entidad, Usuario
from procesos.models import Proceso


class ProcesoFilter(django_filters.FilterSet):
    q = django_filters.CharFilter(method="filtrar_texto_libre", label="Buscar")
    estado = django_filters.ChoiceFilter(
        choices=Proceso.Estado.choices, empty_label="Todos los estados",
    )
    modalidad = django_filters.ChoiceFilter(
        choices=Proceso.Modalidad.choices, empty_label="Todas las modalidades",
    )
    entidad = django_filters.ModelChoiceFilter(
        queryset=Entidad.objects.order_by("nombre"), empty_label="Todas las entidades",
    )
    responsable = django_filters.ModelChoiceFilter(
        queryset=Usuario.objects.filter(activo_comercial=True).order_by("first_name"),
        empty_label="Todos los responsables",
    )
    fecha_cierre_desde = django_filters.DateFilter(
        field_name="fecha_cierre", lookup_expr="date__gte", label="Cierre desde",
    )
    fecha_cierre_hasta = django_filters.DateFilter(
        field_name="fecha_cierre", lookup_expr="date__lte", label="Cierre hasta",
    )

    class Meta:
        model = Proceso
        fields = ["estado", "entidad", "modalidad", "responsable"]

    def filtrar_texto_libre(self, queryset, name, value):
        return queryset.filter(Q(numero_proceso__icontains=value) | Q(objeto__icontains=value))
