/* Service Worker — das Mindeste, damit der Browser die Anwendung als
   installierbar ansieht.

   Bewusst ohne Zwischenspeicher: OTA ist eine Fernsteuerung. Alles, was hier
   zählt, kommt live über einen Websocket; eine offline zwischengelagerte
   Oberfläche zeigte nur einen Rahmen um nichts. Der Worker existiert für die
   Installierbarkeit und für eine ehrliche Meldung, wenn der Server weg ist. */

self.addEventListener('install', () => self.skipWaiting())
self.addEventListener('activate', (e) => e.waitUntil(self.clients.claim()))

const OFFLINE = `<!doctype html><html lang="de"><head><meta charset="utf-8">
<title>OpenTerminalApps</title><meta name="viewport" content="width=device-width,initial-scale=1">
<style>html,body{height:100%;margin:0;background:#0B1315;color:#E6EDEC;
font-family:Archivo,system-ui,sans-serif;display:grid;place-items:center;text-align:center}
p{color:#8AA1A5;max-width:34ch;line-height:1.5}</style></head><body><div>
<h1 style="font-weight:500">Kein Kontakt zum Server</h1>
<p>OpenTerminalApps ist gerade nicht erreichbar. Deine Dateien im Arbeitsplatz
sind davon nicht betroffen.</p></div></body></html>`

self.addEventListener('fetch', (event) => {
  const req = event.request
  // Nur die Navigation abfangen. Alles andere — API, Streams, Websockets —
  // geht unangetastet ans Netz.
  if (req.mode !== 'navigate') return
  event.respondWith(
    fetch(req).catch(() => new Response(OFFLINE, {
      status: 503,
      headers: { 'Content-Type': 'text/html; charset=utf-8' },
    })),
  )
})
