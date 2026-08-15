from django.contrib import admin

from social.models import Actividad, Alerta, Comentario


@admin.register(Comentario)
class ComentarioAdmin(admin.ModelAdmin):
    list_display = ["proceso", "autor", "creado_en"]
    list_filter = ["proceso"]
    search_fields = ["cuerpo", "autor__username"]


@admin.register(Actividad)
class ActividadAdmin(admin.ModelAdmin):
    list_display = ["titulo", "proceso", "tipo", "asignado_a", "vence_en", "completada_en"]
    list_filter = ["tipo", "asignado_a"]
    search_fields = ["titulo", "proceso__numero_proceso"]


@admin.register(Alerta)
class AlertaAdmin(admin.ModelAdmin):
    list_display = ["titulo", "destinatario", "tipo", "proceso", "leida_en"]
    list_filter = ["tipo", "leida_en"]
    search_fields = ["titulo", "destinatario__username"]
