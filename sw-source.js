// Hors-Sol · service worker : uniquement pour le rappel de 18 h (aucune mise en cache du site).
// Généré en sw.js par build.py (ne pas modifier sw.js à la main).
const API = "__API_LIGUES__";
self.addEventListener("install", () => self.skipWaiting());
self.addEventListener("activate", e => e.waitUntil(self.clients.claim()));
self.addEventListener("push", e => {
  e.waitUntil((async () => {
    let msg = {title: "Hors-Sol · plus que 6 h !", body: "🛒 Votre défi du jour vous attend. La caisse ferme à minuit !", url: "/?src=rappel"};
    try {
      const c = await caches.open("horssol-sw");
      const r = await c.match("/pid");
      const pid = r ? await r.text() : "";
      const x = await fetch(API + "/rappel?pid=" + encodeURIComponent(pid));
      if (x.ok) msg = Object.assign(msg, await x.json());
    } catch (err) {}
    await self.registration.showNotification(msg.title, {body: msg.body, icon: "assets/icon-192.png", badge: "assets/icon-192.png", tag: "rappel-hors-sol", data: {url: msg.url}});
  })());
});
self.addEventListener("notificationclick", e => {
  e.notification.close();
  const url = (e.notification.data && e.notification.data.url) || "/?src=rappel";
  e.waitUntil((async () => {
    const wins = await self.clients.matchAll({type: "window", includeUncontrolled: true});
    for (const w of wins){ try { await w.navigate(url); return w.focus(); } catch (err) {} }
    return self.clients.openWindow(url);
  })());
});
