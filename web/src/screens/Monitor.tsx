import { useEffect, useState } from 'react'
import { Led } from '../components/controls'
import { WebTerminal } from '../components/WebTerminal'
import { ApiError, api, type Arbeitsplatz, type AuditEntry, type Platz } from '../lib/api'
import { Backups } from './Backups'
import { ago, duration, gb } from '../lib/format'
import { getLang, t as tr, useLang } from '../lib/i18n'

type Tab = 'Arbeitsplätze' | 'Protokoll' | 'Sicherung'

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

  // Root-Arbeitsplätze und Webterminal (Kapitel 25)
  'platz.angehalten': 'Root-Arbeitsplatz angehalten',
  'platz.fortgesetzt': 'Root-Arbeitsplatz fortgesetzt',
  'platz.neu_aufgesetzt': 'Root-Arbeitsplatz neu aufgesetzt',
  'platz.geloescht': 'Root-Arbeitsplatz gelöscht',
  'terminal.geoeffnet': 'Webterminal geöffnet',
  'terminal.geschlossen': 'Webterminal geschlossen',
  'terminal.protokoll_exportiert': 'Terminal-Protokoll exportiert',
}

const FAILURE = /failed/

function GrenzeLabel({ platz, grenzeGb }: { platz: Platz | undefined; grenzeGb: number }) {
  if (!platz) return <span className="silk">…</span>
  if (platz.gesamt === null) return <span className="silk">—</span>
  const anteil = grenzeGb ? platz.gesamt / (grenzeGb * 1024 ** 3) : 0
  return (
    <span className="data"
      style={{ color: anteil > 1 ? 'var(--halt)' : anteil > .9 ? 'var(--caution)' : 'var(--label)' }}
      title={tr('Container {c} GB, Docker-Daten {d} GB', {
        c: gb(platz.schicht ?? 0), d: gb(platz.docker ?? 0) })}>
      {gb(platz.gesamt)} / {grenzeGb} GB
    </span>
  )
}

export function Monitor({ onToast, darfTerminal = false }: {
  onToast: (m: string, tone?: 'ok' | 'bad') => void
  darfTerminal?: boolean
}) {
  useLang()
  const [tab, setTab] = useState<Tab>('Arbeitsplätze')
  const [sessions, setSessions] = useState<Arbeitsplatz[] | null>(null)
  const [audit, setAudit] = useState<AuditEntry[]>([])
  const [failed, setFailed] = useState<string | null>(null)
  const [plaetze, setPlaetze] = useState<Record<string, Platz>>({})
  const [terminal, setTerminal] = useState<Arbeitsplatz | null>(null)
  const [loeschFrage, setLoeschFrage] = useState<string | null>(null)
  const [busy, setBusy] = useState<string | null>(null)

  async function load() {
    try {
      const [s, a] = await Promise.all([api.arbeitsplaetze(), api.audit(120)])
      setSessions(s); setAudit(a); setFailed(null)
      // Der Platz wird je Root-Arbeitsplatz nachgeladen: Die Messung dauert,
      // und die Liste soll nicht auf sie warten.
      for (const x of s.filter((y) => y.klasse === 'root' && y.hat_container)) {
        api.arbeitsplatzPlatz(x.id)
          .then((p) => setPlaetze((prev) => ({ ...prev, [x.id]: p })))
          .catch(() => undefined)
      }
    } catch (err) {
      setFailed(err instanceof ApiError ? err.message : 'Laden fehlgeschlagen')
    }
  }

  async function aktion(x: Arbeitsplatz, was: 'starten' | 'anhalten' | 'loeschen') {
    setBusy(x.id)
    try {
      if (was === 'starten') await api.arbeitsplatzStarten(x.id)
      else if (was === 'anhalten') await api.arbeitsplatzAnhalten(x.id)
      else await api.arbeitsplatzLoeschen(x.id)
      onToast({
        starten: tr('{name} von {user} läuft', { name: x.template_name, user: x.username }),
        anhalten: tr('{name} von {user} angehalten — alles darin bleibt',
          { name: x.template_name, user: x.username }),
        loeschen: tr('{name} von {user} gelöscht. Das Zuhause bleibt erhalten.',
          { name: x.template_name, user: x.username }),
      }[was])
      setLoeschFrage(null)
      await load()
    } catch (err) {
      onToast(err instanceof ApiError ? err.message : tr('Aktion fehlgeschlagen'), 'bad')
    } finally {
      setBusy(null)
    }
  }

  useEffect(() => {
    void load()
    const timer = setInterval(() => { void load() }, 15_000)
    return () => clearInterval(timer)
  }, [])


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

  const laufend = sessions.filter((s) => s.status !== 'angehalten')
  const totalMem = laufend.reduce((a, s) => a + s.memory_bytes, 0)

  return (
    <div className="wrap">
      <header className="topbar">
        <div>
          <p className="silk" style={{ marginBottom: 6 }}>{tr('Verwaltung')}</p>
          <h1 className="h-page">{tr('Betrieb')}</h1>
        </div>
      </header>

      <div className="seg" role="radiogroup" aria-label={tr('Ansicht')} style={{ marginBottom: 20 }}>
        {(['Arbeitsplätze', 'Protokoll', 'Sicherung'] as Tab[]).map((x) => (
          <button key={x} type="button" role="radio" aria-checked={tab === x}
            className={`seg__opt${tab === x ? ' is-on' : ''}`} onClick={() => setTab(x)}>
            {tr(x)}{x !== 'Sicherung' && (
              <span className="data" style={{ opacity: .6 }}>
                {' '}{x === 'Arbeitsplätze' ? sessions.length : audit.length}
              </span>
            )}
          </button>
        ))}
      </div>

      {tab === 'Sicherung' ? (
        <Backups onToast={onToast} />
      ) : tab === 'Arbeitsplätze' ? (
        sessions.length === 0 ? (
          <div className="empty">
            <p className="empty__title">{tr('Zurzeit gibt es keine Arbeitsplätze')}</p>
            <p className="empty__body">
              {tr('Hier stehen alle laufenden Arbeitsplätze aller Nutzer — und angehaltene Root-Arbeitsplätze, die auf ihren nächsten Start warten.')}
            </p>
          </div>
        ) : (
          <>
            <p className="sub" style={{ marginBottom: 14 }}>
              {tr('{n} laufen und belegen zusammen', { n: laufend.length })}{' '}
              <b className="data">{gb(totalMem)} GB</b>{' '}{tr('zugeteilten Speicher.')}
              {sessions.length > laufend.length && (
                <>{' '}{tr('{n} Root-Arbeitsplätze sind angehalten.', { n: sessions.length - laufend.length })}</>
              )}
            </p>
            <div className="panel" style={{ padding: '14px 0 0', overflowX: 'auto' }}>
              <table className="tbl">
                <thead>
                  <tr>
                    <th style={{ paddingLeft: 20 }}>{tr('Nutzer')}</th>
                    <th>{tr('Workspace')}</th>
                    <th>{tr('Status')}</th>
                    <th>{tr('Zuletzt aktiv')}</th>
                    <th>{tr('Platz')}</th>
                    <th>{tr('Zugeteilt')}</th>
                    <th />
                  </tr>
                </thead>
                <tbody>
                  {sessions.map((s) => {
                    const root = s.klasse === 'root'
                    const laeuft = s.status === 'running'
                    const angehalten = s.status === 'angehalten'
                    return (
                      <tr key={s.id}>
                        <td style={{ paddingLeft: 20, fontWeight: 500 }}>
                          {s.username}
                          {s.display_name && (
                            <span className="silk" style={{ display: 'block' }}>{s.display_name}</span>
                          )}
                        </td>
                        <td style={{ color: 'var(--label)' }}>
                          <span aria-hidden="true" style={{ marginRight: 8 }}>{s.template_icon}</span>
                          {s.template_name}
                          {root && (
                            <span className="silk" style={{ marginLeft: 8, color: 'var(--halt)' }}>root</span>
                          )}
                          {s.app_count > 0 && laeuft && (
                            <span className="silk" style={{ marginLeft: 8 }}>
                              {tr('{n} Apps', { n: s.app_count })}
                            </span>
                          )}
                        </td>
                        <td><Led status={s.status} /></td>
                        <td className="data" style={{ color: 'var(--mute)', fontSize: 12 }}>
                          {ago(new Date(s.last_seen_at).getTime())}
                        </td>
                        <td>
                          {root && s.hat_container
                            ? <GrenzeLabel platz={plaetze[s.id]} grenzeGb={s.platz_grenze_gb} />
                            : root ? <span className="silk">{tr('neu aufgesetzt')}</span>
                              : <span className="silk">—</span>}
                        </td>
                        <td className="data" style={{ color: 'var(--label)' }}>
                          {laeuft ? `${s.cores} × ${gb(s.memory_bytes)} GB` : '—'}
                        </td>
                        <td style={{ textAlign: 'right', paddingRight: 20, whiteSpace: 'nowrap' }}>
                          {loeschFrage === s.id ? (
                            <>
                              <span className="silk" style={{ marginRight: 8 }}>
                                {root ? tr('Samt Docker-Daten löschen?') : tr('Container beenden?')}
                              </span>
                              <button className="btn btn--sm btn--halt" disabled={busy === s.id}
                                onClick={() => void aktion(s, 'loeschen')}>
                                {root ? tr('Löschen') : tr('Beenden')}
                              </button>{' '}
                              <button className="btn btn--sm btn--ghost"
                                onClick={() => setLoeschFrage(null)}>{tr('Abbrechen')}</button>
                            </>
                          ) : (
                            <>
                              {laeuft && darfTerminal && (
                                <button className="btn btn--sm" onClick={() => setTerminal(s)}
                                  title={tr('root-Shell im Browser — jede Eingabe wird protokolliert')}>
                                  {tr('Terminal')}
                                </button>
                              )}{' '}
                              {root && angehalten && s.hat_container && (
                                <button className="btn btn--sm" disabled={busy === s.id}
                                  onClick={() => void aktion(s, 'starten')}>{tr('Starten')}</button>
                              )}
                              {root && laeuft && (
                                <button className="btn btn--sm" disabled={busy === s.id}
                                  onClick={() => void aktion(s, 'anhalten')}>{tr('Anhalten')}</button>
                              )}{' '}
                              <a className="btn btn--sm btn--ghost" href={api.terminalProtokollUrl(s.id, 'txt')}
                                title={tr('Terminal-Protokoll dieses Arbeitsplatzes herunterladen')}>
                                {tr('Terminal-Protokoll')}
                              </a>{' '}
                              <a className="btn btn--sm btn--ghost" href={api.terminalProtokollUrl(s.id, 'csv')}
                                title={tr('Terminal-Protokoll als CSV')}>CSV</a>{' '}
                              <button className="btn btn--sm btn--halt" disabled={busy === s.id}
                                onClick={() => setLoeschFrage(s.id)}>
                                {root ? tr('Löschen') : tr('Beenden')}
                              </button>
                            </>
                          )}
                        </td>
                      </tr>
                    )
                  })}
                </tbody>
              </table>
            </div>
            <p className="field__hint" style={{ marginTop: 12 }}>
              {tr('Beenden entfernt den Container eines Standard-Arbeitsplatzes. Löschen entfernt einen Root-Arbeitsplatz samt Docker-Daten. Das Zuhause des Nutzers bleibt in beiden Fällen erhalten.')}
            </p>
            {terminal && (
              <WebTerminal sessionId={terminal.id}
                title={`${terminal.username} · ${terminal.template_name}`}
                onClose={() => setTerminal(null)} />
            )}
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
