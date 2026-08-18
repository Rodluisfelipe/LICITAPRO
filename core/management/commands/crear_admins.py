from django.core.management.base import BaseCommand

from core.models import Usuario


class Command(BaseCommand):
    help = (
        "Crea o promueve a administrador general (is_staff + is_superuser) las "
        "cuentas de correo dadas. Idempotente — correrlo varias veces no rompe. "
        "El usuario se conecta a su cuenta de Google la primera vez que entra "
        "(ver core.adapters.SocialAccountAdapterDominio)."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "correos", nargs="+", help="Correos @dominio a marcar como administradores generales.",
        )

    def handle(self, *args, **options):
        for correo_crudo in options["correos"]:
            correo = correo_crudo.strip().lower()
            usuario, creado = Usuario.objects.get_or_create(
                email=correo,
                defaults={
                    "username": correo, "is_staff": True, "is_superuser": True, "is_active": True,
                },
            )

            if not creado:
                campos_a_actualizar = [
                    campo
                    for campo in ("is_staff", "is_superuser", "is_active")
                    if not getattr(usuario, campo)
                ]
                for campo in campos_a_actualizar:
                    setattr(usuario, campo, True)
                if campos_a_actualizar:
                    usuario.save(update_fields=campos_a_actualizar)

            accion = "creado" if creado else "ya existía — verificado"
            self.stdout.write(self.style.SUCCESS(f"{correo}: {accion} como administrador general."))
