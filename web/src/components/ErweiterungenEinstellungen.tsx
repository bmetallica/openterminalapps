import { useCallback, useEffect, useState } from 'react'
import { ChipSelect, Field, Toggle } from './controls'
import { ApiError, api, type Erweiterung, type ErweiterungFeld, type Group } from '../lib/api'
import { t as tr } from '../lib/i18n'

/**
 * Einstellungen → Erweiterungen (Handbuch Kapitel 39).
 *
 * Eine Erweiterung ist eine eigenständige Docker-Anwendung mit eigenem
 * Compose-Projekt im Netz ota_erweiterungen. Hier wird sie gekoppelt (Adresse
 * und Kopplungsschlüssel aus ihrer .env), für Gruppen eingeschaltet und
 * eingestellt — das Formular beschreibt die Erweiterung selbst (JSON-Schema).
 */
export function ErweiterungenEinstellungen({ onToast }: {
  onToast: (m: string, tone?: 'ok' | 'bad') => void
}) {
  const [liste, setListe] = useState<Erweiterung[] | null>(null)
  const [gruppen, setGruppen] = useState<Group[]>([])
  const [adresse, setAdresse] = useState('')
  const [schluessel, setSchluessel] = useState('')
  const [busy, setBusy] = useState<string | null>(null)

  const laden = useCallback(async () => {
    try { setListe(await api.erweiterungen()) } catch { setListe([]) }
    try { setGruppen(await api.groups()) } catch { /* egal */ }
  }, [])
  useEffect(() => { void laden() }, [laden])

  async function tun(was: string, fn: () => Promise<string | void>) {
    setBusy(was)
    try {
      const m = await fn()
      if (m) onToast(m)
    } catch (err) {
      onToast(err instanceof ApiError ? err.message : tr('Hat nicht geklappt'), 'bad')
    } finally {
      setBusy(null)
    }
  }

  if (!liste) return <p className="sub">{tr('Wird geladen…')}</p>

  return (
    <div className="panel" style={{ padding: '16px 20px' }}>
      <p className="field__hint" style={{ marginTop: 0, marginBottom: 14 }}>
        {tr('Eigenständige Docker-Anwendungen, die OTA in die Arbeitsplätze einbindet — etwa ein Gedächtnis für opencode. Jede läuft als eigenes Compose-Projekt im Netz ota_erweiterungen; OTA gibt berechtigten Arbeitsplätzen Zugang und zeigt ihre Ansichten unter Mein Konto und im Menü der Kachel.')}
      </p>

      {liste.map((e) => (
        <ErweiterungKarte key={e.slug} e={e} gruppen={gruppen} busy={busy} tun={tun}
          neu={(x) => setListe(liste.map((y) => (y.slug === x.slug ? x : y)))}
          weg={() => setListe(liste.filter((y) => y.slug !== e.slug))} />
      ))}

      <Field label={tr('Erweiterung koppeln')}
        hint={tr('Adresse im Netz ota_erweiterungen und den Kopplungsschlüssel, den die Erweiterung bei ihrem setup.sh ausgibt (steht in ihrer .env). Danach braucht OTA den Schlüssel nicht mehr.')}>
        <div className="row-item">
          <input value={adresse} placeholder="http://ota-gedaechtnis:8080" aria-label={tr('Adresse')}
            onChange={(ev) => setAdresse(ev.target.value)} />
          <input type="password" autoComplete="off" value={schluessel} placeholder={tr('Kopplungsschlüssel')}
            aria-label={tr('Kopplungsschlüssel')} onChange={(ev) => setSchluessel(ev.target.value)} />
          <button className="btn btn--primary" disabled={busy !== null || !adresse.trim() || !schluessel.trim()}
            onClick={() => void tun('koppeln', async () => {
              const x = await api.erweiterungKoppeln(adresse.trim(), schluessel.trim())
              setAdresse(''); setSchluessel('')
              await laden()
              return tr('„{n}“ ist gekoppelt. Zum Einschalten den Schalter umlegen.', { n: x.name })
            })}>{busy === 'koppeln' ? tr('Wird gekoppelt…') : tr('Koppeln')}</button>
        </div>
      </Field>
    </div>
  )
}

function ErweiterungKarte({ e, gruppen, busy, tun, neu, weg }: {
  e: Erweiterung
  gruppen: Group[]
  busy: string | null
  tun: (was: string, fn: () => Promise<string | void>) => Promise<void>
  neu: (e: Erweiterung) => void
  weg: () => void
}) {
  const [werte, setWerte] = useState<Record<string, unknown> | null>(null)
  const [entwurf, setEntwurf] = useState<Record<string, unknown>>({})
  const [offen, setOffen] = useState(false)
  const [info, setInfo] = useState<string>('')
  const felder = Object.entries(e.konfiguration_schema?.properties ?? {})
  const gruppenNamen = gruppen.filter((g) => e.gruppen.includes(g.id)).map((g) => g.name)
  const byName = Object.fromEntries(gruppen.map((g) => [g.name, g.id]))

  async function aufklappen() {
    setOffen(!offen)
    if (!offen && werte === null) {
      try { setWerte(await api.erweiterungKonfiguration(e.slug)) } catch { setWerte({}) }
    }
  }

  const geaendert = Object.keys(entwurf).length > 0

  return (
    <div className="panel" style={{ padding: '12px 16px', marginBottom: 14, background: 'var(--well)' }}>
      <div className="viewer__row" style={{ justifyContent: 'space-between', alignItems: 'baseline' }}>
        <div>
          <h3 className="h-card" style={{ margin: 0 }}>{e.name} <span className="sub data">{e.version}</span></h3>
          <p className="sub" style={{ margin: '2px 0 0' }}>{e.beschreibung}</p>
          <p className="field__hint" style={{ margin: '2px 0 0' }}>
            <span className="data">{e.adresse}</span> · {e.stand}
          </p>
        </div>
        <button className="btn btn--ghost" onClick={() => void aufklappen()}>
          {offen ? tr('Weniger') : tr('Einstellen')}
        </button>
      </div>

      <Field label={tr('Eingeschaltet')}>
        <Toggle on={e.an} name={e.an ? tr('Eingeschaltet') : tr('Ausgeschaltet')}
          note={tr('Gilt ab dem nächsten Start oder Fortsetzen eines Arbeitsplatzes; die Ansichten sofort.')}
          onChange={(v) => void tun(`an-${e.slug}`, async () => {
            neu(await api.erweiterungEinstellen(e.slug, { an: v }))
            return v ? tr('„{n}“ ist eingeschaltet.', { n: e.name }) : tr('„{n}“ ist ausgeschaltet.', { n: e.name })
          })} />
      </Field>

      <Field label={tr('Wer darf')}
        hint={tr('Ohne Gruppe alle. Sonst nur Mitglieder dieser Gruppen; Administratoren immer. Wer nicht mehr darf, wird in der Erweiterung gesperrt — seine Daten bleiben.')}>
        <ChipSelect label={tr('Gruppen')} selected={gruppenNamen} options={gruppen.map((g) => g.name)}
          onChange={(namen) => void tun(`gruppen-${e.slug}`, async () => {
            neu(await api.erweiterungEinstellen(e.slug, { gruppen: namen.map((n) => byName[n]).filter(Boolean) }))
          })} />
      </Field>

      {offen && (
        <>
          {e.liefert.includes('prompt') && (
            <Field label={tr('Zusatz zum Systemprompt')}>
              <Toggle on={e.prompt_an} name={e.prompt_an ? tr('Geht mit') : tr('Geht nicht mit')}
                note={tr('Die Erweiterung erklärt dem Modell, wie es sie benutzt. Zu sehen in der Vorschau unter opencode.')}
                onChange={(v) => void tun(`prompt-${e.slug}`, async () => {
                  neu(await api.erweiterungEinstellen(e.slug, { prompt_an: v }))
                })} />
            </Field>
          )}

          {werte === null ? <p className="sub">{tr('Wird geladen…')}</p> : felder.map(([k, f]) => (
            <FeldEingabe key={k} name={k} f={f}
              wert={k in entwurf ? entwurf[k] : werte[k]}
              gesetzt={!!werte[`${k}_gesetzt`]}
              setze={(v) => setEntwurf({ ...entwurf, [k]: v })} />
          ))}

          <div className="viewer__row" style={{ gap: 10, margin: '6px 0 12px', flexWrap: 'wrap' }}>
            {geaendert && (
              <>
                <button className="btn btn--primary" disabled={busy !== null}
                  onClick={() => void tun(`konf-${e.slug}`, async () => {
                    setWerte(await api.erweiterungKonfigurieren(e.slug, entwurf))
                    setEntwurf({})
                    return tr('Gespeichert.')
                  })}>{tr('Speichern')}</button>
                <button className="btn" onClick={() => setEntwurf({})}>{tr('Verwerfen')}</button>
              </>
            )}
            <button className="btn" disabled={busy !== null} onClick={() => void tun(`test-${e.slug}`, async () => {
              const r = await api.erweiterungTesten(e.slug)
              setInfo(r.an === false ? tr('Nichts zu testen (Embeddings aus).')
                : r.ok ? tr('Antwort nach {ms} ms, {d} Dimensionen.', { ms: String(r.ms), d: String(r.dimension) })
                  : tr('Fehler: {m}', { m: String(r.meldung ?? '') }))
            })}>{busy === `test-${e.slug}` ? tr('Wird getestet…') : tr('Testen')}</button>
            <button className="btn" disabled={busy !== null} onClick={() => void tun(`stat-${e.slug}`, async () => {
              const s = await api.erweiterungStatistik(e.slug)
              setInfo(Object.entries(s).map(([k, v]) => `${k}: ${v}`).join(' · '))
            })}>{tr('Zahlen')}</button>
            <button className="btn btn--ghost" disabled={busy !== null} onClick={() => {
              if (!confirm(tr('„{n}“ entkoppeln? Die Arbeitsplätze verlieren den Zugang; die Daten bleiben in der Erweiterung.', { n: e.name }))) return
              void tun(`weg-${e.slug}`, async () => {
                await api.erweiterungEntfernen(e.slug)
                weg()
                return tr('Entkoppelt.')
              })
            }}>{tr('Entkoppeln')}</button>
          </div>
          {info && <p className="field__hint">{info}</p>}
          <p className="field__hint">
            {tr('Wege aus den Arbeitsplätzen: {p}. Admins sehen hier nur Zahlen, keine Inhalte.', {
              p: e.pfade.map((p) => `ota-erweiterungen:8091/${e.slug}${p}`).join(', ') || '—' })}
          </p>
        </>
      )}
    </div>
  )
}

function FeldEingabe({ name, f, wert, gesetzt, setze }: {
  name: string
  f: ErweiterungFeld
  wert: unknown
  gesetzt: boolean
  setze: (v: unknown) => void
}) {
  const titel = f.title || name
  if (f.type === 'boolean') {
    return (
      <Field label={titel}>
        <Toggle on={!!wert} name={wert ? tr('An') : tr('Aus')} note={f.description} onChange={setze} />
      </Field>
    )
  }
  if (f.enum) {
    return (
      <Field label={titel} hint={f.description}>
        <select value={String(wert ?? '')} aria-label={titel} onChange={(ev) => setze(ev.target.value)}>
          {f.enum.map((o) => <option key={o} value={o}>{o}</option>)}
        </select>
      </Field>
    )
  }
  if (f.type === 'integer' || f.type === 'number') {
    return (
      <Field label={titel} hint={f.description}>
        <input type="number" min={f.minimum} max={f.maximum} value={wert === undefined || wert === null ? '' : Number(wert)}
          aria-label={titel} style={{ width: 140 }}
          onChange={(ev) => setze(ev.target.value === '' ? null : Number(ev.target.value))} />
      </Field>
    )
  }
  if (f['x-geheim']) {
    return (
      <Field label={titel} hint={f.description}>
        <input type="password" autoComplete="new-password" value={String(wert ?? '')} aria-label={titel}
          placeholder={gesetzt ? tr('gesetzt — leer lassen, um ihn zu behalten') : tr('keiner')}
          onChange={(ev) => setze(ev.target.value)} />
      </Field>
    )
  }
  return (
    <Field label={titel} hint={f.description}>
      <input value={String(wert ?? '')} aria-label={titel} style={{ width: '100%' }}
        onChange={(ev) => setze(ev.target.value)} />
    </Field>
  )
}
