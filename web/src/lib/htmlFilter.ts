/**
 * HTML für die News, nach Positivliste gefiltert.
 *
 * Ein Beitrag läuft im Browser jedes Nutzers mit dessen Anmeldung, und die
 * CSP erlaubt Inline-Skripte. Was ein Autor schreibt, darf deshalb gestalten
 * (`<center>`, `<font color>`, `style="color:…"`, Tabellen), aber nichts
 * ausführen: keine Skripte, keine Ereignis-Attribute, keine `javascript:`-
 * Verweise, keine Formulare, kein `position:fixed` über der Seite.
 *
 * Geparst wird mit DOMParser: das Dokument ist inert, nichts darin lädt oder
 * läuft, bevor der Filter fertig ist.
 */

// Samt Inhalt weg: was hier drinsteht, ist nie Text für Leser.
const WEG = new Set(['script', 'style', 'iframe', 'frame', 'frameset', 'object', 'embed', 'applet',
  'template', 'noscript', 'svg', 'math', 'form', 'input', 'button', 'textarea', 'select', 'option',
  'link', 'meta', 'base', 'title', 'head', 'audio', 'video', 'source', 'track', 'canvas', 'dialog'])

const ALLE = ['style', 'title', 'align', 'dir', 'lang']
const TAGS: Record<string, string[]> = {
  b: [], i: [], u: [], s: [], strike: [], strong: [], em: [], mark: [], small: [], big: [],
  sub: [], sup: [], br: [], hr: [], p: [], div: [], span: [], center: [], kbd: [], abbr: [],
  font: ['color', 'size', 'face'], h1: [], h2: [], h3: [], h4: [], h5: [], h6: [],
  ul: [], ol: ['start', 'type'], li: [], blockquote: [], pre: ['data-lang'], code: [],
  table: ['border', 'cellpadding', 'cellspacing', 'width'], thead: [], tbody: [], tfoot: [], tr: [],
  th: ['colspan', 'rowspan', 'width'], td: ['colspan', 'rowspan', 'width'], caption: [],
  colgroup: [], col: ['span', 'width'], details: ['open'], summary: [], dl: [], dt: [], dd: [],
  a: ['href', 'data-chapter'], img: ['src', 'alt', 'width', 'height', 'loading'],
}

// Gestalten ja, Verlassen des Beitrags nein: kein position, kein z-index.
const CSS = new Set(['color', 'background', 'background-color', 'text-align', 'font-size',
  'font-weight', 'font-style', 'font-family', 'text-decoration', 'line-height', 'letter-spacing',
  'margin', 'margin-top', 'margin-bottom', 'margin-left', 'margin-right', 'padding', 'padding-top',
  'padding-bottom', 'padding-left', 'padding-right', 'border', 'border-top', 'border-bottom',
  'border-left', 'border-right', 'border-color', 'border-radius', 'border-collapse', 'width',
  'max-width', 'height', 'vertical-align', 'white-space', 'display', 'opacity', 'list-style-type'])

function css(wert: string): string {
  return wert.split(';').map((teil) => {
    const i = teil.indexOf(':')
    if (i < 0) return ''
    const prop = teil.slice(0, i).trim().toLowerCase()
    const v = teil.slice(i + 1).trim()
    if (!CSS.has(prop) || /url\s*\(|expression|javascript:|@import|\\|[<>]/i.test(v)) return ''
    return `${prop}: ${v}`
  }).filter(Boolean).join('; ')
}

function attribute(el: Element, tag: string) {
  const erlaubt = new Set([...ALLE, ...TAGS[tag]])
  for (const { name, value } of Array.from(el.attributes)) {
    const n = name.toLowerCase()
    // Die eigenen Klassen des Markdown-Renderers bleiben, fremde nicht.
    if (n === 'class' && /^md-[a-z-]+$/.test(value)) continue
    if (!erlaubt.has(n)) { el.removeAttribute(name); continue }
    if (n === 'style') {
      const s = css(value)
      if (s) el.setAttribute('style', s); else el.removeAttribute('style')
    } else if (n === 'href' && !/^(https?:|mailto:|#|\/(?!\/))/i.test(value.trim())) {
      el.removeAttribute(name)
    } else if (n === 'src' && !/^(\/(?!\/)|data:image\/(png|jpe?g|gif|webp);)/i.test(value.trim())) {
      el.removeAttribute(name)
    } else if ((n === 'color' || n === 'face' || n === 'size') && !/^[#\w\s,.%()+-]+$/.test(value)) {
      el.removeAttribute(name)
    }
  }
  if (tag === 'a' && /^https?:/i.test(el.getAttribute('href') ?? '')) {
    el.setAttribute('target', '_blank')
    el.setAttribute('rel', 'noopener noreferrer')
  }
}

function saeubern(knoten: Node) {
  for (const kind of Array.from(knoten.childNodes)) {
    if (kind.nodeType === Node.COMMENT_NODE) { kind.remove(); continue }
    if (kind.nodeType !== Node.ELEMENT_NODE) continue
    const el = kind as Element
    const tag = el.tagName.toLowerCase()
    if (WEG.has(tag)) { el.remove(); continue }
    saeubern(el)
    if (!(tag in TAGS)) { el.replaceWith(...Array.from(el.childNodes)); continue }
    attribute(el, tag)
    if (tag === 'img' && !el.getAttribute('src')) el.remove()
  }
}

export function htmlFiltern(html: string): string {
  const doc = new DOMParser().parseFromString(`<body>${html}</body>`, 'text/html')
  saeubern(doc.body)
  return doc.body.innerHTML
}
