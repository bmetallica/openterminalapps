import { useEffect, useState } from 'react'
import { CapacityFader, Field, Led, Segmented, Toggle } from '../components/controls'
import {
  ApiError, api,
  type Backup, type BackupPolicy, type BackupStorage,
} from '../lib/api'
import { ago, gb } from '../lib/format'

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

function mb(bytes: number): string {
  if (bytes >= 1024 ** 3) return `${gb(bytes)} GB`
  return `${(bytes / 1024 ** 2).toFixed(1).replace('.', ',')} MB`
}

export function Backups({ onToast }: { onToast: (m: string, tone?: 'ok' | 'bad') => void }) {
  const [list, setList] = useState<Backup[] | null>(null)
  const [storage, setStorage] = useState<BackupStorage | null>(null)
  const [policy, setPolicy] = useState<BackupPolicy | null>(null)
  const [busy, setBusy] = useState<string | null>(null)
  const [confirm, setConfirm] = useState<Backup | null>(null)
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
      onToast(err instanceof ApiError ? err.message : 'Sicherung fehlgeschlagen', 'bad')
    } finally {
      setBusy(null)
    }
  }

  async function savePolicy(next: BackupPolicy) {
    setPolicy(next)
    try {
      await api.saveBackupPolicy(next)
    } catch (err) {
      onToast(err instanceof ApiError ? err.message : 'Speichern fehlgeschlagen', 'bad')
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
      onToast(err instanceof ApiError ? err.message : 'Löschen fehlgeschlagen', 'bad')
    } finally {
      setBusy(null)
    }
  }

  if (failed) {
    return (
      <div className="empty">
        <p className="empty__title">Konnte nicht geladen werden</p>
        <p className="empty__body">{failed}</p>
        <button className="btn" onClick={() => void load()}>Erneut versuchen</button>
      </div>
    )
  }
  if (!list || !storage || !policy) return <p className="sub">Wird geladen…</p>

  const usedPct = ((storage.disk_total - storage.disk_free) / storage.disk_total) * 100

  return (
    <>
      {/* Ablage */}
      <div className="meters" style={{ marginBottom: 20 }}>
        <div className="panel meter">
          <div className="meter__top"><span className="silk">Ablage</span>
            <span className="meter__val" style={{ fontSize: 13 }}>
              {storage.is_network ? 'Netzlaufwerk' : 'lokale Platte'}
            </span></div>
          <p className="meter__note data" style={{ fontSize: 11 }}>{storage.path}</p>
          <p className="meter__note">
            {storage.fstype}{storage.source ? ` · ${storage.source}` : ''}
            {storage.writable ? '' : ' · NICHT beschreibbar'}
          </p>
        </div>

        <div className="panel meter">
          <div className="meter__top"><span className="silk">Platz frei</span>
            <span className="meter__val">{gb(storage.disk_free)} GB</span></div>
          <div className="meter__bar">
            <div className="meter__fill" data-tone={usedPct > 85 ? 'caution' : undefined}
              style={{ width: `${usedPct}%` }} />
          </div>
          <p className="meter__note">von {gb(storage.disk_total, 0)} GB</p>
        </div>

        <div className="panel meter">
          <div className="meter__top"><span className="silk">Belegt durch Sicherungen</span>
            <span className="meter__val">{mb(storage.used_by_backups)}</span></div>
          <p className="meter__note">{list.filter((b) => b.status === 'ok').length} gültige Sicherungen</p>
        </div>
      </div>

      {!storage.is_network && (
        <p className="note-info" style={{ marginBottom: 20 }}>
          Die Sicherungen liegen auf der lokalen Platte. Für ein Netzlaufwerk genügt es,
          ein NFS unter <code className="data">{storage.path}</code> einzuhängen — an OTA
          ändert sich dabei nichts, es sieht weiterhin nur diesen einen Pfad.
        </p>
      )}

      {/* Zeitplan */}
      <div className="section__head"><span className="silk">Zeitplan</span><span className="section__rule" /></div>
      <div className="panel" style={{ padding: '18px 20px', marginBottom: 22 }}>
        <Toggle on={policy.is_enabled} name="Automatisch sichern"
          note={policy.is_enabled
            ? `Täglich um ${String(policy.hour).padStart(2, '0')}:${String(policy.minute).padStart(2, '0')} Uhr` +
              (policy.weekdays.length ? ` an ${policy.weekdays.map((d) => WEEKDAYS[d]).join(', ')}` : '')
            : 'Es wird nur gesichert, wenn du es von Hand anstösst.'}
          onChange={(v) => void savePolicy({ ...policy, is_enabled: v })} />

        {policy.is_enabled && (
          <div style={{ marginTop: 18 }}>
            <Field label="Uhrzeit" hint="Ortszeit des Servers. Am besten dann, wenn niemand arbeitet.">
              <div className="row-item" style={{ maxWidth: 200 }}>
                <input type="time" aria-label="Uhrzeit"
                  value={`${String(policy.hour).padStart(2, '0')}:${String(policy.minute).padStart(2, '0')}`}
                  onChange={(e) => {
                    const [h, m] = e.target.value.split(':').map(Number)
                    if (!Number.isNaN(h)) void savePolicy({ ...policy, hour: h, minute: m || 0 })
                  }} />
              </div>
            </Field>

            <Field label="An welchen Tagen" hint="Nichts ausgewählt bedeutet: jeden Tag.">
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
                      })}>{day}</button>
                  )
                })}
              </div>
            </Field>

            <Field label="Was gesichert wird">
              <Toggle on={policy.include_profiles} name="Profile der Nutzer"
                note="Das Home mit Projekten, Einstellungen und Schlüsseln. Der eigentliche Wert."
                onChange={(v) => void savePolicy({ ...policy, include_profiles: v })} />
              <Toggle on={policy.include_containers} name="Änderungen in den Containern"
                note="Nur was ausserhalb des Home verändert wurde. Meist aus dem Golden Image reproduzierbar."
                onChange={(v) => void savePolicy({ ...policy, include_containers: v })} />
            </Field>

            <Field label="Wie viele tägliche Stände bleiben"
              hint="Ältere werden nach dem Lauf entfernt.">
              <CapacityFader aria-label="Tägliche Stände"
                value={policy.keep_daily} min={1} max={30} step={1}
                format={(v) => String(v)} unit="Stände"
                ticks={[1, 7, 14, 21, 30]} tickLabel={(t) => String(t)}
                onChange={(v) => void savePolicy({ ...policy, keep_daily: v })} />
            </Field>

            <Field label="Zusätzliche wöchentliche Stände"
              hint="Aus den älteren wird je Kalenderwoche der neueste behalten.">
              <CapacityFader aria-label="Wöchentliche Stände"
                value={policy.keep_weekly} min={0} max={26} step={1}
                format={(v) => String(v)} unit="Wochen"
                ticks={[0, 4, 8, 16, 26]} tickLabel={(t) => String(t)}
                onChange={(v) => void savePolicy({ ...policy, keep_weekly: v })} />
            </Field>
          </div>
        )}

        {policy.last_run_at && (
          <p className="field__hint" style={{ marginTop: 14 }}>
            Zuletzt gelaufen {ago(new Date(policy.last_run_at).getTime())}
            {policy.last_result ? ` — ${policy.last_result}` : ''}
          </p>
        )}
      </div>

      {/* Sicherungen */}
      <div className="section__head">
        <span className="silk">Vorhandene Sicherungen</span>
        <span className="section__rule" />
        <button className="btn btn--sm btn--primary" disabled={busy === 'all'}
          onClick={() => void runAll()}>
          {busy === 'all' ? 'Läuft…' : 'Jetzt alle sichern'}
        </button>
      </div>

      {list.length === 0 ? (
        <div className="empty">
          <p className="empty__title">Noch nichts gesichert</p>
          <p className="empty__body">
            Stosse eine Sicherung von Hand an oder schalte den Zeitplan ein.
          </p>
        </div>
      ) : (
        <div className="panel" style={{ padding: '14px 0 0' }}>
          <table className="tbl">
            <thead>
              <tr>
                <th style={{ paddingLeft: 20 }}>Zeitpunkt</th>
                <th>Nutzer</th>
                <th>Art</th>
                <th>Grösse</th>
                <th>Ausgelöst</th>
                <th>Status</th>
                <th />
              </tr>
            </thead>
            <tbody>
              {list.map((b) => (
                <tr key={b.id} style={{ cursor: 'default' }}>
                  <td style={{ paddingLeft: 20 }} className="data">
                    {new Date(b.started_at).toLocaleString('de-DE', {
                      day: '2-digit', month: '2-digit',
                      hour: '2-digit', minute: '2-digit',
                    })}
                  </td>
                  <td style={{ fontWeight: 500 }}>{b.username ?? '—'}</td>
                  <td style={{ color: 'var(--label)' }}>{KIND_TEXT[b.kind] ?? b.kind}</td>
                  <td className="data" style={{ color: 'var(--label)' }}>
                    {b.status === 'ok' ? `${mb(b.size_bytes)}` : '—'}
                    {b.file_count > 0 && (
                      <span className="silk" style={{ marginLeft: 8 }}>{b.file_count} Dateien</span>
                    )}
                  </td>
                  <td style={{ color: 'var(--mute)', fontSize: 12 }}>
                    {TRIGGER_TEXT[b.trigger] ?? b.trigger}
                    {b.actor ? ` · ${b.actor}` : ''}
                  </td>
                  <td>
                    <Led status={b.status === 'ok' ? 'running'
                      : b.status === 'failed' ? 'failed' : 'starting'} />
                    {b.error && (
                      <div style={{ fontSize: 11, color: 'var(--halt)', marginTop: 3, maxWidth: 300 }}>
                        {b.error}
                      </div>
                    )}
                  </td>
                  <td style={{ textAlign: 'right', paddingRight: 20, whiteSpace: 'nowrap' }}>
                    {b.status === 'ok' && b.kind === 'profile' && (
                      <button className="btn btn--sm" disabled={busy === b.id}
                        onClick={() => setConfirm(b)}>Wiederherstellen</button>
                    )}
                    <button className="btn btn--sm btn--ghost" disabled={busy === b.id}
                      style={{ marginLeft: 6 }}
                      aria-label="Sicherung löschen"
                      onClick={() => void remove(b)}>✕</button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {/* Bestätigung: nennt die Folgen konkret, statt nur zu fragen */}
      {confirm && (
        <>
          <div className="scrim" onClick={() => setConfirm(null)} />
          <div className="drawer" style={{ width: 'min(500px, 100vw)' }} role="dialog" aria-modal="true">
            <header className="drawer__head">
              <div>
                <h2 className="h-card">Profil wiederherstellen</h2>
                <p className="sub" style={{ marginTop: 4 }}>{confirm.username}</p>
              </div>
            </header>
            <div className="drawer__body">
              <p className="note-warn" style={{ marginBottom: 16 }}>
                Das aktuelle Profil von <b>{confirm.username}</b> wird durch den Stand vom{' '}
                <b>{new Date(confirm.started_at).toLocaleString('de-DE')}</b> ersetzt.
                Alles, was seitdem entstanden ist, verschwindet aus dem Arbeitsplatz.
              </p>
              <p className="sub">
                Der bisherige Stand wird nicht gelöscht, sondern daneben aufgehoben — falls
                die Wiederherstellung doch nicht das Richtige war, lässt er sich zurückholen.
              </p>
              <p className="sub" style={{ marginTop: 12 }}>
                Laufende Sessions des Nutzers müssen vorher beendet sein.
              </p>
            </div>
            <footer className="drawer__foot">
              <button className="btn btn--ghost" onClick={() => setConfirm(null)}>Abbrechen</button>
              <button className="btn btn--primary" disabled={busy === confirm.id}
                onClick={() => void restore(confirm)}>
                {busy === confirm.id ? 'Läuft…' : 'Wiederherstellen'}
              </button>
            </footer>
          </div>
        </>
      )}
    </>
  )
}
