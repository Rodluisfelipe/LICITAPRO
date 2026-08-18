from unittest.mock import patch

import pytest
from allauth.core.exceptions import ImmediateHttpResponse
from allauth.socialaccount.models import SocialAccount, SocialLogin
from django.conf import settings
from django.contrib.messages.storage.fallback import FallbackStorage
from django.core.management import call_command
from django.test import RequestFactory, override_settings

from core.adapters import SocialAccountAdapterDominio
from core.models import Usuario
from core.tests.factories import UsuarioFactory
from procesos.tests.factories import ProcesoFactory


def _sociallogin(email: str) -> SocialLogin:
    usuario = Usuario(email=email)
    cuenta = SocialAccount(provider="google", uid=email)
    return SocialLogin(user=usuario, account=cuenta)


def _request_con_messages(rf, ruta="/accounts/google/login/callback/"):
    """pre_social_login llama messages.error(), que necesita un storage
    real — RequestFactory no pasa por MessageMiddleware, así que se
    engancha a mano, como recomienda la documentación de Django para
    probar vistas que usan el framework de mensajes fuera del ciclo
    request/response completo."""
    request = rf.get(ruta)
    request.session = {}
    request._messages = FallbackStorage(request)
    return request


@pytest.mark.django_db
@override_settings(GOOGLE_WORKSPACE_DOMAIN="licitapro.test")
def test_pre_social_login_rechaza_dominio_ajeno(rf):
    request = _request_con_messages(rf)

    with pytest.raises(ImmediateHttpResponse):
        SocialAccountAdapterDominio().pre_social_login(request, _sociallogin("alguien@gmail.com"))


@pytest.mark.django_db
@override_settings(GOOGLE_WORKSPACE_DOMAIN="licitapro.test")
def test_pre_social_login_acepta_dominio_correcto(rf):
    request = _request_con_messages(rf)

    # No debe lanzar — es un sociallogin nuevo (usuario.pk es None) y sin
    # coincidencia previa por email, así que sigue el flujo normal de
    # SOCIALACCOUNT_AUTO_SIGNUP sin intervención del adapter.
    SocialAccountAdapterDominio().pre_social_login(request, _sociallogin("nueva@licitapro.test"))


@pytest.mark.django_db
@override_settings(GOOGLE_WORKSPACE_DOMAIN="licitapro.test")
def test_pre_social_login_conecta_usuario_preexistente_por_email(rf):
    usuario_precreado = UsuarioFactory(email="admin@licitapro.test")
    request = _request_con_messages(rf)
    sociallogin = _sociallogin("admin@licitapro.test")

    with patch.object(SocialLogin, "connect") as connect_mock:
        SocialAccountAdapterDominio().pre_social_login(request, sociallogin)

    connect_mock.assert_called_once_with(request, usuario_precreado)


@pytest.mark.django_db
@override_settings(GOOGLE_WORKSPACE_DOMAIN="licitapro.test")
def test_pre_social_login_rechaza_usuario_preexistente_desactivado(rf):
    UsuarioFactory(email="exempleado@licitapro.test", is_active=False)
    request = _request_con_messages(rf)

    with pytest.raises(ImmediateHttpResponse):
        SocialAccountAdapterDominio().pre_social_login(
            request, _sociallogin("exempleado@licitapro.test"),
        )


@pytest.mark.django_db
def test_crear_admins_es_idempotente():
    call_command("crear_admins", "admin1@licitapro.test", "admin2@licitapro.test")
    call_command("crear_admins", "admin1@licitapro.test", "admin2@licitapro.test")

    admins = Usuario.objects.filter(email__in=["admin1@licitapro.test", "admin2@licitapro.test"])
    assert admins.count() == 2
    assert all(u.is_staff and u.is_superuser and u.is_active for u in admins)


@pytest.mark.django_db
def test_crear_admins_promueve_usuario_existente_sin_privilegios():
    UsuarioFactory(email="comercial@licitapro.test", is_staff=False, is_superuser=False)

    call_command("crear_admins", "comercial@licitapro.test")

    usuario = Usuario.objects.get(email="comercial@licitapro.test")
    assert usuario.is_staff and usuario.is_superuser


@pytest.mark.django_db
def test_vistas_protegidas_redirigen_anonimo_a_login(client):
    proceso = ProcesoFactory()

    rutas_get = [
        "/procesos/",
        f"/procesos/{proceso.pk}/",
        "/entidades/",
    ]
    for ruta in rutas_get:
        respuesta = client.get(ruta)
        assert respuesta.status_code == 302, ruta
        assert "/accounts/login/" in respuesta.url, ruta

    respuesta = client.post(f"/procesos/{proceso.pk}/transicion/iniciar_evaluacion/")
    assert respuesta.status_code == 302
    assert "/accounts/login/" in respuesta.url

    respuesta = client.post(f"/procesos/{proceso.pk}/mover/en_evaluacion/")
    assert respuesta.status_code == 302
    assert "/accounts/login/" in respuesta.url


@pytest.mark.django_db
def test_login_page_es_publica_para_anonimo(client):
    respuesta = client.get("/accounts/login/")
    assert respuesta.status_code == 200


@pytest.mark.django_db
@override_settings(GOOGLE_WORKSPACE_DOMAIN="licitapro.test")
def test_rechazo_de_dominio_aterriza_con_mensaje_en_nuestra_pagina_de_login(client):
    """Pendiente del día 1: el rechazo del adapter no debe caer en la
    página de error genérica de allauth. Reproduce el ciclo real —
    mismo request, misma sesión que después sigue el cliente de
    pruebas — para confirmar que el mensaje sobrevive el redirect y se
    ve en NUESTRA plantilla, no en socialaccount/authentication_error.html."""
    client.get("/accounts/login/")  # crea la sesión del cliente

    request = RequestFactory().get("/accounts/google/login/callback/")
    request.session = client.session
    request._messages = FallbackStorage(request)

    with pytest.raises(ImmediateHttpResponse) as exc_info:
        SocialAccountAdapterDominio().pre_social_login(request, _sociallogin("alguien@gmail.com"))

    respuesta_redirect = exc_info.value.response
    assert respuesta_redirect.status_code == 302
    assert respuesta_redirect.url == "/accounts/login/"

    # Lo que hace MessageMiddleware.process_response de verdad: escribir el
    # mensaje pendiente sobre la respuesta que efectivamente vuelve al
    # navegador (acá, CookieStorage lo pone en una cookie de ESE redirect,
    # no en la sesión — por eso hay que copiar sus cookies al cliente).
    request._messages.update(respuesta_redirect)
    request.session.save()
    client.cookies[settings.SESSION_COOKIE_NAME] = request.session.session_key
    for nombre, morsel in respuesta_redirect.cookies.items():
        client.cookies[nombre] = morsel.value

    respuesta_login = client.get("/accounts/login/")
    assert respuesta_login.status_code == 200
    contenido = respuesta_login.content.decode()
    assert "Solo se permite el acceso con cuentas de licitapro.test" in contenido
    # No es la plantilla genérica de allauth.
    assert "Third-Party Login Failure" not in contenido
