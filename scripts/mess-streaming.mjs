/**
 * Misst, was eine Sitzung kostet — CPU, Reaktionszeit und Bandbreite.
 *
 * **Wozu.** Die Entscheidung fuer Selkies fiel funktional: Es kommt ein Bild,
 * die Zwischenablage traegt, eine Einzelanwendung laesst sich formfuellend
 * streamen. Was nie gemessen wurde, ist der Preis. x264 laeuft hier in
 * Software, die Maschine hat keine GPU — und davon haengt ab, wie viele
 * Menschen gleichzeitig arbeiten koennen. Das ist eine Kapazitaetsfrage, und
 * die beantwortet man nicht mit einem Gefuehl.
 *
 * **Der Kniff: zweimal dieselbe Last, einmal ohne und einmal mit Betrachter.**
 * Beide Maschinen kodieren erst, wenn jemand zusieht. Die Differenz ist
 * deshalb sauber das, was der Strom kostet — ohne die Kosten der Anwendung,
 * die auf beiden Seiten dieselben waeren. Ohne diesen Vergleich misst man vor
 * allem xfce4-terminal.
 *
 * **Die Reihenfolge ist Absicht: erst verbinden, dann die Grundlast messen.**
 * Der erste Messlauf machte es andersherum und bekam fuer dieselbe Last in
 * Debian 0,42 und in Ubuntu 0,06 Kerne — ein Siebtel, und das ergab keinen
 * Sinn. Der Grund: Ohne Betrachter steht Xvfb in OTAs Abbild auf 3840x2160
 * und faellt erst auf die Groesse des Betrachters, wenn einer da ist. Die
 * Grundlast war also auf achtfacher Flaeche gemessen und als Abzug wertlos.
 * Jetzt verbindet sich der Betrachter zuerst, die Aufloesung stellt sich ein,
 * und danach geht er wieder — die Flaeche bleibt, das Kodieren hoert auf.
 *
 * **Reaktionszeit** ist von Glas zu Glas gemessen, nicht geschaetzt: Im
 * Container schaltet ein formfuellendes Terminal seinen Hintergrund auf weiss
 * und schreibt im selben Atemzug die Uhrzeit weg; im Browser liest ein
 * Abtaster jedes Einzelbild die Helligkeit und merkt sich, wann sie umspringt.
 * Beide Uhren sind dieselbe — Container teilen sich die Uhr des Wirts.
 * Enthalten ist damit alles: Zeichnen, Kodieren, TURN, Dekodieren, Anzeigen.
 *
 * **Bandbreite** kommt aus dem Zaehler der Netzkarte des Session-Containers.
 * Das ist der einzige Wert, den beide Maschinen gleich melden — WebRTC-
 * Statistik gibt es bei KasmVNC nicht.
 *
 * Aufruf (der Prüfbrowser muss laufen, siehe mess-streaming.sh):
 *
 *     OTA_CDP=http://127.0.0.1:9225 OTA_PROBE=ota-mess-browser \
 *       node scripts/mess-streaming.mjs <vorlagen-slug>
 *
 * Die letzte Zeile auf stdout ist JSON — die Huelle liest sie aus.
 */

import { execFileSync } from 'node:child_process'
import { readFileSync } from 'node:fs'
import puppeteer from './../tests/node_modules/puppeteer-core/lib/esm/puppeteer/puppeteer-core.js'

const env = Object.fromEntries(
  readFileSync(new URL('../deploy/.env', import.meta.url), 'utf8')
    .split('\n').filter((z) => z.includes('=') && !z.trim().startsWith('#'))
    .map((z) => [z.slice(0, z.indexOf('=')).trim(), z.slice(z.indexOf('=') + 1).trim()]))

const BASE = process.env.OTA_BASE ?? 'https://192.168.66.224:8443'
const CDP = process.env.OTA_CDP ?? 'http://127.0.0.1:9225'
const PROBE = process.env.OTA_PROBE ?? ''
const USER = process.env.OTA_TEST_ADMIN ?? env.OTA_TEST_ADMIN ?? 'notfall'
const PW = process.env.OTA_TEST_ADMIN_PW ?? env.OTA_TEST_ADMIN_PW
const SLUG = process.argv[2] ?? process.env.OTA_SLUG
const SEK = Number(process.env.OTA_MESS_SEKUNDEN ?? 20)   // je Last und Phase
const BLITZE = Number(process.env.OTA_MESS_BLITZE ?? 12)
const BREITE = Number(process.env.OTA_MESS_BREITE ?? 1280)
const HOEHE = Number(process.env.OTA_MESS_HOEHE ?? 720)

if (!SLUG) { console.error('Aufruf: node mess-streaming.mjs <vorlagen-slug>'); process.exit(2) }
const sag = (t) => console.error(`    ${t}`)

// ------------------------------------------------------------------ Docker
//
// Der Messstand fasst Docker direkt an. Das widerspricht ADR-002 nicht: Die
// Regel gilt fuer die API, nicht fuer ein Werkzeug, das ein Administrator auf
// dem Wirt startet — so wie pruef-turn.py und die Sicherungspruefung auch.
const dock = (...a) => execFileSync('docker', a, { encoding: 'utf8' })
const inContainer = (c, ...a) => dock('exec', c, ...a)

/** CPU-Zeit des Containers in Sekunden (cgroup v2, im Container sichtbar). */
function cpuZeit(c) {
  const t = inContainer(c, 'cat', '/sys/fs/cgroup/cpu.stat')
  return Number(/usage_usec (\d+)/.exec(t)[1]) / 1e6
}

/**
 * Gesendete Bytes ueber **alle** Netzkarten — engine-neutral, beide Wege
 * zaehlen gleich.
 *
 * Ueber alle, nicht ueber `eth0`: Session-Container haengen in zwei Netzen
 * (`ota_sessions` und das der Anlage), und welche Karte den Strom traegt,
 * ist nicht verabredet. Der erste Messlauf meldete fuer KasmVNC deshalb
 * 0,00 Mbit/s — nicht weil nichts floss, sondern weil es woanders floss.
 */
function gesendet(c) {
  try {
    const t = inContainer(c, 'sh', '-c',
      'for n in /sys/class/net/*/statistics/tx_bytes; do ' +
      'case "$n" in */lo/*) continue;; esac; cat "$n"; done')
    return t.split('\n').filter(Boolean).reduce((s, z) => s + Number(z), 0)
  } catch { return 0 }
}

/**
 * Eine Probe ueber `SEK` Sekunden: wie viele Kerne verbraucht der Container,
 * und wie viel schickt er dabei weg.
 */
async function probe(container, sekunden) {
  const c0 = cpuZeit(container), n0 = gesendet(container), t0 = Date.now()
  const b0 = PROBE ? cpuZeit(PROBE) : 0
  await new Promise((r) => setTimeout(r, sekunden * 1000))
  const dt = (Date.now() - t0) / 1000
  return {
    kerne: (cpuZeit(container) - c0) / dt,
    browserKerne: PROBE ? (cpuZeit(PROBE) - b0) / dt : null,
    mbitS: ((gesendet(container) - n0) * 8) / dt / 1e6,
  }
}

// ------------------------------------------------------------------- Lasten
//
// Beide Lasten laufen in **beiden** Abbildern gleich: xfce4-terminal ist in
// Debian wie in Ubuntu dasselbe Programm, und scrollender Zufallstext aendert
// die ganze Flaeche, ohne dass das Zeichnen selbst die Messung auffrisst.
// Genau darum kein glxgears: Dessen Softwarerenderer wuerde alles zudecken,
// was hier eigentlich interessiert.
const TERMINAL = 'xfce4-terminal --disable-server --hide-menubar --hide-scrollbar --fullscreen'

function lastStarten(c, was) {
  lastBeenden(c)
  if (was === 'leerlauf') return
  // **Feste Rate, nicht so schnell es geht.** Der erste Messlauf liess die
  // Schleife rennen: Sie frass jeden freien Kern, beide Phasen liefen an der
  // Kerngrenze des Containers, und die Differenz — also genau das, was hier
  // gesucht wird — war null. Jetzt sind es 150 Zeilen je Sekunde, gleich in
  // beiden Phasen und in beiden Abbildern, und der Text steht vorher fest:
  // `/dev/urandom` und `base64` je Zeile waeren schon wieder Last, die nichts
  // mit dem Bild zu tun hat.
  const innen =
    'printf "\\033[?25l"; Z=$(head -c 200 /dev/urandom | base64 | tr -d "\\n" | cut -c1-110); ' +
    'while true; do i=0; while [ $i -lt 15 ]; do echo "$Z"; i=$((i+1)); done; sleep 0.1; done'
  dock('exec', '-u', '1000', '-e', 'DISPLAY=:1', '-d', c, 'sh', '-c',
       `${TERMINAL} -x sh -c '${innen}' >/dev/null 2>&1`)
}

function lastBeenden(c) {
  // `pkill -x`, nicht `-f`: Mit `-f` traefe das Muster die eigene Befehlszeile
  // dieses Aufrufs mit. Genau darauf bin ich in diesem Projekt schon zweimal
  // hereingefallen.
  try { inContainer(c, 'pkill', '-x', 'xfce4-terminal') } catch { /* keins da */ }
}

/** Wie gross die Flaeche gerade ist, die tatsaechlich uebertragen wird. */
async function bildGroesse(seite) {
  return await seite.evaluate(() => {
    const v = document.querySelector('video')
    if (v && v.videoWidth > 0) return `video ${v.videoWidth}x${v.videoHeight}`
    const cs = [...document.querySelectorAll('canvas')]
      .filter((c) => c.width >= 640 && c.height >= 360)
      .sort((a, b) => b.width * b.height - a.width * a.height)
    return cs.length ? `canvas ${cs[0].width}x${cs[0].height}` : 'kein Bild'
  })
}

// ------------------------------------------------------------------ Browser
const browser = await puppeteer.connect({
  browserURL: CDP, defaultViewport: { width: BREITE, height: HOEHE } })
const page = (await browser.pages())[0] ?? await browser.newPage()

await page.goto(BASE + '/login', { waitUntil: 'networkidle2', timeout: 30000 })
if (!(await page.$('.rail'))) {
  await page.waitForSelector('input[autocomplete="username"]', { timeout: 15000 })
  await page.type('input[autocomplete="username"]', USER)
  await page.type('input[autocomplete="current-password"]', PW)
  await Promise.all([page.click('button.btn--primary'),
                     page.waitForSelector('.rail', { timeout: 25000 })])
}

const sitzung = await page.evaluate(async (slug) => {
  const v = await (await fetch('/api/templates', { credentials: 'include' })).json()
  const t = (Array.isArray(v) ? v : v.items ?? []).find((x) => x.slug === slug)
  if (!t) return { fehler: `Vorlage ${slug} nicht sichtbar` }
  const a = await fetch('/api/sessions', {
    method: 'POST', credentials: 'include',
    headers: { 'content-type': 'application/json' },
    body: JSON.stringify({ template_id: t.id }),
  })
  if (!a.ok) return { fehler: `Start abgelehnt: ${a.status} ${await a.text()}` }
  return { ...(await a.json()), maschine: t.stream_engine, kerneGrenze: t.cores }
}, SLUG)

if (sitzung.fehler) { console.error(sitzung.fehler); process.exit(2) }
const CN = `ota-s-${sitzung.id.slice(0, 12)}`
sag(`Sitzung ${sitzung.id} (${sitzung.maschine}), Container ${CN}`)

const ergebnis = {
  slug: SLUG, maschine: sitzung.maschine, kerneGrenze: sitzung.kerneGrenze,
  ohne: {}, mit: {}, reaktion: null,
}
let fehlgeschlagen = null

try {
  // Warten, bis der Container wirklich steht — sonst misst die erste Probe
  // den Startvorgang.
  for (let i = 0; i < 60; i++) {
    try { if (inContainer(CN, 'pgrep', '-x', 'xfwm4').trim()) break } catch { /* noch nicht */ }
    await new Promise((r) => setTimeout(r, 1000))
  }
  await new Promise((r) => setTimeout(r, 8000))

  // ------------------------------------ Phase 1: verbinden, Aufloesung setzen
  await page.goto(BASE + sitzung.url, { waitUntil: 'domcontentloaded', timeout: 40000 })

  // Auf ein wirklich laufendes Bild warten: Ein <video> ohne Masse oder ein
  // leeres <canvas> sieht im DOM fertig aus und traegt trotzdem nichts.
  const bild = await page.waitForFunction(() => {
    const v = document.querySelector('video')
    if (v && v.videoWidth > 0) return `video ${v.videoWidth}x${v.videoHeight}`
    // Mindestens 640x360: Die Bedienleiste von KasmVNC bringt eigene kleine
    // Leinwaende mit, und eine davon meldete im ersten Lauf „700x230" als
    // Bild — waehrend die richtige daneben noch leer war.
    const cs = [...document.querySelectorAll('canvas')]
      .filter((c) => c.width >= 640 && c.height >= 360)
      .sort((a, b) => b.width * b.height - a.width * a.height)
    return cs.length ? `canvas ${cs[0].width}x${cs[0].height}` : false
  }, { timeout: 90000, polling: 500 }).then((h) => h.jsonValue())
  sag(`Bild steht: ${bild}`)
  // KasmVNC meldet die Endgroesse erst ein paar Sekunden spaeter — die erste
  // Leinwand steht noch auf der Startaufloesung.
  await new Promise((r) => setTimeout(r, 12000))
  ergebnis.bild = await bildGroesse(page)
  sag(`Uebertragene Flaeche: ${ergebnis.bild}`)

  // ------------------------------------- Phase 2: Grundlast ohne Betrachter
  //
  // Der Betrachter geht, die eingestellte Flaeche bleibt. Beide Maschinen
  // hoeren damit auf zu kodieren — genau das soll hier herausgerechnet werden.
  await page.goto('about:blank', { waitUntil: 'domcontentloaded', timeout: 20000 })
  await new Promise((r) => setTimeout(r, 6000))

  for (const last of ['leerlauf', 'text']) {
    lastStarten(CN, last)
    await new Promise((r) => setTimeout(r, 5000))
    ergebnis.ohne[last] = await probe(CN, SEK)
    sag(`ohne Betrachter · ${last}: ${ergebnis.ohne[last].kerne.toFixed(2)} Kerne`)
  }
  lastBeenden(CN)

  // ------------------------------------------------- Phase 3: mit Betrachter
  await page.goto(BASE + sitzung.url, { waitUntil: 'domcontentloaded', timeout: 40000 })
  await page.waitForFunction(() => {
    const v = document.querySelector('video')
    if (v && v.videoWidth > 0) return true
    return [...document.querySelectorAll('canvas')]
      .some((c) => c.width >= 640 && c.height >= 360)
  }, { timeout: 90000, polling: 500 })
  await new Promise((r) => setTimeout(r, 8000))
  const flaecheJetzt = await bildGroesse(page)
  if (flaecheJetzt !== ergebnis.bild) {
    sag(`⚠ Flaeche hat sich geaendert: ${ergebnis.bild} → ${flaecheJetzt}`)
    ergebnis.bild = flaecheJetzt
  }

  for (const last of ['leerlauf', 'text']) {
    lastStarten(CN, last)
    await new Promise((r) => setTimeout(r, 5000))
    ergebnis.mit[last] = await probe(CN, SEK)
    const m = ergebnis.mit[last]
    sag(`mit Betrachter · ${last}: ${m.kerne.toFixed(2)} Kerne, ${m.mbitS.toFixed(2)} Mbit/s`)
  }

  // ------------------------------------------------------- Reaktionszeit
  lastBeenden(CN)
  await new Promise((r) => setTimeout(r, 4000))

  // Der Abtaster laeuft im Browser und liest jedes Einzelbild die Helligkeit
  // der Bildmitte. `timeOrigin + now()` ist die Uhr des Wirts — dieselbe, in
  // die der Container gleich seine Blitze schreibt.
  await page.evaluate(() => {
    window.__mess = { hell: [], laeuft: true }
    const quelle = document.querySelector('video')?.videoWidth
      ? document.querySelector('video')
      : [...document.querySelectorAll('canvas')]
          .filter((c) => c.width >= 640 && c.height >= 360)
          .sort((a, b) => b.width * b.height - a.width * a.height)[0]
    const k = document.createElement('canvas')
    k.width = 8; k.height = 8
    const g = k.getContext('2d', { willReadFrequently: true })
    let warHell = false
    const tick = () => {
      if (!window.__mess.laeuft) return
      try {
        g.drawImage(quelle, 0, 0, 8, 8)
        const d = g.getImageData(0, 0, 8, 8).data
        let s = 0
        for (let i = 0; i < d.length; i += 4) s += (d[i] + d[i + 1] + d[i + 2]) / 3
        const h = s / (d.length / 4)
        // 120, nicht 170: Das „Weiss" eines Terminals ist ein helles Grau,
        // und der Streifen des Panels am oberen Rand zieht den Mittelwert
        // weiter herunter. Gemessen kommt ein Blitz bei 166 an, eine
        // schwarze Flaeche bei 0 — die Schwelle liegt bequem dazwischen.
        if (h > 120 && !warHell) {
          warHell = true
          window.__mess.hell.push(performance.timeOrigin + performance.now())
        } else if (h < 60) warHell = false
      } catch { /* Einzelbild noch nicht lesbar */ }
      requestAnimationFrame(tick)
    }
    requestAnimationFrame(tick)
  })

  // Blitze im Container: Hintergrund weiss, Uhrzeit wegschreiben, wieder
  // schwarz. Der Schreibvorgang und die Uhrzeit stehen in derselben Shell —
  // dazwischen liegt nichts, was die Messung verschieben koennte.
  inContainer(CN, 'rm', '-f', '/tmp/ota-blitz.log')
  const blitzer = `i=0; while [ $i -lt ${BLITZE} ]; do
      printf "\\033[47m\\033[2J"; date +%s%3N >> /tmp/ota-blitz.log
      sleep 1; printf "\\033[40m\\033[2J"; sleep 1; i=$((i+1)); done`
  lastBeenden(CN)
  dock('exec', '-u', '1000', '-e', 'DISPLAY=:1', '-d', CN, 'sh', '-c',
       `${TERMINAL} -x sh -c '${blitzer}' >/dev/null 2>&1`)
  await new Promise((r) => setTimeout(r, (BLITZE * 2 + 8) * 1000))

  const gesehen = await page.evaluate(() => { window.__mess.laeuft = false; return window.__mess.hell })
  const gesetzt = inContainer(CN, 'sh', '-c', 'cat /tmp/ota-blitz.log 2>/dev/null || true')
    .split('\n').filter(Boolean).map(Number)

  // Jeden Blitz mit dem naechsten Sehen danach paaren. Was laenger als drei
  // Sekunden braucht, ist kein spaetes Bild mehr, sondern ein verlorenes —
  // und wird als solches gezaehlt, nicht als Ausreisser gemittelt.
  const zeiten = []
  let verloren = 0
  for (const t of gesetzt) {
    const treffer = gesehen.find((g) => g > t && g - t < 3000)
    if (treffer) zeiten.push(treffer - t); else verloren++
  }
  zeiten.sort((a, b) => a - b)
  ergebnis.reaktion = zeiten.length ? {
    anzahl: zeiten.length, verloren,
    median: zeiten[Math.floor(zeiten.length / 2)],
    schnellste: zeiten[0], langsamste: zeiten[zeiten.length - 1],
  } : { anzahl: 0, verloren, median: null }
  if (zeiten.length) {
    sag(`Reaktionszeit: Median ${Math.round(ergebnis.reaktion.median)} ms ` +
        `(${zeiten.length} Blitze, ${verloren} verloren)`)
  } else {
    sag(`Reaktionszeit: kein Blitz erkannt (${gesetzt.length} gesetzt)`)
  }
} catch (e) {
  fehlgeschlagen = String(e?.message ?? e)
  sag(`Abbruch: ${fehlgeschlagen}`)
} finally {
  try { lastBeenden(CN) } catch { /* Container schon weg */ }
  await page.goto(BASE + '/', { waitUntil: 'domcontentloaded', timeout: 20000 }).catch(() => {})
  await page.evaluate(async (id) => {
    await fetch(`/api/sessions/${id}/stop`, { method: 'POST', credentials: 'include' })
  }, sitzung.id).catch(() => {})
  await browser.disconnect()
}

ergebnis.fehler = fehlgeschlagen
console.log(JSON.stringify(ergebnis))
process.exit(fehlgeschlagen ? 1 : 0)
