import { useEffect, useRef, useState } from 'react'
import { api, type Session, type Stream, type Template } from '../lib/api'
import { startClipboardBridge, type Bridge } from '../lib/clipboardBridge'
import { Led } from '../components/controls'
import { t, useLang } from '../lib/i18n'
import { openInTab, viewPath } from '../lib/routes'
import { extensionPresent, isFirefox } from '../lib/firefoxClipboard'
import { InstallButton } from '../components/InstallButton'

/**
 * Der Stream läuft in einem iframe. Zwei Dinge sind dabei nicht optional:
 *
 * 1. `allow="clipboard-read; clipboard-write"` — ohne diese Angabe blockiert
 *    die Permissions-Policy die Zwischenablage, und zwar lautlos.
 * 2. Der Fokus muss im iframe liegen, sonst erreichen Tastenanschläge den
 *    Stream nie.
 */
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

  // Lebenszeichen, damit der Leerlauf-Aufräumer die Session nicht beendet,
  // während jemand danebensitzt und liest.
  useEffect(() => {
    const beat = () => { api.heartbeat(session.id).catch(() => {}) }
    beat()
    const timer = setInterval(beat, 30_000)
    return () => clearInterval(timer)
  }, [session.id])

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
        key={src}
        src={src}
        title={t('{name} — Sitzung', { name: label })}
        onLoad={() => { setFrameReady((n) => n + 1); focusFrame() }}
        /* Ohne diese Zeile funktioniert die Zwischenablage nicht. */
        allow="clipboard-read; clipboard-write; fullscreen; autoplay; microphone; camera"
      />

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
                      <span className="strip__icon" aria-hidden="true">{app?.icon ?? '▢'}</span>
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
