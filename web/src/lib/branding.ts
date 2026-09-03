/**
 * Das Gesicht der Anlage — Name, Farbe, Zeichen.
 *
 * OTA steht in einem Unternehmen und heisst dort selten „OpenTerminalApps".
 * Wer die Anlage aufmacht, soll sein eigenes Zeichen sehen. Was ein
 * Administrator dafür hinterlegt, liegt auf dem Server (`/api/branding`) und
 * nicht im Browser: Eine Marke gilt für die Anlage, nicht für den Rechner, an
 * dem gerade jemand sitzt. Genau andersherum als beim Gewand — das ist eine
 * Frage des Arbeitsplatzes und liegt deshalb im `localStorage`
 * (`lib/theme.ts`).
 *
 * **Die Farben gehen über eine Zwischenstufe.** Das Stylesheet liest
 * `--accent: var(--brand-accent, #06B6D4)`. Ist nichts hinterlegt, greift die
 * Vorgabe aus dem Stylesheet — mit allem, was daran hängt, auch der eigens
 * abgedunkelten Fassung fürs helle Gewand. Erst eine wirklich gewählte Farbe
 * setzt die Variablen und übersteuert damit beide Gewänder auf einmal. Ohne
 * diese Stufe müsste hier nachgehalten werden, welches Gewand gerade gilt.
 */

import { useSyncExternalStore } from 'react'

export type Marke = {
  name: string
  accent: string
  logo_url: string | null
  has_logo: boolean
}

export const VORGABE: Marke = {
  name: 'OpenTerminalApps',
  accent: '#06B6D4',
  logo_url: null,
  has_logo: false,
}

let marke: Marke = VORGABE
const hoerer = new Set<() => void>()

export function aktuelleMarke(): Marke { return marke }

/** Für `useSyncExternalStore`: melden, wenn sich die Marke ändert. */
export function markeAbonnieren(fn: () => void): () => void {
  hoerer.add(fn)
  return () => { hoerer.delete(fn) }
}

/** Eine Farbe abdunkeln — für die zweite Stufe und das helle Gewand. */
function dunkler(hex: string, faktor: number): string {
  const n = parseInt(hex.slice(1), 16)
  const teil = (v: number) => Math.max(0, Math.min(255, Math.round(v * faktor)))
  const r = teil((n >> 16) & 255), g = teil((n >> 8) & 255), b = teil(n & 255)
  return '#' + [r, g, b].map((v) => v.toString(16).padStart(2, '0')).join('')
}

function anwenden(m: Marke): void {
  const wurzel = document.documentElement
  if (m.accent && m.accent.toUpperCase() !== VORGABE.accent) {
    wurzel.style.setProperty('--brand-accent', m.accent)
    wurzel.style.setProperty('--brand-accent-dim', dunkler(m.accent, 0.85))
    // Auf heller Fläche braucht dieselbe Farbe mehr Tiefe, sonst verschwindet
    // sie. Denselben Sprung macht die Vorgabe im Stylesheet auch.
    wurzel.style.setProperty('--brand-accent-hell', dunkler(m.accent, 0.7))
    wurzel.style.setProperty('--brand-accent-hell-dim', dunkler(m.accent, 0.58))
  } else {
    for (const v of ['--brand-accent', '--brand-accent-dim',
                     '--brand-accent-hell', '--brand-accent-hell-dim']) {
      wurzel.style.removeProperty(v)
    }
  }

  // Und eine Kopie in den localStorage, für die Anmeldemaske von Keycloak.
  // Die liegt auf derselben Herkunft und liest sie synchron im <head>
  // (`deploy/keycloak-theme/ota/login/resources/js/gewand.js`) — genau wie
  // beim Gewand. Ein `fetch` dort wäre asynchron, und die Maske blitzte kurz
  // in der falschen Farbe auf. Wer OTA noch nie geöffnet hat, sieht bei der
  // ersten Anmeldung die Vorgabe; danach stimmt es.
  try {
    localStorage.setItem('ota.marke', JSON.stringify(
      { accent: m.accent, name: m.name, logo_url: m.logo_url }))
  } catch { /* privater Modus — dann eben nur hier */ }

  document.title = m.name
  // Auch das Zeichen im Reiter des Browsers. Ein fremdes Symbol dort macht
  // jede andere Mühe zunichte — der Reiter ist das, was den ganzen Tag zu
  // sehen ist.
  const icon = document.querySelector<HTMLLinkElement>('link[rel="icon"]')
  if (icon) icon.href = m.logo_url ?? '/icon.svg'
}

export function setzeMarke(m: Marke): void {
  marke = m
  anwenden(m)
  for (const fn of hoerer) fn()
}

/**
 * Die Marke holen, bevor gezeichnet wird.
 *
 * Scheitert der Aufruf, bleibt es bei der Vorgabe — eine Anlage ohne
 * erreichbare API zeigt lieber das eigene Zeichen als gar nichts. Deshalb
 * fängt der Aufrufer hier nichts ab; das erledigt der Weg selbst.
 */
export async function ladeMarke(): Promise<void> {
  try {
    const antwort = await fetch('/api/branding', { credentials: 'include' })
    if (!antwort.ok) return
    const daten = await antwort.json() as Marke
    setzeMarke({ ...VORGABE, ...daten })
  } catch { /* Vorgabe bleibt */ }
}

/** Der Haken für die Oberfläche — meldet sich, wenn ein Administrator etwas ändert. */
export function useMarke(): Marke {
  return useSyncExternalStore(markeAbonnieren, aktuelleMarke, () => VORGABE)
}
