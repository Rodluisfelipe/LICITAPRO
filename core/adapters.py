from allauth.account.adapter import DefaultAccountAdapter
from allauth.core.exceptions import ImmediateHttpResponse
from allauth.socialaccount.adapter import DefaultSocialAccountAdapter
from django.conf import settings
from django.contrib import messages
from django.shortcuts import redirect

from core.models import Usuario


class AccountAdapterSinRegistro(DefaultAccountAdapter):
    """El único camino de entrada es Google. Sin esto, allauth expone un
    formulario de registro por correo/contraseña en /accounts/signup/.

    Esto NO afecta el alta automática vía Google (esa la gobierna
    SOCIALACCOUNT_AUTO_SIGNUP + SocialAccountAdapterDominio) — is_open_for_signup
    aquí solo controla el signup clásico de allauth.account."""

    def is_open_for_signup(self, request):
        return False


class SocialAccountAdapterDominio(DefaultSocialAccountAdapter):
    """Restringe el login de Google al dominio de Workspace de la empresa.

    El parámetro `hd` en AUTH_PARAMS no basta: solo le sugiere a Google qué
    cuenta mostrar en el selector — un usuario puede editarlo a mano en la
    URL o elegir una cuenta personal igual. La verificación real tiene que
    pasar por acá, del lado del servidor, contra el email que Google
    efectivamente devolvió (ver DECISIONES.md)."""

    def pre_social_login(self, request, sociallogin):
        dominio_permitido = settings.GOOGLE_WORKSPACE_DOMAIN
        email = (sociallogin.user.email or "").lower()

        if dominio_permitido and not email.endswith(f"@{dominio_permitido.lower()}"):
            messages.error(
                request, f"Solo se permite el acceso con cuentas de {dominio_permitido}.",
            )
            raise ImmediateHttpResponse(redirect("account_login"))

        if sociallogin.is_existing:
            return

        # Cuenta pre-creada por `crear_admins` (u otro admin) antes del
        # primer login: conectar en vez de dejar que allauth cree un
        # Usuario duplicado.
        try:
            usuario_existente = Usuario.objects.get(email__iexact=email)
        except Usuario.DoesNotExist:
            return

        if not usuario_existente.is_active:
            messages.error(request, "Tu cuenta está desactivada. Contacta a un administrador.")
            raise ImmediateHttpResponse(redirect("account_login"))

        sociallogin.connect(request, usuario_existente)
