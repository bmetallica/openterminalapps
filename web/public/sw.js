/* Service Worker — das Mindeste, damit der Browser die Anwendung als
   installierbar ansieht.

   Bewusst ohne Zwischenspeicher: OTA ist eine Fernsteuerung. Alles, was hier
   zählt, kommt live über einen Websocket; eine offline zwischengelagerte
   Oberfläche zeigte nur einen Rahmen um nichts. Der Worker existiert für die
   Installierbarkeit und für eine ehrliche Meldung, wenn der Server weg ist.

   **Keine Sackgasse** (2026-11-02): Die Meldung kam auch, wenn nur kurz das
   Netz fehlte — typisch, wenn der Rechner aus dem Ruhezustand kommt und das
   WLAN noch nicht steht, die Anmeldung inzwischen abgelaufen war und der
   Browser zur Anmeldung wollte. Die Seite blieb dann stehen. Jetzt versucht
   der Worker es erst ein zweites Mal, und die Seite lädt von selbst neu,
   sobald das Netz zurück ist; dazu ein Knopf und der Weg zur Anmeldung. */

self.addEventListener('install', () => self.skipWaiting())
self.addEventListener('activate', (e) => e.waitUntil(self.clients.claim()))

const OFFLINE = `<!doctype html><html lang="de"><head><meta charset="utf-8">
<title>OpenTerminalApps</title><meta name="viewport" content="width=device-width,initial-scale=1">
<style>html,body{height:100%;margin:0;background:#0B1315;color:#E6EDEC;
font-family:Archivo,system-ui,sans-serif;display:grid;place-items:center;text-align:center}
p{color:#8AA1A5;max-width:36ch;line-height:1.5;margin:0 auto 14px}
a,button{font:inherit;color:#0B1315;background:#06B6D4;border:0;border-radius:7px;padding:8px 14px;
margin:4px;cursor:pointer;text-decoration:none;display:inline-block}
a.leise{background:transparent;color:#8AA1A5;border:1px solid #334155}</style></head><body><div>
<h1 style="font-weight:500" id="t">Kein Kontakt zum Server</h1>
<p id="p">OpenTerminalApps ist gerade nicht erreichbar. Deine Dateien im Arbeitsplatz
sind davon nicht betroffen. Die Seite versucht es von selbst wieder.</p>
<button id="b" onclick="location.reload()">Erneut versuchen</button>
<a class="leise" id="a" href="/">Zur Anmeldung</a></div>
<script>
if (!/^de/i.test(navigator.language || '')) {
  document.documentElement.lang = 'en'
  document.getElementById('t').textContent = 'No contact with the server'
  document.getElementById('p').textContent = 'OpenTerminalApps cannot be reached right now. The files in your workspace are not affected. The page tries again by itself.'
  document.getElementById('b').textContent = 'Try again'
  document.getElementById('a').textContent = 'To the sign-in'
}
var n = 0
function nochmal() {
  n++
  fetch('/healthz', { cache: 'no-store' }).then(function (r) { if (r.ok) location.reload() }).catch(function () {})
  setTimeout(nochmal, Math.min(30000, 3000 * n))
}
addEventListener('online', function () { setTimeout(function () { location.reload() }, 1000) })
setTimeout(nochmal, 3000)
</script></body></html>`

const warten = (ms) => new Promise((r) => setTimeout(r, ms))

self.addEventListener('fetch', (event) => {
  const req = event.request
  // Nur die Navigation abfangen. Alles andere — API, Streams, Websockets —
  // geht unangetastet ans Netz.
  if (req.mode !== 'navigate') return
  event.respondWith(
    fetch(req)
      // Ein zweiter Versuch nach kurzer Pause: Nach dem Aufwachen steht das
      // Netz oft eine Sekunde später.
      .catch(() => warten(1500).then(() => fetch(req)))
      .catch(() => new Response(OFFLINE, {
        status: 503,
        headers: { 'Content-Type': 'text/html; charset=utf-8' },
      })),
  )
})
