import { useEffect, useState } from 'react'
import { t, useLang } from '../lib/i18n'

/**
 * Das Banner während eines Updates — auf jeder Seite, auch in Sessions im
 * eigenen Tab und auf der Anmeldeseite.
 *
 * `make update` setzt vor dem Bauen eine Marke in der Datenbank und nimmt sie
 * erst wieder weg, wenn die neue API gesund ist. Hier wird alle 15 Sekunden
 * nachgesehen (`/api/wartung`, ohne Anmeldung).
 *
 * **Bleibt stehen, solange keine Antwort kommt.** Mitten im Update startet die
 * API neu, und für einen Moment antwortet niemand. Das Banner verschwindet nur
 * auf ein ausdrückliches „kein Update" — sonst flackerte es genau dann weg,
 * wenn es am meisten gilt.
 *
 * Es fängt keine Klicks ab (`pointer-events: none`): Wer gerade in einer
 * Sitzung arbeitet, soll weiterarbeiten können, bis er neu lädt.
 */
const TAKT_MS = 15_000

export function UpdateBanner() {
  useLang()
  const [aktiv, setAktiv] = useState(false)

  useEffect(() => {
    let weg = false
    async function fragen() {
      try {
        const antwort = await fetch('/api/wartung', { cache: 'no-store', credentials: 'include' })
        if (!antwort.ok) return            // API startet gerade neu: so lassen
        const daten = (await antwort.json()) as { update?: boolean }
        if (!weg) setAktiv(Boolean(daten.update))
      } catch {
        /* keine Verbindung: so lassen, wie es ist */
      }
    }
    void fragen()
    const takt = setInterval(() => { void fragen() }, TAKT_MS)
    return () => { weg = true; clearInterval(takt) }
  }, [])

  if (!aktiv) return null
  return (
    <div className="update-banner" role="status" aria-live="polite">
      <b>{t('Achtung!')}</b>{' '}
      {t('OTA Update im Gange, bitte laden Sie alle OTA-Seiten neu, sobald diese Meldung verschwunden ist.')}
    </div>
  )
}
