import { useCallback, useEffect, useState } from 'react'
import { ChipSelect, Field, Toggle } from './controls'
import { ApiError, api, type GitStand, type Group } from '../lib/api'
import { t as tr } from '../lib/i18n'
import { GitGeheimnisseEinstellungen } from './GitGeheimnisseEinstellungen'

/**
 * Einstellungen → Git (Handbuch Kapitel 27).
 *
 * OTA-Git ist eine Forgejo-Instanz, die zu OTA gehört: Anmeldung über
 * Keycloak, Konten legt OTA an, und berechtigte Arbeitsplätze bekommen Git
 * vorkonfiguriert. Hier wird sie ein- und ausgeschaltet; ausschalten hält
 * nur an — Repositories und Konten bleiben.
 */
export function GitEinstellungen({ onToast }: {
  onToast: (m: string, tone?: 'ok' | 'bad') => void
}) {
  const [stand, setStand] = useState<GitStand | null>(null)
  const [gruppen, setGruppen] = useState<Group[]>([])
  const [domain, setDomain] = useState('')
  const [otaUrl, setOtaUrl] = useState('')
  const [busy, setBusy] = useState<string | null>(null)

  const laden = useCallback(async () => {
    try {
      const s = await api.git()
      setStand(s); setDomain(s.domain); setOtaUrl(s.ota_url || window.location.origin)
    } catch { setStand(null) }
    try { setGruppen(await api.groups()) } catch { /* egal */ }
  }, [])
  useEffect(() => { void laden() }, [laden])

  async function tun(was: string, fn: () => Promise<string | void>) {
    setBusy(was)
    try {
      const m = await fn()
      if (m) onToast(m)
      await laden()
    } catch (err) {
      onToast(err instanceof ApiError ? err.message : tr('Hat nicht geklappt'), 'bad')
    } finally {
      setBusy(null)
    }
  }

  if (!stand) return <p className="sub">{tr('Wird geladen…')}</p>

  const gewaehlt = gruppen.filter((g) => stand.gruppen.includes(g.id)).map((g) => g.name)
  const byName = Object.fromEntries(gruppen.map((g) => [g.name, g.id]))
  const geaendert = domain.trim() !== stand.domain || otaUrl.trim() !== (stand.ota_url || '')
  const laeuft = stand.dienst.container === 'running' && stand.dienst.gesund === 'healthy'

  return (
    <div className="panel" style={{ padding: '16px 20px' }}>
      <p className="field__hint" style={{ marginTop: 0, marginBottom: 14 }}>
        {tr('Eine Git-Plattform (Forgejo) unter eigener Subdomain. Anmeldung mit denselben Zugangsdaten wie in OTA; die Konten legt OTA an. Berechtigte Arbeitsplätze bekommen Git vorkonfiguriert, andere Git-Server bleiben daneben nutzbar.')}
      </p>

      <Field label={tr('OTA-Git')}>
        <Toggle on={stand.an} name={stand.an ? tr('Eingeschaltet') : tr('Ausgeschaltet')}
          note={stand.an
            ? (laeuft ? tr('Läuft. {n} Konten, davon {g} gesperrt.', { n: stand.konten, g: stand.gesperrt })
              : tr('Container: {s}', { s: `${stand.dienst.container}${stand.dienst.gesund ? ` (${stand.dienst.gesund})` : ''}` }))
            : tr('Repositories und Konten bleiben erhalten, auch wenn es aus ist.')}
          onChange={(v) => {
            if (busy) return
            if (!v && !window.confirm(tr('OTA-Git anhalten? Repositories und Konten bleiben, aber niemand kommt hinein, bis es wieder an ist.'))) return
            void tun(v ? 'an' : 'aus', async () => {
              if (v) {
                if (geaendert) await api.gitEinstellen({ domain: domain.trim(), ota_url: otaUrl.trim() })
                await api.gitAn()
                return tr('OTA-Git läuft unter https://{d}/', { d: domain.trim() })
              }
              await api.gitAus()
              return tr('OTA-Git ist angehalten.')
            })
          }} />
        {busy === 'an' && <p className="field__hint">{tr('Wird eingerichtet — beim ersten Mal lädt OTA Forgejo herunter. Das dauert eine Weile.')}</p>}
      </Field>

      <Field label={tr('Subdomain')}
        hint={tr('Unter diesem Namen erreichen Browser OTA-Git — über euren Reverse Proxy auf denselben Port wie OTA. Arbeitsplätze brauchen keinen DNS-Eintrag.')}>
        <div className="row-item">
          <input value={domain} placeholder="git.firma.de" aria-label={tr('Subdomain')}
            onChange={(e) => setDomain(e.target.value)} />
        </div>
        {stand.domain && (
          <p className={stand.dns ? 'field__hint' : 'note-warn'} style={{ marginTop: 6 }}>
            {stand.dns
              ? tr('DNS: {d} → {ip}', { d: stand.domain, ip: stand.dns })
              : tr('Für {d} gibt es (vom OTA-Host aus gesehen) keinen DNS-Eintrag. Browser brauchen einen — auf den Reverse Proxy bzw. diesen Host.', { d: stand.domain })}
          </p>
        )}
      </Field>

      <Field label={tr('Adresse von OTA')}
        hint={tr('So, wie Browser OTA sehen. Forgejo findet die Anmeldung (Keycloak) darüber.')}>
        <div className="row-item">
          <input value={otaUrl} placeholder="https://ota.firma.de" aria-label={tr('Adresse von OTA')}
            onChange={(e) => setOtaUrl(e.target.value)} />
        </div>
      </Field>

      {geaendert && (
        <button className="btn" disabled={busy !== null || !domain.trim()} style={{ marginBottom: 14 }}
          onClick={() => void tun('speichern', async () => {
            await api.gitEinstellen({ domain: domain.trim(), ota_url: otaUrl.trim() })
            return stand.an ? tr('Gespeichert — OTA-Git läuft jetzt unter der neuen Adresse.') : tr('Gespeichert.')
          })}>
          {busy === 'speichern' ? tr('Wird gespeichert…') : tr('Speichern')}
        </button>
      )}

      <Field label={tr('Wer darf')}
        hint={tr('Mitglieder dieser Gruppen bekommen ein Konto und Git im Arbeitsplatz. Administratoren dürfen immer und sind auch in Forgejo Administratoren. Wer herausfällt, wird gesperrt, nicht gelöscht.')}>
        <ChipSelect label={tr('Gruppen')} selected={gewaehlt} options={gruppen.map((g) => g.name)}
          onChange={(namen) => void tun('gruppen', async () => {
            await api.gitEinstellen({ gruppen: namen.map((n) => byName[n]).filter(Boolean) })
            return tr('Gespeichert.')
          })} />
        {stand.gruppen.length === 0 && (
          <p className="note-warn" style={{ marginTop: 6 }}>{tr('Keine Gruppe gewählt — nur Administratoren kommen hinein.')}</p>
        )}
      </Field>

      <Field label={tr('Branch-Schutz als Vorgabe')}
        hint={tr('OTA schützt den Hauptzweig jedes Repositorys, sobald es Inhalt hat: kein direkter Push, Änderungen nur über einen Pull-Request mit Freigabe durch eine andere Person. Jedes Repository bekommt die Regel einmal; wer dort Administrator ist, kann sie ändern oder entfernen, und OTA setzt sie dann nicht neu. In Organisationen, in denen die Entwickler nur Schreibrecht haben, bleibt sie damit stehen.')}>
        <Toggle on={stand.branchschutz.an}
          name={stand.branchschutz.an ? tr('Eingeschaltet') : tr('Ausgeschaltet')}
          note={stand.branchschutz.an
            ? tr('{n} Repositories haben die Regel bekommen. Neue folgen spätestens nach 15 Minuten.', { n: stand.branchschutz_repos })
            : tr('Bestehende Regeln bleiben, wenn es aus ist.')}
          onChange={(v) => {
            if (busy) return
            void tun('schutz', async () => {
              const s = await api.gitEinstellen({ branchschutz: { an: v } })
              const n = (s.ergebnis as { gesetzt?: string[] } | undefined)?.gesetzt?.length
              return v ? tr('Branch-Schutz ist Vorgabe. Eben gesetzt: {n}', { n: n ?? 0 }) : tr('Branch-Schutz ist keine Vorgabe mehr.')
            })
          }} />
      </Field>

      {stand.branchschutz.an && (
        <>
          <Field label={tr('Pflicht-Freigaben')}
            hint={tr('So viele andere Personen müssen einen Pull-Request freigeben. Selbst freigeben geht in Forgejo nicht. 0 heißt: nur kein direkter Push. Gilt für Repositories, die die Regel ab jetzt bekommen.')}>
            <div className="numfield">
              <input type="number" min={0} max={5} step={1} aria-label={tr('Pflicht-Freigaben')}
                defaultValue={stand.branchschutz.freigaben}
                onBlur={(e) => {
                  const n = Number(e.target.value)
                  if (n === stand.branchschutz.freigaben) return
                  void tun('schutz', async () => {
                    await api.gitEinstellen({ branchschutz: { freigaben: n } })
                    return tr('Gespeichert.')
                  })
                }} />
            </div>
          </Field>
          <Field label={tr('Auch für Administratoren des Repositorys')}
            hint={tr('Aus: Der Eigentümer eines Repositorys darf trotz fehlender Freigabe zusammenführen. An: niemand, auch er nicht. Für Einzelprojekte heißt das, dass immer eine zweite Person mitliest.')}>
            <Toggle on={stand.branchschutz.fuer_admins}
              name={stand.branchschutz.fuer_admins ? tr('Eingeschaltet') : tr('Ausgeschaltet')}
              onChange={(v) => {
                if (busy) return
                void tun('schutz', async () => {
                  await api.gitEinstellen({ branchschutz: { fuer_admins: v } })
                  return tr('Gespeichert.')
                })
              }} />
          </Field>
        </>
      )}

      <GitGeheimnisseEinstellungen onToast={onToast} />

      {stand.an && (
        <div className="viewer__row" style={{ gap: 10, flexWrap: 'wrap', marginTop: 4 }}>
          <a className="btn" href={`https://${stand.domain}/`} target="_blank" rel="noreferrer">
            {tr('OTA-Git öffnen')}
          </a>
          <button className="btn" disabled={busy !== null}
            onClick={() => void tun('abgleich', async () => {
              await api.gitAbgleich()
              return tr('Konten abgeglichen.')
            })}>
            {busy === 'abgleich' ? tr('Wird abgeglichen…') : tr('Konten jetzt abgleichen')}
          </button>
        </div>
      )}

      <p className="field__hint" style={{ marginTop: 14 }}>
        {tr('SSH (Port 2222) geht nur aus den Arbeitsplätzen, nicht von außen. Reverse Proxy: dieselbe Weiterleitung wie für OTA, mit dem Namen der Subdomain (Host und SNI) — Handbuch Kapitel 27.')}
      </p>
    </div>
  )
}
