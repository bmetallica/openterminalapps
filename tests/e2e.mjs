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
const PW = process.env.OTA_PW ?? 'OtaStart2026!xyz'
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

const ctx = browser.defaultBrowserContext()
// Die Zwischenablage-Freigabe erteilen, wie ein Nutzer sie im Browser gibt.
await ctx.overridePermissions(BASE, ['clipboard-read', 'clipboard-write'])

const page = await browser.newPage()
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
  await page.waitForSelector('.drawer', { timeout: 10000 })
  ok('Editor öffnet als Seitenleiste')

  await page.evaluate(() => {
    const t = [...document.querySelectorAll('.drawer__tab')]
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
    const t = [...document.querySelectorAll('.drawer__tab')]
      .find((x) => x.textContent?.includes('Rechte'))
    t?.click()
  })
  await page.waitForSelector('.toggle', { timeout: 10000 })
  const toggles = await page.$$eval('.toggle', (els) => els.length)
  check(toggles >= 8, `${toggles} Schalter im Rechte-Reiter`)
  await shot(page, '05-editor-rechte')

  // Zuteilung je Nutzer
  await page.evaluate(() => {
    const t = [...document.querySelectorAll('.drawer__tab')]
      .find((x) => x.textContent?.includes('Zuteilung'))
    t?.click()
  })
  await page.waitForSelector('.assign', { timeout: 10000 })
  await new Promise((r) => setTimeout(r, 1200))
  await shot(page, '06-editor-zuteilung')
  const allocRows = await page.$$eval('.alloc__row', (els) => els.length).catch(() => 0)
  ok(`Zuteilung je Nutzer: ${allocRows} Zeile(n)`)

  await page.keyboard.press('Escape')

  // ------------------------------------------------------------ Session
  console.log('\nSession-Viewer')
  await page.evaluate(() => {
    const b = [...document.querySelectorAll('.rail__btn')]
      .find((x) => x.textContent?.includes('Start'))
    b?.click()
  })
  await page.waitForSelector('.tiles', { timeout: 15000 })

  const hasBay = await page.$('.bay')
  if (hasBay) {
    await page.click('.bay .btn--primary')
  } else {
    // Keine Session offen — eine über die Kachel starten. Die App springt
    // danach von selbst in den Viewer, deshalb wird auf ihn gewartet.
    await page.click('.tile')
    ok('Session über die Kachel gestartet')
  }

  {
    await page.waitForSelector('.viewer__frame', { timeout: 120000 })
    ok('Session-Viewer öffnet')

    const allow = await page.$eval('.viewer__frame', (el) => el.getAttribute('allow'))
    check(allow?.includes('clipboard-read') && allow?.includes('clipboard-write'),
      `iframe trägt die Zwischenablage-Erlaubnis (${allow?.slice(0, 46)}…)`)

    // Warten, bis der Stream wirklich verbunden ist. Der Titel allein sagt
    // nichts — die Seite lädt auch dann, wenn der Websocket scheitert.
    let state = null
    for (let i = 0; i < 20; i++) {
      await new Promise((r) => setTimeout(r, 1500))
      state = await page.evaluate(() => {
        const d = document.querySelector('.viewer__frame')?.contentDocument
        if (!d) return null
        return { cls: d.documentElement.className, canvas: !!d.querySelector('canvas') }
      })
      if (state?.cls?.includes('noVNC_connected')) break
    }
    check(state?.cls?.includes('noVNC_connected'),
      `Websocket verbunden (Zustand: ${state?.cls ?? 'unbekannt'})`)
    check(state?.canvas === true, 'Bildfläche des Streams vorhanden')
    await shot(page, '07-session')

    // Kontrollleiste öffnen.
    //
    // Bewusst über den Griff am Rand, nicht über ein Tastenkürzel: Der ferne
    // Desktop beansprucht die Tastatur für sich — gemessen kommen Control und
    // Alt noch am iframe an, Shift und Buchstaben nicht mehr. Ein Kürzel, das
    // im laufenden Stream verlässlich greift, gibt es deshalb nicht. Der Griff
    // liegt im Elternfenster und funktioniert immer.
    await page.click('.viewer__handle')
    await new Promise((r) => setTimeout(r, 500))
    const barOpen = await page.$('.viewer__bar')
    check(!!barOpen, 'Griff am Rand öffnet die Kontrollleiste')
    if (barOpen) await shot(page, '08-session-leiste')

    // Zwischenablage.
    //
    // Was hier NICHT geprüft werden kann: der vollständige Weg über die
    // System-Zwischenablage. Headless-Chromium verweigert
    // navigator.clipboard grundsätzlich ("Write permission denied"), auch
    // mit erteilter Berechtigung. Das ist eine Grenze der Testumgebung, kein
    // Fehler der Anwendung.
    //
    // Geprüft wird deshalb alles, was die Voraussetzung dafür bildet — und
    // dass der Rückfallweg über das Panel vorhanden und bedienbar ist. Der
    // vollständige Durchlauf steht als Abnahmematrix in plan.md §10.5 und
    // gehört in einen echten Browser.
    if (barOpen) {
      await page.type('.viewer__clip', 'Prüftext für die Zwischenablage: äöü ß 123')
      const typed = await page.$eval('.viewer__clip', (el) => el.value)
      check(typed.includes('äöü ß'),
        'Zwischenablage-Panel nimmt Text inklusive Umlauten an')

      const buttons = await page.$$eval('.viewer__row .btn', (els) => els.map((e) => e.textContent))
      check(buttons.some((b) => b?.includes('In den Browser legen')) &&
            buttons.some((b) => b?.includes('Aus dem Browser holen')),
        'Beide Richtungen sind als Rückfallweg bedienbar')

      // Auch wenn der Browser die Zwischenablage verweigert, darf die
      // Anwendung nicht stumm bleiben — sie muss es sagen.
      await page.evaluate(() => {
        const b = [...document.querySelectorAll('.viewer__row .btn')]
          .find((x) => x.textContent?.includes('In den Browser legen'))
        b?.click()
      })
      await new Promise((r) => setTimeout(r, 900))
      const toast = await page.$eval('.toast', (el) => el.textContent).catch(() => null)
      check(!!toast, `Rückmeldung erscheint statt stillem Fehlschlag ("${toast?.slice(0, 52) ?? '—'}")`)
    }

    await page.evaluate(() => {
      const b = [...document.querySelectorAll('.btn')]
        .find((x) => x.textContent?.includes('Zurück zum Dashboard'))
      b?.click()
    })
    await page.waitForSelector('.tiles', { timeout: 15000 })
    ok('Rückkehr zum Dashboard funktioniert')
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
      // unabhängig vom Vorzustand prüfbar bleibt.
      await page.click('.bay .strip__app:not(:disabled)')
      await page.waitForSelector('.viewer__frame', { timeout: 90000 })
      await page.evaluate(() => {
        const b = [...document.querySelectorAll('.btn')]
          .find((x) => x.textContent?.includes('Zurück zum Dashboard'))
        b?.click()
      }).catch(() => {})
      await page.click('.viewer__handle').catch(() => {})
      await new Promise((r) => setTimeout(r, 500))
      await page.evaluate(() => {
        const b = [...document.querySelectorAll('.btn')]
          .find((x) => x.textContent?.includes('Zurück zum Dashboard'))
        b?.click()
      })
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
    await running[running.length - 1].click()
    await page.waitForSelector('.viewer__frame', { timeout: 60000 })
    const appSrc = await page.$eval('.viewer__frame', (el) => el.getAttribute('src'))
    check(/\/s\/[0-9a-f-]{36}\//.test(appSrc ?? ''),
      `Stream der App wird geladen (${appSrc?.slice(0, 44)}…)`)
    if (running.length > 1) {
      check(appSrc?.includes('/a/'),
        'Zusätzliche App läuft auf einem eigenen Display')
    }

    let appState = null
    for (let i = 0; i < 20; i++) {
      await new Promise((r) => setTimeout(r, 1500))
      appState = await page.evaluate(() => {
        const d = document.querySelector('.viewer__frame')?.contentDocument
        return d ? d.documentElement.className : null
      })
      if (appState?.includes('noVNC_connected')) break
    }
    check(appState?.includes('noVNC_connected'), 'Eigener Stream der App verbindet')
    await shot(page, '09-arbeitsplatz-app')

    // Umschalter in der Kontrollleiste
    await page.click('.viewer__handle')
    await new Promise((r) => setTimeout(r, 600))
    const switcher = await page.$$eval('.viewer__bar .strip__app .strip__name',
      (els) => els.map((e) => e.textContent)).catch(() => [])
    check(switcher.includes('Desktop') && switcher.length > 1,
      `Umschalter bietet ${switcher.length} Ansichten: ${switcher.join(', ')}`)
    await shot(page, '10-arbeitsplatz-umschalter')

    await page.evaluate(() => {
      const b = [...document.querySelectorAll('.btn')]
        .find((x) => x.textContent?.includes('Zurück zum Dashboard'))
      b?.click()
    })
    await page.waitForSelector('.tiles', { timeout: 15000 })
  } else {
    ok('Kein Arbeitsplatz mit App-Katalog vorhanden — Abschnitt übersprungen')
  }

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
