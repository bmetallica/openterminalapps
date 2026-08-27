/* Hintergrundskript.
 *
 * Zwei Aufgaben, mehr nicht:
 *
 *  1. Auf Klick die aktuelle Adresse freigeben lassen und die Brücke dort
 *     dauerhaft registrieren. Die Erweiterung kommt ohne jede Seitenberechtigung
 *     ins Haus; wer sie nie anklickt, gibt ihr nie Zugriff.
 *  2. Die Zwischenablage lesen, wenn die Brücke danach fragt. Das passiert
 *     hier und nicht im Inhaltsskript, weil `clipboardRead` an die Erweiterung
 *     gebunden ist, nicht an die Seite.
 */

const SCRIPT_ID = 'ota-clipboard-bridge'

async function origins() {
  const stored = await browser.storage.local.get('origins')
  return Array.isArray(stored.origins) ? stored.origins : []
}

/** Registriert die Brücke für alle bereits freigegebenen Adressen. */
async function refresh() {
  const list = await origins()
  const granted = []
  for (const origin of list) {
    if (await browser.permissions.contains({ origins: [origin] })) granted.push(origin)
  }

  try { await browser.scripting.unregisterContentScripts({ ids: [SCRIPT_ID] }) } catch { /* gab es noch nicht */ }
  if (granted.length === 0) return

  await browser.scripting.registerContentScripts([{
    id: SCRIPT_ID,
    matches: granted,
    js: ['bridge.js'],
    runAt: 'document_start',
    persistAcrossSessions: true,
    allFrames: false,
  }])
}

browser.runtime.onInstalled.addListener(refresh)
browser.runtime.onStartup.addListener(refresh)

browser.action.onClicked.addListener(async (tab) => {
  if (!tab.url) return
  let origin
  try {
    origin = `${new URL(tab.url).origin}/*`
  } catch {
    return
  }

  const ok = await browser.permissions.request({ origins: [origin] })
  if (!ok) return

  const list = await origins()
  if (!list.includes(origin)) {
    await browser.storage.local.set({ origins: [...list, origin] })
  }
  await refresh()

  // Sofort auch im schon offenen Tab, sonst müsste man neu laden.
  try {
    await browser.scripting.executeScript({ target: { tabId: tab.id }, files: ['bridge.js'] })
  } catch { /* dann greift es beim nächsten Laden */ }
})

/* Die Seite fragt über das Inhaltsskript nach der Zwischenablage. Gelesen
   wird ausschliesslich auf Anfrage einer freigegebenen Adresse — die
   Erweiterung sammelt nichts und speichert nichts. */
browser.runtime.onMessage.addListener((msg) => {
  if (msg?.type === 'ota-clip-read') {
    return navigator.clipboard.readText().then(
      (text) => ({ ok: true, text }),
      (err) => ({ ok: false, error: String(err) }),
    )
  }
  if (msg?.type === 'ota-clip-write' && typeof msg.text === 'string') {
    return navigator.clipboard.writeText(msg.text).then(
      () => ({ ok: true }),
      (err) => ({ ok: false, error: String(err) }),
    )
  }
  return undefined
})
