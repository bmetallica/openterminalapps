# 3 · The workspace

*For users.*

## Your dashboard

After signing in you see two areas:

**Your sessions** — what is running or paused right now. It is at the top because everyday work is
not "pick an app" but "back into my machine".

**Your apps** — what you can start.

A session card shows run time, last activity, CPU and memory. The coloured edge on the left and the
indicator dots tell the state:

| Colour | State |
|---|---|
| Green, pulsing | running |
| Blue | paused — memory stays allocated, resuming takes under a second |
| Grey | stopped — the profile is kept, starting takes a moment again |
| Red | failed |

## Starting apps in the workspace ✅

The workspace carries an **app bar**. A click starts the application or brings it to the front.
Apps with an indicator dot are already running.

Apps that are not started cost **nothing** — their display is only created on the first click and
torn down again when closed.

All apps share:
- the same `/home` with your projects
- your SSH keys and the Git configuration
- **the same clipboard** — copying in VS Code and pasting in IntelliJ works
  ([chapter 4](04-zwischenablage.md))

Whoever prefers a full desktop with a taskbar instead of single full-screen apps finds it in the
bar as its own entry.

## Session view

The control bar is collapsed so the application gets the space. It is opened via the **handle on
the right edge**.

> The shortcut **Ctrl + Alt + Shift** only works while the focus is *not* in the stream. As soon
> as you have clicked into the application, the remote desktop claims the keyboard for itself —
> rightly, otherwise you could not use any key combination there. The handle always works.

Inside: the **switcher between your applications**, the clipboard panel, full screen, reset focus,
reconnect and the way back to the dashboard.

### Every application in its own tab ✅

When opened from the dashboard, an application gets its own browser tab. The dashboard stays in the
first tab — you switch between your applications like between windows on the desktop, instead of
leaving the running application every time.

Every tab has its own address (`/view/s/…`). A bookmark to it leads back into the same application.

### The application grows with the window ✅

The remote screen adapts to the window size. If you drag the browser window larger, the
application's work area grows too — no black border remains, and nothing is scaled. What you see is
the real resolution.

### Pinning to the desktop ✅

On the dashboard, above the tiles, is the section **On the desktop** with the button **Create
shortcut**. Below it each application is listed separately: terminal, VS Code, Firefox, GIMP — and
for templates without apps the whole workspace. A click opens the pinning page of that one
application; you pin it there.

Afterwards you have an icon like for a local program. A click on it opens **its own window without
an address bar and without tabs**, starts the container if none is running yet, and opens the
application in it. If you are not signed in, the sign-in comes first — in the same window, and then
it continues directly. The address stays the same; nothing is redirected.

**Why a separate page and not a button in place:** the browser decides about pinning based on the
manifest that is in the document when it loads — whatever is swapped in afterwards no longer changes
its decision. A button in the middle of the viewer that promises "this application" would in truth
have pinned the dashboard. That is why every application has its own address whose manifest means
it from the start: `/launch/<workspace>/<app>?ablegen`. Without `?ablegen` the same address is the
start — that is the one the icon points to.

**Nothing is started** on the pinning page. Whoever creates an icon does not want to work yet.

If the browser does not offer pinning by itself, the page shows the way through its menu: in Chrome
and Edge via the icon on the right of the address bar, in Firefox via "Install this page".

## The shared shelf ✅

In your home there is a folder **Gemeinsam** (shared). It contains what administration provides for
everyone — certificates, installation packages, templates. It is **read-only**: copy out what you
need.

The same folder is also reachable under `/mnt/ota`, in case you refer to it in a script.

## What happens to your work

Your home directory is **persisted** — projects, settings, extensions, keys. It survives stopping,
restarting and **updates of the golden image**: your home lives on the host and is laid over the
image on every start. New software in the image changes nothing about your settings.

Everything outside `/home` is **not persisted**: system-wide installed packages, changes to `/etc`.
Whoever needs a system package permanently asks the administrator — it belongs in the golden image
([chapter 7](07-golden-images.md)).

## Who else can see your screen

**An administrator can connect to a running session** and then sees the same as you — your open
terminal, your unlocked password store, your mail. Technically this can hardly be prevented:
whoever administers the machine your workspace runs on reaches the same through other paths
anyway.

What OTA makes of it:

* **A supporter cannot.** The permission *See and end all sessions* is explicitly **not** enough for
  it — seeing that something runs and sitting at it are two different things. Only a full
  administrator gets there.
* **It is in the audit log.** Every connection creates an entry with the time, the name of the
  person watching and yours. Readable under **Operations → Audit log**, there as "Connected to
  someone else's screen" — and so verifiable, for example against a works agreement. The entry
  stays for a year; the daily sign-in and session data expires after 90 days.
* **You do not notice it today.** A notice in the picture while someone else is watching is
  planned and not built yet. Until then the audit log is the way to check.

## Automatic sign-out ✅

If OTA stays unused for a while, you are signed out and have to sign in again. How long that takes
is set by administration ([chapter 11](11-betrieb.md)); by default it is eight hours.

The timeout counts **inactivity**, not time: as long as you work, it restarts with every request.
Being signed out in the middle of typing cannot happen.

Unaffected by this, your container keeps running — its own timeout in the next section applies to
it.

## Automatic ending

Without activity the session is paused, stopped or deleted after a set time. What applies is shown
on the card. Ten minutes before, a notice appears with the option to extend, if the policy allows
it.

**In all three cases your profile is kept.** "Deleted" refers to the container, not your files.

## Resetting the profile

Under *Settings* there is **Reset profile**. It restores the golden image's delivery state. A backup
is made automatically beforehand — but it is an intervention, not a tidy-up button.
