from django.contrib import admin

from core.models import Entidad


@admin.register(Entidad)
class EntidadAdmin(admin.ModelAdmin):
    list_display = ["nombre", "nit", "orden", "departamento", "municipio"]
    search_fields = ["nombre", "nit"]
    list_filter = ["orden", "departamento"]
