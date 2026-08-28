import { useCallback, useEffect, useState } from 'react'
import { Field, Segmented, Toggle } from './controls'
import { ApiError, api, type KcVerzeichnisIn } from '../lib/api'
import { t as tr } from '../lib/i18n'

/**
 * Ein Active Directory anbinden — in OTA, nicht in der Keycloak-Konsole.
 *
 * Das ist der eigentliche Gewinn des Umbaus (auth-roadmap.md, Etappe C):
 * Keycloak führt die Identitäten, aber eine Administration muss es dafür
 * nicht öffnen.
 *
 * Der Aufbau folgt der Reihenfolge, in der man das wirklich tut: eintragen,
 * **prüfen**, speichern, einmal abgleichen. Der Prüf-Knopf steht bewusst vor
 * dem Speichern — an dieser Einstellung hängt, wer sich morgen anmelden kann.
 *
 * Das Kennwort geht nur hinein. Leer heisst „nicht anfassen": Sonst verlöre
 * eine Änderung an der Adresse nebenbei die Zugangsdaten, und das fiele erst
 * bei der nächsten Anmeldung auf.
 */
const LEER: KcVerzeichnisIn = {
  server_uri: '', base_dn: '', bind_dn: '', bind_password: '',
  user_filter: '', login_attribute: '', kind: 'ad', is_enabled: true,
}

export function KcVerzeichnis({ onToast }: {
  onToast: (m: string, tone?: 'ok' | 'bad') => void
}) {
  const [entwurf, setEntwurf] = useState<KcVerzeichnisIn>(LEER)
  const [gespeichert, setGespeichert] = useState(false)
  const [hatKennwort, setHatKennwort] = useState(false)
  const [pruefung, setPruefung] = useState<
    { verbindung: boolean; anmeldung: boolean; hinweise: string[] } | null>(null)
  const [busy, setBusy] = useState<string | null>(null)

  const laden = useCallback(async () => {
    try {
      const d = await api.kcVerzeichnis()
      setGespeichert(d.eingerichtet)
      setHatKennwort(Boolean(d.hat_kennwort))
      if (d.eingerichtet) {
        setEntwurf({
          server_uri: d.server_uri ?? '', base_dn: d.base_dn ?? '',
          bind_dn: d.bind_dn ?? '', bind_password: '',
          user_filter: d.user_filter ?? '', login_attribute: d.login_attribute ?? '',
          kind: d.kind === 'ad' ? 'ad' : 'other', is_enabled: d.is_enabled !== false,
        })
      }
    } catch { /* nicht eingerichtet oder Keycloak schweigt */ }
  }, [])

  useEffect(() => { void laden() }, [laden])

  const setz = <K extends keyof KcVerzeichnisIn>(k: K, v: KcVerzeichnisIn[K]) =>
    setEntwurf((e) => ({ ...e, [k]: v }))

  const bereit = entwurf.server_uri.length > 3 && entwurf.base_dn.length > 3

  async function tun(was: string, fn: () => Promise<unknown>, meldung: string) {
    setBusy(was)
    try {
      await fn()
      onToast(meldung)
      await laden()
    } catch (err) {
      onToast(err instanceof ApiError ? err.message : tr('Hat nicht geklappt'), 'bad')
    } finally {
      setBusy(null)
    }
  }

  return (
    <>
      <div className="section__head">
        <span className="silk">{tr('Verzeichnis in Keycloak')}</span>
        <span className="section__rule" />
        <span className="silk data">{gespeichert ? tr('eingerichtet') : tr('nicht eingerichtet')}</span>
      </div>

      <div className="panel" style={{ padding: '16px 20px', marginBottom: 18 }}>
        <p className="field__hint" style={{ marginTop: 0, marginBottom: 16 }}>
          {tr('Keycloak holt die Konten aus dem Verzeichnis. OTA schreibt nie hinein — was dort steht, wird gelesen, nicht geändert.')}
        </p>

        <Field label={tr('Art des Verzeichnisses')}
          hint={entwurf.kind === 'ad'
            ? tr('Anmeldename ist sAMAccountName, Kennung objectGUID.')
            : tr('Anmeldename ist uid, Kennung entryUUID.')}>
          <Segmented label={tr('Art')} value={entwurf.kind === 'ad' ? 'ad' : 'other'}
            options={[
              { value: 'ad' as const, label: tr('Active Directory') },
              { value: 'other' as const, label: tr('LDAP') },
            ]}
            onChange={(v) => setz('kind', v)} />
        </Field>

        <Field label={tr('Adresse')}
          hint={tr('ldaps://server:636 für eine verschlüsselte Verbindung, oder ldap://server:389.')}>
          <div className="row-item">
            <input value={entwurf.server_uri} placeholder="ldaps://dc01.firma.local:636"
              onChange={(e) => setz('server_uri', e.target.value)} />
          </div>
        </Field>

        <Field label={tr('Basis der Konten')} hint={tr('Wo die Personen liegen, nicht die Wurzel der Domäne.')}>
          <div className="row-item">
            <input value={entwurf.base_dn} placeholder="OU=Users,DC=firma,DC=local"
              onChange={(e) => setz('base_dn', e.target.value)} />
          </div>
        </Field>

        <Field label={tr('Dienstkonto')} hint={tr('Ein Konto, das lesen darf. Mehr braucht es nicht.')}>
          <div className="row-item">
            <input value={entwurf.bind_dn} placeholder="CN=svc-keycloak,OU=Dienste,DC=firma,DC=local"
              onChange={(e) => setz('bind_dn', e.target.value)} />
          </div>
        </Field>

        <Field label={tr('Kennwort des Dienstkontos')}
          hint={hatKennwort
            ? tr('Ein Kennwort ist hinterlegt. Leer lassen heisst: unverändert.')
            : tr('Wird gebraucht, um die Anbindung anzulegen.')}>
          <div className="row-item">
            <input type="password" value={entwurf.bind_password}
              placeholder={hatKennwort ? '••••••••' : ''}
              onChange={(e) => setz('bind_password', e.target.value)} />
          </div>
        </Field>

        <Field label={tr('Eingeschaltet')}
          hint={tr('Aus heisst: Die Anbindung bleibt stehen, aber niemand meldet sich darüber an.')}>
          <Toggle on={entwurf.is_enabled} name={tr('Konten aus dem Verzeichnis zulassen')}
            onChange={(v) => setz('is_enabled', v)} />
        </Field>

        {pruefung && (
          <div className={pruefung.anmeldung ? 'note-info' : 'note-warn'} style={{ marginTop: 12 }}>
            <p style={{ margin: 0 }}>
              {pruefung.verbindung ? tr('Der Server antwortet.') : tr('Der Server antwortet nicht.')}
              {' '}
              {pruefung.anmeldung ? tr('Das Dienstkonto kommt herein.') : ''}
            </p>
            {pruefung.hinweise.map((h, i) => <p key={i} style={{ margin: '6px 0 0' }}>{h}</p>)}
          </div>
        )}

        <div className="viewer__row" style={{ marginTop: 16 }}>
          <button className="btn" disabled={!bereit || busy !== null}
            onClick={() => void tun('test', async () => {
              setPruefung(await api.kcVerzeichnisTest(entwurf))
            }, tr('Geprüft.'))}>
            {busy === 'test' ? tr('Wird geprüft…') : tr('Verbindung testen')}
          </button>

          <button className="btn btn--primary" disabled={!bereit || busy !== null}
            onClick={() => void tun('speichern',
              () => api.kcVerzeichnisSetzen(entwurf), tr('Gespeichert.'))}>
            {tr('Speichern')}
          </button>

          {gespeichert && (
            <>
              <button className="btn" disabled={busy !== null}
                onClick={() => void tun('abgleich', async () => {
                  const r = await api.kcVerzeichnisAbgleich(true)
                  onToast(tr('{n} Konten geholt.', { n: r.added ?? 0 }))
                }, tr('Abgleich gelaufen.'))}>
                {busy === 'abgleich' ? tr('Wird abgeglichen…') : tr('Jetzt abgleichen')}
              </button>
              <button className="btn btn--halt" disabled={busy !== null}
                onClick={() => {
                  if (!window.confirm(tr('Die Anbindung entfernen? Konten, die daraus stammen, können sich danach nicht mehr anmelden.'))) return
                  void tun('weg', () => api.kcVerzeichnisWeg(), tr('Entfernt.'))
                }}>
                {tr('Entfernen')}
              </button>
            </>
          )}
        </div>
      </div>
    </>
  )
}
