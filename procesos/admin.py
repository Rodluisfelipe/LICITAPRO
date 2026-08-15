from django.contrib import admin

from procesos.models import Proceso, Requisito, VersionDocumental


@admin.register(Proceso)
class ProcesoAdmin(admin.ModelAdmin):
    list_display = ["numero_proceso", "entidad", "estado", "fecha_cierre", "responsable"]
    list_filter = ["estado", "modalidad", "entidad"]
    search_fields = ["numero_proceso", "objeto"]
    readonly_fields = ["estado"]


class RequisitoInline(admin.TabularInline):
    """Los requisitos son inmutables: descripción y umbral se muestran pero
    no se editan aquí. Una adenda los deroga vía procesos.services.derogar_requisito."""

    model = Requisito
    fk_name = "version_origen"
    extra = 0
    fields = ["tipo", "numeral", "descripcion", "operador", "valor_umbral", "cumplimiento", "origen"]
    readonly_fields = ["descripcion", "valor_umbral"]


@admin.register(VersionDocumental)
class VersionDocumentalAdmin(admin.ModelAdmin):
    list_display = ["proceso", "secuencia", "tipo", "fecha_publicacion", "procesada"]
    list_filter = ["tipo", "procesada"]
    search_fields = ["proceso__numero_proceso"]
    inlines = [RequisitoInline]
