import { useEffect, useRef, useState } from 'react'
import { AppIcon } from '../components/AppIcon'
import { api, type Session, type Stream, type Template } from '../lib/api'
import { startClipboardBridge, type Bridge } from '../lib/clipboardBridge'
import { Led } from '../components/controls'
import { t, useLang } from '../lib/i18n'
import { openInTab, viewPath } from '../lib/routes'
import { extensionPresent, isFirefox } from '../lib/firefoxClipboard'
import { InstallButton } from '../components/InstallButton'
import { ShelfPanel } from '../components/ShelfPanel'

/**
 * Der Stream läuft in einem iframe. Zwei Dinge sind dabei nicht optional:
 *
 * 1. `allow="clipboard-read; clipboard-write"` — ohne diese Angabe blockiert
 *    die Permissions-Policy die Zwischenablage, und zwar lautlos.
 * 2. Der Fokus muss im iframe liegen, sonst erreichen Tastenanschläge den
 *    Stream nie.
 */
/** Was OTA über die Verbindung zum Stream weiss. */
type Link =
  | { phase: 'wartet'; versuche: number }     // Rahmen lädt, noch kein Urteil
  | { phase: 'steht'; versuche: number }      // verbunden
  | { phase: 'weg'; versuche: number }        // abgerissen, gleich neuer Versuch
  | { phase: 'verbindet'; versuche: number }  // Rahmen lädt neu
  | { phase: 'beendet'; versuche: number }    // die Session gibt es nicht mehr

/** Zustände, in denen sich eine Session noch verbinden lässt. */
const LEBT = new Set(['running', 'starting', 'paused'])

/** Wie oft OTA von selbst nachfasst, bevor es beim Knopf bleibt. */
const MAX_VERSUCHE = 8

export function SessionViewer({
  session, stream, template, standalone = false, onSwitch, onClose, onToast,
}: {
  session: Session
  /** Welche App gezeigt wird. Ohne Angabe der Hauptdesktop. */
  stream?: Stream
  template?: Template
  /** Läuft diese Ansicht in einem eigenen Tab? Dann gibt es kein Dashboard
      darunter, und der Umschalter wechselt die Adresse statt der Ansicht. */
  standalone?: boolean
  onSwitch: (s?: Stream) => void
  onClose: () => void
  onToast: (m: string) => void
}) {
  useLang()
  const src = stream?.url ?? session.url
  const label = stream
    ? template?.apps.find((a) => a.slug === stream.app_slug)?.name ?? stream.app_slug
    : session.template_name
  const [barOpen, setBarOpen] = useState(false)
  // In Firefox fehlt der Lesezugriff auf die Zwischenablage. Fehlt auch die
  // Erweiterung, wird hier gesagt, was zu tun ist — statt dass es einfach
  // nicht funktioniert.
  const [needsAddon, setNeedsAddon] = useState(false)
  const [clip, setClip] = useState('')
  const [frameReady, setFrameReady] = useState(0)
  const [clipReady, setClipReady] = useState(false)
  const frame = useRef<HTMLIFrameElement>(null)
  const bridge = useRef<Bridge | null>(null)

  // Zustand der Verbindung, von aussen beobachtet. Siehe `useEffect` unten.
  const [link, setLink] = useState<Link>({ phase: 'wartet', versuche: 0 })
  const [nonce, setNonce] = useState(0)

  // Lebenszeichen, damit der Leerlauf-Aufräumer die Session nicht beendet,
  // während jemand danebensitzt und liest.
  useEffect(() => {
    const beat = () => { api.heartbeat(session.id).catch(() => {}) }
    beat()
    const timer = setInterval(beat, 30_000)
    return () => clearInterval(timer)
  }, [session.id])

  /* --------------------------------------------- Die Uhr im Client stellen
   *
   * KasmVNC bringt eine eigene Leerlaufabschaltung mit und stellt sie ohne
   * Zutun auf 20 Minuten. Gezaehlt werden nur Maus und Tastatur: Wer einem
   * Build zusieht oder ein langes Dokument liest, ohne etwas anzufassen,
   * fliegt heraus — weit vor der Grenze, die in der Vorlage steht. Genau
   * dieser Abbruch ist gemeldet worden.
   *
   * Ueber die Adresse laesst sich das nur bis 60 Minuten heben (dort ist es
   * ein Auswahlfeld mit vier Werten). Diese Nachricht geht daran vorbei: Sie
   * schreibt den Wert direkt in den laufenden Client. Ein Jahr heisst hier
   * „nie" — abschalten laesst sich die Uhr nicht, nur weit stellen.
   *
   * Ueber die Laufzeit einer Session entscheidet damit allein OTA: solange
   * dieses Fenster offen ist, schlaegt oben das Herz.
   */
  useEffect(() => {
    if (!frameReady) return
    const stellen = () => {
      try {
        frame.current?.contentWindow?.postMessage(
          { action: 'set_idle_timeout', value: 365 * 24 * 3600 }, '*')
      } catch { /* andere Herkunft — dann bleiben die 60 Minuten aus der Adresse */ }
    }
    // Zweimal: einmal sofort und einmal, wenn der Client seine Einstellungen
    // fertig eingelesen hat. Die erste Nachricht kann sonst ins Leere gehen.
    stellen()
    const t = setTimeout(stellen, 3000)
    return () => clearTimeout(t)
  }, [frameReady, nonce])

  // Strg+Alt+Shift schaltet die Leiste um — solange der Fokus NICHT im Stream
  // liegt.
  //
  // Warum die Einschränkung: Der ferne Desktop beansprucht die Tastatur für
  // sich, und das zu Recht — sonst könnte man dort keine Tastenkombination
  // benutzen. Gemessen wurde: Control und Alt erreichen das iframe-Fenster
  // noch, Shift und Buchstabentasten nicht mehr. Ein Kürzel, das im laufenden
  // Stream verlässlich greift, gibt es deshalb nicht.
  //
  // Der Griff am rechten Rand liegt im Elternfenster und funktioniert immer.
  // Er ist der eigentliche Weg; das Kürzel ist die Abkürzung für alles davor.
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.ctrlKey && e.altKey && e.shiftKey) {
        e.preventDefault()
        e.stopImmediatePropagation()
        setBarOpen((v) => !v)
      }
      if (e.key === 'Escape') setBarOpen(false)
    }

    // capture: true ist entscheidend. KasmVNC leitet jede Taste an den
    // entfernten Desktop weiter und stoppt sie dabei — in der Bubble-Phase
    // käme unser Zuhörer nie an die Reihe.
    window.addEventListener('keydown', onKey, true)

    // Am FENSTER des iframes, nicht am Dokument. KasmVNC hängt seine
    // Tastaturbehandlung ans Dokument; in der Capture-Phase läuft das Fenster
    // davor. Am Dokument käme unser Zuhörer zu spät und würde durch
    // stopImmediatePropagation nie erreicht.
    let innerWin: Window | null = null
    try {
      innerWin = frame.current?.contentWindow ?? null
      innerWin?.addEventListener('keydown', onKey, true)
    } catch {
      // Andere Herkunft — dann bleibt der Griff am Rand der Weg.
    }

    return () => {
      window.removeEventListener('keydown', onKey, true)
      try { innerWin?.removeEventListener('keydown', onKey, true) } catch { /* egal */ }
    }
  }, [frameReady])

  /* ------------------------------------------------ Verbindung überwachen
   *
   * Der Stream kann aus Gründen abreissen, die OTA nicht kennt und nicht
   * beeinflusst: ein Zwischenstück im Netz, das eine schweigende Verbindung
   * abräumt, ein Rechner, der schlafen geht, ein Wechsel des WLAN. Ohne
   * Gegenmassnahme bleibt dann KasmVNCs eigener Abbruchbildschirm stehen —
   * und der bietet nichts an ausser dem Wort „Disconnected".
   *
   * Erkannt wird das am **positiven** Merkmal: Solange die Verbindung steht,
   * trägt das Wurzelelement im iframe die Klasse `noVNC_connected`. Ihr
   * Verschwinden ist das Signal. Auf die genaue Gestalt des Abbruch-Dialogs
   * verlässt sich hier nichts — die kann sich mit jeder KasmVNC-Fassung
   * ändern, die Klasse ist der stabile Teil.
   *
   * Zwei Messungen hintereinander, bevor etwas passiert: Beim Laden ist die
   * Klasse kurz weg, und ein Neuladen mitten im Verbindungsaufbau wäre eine
   * Schleife.
   */
  useEffect(() => {
    if (!frameReady) return
    let fehlt = 0

    const timer = setInterval(() => {
      const wurzel = frame.current?.contentDocument?.documentElement
      // Kein Dokument: Der Rahmen lädt gerade. Das ist kein Abbruch.
      if (!wurzel) return

      if (wurzel.classList.contains('noVNC_connected')) {
        fehlt = 0
        setLink((l) => (l.phase === 'steht' ? l : { phase: 'steht', versuche: 0 }))
        return
      }

      fehlt += 1

      setLink((l) => {
        if (l.phase === 'beendet' || l.phase === 'weg') return l
        // Waehrend eines Neuversuchs mehr Geduld: Ein Verbindungsaufbau
        // dauert ein paar Sekunden, und ihn abzubrechen, um ihn neu zu
        // beginnen, waere eine Schleife, die nie ankommt.
        const geduld = l.phase === 'verbindet' ? 6 : 2
        if (fehlt < geduld) return l
        fehlt = 0
        return { phase: 'weg', versuche: l.versuche }
      })
    }, 2500)

    return () => clearInterval(timer)
  }, [frameReady, nonce])

  /* Wieder verbinden — aber nur, wenn es noch etwas zu verbinden gibt.
   *
   * Erst die Session fragen, dann den Rahmen neu laden. Andersherum liefe
   * OTA gegen eine beendete Session an und zeigte alle drei Sekunden
   * dieselbe Fehlerseite; der Mensch davor erführe nicht, was los ist. */
  useEffect(() => {
    if (link.phase !== 'weg') return

    let abgebrochen = false
    const versuch = link.versuche + 1

    // Nach genug vergeblichen Versuchen aufhoeren, von selbst zu ziehen.
    // Ein Tab, der stundenlang im Hintergrund alle zehn Sekunden neu laedt,
    // ist niemandem eine Hilfe — der Knopf bleibt.
    if (versuch > MAX_VERSUCHE) {
      setLink({ phase: 'verbindet', versuche: link.versuche })
      return
    }

    const wartezeit = Math.min(2000 * versuch, 10000)
    const t = setTimeout(() => {
      void (async () => {
        try {
          const alle = await api.sessions()
          const noch = alle.find((s) => s.id === session.id)
          if (abgebrochen) return
          if (!noch || !LEBT.has(noch.status)) {
            setLink({ phase: 'beendet', versuche: versuch })
            return
          }
        } catch {
          // Auch die API ist nicht erreichbar. Dann ist der Abbruch weiter
          // draussen, und ein neuer Versuch ist trotzdem richtig.
        }
        if (abgebrochen) return
        setLink({ phase: 'verbindet', versuche: versuch })
        setNonce((n) => n + 1)
      })()
    }, wartezeit)

    return () => { abgebrochen = true; clearTimeout(t) }
  }, [link.phase, link.versuche, session.id])

  // Zwischenablage-Brücke. KasmVNCs eigene nahtlose Übertragung springt nur
  // an, wenn der Browser `clipboard-read` freigegeben hat, und bleibt sonst
  // stumm — für den Nutzer sieht das aus, als sei die Zwischenablage kaputt.
  // Die Brücke steuert den Client von aussen an; der Stream kommt von
  // derselben Herkunft, also ist das möglich.
  useEffect(() => {
    if (!frameReady || !frame.current) return
    bridge.current?.stop()
    bridge.current = startClipboardBridge(frame.current, { onNote: onToast })
    setClipReady(true)
    return () => {
      bridge.current?.stop()
      bridge.current = null
      setClipReady(false)
    }
  }, [frameReady, src, onToast])

  // KasmVNC baut sein Dokument nach dem Laden noch um. Ein zweiter Versuch
  // kurz danach stellt sicher, dass der Zuhörer am Ende wirklich hängt.
  useEffect(() => {
    if (!frameReady) return
    const t = setTimeout(() => setFrameReady((n) => n + 1), 2500)
    return () => clearTimeout(t)
  }, [frameReady === 1])

  useEffect(() => {
    if (!isFirefox()) return
    void extensionPresent().then((yes) => setNeedsAddon(!yes))
  }, [])

  function focusFrame() {
    frame.current?.contentWindow?.focus()
  }

  /** Holt, was gerade in der Session kopiert wurde. */
  function pullFromSession() {
    const panel = frame.current?.contentDocument?.getElementById('noVNC_clipboard_text')
    const value = (panel as HTMLTextAreaElement | null)?.value
    if (value) {
      setClip(value)
      onToast(t('Aus der Session übernommen'))
    } else {
      onToast(t('In der Session wurde noch nichts kopiert'))
    }
  }

  /** Schiebt den Feldinhalt in die Session. */
  function sendToSession() {
    if (!clip) { onToast(t('Das Feld ist leer')); return }
    if (bridge.current?.pushToSession(clip)) {
      onToast(t('In die Session übertragen'))
    } else {
      onToast(t('Übertragung nicht möglich — läuft der Stream?'))
    }
  }

  return (
    <div className="viewer">
      <iframe
        ref={frame}
        className="viewer__frame"
        /* `nonce` erzwingt einen frischen Rahmen beim Wiederverbinden. Ohne
           Wechsel des Schlüssels behielte React das alte Element samt seiner
           toten Verbindung. */
        key={`${src}#${nonce}`}
        src={src}
        title={t('{name} — Sitzung', { name: label })}
        onLoad={() => { setFrameReady((n) => n + 1); focusFrame() }}
        /* Ohne diese Zeile funktioniert die Zwischenablage nicht. */
        allow="clipboard-read; clipboard-write; fullscreen; autoplay; microphone; camera"
      />

      {(link.phase === 'weg' || link.phase === 'verbindet' || link.phase === 'beendet') && (
        <div className="linkloss" role="status" aria-live="polite">
          {link.phase === 'beendet' ? (
            <>
              <b>{t('Diese Sitzung läuft nicht mehr.')}</b>
              <span>{t('Deine Dateien sind davon nicht betroffen — sie liegen im Profil, nicht in der Sitzung.')}</span>
              <button className="btn btn--sm btn--primary"
                onClick={() => { window.location.href = '/' }}>
                {t('Zum Dashboard')}
              </button>
            </>
          ) : (
            <>
              <b>{t('Verbindung unterbrochen.')}</b>
              <span>
                {link.versuche <= 1
                  ? t('Wird neu verbunden…')
                  : t('Wird neu verbunden — Versuch {n}.', { n: String(link.versuche) })}
              </span>
              <button className="btn btn--sm" disabled={link.phase === 'verbindet'}
                onClick={() => { setLink({ phase: 'verbindet', versuche: 0 }); setNonce((n) => n + 1) }}>
                {t('Sofort versuchen')}
              </button>
            </>
          )}
        </div>
      )}

      <button
        className={`viewer__handle${barOpen ? ' is-open' : ''}`}
        onClick={() => setBarOpen(!barOpen)}
        aria-expanded={barOpen}
        aria-label={barOpen ? t('Kontrollleiste schliessen') : t('Kontrollleiste öffnen')}
      >
        {barOpen ? '▸' : '◂'}
      </button>

      {barOpen && (
        <aside className="viewer__bar">
          <header className="viewer__head">
            <div>
              <div className="h-card" style={{ fontSize: 15 }}>{label}</div>
              <Led status={session.status} />
            </div>
            <button className="btn btn--icon btn--ghost" onClick={() => setBarOpen(false)}
              aria-label={t('Leiste schliessen')}>✕</button>
          </header>

          {session.template_mode === 'workspace' && (
            <div className="viewer__group">
              <span className="silk">{t('Anwendung')}</span>
              <div className="strip" style={{ marginTop: 9 }}>
                <button className={`strip__app${!stream ? ' is-on' : ''}`}
                  onClick={() => onSwitch(undefined)}>
                  <span className="strip__icon" aria-hidden="true">▦</span>
                  <span className="strip__name">{t('Desktop')}</span>
                </button>
                {session.streams.map((st) => {
                  const app = template?.apps.find((a) => a.slug === st.app_slug)
                  const active = stream?.app_slug === st.app_slug
                  return (
                    <button key={st.app_slug}
                      className={`strip__app${active ? ' is-on' : ''}`}
                      onClick={() => onSwitch(st)}>
                      <AppIcon className="strip__icon" url={app?.icon_url}
                        glyph={app?.icon} size={18} />
                      <span className="strip__name">{app?.name ?? st.app_slug}</span>
                      <span className="strip__led" aria-hidden="true" />
                    </button>
                  )
                })}
              </div>
              <p className="field__hint">
                {t('Alle Anwendungen teilen sich dasselbe Zuhause und dieselbe Zwischenablage.')}
              </p>
            </div>
          )}

          {template?.user_shelf !== false && <ShelfPanel onToast={onToast} />}

          <div className="viewer__group">
            <span className="silk">{t('Zwischenablage')}</span>
            <p className="field__hint" style={{ marginTop: 6 }}>
              {clipReady
                ? t('Strg+C und Strg+V werden zwischen Browser und Session abgeglichen. Dieses Feld ist der Weg, wenn der Browser die Zwischenablage nicht freigibt.')
                : t('Der Abgleich startet, sobald der Stream steht.')}
            </p>
            <textarea
              className="viewer__clip"
              value={clip}
              placeholder={t('Text zum Übertragen…')}
              aria-label={t('Zwischenablage-Inhalt')}
              onChange={(e) => setClip(e.target.value)}
            />
            {needsAddon && (
              <div className="note-warn" style={{ marginTop: 10 }}>
                <p style={{ margin: '0 0 8px' }}>
                  {t('Firefox lässt Webseiten nicht in die Zwischenablage sehen. Mit der OTA-Erweiterung geht Kopieren und Einfügen wie gewohnt; ohne sie bleibt Strg+V im Stream.')}
                </p>
                <a className="btn btn--sm" href="/api/help/extension/firefox" download>
                  {t('Erweiterung herunterladen')}
                </a>
              </div>
            )}
            <div className="viewer__row">
              <button className="btn btn--sm" onClick={sendToSession}>{t('In die Session')}</button>
              <button className="btn btn--sm" onClick={pullFromSession}>{t('Aus der Session')}</button>
            </div>
          </div>

          <div className="viewer__group">
            <span className="silk">{t('Ansicht')}</span>
            <div className="viewer__row" style={{ marginTop: 8 }}>
              <button className="btn btn--sm" onClick={() => frame.current?.requestFullscreen()}>
                {t('Vollbild')}
              </button>
              <button className="btn btn--sm" onClick={() => { focusFrame(); onToast(t('Fokus zurück in der Sitzung')) }}>
                {t('Fokus setzen')}
              </button>
            </div>
          </div>

          <div className="viewer__group">
            <span className="silk">{t('Sitzung')}</span>
            <div className="viewer__row" style={{ marginTop: 8 }}>
              <button className="btn btn--sm" onClick={() => {
                if (frame.current) frame.current.src = src
                onToast(t('Neu verbunden'))
              }}>{t('Neu verbinden')}</button>
              <button className="btn btn--sm btn--halt" onClick={onClose}>
                {standalone ? t('Tab schliessen') : t('Zurück zum Dashboard')}
              </button>
            </div>
            {!standalone && (
              <div className="viewer__row" style={{ marginTop: 8 }}>
                <button className="btn btn--sm" onClick={() =>
                  openInTab(viewPath(session.id, stream?.display_num))}>
                  {t('In eigenem Tab öffnen')}
                </button>
              </div>
            )}
            <InstallButton session={session} stream={stream} template={template} onToast={onToast} />
          </div>
        </aside>
      )}
    </div>
  )
}
