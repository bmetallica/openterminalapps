/**
 * Anbindung an die Firefox-Erweiterung.
 *
 * Firefox stellt `navigator.clipboard.readText()` normalen Webseiten nicht zur
 * Verfügung — und daran ändert auch HTTPS nichts, das ist eine bewusste
 * Entscheidung des Browsers. Der Rückfall über das `paste`-Ereignis
 * funktioniert, verlangt aber bei jedem Einfügen ein Strg+V im richtigen
 * Fenster. Für eine Anwendung, die sich wie ein Desktop anfühlen soll, ist das
 * zu wenig.
 *
 * Die Erweiterung schliesst genau diese Lücke und sonst nichts. Sie liegt in
 * `extension/firefox/` und wird über den Verwaltungsbereich verteilt.
 *
 * Ist sie nicht da, verhält sich alles wie vorher: Diese Datei meldet dann
 * „nicht verfügbar", und die Brücke nimmt ihre übrigen Wege.
 */

const CHANNEL = 'ota-clipboard'
const TIMEOUT_MS = 1200

type Answer = { ok: boolean; text?: string; error?: string; version?: string }

let counter = 0
let known: boolean | null = null

export const isFirefox = (): boolean =>
  navigator.userAgent.toLowerCase().includes('firefox')

function ask(action: 'ping' | 'read' | 'write', text?: string): Promise<Answer | null> {
  return new Promise((resolve) => {
    const id = `ota-${++counter}`
    let done = false

    const finish = (value: Answer | null) => {
      if (done) return
      done = true
      window.removeEventListener('message', onMessage)
      clearTimeout(timer)
      resolve(value)
    }

    const onMessage = (event: MessageEvent) => {
      if (event.source !== window) return
      const msg = event.data
      if (!msg || msg.channel !== CHANNEL || msg.direction !== 'from-extension') return
      if (msg.id !== id) return
      finish(msg as Answer)
    }

    // Kein Aufräumen ohne Frist: Ohne installierte Erweiterung antwortet
    // niemand, und der Aufrufer wartet sonst ewig.
    const timer = window.setTimeout(() => finish(null), TIMEOUT_MS)
    window.addEventListener('message', onMessage)
    window.postMessage({ channel: CHANNEL, direction: 'to-extension', id, action, text }, window.origin)
  })
}

/** Ist die Erweiterung installiert und für diese Adresse freigegeben? */
export async function extensionPresent(): Promise<boolean> {
  if (known !== null) return known
  const answer = await ask('ping')
  known = Boolean(answer?.ok)
  return known
}

export async function readViaExtension(): Promise<string | null> {
  const answer = await ask('read')
  return answer?.ok && typeof answer.text === 'string' ? answer.text : null
}

export async function writeViaExtension(text: string): Promise<boolean> {
  const answer = await ask('write', text)
  return Boolean(answer?.ok)
}
