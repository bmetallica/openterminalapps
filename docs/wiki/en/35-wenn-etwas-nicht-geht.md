# 35 · When something goes wrong

*For users.* The most common stumbling blocks, what you can do yourself, and what the
administrators need to know from you if it does not help.

## Try this first

| What you see | What you do |
|---|---|
| **"That session is no longer running"** | The session was ended, for example because it was idle. Back to the start page and start again. Your home is still there |
| **Black or frozen picture** | Control bar → **Reconnect**. If that does not help, close the tab and open the session again from the start page |
| **Keyboard does not respond** | Click into the picture once, otherwise control bar → **Focus session** |
| **Copy and paste does not work** | the checklist in [chapter 4](04-zwischenablage.md). As a fallback, the text field in the control bar |
| **Umlauts missing, `/` turns into `?`** | End the session and start it again. If it stays, report it |
| **Picture stutters** | check compute-heavy programs in the workspace (tests, builds, indexing). If permanent: report it |
| **An application in the workspace does not start** | End the session and start it again. Root workspace: stop and resume |
| **Desktop empty, without menu and panel** | End the session and start it again |
| **Page shows "The data could not be loaded"** | Reload the page (F5). Right after an update of the system this is normal |

## Messages when starting

| Message | Meaning | What you do |
|---|---|---|
| **Two-factor is mandatory for your group** | no start without a second factor | **Set it up now** ([chapter 30](30-mein-konto.md#second-factor-)) |
| **"… is already running and uses the same home"** | another workspace has your home open | end the other one ([chapter 31](31-dateien.md#several-workspaces-one-home)) |
| **"Your home uses … GB"** | your home is full | tidy up: downloads, caches, old files. Or ask for more space |
| **"This root workspace uses … GB"** | the workspace itself is full | [chapter 32](32-root-arbeitsplatz-nutzen.md#space) |
| **"At most … applications can be open at once"** | too many applications open | close one |

You find what takes space in your home like this:

```bash
du -sh ~/* ~/.[!.]* 2>/dev/null | sort -h | tail -15
```

Often it is `~/.cache`, `~/Downloads` or old images in `~/.local/share`.

## What the administrators need from you

If none of this helps, write to the administrators:

1. **Which workspace:** the name of the tile
2. **When:** date and approximate time. That lets them find the entry in the log
3. **What exactly:** the message word for word or a screenshot
4. **What you did before:** started, resumed, uploaded a file …
5. **Since when:** only once, or again and again

Under **Operations** the administrators see how busy your workspace is, and they can connect to it
with a terminal. Both are logged.
