import { useEffect, useState } from 'react'
import { Led, stateClass } from '../components/controls'
import { ApiError, api, type Me, type Session, type Stream, type Template } from '../lib/api'
import { ago, duration, gb } from '../lib/format'

function greeting(): string {
  const h = new Date().getHours()
  if (h < 5) return 'Noch wach'
  if (h < 11) return 'Guten Morgen'
  if (h < 18) return 'Guten Tag'
  return 'Guten Abend'
}

function Bay({ session, template, onOpen, onAct, onApp, busy, busyApp }: {
  session: Session
  template: Template | undefined
  onOpen: (s: Session, stream?: Stream) => void
  onAct: (s: Session, a: 'pause' | 'unpause' | 'stop') => void
  onApp: (s: Session, slug: string) => void
  busy: boolean
  busyApp: string | null
}) {
  const running = session.status === 'running'
  const started = new Date(session.started_at).getTime()
  const isWorkspace = session.template_mode === 'workspace'
  const apps = (template?.apps ?? []).filter((a) => a.is_enabled && !a.blocked_reason)
  const openSlugs = new Set(session.streams.map((s) => s.app_slug))

  return (
    <article className={`panel panel--state panel--${stateClass(session.status)} bay`}>
      <div className={`bay__screen${running ? ' bay__screen--on' : ''}`}>
        <span className="bay__screen-tag data">{running ? 'bereit' : 'eingefroren'}</span>
      </div>

      <div className="bay__meta">
        <div className="bay__title-row">
          <h3 className="h-card">{session.template_name}</h3>
          <Led status={session.status} />
        </div>

        {session.error && <p className="note-warn" style={{ marginTop: 8 }}>{session.error}</p>}

        {isWorkspace && apps.length > 0 && (
          <div className="strip">
            {apps.map((a) => {
              const stream = session.streams.find((s) => s.app_slug === a.slug)
              const on = openSlugs.has(a.slug)
              return (
                <button key={a.slug} className={`strip__app${on ? ' is-on' : ''}`}
                  disabled={!running || busyApp === a.slug}
                  title={on ? `${a.name} anzeigen` : `${a.name} starten`}
                  onClick={() => (on && stream ? onOpen(session, stream) : onApp(session, a.slug))}>
                  <span className="strip__icon" aria-hidden="true">{a.icon}</span>
                  <span className="strip__name">{a.name}</span>
                  {busyApp === a.slug
                    ? <span className="strip__wait" aria-label="startet" />
                    : on && <span className="strip__led" aria-label="läuft" />}
                </button>
              )
            })}
          </div>
        )}

        <div className="bay__facts">
          <span className="bay__fact"><span className="silk">Laufzeit</span>
            <b>{duration(Date.now() - started)}</b></span>
          <span className="bay__fact"><span className="silk">Zuletzt aktiv</span>
            <b>{ago(new Date(session.last_seen_at).getTime())}</b></span>
          <span className="bay__fact"><span className="silk">Zugeteilt</span>
            <b>{session.cores} × {gb(session.memory_bytes)} GB</b></span>
          {isWorkspace && (
            <span className="bay__fact"><span className="silk">Apps offen</span>
              <b>{session.streams.length} von {apps.length}</b></span>
          )}
        </div>
      </div>

      <div className="bay__actions">
        <button className="btn btn--primary" disabled={busy}
          onClick={() => (running ? onOpen(session) : onAct(session, 'unpause'))}>
          {running ? (isWorkspace ? 'Desktop öffnen' : 'Weiter arbeiten') : 'Fortsetzen'}
        </button>
        {running && (
          <button className="btn" disabled={busy} onClick={() => onAct(session, 'pause')}>Pause</button>
        )}
        <button className="btn btn--halt btn--icon" disabled={busy}
          aria-label={`${session.template_name} beenden`}
          onClick={() => onAct(session, 'stop')}>■</button>
      </div>
    </article>
  )
}

export function Dashboard({ me, onOpen, onToast }: {
  me: Me
  onOpen: (s: Session, stream?: Stream) => void
  onToast: (m: string, tone?: 'ok' | 'bad') => void
}) {
  const [sessions, setSessions] = useState<Session[] | null>(null)
  const [templates, setTemplates] = useState<Template[] | null>(null)
  const [busy, setBusy] = useState<string | null>(null)
  const [busyApp, setBusyApp] = useState<string | null>(null)
  const [failed, setFailed] = useState<string | null>(null)

  async function load() {
    try {
      const [s, t] = await Promise.all([api.sessions(), api.templates()])
      setSessions(s)
      setTemplates(t)
      setFailed(null)
    } catch (err) {
      setFailed(err instanceof ApiError ? err.message : 'Laden fehlgeschlagen')
    }
  }

  useEffect(() => {
    void load()
    const timer = setInterval(() => { void load() }, 15_000)
    return () => clearInterval(timer)
  }, [])

  async function start(t: Template) {
    setBusy(t.id)
    try {
      const s = await api.startSession(t.id)
      onToast(`${t.friendly_name} läuft`)
      await load()
      if (s.status === 'running') onOpen(s)
    } catch (err) {
      onToast(err instanceof ApiError ? err.message : 'Start fehlgeschlagen', 'bad')
    } finally {
      setBusy(null)
    }
  }

  /** Startet eine Anwendung im Arbeitsplatz und öffnet sie danach. */
  async function openApp(s: Session, slug: string) {
    setBusyApp(slug)
    try {
      const updated = await api.startApp(s.id, slug)
      const stream = updated.streams.find((x) => x.app_slug === slug)
      setSessions((prev) => (prev ?? []).map((x) => (x.id === updated.id ? updated : x)))
      if (stream) onOpen(updated, stream)
    } catch (err) {
      onToast(err instanceof ApiError ? err.message : 'Start fehlgeschlagen', 'bad')
    } finally {
      setBusyApp(null)
    }
  }

  async function act(s: Session, action: 'pause' | 'unpause' | 'stop') {
    setBusy(s.id)
    try {
      await api.sessionAction(s.id, action)
      onToast({ pause: 'Pausiert', unpause: 'Fortgesetzt', stop: 'Beendet — dein Profil bleibt erhalten' }[action])
      await load()
    } catch (err) {
      onToast(err instanceof ApiError ? err.message : 'Aktion fehlgeschlagen', 'bad')
    } finally {
      setBusy(null)
    }
  }

  if (failed) {
    return (
      <div className="wrap">
        <div className="empty">
          <p className="empty__title">Die Daten konnten nicht geladen werden</p>
          <p className="empty__body">{failed}</p>
          <button className="btn" onClick={() => void load()}>Erneut versuchen</button>
        </div>
      </div>
    )
  }

  if (!sessions || !templates) {
    return <div className="wrap"><p className="sub">Wird geladen…</p></div>
  }

  const busyTemplates = new Set(sessions.map((s) => s.template_id))
  const available = templates.filter((t) => t.is_enabled)

  return (
    <div className="wrap">
      <header className="topbar">
        <div>
          <p className="silk" style={{ marginBottom: 6 }}>Angemeldet als {me.username}</p>
          <h1 className="h-page">{greeting()}</h1>
        </div>
      </header>

      <section>
        <div className="section__head">
          <span className="silk">Deine Sessions</span>
          <span className="section__rule" />
          <span className="silk data">{sessions.length}</span>
        </div>

        {sessions.length > 0 ? (
          <div className="bay-grid">
            {sessions.map((s) => (
              <Bay key={s.id} session={s}
                template={templates.find((t) => t.id === s.template_id)}
                onOpen={onOpen} onAct={act} onApp={openApp}
                busy={busy === s.id} busyApp={busyApp} />
            ))}
          </div>
        ) : (
          <div className="empty">
            <p className="empty__title">Keine Session läuft</p>
            <p className="empty__body">
              Wähle unten eine App. Der erste Start dauert etwas länger, danach
              bleibt deine Umgebung erhalten.
            </p>
          </div>
        )}
      </section>

      <section className="section">
        <div className="section__head">
          <span className="silk">Deine Apps</span>
          <span className="section__rule" />
          <span className="silk data">{available.length}</span>
        </div>

        {available.length === 0 ? (
          <div className="empty">
            <p className="empty__title">Dir ist noch nichts zugewiesen</p>
            <p className="empty__body">
              Wende dich an deinen Administrator — er kann dir einen Arbeitsplatz freischalten.
            </p>
          </div>
        ) : (
          <div className="tiles">
            {available.map((t) => {
              const isBusy = busyTemplates.has(t.id)
              const cores = t.effective_cores ?? t.cores
              const mem = t.effective_memory_bytes ?? t.memory_bytes
              return (
                <button key={t.id} className={`tile${isBusy ? ' tile--busy' : ''}`}
                  disabled={busy === t.id}
                  onClick={() => (isBusy
                    ? onToast(`${t.friendly_name} läuft bereits — oben verbinden`)
                    : void start(t))}>
                  <span className="tile__top">
                    <span className="tile__icon" aria-hidden="true">{t.icon}</span>
                    <span className="tile__name">{t.friendly_name}</span>
                  </span>
                  <span className="tile__desc">{t.description}</span>
                  {t.mode === 'workspace' && t.apps.length > 0 && (
                    <span className="tile__mode">
                      {t.apps.filter((a) => a.is_enabled).length} Apps in einem Container
                    </span>
                  )}
                  <span className="tile__foot">
                    <span className="tile__spec data">
                      <span>{cores} {cores === 1 ? 'Kern' : 'Kerne'}</span>
                      <span>{gb(mem)} GB</span>
                    </span>
                    {busy === t.id
                      ? <span className="silk">startet…</span>
                      : isBusy
                        ? <Led status="live" />
                        : <span className="silk" style={{ color: 'var(--bone)' }}>Starten</span>}
                  </span>
                </button>
              )
            })}
          </div>
        )}
      </section>
    </div>
  )
}
