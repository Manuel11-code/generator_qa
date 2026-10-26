import base64

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ec
from django.core.management.base import BaseCommand


def b64url(datos):
    return base64.urlsafe_b64encode(datos).rstrip(b'=').decode()


class Command(BaseCommand):
    help = 'Genera el par de llaves VAPID para Web Push. Copia la salida a tu .env.'

    def handle(self, *args, **options):
        privada = ec.generate_private_key(ec.SECP256R1())
        publica = privada.public_key().public_bytes(
            serialization.Encoding.X962, serialization.PublicFormat.UncompressedPoint)
        self.stdout.write(f'VAPID_PUBLIC_KEY={b64url(publica)}')
        self.stdout.write(f'VAPID_PRIVATE_KEY={b64url(privada.private_numbers().private_value.to_bytes(32, "big"))}')
        self.stdout.write('VAPID_SUBJECT=mailto:tu-correo@ejemplo.com')
