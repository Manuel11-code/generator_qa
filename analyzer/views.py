import anthropic
import json
import logging
import os
from django.conf import settings
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth import login, logout, authenticate
from django.contrib.auth.models import User
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.views.decorators.http import require_POST
from django.http import HttpResponse, FileResponse, JsonResponse
from django.contrib.staticfiles import finders
from django.urls import reverse
from django.utils import timezone
from django.utils.formats import date_format
from django.utils.text import Truncator
from django.views.decorators.clickjacking import xframe_options_sameorigin
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import inch
from reportlab.lib import colors
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, HRFlowable
from reportlab.lib.enums import TA_CENTER
# pyrefly: ignore [missing-import]
from .models import Analisis, SuscripcionPush
from .push import enviar_push, push_configurado

logger = logging.getLogger(__name__)


# ─── PWA Views ────────────────────────────────────────────────────────────────

def service_worker(request):
    """
    Sirve el Service Worker (sw.js) desde la raíz del dominio (/sw.js)
    con el scope correcto para controlar toda la aplicación.
    """
    sw_path = finders.find('analyzer/sw.js')
    if sw_path:
        response = FileResponse(
            open(sw_path, 'rb'),
            content_type='application/javascript; charset=utf-8'
        )
        # Permite que el SW controle todo el origin (scope = '/')
        response['Service-Worker-Allowed'] = '/'
        # No cachear el SW para que siempre se obtenga la versión más reciente
        response['Cache-Control'] = 'no-cache, no-store, must-revalidate'
        return response
    return HttpResponse('Service Worker not found.', status=404)

# ✅ Fix 1 — Constantes seguras
AREAS_PERMITIDAS = {'finanzas', 'salud', 'tecnologia'}
MAX_CODIGO_LENGTH = 10000

# ✅ Fix 2 — Cliente Anthropic inicializado una sola vez
def get_anthropic_client():
    api_key = os.getenv('ANTHROPIC_API_KEY')
    if not api_key:
        raise ValueError("ANTHROPIC_API_KEY no está configurada")
    return anthropic.Anthropic(api_key=api_key)


def registro(request):
    if request.method == 'POST':
        username = request.POST.get('username', '').strip()
        email = request.POST.get('email', '').strip()
        password1 = request.POST.get('password1', '')
        password2 = request.POST.get('password2', '')

        # ✅ Fix 3 — Validación de campos vacíos
        if not username or not email or not password1 or not password2:
            messages.error(request, 'Todos los campos son obligatorios')
            return redirect('registro')

        # ✅ Fix 4 — Validación de longitud
        if len(username) < 3 or len(username) > 20:
            messages.error(request, 'El usuario debe tener entre 3 y 20 caracteres')
            return redirect('registro')

        # ✅ Fix 5 — Política de contraseña
        if len(password1) < 8:
            messages.error(request, 'La contraseña debe tener al menos 8 caracteres')
            return redirect('registro')

        if password1 != password2:
            messages.error(request, 'Las contraseñas no coinciden')
            return redirect('registro')

        if User.objects.filter(username=username).exists():
            messages.error(request, 'El usuario ya existe')
            return redirect('registro')

        try:
            user = User.objects.create_user(username=username, email=email, password=password1)
            login(request, user)
            return redirect('dashboard')
        except Exception:
            messages.error(request, 'Error al crear la cuenta, intenta de nuevo')
            return redirect('registro')

    return render(request, 'analyzer/registro.html')


def login_view(request):
    if request.method == 'POST':
        username = request.POST.get('username', '').strip()
        password = request.POST.get('password', '')

        if not username or not password:
            messages.error(request, 'Completa todos los campos')
            return render(request, 'analyzer/login.html')

        user = authenticate(request, username=username, password=password)

        if user is not None:
            login(request, user)
            return redirect('dashboard')
        else:
            messages.error(request, 'Usuario o contraseña incorrectos')

    return render(request, 'analyzer/login.html')


# ✅ Fix 6 — Logout con POST para protección CSRF
@require_POST
def logout_view(request):
    logout(request)
    return redirect('login')


@login_required(login_url='login')
def dashboard(request):
    return render(request, 'analyzer/dashboard.html')


@login_required(login_url='login')
def analizar(request):
    if request.method == 'POST':
        codigo = request.POST.get('codigo', '').strip()
        area = request.POST.get('area', '').strip()

        # ✅ Fix 7 — Whitelist de áreas
        if area not in AREAS_PERMITIDAS:
            messages.error(request, 'Área no válida')
            return redirect('analizar')

        # ✅ Fix 8 — Límite de tamaño
        if len(codigo) > MAX_CODIGO_LENGTH:
            messages.error(request, f'El código no puede superar {MAX_CODIGO_LENGTH} caracteres')
            return redirect('analizar')

        if not codigo:
            messages.error(request, 'El código no puede estar vacío')
            return redirect('analizar')

        prompts = {
            'finanzas': 'Eres un experto en QA para sistemas financieros. Analiza este código buscando vulnerabilidades, errores lógicos y problemas de seguridad típicos en aplicaciones de finanzas como pagos, transferencias o cálculos monetarios.',
            'salud': 'Eres un experto en QA para sistemas de salud digital. Analiza este código buscando vulnerabilidades, errores lógicos y problemas críticos en aplicaciones médicas como expedientes, citas o cálculos de dosis.',
            'tecnologia': 'Eres un experto en QA para sistemas tecnológicos. Analiza este código buscando vulnerabilidades de seguridad, errores lógicos, malas prácticas y posibles fallos en APIs, autenticación o bases de datos.',
        }

        try:
            client = get_anthropic_client()

            # ✅ Fix 9 — Separación clara entre instrucción y datos del usuario
            message = client.messages.create(
                model="claude-sonnet-4-6",
                max_tokens=2048,
                system=prompts[area],
                messages=[
                    {
                        "role": "user",
                        "content": f"Analiza el siguiente código:\n\n```\n{codigo}\n```\n\nProporciona:\n1. Problemas encontrados\n2. Nivel de riesgo (Alto/Medio/Bajo)\n3. Sugerencias de corrección\n4. Código de pruebas para verificar los problemas"
                    }
                ]
            )

            resultado = message.content[0].text

            nuevo = Analisis.objects.create(
                usuario=request.user,
                area=area,
                codigo_original=codigo,
                resultado=resultado
            )

            # Práctica 2.1 — avisa por push (útil si el usuario cambió de pestaña o
            # cerró la app mientras la IA respondía). Si falla, no afecta el análisis.
            try:
                enviar_push(request.user, '✅ Análisis listo',
                            f'Tu análisis de {nuevo.get_area_display()} ya está disponible.',
                            reverse('detalle_analisis', args=[nuevo.id]))
            except Exception:
                pass

            return render(request, 'analyzer/resultado.html', {
                'resultado': resultado,
                'area': area,
                'codigo': codigo
            })

        except ValueError as e:
            messages.error(request, str(e))
            return redirect('analizar')
        except anthropic.AuthenticationError:
            logger.error('Anthropic rechazó la API key (401)')
            messages.error(request, 'La API key de Anthropic no es válida. Revisa ANTHROPIC_API_KEY en el .env.')
            return redirect('analizar')
        except anthropic.PermissionDeniedError:
            logger.error('Anthropic: la API key no tiene permiso (403)')
            messages.error(request, 'La API key de Anthropic no tiene permiso para usar este modelo.')
            return redirect('analizar')
        except anthropic.BadRequestError as e:
            logger.error('Anthropic rechazó la solicitud: %s', e)
            if 'credit balance' in str(e).lower():
                messages.error(request, 'La cuenta de Anthropic no tiene saldo. Agrega créditos en console.anthropic.com.')
            else:
                messages.error(request, 'La IA rechazó la solicitud. Intenta con otro código.')
            return redirect('analizar')
        except anthropic.RateLimitError:
            messages.error(request, 'Se alcanzó el límite de uso de la IA. Espera un momento e intenta de nuevo.')
            return redirect('analizar')
        except Exception:
            logger.exception('Error al llamar a la API de Anthropic')
            messages.error(request, 'Error al conectar con la IA, intenta de nuevo')
            return redirect('analizar')

    return render(request, 'analyzer/analizar.html')


# ─── Historial: SSR vs CSR (Práctica 1.3) ───────────────────────────────────────
# Las dos versiones muestran la misma pantalla. Se permiten en iframe del mismo
# origen para que /comparar/ pueda medirlas.

@xframe_options_sameorigin
@login_required(login_url='login')
def historial(request):
    """SSR: se consulta la BD y el HTML sale del servidor con la lista ya escrita."""
    analisis = Analisis.objects.filter(usuario=request.user).order_by('-fecha')
    return render(request, 'analyzer/historial.html', {'analisis': analisis})


@xframe_options_sameorigin
@login_required(login_url='login')
def historial_csr(request):
    """CSR: solo se manda el cascarón; el navegador pide los datos a api_historial."""
    return render(request, 'analyzer/historial_csr.html')


def api_historial(request):
    """JSON del historial para la versión CSR (mismos campos que muestra la SSR)."""
    if not request.user.is_authenticated:
        return JsonResponse({'error': 'no-autenticado'}, status=401)
    analisis = Analisis.objects.filter(usuario=request.user).order_by('-fecha')
    datos = [{
        'id': a.id,
        'area': a.area,
        'fecha': date_format(timezone.localtime(a.fecha), 'd/m/Y H:i'),
        'codigo': Truncator(a.codigo_original).chars(100),
        'url': reverse('detalle_analisis', args=[a.id]),
    } for a in analisis]
    response = JsonResponse({'analisis': datos})
    response['Cache-Control'] = 'no-store'
    return response


@login_required(login_url='login')
def comparar_render(request):
    """Mide la primera carga de /historial/ (SSR) contra /historial/csr/ (CSR)."""
    return render(request, 'analyzer/comparar.html')


# ─── Notificaciones push y permisos (Práctica 2.1) ──────────────────────────────

@login_required(login_url='login')
def permisos(request):
    """Página para activar notificaciones push y probar la geolocalización."""
    return render(request, 'analyzer/permisos.html', {
        'vapid_public_key': settings.VAPID_PUBLIC_KEY,
        'dispositivos': request.user.suscripciones_push.count(),
    })


def _leer_json(request):
    try:
        return json.loads(request.body or b'{}')
    except ValueError:
        return None


@require_POST
def push_suscribir(request):
    """Guarda la suscripción que generó pushManager.subscribe() en el navegador."""
    if not request.user.is_authenticated:
        return JsonResponse({'error': 'no-autenticado'}, status=401)
    datos = _leer_json(request) or {}
    endpoint = str(datos.get('endpoint', ''))
    llaves = datos.get('keys') or {}
    p256dh, auth = str(llaves.get('p256dh', '')), str(llaves.get('auth', ''))
    if not endpoint.startswith('https://') or len(endpoint) > 500 or not p256dh or not auth \
            or len(p256dh) > 200 or len(auth) > 100:
        return JsonResponse({'error': 'suscripcion-invalida'}, status=400)

    SuscripcionPush.objects.update_or_create(
        endpoint=endpoint,
        defaults={
            'usuario': request.user,
            'p256dh': p256dh,
            'auth': auth,
            'navegador': request.headers.get('User-Agent', '')[:200],
        },
    )
    return JsonResponse({'ok': True, 'dispositivos': request.user.suscripciones_push.count()})


@require_POST
def push_desuscribir(request):
    """Borra la suscripción de este navegador (el usuario desactivó las notificaciones)."""
    if not request.user.is_authenticated:
        return JsonResponse({'error': 'no-autenticado'}, status=401)
    datos = _leer_json(request) or {}
    SuscripcionPush.objects.filter(usuario=request.user, endpoint=str(datos.get('endpoint', ''))).delete()
    return JsonResponse({'ok': True, 'dispositivos': request.user.suscripciones_push.count()})


@require_POST
def push_prueba(request):
    """Envía una notificación push de prueba a todos los dispositivos del usuario."""
    if not request.user.is_authenticated:
        return JsonResponse({'error': 'no-autenticado'}, status=401)
    if not push_configurado():
        return JsonResponse({'error': 'vapid-sin-configurar'}, status=503)
    enviadas = enviar_push(
        request.user,
        '🔔 Notificación de prueba',
        f'Hola {request.user.username}, las notificaciones push de QA Generator funcionan.',
        reverse('historial'),
    )
    if not enviadas:
        return JsonResponse({'error': 'sin-dispositivos'}, status=404)
    return JsonResponse({'ok': True, 'enviadas': enviadas})


@login_required(login_url='login')
def detalle_analisis(request, id):
    # ✅ Fix 10 — get_object_or_404 en lugar de .get() sin manejo
    analisis = get_object_or_404(Analisis, id=id, usuario=request.user)
    return render(request, 'analyzer/detalle.html', {'analisis': analisis})


@login_required(login_url='login')
def descargar_pdf(request, id):
    # ✅ Fix 10 — get_object_or_404
    analisis = get_object_or_404(Analisis, id=id, usuario=request.user)

    response = HttpResponse(content_type='application/pdf')
    # ✅ Fix 11 — Nombre de archivo sin caracteres raros
    response['Content-Disposition'] = f'attachment; filename="reporte_qa_{id}.pdf"'

    doc = SimpleDocTemplate(response, pagesize=letter,
                            rightMargin=inch, leftMargin=inch,
                            topMargin=inch, bottomMargin=inch)

    styles = getSampleStyleSheet()
    elementos = []

    titulo_style = ParagraphStyle('titulo', parent=styles['Title'],
                                   fontSize=22, textColor=colors.HexColor('#4F46E5'),
                                   spaceAfter=6, alignment=TA_CENTER)
    elementos.append(Paragraph("QA Generator - Reporte de Análisis", titulo_style))
    elementos.append(HRFlowable(width="100%", thickness=2, color=colors.HexColor('#4F46E5')))
    elementos.append(Spacer(1, 0.2 * inch))

    info_style = ParagraphStyle('info', parent=styles['Normal'], fontSize=11, spaceAfter=4)
    elementos.append(Paragraph(f"<b>Usuario:</b> {analisis.usuario.username}", info_style))
    elementos.append(Paragraph(f"<b>Área:</b> {analisis.area.capitalize()}", info_style))
    elementos.append(Paragraph(f"<b>Fecha:</b> {analisis.fecha.strftime('%d/%m/%Y %H:%M')}", info_style))
    elementos.append(Spacer(1, 0.3 * inch))

    seccion_style = ParagraphStyle('seccion', parent=styles['Heading2'],
                                    fontSize=13, textColor=colors.HexColor('#1F2937'),
                                    spaceAfter=6)
    elementos.append(Paragraph("Código Analizado", seccion_style))
    elementos.append(HRFlowable(width="100%", thickness=1, color=colors.HexColor('#E5E7EB')))
    elementos.append(Spacer(1, 0.1 * inch))

    codigo_style = ParagraphStyle('codigo', parent=styles['Code'],
                                   fontSize=8, backColor=colors.HexColor('#F9FAFB'),
                                   borderColor=colors.HexColor('#E5E7EB'),
                                   borderWidth=1, borderPadding=8,
                                   spaceAfter=12)

    # ✅ Fix 12 — Escape HTML completo
    codigo_limpio = (analisis.codigo_original
                     .replace('&', '&amp;')
                     .replace('<', '&lt;')
                     .replace('>', '&gt;')
                     .replace('"', '&quot;')
                     .replace("'", '&#x27;'))
    elementos.append(Paragraph(f"<font name='Courier'>{codigo_limpio}</font>", codigo_style))
    elementos.append(Spacer(1, 0.2 * inch))

    elementos.append(Paragraph("Resultado del Análisis IA", seccion_style))
    elementos.append(HRFlowable(width="100%", thickness=1, color=colors.HexColor('#E5E7EB')))
    elementos.append(Spacer(1, 0.1 * inch))

    resultado_style = ParagraphStyle('resultado', parent=styles['Normal'],
                                      fontSize=10, spaceAfter=6, leading=16)

    resultado_limpio = (analisis.resultado
                        .replace('&', '&amp;')
                        .replace('<', '&lt;')
                        .replace('>', '&gt;')
                        .replace('"', '&quot;')
                        .replace("'", '&#x27;')
                        .replace('\n', '<br/>'))
    elementos.append(Paragraph(resultado_limpio, resultado_style))

    doc.build(elementos)
    return response