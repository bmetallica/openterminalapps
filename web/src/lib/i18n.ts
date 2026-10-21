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
 *
 * Wer nie umgeschaltet hat, bekommt die **Standardsprache der Anlage**
 * (Einstellungen → Sprache, kommt mit `/api/branding`). Sie wird im Browser
 * zwischengespeichert, damit beim nächsten Laden nichts in der falschen
 * Sprache aufblitzt. Bis zum 2026-10-22 entschied hier die Browsersprache.
 */

import { useEffect, useState } from 'react'
import { EN } from './i18n.en'

export type Lang = 'de' | 'en'

/** Die Wahl des Menschen. Fehlt sie, gilt die Standardsprache der Anlage. */
const KEY = 'ota.lang'
/** Die Standardsprache der Anlage, wie sie zuletzt vom Server kam. */
const KEY_STANDARD = 'ota.lang.standard'

function gelesen(key: string): Lang | null {
  try {
    const wert = localStorage.getItem(key)
    if (wert === 'de' || wert === 'en') return wert
  } catch { /* privater Modus — dann eben die Vorgabe */ }
  return null
}

let lang: Lang = gelesen(KEY) ?? gelesen(KEY_STANDARD) ?? 'de'
/** Die am Konto gemerkte Wahl — gilt vor der Standardsprache, nach der des Browsers. */
let konto: Lang | null = null
const listeners = new Set<(l: Lang) => void>()

export function getLang(): Lang {
  return lang
}

function wechseln(next: Lang): void {
  if (next === lang) return
  lang = next
  document.documentElement.lang = next
  listeners.forEach((fn) => fn(next))
}

/** Der Umschalter: Die Wahl gilt in diesem Browser, bis wieder umgeschaltet wird. */
export function setLang(next: Lang): void {
  try { localStorage.setItem(KEY, next) } catch { /* nicht schlimm */ }
  wechseln(next)
}

/** Die Standardsprache der Anlage. Wirkt nur, wo niemand selbst gewählt hat. */
export function setStandardLang(standard: Lang): void {
  try { localStorage.setItem(KEY_STANDARD, standard) } catch { /* nicht schlimm */ }
  if (!gelesen(KEY) && !konto) wechseln(standard)
}

/** Nach der Anmeldung: die am Konto gemerkte Wahl, falls dieser Browser keine hat. */
export function setKontoLang(gewaehlt: Lang | null): void {
  konto = gewaehlt
  if (konto && !gelesen(KEY)) wechseln(konto)
}

function einsetzen(text: string, vars?: Record<string, string | number>): string {
  if (!vars) return text
  return text.replace(/\{(\w+)\}/g, (whole: string, name: string) =>
    name in vars ? String(vars[name]) : whole)
}

/** Übersetzt und setzt Platzhalter ein. */
export function t(text: string, vars?: Record<string, string | number>): string {
  return einsetzen(lang === 'de' ? text : (EN[text] ?? text), vars)
}

/* Meldungen des Servers. Viele tragen einen Namen oder eine Zahl in sich
   („„git.x“ ist kein gültiger Name …“) und stehen deshalb mit Platzhaltern im
   Wörterbuch. Passt der Satz nicht wörtlich, wird er gegen diese Muster
   gehalten; ein Platzhalter steht dabei für beliebigen Text. */
let muster: { re: RegExp; namen: string[]; ziel: string }[] | null = null

function musterBauen() {
  muster = Object.entries(EN)
    .filter(([de]) => /\{\w+\}/.test(de))
    .map(([de, ziel]) => {
      const namen: string[] = []
      const quelle = de.split(/(\{\w+\})/).map((teil) => {
        const m = /^\{(\w+)\}$/.exec(teil)
        if (m) { namen.push(m[1]); return '([\\s\\S]+?)' }
        return teil.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')
      }).join('')
      return { re: new RegExp(`^${quelle}$`), namen, ziel }
    })
  return muster
}

/** Übersetzt eine Meldung des Servers — wörtlich oder über ein Muster. */
export function tServer(text: string): string {
  if (lang === 'de' || !text) return text
  if (EN[text] !== undefined) return EN[text]
  for (const { re, namen, ziel } of muster ?? musterBauen()) {
    const m = re.exec(text)
    if (m) return einsetzen(ziel, Object.fromEntries(namen.map((n, i) => [n, m[i + 1]])))
  }
  return text
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
