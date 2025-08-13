// Cache the UI shell only; let /api/* requests hit the network for fresh data
const CACHE = 'weather-ui-v1';
const ASSETS = ['/', '/index.html', '/manifest.json'];

self.addEventListener('install', (e) => {
  e.waitUntil(caches.open(CACHE).then((c) => c.addAll(ASSETS)));
});

self.addEventListener('activate', (e) => {
  e.waitUntil(
    caches.keys().then((keys) =>
      Promise.all(keys.filter((k) => k !== CACHE).map((k) => caches.delete(k)))
    )
  );
});

self.addEventListener('fetch', (e) => {
  const req = e.request;
  if (req.method !== 'GET') return;

  const url = new URL(req.url);

  // Do not cache API calls
  if (url.pathname.startsWith('/api/')) return;

  e.respondWith(
    caches.match(req).then((cached) => cached || fetch(req))
  );
});