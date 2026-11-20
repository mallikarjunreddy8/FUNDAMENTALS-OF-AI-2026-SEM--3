// MediGuard service worker: keeps the app working with no internet.
// (Reading text from photos needs internet the first time, to download the OCR model.)
const CACHE = "mediguard-v1";
const FILES = [
  "./", "index.html", "style.css", "app.js", "agent.js", "icon.svg", "manifest.json",
  "data/medicines.js", "data/samples.js",
  "lib/html5-qrcode.min.js", "lib/tesseract.min.js", "lib/worker.min.js",
];

self.addEventListener("install", (e) => {
  e.waitUntil(caches.open(CACHE).then((c) => c.addAll(FILES)).then(() => self.skipWaiting()));
});

self.addEventListener("activate", (e) => {
  e.waitUntil(
    caches.keys()
      .then((keys) => Promise.all(keys.filter((k) => k !== CACHE).map((k) => caches.delete(k))))
      .then(() => self.clients.claim())
  );
});

// Network first (so updates show up), fall back to the cache when offline.
self.addEventListener("fetch", (e) => {
  if (e.request.method !== "GET") return;
  e.respondWith(
    fetch(e.request)
      .then((res) => {
        if (res.ok && (new URL(e.request.url).origin === location.origin || /jsdelivr|tessdata/.test(e.request.url))) {
          const copy = res.clone();
          caches.open(CACHE).then((c) => c.put(e.request, copy));
        }
        return res;
      })
      .catch(() => caches.match(e.request))
  );
});
