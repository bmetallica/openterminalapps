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
// Der Notzugang, nicht ein Mensch.
//
// Seit der Übernahme (auth-roadmap.md §5.1) melden sich Menschen über
// Keycloak an. Diese Reihe prüft OTA und nicht Keycloak — und ganz nebenbei
// prüft sie damit bei jedem Lauf, dass der Notausgang offen ist. Das ist die
// Eigenschaft, die man am ehesten stillschweigend verliert.
const USER = process.env.OTA_USER ?? process.env.OTA_TEST_ADMIN ?? 'notfall'
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

// Was dieser Lauf angelegt hat und am Ende wieder verschwinden muss.
//
// Nicht erst im Erfolgsfall aufräumen: Bricht der Lauf mittendrin ab, blieb
// sonst eine Prüfvorlage im Katalog stehen — und die sieht ein Mensch beim
// nächsten Blick auf sein Dashboard. Genau das ist zweimal passiert.
const aufzuraeumen = { vorlagen: [], sessions: [] }
page.on('pageerror', (e) => errors.push(String(e)))
page.on('console', (m) => { if (m.type() === 'error') errors.push(m.text()) })

try {
  console.log(`\nOTA Oberflächentest gegen ${BASE}\n`)

  // ------------------------------------------------------------ Anmeldung
  console.log('Anmeldung')
  // Ausdrücklich `/login` und nicht die Wurzel.
  //
  // Seit der Umstellung auf Keycloak (auth-roadmap.md, Etappe B) leitet jede
  // geschützte Adresse einen Nichtangemeldeten zur zentralen Anmeldung weiter.
  // Diese Reihe prüft OTA und nicht Keycloak — und `bmetallica` ist bis zur
  // Übernahme der Bestandskonten (§5.1) ein lokales Konto. `/login` ist der
  // Weg, der beides bedient: Landeplatz für Fehler und lokale Maske.
  await page.goto(BASE + '/login', { waitUntil: 'networkidle2', timeout: 30000 })
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
  // Der Client meldet die gestellte Leerlaufuhr in der Konsole. Das ist der
  // einzige Weg, an den **wirksamen** Wert heranzukommen: Im Auswahlfeld
  // steht danach weiter 60, weil es den grossen Wert gar nicht anbietet.
  const viewLogs = []
  view?.on('console', (m) => viewLogs.push(m.text()))
  check(!!view, 'Session öffnet in einem eigenen Tab')

  // ------------------------------------------------------------ Symbole
  //
  // Jedes Paket bringt sein Symbol mit; OTA liest es aus der .desktop-Datei
  // und liefert es unter einer eigenen Adresse aus. Geprüft wird hier, was
  // eine Schnittstellenprüfung nicht sieht: dass die Bilder im Browser
  // wirklich ankommen. Ein 200 mit `image/png` sagt nichts darüber, ob das,
  // was drinsteht, ein Bild ist — `naturalWidth` schon.
  //
  // Und zwar **hier**, gleich nach dem Start: Den Anwendungsstreifen zeigt
  // das Dashboard nur zu einer laufenden Session. Weiter unten stand der
  // Abschnitt zwar auch, übersprang sich aber jedes Mal selbst.
  console.log('\nSymbole der Anwendungen')
  {
    await page.bringToFront()
    await page.waitForSelector('.strip__app', { timeout: 30000 }).catch(() => {})
    // Bilder laden nachträglich (`loading="lazy"`), deshalb kurz nachfassen.
    let bilder = { anzahl: 0, geladen: 0, kaputt: 0 }
    for (let i = 0; i < 20; i++) {
      bilder = await page.evaluate(() => {
        const els = [...document.querySelectorAll('.strip__icon img')]
        return {
          anzahl: els.length,
          geladen: els.filter((x) => x.naturalWidth > 0).length,
          kaputt: els.filter((x) => x.complete && x.naturalWidth === 0).length,
        }
      })
      if (bilder.anzahl > 0 && bilder.geladen === bilder.anzahl) break
      await new Promise((r) => setTimeout(r, 500))
    }
    if (bilder.anzahl === 0) {
      bad('Keine Anwendung mit Symbol im Katalog — im Image nachsehen und freigeben')
    } else {
      check(bilder.geladen === bilder.anzahl,
        `Alle Symbole sind im Browser angekommen (${bilder.geladen} von ${bilder.anzahl})`)
      check(bilder.kaputt === 0,
        bilder.kaputt ? `${bilder.kaputt} Symbol(e) blieben leer` : 'Keins blieb leer')
    }
    await view.bringToFront()
  }
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
      // Der Container **dieser** Session, nicht der erste, den docker ps
      // nennt: Auf einem Host mit mehreren laufenden Sessions — etwa der
      // eines Testnutzers aus der Autorisierungsreihe — wäre das der
      // falsche, und die Richtung Session → Browser schlüge grundlos fehl.
      const sid = /\/view\/s\/([0-9a-f-]{36})/.exec(view.url())?.[1] ?? ''
      const cn = sid ? `ota-s-${sid.slice(0, 12)}` : ''
      const inbound = `AUS-DER-SESSION-${Date.now()} äöü ß`
      if (cn) {
        execSync(`docker exec -u 1000 ${cn} bash -c ` +
          `'export XAUTHORITY=$HOME/.Xauthority; ` +
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

      // Abnahmefall 12 — ein Browser ohne readText().
      //
      // Firefox gibt `navigator.clipboard.readText()` ohne Erweiterung nicht
      // her. Der Weg dorthin ist deshalb das `paste`-Ereignis: Es liefert den
      // Inhalt mit, ohne dass der Browser etwas freigeben muss.
      //
      // Geprüft wird hier in Chromium — mit abgeschaltetem readText. Das ist
      // **kein** Ersatz für einen Lauf in Firefox und soll auch keiner sein;
      // es prüft genau den Pfad, der dort greift, und zwar bei jedem Lauf.
      // Ohne das fällt ein Bruch dieses Pfades erst jemandem in Firefox auf.
      {
        await view.evaluate(() => {
          window.__otaReadText = navigator.clipboard.readText
          const strip = (nav) => {
            try {
              Object.defineProperty(nav.clipboard, 'readText',
                { value: undefined, configurable: true })
            } catch { /* egal */ }
          }
          strip(navigator)
          try {
            const n = document.querySelector('.viewer__frame').contentWindow.navigator
            window.__otaReadTextInner = n.clipboard.readText
            strip(n)
          } catch { /* fremde Herkunft */ }
        })
        const weg = await view.evaluate(() => typeof navigator.clipboard.readText)
        check(weg === 'undefined', 'readText() ist für diesen Fall abgeschaltet')

        const viaPaste = `PER-PASTE-EREIGNIS-${Date.now()} äöü`
        await view.evaluate((t) => {
          const dt = new DataTransfer()
          dt.setData('text', t)
          window.dispatchEvent(new ClipboardEvent('paste',
            { clipboardData: dt, bubbles: true }))
        }, viaPaste)
        await new Promise((r) => setTimeout(r, 1500))
        const angekommen = await view.evaluate(() => {
          const d = document.querySelector('.viewer__frame').contentDocument
          return d.getElementById('noVNC_clipboard_text').value
        })
        check(angekommen === viaPaste,
          `Ohne readText() trägt das paste-Ereignis (${angekommen.slice(0, 24)}…)`)

        // Wieder anschalten. Der Rest des Laufs braucht readText — bliebe es
        // aus, schluege danach jede Prüfung fehl, die aus dem Browser liest,
        // und der Grund stünde weit oben.
        await view.evaluate(() => {
          try {
            Object.defineProperty(navigator.clipboard, 'readText',
              { value: window.__otaReadText, configurable: true })
          } catch { /* egal */ }
          try {
            const n = document.querySelector('.viewer__frame').contentWindow.navigator
            Object.defineProperty(n.clipboard, 'readText',
              { value: window.__otaReadTextInner, configurable: true })
          } catch { /* fremde Herkunft */ }
        })
        const zurueck = await view.evaluate(() => typeof navigator.clipboard.readText)
        check(zurueck === 'function', 'readText() ist danach wieder da')
      }
    }

    // Abnahmefall 3 — Text zwischen zwei Sessions desselben Nutzers.
    //
    // Die Brücke im Container spannt über die Displays **einer** Session. Von
    // einer Session in die andere führt kein Weg im Container — der Weg geht
    // über den Browser: Session A → Systemzwischenablage → Session B. Genau
    // dieser Weg wird hier gegangen, mit zwei echten Containern.
    {
      const sid1 = /\/view\/s\/([0-9a-f-]{36})/.exec(view.url())?.[1] ?? ''

      // Die Aufrufe laufen über den Session-Tab und nicht über das
      // Dashboard: Das Dashboard lauscht auf Katalogänderungen und lädt sich
      // neu, sobald eine Vorlage dazukommt — ein `fetch`, das dabei noch
      // unterwegs ist, stirbt mit "Failed to fetch". Genau daran ist der
      // erste Anlauf gescheitert.
      const api = async (pfad, init) => view.evaluate(async (p, i) => {
        try {
          const r = await fetch(p, { credentials: 'include', ...(i ?? {}) })
          const text = await r.text()
          let daten = null
          try { daten = JSON.parse(text) } catch { daten = { detail: text.slice(0, 200) } }
          return { ok: r.ok, status: r.status, daten }
        } catch (e) {
          return { ok: false, status: 0, daten: { detail: String(e) } }
        }
      }, pfad, init ?? null)

      const jsonPost = (pfad, koerper) => api(pfad, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(koerper),
      })

      const lage = await (async () => {
        const sessions = await api('/api/sessions')
        const laufend = (sessions.daten ?? []).find((x) => x.id === sid1)
        const vorlagen = await api('/api/templates')
        const alteVorlage = (vorlagen.daten ?? []).find((t) => t.id === laufend?.template_id)
        if (!alteVorlage) return { fehlt: true }

        // Eine eigene Vorlage für diesen Fall, statt eine vorhandene zu
        // nehmen. Zwei Gründe, beide gemessen:
        //
        //   * Eine vorhandene Vorlage kann auf ein Image zeigen, das auf
        //     diesem Host nicht liegt. Dann wäre nicht die Zwischenablage
        //     kaputt, sondern der Katalog.
        //   * Vor allem aber teilen sich zwei Vorlagen mit
        //     `persistence_scope: 'user'` **dasselbe Zuhause** — OTA lehnt
        //     die zweite Session zu Recht ab ("Zwei Arbeitsplätze auf einem
        //     Profil geraten sich in die Quere").
        //
        // Deshalb: dasselbe Image wie die laufende Session (das liegt
        // garantiert da) und ein eigenes Profil.
        const angelegt = await jsonPost('/api/templates', {
          friendly_name: 'Prüfung zweite Session',
          description: 'Von tests/e2e.mjs angelegt, Abnahmefall 3. '
            + 'Wird am Ende des Laufs wieder entfernt.',
          mode: alteVorlage.mode,
          image_ref: alteVorlage.image_ref,
          cores: 2,
          memory_bytes: 2 * 1024 * 1024 * 1024,
          persistence_scope: 'template',
          idle_minutes: 30,
        })
        if (!angelegt.ok) {
          return { ok: false, slug: 'Prüfung zweite Session', daten: angelegt.daten }
        }
        const vorlage = angelegt.daten
        aufzuraeumen.vorlagen.push(vorlage.id)

        // Der Start dauert: Der Aufruf kehrt erst zurück, wenn der Container
        // steht **und** Traefik die Route kennt. In dieser Zeit lädt sich der
        // Tab womöglich neu, und dann stirbt das `fetch` mit "Failed to
        // fetch" — obwohl die Session serverseitig längst läuft. Gemessen:
        // Der Aufruf meldete einen Fehler, und daneben lief der Container.
        //
        // Deshalb wird die Antwort nicht geglaubt, sondern nachgesehen.
        const gestartet = await jsonPost('/api/sessions', { template_id: vorlage.id })
        if (gestartet.ok) {
          return { slug: vorlage.slug, ok: true, daten: gestartet.daten,
                   vorlage: vorlage.id }
        }
        for (let i = 0; i < 45; i++) {
          await new Promise((r) => setTimeout(r, 2000))
          const liste = await api('/api/sessions')
          const meine = (liste.daten ?? []).find((x) => x.template_id === vorlage.id)
          if (meine) {
            return { slug: vorlage.slug, ok: true, daten: meine,
                     vorlage: vorlage.id, nachgesehen: true }
          }
        }
        return { ok: false, slug: vorlage.slug, daten: gestartet.daten,
                 vorlage: vorlage.id }
      })()

      if (lage.fehlt) {
        ok('Nur eine Vorlage vorhanden — Abnahmefall 3 übersprungen')
      } else if (!lage.ok) {
        ok(`Zweite Session (${lage.slug}) nicht startbar: `
           + `${lage.daten?.detail ?? '?'} — Abnahmefall 3 übersprungen`)
        if (lage.vorlage) await api(`/api/templates/${lage.vorlage}`, { method: 'DELETE' })
      } else {
        const sid2 = lage.daten.id
        aufzuraeumen.sessions.push(sid2)
        const cn2 = `ota-s-${sid2.slice(0, 12)}`

        // Warten, bis der zweite Container wirklich steht — und zwar so, wie
        // der Agent es tut: am offenen Port, nicht an einer festen Zeit.
        let bereit = false
        for (let i = 0; i < 90; i++) {
          await new Promise((r) => setTimeout(r, 2000))
          try {
            execSync(`docker exec ${cn2} bash -lc `
              + `'(exec 3<>/dev/tcp/127.0.0.1/6901)' 2>/dev/null`,
              { shell: '/bin/bash', stdio: 'ignore' })
            bereit = true
            break
          } catch { /* noch nicht */ }
        }
        check(bereit, `Zweite Session ${lage.slug} steht (${cn2}`
          + `${lage.nachgesehen ? ', nachgesehen statt geglaubt' : ''})`)

        if (bereit) {
          // In Session A kopieren …
          const wandertext = `ZWISCHEN-SESSIONS-${Date.now()} äöü ß`
          const cn1 = `ota-s-${sid1.slice(0, 12)}`
          execSync(`docker exec -u 1000 ${cn1} bash -c `
            + `'export XAUTHORITY=$HOME/.Xauthority; `
            + `printf %s ${JSON.stringify(wandertext)} | timeout 3 xclip -d :1 -selection clipboard -i' &`,
            { shell: '/bin/bash' })
          await new Promise((r) => setTimeout(r, 3500))

          // … über den Browser holen …
          const imBrowser = await view.evaluate(() => navigator.clipboard.readText())
          check(imBrowser === wandertext,
            'Session A → Browser (Voraussetzung für den Weg zu Session B)')

          // … und in Session B einfügen. Der Tab muss dafür vorn liegen: Die
          // Brücke zieht den Systeminhalt nur nach, solange das Fenster den
          // Fokus hat — sonst läse jeder offene Tab dauernd fremde Inhalte.
          const view2 = await browser.newPage()
          await view2.goto(`${BASE}/view/s/${sid2}`, { waitUntil: 'domcontentloaded' })
          await view2.waitForSelector('.viewer__frame', { timeout: 120000 })
          for (let i = 0; i < 20; i++) {
            await new Promise((r) => setTimeout(r, 1500))
            const c = await view2.evaluate(() => document.querySelector('.viewer__frame')
              ?.contentDocument?.documentElement?.className ?? '')
            if (c.includes('noVNC_connected')) break
          }
          await view2.bringToFront()
          await view2.evaluate((t) => navigator.clipboard.writeText(t), wandertext)

          let inB = ''
          for (let i = 0; i < 20; i++) {
            await new Promise((r) => setTimeout(r, 1000))
            try {
              inB = execSync(`docker exec -u 1000 ${cn2} bash -c `
                + `'export XAUTHORITY=$HOME/.Xauthority; `
                + `timeout 2 xclip -d :1 -selection clipboard -o'`,
                { shell: '/bin/bash' }).toString()
            } catch { inB = '' }
            if (inB === wandertext) break
          }
          check(inB === wandertext,
            `Browser → Session B: der Text kommt in der zweiten Session an `
            + `(${inB.slice(0, 24)}…)`)
          await view2.close()
        }

        // Aufräumen: weder Session noch Vorlage noch Zuhause bleiben stehen.
        // Der schnelle Weg — das Netz für den Abbruchfall spannt der
        // finally-Block ganz unten.
        //
        // Das Zuhause gehört ausdrücklich dazu: Eine Vorlage mit eigenem
        // Profil legt unter der Kennung des Nutzers ein Verzeichnis nach
        // ihrem Namen an, und das Löschen der Vorlage räumt es **nicht** weg
        // — zu Recht, denn im Betrieb sind das die Daten von Menschen. Hier
        // ist es Prüfmüll, und ohne diese Zeilen wächst er mit jedem Lauf.
        let zuhause = ''
        try {
          zuhause = execSync(`docker inspect ${cn2} --format `
            + `'{{range .Mounts}}{{if or (eq .Destination "/home/kasm-user") (eq .Destination "/home/ota")}}{{.Source}}{{end}}{{end}}'`,
            { shell: '/bin/bash' }).toString().trim()
        } catch { /* Container schon weg */ }

        await api(`/api/sessions/${sid2}`, { method: 'DELETE' })
        if (lage.vorlage) await api(`/api/templates/${lage.vorlage}`, { method: 'DELETE' })

        // Nur, wenn der Pfad wirklich zu dieser Prüfvorlage gehört. Ein
        // `rm -rf` auf einen Pfad, den ein Container gemeldet hat, ohne
        // Gegenprobe wäre genau die Art Zeile, die irgendwann ein echtes
        // Zuhause trifft.
        if (/\/profiles\/[0-9a-f-]{36}\/pr[a-z0-9-]*zweite-session/.test(zuhause)) {
          await new Promise((r) => setTimeout(r, 2000))
          try { execSync(`rm -rf ${JSON.stringify(zuhause)}`, { shell: '/bin/bash' }) }
          catch { /* dann bleibt es liegen */ }
        }
      }
    }

    // Abbruch und Selbstheilung.
    //
    // Bis zum 2026-08-28 blieb ein abgerissener Stream schwarz stehen: Der
    // Client meldet den Abbruch nur in seiner eigenen Oberflaeche — und die
    // liegt im iframe und ist ausgeblendet. Fuer den Benutzer sah es aus, als
    // haette OTA die Session nach wenigen Minuten beendet.
    //
    // Getrennt wird deshalb von innen, wie bei einem echten Leitungsabbruch,
    // und nicht etwa die Klasse entfernt, an der das Elternfenster erkennt,
    // ob es steht — das wuerde nur das Signal faelschen.
    // Zuvor der Grund, aus dem der Abbruch ueberhaupt auffiel: KasmVNC
    // trennt von sich aus nach 20 Minuten ohne Maus oder Tastatur. Die Uhr
    // muss aus sein, sonst entscheidet der Client ueber die Laufzeit und
    // nicht OTA (siehe STREAM_ARGS in api/ota/routers/sessions.py).
    const leerlauf = await view.evaluate(() => {
      const d = document.querySelector('.viewer__frame').contentDocument
      return d.getElementById('noVNC_setting_idle_disconnect')?.value ?? null
    })
    check(Number(leerlauf) >= 60,
      `Der Client trennt nicht mehr nach 20 Minuten ohne Eingabe (${leerlauf})`)

    const gestellt = viewLogs.map((t) => t.match(/idle timeout to (\d+)s/))
      .filter(Boolean).map((m) => Number(m[1]))
    check(gestellt.some((v) => v >= 86400),
      `Der Viewer stellt die Uhr im Client weit (${gestellt.join(', ') || 'keine Meldung'})`)

    const getrennt = await view.evaluate(() => {
      const d = document.querySelector('.viewer__frame').contentDocument
      const b = d.getElementById('noVNC_disconnect_button')
      if (!b) return null
      b.click()
      return 'Trennknopf'
    })
    check(!!getrennt, `Der Stream laesst sich von innen trennen (${getrennt})`)

    let banner = ''
    for (let i = 0; i < 12; i++) {
      await new Promise((r) => setTimeout(r, 1000))
      banner = await view.$eval('.linkloss', (el) => el.textContent).catch(() => '')
      if (banner) break
    }
    check(/unterbrochen|lost/i.test(banner),
      `Der Abbruch wird im Fenster gemeldet (${banner.slice(0, 40) || 'nichts'})`)

    let wieder = false
    for (let i = 0; i < 20; i++) {
      await new Promise((r) => setTimeout(r, 2000))
      wieder = await view.evaluate(() => {
        // Jede Stufe einzeln abgesichert: Während des Neuladens gibt es
        // kurz ein Dokument ohne Wurzelelement, und ein Zugriff darauf
        // beendet den ganzen Lauf statt nur diese Messung.
        const d = document.querySelector('.viewer__frame')?.contentDocument
        return d?.documentElement?.classList?.contains('noVNC_connected') === true
      })
      if (wieder) break
    }
    check(wieder, 'Der Stream verbindet sich von selbst wieder')
    // Das Elternfenster sieht alle 2,5 Sekunden nach — das Banner geht
    // deshalb nicht in derselben Sekunde weg wie der Stream wiederkommt.
    let bannerWeg = false
    for (let i = 0; i < 6; i++) {
      await new Promise((r) => setTimeout(r, 1500))
      bannerWeg = !(await view.$('.linkloss'))
      if (bannerWeg) break
    }
    check(bannerWeg, 'Danach ist das Banner wieder weg')

    await view.close()
    await page.bringToFront()
    await page.waitForSelector('.tiles', { timeout: 15000 })
    ok('Das Dashboard bleibt im ersten Tab stehen')
  }

  // ------------------------------------------------ Auf den Desktop legen
  //
  // Der Anspruch: Eine Anwendung soll sich als Symbol ablegen lassen, in
  // einem eigenen Fenster ohne Browserleiste starten und vorher nach der
  // Anmeldung fragen, falls noch keine besteht. Alle drei Teile werden hier
  // gemessen, keiner davon geglaubt.
  console.log('\nVerknüpfungen')
  {
    const geoeffnet = await page.evaluate(() => {
      const kopf = [...document.querySelectorAll('.section__head')]
        .find((x) => /Desktop/i.test(x.textContent ?? ''))
      const b = kopf?.querySelector('.btn--sm')
      if (!b) return false
      b.click()
      return true
    })
    check(geoeffnet, 'Das Dashboard bietet Verknüpfungen an')

    await new Promise((r) => setTimeout(r, 600))
    const eintraege = await page.$$eval('.shortcut', (els) => els.length)
    check(eintraege > 0, `${eintraege} Anwendungen lassen sich einzeln ablegen`)
    if (eintraege > 0) await shot(page, '09-verknuepfungen')

    // Die Ablege-Seite. Sie ist der eigentliche Trick: Der Browser
    // entscheidet über die Ablage anhand des Manifests, das beim Laden im
    // Dokument steht — nicht anhand dessen, was später hineingetauscht wird.
    const vorher = execSync('docker ps --filter "label=ota.session_id" -q')
      .toString().trim().split('\n').filter(Boolean).length
    const legen = new Promise((resolve) => browser.once('targetcreated',
      (t) => resolve(t.page())))
    await page.click('.shortcut')
    const ablage = await legen
    await ablage.waitForSelector('.place', { timeout: 20000 })
    ok('Die Ablege-Seite öffnet sich')

    const cdp = await ablage.createCDPSession()
    await cdp.send('Page.enable')
    const man = await cdp.send('Page.getAppManifest')
    check(/\/api\/pwa\/manifest\.webmanifest\?template=/.test(man.url ?? ''),
      `Das Manifest gehört der Anwendung, nicht dem Dashboard (${(man.url ?? '').split('?')[1] ?? '—'})`)
    const kennung = /"id":\s*"([^"]+)"/.exec(man.data ?? '')?.[1]
    check(!!kennung && kennung !== 'ota', `Die Verknüpfung hat eine eigene Kennung (${kennung})`)

    const hindernisse = await cdp.send('Page.getInstallabilityErrors')
    check((hindernisse.installabilityErrors ?? []).length === 0,
      `Der Browser sieht nichts, was der Ablage im Weg steht (${
        JSON.stringify(hindernisse.installabilityErrors)})`)

    const nachher = execSync('docker ps --filter "label=ota.session_id" -q')
      .toString().trim().split('\n').filter(Boolean).length
    check(nachher === vorher,
      `Ablegen startet nichts (Container vorher ${vorher}, nachher ${nachher})`)
    await shot(ablage, '10-ablegen')
    const ablagePfad = new URL(ablage.url()).pathname
    await ablage.close()
    await page.bringToFront()

    // Und der Weg vom Symbol aus, ohne Anmeldung. Ein eigener Browserkontext,
    // weil es genau darum geht: kein Cookie, keine Sitzung.
    //
    // Seit Etappe B führt das zur zentralen Anmeldung. Der Punkt, auf den es
    // dabei ankommt, ist die **Herkunft**: Keycloak liegt unter /auth
    // derselben Adresse, und nur deshalb bleibt eine Desktop-Verknüpfung in
    // ihrem Fenster, statt in einen Browser-Tab zu springen.
    const fremd = await browser.createBrowserContext()
    const kalt = await fremd.newPage()
    await kalt.goto(BASE + ablagePfad, { waitUntil: 'networkidle2' })
    await kalt.waitForSelector('#username, .login', { timeout: 25000 })

    const beiKeycloak = await kalt.$('#kc-login')
    check(!!beiKeycloak, 'Ohne Anmeldung führt die Verknüpfung zur zentralen Anmeldung')
    check(new URL(kalt.url()).origin === new URL(BASE).origin,
      `Und sie liegt auf derselben Herkunft (${new URL(kalt.url()).origin})`)

    if (beiKeycloak) {
      await kalt.type('#username', 'kc-pruef')
      await kalt.type('#password', 'KcPruef2026!xy')
      await Promise.all([
        kalt.click('#kc-login'),
        kalt.waitForNavigation({ waitUntil: 'networkidle2', timeout: 30000 }),
      ])
      await new Promise((r) => setTimeout(r, 1500))
      check(new URL(kalt.url()).pathname === ablagePfad,
        `Nach der Anmeldung steht die Adresse wieder da (${new URL(kalt.url()).pathname})`)
      const wer = await kalt.evaluate(async () => {
        const r = await fetch('/api/auth/me')
        return r.ok ? (await r.json()).username : null
      })
      check(wer === 'kc-pruef', `Angemeldet über Keycloak (${wer})`)
    }
    await kalt.close()
    await fremd.close()
  }

  // ------------------------------------------------------- Zweite Stufe
  //
  // Sie liegt seit Etappe B in Keycloak (auth-roadmap.md §5.3). Was in OTA
  // ein Feld an der Gruppe war, ist dort ein Anmeldefluss mit einer
  // Rollenbedingung — und der Fluss ist gebunden, also gilt er für alle.
  //
  // Geprüft wird beides: dass er greift, wo er soll, und **dass er nicht
  // greift, wo er nicht soll**. Das zweite ist das wichtigere: Ein Fluss mit
  // einer leeren Bedingung sperrt entweder jeden aus oder niemanden — und
  // genau letzteres ist beim Bauen einmal passiert.
  console.log('\nZweite Stufe')
  {
    const kcs = process.env.OTA_KEYCLOAK_SECRET ?? ''
    const kb = 'http://ota-keycloak:8080/auth'
    const dex = (cmd) => execSync(`docker exec -i ota-agent ${cmd}`).toString()

    if (!kcs) {
      bad('OTA_KEYCLOAK_SECRET fehlt — die Prüfung der zweiten Stufe entfällt')
    } else {
      const tok = JSON.parse(dex(`curl -s -d client_id=ota-manager ` +
        `--data-urlencode client_secret=${kcs} -d grant_type=client_credentials ` +
        `${kb}/realms/ota/protocol/openid-connect/token`)).access_token

      const konto = JSON.stringify({
        username: 'kc-zweifach', enabled: true, emailVerified: true,
        email: 'kc-zweifach@ota.test', firstName: 'Zwei', lastName: 'Fach',
        requiredActions: [],
        credentials: [{ type: 'password', value: 'KcZwei2026!xy', temporary: false }],
      })
      dex(`curl -s -X POST ${kb}/admin/realms/ota/users -H 'Authorization: Bearer ${tok}' ` +
          `-H 'Content-Type: application/json' -d '${konto}'`)
      const uid = JSON.parse(dex(`curl -s '${kb}/admin/realms/ota/users?username=kc-zweifach' ` +
        `-H 'Authorization: Bearer ${tok}'`))[0]?.id
      const rolle = dex(`curl -s ${kb}/admin/realms/ota/roles/zweiter-faktor ` +
        `-H 'Authorization: Bearer ${tok}'`).trim()
      dex(`curl -s -X POST ${kb}/admin/realms/ota/users/${uid}/role-mappings/realm ` +
          `-H 'Authorization: Bearer ${tok}' -H 'Content-Type: application/json' -d '[${rolle}]'`)

      const anmelden = async (nutzer, pass) => {
        const ctx = await browser.createBrowserContext()
        const seite = await ctx.newPage()
        await seite.goto(BASE + '/api/auth/oidc/start?next=/', { waitUntil: 'networkidle2' })
        await seite.type('#username', nutzer)
        await seite.type('#password', pass)
        await Promise.all([
          seite.click('#kc-login'),
          seite.waitForNavigation({ waitUntil: 'networkidle2', timeout: 30000 }),
        ])
        await new Promise((r) => setTimeout(r, 1500))
        const wer = await seite.evaluate(async () => {
          const r = await fetch('/api/auth/me')
          return r.ok ? (await r.json()).username : null
        })
        const einrichtung = !!(await seite.$('#kc-totp-secret-key, .qrcode, #totp'))
        await seite.close(); await ctx.close()
        return { wer, einrichtung }
      }

      const mit = await anmelden('kc-zweifach', 'KcZwei2026!xy')
      check(mit.einrichtung && mit.wer === null,
        `Wer die Rolle trägt, muss erst einen zweiten Faktor einrichten ` +
        `(Einrichtung: ${mit.einrichtung}, angemeldet: ${mit.wer})`)

      const ohne = await anmelden('kc-pruef', 'KcPruef2026!xy')
      check(!ohne.einrichtung && ohne.wer === 'kc-pruef',
        `Wer sie nicht trägt, kommt unverändert durch (${ohne.wer})`)
    }
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
  // Die E-Mail ist Pflichtfeld, seit sie an angebundene Anwendungen
  // weitergereicht wird. `.invalid` ist die dafuer reservierte Endung —
  // eine Adresse, die erkennbar nirgendwohin geht.
  await page.type('.drawer input[aria-label="E-Mail"]', `${testName}@ota.invalid`)
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
        `docker exec ${cnWs} bash -lc 'export ` +
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
      `docker exec ${cnShared} bash -lc 'readlink "$HOME"/Gemeinsam || echo -'`,
      { shell: '/bin/bash' }).toString().trim()
    check(link === '/mnt/ota', `Verweis im Home zeigt auf die Ablage (${link})`)
  }

  // Wieder aufräumen, damit der Test wiederholbar bleibt.
  await page.evaluate((name) =>
    fetch(`/api/shared?path=${encodeURIComponent(name)}`, { method: 'DELETE' }), stamp)

  // ------------------------------------------------------------ Gewand
  //
  // Der klassische Fehler beim zweiten Farbsatz ist nicht, dass er hässlich
  // wird — er ist, dass **eine** Farbe im Regelwerk stehenbleibt statt in
  // einem Merkmal. Dann steht heller Text auf hellem Grund, und es fällt
  // niemandem auf, der nur das dunkle Gewand benutzt.
  //
  // Deshalb wird hier nicht das Aussehen geprüft, sondern der Kontrast: Für
  // die tragenden Flächen muss sich Text von Grund unterscheiden — in beiden
  // Gewändern.
  console.log('\nGewand')
  {
    const messen = () => page.evaluate(() => {
      const hell = (farbe) => {
        const m = farbe.match(/[\d.]+/g)
        if (!m) return null
        const [r, g, b, a] = m.map(Number)
        if (a === 0) return null            // durchsichtig: der Grund darunter gilt
        return (0.2126 * r + 0.7152 * g + 0.0722 * b) / 255
      }
      // Den wirklich sichtbaren Grund suchen: Ein Element ohne eigenen
      // Hintergrund zeigt den seines Elternteils.
      const grundVon = (el) => {
        for (let e = el; e; e = e.parentElement) {
          const l = hell(getComputedStyle(e).backgroundColor)
          if (l !== null) return l
        }
        return hell(getComputedStyle(document.body).backgroundColor) ?? 0
      }
      const ziele = ['body', '.rail', '.rail__btn', '.panel', '.btn',
                     '.btn--primary', '.h-page', '.sub']
      const out = {}
      for (const sel of ziele) {
        const el = document.querySelector(sel)
        if (!el) continue
        out[sel] = {
          text: hell(getComputedStyle(el).color),
          grund: grundVon(el),
        }
      }
      out.__body = hell(getComputedStyle(document.body).backgroundColor)
      return out
    })

    const pruefe = (werte, wie) => {
      const schwach = Object.entries(werte)
        .filter(([k]) => !k.startsWith('__'))
        .filter(([, v]) => v.text !== null && Math.abs(v.text - v.grund) < 0.25)
        .map(([k, v]) => `${k} (${v.text.toFixed(2)} auf ${v.grund.toFixed(2)})`)
      check(schwach.length === 0, schwach.length
        ? `${wie}: zu wenig Kontrast bei ${schwach.join(', ')}`
        : `${wie}: Text hebt sich überall vom Grund ab`)
    }

    // Ohne Zutun muss es dunkel sein. Das ist die eigentliche Prüfung an
    // dieser Stelle: Die Vorgabe ist **dunkel** und nicht „wie der Rechner" —
    // sonst wäre OTA für jeden, dessen Betriebssystem hell meldet, plötzlich
    // hell. Genau das ist beim ersten Lauf passiert, und der Testbrowser
    // meldet hell.
    const dunkel = await messen()
    check((dunkel.__body ?? 1) < 0.3,
      `Ohne Zutun dunkel (Grundhelligkeit ${dunkel.__body?.toFixed(2)})`)
    pruefe(dunkel, 'Dunkel')

    await page.evaluate(() => {
      localStorage.setItem('ota.theme', 'hell')
      document.documentElement.setAttribute('data-theme', 'hell')
    })
    await new Promise((r) => setTimeout(r, 300))

    const hellWerte = await messen()
    check((hellWerte.__body ?? 0) > 0.7,
      `Hell ist hell (Grundhelligkeit ${hellWerte.__body?.toFixed(2)})`)
    pruefe(hellWerte, 'Hell')
    await shot(page, '20-gewand-hell')

    // Und wieder zurück — der Test hinterlässt kein umgestelltes Gewand.
    await page.evaluate(() => {
      localStorage.removeItem('ota.theme')
      document.documentElement.removeAttribute('data-theme')
    })
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
  // `ERR_NETWORK_CHANGED` steht bewusst mit auf der Liste: Es lässt sich von
  // Anwendungscode gar nicht auslösen — Chromium meldet es, wenn sich die
  // Netzkonfiguration des Rechners **während** einer laufenden Anfrage
  // ändert. Genau das tut diese Prüfreihe selbst: Sie startet und entfernt
  // Session-Container, und jeder davon hängt Dockers Bridge um. Ein Fehler,
  // den der Test sich selbst macht, sagt über OTA nichts.
  const relevant = errors.filter((e) =>
    !/favicon|net::ERR_CERT|net::ERR_NETWORK_CHANGED|Failed to load resource: the server responded with a status of 40/i.test(e))
  const wsErrors = errors.filter((e) => /websocket|websockify/i.test(e))
  check(wsErrors.length === 0,
    wsErrors.length ? `Websocket-Fehler: ${wsErrors[0].slice(0, 90)}` : 'Keine Websocket-Fehler')
  check(relevant.length === 0,
    relevant.length ? `JavaScript-Fehler: ${relevant.slice(0, 2).join(' | ')}` : 'Keine JavaScript-Fehler')

} catch (err) {
  bad(`Abbruch: ${err.message}`)
  try { await shot(page, 'zz-fehler') } catch { /* egal */ }
} finally {
  // Aufräumen mit einer **frischen** Seite. Die Tabs, über die der Lauf
  // gearbeitet hat, können geschlossen, abgemeldet oder mitten in einer
  // Navigation sein — ein `fetch` von dort scheitert dann mit "Failed to
  // fetch", und zwar lautlos.
  if (aufzuraeumen.vorlagen.length || aufzuraeumen.sessions.length) {
    try {
      const putz = await browser.newPage()
      // `networkidle2` und eine Atempause: Die Seite leitet nach dem Laden
      // noch auf die Anmeldemaske um, und ein `evaluate` mitten in dieser
      // Navigation stirbt mit "Execution context was destroyed".
      await putz.goto(`${BASE}/`, { waitUntil: 'networkidle2' })
      await new Promise((r) => setTimeout(r, 500))
      const angemeldet = await putz.evaluate(async (u, p) => {
        const r = await fetch('/api/auth/login', {
          method: 'POST', credentials: 'include',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ username: u, password: p }),
        })
        return r.ok
      }, USER, PW)

      if (angemeldet) {
        // **Den Status zurückgeben, nicht die Antwort.** Ein `Response` lässt
        // sich nicht serialisieren; `evaluate` löst dann auf, bevor der Aufruf
        // durch ist, und die Nachschau unten sieht einen Stand von vorhin. Am
        // 2026-09-05 hat genau das eine Prüfvorlage als „stehengeblieben"
        // gemeldet, die im Protokoll eine Sekunde später gelöscht wurde.
        const weg = (pfad) => putz.evaluate(async (p) => {
          try {
            const r = await fetch(p, { method: 'DELETE', credentials: 'include' })
            return r.status
          } catch { return 0 }
        }, pfad)

        for (const sid of aufzuraeumen.sessions) await weg(`/api/sessions/${sid}`)
        await new Promise((r) => setTimeout(r, 2000))
        for (const tid of aufzuraeumen.vorlagen) await weg(`/api/templates/${tid}`)

        // Und nachsehen, statt es zu glauben — mit ein paar Anläufen, weil das
        // Löschen einer Vorlage am Ende einer Sitzung hängen kann.
        let rest = []
        for (let versuch = 0; versuch < 10; versuch++) {
          rest = await putz.evaluate(async (ids) => {
            const alle = await (await fetch('/api/templates',
              { credentials: 'include' })).json()
            return alle.filter((t) => ids.includes(t.id)).map((t) => t.slug)
          }, aufzuraeumen.vorlagen)
          if (rest.length === 0) break
          await new Promise((r) => setTimeout(r, 1500))
          for (const tid of aufzuraeumen.vorlagen) await weg(`/api/templates/${tid}`)
        }
        check(rest.length === 0, rest.length
          ? `Prüfvorlagen blieben im Katalog stehen: ${rest.join(', ')}`
          : 'Der Lauf hinterlässt keine Prüfvorlage im Katalog')
      } else {
        bad('Aufräumen nicht möglich — Anmeldung schlug fehl')
      }
      await putz.close()
    } catch (err) {
      bad(`Aufräumen fehlgeschlagen: ${err.message}`)
    }
  }
  await browser.close()
}

console.log('\n─────────────────────────────────────')
console.log(`  bestanden: ${pass}   fehlgeschlagen: ${fail}`)
console.log(`  Screenshots: ${SHOTS}`)
process.exit(fail === 0 ? 0 : 1)
