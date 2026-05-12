/* Daily Intelligence — Service Worker (v1)
   전략:
   - 정적 자산(CSS/JS/이미지): cache-first
   - HTML/JSON: network-first (매일 콘텐츠가 바뀜), 오프라인 시 캐시 fallback
*/
'use strict';

var CACHE = 'di-v3';
var BASE  = self.registration.scope; // "https://tigerjk9.github.io/Live-Artifact/"

var PRECACHE = [
  BASE,
  BASE + 'index.html',
  BASE + 'assets/style.css',
  BASE + 'assets/app.js',
  BASE + 'assets/manifest.json',
  BASE + 'assets/facilitator.png',
];

/* ── Install: 정적 자산 선캐시 ─────────────────── */
self.addEventListener('install', function (e) {
  e.waitUntil(
    caches.open(CACHE).then(function (c) { return c.addAll(PRECACHE); })
  );
  self.skipWaiting();
});

/* ── Activate: 구버전 캐시 정리 ────────────────── */
self.addEventListener('activate', function (e) {
  e.waitUntil(
    caches.keys().then(function (keys) {
      return Promise.all(
        keys.filter(function (k) { return k !== CACHE; }).map(function (k) { return caches.delete(k); })
      );
    })
  );
  self.clients.claim();
});

/* ── Fetch ──────────────────────────────────────── */
self.addEventListener('fetch', function (e) {
  var url = e.request.url;

  // 다른 오리진 요청(CDN 폰트 등)은 그냥 통과
  if (url.indexOf(self.location.origin) !== 0) return;

  var isHtmlOrJson = /\.(html|json)$/.test(url) || url === BASE || url.endsWith('/');

  if (isHtmlOrJson) {
    // network-first: 최신 콘텐츠 우선, 실패 시 캐시 fallback
    e.respondWith(
      fetch(e.request)
        .then(function (r) {
          var clone = r.clone();
          caches.open(CACHE).then(function (c) { c.put(e.request, clone); });
          return r;
        })
        .catch(function () { return caches.match(e.request); })
    );
  } else {
    // cache-first: 정적 자산
    e.respondWith(
      caches.match(e.request).then(function (cached) {
        return cached || fetch(e.request).then(function (r) {
          var clone = r.clone();
          caches.open(CACHE).then(function (c) { c.put(e.request, clone); });
          return r;
        });
      })
    );
  }
});
