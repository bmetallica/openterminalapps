import { useCallback, useEffect, useState } from 'react'
import { Field, Segmented, Toggle } from './controls'
import { ApiError, api, type SyslogEinstellungen as Einst, type SyslogStand, type SyslogTest } from '../lib/api'
import { t as tr } from '../lib/i18n'

/**
 * Einstellungen → Protokoll an Syslog (Handbuch Kapitel 11).
 *
 * Jeder Protokolleintrag geht zusätzlich an einen Syslog-Server (RFC 5424,
 * UDP, TCP oder TLS). Was nicht ankommt, bleibt in der Tabelle und geht beim
 * nächsten Versuch mit. Die Felder werden erst mit „Speichern“ wirksam;
 * „Testen“ prüft die Werte im Formular, auch ungespeichert.
 */
export function SyslogEinstellungen({ onToast }: { onToast: (m: string, tone?: 'ok' | 'bad') => void }) {
  const [stand, setStand] = useState<SyslogStand | null>(null)
  const [form, setForm] = useState<Einst | null>(null)
  const [test, setTest] = useState<SyslogTest | null>(null)
  const [busy, setBusy] = useState<string | null>(null)

  const laden = useCallback(async () => {
    try {
      const s = await api.syslog()
      setStand(s)
      setForm((f) => f ?? s)
    } catch { setStand(null) }
  }, [])
  useEffect(() => {
    void laden()
    const t = window.setInterval(() => void laden(), 15_000)
    return () => window.clearInterval(t)
  }, [laden])

  if (!stand || !form) return <p className="sub">{tr('Wird geladen…')}</p>

  const felder: (keyof Einst)[] = ['host', 'port', 'protokoll', 'rahmung', 'ca', 'facility', 'absender', 'umfang']
  const geaendert = felder.some((k) => String(form[k]) !== String(stand[k]))
  const setze = (patch: Partial<Einst>) => { setForm({ ...form, ...patch }); setTest(null) }

  async function speichern(patch: Partial<Einst>, note: string) {
    setBusy('speichern')
    try {
      const s = await api.syslogEinstellen(patch)
      setStand(s)
      setForm(s)
      onToast(note)
    } catch (err) {
      onToast(err instanceof ApiError ? err.message : tr('Speichern fehlgeschlagen'), 'bad')
    } finally {
      setBusy(null)
    }
  }

  async function testen() {
    if (!form) return
    setBusy('test'); setTest(null)
    try {
      setTest(await api.syslogTest(form))
    } catch (err) {
      onToast(err instanceof ApiError ? err.message : tr('Hat nicht geklappt'), 'bad')
    } finally {
      setBusy(null)
    }
  }

  const { lage } = stand
  return (
    <div className="panel" style={{ padding: '16px 20px' }}>
      <p className="field__hint" style={{ marginTop: 0, marginBottom: 14 }}>
        {tr('Jeder Eintrag im Protokoll von OTA geht zusätzlich an einen Syslog-Server, im Format RFC 5424. So bleibt eine Kopie an einem Ort, den die Administratoren von OTA nicht verwalten, und eine nachträgliche Änderung in der Datenbank fällt auf. Was nicht ankommt, geht beim nächsten Versuch mit, auch nach einem Ausfall.')}
      </p>

      <Field label={tr('Protokoll an Syslog')}>
        <Toggle on={stand.an} name={stand.an ? tr('Eingeschaltet') : tr('Ausgeschaltet')}
          note={stand.an ? tr('Gesendet wird ab dem Zeitpunkt des Einschaltens, nicht das bisherige Protokoll.') : undefined}
          onChange={(v) => {
            if (busy) return
            if (v && !form.host.trim()) { onToast(tr('Erst einen Syslog-Server eintragen.'), 'bad'); return }
            void speichern(v ? { ...form, an: true } : { an: false },
              v ? tr('Das Protokoll geht jetzt auch an {h}.', { h: form.host }) : tr('Protokoll an Syslog ist ausgeschaltet.'))
          }} />
      </Field>

      <Field label={tr('Server')} hint={tr('Name oder Adresse des Syslog-Servers, ohne Schema. Port meist 514 (UDP, TCP) oder 6514 (TLS).')}>
        <div className="viewer__row" style={{ gap: 10, flexWrap: 'wrap' }}>
          <input className="input" style={{ flex: '1 1 220px' }} value={form.host} aria-label={tr('Server')}
            placeholder="syslog.firma.de" onChange={(e) => setze({ host: e.target.value })} />
          <div className="numfield">
            <input type="number" min={1} max={65535} aria-label={tr('Port')} value={form.port}
              onChange={(e) => setze({ port: Number(e.target.value) })} />
            <span className="numfield__unit">{tr('Port')}</span>
          </div>
        </div>
      </Field>

      <Field label={tr('Übertragung')}
        hint={tr('TLS verschlüsselt und prüft den Server; empfohlen, sobald das Protokoll über ein fremdes Netz geht. UDP kennt keine Bestätigung: Ein Eintrag, der unterwegs verloren geht, fällt niemandem auf.')}>
        <Segmented label={tr('Übertragung')} value={form.protokoll}
          options={[
            { value: 'udp', label: 'UDP' },
            { value: 'tcp', label: 'TCP' },
            { value: 'tls', label: 'TLS' },
          ]}
          onChange={(v) => setze({ protokoll: v, port: v === 'tls' && form.port === 514 ? 6514 : v !== 'tls' && form.port === 6514 ? 514 : form.port })} />
      </Field>

      {form.protokoll === 'tcp' && (
        <Field label={tr('Rahmung')}
          hint={tr('Wie der Server eine Nachricht von der nächsten trennt. Mit Länge (RFC 6587, Octet Counting) ist die Regel bei rsyslog und syslog-ng; ein Zeilenumbruch für Empfänger, die nur das können.')}>
          <Segmented label={tr('Rahmung')} value={form.rahmung}
            options={[
              { value: 'laenge', label: tr('Mit Länge') },
              { value: 'zeilenumbruch', label: tr('Zeilenumbruch') },
            ]}
            onChange={(v) => setze({ rahmung: v })} />
        </Field>
      )}

      {form.protokoll === 'tls' && (
        <Field label={tr('CA-Zertifikat')}
          hint={tr('Die Zertifizierungsstelle, die das Zertifikat des Syslog-Servers ausgestellt hat, im PEM-Format. Leer: die üblichen öffentlichen Zertifizierungsstellen.')}>
          <textarea className="input" rows={4} style={{ width: '100%', fontFamily: 'var(--mono, monospace)', fontSize: 12 }}
            value={form.ca} aria-label={tr('CA-Zertifikat')} placeholder="-----BEGIN CERTIFICATE-----"
            onChange={(e) => setze({ ca: e.target.value })} />
        </Field>
      )}

      <Field label={tr('Umfang')}
        hint={tr('Ohne Alltag: erfolgreiche Anmeldungen und Beginn und Ende von Sitzungen bleiben in OTA. Sie sagen viel über die Arbeitszeit eines Menschen und wenig über Angriffe. Gescheiterte Anmeldungen und alle Verwaltungsvorgänge gehen mit.')}>
        <Segmented label={tr('Umfang')} value={form.umfang}
          options={[
            { value: 'ohne_alltag', label: tr('Ohne Alltag') },
            { value: 'alle', label: tr('Alles') },
          ]}
          onChange={(v) => setze({ umfang: v })} />
      </Field>

      <Field label={tr('Facility und Absender')}
        hint={tr('Unter welcher Facility die Einträge ankommen und welcher Name als Absender (HOSTNAME) darin steht. Die Anwendung heißt immer „ota“.')}>
        <div className="viewer__row" style={{ gap: 10, flexWrap: 'wrap' }}>
          <select value={form.facility} aria-label={tr('Facility')} onChange={(e) => setze({ facility: e.target.value })}>
            {stand.facilities.map((f) => <option key={f} value={f}>{f}</option>)}
          </select>
          <input className="input" style={{ flex: '1 1 160px' }} value={form.absender} aria-label={tr('Absender')}
            onChange={(e) => setze({ absender: e.target.value })} />
        </div>
      </Field>

      <div className="viewer__row" style={{ gap: 10, flexWrap: 'wrap', marginBottom: 12 }}>
        <button className="btn" disabled={busy !== null || !form.host.trim()} onClick={() => void testen()}>
          {busy === 'test' ? tr('Wird gesendet…') : tr('Testnachricht senden')}
        </button>
        {geaendert && (
          <button className="btn btn--primary" disabled={busy !== null}
            onClick={() => void speichern(form, tr('Gespeichert.'))}>
            {busy === 'speichern' ? tr('Wird gespeichert…') : tr('Speichern')}
          </button>
        )}
      </div>

      {test && (
        <div className={test.ok ? 'note-info' : 'note-warn'} style={{ marginBottom: 12 }}>
          {test.ok
            ? (test.udp
              ? tr('Gesendet in {ms} ms. UDP bestätigt nichts: Ob sie ankam, zeigt nur der Syslog-Server.', { ms: test.ms })
              : tr('Der Server hat die Testnachricht angenommen ({ms} ms).', { ms: test.ms }))
            : tr('Nicht gesendet: {f}', { f: test.fehler ?? '' })}
        </div>
      )}

      {stand.an && (
        <div className={lage.fehler ? 'note-warn' : 'note-info'}>
          {lage.fehler
            ? tr('Zurzeit nicht erreichbar: {f}. Noch nicht gesendet: {n} Einträge; sie gehen mit, sobald der Server wieder antwortet.', { f: lage.fehler, n: stand.rueckstand })
            : tr('Seit dem Start der API gesendet: {n}. Zuletzt: {z}. Noch nicht gesendet: {r}.', {
              n: lage.gesendet,
              z: lage.zuletzt ? new Date(lage.zuletzt).toLocaleString() : tr('noch nichts'),
              r: stand.rueckstand,
            })}
        </div>
      )}
    </div>
  )
}
