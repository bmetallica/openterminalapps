import { useCallback, useEffect, useState } from 'react'
import { Dashboard } from './screens/Dashboard'
import { Login } from './screens/Login'
import { SessionViewer } from './screens/SessionViewer'
import { Workspaces } from './screens/Workspaces'
import { ApiError, api, type Host, type Me, type Session, type Stream, type Template } from './lib/api'
import { gb } from './lib/format'
import './styles/app.css'

type View = 'dashboard' | 'workspaces'
type Toast = { id: number; msg: string; tone: 'ok' | 'bad' }

const NAV: { id: View; glyph: string; cap: string; adminOnly: boolean }[] = [
  { id: 'dashboard', glyph: '▣', cap: 'Start', adminOnly: false },
  { id: 'workspaces', glyph: '⬡', cap: 'Workspaces', adminOnly: true },
]

export default function App() {
  const [me, setMe] = useState<Me | null>(null)
  const [checking, setChecking] = useState(true)
  const [view, setView] = useState<View>('dashboard')
  const [viewing, setViewing] = useState<Session | null>(null)
  const [viewingStream, setViewingStream] = useState<Stream | undefined>()
  const [templates, setTemplates] = useState<Template[]>([])
  const [host, setHost] = useState<Host | null>(null)
  const [toasts, setToasts] = useState<Toast[]>([])

  const toast = useCallback((msg: string, tone: 'ok' | 'bad' = 'ok') => {
    const id = Date.now() + Math.random()
    setToasts((t) => [...t, { id, msg, tone }])
    setTimeout(() => setToasts((t) => t.filter((x) => x.id !== id)), tone === 'bad' ? 6000 : 2800)
  }, [])

  // Beim Laden prüfen, ob noch eine gültige Sitzung besteht.
  useEffect(() => {
    api.me().then(setMe).catch(() => setMe(null)).finally(() => setChecking(false))
  }, [])

  // Host-Auslastung nur für Admins — normale Nutzer bekommen dafür keine Rechte.
  useEffect(() => {
    if (!me?.is_admin) return
    const load = () => { api.host().then(setHost).catch(() => {}) }
    load()
    const timer = setInterval(load, 20_000)
    return () => clearInterval(timer)
  }, [me])

  // Für den App-Umschalter im Viewer wird der Katalog gebraucht.
  useEffect(() => {
    if (!me) return
    api.templates().then(setTemplates).catch(() => {})
  }, [me])

  function openSession(s: Session, stream?: Stream) {
    setViewing(s)
    setViewingStream(stream)
  }

  async function logout() {
    await api.logout().catch(() => {})
    setMe(null)
    setViewing(null)
    setViewingStream(undefined)
    setView('dashboard')
  }

  if (checking) {
    return <div className="boot"><span className="silk">OpenTerminalApps startet…</span></div>
  }

  if (!me) {
    return <Login onDone={(u) => { setMe(u); toast(`Willkommen, ${u.username}`) }} />
  }

  if (viewing) {
    return (
      <>
        <SessionViewer
          session={viewing}
          stream={viewingStream}
          template={templates.find((t) => t.id === viewing.template_id)}
          onSwitch={setViewingStream}
          onClose={() => { setViewing(null); setViewingStream(undefined) }}
          onToast={toast} />
        <Toasts items={toasts} />
      </>
    )
  }

  const visible = NAV.filter((n) => !n.adminOnly || me.is_admin)
  const current = visible.some((n) => n.id === view) ? view : 'dashboard'
  const freePct = host ? (host.memory_available / host.memory_total) * 100 : null

  return (
    <div className="shell">
      <nav className="rail" aria-label="Hauptnavigation">
        <div className="rail__mark" aria-hidden="true">O</div>

        {visible.map((n) => (
          <button key={n.id} className={`rail__btn${current === n.id ? ' is-on' : ''}`}
            onClick={() => setView(n.id)} aria-current={current === n.id ? 'page' : undefined}>
            <span className="rail__glyph" aria-hidden="true">{n.glyph}</span>
            <span className="rail__cap">{n.cap}</span>
          </button>
        ))}

        <div className="rail__spacer" />

        <button className="rail__btn" onClick={() => void logout()} title={`Abmelden (${me.username})`}>
          <span className="rail__glyph" aria-hidden="true">⇥</span>
          <span className="rail__cap">Abmelden</span>
        </button>

        {freePct !== null && host && (
          <div className="rail__host" title={`${gb(host.memory_available)} GB von ${gb(host.memory_total, 0)} GB frei`}>
            <span className={`led ${freePct < 15 ? 'led--fail' : 'led--live'}`}>
              <span className="led__dot" aria-hidden="true" />
            </span>
            <b className="data">{Math.round(freePct)}%</b>
            <span className="silk" style={{ fontSize: 8 }}>frei</span>
          </div>
        )}
      </nav>

      <main className="main">
        {me.must_change_password && (
          <PasswordGate onDone={() => setMe({ ...me, must_change_password: false })} onToast={toast} />
        )}
        {current === 'dashboard' && (
          <Dashboard me={me} onOpen={openSession} onToast={toast} />
        )}
        {current === 'workspaces' && <Workspaces onToast={toast} />}
      </main>

      <Toasts items={toasts} />
    </div>
  )
}

function Toasts({ items }: { items: Toast[] }) {
  return (
    <div className="toasts" role="status" aria-live="polite">
      {items.map((t) => (
        <div key={t.id} className={`toast${t.tone === 'bad' ? ' toast--bad' : ''}`}>
          <span className={`led ${t.tone === 'bad' ? 'led--fail' : 'led--live'}`}>
            <span className="led__dot" aria-hidden="true" />
          </span>
          {t.msg}
        </div>
      ))}
    </div>
  )
}

/** Erzwungener Passwortwechsel nach dem ersten Login. */
function PasswordGate({ onDone, onToast }: {
  onDone: () => void
  onToast: (m: string, tone?: 'ok' | 'bad') => void
}) {
  const [current, setCurrent] = useState('')
  const [next, setNext] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)

  async function submit(e: React.FormEvent) {
    e.preventDefault()
    setBusy(true)
    setError(null)
    try {
      await api.changePassword(current, next)
      onToast('Passwort geändert')
      onDone()
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'Wechsel fehlgeschlagen')
    } finally {
      setBusy(false)
    }
  }

  return (
    <>
      <div className="scrim" />
      <form className="drawer" style={{ width: 'min(460px, 100vw)' }} onSubmit={submit}>
        <header className="drawer__head">
          <div>
            <h2 className="h-card">Passwort ändern</h2>
            <p className="sub" style={{ marginTop: 4 }}>
              Dein Konto wurde mit einem Einmal-Passwort angelegt. Bitte vergib ein eigenes.
            </p>
          </div>
        </header>
        <div className="drawer__body">
          <label className="field">
            <span className="field__label" style={{ display: 'block', marginBottom: 8 }}>Aktuelles Passwort</span>
            <div className="row-item">
              <input type="password" value={current} required autoFocus
                onChange={(e) => setCurrent(e.target.value)} />
            </div>
          </label>
          <label className="field">
            <span className="field__label" style={{ display: 'block', marginBottom: 8 }}>Neues Passwort</span>
            <div className="row-item">
              <input type="password" value={next} required
                onChange={(e) => setNext(e.target.value)} />
            </div>
            <p className="field__hint">Mindestens 12 Zeichen.</p>
          </label>
          {error && <p className="login__error" role="alert">{error}</p>}
        </div>
        <footer className="drawer__foot">
          <button className="btn btn--primary" disabled={busy}>
            {busy ? 'Wird gespeichert…' : 'Passwort setzen'}
          </button>
        </footer>
      </form>
    </>
  )
}
