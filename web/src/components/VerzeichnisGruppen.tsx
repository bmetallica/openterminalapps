import { useCallback, useEffect, useState } from 'react'
import { Field, Segmented } from './controls'
import {
  ApiError, api,
  type VerzeichnisAbgleich, type VerzeichnisGruppen as Gruppen,
} from '../lib/api'
import { ago } from '../lib/format'
import { t as tr } from '../lib/i18n'

/**
 * Gruppen aus dem Verzeichnis, ihr Abgleich, und was ein Konto ohne Gruppe
 * liest (Handbuch Kapitel 08).
 *
 * Gekoppelt wird an der **OTA-Gruppe** (Nutzer und Gruppen → Gruppe). Hier
 * steht nur, woher die Gruppen kommen und wie oft nachgesehen wird.
 */
const formen = () => [
  { value: 'auto', label: tr('Automatisch') },
  { value: 'groupOfNames', label: 'groupOfNames' },
  { value: 'groupOfUniqueNames', label: 'groupOfUniqueNames' },
  { value: 'posixGroup', label: 'posixGroup' },
]

function taktName(min: number): string {
  if (min === 0) return tr('aus')
  if (min < 60) return tr('{n} Min.', { n: min })
  if (min < 1440) return tr('{n} Std.', { n: min / 60 })
  return tr('1 Tag')
}

export function abgleichSatz(a: VerzeichnisAbgleich): string {
  if (!a.ok) return a.fehler ?? tr('Gescheitert')
  const teile = Object.entries(a.gruppen ?? {})
    .map(([g, [dazu, weg]]) => `${g} ${dazu ? `+${dazu}` : ''}${dazu && weg ? ' ' : ''}${weg ? `−${weg}` : ''}`)
  if (a.deaktiviert?.length) teile.push(tr('{n} deaktiviert', { n: a.deaktiviert.length }))
  return teile.length ? teile.join(' · ') : tr('keine Änderung')
}

export function VerzeichnisGruppen({ onToast }: {
  onToast: (m: string, tone?: 'ok' | 'bad') => void
}) {
  const [stand, setStand] = useState<Gruppen | null>(null)
  const [dn, setDn] = useState('')
  const [form, setForm] = useState('auto')
  const [filter, setFilter] = useState('')
  const [takt, setTakt] = useState<{ intervall: number; stufen: number[]; letzter: VerzeichnisAbgleich | null } | null>(null)
  const [hinweis, setHinweis] = useState('')
  const [busy, setBusy] = useState<string | null>(null)

  const laden = useCallback(async () => {
    try {
      const g = await api.verzeichnisGruppen()
      setStand(g)
      if (g.eingerichtet) {
        setDn(g.gruppen_dn ?? ''); setForm(g.form ?? 'auto'); setFilter(g.filter ?? '')
      }
    } catch { setStand(null) }
    try { setTakt(await api.verzeichnisTakt()) } catch { /* Keycloak schweigt */ }
    try { setHinweis((await api.settings()).ohne_gruppe_hinweis ?? '') } catch { /* egal */ }
  }, [])
  useEffect(() => { void laden() }, [laden])

  async function tun(was: string, fn: () => Promise<string | void>) {
    setBusy(was)
    try {
      const meldung = await fn()
      if (meldung) onToast(meldung)
      await laden()
    } catch (err) {
      onToast(err instanceof ApiError ? err.message : tr('Hat nicht geklappt'), 'bad')
    } finally {
      setBusy(null)
    }
  }

  const letzter = takt?.letzter

  return (
    <>
      <div className="section__head">
        <span className="silk">{tr('Gruppen aus dem Verzeichnis')}</span>
        <span className="section__rule" />
        <span className="silk data">
          {stand?.eingerichtet ? tr('{n} Gruppen', { n: stand.gruppen.length }) : tr('nicht eingerichtet')}
        </span>
      </div>

      <div className="panel" style={{ padding: '16px 20px', marginBottom: 18 }}>
        <p className="field__hint" style={{ marginTop: 0, marginBottom: 16 }}>
          {tr('Keycloak liest die Gruppen aus dem Verzeichnis. In OTA wirken sie erst, wenn eine OTA-Gruppe daran gekoppelt ist (Nutzer und Gruppen → Gruppe → Mitglieder aus dem Verzeichnis). Eine Verzeichnisgruppe gibt von sich aus keine Rechte — auch nicht, wenn sie „admins“ heisst.')}
        </p>

        <Field label={tr('Basis der Gruppen')} hint={tr('Wo die Gruppen liegen, z. B. ou=groups,dc=firma,dc=de.')}>
          <div className="row-item">
            <input value={dn} placeholder="ou=groups,dc=firma,dc=de" aria-label={tr('Basis der Gruppen')}
              onChange={(e) => setDn(e.target.value)} />
          </div>
        </Field>

        <Field label={tr('Form')}
          hint={tr('Automatisch probiert alle drei und nimmt die erste, unter der Gruppen auftauchen. groupOfNames: Mitglieder als DN (member). posixGroup: Mitglieder als Anmeldename (memberUid).')}>
          <Segmented label={tr('Form')} value={form} options={formen()} onChange={setForm} />
        </Field>

        <Field label={tr('Filter')} hint={tr('Optional, in Klammern — z. B. (cn=ki-*), damit nur diese Gruppen erscheinen.')}>
          <div className="row-item">
            <input value={filter} placeholder="(cn=ota-*)" aria-label={tr('Filter')}
              onChange={(e) => setFilter(e.target.value)} />
          </div>
        </Field>

        {stand?.eingerichtet && (
          <div style={{ margin: '4px 0 12px' }}>
            <p className="silk" style={{ marginBottom: 6 }}>
              {tr('Gefunden ({form})', { form: stand.form ?? '' })}
            </p>
            {stand.gruppen.length ? (
              <div className="strip">
                {stand.gruppen.map((g) => <span key={g} className="chip is-on">{g}</span>)}
              </div>
            ) : (
              <p className="note-warn" style={{ margin: 0 }}>
                {tr('Unter dieser Basis wurden keine Gruppen gefunden. Stimmen Basis und Form? Darf das Dienstkonto dort lesen?')}
              </p>
            )}
          </div>
        )}

        <div className="viewer__row" style={{ marginTop: 8 }}>
          <button className="btn btn--primary" disabled={dn.trim().length < 3 || busy !== null}
            onClick={() => void tun('setzen', async () => {
              const r = await api.verzeichnisGruppenSetzen({ gruppen_dn: dn.trim(), form, filter })
              return tr('{n} Gruppen gefunden ({form}).', { n: r.gruppen.length, form: r.form ?? '' })
            })}>
            {busy === 'setzen' ? tr('Wird gelesen…') : tr('Speichern und Gruppen holen')}
          </button>
          {stand?.eingerichtet && (
            <button className="btn btn--halt" disabled={busy !== null}
              onClick={() => {
                if (!window.confirm(tr('Gruppen nicht mehr lesen? Gekoppelte OTA-Gruppen verlieren beim nächsten Abgleich alle Mitglieder, die nur über das Verzeichnis drin waren.'))) return
                void tun('weg', async () => { await api.verzeichnisGruppenWeg(); return tr('Entfernt.') })
              }}>
              {tr('Entfernen')}
            </button>
          )}
        </div>
      </div>

      <div className="section__head">
        <span className="silk">{tr('Abgleich')}</span>
        <span className="section__rule" />
        <span className="silk data">{takt ? taktName(takt.intervall) : '—'}</span>
      </div>

      <div className="panel" style={{ padding: '16px 20px', marginBottom: 18 }}>
        <p className="field__hint" style={{ marginTop: 0, marginBottom: 16 }}>
          {tr('Bei jeder Anmeldung gilt ohnehin der aktuelle Stand des Verzeichnisses. Der Abgleich zieht ihn auch für alle nach, die sich gerade nicht anmelden — und deaktiviert Konten, die im Verzeichnis fehlen (nie löschen).')}
        </p>
        {takt && (
          <Field label={tr('Wie oft')}>
            <Segmented label={tr('Wie oft')} value={String(takt.intervall)}
              options={takt.stufen.map((s) => ({ value: String(s), label: taktName(s) }))}
              onChange={(v) => void tun('takt', async () => {
                await api.verzeichnisTaktSetzen(Number(v))
                return tr('Gespeichert.')
              })} />
          </Field>
        )}

        {letzter && (
          <p className={letzter.ok ? 'field__hint' : 'note-warn'} style={{ margin: '4px 0 12px' }}>
            {tr('Letzter Abgleich')}: {letzter.zeit ? ago(new Date(letzter.zeit).getTime()) : '—'}
            {letzter.ok && <> · {tr('{n} Konten', { n: letzter.konten ?? 0 })}</>}
            {' · '}{abgleichSatz(letzter)}
          </p>
        )}

        <button className="btn" disabled={busy !== null}
          onClick={() => void tun('abgleich', async () => {
            const r = await api.verzeichnisAbgleichen()
            if (!r.ok) throw new ApiError(400, r.fehler ?? tr('Gescheitert'))
            return `${tr('Abgleich gelaufen')}: ${abgleichSatz(r)}`
          })}>
          {busy === 'abgleich' ? tr('Wird abgeglichen…') : tr('Jetzt abgleichen')}
        </button>
      </div>

      <div className="section__head">
        <span className="silk">{tr('Konten ohne Gruppe')}</span>
        <span className="section__rule" />
      </div>

      <div className="panel" style={{ padding: '16px 20px', marginBottom: 18 }}>
        <Field label={tr('Hinweis auf dem Dashboard')}
          hint={tr('Wer sich anmeldet und in keiner Gruppe ist, sieht ein leeres Dashboard mit diesem Text. In der Nutzerliste steht das Konto mit „ohne Gruppe“.')}>
          <textarea rows={3} value={hinweis} aria-label={tr('Hinweis auf dem Dashboard')}
            style={{ width: '100%' }} onChange={(e) => setHinweis(e.target.value)} />
        </Field>
        <button className="btn" disabled={busy !== null}
          onClick={() => void tun('hinweis', async () => {
            await api.saveSettings({ ohne_gruppe_hinweis: hinweis })
            return tr('Gespeichert.')
          })}>
          {tr('Hinweis speichern')}
        </button>
      </div>
    </>
  )
}
