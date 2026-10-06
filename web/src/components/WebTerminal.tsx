import { useEffect, useRef, useState } from 'react'
import { Terminal } from '@xterm/xterm'
import { FitAddon } from '@xterm/addon-fit'
import '@xterm/xterm/css/xterm.css'
import { t as tr } from '../lib/i18n'

/**
 * Eine root-Shell im Arbeitsplatz eines Nutzers — für Administratoren
 * (Handbuch Kapitel 25).
 *
 * Browser ⇄ API ⇄ Agent ⇄ `docker exec`. Die API steht in der Mitte, weil nur
 * sie weiss, wer tippt: Jede Eingabezeile landet dort mit Namen im
 * Terminal-Protokoll, bevor sie weitergeht. Dieses Fenster sagt das, bevor
 * jemand etwas eintippt.
 *
 * Protokoll zur API: Eingaben als `{"i": "…"}`, Grösse als `{"r": [Spalten,
 * Zeilen]}`; zurück kommt die Ausgabe der Shell als Bytes.
 */
export function WebTerminal({ sessionId, title, onClose }: {
  sessionId: string
  title: string
  onClose: () => void
}) {
  const box = useRef<HTMLDivElement>(null)
  const [zustand, setZustand] = useState<'verbindet' | 'offen' | 'zu'>('verbindet')

  useEffect(() => {
    if (!box.current) return
    const term = new Terminal({
      cursorBlink: true,
      fontSize: 13,
      // Nur Schriften, die auf dem Rechner liegen — die Oberfläche lädt nichts
      // von fremden Hosts (M13).
      fontFamily: 'ui-monospace, "DejaVu Sans Mono", "Liberation Mono", Menlo, Consolas, monospace',
      theme: { background: '#0e1116', foreground: '#d7dde5', cursor: '#d7dde5' },
      scrollback: 5000,
    })
    const fit = new FitAddon()
    term.loadAddon(fit)
    term.open(box.current)
    fit.fit()

    const proto = location.protocol === 'https:' ? 'wss' : 'ws'
    const ws = new WebSocket(`${proto}://${location.host}/api/admin/arbeitsplaetze/${sessionId}/terminal`)
    ws.binaryType = 'arraybuffer'
    const groesse = () => {
      if (ws.readyState === WebSocket.OPEN) ws.send(JSON.stringify({ r: [term.cols, term.rows] }))
    }
    ws.onopen = () => { setZustand('offen'); groesse(); term.focus() }
    ws.onmessage = (e) => {
      term.write(typeof e.data === 'string' ? e.data : new Uint8Array(e.data as ArrayBuffer))
    }
    ws.onclose = (e) => {
      setZustand('zu')
      const grund = e.code === 4403 ? tr('Dafür fehlt das Recht „Per Webterminal in Arbeitsplätze“.')
        : e.code === 4409 ? tr('Der Arbeitsplatz läuft nicht.')
          : tr('Verbindung beendet.')
      term.write(`\r\n\x1b[2m[${grund}]\x1b[0m\r\n`)
    }
    const eingabe = term.onData((daten) => {
      if (ws.readyState === WebSocket.OPEN) ws.send(JSON.stringify({ i: daten }))
    })
    const neu = () => { fit.fit(); groesse() }
    window.addEventListener('resize', neu)
    return () => {
      window.removeEventListener('resize', neu)
      eingabe.dispose()
      ws.close()
      term.dispose()
    }
  }, [sessionId])

  return (
    <div className="overlay" role="dialog" aria-modal="true" aria-label={title}
      style={{ position: 'fixed', inset: 0, zIndex: 50, background: 'rgba(0,0,0,.55)',
               display: 'flex', alignItems: 'center', justifyContent: 'center', padding: 24 }}>
      <div className="panel" style={{ width: 'min(1200px, 100%)', height: 'min(760px, 100%)',
                                       display: 'flex', flexDirection: 'column', padding: 0 }}>
        <header style={{ display: 'flex', alignItems: 'center', gap: 12, padding: '12px 16px',
                         borderBottom: '1px solid var(--edge)' }}>
          <div style={{ flex: 1 }}>
            <p className="silk" style={{ margin: 0 }}>{tr('Webterminal · root')}</p>
            <b>{title}</b>
          </div>
          <span className="silk">
            {zustand === 'offen' ? tr('verbunden') : zustand === 'verbindet' ? tr('verbindet…') : tr('getrennt')}
          </span>
          <button className="btn btn--ghost" onClick={onClose}>{tr('Schliessen')}</button>
        </header>
        <p className="field__hint" style={{ margin: '8px 16px 0' }}>
          {tr('Jede Eingabe wird mit deinem Namen protokolliert und lässt sich unter Betrieb exportieren. Kennwörter nicht auf der Kommandozeile eintippen.')}
        </p>
        <div ref={box} style={{ flex: 1, minHeight: 0, margin: 12, background: '#0e1116' }} />
      </div>
    </div>
  )
}
