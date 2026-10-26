// =====================================================================
//  QA Generator - Service Worker
//  Estrategias:
//    · Navegación (HTML) ........ Network First → caché → offline.html
//    · /static/ y CDNs .......... Cache First (CSS, JS, fuentes, íconos)
//    · /api/, /admin/, POST ..... siempre a la red (nunca se cachean)
//  Al cerrar sesión se borra la caché de páginas (contiene datos del usuario).
// =====================================================================

const CACHE_VERSION = 'v4';
const STATIC_CACHE  = `qa-generator-static-${CACHE_VERSION}`;
const DYNAMIC_CACHE = `qa-generator-dynamic-${CACHE_VERSION}`;
const OFFLINE_URL   = '/static/analyzer/offline.html';
const MAX_DYNAMIC_ENTRIES = 40;

// Solo recursos públicos: las páginas con login NO se precargan, porque sin
// sesión el servidor responde con una redirección al login y eso quedaría
// guardado en lugar de la página real.
const PRECACHE_ASSETS = [
  OFFLINE_URL,
  '/static/analyzer/manifest.json',
  '/static/analyzer/icons/icon-192x192.png',
  '/static/analyzer/icons/icon-512x512.png',
  '/static/analyzer/icons/maskable-512x512.png',
  '/static/analyzer/js/metricas.js',
  'https://cdn.tailwindcss.com',
  'https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700&display=swap',
];

// URLs que NO deben cachearse nunca
const NEVER_CACHE = [
  '/admin/',
  '/logout/',
  '/analizar/',   // formulario con token CSRF – siempre fresco
  '/api/',        // datos JSON del usuario
  '/sw.js',
];

// ─── Utilidades ───────────────────────────────────────────────────────────────

function shouldNeverCache(url) {
  return url.origin === self.location.origin && NEVER_CACHE.some(p => url.pathname.startsWith(p));
}

function isStaticAsset(url) {
  return (url.origin === self.location.origin && url.pathname.startsWith('/static/')) ||
    url.hostname === 'cdn.tailwindcss.com' ||
    url.hostname === 'fonts.googleapis.com' ||
    url.hostname === 'fonts.gstatic.com';
}

// Las respuestas de otros dominios sin CORS llegan "opaque" (status 0).
function isCacheable(response) {
  return response && (response.ok || response.type === 'opaque') && !response.redirected;
}

async function trimCache(cacheName, maxEntries) {
  const cache = await caches.open(cacheName);
  const keys = await cache.keys();
  for (let i = 0; i < keys.length - maxEntries; i++) {
    await cache.delete(keys[i]);
  }
}

// ─── Instalación ──────────────────────────────────────────────────────────────

self.addEventListener('install', event => {
  console.log('[SW] Installing Service Worker...');
  event.waitUntil(
    caches.open(STATIC_CACHE).then(cache =>
      // Uno a uno para no fallar si alguno no está disponible
      Promise.allSettled(
        PRECACHE_ASSETS.map(url =>
          cache.add(url).catch(err => console.warn(`[SW] Could not pre-cache: ${url}`, err))
        )
      )
    )
  );
  // No se llama a skipWaiting(): si ya hay una versión controlando la página,
  // la nueva espera a que el usuario acepte actualizar (ver base.html).
});

// ─── Activación ───────────────────────────────────────────────────────────────

self.addEventListener('activate', event => {
  console.log('[SW] Activating Service Worker...');
  event.waitUntil((async () => {
    const cacheNames = await caches.keys();
    await Promise.all(
      cacheNames
        .filter(name => name.startsWith('qa-generator-') && name !== STATIC_CACHE && name !== DYNAMIC_CACHE)
        .map(name => {
          console.log(`[SW] Deleting old cache: ${name}`);
          return caches.delete(name);
        })
    );
    // Navigation Preload: la petición de la página arranca mientras el SW despierta.
    if (self.registration.navigationPreload) {
      await self.registration.navigationPreload.enable();
    }
    await self.clients.claim();
  })());
});

// ─── Mensajes desde la página ─────────────────────────────────────────────────

self.addEventListener('message', event => {
  if (!event.data) return;
  if (event.data.type === 'SKIP_WAITING') self.skipWaiting();
  if (event.data.type === 'CLEAR_USER_CACHE') event.waitUntil(caches.delete(DYNAMIC_CACHE));
});

// ─── Estrategia de fetch ───────────────────────────────────────────────────────

self.addEventListener('fetch', event => {
  const { request } = event;
  const url = new URL(request.url);

  // Ignorar solicitudes que no sean http/https
  if (!url.protocol.startsWith('http')) return;

  // Cerrar sesión: se borran las páginas privadas guardadas y se deja pasar.
  if (request.method === 'POST' && url.pathname === '/logout/') {
    event.waitUntil(caches.delete(DYNAMIC_CACHE));
    return;
  }

  // Sólo interceptar GET
  if (request.method !== 'GET') return;

  if (isStaticAsset(url)) {
    // ── Cache First para assets estáticos ──────────────────────────
    event.respondWith(cacheFirst(request));
  } else if (request.mode === 'navigate') {
    // ── Network First para navegación (páginas HTML) ────────────────
    // ?medir= son las cargas de prueba de /comparar/: no se guardan.
    const saveToCache = !shouldNeverCache(url) && !url.searchParams.has('medir');
    event.respondWith(networkFirst(event, saveToCache));
  }
  // El resto (API, admin, etc.) va directo a la red.
});

// ─── Cache First ──────────────────────────────────────────────────────────────

async function cacheFirst(request) {
  const cached = await caches.match(request);
  if (cached) return cached;

  try {
    const networkResponse = await fetch(request);
    if (isCacheable(networkResponse)) {
      const cache = await caches.open(STATIC_CACHE);
      cache.put(request, networkResponse.clone());
    }
    return networkResponse;
  } catch (err) {
    console.warn('[SW] Cache First - network error, no cache available', err);
    return new Response('', { status: 503, statusText: 'Service Unavailable' });
  }
}

// ─── Network First ────────────────────────────────────────────────────────────

async function networkFirst(event, saveToCache) {
  const { request } = event;
  try {
    const networkResponse = (await event.preloadResponse) || (await fetch(request));
    if (saveToCache && isCacheable(networkResponse)) {
      const cache = await caches.open(DYNAMIC_CACHE);
      await cache.put(request, networkResponse.clone());
      trimCache(DYNAMIC_CACHE, MAX_DYNAMIC_ENTRIES);
    }
    return networkResponse;
  } catch (err) {
    console.warn('[SW] Network First - offline, trying cache...', err);
    const cached = await caches.match(request);
    if (cached) return cached;
    return (await caches.match(OFFLINE_URL)) ||
      new Response('Sin conexión', { status: 503, headers: { 'Content-Type': 'text/plain; charset=utf-8' } });
  }
}

// ─── Push Notifications ───────────────────────────────────────────────────────

self.addEventListener('push', event => {
  console.log('[SW] Push notification received');

  let data = {
    title: 'QA Generator',
    body: 'Tienes una actualización pendiente.',
    icon: '/static/analyzer/icons/icon-192x192.png',
    badge: '/static/analyzer/icons/icon-192x192.png',
    tag: 'qa-generator-notification',
    renotify: true,
  };

  if (event.data) {
    try {
      Object.assign(data, event.data.json());
    } catch (e) {
      data.body = event.data.text();
    }
  }

  const options = {
    body: data.body,
    icon: data.icon,
    badge: data.badge,
    tag: data.tag,
    renotify: data.renotify,
    data: { url: data.url || '/historial/' },
    actions: [
      { action: 'open',    title: 'Abrir App' },
      { action: 'dismiss', title: 'Descartar'  },
    ],
    vibrate: [100, 50, 100],
  };

  event.waitUntil(
    self.registration.showNotification(data.title, options)
  );
});

self.addEventListener('notificationclick', event => {
  event.notification.close();

  if (event.action === 'dismiss') return;

  const targetUrl = new URL((event.notification.data && event.notification.data.url) || '/', self.location.origin).href;

  event.waitUntil(
    clients.matchAll({ type: 'window', includeUncontrolled: true })
      .then(clientList => {
        for (const client of clientList) {
          if (client.url === targetUrl && 'focus' in client) {
            return client.focus();
          }
        }
        if (clients.openWindow) {
          return clients.openWindow(targetUrl);
        }
      })
  );
});

// ─── Background Sync ──────────────────────────────────────────────────────────

self.addEventListener('sync', event => {
  console.log(`[SW] Background Sync triggered: ${event.tag}`);

  if (event.tag === 'sync-pending-analysis') {
    event.waitUntil(syncPendingAnalysis());
  }
});

async function syncPendingAnalysis() {
  try {
    // Recuperar solicitudes pendientes guardadas en IndexedDB (si las hay)
    // Esta función puede expandirse según la lógica de negocio
    console.log('[SW] Syncing pending analysis requests...');
    // Aquí iría la lógica para reenviar solicitudes fallidas
  } catch (err) {
    console.error('[SW] Background sync failed:', err);
  }
}
