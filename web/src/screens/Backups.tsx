import { useEffect, useState } from 'react'
import { CapacityFader, Field, Toggle } from '../components/controls'
import {
  ApiError, api,
  type Backup, type BackupPolicy, type BackupStorage,
} from '../lib/api'
import { ago, gb } from '../lib/format'
import { getLang, t as tr, useLang } from '../lib/i18n'

const WEEKDAYS = ['Mo', 'Di', 'Mi', 'Do', 'Fr', 'Sa', 'So']

const KIND_TEXT: Record<string, string> = {
  profile: 'Profil',
  container: 'Container',
  database: 'Datenbank',
}

const TRIGGER_TEXT: Record<string, string> = {
  manual: 'von Hand',
  schedule: 'nach Plan',
  pre_restore: 'vor Wiederherstellung',
}

/** Grösse in der Einheit, die den Wert lesbar macht. "0,0 MB" sagt nichts. */
function size(bytes: number): string {
  if (bytes >= 1024 ** 3) return `${gb(bytes)} GB`
  if (bytes >= 1024 ** 2) return `${(bytes / 1024 ** 2).toFixed(1).replace('.', ',')} MB`
  if (bytes >= 1024) return `${Math.round(bytes / 1024)} KB`
  return `${bytes} B`
}

/* Der Zustand einer Sicherung ist nicht der einer Session — "läuft" wäre für
   eine abgeschlossene Sicherung schlicht falsch. */
const STATUS_TEXT: Record<string, string> = {
  ok: 'fertig',
  running: 'läuft',
  failed: 'fehlgeschlagen',
}
const STATUS_DOT: Record<string, string> = {
  ok: 'led--live',
  running: 'led--paused',
  failed: 'led--fail',
}

function BackupStatus({ status }: { status: string }) {
  return (
    <span className={`led ${STATUS_DOT[status] ?? 'led--stop'}`}>
      <span className="led__dot" aria-hidden="true" />
      <span className="led__text">{tr(STATUS_TEXT[status] ?? status)}</span>
    </span>
  )
}

export function Backups({ onToast }: { onToast: (m: string, tone?: 'ok' | 'bad') => void }) {
  useLang()
  const [list, setList] = useState<Backup[] | null>(null)
  const [storage, setStorage] = useState<BackupStorage | null>(null)
  const [policy, setPolicy] = useState<BackupPolicy | null>(null)
  const [busy, setBusy] = useState<string | null>(null)
  const [confirm, setConfirm] = useState<Backup | null>(null)
  const [dbHint, setDbHint] = useState<Backup | null>(null)
  const [failed, setFailed] = useState<string | null>(null)

  async function load() {
    try {
      const [b, s, p] = await Promise.all([
        api.backups(), api.backupStorage(), api.backupPolicy(),
      ])
      setList(b); setStorage(s); setPolicy(p); setFailed(null)
    } catch (err) {
      setFailed(err instanceof ApiError ? err.message : 'Laden fehlgeschlagen')
    }
  }

  useEffect(() => {
    void load()
    const timer = setInterval(() => { void load() }, 20_000)
    return () => clearInterval(timer)
  }, [])

  async function runAll() {
    setBusy('all')
    try {
      const res = await api.runBackup({})
      onToast(res.status)
      setTimeout(() => { void load() }, 2500)
    } catch (err) {
      onToast(err instanceof ApiError ? err.message : tr('Sicherung fehlgeschlagen'), 'bad')
    } finally {
      setBusy(null)
    }
  }

  async function runDatabase() {
    setBusy('db')
    try {
      onToast((await api.runBackup({ database_only: true })).status)
      await load()
    } catch (err) {
      onToast(err instanceof ApiError ? err.message : tr('Sicherung fehlgeschlagen'), 'bad')
    } finally {
      setBusy(null)
    }
  }

  /** Container-Sicherungen gehen in den laufenden Arbeitsplatz zurück. */
  async function restoreIntoSession(b: Backup) {
    setBusy(b.id)
    try {
      onToast((await api.restoreIntoSession(b.id)).status)
      await load()
    } catch (err) {
      onToast(err instanceof ApiError ? err.message : 'Wiederherstellung fehlgeschlagen', 'bad')
    } finally {
      setBusy(null)
    }
  }

  async function savePolicy(next: BackupPolicy) {
    setPolicy(next)
    try {
      await api.saveBackupPolicy(next)
    } catch (err) {
      onToast(err instanceof ApiError ? err.message : tr('Speichern fehlgeschlagen'), 'bad')
      void load()
    }
  }

  async function restore(b: Backup) {
    setBusy(b.id)
    try {
      const res = await api.restoreBackup(b.id)
      onToast(res.status)
      setConfirm(null)
      await load()
    } catch (err) {
      onToast(err instanceof ApiError ? err.message : 'Wiederherstellung fehlgeschlagen', 'bad')
      setConfirm(null)
    } finally {
      setBusy(null)
    }
  }

  async function remove(b: Backup) {
    setBusy(b.id)
    try {
      onToast((await api.deleteBackup(b.id)).status)
      await load()
    } catch (err) {
      onToast(err instanceof ApiError ? err.message : tr('Löschen fehlgeschlagen'), 'bad')
    } finally {
      setBusy(null)
    }
  }

  if (failed) {
    return (
      <div className="empty">
        <p className="empty__title">{tr('Konnte nicht geladen werden')}</p>
        <p className="empty__body">{failed}</p>
        <button className="btn" onClick={() => void load()}>{tr('Erneut versuchen')}</button>
      </div>
    )
  }
  if (!list || !storage || !policy) return <p className="sub">{tr('Wird geladen…')}</p>

  const usedPct = ((storage.disk_total - storage.disk_free) / storage.disk_total) * 100

  return (
    <>
      {/* Ablage */}
      <div className="meters" style={{ marginBottom: 20 }}>
        <div className="panel meter">
          <div className="meter__top"><span className="silk">{tr('Ablage')}</span>
            <span className="meter__val" style={{ fontSize: 13 }}>
              {storage.is_network ? tr('Netzlaufwerk') : tr('lokale Platte')}
            </span></div>
          <p className="meter__note data" style={{ fontSize: 11 }}>{storage.path}</p>
          <p className="meter__note">
            {storage.fstype}{storage.source ? ` · ${storage.source}` : ''}
            {storage.writable ? '' : ` · ${tr('NICHT beschreibbar')}`}
          </p>
        </div>

        <div className="panel meter">
          <div className="meter__top"><span className="silk">{tr('Platz frei')}</span>
            <span className="meter__val">{gb(storage.disk_free)} GB</span></div>
          <div className="meter__bar">
            <div className="meter__fill" data-tone={usedPct > 85 ? 'caution' : undefined}
              style={{ width: `${usedPct}%` }} />
          </div>
          <p className="meter__note">{tr('von {n} GB', { n: gb(storage.disk_total, 0) })}</p>
        </div>

        <div className="panel meter">
          <div className="meter__top"><span className="silk">{tr('Belegt durch Sicherungen')}</span>
            <span className="meter__val">{size(storage.used_by_backups)}</span></div>
          <p className="meter__note">
            {tr('{n} gültige Sicherungen', { n: list.filter((b) => b.status === 'ok').length })}
          </p>
        </div>
      </div>

      {!storage.is_network && (
        <p className="note-info" style={{ marginBottom: 20 }}>
          {tr('Die Sicherungen liegen auf der lokalen Platte. Für ein Netzlaufwerk genügt es, ein NFS unter')}{' '}
          <code className="data">{storage.path}</code>{' '}
          {tr('einzuhängen — an OTA ändert sich dabei nichts, es sieht weiterhin nur diesen einen Pfad.')}
        </p>
      )}

      {/* Zeitplan */}
      <div className="section__head"><span className="silk">{tr('Zeitplan')}</span><span className="section__rule" /></div>
      <div className="panel" style={{ padding: '18px 20px', marginBottom: 22 }}>
        <Toggle on={policy.is_enabled} name={tr('Automatisch sichern')}
          note={policy.is_enabled
            ? tr('Täglich um {time} Uhr', {
                time: `${String(policy.hour).padStart(2, '0')}:${String(policy.minute).padStart(2, '0')}`,
              }) + (policy.weekdays.length
                ? ' ' + tr('an {days}', { days: policy.weekdays.map((d) => tr(WEEKDAYS[d])).join(', ') })
                : '')
            : tr('Es wird nur gesichert, wenn du es von Hand anstösst.')}
          onChange={(v) => void savePolicy({ ...policy, is_enabled: v })} />

        {policy.is_enabled && (
          <div style={{ marginTop: 18 }}>
            <Field label={tr('Uhrzeit')} hint={tr('Ortszeit des Servers. Am besten dann, wenn niemand arbeitet.')}>
              <div className="row-item" style={{ maxWidth: 200 }}>
                <input type="time" aria-label={tr('Uhrzeit')}
                  value={`${String(policy.hour).padStart(2, '0')}:${String(policy.minute).padStart(2, '0')}`}
                  onChange={(e) => {
                    const [h, m] = e.target.value.split(':').map(Number)
                    if (!Number.isNaN(h)) void savePolicy({ ...policy, hour: h, minute: m || 0 })
                  }} />
              </div>
            </Field>

            <Field label={tr('An welchen Tagen')} hint={tr('Nichts ausgewählt bedeutet: jeden Tag.')}>
              <div className="chips">
                {WEEKDAYS.map((day, i) => {
                  const on = policy.weekdays.includes(i)
                  return (
                    <button key={day} type="button" aria-pressed={on}
                      className={`chip${on ? ' is-on' : ''}`}
                      onClick={() => void savePolicy({
                        ...policy,
                        weekdays: on ? policy.weekdays.filter((d) => d !== i)
                                     : [...policy.weekdays, i].sort(),
                      })}>{tr(day)}</button>
                  )
                })}
              </div>
            </Field>

            <Field label={tr('Was gesichert wird')}>
              <Toggle on={policy.include_profiles} name={tr('Profile der Nutzer')}
                note={tr('Das Home mit Projekten, Einstellungen und Schlüsseln. Der eigentliche Wert.')}
                onChange={(v) => void savePolicy({ ...policy, include_profiles: v })} />
              <Toggle on={policy.include_containers} name={tr('Änderungen in den Containern')}
                note={tr('Nur was ausserhalb des Home verändert wurde. Meist aus dem Golden Image reproduzierbar.')}
                onChange={(v) => void savePolicy({ ...policy, include_containers: v })} />
              <Toggle on={policy.include_database} name={tr('Datenbank')}
                note={tr('Nutzer, Gruppen, Workspaces, Zuweisungen und das Audit-Log. Klein und schnell.')}
                onChange={(v) => void savePolicy({ ...policy, include_database: v })} />
            </Field>

            <Field label={tr('Wie viele tägliche Stände bleiben')}
              hint={tr('Ältere werden nach dem Lauf entfernt.')}>
              <CapacityFader aria-label={tr('Tägliche Stände')}
                value={policy.keep_daily} min={1} max={30} step={1}
                format={(v) => String(v)} unit={tr('Stände')}
                ticks={[1, 7, 14, 21, 30]} tickLabel={(t) => String(t)}
                onChange={(v) => void savePolicy({ ...policy, keep_daily: v })} />
            </Field>

            <Field label={tr('Zusätzliche wöchentliche Stände')}
              hint={tr('Aus den älteren wird je Kalenderwoche der neueste behalten.')}>
              <CapacityFader aria-label={tr('Wöchentliche Stände')}
                value={policy.keep_weekly} min={0} max={26} step={1}
                format={(v) => String(v)} unit={tr('Wochen')}
                ticks={[0, 4, 8, 16, 26]} tickLabel={(t) => String(t)}
                onChange={(v) => void savePolicy({ ...policy, keep_weekly: v })} />
            </Field>
          </div>
        )}

        {policy.last_run_at && (
          <p className="field__hint" style={{ marginTop: 14 }}>
            {tr('Zuletzt gelaufen {when}', { when: ago(new Date(policy.last_run_at).getTime()) })}
            {policy.last_result ? ` — ${tr(policy.last_result)}` : ''}
          </p>
        )}
      </div>

      {/* Sicherungen */}
      <div className="section__head">
        <span className="silk">{tr('Vorhandene Sicherungen')}</span>
        <span className="section__rule" />
        <button className="btn btn--sm" disabled={busy === 'db'}
          onClick={() => void runDatabase()}>
          {busy === 'db' ? tr('Läuft…') : tr('Nur Datenbank')}
        </button>
        <button className="btn btn--sm btn--primary" disabled={busy === 'all'}
          onClick={() => void runAll()}>
          {busy === 'all' ? tr('Läuft…') : tr('Jetzt alle sichern')}
        </button>
      </div>

      {list.length === 0 ? (
        <div className="empty">
          <p className="empty__title">{tr('Noch nichts gesichert')}</p>
          <p className="empty__body">
            {tr('Stosse eine Sicherung von Hand an oder schalte den Zeitplan ein.')}
          </p>
        </div>
      ) : (
        <div className="panel" style={{ padding: '14px 0 0' }}>
          <table className="tbl">
            <thead>
              <tr>
                <th style={{ paddingLeft: 20 }}>{tr('Zeitpunkt')}</th>
                <th>{tr('Nutzer')}</th>
                <th>{tr('Art')}</th>
                <th>{tr('Grösse')}</th>
                <th>{tr('Ausgelöst')}</th>
                <th>{tr('Status')}</th>
                <th />
              </tr>
            </thead>
            <tbody>
              {list.map((b) => (
                <tr key={b.id} style={{ cursor: 'default' }}>
                  <td style={{ paddingLeft: 20 }} className="data">
                    {new Date(b.started_at).toLocaleString(getLang() === 'de' ? 'de-DE' : 'en-GB', {
                      day: '2-digit', month: '2-digit',
                      hour: '2-digit', minute: '2-digit',
                    })}
                  </td>
                  <td style={{ fontWeight: 500 }}>{b.username ?? '—'}</td>
                  <td style={{ color: 'var(--label)' }}>{tr(KIND_TEXT[b.kind] ?? b.kind)}</td>
                  <td className="data" style={{ color: 'var(--label)' }}>
                    {b.status === 'ok' ? size(b.size_bytes) : '—'}
                    {b.file_count > 0 && (
                      <span className="silk" style={{ marginLeft: 8 }}>{tr('{n} Dateien', { n: b.file_count })}</span>
                    )}
                  </td>
                  <td style={{ color: 'var(--mute)', fontSize: 12 }}>
                    {tr(TRIGGER_TEXT[b.trigger] ?? b.trigger)}
                    {b.actor ? ` · ${b.actor}` : ''}
                  </td>
                  <td>
                    <BackupStatus status={b.status} />
                    {b.error && (
                      <div style={{ fontSize: 11, color: 'var(--halt)', marginTop: 3, maxWidth: 300 }}>
                        {b.error}
                      </div>
                    )}
                  </td>
                  <td style={{ textAlign: 'right', paddingRight: 20, whiteSpace: 'nowrap' }}>
                    {b.status === 'ok' && b.kind === 'profile' && (
                      <button className="btn btn--sm" disabled={busy === b.id}
                        onClick={() => setConfirm(b)}>{tr('Wiederherstellen')}</button>
                    )}
                    {b.status === 'ok' && b.kind === 'container' && b.size_bytes > 0 && (
                      <button className="btn btn--sm" disabled={busy === b.id}
                        title={tr('Legt die Dateien in den laufenden Arbeitsplatz zurück')}
                        onClick={() => void restoreIntoSession(b)}>{tr('In Session zurückspielen')}</button>
                    )}
                    {b.status === 'ok' && b.kind === 'database' && (
                      <button className="btn btn--sm" disabled={busy === b.id}
                        onClick={() => setDbHint(b)}>{tr('Wiederherstellen')}</button>
                    )}
                    <button className="btn btn--sm btn--ghost" disabled={busy === b.id}
                      style={{ marginLeft: 6 }}
                      aria-label={tr('Sicherung löschen')}
                      onClick={() => void remove(b)}>✕</button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {/* Datenbank: bewusst kein Knopf, sondern eine Anleitung */}
      {dbHint && (
        <>
          <div className="scrim" onClick={() => setDbHint(null)} />
          <div className="drawer" style={{ width: 'min(560px, 100vw)' }} role="dialog" aria-modal="true">
            <header className="drawer__head">
              <div>
                <h2 className="h-card">{tr('Datenbank wiederherstellen')}</h2>
                <p className="sub" style={{ marginTop: 4 }}>
                  {new Date(dbHint.started_at).toLocaleString(getLang() === 'de' ? 'de-DE' : 'en-GB')}
                </p>
              </div>
            </header>
            <div className="drawer__body">
              <p className="note-info" style={{ marginBottom: 16 }}>
                {tr('Das geht bewusst nicht per Knopfdruck. Die Datenbank trägt die Anmeldung, mit der du gerade hier stehst — sie unter der laufenden Anwendung auszutauschen bricht jede offene Verbindung mittendrin.')}
              </p>
              <p className="sub" style={{ marginBottom: 12 }}>
                {tr('Auf dem Server ausführen. Das Skript legt vorher eine Sicherheitskopie an, hält API und Agent an, spielt zurück und startet beides wieder:')}
              </p>
              <pre className="viewer__clip" style={{ minHeight: 0, whiteSpace: 'pre-wrap' }}>
{`cd /opt/openterminalapps
./scripts/restore-db.sh \\
  ${dbHint.path}`}
              </pre>
              <p className="field__hint">
                {tr('Profile auf der Platte sind davon nicht betroffen. Nach der Wiederherstellung müssen sich alle neu anmelden.')}
              </p>
            </div>
            <footer className="drawer__foot">
              <button className="btn" onClick={() => setDbHint(null)}>{tr('Verstanden')}</button>
            </footer>
          </div>
        </>
      )}

      {/* Bestätigung: nennt die Folgen konkret, statt nur zu fragen */}
      {confirm && (
        <>
          <div className="scrim" onClick={() => setConfirm(null)} />
          <div className="drawer" style={{ width: 'min(500px, 100vw)' }} role="dialog" aria-modal="true">
            <header className="drawer__head">
              <div>
                <h2 className="h-card">{tr('Profil wiederherstellen')}</h2>
                <p className="sub" style={{ marginTop: 4 }}>{confirm.username}</p>
              </div>
            </header>
            <div className="drawer__body">
              <p className="note-warn" style={{ marginBottom: 16 }}>
                {tr('Das aktuelle Profil von')} <b>{confirm.username}</b> {tr('wird durch den Stand vom')}{' '}
                <b>{new Date(confirm.started_at).toLocaleString(getLang() === 'de' ? 'de-DE' : 'en-GB')}</b>{' '}
                {tr('ersetzt. Alles, was seitdem entstanden ist, verschwindet aus dem Arbeitsplatz.')}
              </p>
              <p className="sub">
                {tr('Der bisherige Stand wird nicht gelöscht, sondern daneben aufgehoben — falls die Wiederherstellung doch nicht das Richtige war, lässt er sich zurückholen.')}
              </p>
              <p className="sub" style={{ marginTop: 12 }}>
                {tr('Laufende Sessions des Nutzers müssen vorher beendet sein.')}
              </p>
            </div>
            <footer className="drawer__foot">
              <button className="btn btn--ghost" onClick={() => setConfirm(null)}>{tr('Abbrechen')}</button>
              <button className="btn btn--primary" disabled={busy === confirm.id}
                onClick={() => void restore(confirm)}>
                {busy === confirm.id ? tr('Läuft…') : tr('Wiederherstellen')}
              </button>
            </footer>
          </div>
        </>
      )}
    </>
  )
}
