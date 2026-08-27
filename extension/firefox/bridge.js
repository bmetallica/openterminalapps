/* Inhaltsskript — die Brücke zwischen Seite und Erweiterung.
 *
 * Es läuft in der Seite, hat aber keinen eigenen Zugriff auf die
 * Zwischenablage; es reicht die Bitte an das Hintergrundskript weiter. Die
 * Seite selbst kann die Erweiterung nicht direkt ansprechen, deshalb der
 * Umweg über `window.postMessage`.
 *
 * Das Protokoll ist absichtlich winzig und einseitig: Die Seite fragt, die
 * Erweiterung antwortet. Sie ruft von sich aus nie etwas auf, und sie
 * schickt nichts an irgendjemanden.
 */

const CHANNEL = 'ota-clipboard'

function reply(id, payload) {
  window.postMessage({ channel: CHANNEL, direction: 'from-extension', id, ...payload }, window.origin)
}

window.addEventListener('message', (event) => {
  // Nur Nachrichten aus diesem Fenster und von dieser Herkunft. Ohne die
  // Prüfung könnte ein eingebettetes fremdes Dokument die Zwischenablage
  // über uns auslesen.
  if (event.source !== window) return
  const msg = event.data
  if (!msg || msg.channel !== CHANNEL || msg.direction !== 'to-extension') return

  const { id, action, text } = msg

  if (action === 'ping') {
    reply(id, { ok: true, version: browser.runtime.getManifest().version })
    return
  }

  if (action === 'read') {
    browser.runtime.sendMessage({ type: 'ota-clip-read' })
      .then((res) => reply(id, res ?? { ok: false, error: 'keine Antwort' }))
      .catch((err) => reply(id, { ok: false, error: String(err) }))
    return
  }

  if (action === 'write') {
    browser.runtime.sendMessage({ type: 'ota-clip-write', text })
      .then((res) => reply(id, res ?? { ok: false, error: 'keine Antwort' }))
      .catch((err) => reply(id, { ok: false, error: String(err) }))
  }
})

// Die Seite soll nicht raten müssen, ob die Erweiterung da ist. Sie meldet
// sich einmal von selbst — wer später lädt, kann immer noch "ping" schicken.
window.postMessage({ channel: CHANNEL, direction: 'from-extension', id: 'hello', ok: true }, window.origin)
