import { useCallback, useEffect, useState } from 'react'
import { Field, Segmented, Toggle } from './controls'
import { ApiError, api, type GitGeheimnisseEinstellungen as Einst, type GitGeheimnisseStand } from '../lib/api'
import { t as tr } from '../lib/i18n'

/**
 * Einstellungen → Git → Geheimnisse beim Push (Handbuch Kapitel 27).
 *
 * Ein Hook in Forgejo prüft die neuen Commits jedes Pushes auf private
 * Schlüssel, Tokens, Passwörter im Code und Dateien wie `.env`. Gezählt
 * werden nur Fälle und Arten (Betrieb → Sicherheit), nie Fundorte.
 */
export function GitGeheimnisseEinstellungen({ onToast }: { onToast: (m: string, tone?: 'ok' | 'bad') => void }) {
  const [stand, setStand] = useState<GitGeheimnisseStand | null>(null)
  const [busy, setBusy] = useState(false)

  const laden = useCallback(async () => {
    try { setStand(await api.gitGeheimnisse()) } catch { setStand(null) }
  }, [])
  useEffect(() => { void laden() }, [laden])

  async function setze(patch: Partial<Einst>, note = tr('Gespeichert.')) {
    setBusy(true)
    try {
      const s = await api.gitGeheimnisseEinstellen(patch)
      setStand(s)
      if (s.abgleich?.fehler) onToast(tr('Gespeichert, aber Forgejo nicht erreicht: {f}', { f: s.abgleich.fehler }), 'bad')
      else onToast(note)
    } catch (err) {
      onToast(err instanceof ApiError ? err.message : tr('Hat nicht geklappt'), 'bad')
    } finally {
      setBusy(false)
    }
  }

  if (!stand) return null

  return (
    <>
      <Field label={tr('Geheimnisse beim Push erkennen')}
        hint={tr('Forgejo prüft die neuen Commits jedes Pushes auf private Schlüssel, Tokens und API-Schlüssel, Passwörter im Code, Zugangsdaten in Adressen und Dateien wie .env oder id_rsa. Wer pusht, sieht Datei und Commit in der Ausgabe von git; OTA zählt nur Fälle und Arten, nie Fundorte, Repositories oder Personen.')}>
        <Toggle on={stand.an} name={stand.an ? tr('Eingeschaltet') : tr('Ausgeschaltet')}
          note={stand.an ? tr('Gilt für jedes Repository, auch für neue, Forks und Migrationen.') : undefined}
          onChange={(v) => { if (!busy) void setze({ an: v }, v ? tr('Geheimnisprüfung ist eingeschaltet.') : tr('Geheimnisprüfung ist ausgeschaltet.')) }} />
      </Field>
      {stand.an && (
        <>
          <Field label={tr('Bei einem Fund')}
            hint={tr('Beobachten zählt nur. Warnen nimmt den Push an und zeigt, was gefunden wurde, samt Anleitung. Sperren weist den Push ab. Ein Geheimnis in der Historie bleibt dort, auch wenn ein späterer Commit es löscht; Sperren verhindert, dass es überhaupt ankommt.')}>
            <Segmented label={tr('Bei einem Fund')} value={stand.betriebsart}
              options={[
                { value: 'beobachten', label: tr('Beobachten') },
                { value: 'warnen', label: tr('Warnen') },
                { value: 'sperren', label: tr('Sperren'), tone: 'halt' },
              ]}
              onChange={(v) => void setze({ betriebsart: v })} />
          </Field>
          {stand.betriebsart === 'sperren' && (
            <Field label={tr('Fehlalarm übergehen erlauben')}
              hint={tr('Mit „git push -o ota.geheimnis=falscher-alarm“ geht ein gesperrter Push doch durch, etwa für einen Beispielschlüssel in Tests. Wird als „übergangen“ gezählt.')}>
              <Toggle on={stand.uebergehen} name={stand.uebergehen ? tr('Eingeschaltet') : tr('Ausgeschaltet')}
                onChange={(v) => void setze({ uebergehen: v })} />
            </Field>
          )}
        </>
      )}
    </>
  )
}
