/**
 * Faehrt eine Selkies-Sitzung durch den echten Weg und sagt, ob ein Bild kommt.
 *
 * **Wozu.** Das Versagen des Medienwegs sieht im Browser immer gleich aus —
 * eine leere Flaeche — und im Protokoll steht kein Grund. Dieses Skript zaehlt
 * die Bilder, die der Browser wirklich dekodiert hat.
 *
 * **Beide Fassungen.** Selkies 2.0 (Basisimage ab 2026-10-07) streamt ueber
 * WebSockets durch Traefik und dekodiert mit WebCodecs in ein `<video>`.
 * Selkies 1.6.2 (Golden Images auf dem alten Basisimage) streamt ueber WebRTC
 * und TURN; dort steht zusaetzlich die WebRTC-Statistik im Bericht. Gezaehlt
 * wird in beiden Faellen am `<video>`: `getVideoPlaybackQuality()`.
 *
 * **Der Browser laeuft in einem eigenen Container im Standardnetz.** Von dort
 * ist der Session-Container **nicht** direkt erreichbar, genau wie von einem
 * Arbeitsplatz im Firmennetz.
 *
 *   OTA_CDP=http://127.0.0.1:9224 OTA_SLUG=<vorlage> [OTA_APP=<slug>] node scripts/pruef-selkies.mjs
 *
 * Mit `OTA_APP` wird zusaetzlich diese Anwendung auf ihrem eigenen Bildschirm
 * gestartet und deren Strom genauso geprueft.
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

// Der Start wird wiederholt, wenn der Browser die Anfrage selbst abbricht: Auf
// dem Docker-Wirt haelt Chromium die Netze, die ein neuer Arbeitsplatz
// anlegt, fuer einen Netzwechsel (`net::ERR_NETWORK_CHANGED`). Ein zweiter
// Start gibt den laufenden Arbeitsplatz einfach zurueck.
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
  for (let i = 0; ; i++) {
    try {
      const a = await fetch('/api/sessions', {
        method: 'POST', credentials: 'include',
        headers: { 'content-type': 'application/json' },
        body: JSON.stringify({ template_id: v.id }),
      })
      if (!a.ok) return { fehler: `Start abgelehnt: ${a.status} ${await a.text()}` }
      return await a.json()
    } catch (e) {
      if (i >= 10) return { fehler: `Start: ${e}` }
      await new Promise((r) => setTimeout(r, 3000))
    }
  }
}, SLUG)

if (sitzung.fehler) { console.error(sitzung.fehler); await browser.disconnect(); process.exit(2) }
console.log(`Sitzung ${sitzung.id}, Maschine ${sitzung.stream_engine}, ${sitzung.url}`)

/** Eine Seite oeffnen, warten, die dekodierten Bilder zaehlen. */
async function messen (pfad, name) {
  await page.goto(BASE + pfad, { waitUntil: 'domcontentloaded', timeout: 40000 })
  console.log(`[${name}] warte ${WARTE}s auf ein Bild …`)
  await new Promise((r) => setTimeout(r, WARTE * 1000))
  const b = await page.evaluate(async () => {
    const out = { zustaende: window.__ota?.zustaende ?? [], paare: [], webrtc: null }
    for (const pc of window.__ota?.pcs ?? []) {
      const stats = await pc.getStats()
      const alle = new Map()
      stats.forEach((x) => alle.set(x.id, x))
      stats.forEach((x) => {
        if (x.type === 'candidate-pair' && x.state === 'succeeded' && x.nominated) {
          const l = alle.get(x.localCandidateId), f = alle.get(x.remoteCandidateId)
          out.paare.push(`${l?.candidateType}/${l?.address}:${l?.port} -> ` +
            `${f?.candidateType}/${f?.address}:${f?.port}  empfangen=${x.bytesReceived}B`)
        }
        if (x.type === 'inbound-rtp' && x.kind === 'video') {
          out.webrtc = `${x.framesDecoded ?? 0} Bilder ueber WebRTC, ${x.bytesReceived}B`
        }
      })
    }
    // Das groesste Video zaehlt — Selkies 2.0 legt daneben noch kleine an.
    const v = [...document.querySelectorAll('video')]
      .sort((a, b) => b.videoWidth * b.videoHeight - a.videoWidth * a.videoHeight)[0]
    const q = v?.getVideoPlaybackQuality?.()
    out.abmessung = v ? `${v.videoWidth}x${v.videoHeight}` : 'kein <video>'
    out.bilder = q ? q.totalVideoFrames : 0
    out.selkies2 = !!document.querySelector('#videoCanvas')
    return out
  })
  if (b.zustaende.length) {
    console.log(`[${name}] Zustandsverlauf:`)
    for (const z of b.zustaende) console.log('  ' + z)
  }
  for (const p of b.paare) console.log(`[${name}] Kandidatenpaar ${p}`)
  if (b.webrtc) console.log(`[${name}] ${b.webrtc}`)
  console.log(`[${name}] ${b.selkies2 ? 'Selkies 2.0, WebSockets' : 'Selkies 1.6.2, WebRTC'}: ` +
    `${b.bilder} Bilder dekodiert, Bildgroesse ${b.abmessung}`)
  return b.abmessung !== 'kein <video>' && b.abmessung !== '0x0' && b.bilder > 0
}

let gut = await messen(sitzung.url, 'Arbeitsplatz')
console.log(gut ? 'Ein Bild kommt an.' : 'KEIN BILD.')

// Eine Anwendung auf ihrem eigenen Bildschirm — eigener Selkies, eigener Port,
// eigene Route.
const APP = process.env.OTA_APP ?? ''
if (APP) {
  await page.goto(BASE + '/', { waitUntil: 'domcontentloaded', timeout: 20000 })
  const mitApp = await page.evaluate(async ({ id, app }) => {
    const a = await fetch(`/api/sessions/${id}/apps/${app}`, { method: 'POST', credentials: 'include' })
    return a.ok ? await a.json() : { fehler: `${a.status} ${await a.text()}` }
  }, { id: sitzung.id, app: APP })
  const strom = (mitApp.streams ?? []).find((x) => x.app_slug === APP)
  if (!strom) {
    console.log(`[Anwendung] liess sich nicht starten: ${mitApp.fehler ?? 'kein Strom'}`)
    gut = false
  } else {
    const appGut = await messen(strom.url, `Anwendung ${APP}`)
    console.log(appGut ? 'Die Anwendung bringt ein Bild.' : 'ANWENDUNG OHNE BILD.')
    gut = gut && appGut
  }
}

// Die Pruefsitzung wieder beenden. Eine liegengebliebene faelscht jede
// spaetere Messung. Zurueck auf OTAs Seite: Selkies 2.0 ersetzt auf seiner
// eigenen `fetch`, und ein Aufruf der OTA-API von dort scheitert.
if (!process.env.OTA_BEHALTEN) {
  await page.goto(BASE + '/', { waitUntil: 'domcontentloaded', timeout: 20000 })
  // Auch hier kann der Browser die Antwort verwerfen, weil das Beenden Netze
  // abbaut (siehe oben); beendet ist die Sitzung trotzdem.
  const weg = await page.evaluate(async (id) => {
    try {
      const a = await fetch(`/api/sessions/${id}`, { method: 'DELETE', credentials: 'include' })
      return a.status
    } catch (e) { return `Antwort verworfen: ${e}` }
  }, sitzung.id)
  console.log(`Pruefsitzung beendet (${weg})`)
}
await browser.disconnect()
process.exit(gut ? 0 : 1)
