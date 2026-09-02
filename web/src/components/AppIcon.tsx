import { useState } from 'react'

/**
 * Das Symbol einer Anwendung — das echte aus dem Paket, sonst das Zeichen.
 *
 * Jedes Linux-Paket bringt sein Symbol mit, und OTA liest es beim Durchsehen
 * des Images aus der `.desktop`-Datei. Wo eines vorliegt, gehört es hierher:
 * Ein Mensch erkennt Firefox am Fuchs, nicht an einem Kreis.
 *
 * Das Zeichen bleibt trotzdem — an drei Stellen:
 *
 * * Ein Image bringt kein Symbol mit (kommt vor, etwa bei selbst gebauten
 *   Startskripten ohne `.desktop`-Eintrag).
 * * Das Bild lädt noch. Dann steht das Zeichen da und springt nicht, weil
 *   beide denselben Platz einnehmen.
 * * Das Bild lässt sich nicht laden. Ein kaputtes Symbol ist kein Grund für
 *   eine leere Kachel — `onError` schaltet still zurück.
 */
export function AppIcon({ url, glyph, size = 20, className }: {
  url?: string | null
  glyph?: string | null
  size?: number
  className?: string
}) {
  const [kaputt, setKaputt] = useState(false)

  if (!url || kaputt) {
    return (
      <span className={className} aria-hidden="true">{glyph || '▢'}</span>
    )
  }

  return (
    <span className={className} aria-hidden="true"
      style={{ display: 'inline-flex', alignItems: 'center', justifyContent: 'center' }}>
      <img src={url} alt="" width={size} height={size} loading="lazy"
        onError={() => setKaputt(true)}
        style={{ width: size, height: size, objectFit: 'contain', display: 'block' }} />
    </span>
  )
}
