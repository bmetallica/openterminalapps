import { useEffect, useState } from 'react'
import { Led } from '../components/controls'
import { ApiError, api, type AdminSession, type AuditEntry } from '../lib/api'
import { Backups } from './Backups'
import { ago, duration, gb } from '../lib/format'
import { getLang, t as tr, useLang } from '../lib/i18n'

type Tab = 'Sessions' | 'Protokoll' | 'Sicherung'

/* Technische Vorgangsnamen in Klartext. Wer ins Protokoll schaut, will
   wissen was passiert ist — nicht, wie der Endpunkt heisst.

   **Vollständig zu halten ist hier keine Fleissarbeit, sondern der Zweck.**
   Am 2026-09-05 standen hier 23 Einträge, während in der Datenbank 78
   verschiedene Vorgänge vorkamen — der Rest erschien als roher Bezeichner.
   Darunter ausgerechnet `session.attached`: der Eintrag, den ein Betroffener
   oder ein Betriebsrat lesen können muss. Wer einen neuen Vorgang
   protokolliert, trägt ihn hier ein. */
const ACTION_TEXT: Record<string, string> = {
  // Anmeldung
  'login.ok': 'Anmeldung',
  'login.oidc_ok': 'Anmeldung über die zentrale Anmeldung',
  'login.failed': 'Anmeldung fehlgeschlagen',
  'login.oidc_refused': 'Zentrale Anmeldung abgewiesen',
  'login.oidc_rejected': 'Zentrale Anmeldung zurückgewiesen',
  'login.totp_failed': 'Zweiter Faktor falsch',
  'login.recovery_used': 'Rückfallcode benutzt',
  'login.recovery_failed': 'Rückfallcode falsch',
  'login.directory_unreachable': 'Verzeichnis nicht erreichbar',
  'logout.backchannel': 'Abmeldung über den Rückkanal',
  'password.changed': 'Passwort geändert',
  'totp.enabled': 'Zweiter Faktor eingerichtet',
  'totp.disabled': 'Zweiter Faktor abgeschaltet',
  'user.totp_reset': 'Zweiter Faktor zurückgesetzt',

  // Sitzungen
  'session.started': 'Session gestartet',
  'session.stop': 'Session gestoppt',
  'session.pause': 'Session pausiert',
  'session.unpause': 'Session fortgesetzt',
  'session.deleted': 'Session beendet',
  // Der wichtigste Eintrag in dieser Liste.
  'session.attached': 'Auf fremden Bildschirm geschaltet',
  'app.started': 'Anwendung geöffnet',
  'app.stopped': 'Anwendung geschlossen',

  // Workspaces und Zuteilung
  'template.created': 'Workspace angelegt',
  'template.updated': 'Workspace geändert',
  'template.deleted': 'Workspace gelöscht',
  'template.apps_set': 'App-Katalog gesetzt',
  'override.set': 'Zuteilung gesetzt',
  'override.cleared': 'Zuteilung entfernt',
  'once_script.created': 'Einmal-Skript angelegt',
  'once_script.deleted': 'Einmal-Skript gelöscht',
  'once_script.reset': 'Einmal-Skript zurückgesetzt',

  // Nutzer und Gruppen
  'user.created': 'Nutzer angelegt',
  'user.created_from_directory': 'Nutzer aus dem Verzeichnis übernommen',
  'user.updated': 'Nutzer geändert',
  'user.deleted': 'Nutzer gelöscht',
  'group.created': 'Gruppe angelegt',
  'group.updated': 'Gruppe geändert',
  'group.deleted': 'Gruppe gelöscht',
  'uebernahme.gelaufen': 'Bestandskonten übernommen',
  'uebernahme.zurueckgenommen': 'Übernahme zurückgenommen',

  // Identität
  'identity.updated': 'Anmeldung eingerichtet',
  'identity.synced': 'Mit Keycloak abgeglichen',
  'keycloak.verzeichnis_gesetzt': 'Verzeichnis in Keycloak eingerichtet',
  'keycloak.verzeichnis_entfernt': 'Verzeichnis in Keycloak entfernt',
  'keycloak.verzeichnis_abgleich': 'Verzeichnis abgeglichen',
  'notfallkonto.gesetzt': 'Notfallkonto gesetzt',
  'notfallkonto.entfernt': 'Notfallkonto entfernt',
  'webapp.created': 'Anwendung angebunden',
  'webapp.updated': 'Angebundene Anwendung geändert',
  'webapp.deleted': 'Angebundene Anwendung entfernt',
  'webapp.secret_rotated': 'Geheimnis der Anwendung erneuert',

  // Netz
  'netprofile.created': 'Netzprofil angelegt',
  'netprofile.deleted': 'Netzprofil gelöscht',
  'netprofile.opened': 'Netzprofil auf „aus“ gesetzt',
  'firewall.global_updated': 'Globale Freigaben geändert',
  'firewall.forward_created': 'Portfreigabe angelegt',
  'firewall.forward_deleted': 'Portfreigabe entfernt',

  // Images und Rezepte
  'build.started': 'Image-Bau gestartet',
  'build.activated': 'Image-Fassung aktiviert',
  'build.deleted': 'Image-Fassung gelöscht',
  'build.frozen': 'Session eingefroren',
  'recipe.created': 'Rezept angelegt',
  'recipe.updated': 'Rezept geändert',
  'recipe.deleted': 'Rezept gelöscht',
  'registry.added': 'Registry eingetragen',
  'registry.refreshed': 'Registry aktualisiert',
  'registry.imported': 'Aus Registry übernommen',

  // Dateien und Ablagen
  'files.uploaded': 'Datei in die eigene Ablage gelegt',
  'files.deleted': 'Datei aus der eigenen Ablage gelöscht',
  'shared.uploaded': 'Datei in die gemeinsame Ablage gelegt',
  'shared.deleted': 'Datei aus der gemeinsamen Ablage gelöscht',
  'shared.dir_created': 'Ordner in der gemeinsamen Ablage angelegt',
  'groupfiles.uploaded': 'Datei ins Gruppenlaufwerk gelegt',
  'groupfiles.deleted': 'Datei aus dem Gruppenlaufwerk gelöscht',
  'skeleton.uploaded': 'Skeleton-Datei hinzugefügt',
  'skeleton.removed': 'Skeleton-Datei entfernt',
  'skeleton.dir_created': 'Skeleton-Ordner angelegt',

  // Betrieb
  'settings.updated': 'Einstellungen geändert',
  'branding.updated': 'Marke geändert',
  'branding.logo_set': 'Zeichen gesetzt',
  'branding.logo_cleared': 'Zeichen entfernt',
  'backup.started': 'Sicherung gestartet',
  'backup.policy_changed': 'Sicherungsplan geändert',
  'backup.restored': 'Profil wiederhergestellt',
  'backup.restored_container': 'Container wiederhergestellt',
  'protokoll.aufgeraeumt': 'Protokoll aufgeräumt (Aufbewahrungsfrist)',
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
