import base64
import json
import os
from unittest import mock

import http_ece
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ec
from django.contrib.auth.models import User
from django.test import TestCase, override_settings

from .models import SuscripcionPush


def b64url(datos):
    return base64.urlsafe_b64encode(datos).rstrip(b'=').decode()


def llaves_vapid():
    privada = ec.generate_private_key(ec.SECP256R1())
    publica = privada.public_key().public_bytes(
        serialization.Encoding.X962, serialization.PublicFormat.UncompressedPoint)
    return b64url(publica), b64url(privada.private_numbers().private_value.to_bytes(32, 'big'))


VAPID_PUB, VAPID_PRIV = llaves_vapid()


class NavegadorFalso:
    """Simula lo que hace pushManager.subscribe(): llaves p256dh/auth reales."""

    def __init__(self, endpoint='https://fcm.googleapis.com/fcm/send/abc123'):
        self.privada = ec.generate_private_key(ec.SECP256R1())
        self.auth = os.urandom(16)
        self.endpoint = endpoint

    def suscripcion(self):
        p256dh = self.privada.public_key().public_bytes(
            serialization.Encoding.X962, serialization.PublicFormat.UncompressedPoint)
        return {'endpoint': self.endpoint, 'keys': {'p256dh': b64url(p256dh), 'auth': b64url(self.auth)}}

    def descifrar(self, cuerpo):
        return json.loads(http_ece.decrypt(cuerpo, private_key=self.privada, auth_secret=self.auth))


class RespuestaFalsa:
    def __init__(self, status_code):
        self.status_code = status_code
        self.text = ''
        self.headers = {}
        self.reason = ''


@override_settings(VAPID_PUBLIC_KEY=VAPID_PUB, VAPID_PRIVATE_KEY=VAPID_PRIV, VAPID_SUBJECT='mailto:test@example.com')
class PushTests(TestCase):
    """Práctica 2.1: flujo de suscripción y envío de notificaciones push."""

    def setUp(self):
        self.user = User.objects.create_user('ana', password='clave-segura-123')
        self.client.force_login(self.user)
        self.navegador = NavegadorFalso()

    def suscribir(self, datos=None):
        return self.client.post('/api/push/suscribir/', json.dumps(datos or self.navegador.suscripcion()),
                                content_type='application/json')

    def test_pagina_permisos_entrega_llave_publica(self):
        r = self.client.get('/permisos/')
        self.assertEqual(r.status_code, 200)
        self.assertContains(r, VAPID_PUB)

    def test_suscribir_guarda_y_no_duplica(self):
        self.assertEqual(self.suscribir().json()['dispositivos'], 1)
        self.assertEqual(self.suscribir().json()['dispositivos'], 1)  # mismo endpoint
        self.assertEqual(SuscripcionPush.objects.get().usuario, self.user)

    def test_suscribir_rechaza_datos_invalidos(self):
        self.assertEqual(self.suscribir({'endpoint': 'http://inseguro', 'keys': {}}).status_code, 400)
        self.assertFalse(SuscripcionPush.objects.exists())

    def test_requiere_sesion(self):
        self.client.logout()
        self.assertEqual(self.suscribir().status_code, 401)
        self.assertEqual(self.client.post('/api/push/prueba/').status_code, 401)

    def test_prueba_sin_dispositivos(self):
        self.assertEqual(self.client.post('/api/push/prueba/').status_code, 404)

    def test_prueba_envia_mensaje_cifrado_y_firmado(self):
        self.suscribir()
        with mock.patch('pywebpush.requests.post', return_value=RespuestaFalsa(201)) as post:
            r = self.client.post('/api/push/prueba/')
        self.assertEqual(r.json(), {'ok': True, 'enviadas': 1})

        url = post.call_args.args[0]
        headers = post.call_args.kwargs['headers']
        self.assertEqual(url, self.navegador.endpoint)
        self.assertIn('vapid', headers['authorization'].lower())     # firmado con VAPID
        self.assertEqual(headers['content-encoding'], 'aes128gcm')    # cifrado
        # Solo el navegador (con su llave privada) puede leer el contenido:
        datos = self.navegador.descifrar(post.call_args.kwargs['data'])
        self.assertEqual(datos['title'], '🔔 Notificación de prueba')
        self.assertEqual(datos['url'], '/historial/')

    def test_suscripcion_vencida_se_borra(self):
        self.suscribir()
        with mock.patch('pywebpush.requests.post', return_value=RespuestaFalsa(410)):
            r = self.client.post('/api/push/prueba/')
        self.assertEqual(r.status_code, 404)
        self.assertFalse(SuscripcionPush.objects.exists())

    def test_desuscribir(self):
        self.suscribir()
        r = self.client.post('/api/push/desuscribir/', json.dumps({'endpoint': self.navegador.endpoint}),
                             content_type='application/json')
        self.assertEqual(r.json()['dispositivos'], 0)

    @override_settings(VAPID_PUBLIC_KEY='', VAPID_PRIVATE_KEY='')
    def test_sin_llaves_vapid(self):
        self.suscribir()
        self.assertEqual(self.client.post('/api/push/prueba/').status_code, 503)
