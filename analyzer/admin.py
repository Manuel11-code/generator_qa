from django.contrib import admin
from .models import Analisis, SuscripcionPush


@admin.register(Analisis)
class AnalisisAdmin(admin.ModelAdmin):
    list_display = ('usuario', 'area', 'fecha')
    list_filter = ('area',)


@admin.register(SuscripcionPush)
class SuscripcionPushAdmin(admin.ModelAdmin):
    list_display = ('usuario', 'navegador', 'creada')
