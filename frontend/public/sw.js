// Cache only the public offline page; never cache API responses or personal data.
self.addEventListener('install', event => event.waitUntil(caches.open('caresignal-public-v1').then(c => c.add('/offline.html'))));
self.addEventListener('fetch', event => { if(event.request.mode === 'navigate') event.respondWith(fetch(event.request).catch(() => caches.match('/offline.html'))); });
