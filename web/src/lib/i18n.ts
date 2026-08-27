/**
 * Zweisprachigkeit — Deutsch und Englisch.
 *
 * Der **deutsche Satz ist der Schlüssel**. Das ist bewusst so gewählt und
 * nicht der übliche Weg über erfundene Bezeichner wie `nav.help`:
 *
 *  - Im Quelltext steht weiterhin der Satz, den der Nutzer sieht. Wer den Code
 *    liest, muss nicht in einer zweiten Datei nachschlagen, was `nav.help`
 *    bedeutet.
 *  - Es gibt nur **ein** Wörterbuch statt zwei. Ein Bezeichner-Ansatz bräuchte
 *    auch für Deutsch eine vollständige Tabelle, die mit dem Quelltext
 *    auseinanderlaufen kann.
 *  - Der Rückfall ist brauchbar: Fehlt eine Übersetzung, erscheint der
 *    deutsche Satz — nicht `nav.help` oder eine leere Fläche.
 *
 * Platzhalter werden in geschweiften Klammern geschrieben:
 *
 *     t('{n} Nutzer in der Liste', { n: users.length })
 *
 * Die Sprache liegt im Browser des Nutzers (`localStorage`), nicht am Konto:
 * Sie ist eine Frage des Arbeitsplatzes, nicht der Identität — dieselbe Person
 * am englischen Rechner will Englisch sehen, ohne ihr Konto zu ändern.
 */

import { useEffect, useState } from 'react'
import { EN } from './i18n.en'

export type Lang = 'de' | 'en'

const KEY = 'ota.lang'

function initial(): Lang {
  try {
    const saved = localStorage.getItem(KEY)
    if (saved === 'de' || saved === 'en') return saved
  } catch { /* privater Modus — dann eben die Browsersprache */ }
  return navigator.language?.toLowerCase().startsWith('de') ? 'de' : 'en'
}

let lang: Lang = initial()
const listeners = new Set<(l: Lang) => void>()

export function getLang(): Lang {
  return lang
}

export function setLang(next: Lang): void {
  if (next === lang) return
  lang = next
  try { localStorage.setItem(KEY, next) } catch { /* nicht schlimm */ }
  document.documentElement.lang = next
  listeners.forEach((fn) => fn(next))
}

/** Übersetzt und setzt Platzhalter ein. */
export function t(text: string, vars?: Record<string, string | number>): string {
  const out = lang === 'de' ? text : (EN[text] ?? text)
  if (!vars) return out
  return out.replace(/\{(\w+)\}/g, (whole: string, name: string) =>
    name in vars ? String(vars[name]) : whole)
}

/**
 * Sorgt dafür, dass eine Komponente nach dem Sprachwechsel neu zeichnet.
 *
 * `t()` ist bewusst eine schlichte Funktion und kein Hook — sonst müsste jede
 * Hilfsfunktion und jede Konstantentabelle zur Komponente umgebaut werden.
 * Den Neuaufbau stösst dieser Hook an; er gehört in jede Ansicht, die
 * übersetzten Text zeigt.
 */
export function useLang(): Lang {
  const [current, setCurrent] = useState(lang)
  useEffect(() => {
    listeners.add(setCurrent)
    return () => { listeners.delete(setCurrent) }
  }, [])
  return current
}

document.documentElement.lang = lang
