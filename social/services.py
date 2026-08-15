import re

from auditlog.models import LogEntry
from django.contrib.contenttypes.models import ContentType
from django.db import transaction
from django.db.models import Q

from core.models import Usuario
from procesos.models import Proceso
from social.models import Actividad, Alerta, Comentario

PATRON_MENCION = re.compile(r"@([\w.]+)")


def buscar_usuarios_mencionables(termino: str, limite: int = 6):
    """Candidatos para el autocompletado de @menciones en el chatter."""
    return Usuario.objects.filter(
        Q(username__icontains=termino)
        | Q(first_name__icontains=termino)
        | Q(last_name__icontains=termino),
        is_active=True,
    ).order_by("username")[:limite]


def _usuarios_mencionados_en(cuerpo: str, excluir: Usuario):
    nombres_usuario = set(PATRON_MENCION.findall(cuerpo))
    if not nombres_usuario:
        return Usuario.objects.none()
    return Usuario.objects.filter(username__in=nombres_usuario).exclude(pk=excluir.pk)


@transaction.atomic
def publicar_comentario(
    proceso: Proceso,
    autor: Usuario,
    cuerpo: str,
    adjunto="",
    responde_a=None,
) -> Comentario:
    """Crea el comentario y, por cada @mención resuelta a un usuario real,
    dispara una Alerta tipo MENCION al destinatario."""
    comentario = Comentario.objects.create(
        proceso=proceso,
        autor=autor,
        cuerpo=cuerpo,
        adjunto=adjunto,
        responde_a=responde_a,
    )
    mencionados = list(_usuarios_mencionados_en(cuerpo, excluir=autor))
    if mencionados:
        comentario.menciones.set(mencionados)
    for usuario in mencionados:
        Alerta.objects.create(
            proceso=proceso,
            destinatario=usuario,
            tipo=Alerta.Tipo.MENCION,
            titulo=f"{autor.get_full_name() or autor.username} te mencionó en {proceso.numero_proceso}",
            cuerpo=cuerpo,
        )
    return comentario


def programar_actividad(
    proceso: Proceso,
    asignado_a: Usuario,
    tipo: str,
    titulo: str,
    vence_en,
    notas: str = "",
) -> Actividad:
    return Actividad.objects.create(
        proceso=proceso,
        asignado_a=asignado_a,
        tipo=tipo,
        titulo=titulo,
        vence_en=vence_en,
        notas=notas,
    )


def linea_de_tiempo(proceso: Proceso) -> list[dict]:
    """Timeline unificada del chatter: comentarios + cambios de auditoría,
    más reciente primero."""
    comentarios = proceso.comentarios.select_related("autor").prefetch_related("menciones")
    cambios = LogEntry.objects.filter(
        content_type=ContentType.objects.get_for_model(Proceso),
        object_pk=str(proceso.pk),
    ).select_related("actor")

    eventos = [{"tipo": "comentario", "cuando": c.creado_en, "obj": c} for c in comentarios]
    eventos += [{"tipo": "cambio", "cuando": e.timestamp, "obj": e} for e in cambios]
    eventos.sort(key=lambda evento: evento["cuando"], reverse=True)
    return eventos
