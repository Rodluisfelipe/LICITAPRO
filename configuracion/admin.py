from django.contrib import admin

from configuracion.models import PerfilInfo


@admin.register(PerfilInfo)
class PerfilInfoAdmin(admin.ModelAdmin):
    list_display = ["grupo", "descripcion"]
