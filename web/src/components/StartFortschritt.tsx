import { useEffect, useState } from 'react'
import { api, type StartStand } from '../lib/api'
import { t as tr } from '../lib/i18n'

/** Was gerade passiert, in Worten. Die Schlüssel kommen aus API und Agent
 *  (`SCHRITTE_NEU`, `SCHRITTE_FORTSETZEN`, `_Startlauf`). */
const SCHRITT: Record<string, string> = {
  pruefen: 'Platz und Speicher prüfen',
  image: 'Image bereitstellen',
  netz: 'Netz einrichten',
  container: 'Container starten',
  einrichten: 'Zugänge einrichten',
  selkies: 'Bildübertragung prüfen',
  desktop: 'Desktop startet',
  ausstattung: 'Arbeitsplatz einrichten',
  skripte: 'Startskripte',
  route: 'Verbindung herstellen',
}

/**
 * Der Balken während eines Starts. Fragt alle 700 ms nach, solange er zu
 * sehen ist; der Start selbst ist ein einziger langer Aufruf, der davon
 * nichts weiß. Antwortet niemand, steht nur „startet…" da — wie vorher.
 */
export function StartFortschritt({ templateId }: { templateId: string }) {
  const [stand, setStand] = useState<StartStand | null>(null)

  useEffect(() => {
    let aus = false
    async function fragen() {
      try {
        const s = await api.startFortschritt(templateId)
        if (!aus) setStand(s.aktiv ? s : null)
      } catch { /* nur eine Anzeige */ }
    }
    void fragen()
    const timer = setInterval(() => { void fragen() }, 700)
    return () => { aus = true; clearInterval(timer) }
  }, [templateId])

  const anteil = stand?.anteil ?? 0
  const nummer = stand ? stand.schritte.indexOf(stand.schritt) + 1 : 0
  return (
    <span className="startlauf" role="progressbar" aria-valuemin={0} aria-valuemax={100}
      aria-valuenow={Math.round(anteil * 100)}>
      <span className="startlauf__kopf">
        <span className="startlauf__text">
          {stand ? tr(SCHRITT[stand.schritt] ?? stand.schritt) : tr('startet…')}
        </span>
        {stand && (
          <span className="silk data">
            {nummer}/{stand.schritte.length} · {Math.round(stand.sekunden)} s
          </span>
        )}
      </span>
      <span className="balken">
        <span className="balken__fuell startlauf__fuell" style={{ width: `${Math.max(3, anteil * 100)}%` }} />
      </span>
    </span>
  )
}
