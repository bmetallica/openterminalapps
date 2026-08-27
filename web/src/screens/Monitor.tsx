import { useEffect, useState } from 'react'
import { Led } from '../components/controls'
import { ApiError, api, type AdminSession, type AuditEntry } from '../lib/api'
import { Backups } from './Backups'
import { ago, duration, gb } from '../lib/format'
import { getLang, t as tr, useLang } from '../lib/i18n'

type Tab = 'Sessions' | 'Protokoll' | 'Sicherung'

/* Technische Vorgangsnamen in Klartext. Wer ins Protokoll schaut, will
   wissen was passiert ist — nicht, wie der Endpunkt heisst. */
const ACTION_TEXT: Record<string, string> = {
  'login.ok': 'Anmeldung',
  'login.failed': 'Anmeldung fehlgeschlagen',
  'login.totp_failed': 'Zweiter Faktor falsch',
  'password.changed': 'Passwort geändert',
  'session.started': 'Session gestartet',
  'session.stop': 'Session gestoppt',
  'session.pause': 'Session pausiert',
  'session.unpause': 'Session fortgesetzt',
  'session.deleted': 'Session beendet',
  'app.started': 'Anwendung geöffnet',
  'app.stopped': 'Anwendung geschlossen',
  'template.created': 'Workspace angelegt',
  'template.updated': 'Workspace geändert',
  'template.deleted': 'Workspace gelöscht',
  'template.apps_set': 'App-Katalog gesetzt',
  'override.set': 'Zuteilung gesetzt',
  'override.cleared': 'Zuteilung entfernt',
  'user.created': 'Nutzer angelegt',
  'user.updated': 'Nutzer geändert',
  'user.deleted': 'Nutzer gelöscht',
  'group.created': 'Gruppe angelegt',
  'group.updated': 'Gruppe geändert',
  'group.deleted': 'Gruppe gelöscht',
}

const FAILURE = /failed/

export function Monitor({ onToast }: { onToast: (m: string, tone?: 'ok' | 'bad') => void }) {
  useLang()
  const [tab, setTab] = useState<Tab>('Sessions')
  const [sessions, setSessions] = useState<AdminSession[] | null>(null)
  const [audit, setAudit] = useState<AuditEntry[]>([])
  const [failed, setFailed] = useState<string | null>(null)

  async function load() {
    try {
      const [s, a] = await Promise.all([api.adminSessions(), api.audit(120)])
      setSessions(s); setAudit(a); setFailed(null)
    } catch (err) {
      setFailed(err instanceof ApiError ? err.message : 'Laden fehlgeschlagen')
    }
  }

  useEffect(() => {
    void load()
    const timer = setInterval(() => { void load() }, 15_000)
    return () => clearInterval(timer)
  }, [])

  async function stop(s: AdminSession) {
    try {
      await api.deleteSession(s.id)
      onToast(`Session von ${s.username} beendet. Das Profil bleibt erhalten.`)
      await load()
    } catch (err) {
      onToast(err instanceof ApiError ? err.message : 'Beenden fehlgeschlagen', 'bad')
    }
  }

  if (failed) {
    return (
      <div className="wrap"><div className="empty">
        <p className="empty__title">{tr('Konnte nicht geladen werden')}</p>
        <p className="empty__body">{failed}</p>
        <button className="btn" onClick={() => void load()}>Erneut versuchen</button>
      </div></div>
    )
  }
  if (!sessions) return <div className="wrap"><p className="sub">Wird geladen…</p></div>

  const totalMem = sessions.reduce((a, s) => a + s.memory_bytes, 0)

  return (
    <div className="wrap">
      <header className="topbar">
        <div>
          <p className="silk" style={{ marginBottom: 6 }}>{tr('Verwaltung')}</p>
          <h1 className="h-page">{tr('Betrieb')}</h1>
        </div>
      </header>

      <div className="seg" role="radiogroup" aria-label={tr('Ansicht')} style={{ marginBottom: 20 }}>
        {(['Sessions', 'Protokoll', 'Sicherung'] as Tab[]).map((x) => (
          <button key={x} type="button" role="radio" aria-checked={tab === x}
            className={`seg__opt${tab === x ? ' is-on' : ''}`} onClick={() => setTab(x)}>
            {tr(x)}{x !== 'Sicherung' && (
              <span className="data" style={{ opacity: .6 }}>
                {' '}{x === 'Sessions' ? sessions.length : audit.length}
              </span>
            )}
          </button>
        ))}
      </div>

      {tab === 'Sicherung' ? (
        <Backups onToast={onToast} />
      ) : tab === 'Sessions' ? (
        sessions.length === 0 ? (
          <div className="empty">
            <p className="empty__title">{tr('Zurzeit läuft nichts')}</p>
            <p className="empty__body">
              {tr('Hier stehen alle Sessions aller Nutzer, sobald jemand einen Workspace öffnet.')}
            </p>
          </div>
        ) : (
          <>
            <p className="sub" style={{ marginBottom: 14 }}>
              {tr('{n} Session(en) belegen zusammen', { n: sessions.length })}{' '}
              <b className="data">{gb(totalMem)} GB</b>{' '}{tr('zugeteilten Speicher.')}
            </p>
            <div className="panel" style={{ padding: '14px 0 0' }}>
              <table className="tbl">
                <thead>
                  <tr>
                    <th style={{ paddingLeft: 20 }}>{tr('Nutzer')}</th>
                    <th>{tr('Workspace')}</th>
                    <th>{tr('Laufzeit')}</th>
                    <th>{tr('Zuletzt aktiv')}</th>
                    <th>{tr('Zugeteilt')}</th>
                    <th>{tr('Status')}</th>
                    <th />
                  </tr>
                </thead>
                <tbody>
                  {sessions.map((s) => (
                    <tr key={s.id}>
                      <td style={{ paddingLeft: 20, fontWeight: 500 }}>{s.username}</td>
                      <td style={{ color: 'var(--label)' }}>
                        <span aria-hidden="true" style={{ marginRight: 8 }}>{s.template_icon}</span>
                        {s.template_name}
                        {s.app_count > 0 && (
                          <span className="silk" style={{ marginLeft: 8 }}>
                            {tr('{n} Apps', { n: s.app_count })}
                          </span>
                        )}
                      </td>
                      <td className="data" style={{ color: 'var(--label)' }}>
                        {duration(Date.now() - new Date(s.started_at).getTime())}
                      </td>
                      <td className="data" style={{ color: 'var(--mute)', fontSize: 12 }}>
                        {ago(new Date(s.last_seen_at).getTime())}
                      </td>
                      <td className="data" style={{ color: 'var(--label)' }}>
                        {s.cores} × {gb(s.memory_bytes)} GB
                      </td>
                      <td><Led status={s.status} /></td>
                      <td style={{ textAlign: 'right', paddingRight: 20 }}>
                        <button className="btn btn--sm btn--halt" onClick={() => void stop(s)}>
                          {tr('Beenden')}
                        </button>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            <p className="field__hint" style={{ marginTop: 12 }}>
              {tr('Beenden entfernt nur den Container. Das persistente Profil des Nutzers bleibt erhalten.')}
            </p>
          </>
        )
      ) : (
        <>
          <p className="sub" style={{ marginBottom: 14 }}>
            {tr('Vorgänge, keine Inhalte. Was in einer Session getan wird, steht hier nicht.')}
          </p>
          <div className="panel" style={{ padding: '14px 0 0' }}>
            <table className="tbl">
              <thead>
                <tr>
                  <th style={{ paddingLeft: 20 }}>{tr('Zeitpunkt')}</th>
                  <th>{tr('Wer')}</th>
                  <th>{tr('Was')}</th>
                  <th>{tr('Betrifft')}</th>
                  <th>{tr('Von wo')}</th>
                </tr>
              </thead>
              <tbody>
                {audit.map((e, i) => {
                  const bad = FAILURE.test(e.action)
                  return (
                    <tr key={i} style={{ cursor: 'default' }}>
                      <td style={{ paddingLeft: 20 }} className="data">
                        {new Date(e.ts).toLocaleString(getLang() === 'de' ? 'de-DE' : 'en-GB', {
                          day: '2-digit', month: '2-digit',
                          hour: '2-digit', minute: '2-digit', second: '2-digit',
                        })}
                      </td>
                      <td style={{ color: 'var(--label)' }}>{e.actor ?? '—'}</td>
                      <td style={{ color: bad ? 'var(--halt)' : 'var(--text)' }}>
                        {tr(ACTION_TEXT[e.action] ?? e.action)}
                      </td>
                      <td className="data" style={{ color: 'var(--mute)', fontSize: 11.5 }}>
                        {e.object_id ?? '—'}
                      </td>
                      <td className="data" style={{ color: 'var(--mute)', fontSize: 11.5 }}>
                        {e.ip ?? '—'}
                      </td>
                    </tr>
                  )
                })}
              </tbody>
            </table>
          </div>
        </>
      )}
    </div>
  )
}
