from django.db import models

# Create your models here.
from django.db import models
from django.contrib.auth.models import User

class Analisis(models.Model):
    AREA_CHOICES = [
        ('finanzas', 'Finanzas'),
        ('salud', 'Salud Digital'),
        ('tecnologia', 'Tecnología'),
    ]

    usuario = models.ForeignKey(User, on_delete=models.CASCADE)
    area = models.CharField(max_length=20, choices=AREA_CHOICES)
    codigo_original = models.TextField()
    resultado = models.TextField()
    fecha = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.usuario.username} - {self.area} - {self.fecha.strftime('%d/%m/%Y')}"

class SuscripcionPush(models.Model):
    """Suscripción Web Push de un navegador (Práctica 2.1).

    El navegador la genera con pushManager.subscribe(): 'endpoint' es la URL del
    servicio push (FCM de Chrome, Mozilla, Apple…) y 'p256dh'/'auth' son las
    llaves para cifrar el mensaje. Un usuario puede tener varias (PC, celular…).
    """
    usuario = models.ForeignKey(User, on_delete=models.CASCADE, related_name='suscripciones_push')
    endpoint = models.URLField(max_length=500, unique=True)
    p256dh = models.CharField(max_length=200)
    auth = models.CharField(max_length=100)
    navegador = models.CharField(max_length=200, blank=True)
    creada = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.usuario.username} - {self.navegador[:40] or self.endpoint[:40]}"
