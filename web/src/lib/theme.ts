/**
 * Dunkel oder hell — das Gewand der Oberfläche.
 *
 * Genau wie die Sprache liegt es im Browser (`localStorage`) und nicht am
 * Konto: Es ist eine Frage des Arbeitsplatzes, nicht der Identität. Dieselbe
 * Person am hellen Bildschirm im Büro und am dunklen zu Hause will nicht ihr
 * Konto umstellen.
 *
 * Drei Zustände, nicht zwei: dunkel, hell, oder „wie der Rechner".
 *
 * **Die Vorgabe ist dunkel, nicht „wie der Rechner".** Das ist eine bewusste
 * Entscheidung und keine Bequemlichkeit: Die meisten Rechner melden hell, und
 * mit „System" als Vorgabe wäre OTA beim nächsten Aufruf für fast alle
 * plötzlich hell — eine Überraschung, kein Feature. Die dunkle Fläche ist
 * ausserdem das grösste Stück Farbe im Bild und trägt mehr zur Wiedererkennung
 * bei als jeder Akzent (siehe den Kopf von `styles/app.css`). Wer dem Rechner
 * folgen will, wählt das ausdrücklich.
 *
 * Gesetzt wird ein Attribut am Wurzelelement; die Farben stehen in
 * `styles/app.css` unter `:root[data-theme="hell"]`. Der Umweg über CSS und
 * nicht über React ist Absicht: So gilt das Gewand auch für das, was React
 * nicht malt — die Anmeldemaske vor dem ersten Rendern und den Grund der
 * Seite, bevor irgendetwas geladen ist.
 */

import { useEffect, useState } from 'react'

export type Theme = 'system' | 'hell' | 'dunkel'

const KEY = 'ota.theme'

function gespeichert(): Theme {
  try {
    const saved = localStorage.getItem(KEY)
    if (saved === 'hell' || saved === 'dunkel' || saved === 'system') return saved
  } catch { /* privater Modus — dann eben die Vorgabe */ }
  return 'dunkel'
}

let theme: Theme = gespeichert()
const listeners = new Set<(t: Theme) => void>()

const systemHell = () =>
  typeof window.matchMedia === 'function' &&
  window.matchMedia('(prefers-color-scheme: light)').matches

/** Was gerade wirklich gilt — „system" aufgelöst. */
export function wirksam(): 'hell' | 'dunkel' {
  if (theme === 'system') return systemHell() ? 'hell' : 'dunkel'
  return theme
}

function anwenden(): void {
  // Nur bei Hell ein Attribut setzen. Dunkel ist die Grundfarbe des
  // Stylesheets; ein Attribut dafür wäre eine zweite Wahrheit, die
  // irgendwann von der ersten abweicht.
  if (wirksam() === 'hell') document.documentElement.setAttribute('data-theme', 'hell')
  else document.documentElement.removeAttribute('data-theme')
}

export function getTheme(): Theme {
  return theme
}

export function setTheme(next: Theme): void {
  if (next === theme) return
  theme = next
  try { localStorage.setItem(KEY, next) } catch { /* nicht schlimm */ }
  anwenden()
  listeners.forEach((fn) => fn(next))
}

/** Zeichnet eine Ansicht nach dem Wechsel neu. Wie `useLang`. */
export function useTheme(): Theme {
  const [current, setCurrent] = useState(theme)
  useEffect(() => {
    listeners.add(setCurrent)
    return () => { listeners.delete(setCurrent) }
  }, [])
  return current
}

anwenden()

// Dem Rechner folgen, solange niemand sich festgelegt hat. Ohne das bliebe
// die Oberfläche dunkel, wenn das Betriebssystem morgens auf hell wechselt —
// und der Nutzer hätte „System" gewählt, gerade damit das passiert.
if (typeof window.matchMedia === 'function') {
  window.matchMedia('(prefers-color-scheme: light)').addEventListener('change', () => {
    if (theme === 'system') {
      anwenden()
      listeners.forEach((fn) => fn(theme))
    }
  })
}
