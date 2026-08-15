from django.apps import AppConfig


class ProcesosConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "procesos"

    def ready(self):
        from auditlog.registry import auditlog

        from procesos.models import Proceso

        auditlog.register(Proceso)
