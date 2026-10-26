"""Envío de notificaciones Web Push (Práctica 2.1).

Flujo: el servidor firma cada mensaje con su llave privada VAPID, lo cifra con
las llaves de la suscripción (p256dh/auth) y lo entrega al servicio push del
navegador (endpoint). Ese servicio lo hace llegar al dispositivo y el Service
Worker (evento 'push' en sw.js) muestra la notificación, aunque la app esté cerrada.
"""
import json
import logging

from django.conf import settings
# pyrefly: ignore [missing-import]
from pywebpush import webpush, WebPushException

from .models import SuscripcionPush

logger = logging.getLogger(__name__)


def push_configurado():
    return bool(settings.VAPID_PUBLIC_KEY and settings.VAPID_PRIVATE_KEY)


def enviar_push(usuario, titulo, cuerpo, url='/'):
    """Envía la notificación a todos los dispositivos del usuario.

    Devuelve cuántas se entregaron. Las suscripciones vencidas o canceladas
    (el servicio push responde 404/410) se borran.
    """
    if not push_configurado():
        logger.warning('Push sin configurar: faltan VAPID_PUBLIC_KEY / VAPID_PRIVATE_KEY')
        return 0

    payload = json.dumps({'title': titulo, 'body': cuerpo, 'url': url})
    enviadas = 0
    for s in SuscripcionPush.objects.filter(usuario=usuario):
        try:
            webpush(
                subscription_info={'endpoint': s.endpoint, 'keys': {'p256dh': s.p256dh, 'auth': s.auth}},
                data=payload,
                vapid_private_key=settings.VAPID_PRIVATE_KEY,
                vapid_claims={'sub': settings.VAPID_SUBJECT},
                ttl=60 * 60,
            )
            enviadas += 1
        except WebPushException as e:
            estado = getattr(e.response, 'status_code', None)
            if estado in (404, 410):
                s.delete()
            else:
                logger.warning('Push falló (%s): %s', estado, e)
    return enviadas
