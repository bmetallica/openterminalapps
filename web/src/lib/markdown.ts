/**
 * Ein kleiner Markdown-Übersetzer für das Handbuch.
 *
 * Warum nicht eine Bibliothek: Das Handbuch nutzt eine überschaubare Teilmenge
 * — Überschriften, Listen, Tabellen, Codeblöcke, Zitate, fette Stellen und
 * Links. Dafür eine Abhängigkeit samt Sanitizer mitzuschleppen wäre teurer als
 * diese Datei, und jede Bibliothek müsste hier ohnehin gebändigt werden, weil
 * rohes HTML im Handbuch nichts zu suchen hat.
 *
 * Sicherheit: Es wird **zuerst** alles maskiert und danach ausschliesslich das
 * eingesetzt, was diese Datei selbst erzeugt. Rohes HTML aus der Quelldatei
 * kann deshalb nie im Dokument landen — auch dann nicht, wenn jemand mit
 * Schreibrecht auf `docs/wiki/` es versuchen würde.
 */

import { htmlFiltern } from './htmlFilter'
import { getLang } from './i18n'

const esc = (s: string): string =>
  s.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;')

// Platzhalter für Code-Abschnitte. Ein Zeichen, das in Markdown nicht vorkommt
// und das die Maskierung oben nicht erzeugen kann.
const MARK = '\u0000'
// Platzhalter für einen erzwungenen Zeilenumbruch, aus demselben Grund.
const UMBRUCH = '\u0001'
// Platzhalter für ein HTML-Tag im HTML-Modus.
const TAG = '\u0002'
const TAG_MUSTER = /<\/?[a-zA-Z][^<>]*>|<!--[\s\S]*?-->/g
// Eine Zeile, die nur aus Tags besteht, ist ein eigener Block und kein Absatz.
const NUR_TAGS = /^\s*(<\/?[a-zA-Z][^<>]*>\s*)+$/
// Beginnt ein Absatz mit einem Block-Tag, kommt kein <p> darum — der Browser
// schlösse es vor dem Tag und hinterliesse leere Absätze.
const BLOCK_ANFANG = /^\s*<\/?(center|div|p|table|h[1-6]|ul|ol|blockquote|pre|hr|details|dl)\b/i

/** Fette Stellen, Code, Links. Maskiert wird hier; mit `html` bleiben die
 *  Tags stehen und gehen danach durch `htmlFiltern`. */
function inline(raw: string, html = false): string {
  // Code zuerst herausnehmen: darin darf nichts weiter ersetzt werden, auch
  // kein HTML — `<b>` in Backticks bleibt Text.
  const code: string[] = []
  let s = raw.replace(/`([^`]+)`/g, (_m, c: string) =>
    MARK + String(code.push(`<code>${esc(c)}</code>`) - 1) + MARK)
  const tags: string[] = []
  if (html) s = s.replace(TAG_MUSTER, (m) => TAG + String(tags.push(m) - 1) + TAG)
  s = esc(s)
  s = s.replace(/\*\*([^*]+)\*\*/g, '<strong>$1</strong>')
  s = s.replace(/(^|[\s(])\*([^*\n]+)\*/g, '$1<em>$2</em>')
  // Bilder **vor** den Verweisen: `![…](…)` ist syntaktisch ein Verweis mit
  // einem Ausrufezeichen davor, und die Verweisregel unten wuerde daraus einen
  // Link machen, dem ein einsames „!" vorausgeht.
  //
  // Erlaubt ist genau eine Form: `bilder/name.svg` neben dem Handbuch. Kein
  // Pfad nach draussen, kein fremder Host, keine Datenadresse — die API liefert
  // die Datei aus, und ihr Name muss die Prüfung dort ebenfalls bestehen.
  s = s.replace(/!\[([^\]]*)\]\(bilder\/([a-z0-9-]+\.svg)\)/g,
    (_m, alt: string, datei: string) =>
      `<img class="md-bild" src="/api/help/bild/${datei}?lang=${getLang()}" alt="${alt}" loading="lazy" />`)

  s = s.replace(/\[([^\]]+)\]\(([^)]+)\)/g, (_m, text: string, href: string) => {
    // Verweise zwischen Kapiteln bleiben im Programm; alles andere geht auf.
    const chapter = /^([0-9]{2}-[a-z0-9-]+)\.md/.exec(href)
    if (chapter) return `<a href="#" data-chapter="${chapter[1]}">${text}</a>`
    if (/^https?:\/\//.test(href)) {
      return `<a href="${href}" target="_blank" rel="noopener noreferrer">${text}</a>`
    }
    // Verweise auf Dateien im Projekt (plan.md, roadmap.md) sind im Browser
    // nicht erreichbar — als Text stehen lassen, statt ins Leere zu zeigen.
    return `<span class="md-ref">${text}</span>`
  })
  return s.replace(/\u0000(\d+)\u0000/g, (_m, i: string) => code[Number(i)])
    .replace(/\u0002(\d+)\u0002/g, (_m, i: string) => tags[Number(i)])
    .replace(/\u0001/g, '<br />')
}

/** Zeilen eines Absatzes zusammenfügen. Zwei Leerzeichen oder `\` am Ende
 *  erzwingen einen Umbruch, mit `umbrueche` jede Zeilenschaltung. */
function zeilen(body: string[], umbrueche: boolean): string {
  return body.map((z, n) => {
    if (n === body.length - 1) return z
    if (/ {2,}$/.test(z)) return z.replace(/ +$/, '') + UMBRUCH
    if (/\\$/.test(z)) return z.slice(0, -1) + UMBRUCH
    return umbrueche ? z + UMBRUCH : z + ' '
  }).join('')
}

function tableRow(line: string): string[] {
  return line.replace(/^\||\|$/g, '').split('|').map((c) => c.trim())
}

/** Für die News, wo man schreibt wie in einer Mail:
 *  `umbrueche` — jede Zeilenschaltung im Absatz bleibt eine;
 *  `html` — HTML im Text gilt, gefiltert nach `htmlFilter.ts`.
 *  Das Handbuch nutzt beides nicht: es bricht seine Quelltextzeilen um, und
 *  rohes HTML hat darin nichts zu suchen. */
export function renderMarkdown(src: string, { umbrueche = false, html = false }:
  { umbrueche?: boolean; html?: boolean } = {}): string {
  const ein = (t: string) => inline(t, html)
  const lines = src.replace(/\r\n/g, '\n').split('\n')
  const out: string[] = []
  let i = 0
  let list: 'ul' | 'ol' | null = null

  const closeList = () => { if (list) { out.push(`</${list}>`); list = null } }

  while (i < lines.length) {
    const line = lines[i]

    // Codeblock
    if (line.startsWith('```')) {
      closeList()
      const lang = line.slice(3).trim()
      const body: string[] = []
      i++
      while (i < lines.length && !lines[i].startsWith('```')) { body.push(lines[i]); i++ }
      i++
      out.push(`<pre class="md-code"${lang ? ` data-lang="${esc(lang)}"` : ''}>` +
               `<code>${esc(body.join('\n'))}</code></pre>`)
      continue
    }

    // Tabelle: Kopfzeile, Trennzeile, dann Inhalt.
    if (line.startsWith('|') && lines[i + 1]?.replace(/[\s|:-]/g, '') === '') {
      closeList()
      const head = tableRow(line)
      i += 2
      const rows: string[][] = []
      while (i < lines.length && lines[i].startsWith('|')) { rows.push(tableRow(lines[i])); i++ }
      out.push('<div class="md-scroll"><table class="md-table"><thead><tr>' +
        head.map((c) => `<th>${ein(c)}</th>`).join('') + '</tr></thead><tbody>' +
        rows.map((r) => '<tr>' + r.map((c) => `<td>${ein(c)}</td>`).join('') + '</tr>').join('') +
        '</tbody></table></div>')
      continue
    }

    const heading = /^(#{1,6})\s+(.*)$/.exec(line)
    if (heading) {
      closeList()
      const level = heading[1].length
      out.push(`<h${level} class="md-h${level}">${ein(heading[2])}</h${level}>`)
      i++
      continue
    }

    if (/^\s*[-*]\s+/.test(line)) {
      if (list !== 'ul') { closeList(); out.push('<ul class="md-list">'); list = 'ul' }
      out.push(`<li>${ein(line.replace(/^\s*[-*]\s+/, ''))}</li>`)
      i++
      continue
    }

    if (/^\s*\d+\.\s+/.test(line)) {
      if (list !== 'ol') { closeList(); out.push('<ol class="md-list">'); list = 'ol' }
      out.push(`<li>${ein(line.replace(/^\s*\d+\.\s+/, ''))}</li>`)
      i++
      continue
    }

    if (line.startsWith('> ')) {
      closeList()
      const body: string[] = []
      while (i < lines.length && lines[i].startsWith('> ')) { body.push(lines[i].slice(2)); i++ }
      out.push(`<blockquote class="md-quote">${ein(zeilen(body, umbrueche))}</blockquote>`)
      continue
    }

    if (/^(---|___|\*\*\*)\s*$/.test(line)) {
      closeList(); out.push('<hr class="md-rule" />'); i++; continue
    }

    if (line.trim() === '') { closeList(); i++; continue }

    if (html && NUR_TAGS.test(line)) { closeList(); out.push(ein(line)); i++; continue }

    // Absatz: bis zur nächsten Leerzeile oder einem Blockanfang.
    closeList()
    const para: string[] = []
    while (i < lines.length && lines[i].trim() !== '' && !(html && NUR_TAGS.test(lines[i])) &&
           !/^(#{1,6}\s|```|\||>\s|\s*[-*]\s|\s*\d+\.\s)/.test(lines[i])) {
      para.push(lines[i]); i++
    }
    const absatz = ein(zeilen(para, umbrueche))
    out.push(html && BLOCK_ANFANG.test(para[0]) ? absatz : `<p class="md-p">${absatz}</p>`)
  }

  closeList()
  return html ? htmlFiltern(out.join('\n')) : out.join('\n')
}
