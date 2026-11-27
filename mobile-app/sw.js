// SangoDiag service worker: keeps the whole app on the phone so it opens and decides with no network.
// Bump VERSION whenever a file changes, so phones pick up the new copy on their next connection.
const VERSION = "sangodiag-v0.2.2";
const APP_FILES = [
  "./",
  "./index.html",
  "./app.css",
  "./manifest.webmanifest",
  "./js/app.js",
  "./js/triage.js",
  "./js/i18n.js",
  "./js/register.js",
  "./js/data.js",
  "./js/store.js",
  "./js/records.js",
  "./icons/logo.svg",
  "./icons/icon-192.png",
  "./icons/icon-512.png",
  "./icons/maskable-512.png",
];

self.addEventListener("install", (event) => {
  // Cache file by file, so one missing file (e.g. icons not built locally) never blocks offline use.
  event.waitUntil(
    caches.open(VERSION)
      // cache: "reload" skips the browser's HTTP cache, so a new version never mixes with old files.
      .then((c) => Promise.all(APP_FILES.map((f) => c.add(new Request(f, { cache: "reload" })).catch(() => null))))
      .then(() => self.skipWaiting()),
  );
});

self.addEventListener("activate", (event) => {
  event.waitUntil(
    caches.keys()
      .then((keys) => Promise.all(keys.filter((k) => k !== VERSION).map((k) => caches.delete(k))))
      .then(() => self.clients.claim()),
  );
});

self.addEventListener("fetch", (event) => {
  const req = event.request;
  if (req.method !== "GET") return;
  const url = new URL(req.url);
  // Calls to the SangoDiag server (another origin) always go to the network.
  if (url.origin !== self.location.origin) return;

  // App files: answer from the phone first (instant, works offline), refresh in the background.
  event.respondWith(
    caches.open(VERSION).then(async (cache) => {
      const cached = await cache.match(req, { ignoreSearch: true });
      const network = fetch(req)
        .then((res) => { if (res.ok) cache.put(req, res.clone()); return res; })
        .catch(() => null);
      if (cached) { event.waitUntil(network); return cached; }
      const res = await network;
      if (res) return res;
      if (req.mode === "navigate") return cache.match("./index.html");
      return new Response("Offline", { status: 503, statusText: "Offline" });
    }),
  );
});
