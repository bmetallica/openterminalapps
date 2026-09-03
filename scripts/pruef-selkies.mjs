/**
 * Faehrt eine Selkies-Sitzung durch den echten Weg und sagt, ob ein Bild kommt.
 *
 * **Wozu.** Der Selkies-Weg hat keine eigene Pruefreihe, und sein Versagen
 * sieht im Browser immer gleich aus: „Waiting for stream". Ob es an ICE, am
 * DTLS-Handschlag oder am Medienstrom liegt, steht nirgends. Dieses Skript
 * liest es aus der WebRTC-Statistik des Browsers aus.
 *
 * **Der Browser laeuft in einem eigenen Container im Standardnetz.** Das ist
 * der Kern: Von dort ist der Session-Container **nicht** direkt erreichbar,
 * genau wie von einem Arbeitsplatz im Firmennetz. Der Medienweg muss also
 * ueber TURN gehen — und nur so prueft das hier, was ein Anwender erlebt.
 * Ein Browser auf dem Server selbst wuerde direkt verbinden und den Fehler
 * nie sehen.
 *
 * Aufruf:
 *
 *     docker run -d --name ota-chrome-probe --network bridge --shm-size=1g \
 *       -p 127.0.0.1:9223:9222 --entrypoint /opt/google/chrome/chrome \
 *       127.0.0.1:5000/ota/arbeitsplatz:v13 \
 *       --headless=new --no-sandbox --disable-dev-shm-usage --disable-gpu \
 *       --ignore-certificate-errors --user-data-dir=/tmp/chrome \
 *       --remote-debugging-port=9222 --remote-debugging-address=0.0.0.0
 *     node scripts/pruef-selkies.mjs
 */

import puppeteer from './../tests/node_modules/puppeteer-core/lib/esm/puppeteer/puppeteer-core.js'
import { readFileSync } from 'node:fs'

const env = Object.fromEntries(
  readFileSync(new URL('../deploy/.env', import.meta.url), 'utf8')
    .split('\n').filter((z) => z.includes('=') && !z.trim().startsWith('#'))
    .map((z) => [z.slice(0, z.indexOf('=')).trim(), z.slice(z.indexOf('=') + 1).trim()]))

const BASE = process.env.OTA_BASE ?? 'https://192.168.66.224:8443'
const CDP = process.env.OTA_CDP ?? 'http://127.0.0.1:9223'
const USER = process.env.OTA_TEST_ADMIN ?? env.OTA_TEST_ADMIN ?? 'notfall'
const PW = process.env.OTA_TEST_ADMIN_PW ?? env.OTA_TEST_ADMIN_PW
// Ohne Angabe die erste Selkies-Vorlage, die es gibt. Vorher stand hier der
// Name einer Vorlage aus dieser einen Anlage — die es inzwischen nicht mehr
// gibt, und in jeder anderen Anlage nie gab.
const SLUG = process.env.OTA_SLUG ?? ''
const WARTE = Number(process.env.OTA_WARTE ?? 60)

const browser = await puppeteer.connect({ browserURL: CDP, defaultViewport: { width: 1440, height: 900 } })
const page = (await browser.pages())[0] ?? await browser.newPage()

// Den Zustand der Verbindung mitschreiben, bevor die Seite laedt — sonst ist
// die erste Haelfte des Verbindungsaufbaus schon vorbei.
await page.evaluateOnNewDocument(() => {
  window.__ota = { zustaende: [], pcs: [] }
  const Echt = window.RTCPeerConnection
  window.RTCPeerConnection = function (...args) {
    const pc = new Echt(...args)
    window.__ota.pcs.push(pc)
    const merke = (was) => window.__ota.zustaende.push(
      `${(performance.now() / 1000).toFixed(1)}s ${was}`)
    pc.addEventListener('iceconnectionstatechange', () => merke(`ice=${pc.iceConnectionState}`))
    pc.addEventListener('connectionstatechange', () => merke(`verbindung=${pc.connectionState}`))
    return pc
  }
  window.RTCPeerConnection.prototype = Echt.prototype
})

await page.goto(BASE + '/login', { waitUntil: 'networkidle2', timeout: 30000 })

// Der Browser laeuft ueber mehrere Laeufe hinweg weiter und bringt seine
// Anmeldung mit. Dann gibt es kein Anmeldefeld, und darauf zu warten ist ein
// Fehler des Pruefstandes, kein Befund.
const angemeldet = await page.$('.rail')
if (angemeldet) {
  console.log(`Bereits angemeldet an ${BASE}`)
} else {
  console.log(`Anmeldung an ${BASE} als ${USER}`)
  await page.waitForSelector('input[autocomplete="username"]', { timeout: 15000 })
  await page.type('input[autocomplete="username"]', USER)
  await page.type('input[autocomplete="current-password"]', PW)
  await Promise.all([page.click('button.btn--primary'), page.waitForSelector('.rail', { timeout: 25000 })])
}

const sitzung = await page.evaluate(async (slug) => {
  const vorlagen = await (await fetch('/api/templates', { credentials: 'include' })).json()
  const alle = Array.isArray(vorlagen) ? vorlagen : vorlagen.items ?? []
  const v = slug
    ? alle.find((t) => t.slug === slug)
    : alle.find((t) => t.stream_engine === 'selkies' && t.mode === 'workspace' && t.is_enabled)
  if (!v) {
    return { fehler: slug ? `Vorlage ${slug} nicht sichtbar`
                          : 'Keine Selkies-Vorlage vorhanden' }
  }
  const a = await fetch('/api/sessions', {
    method: 'POST', credentials: 'include',
    headers: { 'content-type': 'application/json' },
    body: JSON.stringify({ template_id: v.id }),
  })
  if (!a.ok) return { fehler: `Start abgelehnt: ${a.status} ${await a.text()}` }
  return await a.json()
}, SLUG)

if (sitzung.fehler) { console.error(sitzung.fehler); await browser.disconnect(); process.exit(2) }
console.log(`Sitzung ${sitzung.id}, Maschine ${sitzung.stream_engine}, ${sitzung.url}`)

await page.goto(BASE + sitzung.url, { waitUntil: 'domcontentloaded', timeout: 40000 })
console.log(`warte ${WARTE}s auf ein Bild …`)
await new Promise((r) => setTimeout(r, WARTE * 1000))

const bericht = await page.evaluate(async () => {
  const out = { zustaende: window.__ota?.zustaende ?? [], paare: [], video: null }
  for (const pc of window.__ota?.pcs ?? []) {
    const stats = await pc.getStats()
    const alle = new Map()
    stats.forEach((s) => alle.set(s.id, s))
    stats.forEach((s) => {
      if (s.type === 'candidate-pair' && s.state === 'succeeded' && s.nominated) {
        const l = alle.get(s.localCandidateId), f = alle.get(s.remoteCandidateId)
        out.paare.push(`${l?.candidateType}/${l?.address}:${l?.port} -> ` +
          `${f?.candidateType}/${f?.address}:${f?.port}  ` +
          `empfangen=${s.bytesReceived}B gesendet=${s.bytesSent}B`)
      }
      if (s.type === 'inbound-rtp' && s.kind === 'video') {
        out.video = `${s.framesDecoded ?? 0} Bilder, ${s.bytesReceived}B`
      }
    })
  }
  const v = document.querySelector('video')
  out.abmessung = v ? `${v.videoWidth}x${v.videoHeight}` : 'kein <video>'
  return out
})

console.log('\nZustandsverlauf:')
for (const z of bericht.zustaende) console.log('  ' + z)
console.log('\nGewaehlte Kandidatenpaare:')
for (const p of bericht.paare) console.log('  ' + p)
if (!bericht.paare.length) console.log('  (keins — ICE ist nicht durchgekommen)')
console.log(`\nVideo: ${bericht.video ?? 'nichts empfangen'}   Bildgroesse: ${bericht.abmessung}`)
const gut = bericht.abmessung !== 'kein <video>' && bericht.abmessung !== '0x0'
console.log(gut ? '\nEin Bild kommt an.' : '\nKEIN BILD.')

// Die Pruefsitzung wieder beenden. Eine liegengebliebene faelscht jede
// spaetere Messung — und in der Sicherungspruefung hat genau so ein Rest
// schon einmal zwei Fehlschlaege vorgetaeuscht.
if (!process.env.OTA_BEHALTEN) {
  await page.goto(BASE + '/', { waitUntil: 'domcontentloaded', timeout: 20000 })
  const weg = await page.evaluate(async (id) => {
    const a = await fetch(`/api/sessions/${id}/stop`, { method: 'POST', credentials: 'include' })
    return a.status
  }, sitzung.id)
  console.log(`Pruefsitzung beendet (${weg})`)
}
await browser.disconnect()
process.exit(gut ? 0 : 1)
