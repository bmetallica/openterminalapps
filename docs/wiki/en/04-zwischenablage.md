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

#### Installing permanently ⚠️

The `about:debugging` route only lasts until Firefox restarts. For permanent use there are two
ways, and both need a decision outside OTA:

| Way | What to do | When it makes sense |
|---|---|---|
| **Enterprise policy** | Distribute `policies.json` with `ExtensionSettings`, have the extension installed from an internal address | The usual way in a company. Firefox also accepts unsigned extensions this way when they come through the policy |
| **Signing by Mozilla** | Submit the extension to addons.mozilla.org (also as "unlisted", then without publishing) | When no policies can be rolled out |

Firefox ESR additionally allows `xpinstall.signatures.required=false`. That is convenient, but lifts
the signing requirement for **all** extensions — so only where that is a conscious choice.

The source is in `extension/firefox/` and is less than a hundred lines. Whoever wants to review it
before rolling out finds three files there: the manifest, the background script and the bridge to
the page.

## Between apps in the workspace ✅

Copying in VS Code, pasting in IntelliJ — works.

Technically that is not a given: every application runs on its own X display with its own
clipboard. OTA therefore runs a **bridge** in the container that keeps the content the same across
all running displays. It starts automatically as soon as the second application is opened, and
follows the workspace's permissions — if copying is turned off there, the bridge does not run
either.

This is checked with:

```bash
./scripts/test-clipboard-bridge.sh
```

Sixteen checks: both directions, umlauts, multi-line code with tabs, **an image**, **a megabyte of
text**, the behaviour **after pause and resume** and the case that the clipboard is **turned off**
in the workspace.

**Images go over the bridge too** — since 2026-08-28. Not before, and nobody noticed, because there
was nothing to see: an image does not come out of the clipboard as text. Whoever only asks it for
text gets nothing and considers it empty. A screenshot was thus unreachable in the neighbouring
application, without any message.

**The selection does not travel along.** What you select with the mouse (the X PRIMARY selection)
stays on its display. That is intentional: otherwise every selection in one application would
overwrite the selection in all others.

## For administrators

### Settings per workspace ✅

In the workspace editor under **Permissions → Clipboard**:

| Switch | Effect | Technically |
|---|---|---|
| Allow paste | Browser → session | `AcceptCutText` |
| Allow copy | Session → browser | `SendCutText` |
| Transfer images | `image/png` in addition to text | `DLP_ClipTypes` |
| Select and middle click | X PRIMARY selection in addition to Ctrl+C | `SendPrimary` / `SetPrimary` |

By default copy, paste and images are **on**, without a size limit. The PRIMARY selection is
**off** — it surprises users who do not expect selecting to copy.

Groups can be stricter than the workspace, never more generous.

### What matters in the implementation

These points regularly fail in home-grown solutions, and **silently**:

1. **HTTPS is mandatory.** `navigator.clipboard` only exists in a secure context. That is why TLS
   in OTA is not a hardening measure but a prerequisite.
2. **The iframe needs explicit permission.** The session viewer embeds the stream. Without
   `allow="clipboard-read; clipboard-write"` the permissions policy blocks everything, without an
   error.
3. **Do not rely on `readText()` alone.** Firefox does not provide it. The standard way is the
   `paste` event, `readText()` only as an extra.
4. **The server must not take anything back.** Traefik sends in OTA
   `Permissions-Policy: clipboard-read=(self), clipboard-write=(self), …` — a restrictive default at
   this point makes everything else ineffective.
5. **The KasmVNC client turns off the clipboard in an iframe by itself.** It checks
   `window.self !== window.top` and then sets `clipboard_up` and `clipboard_down` to `false`;
   received content is discarded afterwards — without an error, without a message. OTA therefore
   appends `clipboard_up=1&clipboard_down=1` to the stream address, because parameters in the
   address beat the client's default. Whoever rebuilds the viewer or assembles the address
   themselves must carry these parameters along, otherwise the way out of the session is dead
   again.

### Acceptance

"Copy-paste works" is not a testable statement. The complete matrix with twelve cases is in
`plan.md` §10.5. The two cases that experience shows slip through: IntelliJ (Java treats the X11
clipboard in its own way) and the path between two apps in the same workspace.

**Eleven of twelve cases run automatically on every test run** (`make test`):

| | |
|---|---|
| Browser → session, session → browser, multi-line text with umlauts | `tests/e2e.mjs`, in a real iframe |
| Between two apps, both directions | `scripts/test-clipboard-bridge.sh` |
| An image (`image/png`) | same — since 2026-08-28 |
| A megabyte of text, complete and not truncated | same |
| PRIMARY on the same display, **and** that it does not cross the display boundary | same |
| After pause and resume | same |
| Off means off, and it comes back when turned on again | same |
| Between **two sessions** of the same user | `tests/e2e.mjs` — two real containers, the path goes through the browser's system clipboard |
| A browser **without `readText()`** | `tests/e2e.mjs` — in Chromium with `readText` turned off. Not a substitute for a run in Firefox, but it checks exactly the path that applies there, on every run |

The twelfth is **IntelliJ**, or rather Java/AWT. It runs on request:

```bash
OTA_PRUEFE_JAVA=1 scripts/build-base-image.sh --nur-pruefen
```

Not on every run, because it installs a JDK into the test container (~300 MB). That does not belong
in the image — a base image that every workspace derives from does not carry a JDK around just so a
test finds it.

> **Why Java has its own line.** X11 has no storage where something lies: there is an *owner* of
> the selection, and whoever wants the content asks the owner. AWT serves this question from its
> own thread and gives up ownership as soon as the virtual machine ends. A program that copies and
> exits immediately therefore leaves an empty clipboard — this does not happen with Gtk and
> Electron applications.

### Events instead of polling

Since 2026-09-01 the bridge waits for events instead of asking every half second:
`clipnotify -l` per display reports every change. This is decided **inside the container** — if
`clipnotify` is missing (as in all Kasm images), it stays with polling. Both paths share the same
sync logic underneath.

The gain is not the load but the delay: with polling there is up to half a second between copying
and pasting during which the neighbouring application still has the old content. Whoever is quick
enough pastes the previous one — and that looks like a bug nobody can reproduce. With events it is
milliseconds.

`clipnotify` is in OTA's own base image ([chapter 19](19-eigenes-basisimage.md)).

## Files

**Upload** places files in the session's `Uploads` folder. **Download** passes files from the
session on to the browser. Both can be turned off per workspace.

For large or permanent amounts of data, network drives are the better way
([chapter 8](08-nutzer-und-gruppen.md)).

## Sound and microphone

Audio output is streamed into the browser and can be switched per workspace. The microphone is
**off** by default and additionally needs the browser's permission.
