// Tippt wie eine deutsche Tastatur in einen Selkies-Arbeitsplatz und liest im
// Container nach, was ankommt.
//
// **Warum.** Selkies schickt Zeichen, nicht Tasten, und der Container
// uebersetzt sie ueber sein Tastaturlayout zurueck. Passt das Layout nicht,
// verschwinden Umlaute ohne jede Meldung. Gemessen am 2026-09-28 mit `us`:
// getippt `aäöüß/Ä@z-`, angekommen `a?2z-`. Mit `de`, aber ohne Neustart von
// Selkies: `a_²yß`. Beides sah im Browser aus wie „die Tastatur spinnt".
//
// Gesendet wird, was Chrome auf einer deutschen Tastatur meldet: `key` ist das
// Zeichen, `code` die Taste auf der US-Belegung. Getippt wird in ein Terminal,
// das jede Eingabe in /tmp/getippt schreibt.
//
//   OTA_CDP=http://127.0.0.1:9224 OTA_SLUG=<vorlage> node scripts/pruef-tastatur.mjs
import puppeteer from './../tests/node_modules/puppeteer-core/lib/esm/puppeteer/puppeteer-core.js'
import { readFileSync } from 'node:fs'
import { execSync } from 'node:child_process'

const env = Object.fromEntries(readFileSync(new URL('../deploy/.env', import.meta.url), 'utf8')
  .split('\n').filter((z) => /^[A-Z_]+=/.test(z)).map((z) => [z.split('=')[0], z.slice(z.indexOf('=') + 1)]))
const BASE = process.env.OTA_BASE ?? 'https://192.168.66.224:8443'
const SLUG = process.env.OTA_SLUG ?? ''

const browser = await puppeteer.connect({ browserURL: process.env.OTA_CDP, defaultViewport: { width: 1440, height: 900 } })
const page = (await browser.pages())[0] ?? await browser.newPage()
await page.goto(BASE + '/login', { waitUntil: 'networkidle2' })
if (!(await page.$('.rail'))) {
  await page.waitForSelector('input[autocomplete="username"]')
  await page.type('input[autocomplete="username"]', env.OTA_TEST_ADMIN)
  await page.type('input[autocomplete="current-password"]', env.OTA_TEST_ADMIN_PW)
  await Promise.all([page.click('button.btn--primary'), page.waitForSelector('.rail', { timeout: 25000 })])
}
const s = await page.evaluate(async (slug) => {
  const alle = await (await fetch('/api/templates')).json()
  const v = slug ? alle.find((t) => t.slug === slug)
    : alle.find((t) => t.stream_engine === 'selkies' && t.mode === 'workspace' && t.is_enabled)
  const a = await fetch('/api/sessions', { method: 'POST', headers: { 'content-type': 'application/json' },
    body: JSON.stringify({ template_id: v.id }) })
  return a.json()
}, SLUG)
console.log('Sitzung', s.id, s.stream_engine)
await page.goto(BASE + s.url, { waitUntil: 'domcontentloaded' })
await new Promise((r) => setTimeout(r, 20000))

const cn = `ota-s-${s.id.slice(0, 12)}`
// Ein Fenster, das jede Eingabe in eine Datei schreibt, auf dem gestreamten Display.
const disp = execSync(`docker exec ${cn} sh -c 'ps -eo args | grep -o "Xvfb :[0-9]*" | head -1'`).toString().trim().split(' ')[1]
execSync(`docker exec -d -u ota ${cn} sh -c 'DISPLAY=${disp} xfce4-terminal --disable-server -T tippen -x sh -c "stty -icanon -echo; cat > /tmp/getippt"'`)
await new Promise((r) => setTimeout(r, 4000))
execSync(`docker exec -u ota ${cn} sh -c 'DISPLAY=${disp} xdotool search --name tippen windowactivate --sync; DISPLAY=${disp} setxkbmap -query'`, { stdio: 'inherit' })

await page.mouse.click(720, 450)
const c = await page.target().createCDPSession()
const taste = async (key, code, vk, text, modifiers = 0) => {
  await c.send('Input.dispatchKeyEvent', { type: 'keyDown', key, code, windowsVirtualKeyCode: vk, text, modifiers })
  await c.send('Input.dispatchKeyEvent', { type: 'keyUp', key, code, windowsVirtualKeyCode: vk, modifiers })
}
const halten = (key, code, vk, typ, modifiers) =>
  c.send('Input.dispatchKeyEvent', { type: typ, key, code, windowsVirtualKeyCode: vk, modifiers })

await taste('a', 'KeyA', 65, 'a')
await taste('ä', 'Quote', 222, 'ä')
await taste('ö', 'Semicolon', 186, 'ö')
await taste('ü', 'BracketLeft', 219, 'ü')
await taste('ß', 'Minus', 189, 'ß')
await halten('Shift', 'ShiftLeft', 16, 'rawKeyDown', 8)
await taste('/', 'Digit7', 55, '/', 8)
await taste('Ä', 'Quote', 222, 'Ä', 8)
await halten('Shift', 'ShiftLeft', 16, 'keyUp', 0)
await halten('AltGraph', 'AltRight', 225, 'rawKeyDown', 0)
await taste('@', 'KeyQ', 81, '@')
await halten('AltGraph', 'AltRight', 225, 'keyUp', 0)
await taste('z', 'KeyY', 89, 'z')
await taste('-', 'Slash', 189, '-')
await new Promise((r) => setTimeout(r, 2000))

const erwartet = 'aäöüß/Ä@z-'
const bekommen = execSync(`docker exec ${cn} cat /tmp/getippt`).toString()
console.log(`erwartet: ${erwartet}\nbekommen: ${bekommen}`)
console.log(bekommen === erwartet ? 'TASTATUR STIMMT' : 'TASTATUR FALSCH')
if (!process.env.OTA_BEHALTEN) {
  await page.evaluate(async (id) => fetch(`/api/sessions/${id}`, { method: 'DELETE' }), s.id)
}
await browser.disconnect()
