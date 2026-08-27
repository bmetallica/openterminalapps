/**
 * Zwischenablage-Bruecke zwischen Browser und Session.
 *
 * Warum es die braucht: KasmVNCs Weboberflaeche schaltet die Zwischenablage
 * ab, sobald sie in einem iframe laeuft. In `ui.js` steht sinngemaess
 *
 *     window.self !== window.top && !readSetting("show_control_bar")
 *         ? initSetting("clipboard_up",   false),
 *           initSetting("clipboard_down", false)
 *         : ...
 *
 * und `clipboardReceive()` verwirft anschliessend jeden Inhalt, den der Server
 * schickt, weil `rfb.clipboardDown` false ist. Das passiert lautlos: keine
 * Meldung in der Konsole, kein Fehler, das Feld bleibt einfach leer. Gemessen
 * am 2026-08-27 mit demselben Container einmal als eigene Seite und einmal im
 * Viewer — als eigene Seite kam der Text an, im iframe nie.
 *
 * Deshalb haengt die API `clipboard_up=1&clipboard_down=1` an die Stream-
 * Adresse (siehe `STREAM_ARGS` in `api/ota/routers/sessions.py`).
 * `initSetting()` liest zuerst die Adresse und erst danach den Vorgabewert,
 * also gewinnt der Parameter.
 *
 * Den Abgleich mit der System-Zwischenablage macht bewusst nicht der Client,
 * sondern diese Bruecke: Der Stream kommt von derselben Herkunft wie die
 * Anwendung, also laesst sich der Client von aussen ansteuern.
 *
 *   Session → Browser   `#noVNC_clipboard_text` aendert sich, sobald der
 *                       Container etwas kopiert. Wir schreiben den Wert in
 *                       die System-Zwischenablage.
 *   Browser → Session   Wir setzen den Wert und loesen `change` aus; der
 *                       Client ruft daraufhin `clipboardPasteFrom` auf.
 *
 * Drei Wege fuer die Richtung Browser → Session, absteigend nach Bequemlichkeit:
 *   1. `readText()` im Takt, solange das Fenster den Fokus hat. Braucht die
 *      Berechtigung, ist dann aber unsichtbar.
 *   2. Das `paste`-Ereignis. Braucht keine Berechtigung und funktioniert auch
 *      in Firefox, greift aber erst beim Druecken von Strg+V.
 *   3. Das Panel in der Kontrollleiste. Funktioniert immer.
 */


import { extensionPresent, isFirefox, readViaExtension, writeViaExtension } from "./firefoxClipboard"

const PANEL_ID = "noVNC_clipboard_text"
const POLL_MS = 700

export type BridgeState = {
  /** Konnte die System-Zwischenablage gelesen werden? */
  canRead: boolean
  /** Konnte in die System-Zwischenablage geschrieben werden? */
  canWrite: boolean
  /** Zuletzt in Richtung Browser übertragen. */
  lastToBrowser: string | null
  /** Zuletzt in Richtung Session übertragen. */
  lastToSession: string | null
}

export type Bridge = {
  stop: () => void
  /** Text von Hand in die Session schieben — für das Panel im Viewer. */
  pushToSession: (text: string) => boolean
  /** Aktueller Stand, für die Anzeige in der Kontrollleiste. */
  state: () => BridgeState
}

function panelOf(frame: HTMLIFrameElement): HTMLTextAreaElement | null {
  try {
    return (frame.contentDocument?.getElementById(PANEL_ID) as HTMLTextAreaElement) ?? null
  } catch {
    // Andere Herkunft — dann bleibt nur das Panel in der Kontrollleiste.
    return null
  }
}

export function startClipboardBridge(
  frame: HTMLIFrameElement,
  opts: { onNote?: (text: string) => void } = {},
): Bridge {
  const state: BridgeState = {
    canRead: false, canWrite: false, lastToBrowser: null, lastToSession: null,
  }

  let stopped = false
  let notifiedDenied = false
  // Was der Browser noch nicht annehmen wollte. Firefox erlaubt das Schreiben
  // nur unmittelbar nach einer Nutzergeste; der Kopiervorgang passiert aber in
  // der Session, also ohne Geste im Elternfenster. Wir heben den Text auf und
  // versuchen es beim naechsten Klick oder Tastendruck erneut.
  let pending: string | null = null
  // Firefox gibt Webseiten den Lesezugriff nicht. Ist die Erweiterung da,
  // laeuft beides ueber sie; sonst bleibt es beim `paste`-Ereignis.
  let viaExtension = false

  const win = (): Window | null => {
    try { return frame.contentWindow } catch { return null }
  }

  /** Die Zwischenablagen, die wir ansprechen duerfen — innere zuerst.
   *
   * Der Zugriff auf `contentWindow.navigator` wirft einen `SecurityError`,
   * solange das iframe noch `about:blank` zeigt oder gerade auf eine neue
   * Adresse umschaltet: In diesem Moment hat sein Dokument eine eigene,
   * undurchsichtige Herkunft. Das passiert bei jedem Wechsel der Ansicht im
   * Arbeitsplatz und ist voellig normal — nur darf es nicht als Fehler aus dem
   * Intervall herausfallen, sonst steht er in der Konsole und die Brücke
   * ueberspringt den Takt.
   */
  const clipboards = (): Clipboard[] => {
    const out: Clipboard[] = []
    try {
      const inner = win()?.navigator?.clipboard
      if (inner) out.push(inner)
    } catch { /* andere Herkunft, gleich kommt die eigene */ }
    if (navigator.clipboard) out.push(navigator.clipboard)
    return out
  }

  /** Schreibt in die System-Zwischenablage.
   *
   * Bewusst über das Fenster des iframes: Der Browser erlaubt das Schreiben
   * nur dem Dokument, das gerade den Fokus hat — und während jemand in der
   * Session arbeitet, ist das der Stream, nicht die Anwendung darum herum.
   */
  async function writeSystem(text: string): Promise<boolean> {
    if (viaExtension && await writeViaExtension(text)) {
      state.canWrite = true
      return true
    }
    for (const clip of clipboards()) {
      if (!clip.writeText) continue
      try {
        await clip.writeText(text)
        state.canWrite = true
        return true
      } catch {
        /* nächster Versuch */
      }
    }
    state.canWrite = false
    return false
  }

  /** Zweiter Anlauf, sobald jemand das Fenster wieder anfasst. */
  const flushPending = () => {
    if (stopped || pending === null) return
    const text = pending
    void writeSystem(text).then((ok) => { if (ok && pending === text) pending = null })
  }

  async function readSystem(): Promise<string | null> {
    if (viaExtension) {
      const text = await readViaExtension()
      if (text !== null) {
        state.canRead = true
        return text
      }
    }
    for (const clip of clipboards()) {
      if (!clip.readText) continue
      try {
        const text = await clip.readText()
        state.canRead = true
        return text
      } catch {
        /* nächster Versuch */
      }
    }
    state.canRead = false
    return null
  }

  function pushToSession(text: string): boolean {
    const panel = panelOf(frame)
    const w = win()
    if (!panel || !w) return false
    if (text === state.lastToSession) return true

    try {
      panel.value = text
      // Genau dieses Ereignis hängt der Client ab; es löst clipboardPasteFrom
      // aus. Der Konstruktor muss aus dem Fenster des iframes stammen, sonst
      // verwirft dessen Dokument das Ereignis als fremd.
      const EventCtor = (w as unknown as { Event: typeof Event }).Event
      panel.dispatchEvent(new EventCtor("change", { bubbles: true }))
    } catch {
      // Das iframe wechselt gerade die Adresse. Beim nächsten Takt erneut.
      return false
    }
    state.lastToSession = text
    return true
  }

  // ---------------------------------------------------------- Session → Browser
  //
  // Der Client legt empfangene Inhalte im Panel ab. Ein MutationObserver
  // greift hier nicht: Der Wert eines textarea ändert sich als Eigenschaft,
  // nicht als Attribut. Deshalb im Takt nachsehen — 700 ms sind für Menschen
  // nicht spürbar und kosten einen Feldzugriff.
  const timer = window.setInterval(() => {
    if (stopped) return
    const panel = panelOf(frame)
    if (!panel) return

    const value = panel.value
    if (value && value !== state.lastToBrowser && value !== state.lastToSession) {
      state.lastToBrowser = value
      void writeSystem(value).then((ok) => {
        if (!ok) pending = value
        if (!ok && !notifiedDenied) {
          notifiedDenied = true
          opts.onNote?.(
            "Der Browser gibt die Zwischenablage nicht frei. Kopierter Text " +
            "steht im Feld der Kontrollleiste.",
          )
        }
      })
    }
  }, POLL_MS)

  // ---------------------------------------------------------- Browser → Session
  //
  // Solange das Fenster den Fokus hat, den Systeminhalt nachziehen. Damit
  // liegt er bereits in der Session, bevor jemand Strg+V drückt — sonst käme
  // die Tastenkombination vor den Daten an und fügte den alten Inhalt ein.
  const pull = window.setInterval(() => {
    if (stopped || !document.hasFocus()) return
    void readSystem().then((text) => {
      if (text && text !== state.lastToSession) pushToSession(text)
    })
  }, POLL_MS * 2)

  // Rückfall ohne Berechtigung: das Einfüge-Ereignis. Es liefert den Inhalt
  // mit, ohne dass der Browser etwas freigeben muss — der Weg, den Firefox
  // ohnehin verlangt.
  const onPaste = (e: Event) => {
    const text = (e as ClipboardEvent).clipboardData?.getData("text")
    if (text) pushToSession(text)
  }

  function attachInner() {
    const w = win()
    try {
      w?.addEventListener("paste", onPaste, true)
      w?.addEventListener("focus", () => {
        void readSystem().then((t) => { if (t) pushToSession(t) })
      }, true)
    } catch { /* andere Herkunft */ }
  }

  window.addEventListener("paste", onPaste, true)
  window.addEventListener("pointerdown", flushPending, true)
  window.addEventListener("keydown", flushPending, true)
  frame.addEventListener("load", attachInner)
  attachInner()

  // Einmal nachsehen, ob die Firefox-Erweiterung mitspielt. Nur in Firefox —
  // in Chrome waere das eine Sekunde Warten auf eine Antwort, die nie kommt.
  if (isFirefox()) {
    void extensionPresent().then((yes) => {
      viaExtension = yes
      if (yes) {
        state.canRead = state.canWrite = true
      } else {
        opts.onNote?.(
          "Firefox gibt die Zwischenablage nicht frei. Einfügen geht mit " +
          "Strg+V, für den bequemen Weg gibt es die OTA-Erweiterung.",
        )
      }
    })
  }

  // Einmal aktiv nach der Berechtigung fragen. Chrome zeigt die Abfrage erst,
  // wenn tatsächlich gelesen wird; ohne diesen Anstoss bliebe sie aus, und
  // die bequeme Richtung liefe nie an.
  void readSystem()

  return {
    stop() {
      stopped = true
      window.clearInterval(timer)
      window.clearInterval(pull)
      window.removeEventListener("paste", onPaste, true)
      window.removeEventListener("pointerdown", flushPending, true)
      window.removeEventListener("keydown", flushPending, true)
      frame.removeEventListener("load", attachInner)
      try { win()?.removeEventListener("paste", onPaste, true) } catch { /* egal */ }
    },
    pushToSession,
    state: () => ({ ...state }),
  }
}
