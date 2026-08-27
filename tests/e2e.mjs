/**
 * Ende-zu-Ende-Test der Oberfläche mit einem echten Browser.
 *
 * Prüft die Dinge, die sich nur im Browser prüfen lassen: dass der Secure
 * Context steht, dass die Zwischenablage-API erreichbar ist, dass das iframe
 * die nötige Erlaubnis trägt, und dass ein Nutzer nur sieht, was ihm gehört.
 */
import { execSync } from 'node:child_process'
import { mkdirSync, writeFileSync } from 'node:fs'
import puppeteer from 'puppeteer-core'

const BASE = process.env.OTA_BASE ?? 'https://192.168.66.224:8443'
const USER = process.env.OTA_USER ?? 'bmetallica'
/* Kein Vorgabewert: Ein Passwort im Quelltext ist eines, das irgendwann in
   einem Repository steht. Es kommt aus deploy/.env, die der Makefile-Ziel
   `test` einliest. */
const PW = process.env.OTA_TEST_ADMIN_PW ?? process.env.OTA_PW
if (!PW) {
  console.error('OTA_TEST_ADMIN_PW fehlt. Trag es in deploy/.env ein.')
  process.exit(2)
}
const SHOTS = process.env.OTA_SHOTS ?? '/tmp/ota-shots'
const CERT = '/opt/openterminalapps/deploy/certs/ota.crt'

mkdirSync(SHOTS, { recursive: true })

// Das eigene Zertifikat gezielt anerkennen, statt alle Zertifikatsfehler zu
// ignorieren — sonst würde der Test auch bei kaputtem TLS grün.
const spki = execSync(
  `openssl x509 -in ${CERT} -pubkey -noout | openssl pkey -pubin -outform der | openssl dgst -sha256 -binary | base64`,
  { shell: '/bin/bash' },
).toString().trim()

let pass = 0, fail = 0
const ok = (m) => { console.log(`  \x1b[32m✓\x1b[0m ${m}`); pass++ }
const bad = (m) => { console.log(`  \x1b[31m✗\x1b[0m ${m}`); fail++ }
const check = (cond, m) => (cond ? ok(m) : bad(m))

const shot = async (page, name) => {
  await page.screenshot({ path: `${SHOTS}/${name}.png` })
}

const browser = await puppeteer.launch({
  executablePath: '/usr/bin/chromium',
  headless: 'new',
  args: [
    '--no-sandbox', '--disable-gpu', '--disable-dev-shm-usage',
    `--ignore-certificate-errors-spki-list=${spki}`,
    '--window-size=1440,900',
  ],
  defaultViewport: { width: 1440, height: 900 },
})

// Die Zwischenablage-Freigabe erteilen, wie ein Nutzer sie im Browser gibt.
//
// Bewusst ueber das Protokoll und nicht ueber overridePermissions(): Dessen
// Name 'clipboard-write' landet in Chromium nicht auf dem Recht, das
// writeText() tatsaechlich prueft. Ergebnis war "Write permission denied"
// trotz erteilter Freigabe — was frueher als Grenze der Testumgebung
// verbucht wurde, obwohl nur der falsche Name gesetzt war.
const cdp = await browser.target().createCDPSession()
await cdp.send('Browser.grantPermissions', {
  origin: BASE,
  permissions: ['clipboardReadWrite', 'clipboardSanitizedWrite'],
})

// Die Oberflaeche richtet sich nach der Browsersprache. Der Test prueft
// deutsche Beschriftungen, also wird sie hier gesetzt — sonst haengt das
// Ergebnis davon ab, wie der Rechner eingestellt ist, auf dem er laeuft.
const page = await browser.newPage()
await page.evaluateOnNewDocument(() => {
  try { localStorage.setItem('ota.lang', 'de') } catch { /* privater Modus */ }
})
const errors = []
page.on('pageerror', (e) => errors.push(String(e)))
page.on('console', (m) => { if (m.type() === 'error') errors.push(m.text()) })

try {
  console.log(`\nOTA Oberflächentest gegen ${BASE}\n`)

  // ------------------------------------------------------------ Anmeldung
  console.log('Anmeldung')
  await page.goto(BASE, { waitUntil: 'networkidle2', timeout: 30000 })
  await shot(page, '01-login')

  check(await page.evaluate(() => window.isSecureContext),
    'Seite läuft im Secure Context (Voraussetzung für die Zwischenablage)')
  check(await page.evaluate(() => typeof navigator.clipboard?.writeText === 'function'),
    'navigator.clipboard.writeText steht zur Verfügung')

  await page.waitForSelector('input[autocomplete="username"]', { timeout: 10000 })
  await page.type('input[autocomplete="username"]', USER)
  await page.type('input[autocomplete="current-password"]', PW)
  await Promise.all([
    page.click('button.btn--primary'),
    page.waitForSelector('.rail', { timeout: 20000 }),
  ])
  ok('Anmeldung erfolgreich, Dashboard erscheint')

  // ------------------------------------------------------------ Dashboard
  console.log('\nDashboard')
  // Auf die geladenen Daten warten, nicht nur auf das Gerüst.
  await page.waitForSelector('.h-page', { timeout: 20000 })
  await page.waitForSelector('.tiles, .empty', { timeout: 20000 })
  await new Promise((r) => setTimeout(r, 900))
  await shot(page, '02-dashboard')
  const heading = await page.$eval('.h-page', (el) => el.textContent?.trim())
  check(!!heading, `Begrüßung wird angezeigt („${heading}")`)

  const tiles = await page.$$eval('.tile', (els) => els.length)
  check(tiles > 0, `${tiles} App-Kachel(n) sichtbar`)

  const bays = await page.$$eval('.bay', (els) => els.length)
  ok(`${bays} laufende Session(s) auf dem Dashboard`)

  const adminNav = await page.$$eval('.rail__btn .rail__cap',
    (els) => els.map((e) => e.textContent))
  check(adminNav.includes('Workspaces'), 'Administrator sieht den Verwaltungsbereich')

  // ------------------------------------------------------------ Verwaltung
  console.log('\nVerwaltung')
  await page.evaluate(() => {
    const b = [...document.querySelectorAll('.rail__btn')]
      .find((x) => x.textContent?.includes('Workspaces'))
    b?.click()
  })
  await page.waitForSelector('.meters', { timeout: 15000 })
  await shot(page, '03-workspaces')

  const meters = await page.$$eval('.meter__val', (els) => els.map((e) => e.textContent?.trim()))
  check(meters.length === 3, `Kapazitätsanzeige zeigt drei Werte: ${meters.join(' · ')}`)

  const rows = await page.$$eval('.tbl tbody tr', (els) => els.length)
  check(rows > 0, `${rows} Workspace(s) in der Liste`)

  // ------------------------------------------------------------ Editor
  console.log('\nWorkspace-Editor')
  await page.click('.tbl tbody tr')
  // Seit M5 übernimmt der Editor das Hauptfenster statt einer Seitenleiste:
  // App-Listen, Build-Protokolle und Zuteilungen brauchen Breite.
  await page.waitForSelector('.wb__tabs', { timeout: 10000 })
  const crumb = await page.$eval('.wb__crumb', (e) => e.textContent?.replace(/\s+/g, ' ') ?? '')
  check(crumb.startsWith('Workspaces'), `Editor liegt eine Ebene tiefer: ${crumb}`)
  const wide = await page.$eval('.wb__body', (e) => Math.round(e.getBoundingClientRect().width))
  check(wide > 700, `Bearbeitungsfläche ist ${wide} px breit`)

  await page.evaluate(() => {
    const t = [...document.querySelectorAll('.wb__tab')]
      .find((x) => x.textContent?.includes('Ressourcen'))
    t?.click()
  })
  await page.waitForSelector('.fader', { timeout: 10000 })
  await shot(page, '04-editor-ressourcen')

  const faders = await page.$$eval('.fader', (els) => els.length)
  check(faders >= 3, `${faders} Regler statt Eingabefelder`)

  // Die Überbuchungs-Schraffur muss auf der realen Host-Grenze sitzen.
  const limit = await page.$eval('.fader', (el) =>
    getComputedStyle(el).getPropertyValue('--limit').trim())
  check(limit.endsWith('%') && parseFloat(limit) > 0 && parseFloat(limit) <= 100,
    `Kapazitätsgrenze auf der Schiene: ${limit}`)

  // Skalenstriche müssen auf ihrem Wert sitzen, nicht gleichmäßig verteilt.
  const tickPositions = await page.$$eval('.fader__tick',
    (els) => els.map((e) => e.style.left))
  check(tickPositions.length > 0 && tickPositions.some((p) => p && p !== ''),
    `Skalenstriche wertgenau positioniert (${tickPositions.filter(Boolean).length} Striche)`)

  await page.evaluate(() => {
    const t = [...document.querySelectorAll('.wb__tab')]
      .find((x) => x.textContent?.includes('Rechte'))
    t?.click()
  })
  await page.waitForSelector('.toggle', { timeout: 10000 })
  const toggles = await page.$$eval('.toggle', (els) => els.length)
  check(toggles >= 8, `${toggles} Schalter im Rechte-Reiter`)
  await shot(page, '05-editor-rechte')

  // Zuteilung je Nutzer
  await page.evaluate(() => {
    const t = [...document.querySelectorAll('.wb__tab')]
      .find((x) => x.textContent?.includes('Zuteilung'))
    t?.click()
  })
  await page.waitForSelector('.assign', { timeout: 10000 })
  await new Promise((r) => setTimeout(r, 1200))
  await shot(page, '06-editor-zuteilung')
  const allocRows = await page.$$eval('.alloc__row', (els) => els.length).catch(() => 0)
  ok(`Zuteilung je Nutzer: ${allocRows} Zeile(n)`)

  // Sichtbarkeit je Anwendung. Der Normalfall ist „für alle" — die Zeile
  // steht trotzdem da, weil sonst niemand ahnt, dass sich das einschränken
  // lässt.
  await page.evaluate(() => {
    const t = [...document.querySelectorAll('.wb__tab')]
      .find((x) => x.textContent?.includes('Software'))
    t?.click()
  })
  await page.waitForSelector('.applist__row, .btn', { timeout: 15000 })
  await page.evaluate(() => {
    const b = [...document.querySelectorAll('button')]
      .find((x) => /Im Image nachsehen/.test(x.textContent ?? ''))
    b?.click()
  })
  const appRows = await page.waitForSelector('.applist__row', { timeout: 90000 })
    .then(() => page.$$eval('.applist__row', (els) => els.length))
    .catch(() => 0)
  if (appRows > 0) {
    check(appRows > 0, `App-Katalog zeigt ${appRows} Anwendung(en)`)

    const vis = await page.$eval('.applist__vis', (e) => e.textContent?.trim() ?? '')
      .catch(() => '')
    check(/alle|everyone/i.test(vis), `Ohne Einschränkung steht dort „${vis}"`)

    await page.click('.applist__vis')
    await new Promise((r) => setTimeout(r, 300))
    const chips = await page.$$eval('.applist__chips .chip', (els) => els.length)
    check(chips > 0, `${chips} Gruppe(n) zur Auswahl`)

    await page.click('.applist__chips .chip')
    await new Promise((r) => setTimeout(r, 300))
    const picked = await page.$eval('.applist__vis', (e) => e.textContent?.trim() ?? '')
    check(/Nur für|Only for/.test(picked), `Nach der Wahl: „${picked}"`)
    await shot(page, '07-app-sichtbarkeit')

    // Wieder abwählen — der Test hinterlässt keinen eingeschränkten Katalog.
    await page.click('.applist__chips .chip')
    await new Promise((r) => setTimeout(r, 300))
  } else {
    ok('Kein Image zum Durchsehen — Abschnitt übersprungen')
  }

  await page.keyboard.press('Escape')

  // ------------------------------------------------------------ Session
  console.log('\nSession-Viewer')
  await page.evaluate(() => {
    const b = [...document.querySelectorAll('.rail__btn')]
      .find((x) => x.textContent?.includes('Start'))
    b?.click()
  })
  await page.waitForSelector('.tiles', { timeout: 15000 })

  // Sessions oeffnen seit M4 in einem eigenen Tab. Der Test folgt dem Tab —
  // "page" bleibt das Dashboard, "view" ist die Session.
  const hasBay = await page.$('.bay')
  const opened = new Promise((resolve) => browser.once('targetcreated',
    (t) => resolve(t.page())))
  if (hasBay) {
    await page.click('.bay .btn--primary')
  } else {
    await page.click('.tile')
    ok('Session über die Kachel gestartet')
  }

  const view = await opened
  check(!!view, 'Session öffnet in einem eigenen Tab')
  check(/\/view\/s\/[0-9a-f-]{36}/.test(view.url()),
    `Der Tab hat eine eigene Adresse (${new URL(view.url()).pathname})`)

  {
    await view.waitForSelector('.viewer__frame', { timeout: 120000 })
    ok('Session-Viewer öffnet')

    const allow = await view.$eval('.viewer__frame', (el) => el.getAttribute('allow'))
    check(allow?.includes('clipboard-read') && allow?.includes('clipboard-write'),
      `iframe trägt die Zwischenablage-Erlaubnis (${allow?.slice(0, 46)}…)`)

    // Warten, bis der Stream wirklich verbunden ist. Der Titel allein sagt
    // nichts — die Seite lädt auch dann, wenn der Websocket scheitert.
    let state = null
    for (let i = 0; i < 20; i++) {
      await new Promise((r) => setTimeout(r, 1500))
      state = await view.evaluate(() => {
        const d = document.querySelector('.viewer__frame')?.contentDocument
        if (!d) return null
        return { cls: d.documentElement.className, canvas: !!d.querySelector('canvas') }
      })
      if (state?.cls?.includes('noVNC_connected')) break
    }
    check(state?.cls?.includes('noVNC_connected'),
      `Websocket verbunden (Zustand: ${state?.cls ?? 'unbekannt'})`)
    check(state?.canvas === true, 'Bildfläche des Streams vorhanden')
    await shot(view, '07-session')

    // Kontrollleiste öffnen.
    //
    // Bewusst über den Griff am Rand, nicht über ein Tastenkürzel: Der ferne
    // Desktop beansprucht die Tastatur für sich — gemessen kommen Control und
    // Alt noch am iframe an, Shift und Buchstaben nicht mehr. Ein Kürzel, das
    // im laufenden Stream verlässlich greift, gibt es deshalb nicht. Der Griff
    // liegt im Elternfenster und funktioniert immer.
    await view.click('.viewer__handle')
    await new Promise((r) => setTimeout(r, 500))
    const barOpen = await view.$('.viewer__bar')
    check(!!barOpen, 'Griff am Rand öffnet die Kontrollleiste')
    if (barOpen) await shot(view, '08-session-leiste')

    // Zwischenablage — der vollstaendige Weg in beide Richtungen.
    //
    // Der Viewer zeigt den Stream in einem iframe, und genau dort schaltet
    // KasmVNCs Weboberflaeche die Zwischenablage von sich aus ab (siehe
    // web/src/lib/clipboardBridge.ts). Deshalb pruefen wir zuerst, dass die
    // Schalter im Client wirklich stehen, und danach den Rundlauf.
    if (barOpen) {
      const switches = await view.evaluate(() => {
        const d = document.querySelector('.viewer__frame').contentDocument
        const g = (id) => d.getElementById(id)?.checked ?? null
        return {
          up: g('noVNC_setting_clipboard_up'),
          down: g('noVNC_setting_clipboard_down'),
        }
      })
      check(switches.up === true && switches.down === true,
        `Client meldet die Zwischenablage im iframe als offen (${JSON.stringify(switches)})`)

      // Richtung Browser → Session.
      const outbound = `AUS-DEM-BROWSER-${Date.now()} äöü ß`
      await view.evaluate((t) => navigator.clipboard.writeText(t), outbound)
      await new Promise((r) => setTimeout(r, 2500))
      const inSession = await view.evaluate(() => {
        const d = document.querySelector('.viewer__frame').contentDocument
        return d.getElementById('noVNC_clipboard_text').value
      })
      check(inSession === outbound,
        `Browser → Session uebertraegt Umlaute (${inSession.slice(0, 28)}…)`)

      // Richtung Session → Browser: im Container kopieren und im Elternfenster
      // nachsehen. Beides ausserhalb des Browsers zu erzeugen ist der einzige
      // Weg, der den echten Fall trifft — ein Klick im Stream wuerde nur die
      // Anwendung im Container bedienen, nicht ihre Zwischenablage.
      const cn = execSync(`docker ps --filter "label=ota.session_id" --format '{{.Names}}'`)
        .toString().trim().split('\n')[0]
      const inbound = `AUS-DER-SESSION-${Date.now()} äöü ß`
      if (cn) {
        execSync(`docker exec -u 1000 ${cn} bash -c ` +
          `'export HOME=/home/kasm-user XAUTHORITY=/home/kasm-user/.Xauthority; ` +
          `printf %s ${JSON.stringify(inbound)} | timeout 3 xclip -d :1 -selection clipboard -i' &`,
          { shell: '/bin/bash' })
        await new Promise((r) => setTimeout(r, 3500))
        const backInBrowser = await view.evaluate(() => navigator.clipboard.readText())
        check(backInBrowser === inbound,
          `Session → Browser landet in der System-Zwischenablage (${backInBrowser.slice(0, 28)}…)`)
      } else {
        bad('Kein Session-Container fuer die Richtung Session → Browser gefunden')
      }

      // Der Rueckfallweg ueber das Panel muss trotzdem bedienbar bleiben —
      // Firefox gibt das Schreiben ohne Nutzergeste nicht frei.
      await view.type('.viewer__clip', 'Prüftext für die Zwischenablage: äöü ß 123')
      const typed = await view.$eval('.viewer__clip', (el) => el.value)
      check(typed.includes('äöü ß'),
        'Zwischenablage-Panel nimmt Text inklusive Umlauten an')

      const buttons = await view.$$eval('.viewer__row .btn', (els) => els.map((e) => e.textContent))
      check(buttons.some((b) => b?.includes('In die Session')) &&
            buttons.some((b) => b?.includes('Aus der Session')),
        'Beide Richtungen sind als Rueckfallweg bedienbar')
    }

    await view.close()
    await page.bringToFront()
    await page.waitForSelector('.tiles', { timeout: 15000 })
    ok('Das Dashboard bleibt im ersten Tab stehen')
  }

  // ------------------------------------------------- Nutzer und Gruppen
  console.log('\nNutzer und Gruppen')
  await page.evaluate(() => {
    const b = [...document.querySelectorAll('.rail__btn')]
      .find((x) => x.textContent?.includes('Nutzer'))
    b?.click()
  })
  await page.waitForSelector('.tbl', { timeout: 15000 })
  const userRows = await page.$$eval('.tbl tbody tr', (els) => els.length)
  check(userRows > 0, `${userRows} Nutzer in der Liste`)
  await shot(page, '11-nutzer')

  // Nutzer anlegen — bis M3 ging das nur über die API.
  await page.evaluate(() => {
    const b = [...document.querySelectorAll('.topbar .btn--primary')]
      .find((x) => x.textContent?.includes('Nutzer anlegen'))
    b?.click()
  })
  await page.waitForSelector('.drawer', { timeout: 10000 })
  const testName = `pruef-${Date.now().toString().slice(-6)}`
  await page.type('.drawer input[aria-label="Benutzername"]', testName)
  await page.type('.drawer input[aria-label="Passwort"]', 'PruefKonto2026!xy')
  await page.evaluate(() => {
    const chip = [...document.querySelectorAll('.drawer .chip')]
      .find((x) => x.textContent?.trim() === 'users')
    chip?.click()
  })
  await page.evaluate(() => {
    const b = [...document.querySelectorAll('.drawer__foot .btn--primary')]
      .find((x) => x.textContent?.includes('anlegen'))
    b?.click()
  })
  await new Promise((r) => setTimeout(r, 2000))
  const afterCreate = await page.$$eval('.tbl tbody tr', (els) => els.length)
  check(afterCreate === userRows + 1, `Nutzer über die Oberfläche angelegt (${userRows} → ${afterCreate})`)

  // Wieder aufräumen — ein Test, der Spuren hinterlässt, verfälscht den nächsten.
  await page.evaluate((name) => {
    const row = [...document.querySelectorAll('.tbl tbody tr')]
      .find((x) => x.textContent?.includes(name))
    row?.click()
  }, testName)
  await page.waitForSelector('.drawer', { timeout: 10000 })
  await page.evaluate(() => {
    const b = [...document.querySelectorAll('.drawer__foot .btn--halt')]
      .find((x) => x.textContent?.includes('Löschen'))
    b?.click()
  })
  await new Promise((r) => setTimeout(r, 1800))
  const afterDelete = await page.$$eval('.tbl tbody tr', (els) => els.length)
  check(afterDelete === userRows, `Testnutzer wieder entfernt (${afterCreate} → ${afterDelete})`)

  // Gruppen-Reiter
  await page.evaluate(() => {
    const b = [...document.querySelectorAll('.seg__opt')]
      .find((x) => x.textContent?.includes('Gruppen'))
    b?.click()
  })
  await new Promise((r) => setTimeout(r, 700))
  const groupRows = await page.$$eval('.tbl tbody tr', (els) => els.length)
  check(groupRows >= 2, `${groupRows} Gruppen sichtbar`)
  await shot(page, '12-gruppen')

  // Systemgruppe: der Löschknopf darf gar nicht erst erscheinen.
  await page.evaluate(() => {
    const row = [...document.querySelectorAll('.tbl tbody tr')]
      .find((x) => x.textContent?.includes('admins'))
    row?.click()
  })
  await page.waitForSelector('.drawer', { timeout: 10000 })
  const hasDelete = await page.$$eval('.drawer__foot .btn--halt', (els) => els.length)
  check(hasDelete === 0, 'Systemgruppe admins bietet kein Löschen an')
  await page.keyboard.press('Escape')
  await new Promise((r) => setTimeout(r, 500))

  // ------------------------------------------------------------- Betrieb
  console.log('\nBetrieb')
  await page.evaluate(() => {
    const b = [...document.querySelectorAll('.rail__btn')]
      .find((x) => x.textContent?.includes('Betrieb'))
    b?.click()
  })
  await page.waitForSelector('.tbl, .empty', { timeout: 15000 })
  await new Promise((r) => setTimeout(r, 800))
  const sessRows = await page.$$eval('.tbl tbody tr', (els) => els.length).catch(() => 0)
  check(sessRows > 0, `${sessRows} laufende Session(en) in der Betriebsübersicht`)
  await shot(page, '13-betrieb')

  await page.evaluate(() => {
    const b = [...document.querySelectorAll('.seg__opt')]
      .find((x) => x.textContent?.includes('Protokoll'))
    b?.click()
  })
  await new Promise((r) => setTimeout(r, 800))
  const auditRows = await page.$$eval('.tbl tbody tr', (els) => els.length)
  check(auditRows > 0, `${auditRows} Einträge im Protokoll`)
  const actions = await page.$$eval('.tbl tbody tr td:nth-child(3)',
    (els) => els.map((e) => e.textContent))
  check(actions.some((a) => a === 'Anmeldung' || a === 'Nutzer angelegt'),
    `Vorgänge stehen in Klartext (z. B. „${actions[0]}")`)
  await shot(page, '14-protokoll')

  // Zurück zum Dashboard für den nächsten Abschnitt.
  await page.evaluate(() => {
    const b = [...document.querySelectorAll('.rail__btn')]
      .find((x) => x.textContent?.includes('Start'))
    b?.click()
  })

  // ------------------------------------------------------- Arbeitsplatz
  console.log('\nArbeitsplatz (mehrere Apps in einem Container)')
  await page.waitForSelector('.bay, .tiles', { timeout: 15000 })

  const strip = await page.$('.strip')
  if (strip) {
    const appNames = await page.$$eval('.bay .strip__app .strip__name',
      (els) => els.map((e) => e.textContent))
    check(appNames.length > 0, `App-Leiste zeigt ${appNames.length} Anwendungen: ${appNames.join(', ')}`)

    let openCount = await page.$$eval('.bay .strip__app.is-on', (els) => els.length)
    if (openCount === 0) {
      // Frischer Arbeitsplatz: eine Anwendung starten, damit der Abschnitt
      // unabhängig vom Vorzustand prüfbar bleibt. Sie öffnet in einem eigenen
      // Tab, der danach wieder zugeht.
      const spawn = new Promise((r) => browser.once('targetcreated', (t) => r(t.page())))
      await page.click('.bay .strip__app:not(:disabled)')
      const started = await spawn
      await started.waitForSelector('.viewer__frame', { timeout: 90000 })
      await started.close()
      await page.bringToFront()
      await page.waitForSelector('.bay .strip__app.is-on', { timeout: 30000 })
      openCount = await page.$$eval('.bay .strip__app.is-on', (els) => els.length)
      ok('Anwendung im Arbeitsplatz für den Test gestartet')
    }
    check(openCount > 0, `${openCount} Anwendung(en) laufen im Container`)

    const facts = await page.$$eval('.bay__fact b', (els) => els.map((e) => e.textContent))
    check(facts.some((f) => f?.includes('von')), `Zähler "Apps offen": ${facts.find((f) => f?.includes('von'))}`)

    // Eine laufende App öffnen und prüfen, dass ihr eigener Stream verbindet.
    //
    // Bewusst die LETZTE laufende App: Die erste ist oft eine
    // Einzelinstanz-Anwendung, die das Image selbst auf dem Hauptbildschirm
    // startet — die hat dann keine eigene /a/-Route, und das ist richtig so.
    const running = await page.$$('.bay .strip__app.is-on')
    const appTab = new Promise((r) => browser.once('targetcreated', (t) => r(t.page())))
    await running[running.length - 1].click()
    const appView = await appTab
    await appView.waitForSelector('.viewer__frame', { timeout: 60000 })
    const appSrc = await appView.$eval('.viewer__frame', (el) => el.getAttribute('src'))
    check(/\/s\/[0-9a-f-]{36}\//.test(appSrc ?? ''),
      `Stream der App wird geladen (${appSrc?.slice(0, 44)}…)`)
    if (running.length > 1) {
      check(appSrc?.includes('/a/'),
        'Zusätzliche App läuft auf einem eigenen Display')
    }

    let appState = null
    for (let i = 0; i < 20; i++) {
      await new Promise((r) => setTimeout(r, 1500))
      appState = await appView.evaluate(() => {
        const d = document.querySelector('.viewer__frame')?.contentDocument
        return d ? d.documentElement.className : null
      })
      if (appState?.includes('noVNC_connected')) break
    }
    check(appState?.includes('noVNC_connected'), 'Eigener Stream der App verbindet')

    // Fenstersturm-Wache.
    //
    // Am 2026-08-27 startete das geerbte Startskript des Basisimages die
    // Anwendung alle drei Sekunden neu; VS Code ist einzelinstanzig und
    // oeffnete dabei jedes Mal ein neues leeres Fenster. Nach sechs Minuten
    // waren es 119, der Bildschirm blieb schwarz — und nichts davon war an
    // der Oberflaeche zu sehen. Diese Pruefung schaut deshalb im Container
    // nach, nicht im Browser. Sie ist der einzige Weg, diesen Fehler
    // automatisch zu bemerken.
    const cnWs = execSync(`docker ps --filter "label=ota.session_id" --format '{{.Names}}'`)
      .toString().trim().split('\n')[0]
    if (cnWs) {
      const windows = execSync(
        `docker exec ${cnWs} bash -lc 'export HOME=/home/kasm-user ` +
        `XAUTHORITY=$HOME/.Xauthority; DISPLAY=:1 wmctrl -l 2>/dev/null | awk "\\$2 != -1"'`,
        { shell: '/bin/bash' }).toString().trim()
      const count = windows ? windows.split('\n').length : 0
      // Der Hintergrund ("Desktop", Arbeitsflaeche -1) ist herausgefiltert.
      // Uebrig bleiben echte Anwendungsfenster; mehr als eine Handvoll je
      // Anwendung ist immer ein Fehler, nie Absicht.
      check(count <= 3,
        `Display :1 zeigt ${count} Anwendungsfenster (kein Fenstersturm)`)
    }
    await shot(page, '09-arbeitsplatz-app')

    // Umschalter in der Kontrollleiste
    await appView.click('.viewer__handle')
    await new Promise((r) => setTimeout(r, 600))
    const switcher = await appView.$$eval('.viewer__bar .strip__app .strip__name',
      (els) => els.map((e) => e.textContent)).catch(() => [])
    check(switcher.includes('Desktop') && switcher.length > 1,
      `Umschalter bietet ${switcher.length} Ansichten: ${switcher.join(', ')}`)
    await shot(page, '10-arbeitsplatz-umschalter')

    await appView.close()
    await page.bringToFront()
    await page.waitForSelector('.tiles', { timeout: 15000 })
  } else {
    ok('Kein Arbeitsplatz mit App-Katalog vorhanden — Abschnitt übersprungen')
  }

  // ------------------------------------------------------------- Hilfe
  console.log('\nHandbuch und Einstellungen')
  await page.evaluate(() => {
    const b = [...document.querySelectorAll('.rail__btn')]
      .find((x) => x.textContent?.includes('Hilfe'))
    b?.click()
  })
  await page.waitForSelector('.book__item', { timeout: 15000 })
  const chapters = await page.$$eval('.book__item', (els) => els.map((e) => e.textContent))
  check(chapters.length >= 10, `${chapters.length} Kapitel im Handbuch`)
  const firstHeading = await page.$eval('.md-h1', (e) => e.textContent).catch(() => null)
  check(!!firstHeading, `Kapitel wird gesetzt dargestellt („${firstHeading}")`)
  check((await page.$$('.md-table')).length >= 0, 'Tabellen im Handbuch werden gerendert')
  await shot(page, '15-handbuch')

  // Verweise zwischen Kapiteln bleiben im Programm.
  const inlineLink = await page.$('.md a[data-chapter]')
  if (inlineLink) {
    await inlineLink.click()
    await new Promise((r) => setTimeout(r, 700))
    const after = await page.$eval('.md-h1', (e) => e.textContent).catch(() => null)
    check(after !== firstHeading, `Verweis wechselt das Kapitel („${after}")`)
  }

  await page.evaluate(() => {
    const b = [...document.querySelectorAll('.rail__btn')]
      .find((x) => x.textContent?.includes('Einstellungen'))
    b?.click()
  })
  await page.waitForSelector('.fader', { timeout: 15000 })
  const idle = await page.$eval('.fader__value', (e) => e.textContent)
  check(/min|h/.test(idle ?? ''), `Anmeldefrist einstellbar (${idle})`)
  await shot(page, '16-einstellungen')

  // ----------------------------------------------------------- Sprache
  console.log('\nSprache')
  await page.evaluate(() => {
    const b = [...document.querySelectorAll('.rail__langopt')].find((x) => x.textContent === 'EN')
    b?.click()
  })
  await new Promise((r) => setTimeout(r, 400))
  const navEn = await page.$$eval('.rail__cap', (els) => els.map((e) => e.textContent))
  check(navEn.includes('Settings') && navEn.includes('Help'),
    `Oberfläche wechselt nach Englisch (${navEn.join(', ')})`)
  const labelEn = await page.$eval('.field__label', (e) => e.textContent)
  check(!/[äöüß]/i.test(labelEn ?? ''), `Auch die Felder übersetzen ("${labelEn}")`)
  await shot(page, '17-englisch')

  await page.evaluate(() => {
    const b = [...document.querySelectorAll('.rail__langopt')].find((x) => x.textContent === 'DE')
    b?.click()
  })
  await new Promise((r) => setTimeout(r, 400))
  const navDe = await page.$$eval('.rail__cap', (els) => els.map((e) => e.textContent))
  check(navDe.includes('Einstellungen'), 'Zurück auf Deutsch')

  // ------------------------------------------------ Verknüpfung, Erweiterung
  console.log('\nVerknüpfungen')
  const pwa = await page.evaluate(async () => {
    const r = await fetch('/api/pwa/manifest.webmanifest?template=arbeitsplatz&app=vscode')
    return r.ok ? await r.json() : null
  })
  check(pwa?.display === 'standalone' && pwa?.start_url?.startsWith('/launch/'),
    `Manifest für die Desktop-Verknüpfung (${pwa?.name} → ${pwa?.start_url})`)

  const ext = await page.evaluate(async () => {
    const r = await fetch('/api/help/extension/firefox')
    return { ok: r.ok, type: r.headers.get('content-type'), size: (await r.blob()).size }
  })
  check(ext.ok && ext.size > 1000,
    `Firefox-Erweiterung steht bereit (${ext.size} Bytes, ${ext.type})`)

  const sw = await page.evaluate(() => navigator.serviceWorker?.controller !== undefined)
  check(sw, 'Service Worker ist eingerichtet')

  // ------------------------------------------------------- Registries
  console.log('\nRegistries')
  await page.evaluate(() => {
    const b = [...document.querySelectorAll('.rail__btn')]
      .find((x) => x.textContent?.includes('Registries'))
    b?.click()
  })
  await page.waitForSelector('.chip--add, .tbl tbody tr', { timeout: 15000 })

  const regRows = await page.$$eval('.tbl tbody tr', (els) => els.length).catch(() => 0)
  if (regRows > 0) {
    await page.click('.tbl tbody tr')
    await page.waitForSelector('.catalog__item', { timeout: 20000 })
    const items = await page.$$eval('.catalog__item', (els) => els.length)
    check(items > 20, `Katalog zeigt ${items} Anwendungen`)

    // Die Grösse ist der Grund, warum das eine Liste und keine Kachelwand ist:
    // Ein Eintrag wiegt 5 bis 10 GB, und das muss vor dem Klick dastehen.
    const sizes = await page.$$eval('.catalog__size', (els) => els.map((e) => e.textContent))
    check(sizes.every((s) => /GB|MB/.test(s ?? '')),
      `Jeder Eintrag nennt seine Grösse (z. B. ${sizes[0]})`)

    // Symbole laufen über die eigene API — die Inhaltsregel lässt keine
    // fremden Bildquellen zu.
    const iconSrc = await page.$eval('.catalog__item img', (e) => e.getAttribute('src'))
      .catch(() => null)
    check(iconSrc?.startsWith('/api/'),
      `Symbole kommen aus der eigenen Herkunft (${iconSrc?.slice(0, 34) ?? '—'}…)`)

    // Ein arm64-Image auf diesem Host liesse sich uebernehmen und wuerde erst
    // beim Start scheitern — mit einer Meldung, die niemand mit dem Katalog in
    // Verbindung bringt. Geprueft wird gegen den Katalog selbst, nicht gegen
    // eine Annahme: Wie viele Eintraege passen nicht, wie viele sind gesperrt?
    const arch = await page.evaluate(async () => {
      const regs = await (await fetch('/api/admin/registries')).json()
      const list = await (await fetch(`/api/admin/registries/${regs[0].id}/entries`)).json()
      const host = await (await fetch('/api/admin/host')).json()
      const map = { x86_64: 'amd64', aarch64: 'arm64' }
      const here = map[host.architecture] ?? host.architecture
      return {
        here,
        fremd: list.filter((e) => e.architectures.length && !e.architectures.includes(here)).length,
      }
    })
    const blocked = await page.$$eval('.catalog__item button[disabled]', (e) => e.length)
    check(blocked === arch.fremd,
      `Fremde Architektur gesperrt: ${blocked} von ${items} (Host ist ${arch.here})`)

    await page.type('input[aria-label="Katalog durchsuchen"]', 'firefox')
    await new Promise((r) => setTimeout(r, 600))
    const found = await page.$$eval('.catalog__item .catalog__head b', (e) => e.map((x) => x.textContent))
    check(found.length > 0 && found.every((n) => /firefox/i.test(n ?? '')),
      `Suche filtert den Katalog (${found.join(', ')})`)
    await shot(page, '19-registry')

    await page.evaluate(() => document.querySelector('.wb__up')?.click())
    await page.waitForSelector('.tbl tbody tr', { timeout: 10000 })
  } else {
    ok('Keine Registry eingetragen — Abschnitt übersprungen')
  }

  // --------------------------------------------------------- Mein Konto
  console.log('\nMein Konto')
  await page.evaluate(() => {
    const b = [...document.querySelectorAll('.rail__btn')]
      .find((x) => x.textContent?.includes('Mein Konto'))
    b?.click()
  })
  await page.waitForSelector('.wb__tabs', { timeout: 15000 })
  const accountTabs = await page.$$eval('.wb__tab', (els) => els.map((e) => e.textContent))
  check(accountTabs.join(',') === 'Passwort,Zwei-Faktor,Sprache',
    `Eigenes Konto mit drei Bereichen (${accountTabs.join(', ')})`)

  // Ein normaler Nutzer konnte sein Passwort bis M2 nicht selbst ändern.
  const pwFields = await page.$$eval('.wb__body input[type="password"]', (e) => e.length)
  check(pwFields === 3, `Passwortwechsel steht jedem offen (${pwFields} Felder)`)

  await page.evaluate(() => {
    const t = [...document.querySelectorAll('.wb__tab')]
      .find((x) => x.textContent?.includes('Zwei-Faktor'))
    t?.click()
  })
  await new Promise((r) => setTimeout(r, 400))
  const totpText = await page.$eval('.wb__body', (e) => e.innerText)
  check(/Zwei-Faktor einrichten/.test(totpText),
    'Zwei-Faktor lässt sich selbst einrichten')
  await shot(page, '18-konto')

  // ------------------------------------------------------------- Ablage
  console.log('\nAblage und Startskript')
  await page.evaluate(() => {
    const b = [...document.querySelectorAll('.rail__btn')]
      .find((x) => x.textContent?.includes('Ablage'))
    b?.click()
  })
  await page.waitForSelector('.drop', { timeout: 15000 })
  ok('Ablage öffnet mit Ziehfläche')

  // Hochladen über die API, weil ein echtes Ziehen im Browser sich nicht
  // nachstellen lässt. Geprüft wird, was dabei zählt: dass die Datei
  // ankommt und dass sie im Container **nur lesbar** liegt.
  const stamp = `pruef-${Date.now()}.txt`
  const stored = await page.evaluate(async (name) => {
    const body = new FormData()
    body.append('file', new File(['OTA-Pruefdatei'], name, { type: 'text/plain' }))
    const r = await fetch('/api/shared/upload?path=', { method: 'POST', body })
    return r.ok ? await r.json() : null
  }, stamp)
  check(stored?.name === stamp, `Datei landet in der Ablage (${stored?.name ?? '—'})`)

  const cnShared = execSync(`docker ps --filter "label=ota.session_id" --format '{{.Names}}'`)
    .toString().trim().split('\n')[0]
  if (cnShared) {
    const inside = execSync(
      `docker exec ${cnShared} bash -lc 'ls /mnt/ota/${stamp} 2>&1; ` +
      `touch /mnt/ota/darf-nicht 2>&1 | head -1'`, { shell: '/bin/bash' })
      .toString()
    check(inside.includes(stamp), 'Die Datei liegt im Arbeitsplatz unter /mnt/ota')
    check(/[Rr]ead-only/.test(inside),
      'Die Ablage ist im Arbeitsplatz schreibgeschützt')

    const link = execSync(
      `docker exec ${cnShared} bash -lc 'readlink /home/kasm-user/Gemeinsam || echo -'`,
      { shell: '/bin/bash' }).toString().trim()
    check(link === '/mnt/ota', `Verweis im Home zeigt auf die Ablage (${link})`)
  }

  // Wieder aufräumen, damit der Test wiederholbar bleibt.
  await page.evaluate((name) =>
    fetch(`/api/shared?path=${encodeURIComponent(name)}`, { method: 'DELETE' }), stamp)

  // ------------------------------------------------------------ Abmelden
  console.log('\nAbmelden')
  await page.evaluate(() => {
    const b = [...document.querySelectorAll('.rail__btn')]
      .find((x) => x.textContent?.includes('Abmelden'))
    b?.click()
  })
  await page.waitForSelector('.login', { timeout: 15000 })
  ok('Abmelden führt zurück zur Anmeldung')

  // ------------------------------------------------------------ JS-Fehler
  console.log('\nKonsole')
  const relevant = errors.filter((e) =>
    !/favicon|net::ERR_CERT|Failed to load resource: the server responded with a status of 40/i.test(e))
  const wsErrors = errors.filter((e) => /websocket|websockify/i.test(e))
  check(wsErrors.length === 0,
    wsErrors.length ? `Websocket-Fehler: ${wsErrors[0].slice(0, 90)}` : 'Keine Websocket-Fehler')
  check(relevant.length === 0,
    relevant.length ? `JavaScript-Fehler: ${relevant.slice(0, 2).join(' | ')}` : 'Keine JavaScript-Fehler')

} catch (err) {
  bad(`Abbruch: ${err.message}`)
  try { await shot(page, 'zz-fehler') } catch { /* egal */ }
} finally {
  await browser.close()
}

console.log('\n─────────────────────────────────────')
console.log(`  bestanden: ${pass}   fehlgeschlagen: ${fail}`)
console.log(`  Screenshots: ${SHOTS}`)
process.exit(fail === 0 ? 0 : 1)
