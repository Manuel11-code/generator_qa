// =====================================================================
//  Métricas de primera carga (Práctica 1.3 – CSR vs SSR)
//  Se carga en las dos versiones del historial y mide lo mismo en ambas:
//    · TTFB ............... cuándo llegó el primer byte del HTML
//    · FCP ................ primer pintado con contenido (aunque sea un "Cargando…")
//    · Contenido visible .. cuándo la lista del historial ya está en pantalla
//  Cada página llama a QAMetricas.contenidoListo() cuando su lista existe:
//  la versión SSR lo hace al parsear el HTML; la CSR después del fetch.
//  Si la página está dentro de un iframe (página /comparar/), envía los
//  resultados al padre con postMessage.
// =====================================================================

(function () {
  'use strict';

  var modo = document.documentElement.getAttribute('data-render') || '?';
  var datos = { modo: modo, ttfb: 0, fcp: 0, contenido: 0, js: 0, html: 0 };
  var enviado = false;

  function ms(n) { return n ? Math.round(n) + ' ms' : '…'; }

  function completar() {
    var nav = performance.getEntriesByType('navigation')[0] || {};
    datos.ttfb = Math.round(nav.responseStart || 0);
    datos.html = Math.round((nav.decodedBodySize || 0) / 1024 * 10) / 10;
    // KB de JavaScript descargado (sin contar caché del navegador)
    datos.js = Math.round(performance.getEntriesByType('resource')
      .filter(function (r) { return r.initiatorType === 'script' || /\.js(\?|$)/.test(r.name); })
      .reduce(function (s, r) { return s + (r.decodedBodySize || r.transferSize || 0); }, 0) / 1024);
  }

  function pintarBadge() {
    var badge = document.getElementById('metricas-render');
    if (!badge) return;
    badge.innerHTML =
      '<strong>' + modo + '</strong> · TTFB ' + ms(datos.ttfb) +
      ' · FCP ' + ms(datos.fcp) +
      ' · Contenido visible ' + ms(datos.contenido);
  }

  function reportar() {
    if (!datos.fcp || !datos.contenido) return;
    // El contenido no puede verse antes del primer pintado.
    datos.contenido = Math.round(Math.max(datos.contenido, datos.fcp));
    completar();
    pintarBadge();
    if (!enviado && window.parent !== window) {
      enviado = true;
      window.parent.postMessage({ tipo: 'metricas-render', datos: datos }, location.origin);
    }
  }

  // El FCP puede reportarse después del load: se escucha con un observer.
  try {
    new PerformanceObserver(function (lista) {
      lista.getEntries().forEach(function (e) {
        if (e.name === 'first-contentful-paint') { datos.fcp = Math.round(e.startTime); reportar(); }
      });
    }).observe({ type: 'paint', buffered: true });
  } catch (e) { /* navegador sin PerformanceObserver */ }

  window.QAMetricas = {
    contenidoListo: function () {
      if (datos.contenido) return;
      // Se espera al siguiente frame: ahí el contenido ya se pintó.
      requestAnimationFrame(function () {
        datos.contenido = Math.round(performance.now());
        reportar();
      });
    },
  };
})();
