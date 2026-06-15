{% load static %}
// Compass service worker. Served from / so its scope covers the whole app.
// Deliberately minimal: we cache only the public shell (offline page + static
// assets) and never store authenticated, user-specific pages — so the cache can
// never leak one adjudicator's tournament list to another on a shared device.
//
// We deliberately do NOT cache any page containing a form: a cached page bakes
// in its CSRF token, and serving it later (with a rotated cookie) makes every
// submit fail with a 403. The offline fallback is a token-free page instead.

const CACHE = "compass-v6";
const SHELL = [
  "/offline/",
  "{% static 'css/app.css' %}",
  "{% static 'icons/icon-192.png' %}",
  "{% static 'js/jsqr.js' %}",
  "{% static 'js/qr-scan.js' %}",
  "{% static 'js/guest.js' %}",
  "{% static 'js/pull-refresh.js' %}"
];

self.addEventListener("install", (event) => {
  event.waitUntil(
    caches.open(CACHE).then((cache) => cache.addAll(SHELL)).then(() => self.skipWaiting())
  );
});

self.addEventListener("activate", (event) => {
  event.waitUntil(
    caches.keys()
      .then((keys) => Promise.all(keys.filter((k) => k !== CACHE).map((k) => caches.delete(k))))
      .then(() => self.clients.claim())
  );
});

self.addEventListener("fetch", (event) => {
  const request = event.request;
  if (request.method !== "GET") return;

  const url = new URL(request.url);
  if (url.origin !== self.location.origin) return;

  // Page navigations: always go to the network for fresh data; if offline, show
  // the offline page (which keeps the user's URL, so its retry button re-attempts
  // the original navigation — e.g. a /go/ redirect to Tabbycat).
  if (request.mode === "navigate") {
    event.respondWith(fetch(request).catch(() => caches.match("/offline/")));
    return;
  }

  // Static assets: cache-first.
  if (url.pathname.startsWith("/static/")) {
    event.respondWith(caches.match(request).then((hit) => hit || fetch(request)));
  }
});
