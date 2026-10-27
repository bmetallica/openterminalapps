# 4 · Clipboard, files and sound

Copy and paste is the function a remote desktop platform stands or falls by in everyday use. That
is why it gets its own chapter.

## For users

**The normal case**: Ctrl+C and Ctrl+V work in both directions — from the browser into the session
and back, **and between two applications in the same workspace**. Images too, not just text.

**If it does not work**, check in this order:

1. **Is the page served over `https://`?** Browsers only grant clipboard access over HTTPS. Over
   `http://` it is technically unavailable — that cannot be worked around in the application.
2. **Does the session have focus?** Click into the screen area once. Without focus, keystrokes do
   not reach the session.
3. **Did the browser ask?** Chrome asks for permission on the first read. If it was denied, it is
   listed under the lock icon in the address bar.
4. **Is it allowed in the workspace?** The administrator can turn copy and paste off separately.
   The clipboard panel then says that it is blocked.

**The panel as fallback**: the control bar has a text field in both directions. It always works,
even when the browser refuses the automatic clipboard.

### Firefox ✅

Firefox does not give web pages *automatic reading* of the clipboard. That is not a setting that
could be flipped, but a decision of the browser.

**Without an extension**, OTA uses the paste event there: you press Ctrl+V, and the content is
taken over. That works reliably, but requires the key press in the right window every time.

**With the OTA extension**, Firefox behaves like Chrome: copy and paste sync by themselves. The
extension does nothing else — it passes read access on to exactly one address.

When OTA runs in Firefox and the extension is missing, the control bar shows a notice with a
download button. The way there by hand:

1. Open the control bar in the session (handle on the right edge).
2. Under **Clipboard**, click **Download extension**.
3. In Firefox `about:debugging` → **This Firefox** → **Load Temporary Add-on** → choose the
   downloaded ZIP file.
4. Click the extension's icon in the toolbar while OTA is open. Only this click enables it for this
   address — before that it may do nothing.

The `about:debugging` route only lasts until Firefox restarts. The administrators install the
extension permanently; ask them.

## Between apps in the workspace ✅

Copying in VS Code, pasting in IntelliJ — works.

Technically that is not a given: every application runs on its own X display with its own
clipboard. OTA therefore runs a **bridge** in the container that keeps the content the same across
all running displays. It starts automatically as soon as the second application is opened, and
follows the workspace's permissions — if copying is turned off there, the bridge does not run
either.

**Images go over the bridge too** — since 2026-08-28. Not before, and nobody noticed, because there
was nothing to see: an image does not come out of the clipboard as text. Whoever only asks it for
text gets nothing and considers it empty. A screenshot was thus unreachable in the neighbouring
application, without any message.

**The selection does not travel along.** What you select with the mouse (the X PRIMARY selection)
stays on its display. That is intentional: otherwise every selection in one application would
overwrite the selection in all others.

## Files

Files get into the workspace and out again via **My files**, in the browser and in the control bar
of a running session. What lives where and what is kept is in [chapter 31](31-dateien.md).

## Sound and microphone

Whatever plays sound in the workspace, you hear it in the browser. There is no microphone.
