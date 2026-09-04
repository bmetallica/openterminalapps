/**
 * Bilder der Oberflaeche fuer die README.
 *
 * Keine Pruefung — ein Werkzeug. Es meldet sich an, faehrt die Bildschirme
 * ab und legt PNG-Dateien unter `docs/bilder/` ab.
 *
 * **Zwei Regeln, die hier nicht verhandelbar sind:**
 *
 *   1. **Keine fremden Bildschirme.** Das Skript schaltet sich auf keine
 *      laufende Sitzung auf. Fuer das Bild eines Arbeitsplatzes startet es
 *      eine **eigene** und raeumt sie hinterher weg.
 *   2. **Keine Personenlisten.** „Nutzer" und das Protokoll zeigen Namen
 *      echter Menschen. Sie sind hier absichtlich nicht dabei — ein Bild in
 *      einer README wandert weiter, als man denkt.
 *
 * Es liegt neben `e2e.mjs`, weil es denselben Browser braucht — Node loest
 * Module vom Verzeichnis der Datei aus auf, und `puppeteer-core` steht hier.
 *
 * Aufruf:  make bilder                        (Zugangsdaten aus deploy/.env)
 */
import { execSync } from 'node:child_process'
import { mkdirSync } from 'node:fs'
import puppeteer from 'puppeteer-core'

const BASE = process.env.OTA_BASE ?? 'https://192.168.66.224:8443'
const USER = process.env.OTA_TEST_ADMIN ?? 'notfall'
const PW = process.env.OTA_TEST_ADMIN_PW
if (!PW) {
  console.error('OTA_TEST_ADMIN_PW fehlt. Trag es in deploy/.env ein.')
  process.exit(2)
}
const ZIEL = process.env.OTA_BILDER ?? '/opt/openterminalapps/docs/bilder'
const CERT = '/opt/openterminalapps/deploy/certs/ota.crt'
mkdirSync(ZIEL, { recursive: true })

const spki = execSync(
  `openssl x509 -in ${CERT} -pubkey -noout | openssl pkey -pubin -outform der | openssl dgst -sha256 -binary | base64`,
  { shell: '/bin/bash' },
).toString().trim()

const browser = await puppeteer.launch({
  executablePath: '/usr/bin/chromium',
  headless: 'new',
  args: ['--no-sandbox', '--disable-gpu', '--disable-dev-shm-usage',
         `--ignore-certificate-errors-spki-list=${spki}`, '--window-size=1600,1000'],
  // Zwei Bildpunkte je Punkt: Auf einem hochaufloesenden Bildschirm sieht ein
  // Bild sonst weich aus, und Schrift ist genau das, was hier zaehlt.
  defaultViewport: { width: 1600, height: 1000, deviceScaleFactor: 2 },
})

const page = await browser.newPage()
await page.evaluateOnNewDocument(() => {
  try { localStorage.setItem('ota.lang', 'de') } catch { /* egal */ }
})

const warte = (ms) => new Promise((r) => setTimeout(r, ms))
const bild = async (name) => {
  await warte(700)
  await page.screenshot({ path: `${ZIEL}/${name}.png` })
  console.log(`  ${name}.png`)
}
const zu = async (kapitel) => {
  await page.evaluate((k) => {
    const b = [...document.querySelectorAll('.rail__btn')]
      .find((x) => x.textContent?.includes(k))
    b?.click()
  }, kapitel)
  await page.waitForSelector('.h-page', { timeout: 20000 })
  await warte(1400)
}

console.log(`Bilder nach ${ZIEL}`)

await page.goto(BASE + '/login', { waitUntil: 'networkidle2', timeout: 30000 })
await page.waitForSelector('input[autocomplete="username"]', { timeout: 10000 })
await page.type('input[autocomplete="username"]', USER)
await page.type('input[autocomplete="current-password"]', PW)
await Promise.all([
  page.click('button.btn--primary'),
  page.waitForSelector('.rail', { timeout: 20000 }),
])
await page.waitForSelector('.tiles, .empty', { timeout: 20000 })

// Ein Dashboard ohne laufende Sitzung zeigt das Produkt nicht. Also eine
// **eigene** starten — und am Ende wieder wegraeumen.
// Ueber den Knopf, nicht ueber die API: So, wie ein Mensch es tut — und das
// Bild zeigt am Ende denselben Zustand, den ein Mensch sieht.
console.log('  (eigene Sitzung starten …)')
const gestartet = await page.evaluate(() => {
  const kachel = [...document.querySelectorAll('.tile')]
    .find((t) => /Arbeitsplatz/i.test(t.textContent ?? ''))
  const knopf = [...(kachel?.querySelectorAll('button') ?? [])]
    .find((b) => /starten/i.test(b.textContent ?? ''))
  if (!knopf) return false
  knopf.click()
  return true
})
if (gestartet) {
  // Der erste Start dauert; die Kachel wandert danach nach oben in „Deine
  // Sessions". Auf genau das warten, statt auf gut Glueck zu schlafen.
  try {
    await page.waitForSelector('.bay', { timeout: 90000 })
  } catch { /* dann eben ohne laufende Sitzung */ }
  await warte(4000)
}
await warte(1500)
await bild('01-dashboard')

await zu('Workspaces')
await bild('02-workspaces')

// Den Editor oeffnen — dort stecken die Regler, um die es geht.
await page.evaluate(() => document.querySelector('.row, tbody tr')?.click())
await warte(1600)
await bild('03-workspace-editor')

await zu('Netz')
// Den Grundregelsatz aufklappen — zusammengeklappt sagt das Bild nicht, was
// OTA fuer sich selbst oeffnet, und genau das ist der Punkt des Abschnitts.
await page.evaluate(() => {
  document.querySelectorAll('details').forEach((d) => { d.open = true })
})
await warte(900)
await bild('04-netz')

// Der Software-Reiter des Editors: Pakete anklicken, Image bauen. Das ist
// die Funktion, die die README als Kern nennt — eine Image-Liste zeigt sie
// nicht.
await zu('Workspaces')
await page.evaluate(() => document.querySelector('.row, tbody tr')?.click())
await warte(1400)
await page.evaluate(() => {
  const t = [...document.querySelectorAll('button, [role="tab"]')]
    .find((x) => x.textContent?.trim() === 'Software')
  t?.click()
})
await warte(2200)
await bild('05-software')

await zu('Images')
await bild('06-images')

await zu('Betrieb')
// Der Reiter „Sicherung": Die beiden anderen zeigen, wer gerade arbeitet.
await page.evaluate(() => {
  const b = [...document.querySelectorAll('.seg__opt')]
    .find((x) => x.textContent?.includes('Sicherung'))
  b?.click()
})
await warte(1600)
await bild('07-sicherung')

await zu('Hilfe')
await bild('08-handbuch')

// Aufraeumen: Was dieses Werkzeug gestartet hat, beendet es auch.
//
// Ueber die API und nicht ueber den Knopf: Der Weg durch die Oberflaeche
// fragt je nach Zustand nach, und ein Aufraeumen, das an einer Rueckfrage
// haengenbleibt, laesst eine Sitzung stehen — gemessen am 2026-09-05.
if (gestartet) {
  const weg = await page.evaluate(async () => {
    const r = await fetch('/api/sessions', { credentials: 'include' })
    const meine = await r.json()
    const s = meine.find((x) => x.status === 'running')
    if (!s) return 'nichts zu beenden'
    await fetch(`/api/sessions/${s.id}`, { method: 'DELETE', credentials: 'include' })
    return s.id.slice(0, 13)
  })
  console.log(`  (eigene Sitzung beendet: ${weg})`)
}

await browser.close()
console.log('fertig')
