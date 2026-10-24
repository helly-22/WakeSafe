/*
 * WakeSafe service worker (template).
 *
 * Do not edit dist/sw.js: pwa/precachePlugin.ts generates it at build time by
 * filling in the two placeholders below. It is not registered in `vite dev`.
 *
 * Strategy:
 *  - Precache the app shell and every built asset so the demo works offline
 *    after one visit.
 *  - Page navigations are answered with the cached shell (SPA routing), so deep
 *    links like /sleep work offline and without host rewrite rules.
 *  - Same-origin GETs are cache-first from the precache.
 *  - /api/ requests are never intercepted or cached: future API responses may
 *    contain health data and must not be stored by the service worker.
 */
const CACHE = 'wakesafe-__CACHE_VERSION__';
const PRECACHE = __PRECACHE_MANIFEST__;
const SHELL = '/index.html';

self.addEventListener('install', (event) => {
  event.waitUntil(
    caches
      .open(CACHE)
      .then((cache) => cache.addAll(PRECACHE))
      .then(() => self.skipWaiting()),
  );
});

self.addEventListener('activate', (event) => {
  event.waitUntil(
    caches
      .keys()
      .then((keys) =>
        Promise.all(keys.filter((k) => k.startsWith('wakesafe-') && k !== CACHE).map((k) => caches.delete(k))),
      )
      .then(() => self.clients.claim()),
  );
});

self.addEventListener('fetch', (event) => {
  const request = event.request;
  if (request.method !== 'GET') return;

  const url = new URL(request.url);
  if (url.origin !== self.location.origin) return;
  if (url.pathname.startsWith('/api/')) return;

  if (request.mode === 'navigate') {
    event.respondWith(caches.match(SHELL).then((shell) => shell || fetch(request)));
    return;
  }

  event.respondWith(caches.match(request).then((hit) => hit || fetch(request)));
});
