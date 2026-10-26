# Prácticas PWA – QA Generator

## Práctica 1.2 – Service Workers

| Pieza | Archivo | Qué hace |
|---|---|---|
| Manifest | `analyzer/static/analyzer/manifest.json` | Nombre, íconos (`any` y `maskable` por separado), colores, `id`, `start_url`, accesos directos. Permite instalar la app. |
| Service Worker | `analyzer/static/analyzer/sw.js` (servido en `/sw.js` por `views.service_worker`) | Corre en segundo plano: caché, modo sin conexión, notificaciones push y background sync. |
| Registro | `analyzer/templates/analyzer/base.html` | Registra `/sw.js` con scope `/` y avisa cuando hay una versión nueva. |
| Página offline | `analyzer/static/analyzer/offline.html` | Se muestra si no hay red y la página no está en caché. |

### Estrategias de caché

| Tipo de petición | Estrategia | Motivo |
|---|---|---|
| `/static/`, Tailwind CDN, Google Fonts | **Cache First** | No cambian; se sirven al instante sin red. |
| Páginas HTML (navegación) | **Network First** → caché → `offline.html` | Siempre datos frescos; sin red se ve la última versión guardada. |
| `/api/`, `/admin/`, `/analizar/`, `/logout/`, POST | **Solo red** | Datos del usuario y formularios con token CSRF. |

### Optimización de rendimiento
- **Precaché** en `install` de los recursos públicos (íconos, manifest, offline, fuentes, Tailwind).
- **Navigation Preload**: la petición de la página arranca mientras el SW despierta.
- **Versionado de cachés** (`CACHE_VERSION`): en `activate` se borran las versiones viejas.
- **Límite de entradas** en la caché dinámica (`MAX_DYNAMIC_ENTRIES`).
- **Privacidad**: al cerrar sesión (`POST /logout/`) se borra la caché de páginas.
- **Actualización controlada**: la versión nueva espera hasta que el usuario acepta (`SKIP_WAITING`).

### Correcciones respecto a la versión anterior
1. Se precacheaban `/dashboard/`, `/analizar/` e `/historial/`. Esas páginas requieren login y, sin sesión, se guardaba la **redirección al login** en lugar de la página.
2. El mensaje `SKIP_WAITING` no tenía listener en el SW, así que el botón de "Actualizar" no hacía nada.
3. Al instalar por primera vez, `controllerchange` recargaba la página sin necesidad.
4. Las páginas privadas quedaban en caché después de cerrar sesión.
5. Los íconos usaban `"purpose": "any maskable"` juntos (Chrome lo desaconseja); ahora hay un ícono `maskable` propio.

---

## Práctica 1.3 – Renderizado del lado del servidor (SSR)

### 1. Diferencias entre CSR y SSR

| | **CSR** (Client-Side Rendering) | **SSR** (Server-Side Rendering) |
|---|---|---|
| ¿Quién arma el HTML? | El navegador, con JavaScript | El servidor (Django + plantillas) |
| Qué llega en la primera respuesta | Un "cascarón" vacío + JS | La página completa con los datos |
| Pasos hasta ver el contenido | HTML → descargar JS → ejecutar → `fetch` a la API → pintar | HTML → pintar |
| Carga inicial | Más lenta: suma una ida y vuelta extra a la API y el tiempo de ejecutar JS | Más rápida: el contenido aparece en el primer pintado |
| SEO | Malo: un buscador que no ejecuta JS ve la página vacía | Bueno: el contenido ya está en el HTML |
| Navegación posterior | Rápida (solo se piden datos) | Cada página se pide completa |
| Carga del servidor | Menor (solo entrega JSON) | Mayor (arma el HTML en cada petición) |

### 2. Vista renderizada en el servidor
La misma pantalla (el **historial de análisis**) existe en dos versiones:

- **SSR – `/historial/`** (`views.historial` + `historial.html`): Django consulta la base de datos y responde con el HTML de la lista ya escrito.
- **CSR – `/historial/csr/`** (`views.historial_csr` + `historial_csr.html`): el servidor solo manda el cascarón con "Cargando…"; el JavaScript pide `/api/historial/` (`views.api_historial`) y arma las tarjetas en el navegador.

Ambas usan los mismos estilos y muestran los mismos datos. Cada una trae una barra inferior con sus métricas (`analyzer/static/analyzer/js/metricas.js`).

### 3. Comparación de tiempos de primera carga
La página **`/comparar/`** (menú "CSR vs SSR") carga cada versión varias veces de forma alternada y promedia:

- **TTFB**: tiempo hasta el primer byte del HTML.
- **FCP**: primer pintado con contenido (en CSR suele ser el "Cargando…").
- **Contenido visible**: cuándo la lista del historial ya está en pantalla.
- **Tamaño del HTML inicial** y **cuántos análisis trae el HTML** (lo que ve un buscador).

Resultados de una prueba local (servidor de desarrollo, 12 análisis, 5 cargas por versión, sin limitar la red):

| Métrica (promedio) | CSR | SSR | Gana |
|---|---|---|---|
| TTFB | 15 ms | 17 ms | Empate práctico (SSR consulta la BD antes de responder) |
| FCP | 74 ms | 78 ms | Empate práctico |
| **Contenido visible** | **98 ms** | **78 ms** | **SSR (~20 % antes)** |
| Tamaño del HTML inicial | 9.9 KB | 17.5 KB | CSR (pero sin datos) |
| Análisis presentes en el HTML (SEO) | **0** | **12** | **SSR** |

> En local la red es instantánea, por eso las diferencias son pequeñas. Para el reporte conviene repetir la prueba con **DevTools → Network → "Fast 4G" o "Slow 4G"** y con **Lighthouse** (pestaña Lighthouse → Performance): la ida y vuelta extra de CSR a `/api/historial/` hace que la diferencia en "contenido visible" crezca con la latencia.

Además, `Ver código fuente` (Ctrl+U) en cada versión muestra la diferencia de SEO: en `/historial/` aparecen las tarjetas; en `/historial/csr/` solo "Cargando…".

### 4. ¿Qué estrategia conviene en cada parte de la PWA?

| Parte de QA Generator | Estrategia | Por qué |
|---|---|---|
| Login, registro | **SSR** | Deben verse al instante y funcionar sin JS; Django ya maneja CSRF y mensajes. |
| Historial y detalle de un análisis | **SSR** (+ caché del SW) | Es contenido que se lee; aparece en el primer pintado y queda disponible sin conexión. |
| Exportar PDF | **Servidor** | Se genera con ReportLab en el backend. |
| Formulario "Analizar" | **SSR + mejora con JS** | La página se sirve armada; con JS se puede mostrar progreso mientras responde la IA sin recargar. |
| Comparador, filtros, búsquedas en el historial | **CSR** | Son interacciones dentro de la página; solo se piden datos JSON. |
| Shell de la PWA (íconos, estilos, offline) | **Service Worker** | Precaché para que la app abra incluso sin red. |

**Conclusión:** para la primera carga y el SEO conviene SSR (el contenido llega listo en el HTML). CSR conviene para lo interactivo una vez cargada la página. En esta app la mejor combinación es SSR con Django para las pantallas y el Service Worker para la velocidad en visitas repetidas y el modo sin conexión.

> Recomendación extra: `cdn.tailwindcss.com` genera el CSS **en el navegador** (es CSR de los estilos) y la misma librería avisa que no debe usarse en producción. Compilar Tailwind con su CLI a un `.css` estático mejoraría el FCP de todas las páginas.

---

## Práctica 2.1 – Notificaciones push y acceso a características del dispositivo

Todo se prueba en **`/permisos/`** (menú "Permisos").

### 1. ¿Para qué sirven las notificaciones push y cómo es el flujo de suscripción?
Las notificaciones push permiten que el **servidor** le avise algo al usuario **aunque la PWA esté cerrada**. En QA Generator se usa para avisar "✅ Análisis listo" cuando la IA termina un análisis, por si el usuario cambió de pestaña o cerró la app mientras esperaba.

Intervienen cuatro piezas:

| Pieza | Dónde está |
|---|---|
| **Llaves VAPID** (identifican a nuestro servidor ante el servicio push) | `.env` → `VAPID_PUBLIC_KEY` / `VAPID_PRIVATE_KEY`. Se generan con `python manage.py generar_vapid` (`analyzer/management/commands/generar_vapid.py`). |
| **Servicio push del navegador** (FCM de Google, Mozilla Push, Apple Push) | Externo; lo elige el navegador. |
| **Servidor** (guarda suscripciones y envía) | Modelo `SuscripcionPush` (`analyzer/models.py`), vistas `push_suscribir`, `push_desuscribir`, `push_prueba` (`analyzer/views.py`) y `analyzer/push.py` (envío con `pywebpush`). |
| **Service Worker** (recibe y muestra) | `sw.js` → eventos `push` y `notificationclick`. |

**Flujo de suscripción:**
```
 Usuario pulsa "Activar"
   │
   ├─1─▶ Notification.requestPermission()          → el navegador pregunta: Permitir / Bloquear
   │
   ├─2─▶ pushManager.subscribe({applicationServerKey: VAPID_PUBLIC_KEY})
   │        → el navegador crea una suscripción: { endpoint, keys: { p256dh, auth } }
   │
   └─3─▶ POST /api/push/suscribir/                 → Django la guarda en SuscripcionPush

 Envío (push de prueba o "Análisis listo"):
   Django ──(cifra con p256dh/auth + firma con VAPID)──▶ endpoint (FCM/Mozilla/Apple)
          ──▶ dispositivo ──▶ sw.js evento 'push' ──▶ showNotification()
   Clic en la notificación ──▶ sw.js 'notificationclick' ──▶ abre /historial/ o el análisis
```
El mensaje va **cifrado**: el servicio push (Google, Mozilla) solo lo transporta y no puede leerlo; solo el navegador suscrito lo descifra.

### 2. Solicitud de permiso y push de prueba
- **Permiso:** botón **"Activar notificaciones"** → `Notification.requestPermission()` (`permisos.html`). Se pide **solo tras un clic del usuario**, nunca al cargar la página.
- **Push de prueba:** botón **"Enviar push de prueba"** → `POST /api/push/prueba/` → `enviar_push()` envía "🔔 Notificación de prueba" a todos los dispositivos del usuario.
- **Push real de la app:** al terminar un análisis en `/analizar/` se envía "✅ Análisis listo" con enlace al detalle.
- **Desactivar:** `subscription.unsubscribe()` + `POST /api/push/desuscribir/`.
- Si el servicio push responde **404/410** (suscripción vencida o el usuario revocó el permiso), se borra de la base de datos.

### 3. Característica nativa: geolocalización
Tarjeta **"📍 Ubicación"** → botón **"Obtener mi ubicación"** → `navigator.geolocation.getCurrentPosition()`.
- Muestra latitud, longitud, precisión y un enlace al mapa.
- **Respeta los permisos:** solo se pide tras un clic, solo en esta pantalla y **no se envía al servidor**.
- Maneja los tres errores de la API: `1` permiso negado, `2` ubicación no disponible, `3` tiempo agotado.

### 4. Comportamiento al conceder o negar
La página usa la **Permissions API** (`navigator.permissions.query`) para mostrar el estado de cada permiso con una etiqueta (**Sin decidir / Permitido / Bloqueado**). Si el usuario lo cambia desde la configuración del navegador, la etiqueta se actualiza sola (`onchange`). Cada acción queda escrita en el **"Registro de eventos"** de la página.

| Caso | Notificaciones | Ubicación |
|---|---|---|
| **Sin decidir** (`default` / `prompt`) | "Activar" habilitado; al pulsarlo aparece el aviso del navegador. | Al pulsar "Obtener" aparece el aviso del navegador. |
| **Concedido** (`granted`) | Se crea la suscripción y se guarda en el servidor; se habilitan "Enviar prueba" y "Desactivar". | Se muestran las coordenadas. |
| **Negado** (`denied`) | No se crea suscripción, "Activar" queda deshabilitado y se explica cómo reactivarlo (candado → Notificaciones → Permitir). **La app sigue funcionando.** | Error código 1: se explica cómo permitirla; el resto de la app funciona igual. |
| **Cerró el aviso sin elegir** | Sigue en "Sin decidir"; se puede volver a preguntar. | — |
| **Navegador sin soporte / sin HTTPS** | "No disponible", con el motivo. | "No disponible". |

**Verificación realizada**
- **Permiso negado:** probado en navegador, con notificaciones y ubicación bloqueadas. Se muestran "Bloqueado", los mensajes de ayuda y el registro de eventos, sin errores.
- **Servidor:** 9 pruebas automáticas (`python manage.py test analyzer`). Simulan un navegador con llaves reales y comprueban:
  - que la suscripción se guarda y no se duplica;
  - que se rechazan suscripciones inválidas;
  - que hace falta haber iniciado sesión;
  - que el mensaje va **firmado con VAPID y cifrado** (`aes128gcm`) y que solo el navegador puede descifrarlo;
  - que se borran las suscripciones vencidas (410);
  - que la app responde bien cuando faltan las llaves.

**Cómo probarlo en un dispositivo real**
1. `python manage.py runserver` y abrir `http://localhost:8000/permisos/` en Chrome o Edge.
2. **Conceder:** "Activar notificaciones" → Permitir → "Enviar push de prueba". Aparece la notificación del sistema; al hacer clic abre el historial. Luego "Obtener mi ubicación" → Permitir.
3. **Negar:** en el candado de la barra de direcciones pon Notificaciones y Ubicación en **Bloquear** (la etiqueta cambia sola), o usa una ventana de incógnito y elige "Bloquear".
4. **Celular:** los permisos requieren **HTTPS**. Para probar desde el teléfono, expón el servidor con un túnel HTTPS (por ejemplo `ngrok http 8000`) y agrega ese dominio a `ALLOWED_HOSTS` y a `CSRF_TRUSTED_ORIGINS`. En iPhone, primero instala la PWA en la pantalla de inicio (iOS 16.4+).
5. **DevTools:** en Application → Service Workers puedes escribir un texto en **Push** para simular un mensaje y ver cómo lo muestra `sw.js`.
