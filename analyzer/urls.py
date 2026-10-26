# pyrefly: ignore [missing-import]
from django.urls import path
# pyrefly: ignore [missing-import]
from . import views

urlpatterns = [
    # ── PWA ────────────────────────────────────────────────────────────────────
    # sw.js debe estar en la raíz para tener scope sobre todo el origin
    path('sw.js', views.service_worker, name='service_worker'),

    # ── Auth ────────────────────────────────────────────────────────────────────
    path('', views.login_view, name='login'),
    path('registro/', views.registro, name='registro'),
    path('logout/', views.logout_view, name='logout'),

    # ── App ─────────────────────────────────────────────────────────────────────
    path('dashboard/', views.dashboard, name='dashboard'),
    path('analizar/', views.analizar, name='analizar'),
    path('historial/', views.historial, name='historial'),

    # ── SSR vs CSR (Práctica 1.3) ────────────────────────────────────────────
    path('historial/csr/', views.historial_csr, name='historial_csr'),
    path('api/historial/', views.api_historial, name='api_historial'),
    path('comparar/', views.comparar_render, name='comparar_render'),

    # ── Notificaciones push y permisos (Práctica 2.1) ───────────────────────
    path('permisos/', views.permisos, name='permisos'),
    path('api/push/suscribir/', views.push_suscribir, name='push_suscribir'),
    path('api/push/desuscribir/', views.push_desuscribir, name='push_desuscribir'),
    path('api/push/prueba/', views.push_prueba, name='push_prueba'),

    path('analisis/<int:id>/', views.detalle_analisis, name='detalle_analisis'),
    path('analisis/<int:id>/pdf/', views.descargar_pdf, name='descargar_pdf'),
]
