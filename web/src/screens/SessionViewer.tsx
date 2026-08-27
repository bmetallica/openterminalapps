import { useEffect, useRef, useState } from 'react'
import { api, type Session, type Stream, type Template } from '../lib/api'
import { Led } from '../components/controls'

/**
 * Der Stream läuft in einem iframe. Zwei Dinge sind dabei nicht optional:
 *
 * 1. `allow="clipboard-read; clipboard-write"` — ohne diese Angabe blockiert
 *    die Permissions-Policy die Zwischenablage, und zwar lautlos.
 * 2. Der Fokus muss im iframe liegen, sonst erreichen Tastenanschläge den
 *    Stream nie.
 */
export function SessionViewer({ session, stream, template, onSwitch, onClose, onToast }: {
  session: Session
  /** Welche App gezeigt wird. Ohne Angabe der Hauptdesktop. */
  stream?: Stream
  template?: Template
  onSwitch: (s?: Stream) => void
  onClose: () => void
  onToast: (m: string) => void
}) {
  const src = stream?.url ?? session.url
  const label = stream
    ? template?.apps.find((a) => a.slug === stream.app_slug)?.name ?? stream.app_slug
    : session.template_name
  const [barOpen, setBarOpen] = useState(false)
  const [clip, setClip] = useState('')
  const [frameReady, setFrameReady] = useState(0)
  const frame = useRef<HTMLIFrameElement>(null)

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

  // KasmVNC baut sein Dokument nach dem Laden noch um. Ein zweiter Versuch
  // kurz danach stellt sicher, dass der Zuhörer am Ende wirklich hängt.
  useEffect(() => {
    if (!frameReady) return
    const t = setTimeout(() => setFrameReady((n) => n + 1), 2500)
    return () => clearTimeout(t)
  }, [frameReady === 1])

  function focusFrame() {
    frame.current?.contentWindow?.focus()
  }

  async function readClipboard() {
    try {
      setClip(await navigator.clipboard.readText())
      onToast('Zwischenablage gelesen')
    } catch {
      // Firefox stellt readText() nicht bereit, Chrome kann die Freigabe
      // verweigern. Deshalb bleibt das Feld der verlässliche Weg.
      onToast('Der Browser gibt die Zwischenablage nicht frei — Feld unten nutzen')
    }
  }

  async function writeClipboard() {
    try {
      await navigator.clipboard.writeText(clip)
      onToast('In die Zwischenablage kopiert')
    } catch {
      onToast('Kopieren nicht möglich — Text markieren und Strg+C drücken')
    }
  }

  return (
    <div className="viewer">
      <iframe
        ref={frame}
        className="viewer__frame"
        key={src}
        src={src}
        title={`${label} — Sitzung`}
        onLoad={() => { setFrameReady((n) => n + 1); focusFrame() }}
        /* Ohne diese Zeile funktioniert die Zwischenablage nicht. */
        allow="clipboard-read; clipboard-write; fullscreen; autoplay; microphone; camera"
      />

      <button
        className={`viewer__handle${barOpen ? ' is-open' : ''}`}
        onClick={() => setBarOpen(!barOpen)}
        aria-expanded={barOpen}
        aria-label={barOpen ? 'Kontrollleiste schliessen' : 'Kontrollleiste öffnen'}
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
              aria-label="Leiste schliessen">✕</button>
          </header>

          {session.template_mode === 'workspace' && (
            <div className="viewer__group">
              <span className="silk">Anwendung</span>
              <div className="strip" style={{ marginTop: 9 }}>
                <button className={`strip__app${!stream ? ' is-on' : ''}`}
                  onClick={() => onSwitch(undefined)}>
                  <span className="strip__icon" aria-hidden="true">▦</span>
                  <span className="strip__name">Desktop</span>
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
                Alle Anwendungen teilen sich dasselbe Zuhause und dieselbe Zwischenablage.
              </p>
            </div>
          )}

          <div className="viewer__group">
            <span className="silk">Zwischenablage</span>
            <p className="field__hint" style={{ marginTop: 6 }}>
              Strg+C und Strg+V funktionieren direkt. Dieses Feld ist der Weg, wenn
              der Browser die Zwischenablage nicht freigibt.
            </p>
            <textarea
              className="viewer__clip"
              value={clip}
              placeholder="Text zum Übertragen…"
              aria-label="Zwischenablage-Inhalt"
              onChange={(e) => setClip(e.target.value)}
            />
            <div className="viewer__row">
              <button className="btn btn--sm" onClick={readClipboard}>Aus dem Browser holen</button>
              <button className="btn btn--sm" onClick={writeClipboard}>In den Browser legen</button>
            </div>
          </div>

          <div className="viewer__group">
            <span className="silk">Ansicht</span>
            <div className="viewer__row" style={{ marginTop: 8 }}>
              <button className="btn btn--sm" onClick={() => frame.current?.requestFullscreen()}>
                Vollbild
              </button>
              <button className="btn btn--sm" onClick={() => { focusFrame(); onToast('Fokus zurück in der Sitzung') }}>
                Fokus setzen
              </button>
            </div>
          </div>

          <div className="viewer__group">
            <span className="silk">Sitzung</span>
            <div className="viewer__row" style={{ marginTop: 8 }}>
              <button className="btn btn--sm" onClick={() => {
                if (frame.current) frame.current.src = src
                onToast('Neu verbunden')
              }}>Neu verbinden</button>
              <button className="btn btn--sm btn--halt" onClick={onClose}>Zurück zum Dashboard</button>
            </div>
          </div>
        </aside>
      )}
    </div>
  )
}
