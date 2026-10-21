# 20 · Selkies — the streaming path

*For administrators.* **Default since the switch to `ota/base-desktop`.** The older path via KasmVNC
remains and is still needed for Kasm images; it can be switched per workspace.

**Since 2026-10-07 Selkies 2.0 runs** — from OTA's own fork, over WebSockets, without TURN. What
applied until then (Selkies 1.6.2 over WebRTC) is in the
[appendix](#appendix-selkies-162-until-2026-10-07) and still applies to golden images that are built
on the old base image.

## What it is about

KasmVNC speaks **RFB**: it transmits rectangular image regions as soon as something changes. For text
and calm interfaces that is exactly right — little bandwidth, razor sharp. For anything that moves it
is the wrong form: a video, a scroll through a long file, a drawing canvas fall apart into lagging
tiles.

**Selkies** instead encodes an H.264 stream. In version 2.0 it goes over **WebSockets** — through the
same port and the same address as OTA's interface — and the browser decodes it with WebCodecs.

## The two paths compared

| | KasmVNC | Selkies 2.0 |
|---|---|---|
| Applications | **one screen per application**, switchable in the bar | the same — one `Xvfb` per application with its own Selkies instance |
| Path of the picture | through Traefik, one port | **through Traefik**, one port (WebSockets) |
| Additional ports | none | **none** |
| Concurrent sessions | any number | any number |
| Clipboard | OTA's bridge between the displays | Selkies' own, built into the picture |
| Sound | via KasmVNC | via WebSockets |
| Encoder | — | H.264 in software (x264); with GPU NVENC or VA-API |

**What changed with 2.0.** Selkies 1.6.2 sent the picture as WebRTC over UDP past Traefik and needed
a TURN server with ports on the host for that, a block list, an answer to small packet sizes in the
VPN and five interventions in its code. With WebSockets all of that is gone: the way to the picture
is the same as the way to the interface, behind a reverse proxy, through a VPN and through a firewall
with NAT.

## Setting up

```bash
scripts/build-desktop-image.sh --pruefen   # builds ota/base-desktop:1 and checks 18 points
```

Then create a template with `image_ref: ota/base-desktop:1`. The streaming engine does **not** have
to be specified — OTA reads it from the image. Everything else stays as for every workspace: home,
shelves, skeleton, start script, permissions.

**Golden images** built on the old base image still carry Selkies 1.6.2 and keep running — via TURN,
as described in the appendix. They get to 2.0 through the package `ota-selkies`
([below](#upgrading-to-20)). **An ordinary rebuild does not do that:** the image builder builds on
the image the template points to — after an activation that is the previous golden image along with
its Selkies. The agent recognises the version itself (by `/dockerstartup/selkies-starten.sh`).

## OTA's fork

Selkies lives **as source code in OTA's repository** (`third_party/selkies/`), with origin, the
release's checksum and every change of our own in `third_party/selkies/OTA-FORK.md`. The package
`ota-selkies` is built from it, and Selkies only gets into an image through this package.

The reason is an experience: on 2026-10-07 the release files of Selkies 1.6.2 had vanished from
GitHub — the project had been renamed, the old releases removed — and OTA's base image could no
longer be rebuilt anywhere. A change upstream should not hit us a second time.

The dependencies are listed completely and with checksums in
`third_party/selkies/ota-abhaengigkeiten.txt`, including the two Rust extensions `pixelflux`
(picture) and `pcmflux` (sound). With the own package repository they lie in the file pool, and the
build needs no internet ([chapter 26](26-paketquellen.md#the-file-pool)).

## The package `ota-selkies`

Selkies from the fork, its dependencies under `/opt/selkies` and OTA's two start scripts
(`desktop_startup.sh`, `selkies-starten.sh`) in **one** Debian package. It lies in the own package
repository, which always runs ([chapter 26](26-paketquellen.md)), and has three consumers:

| Who | How |
|---|---|
| the base image | `scripts/build-desktop-image.sh` builds the package if needed and installs it |
| a golden image | **Software → "Upgrade to …"** (see below) |
| a root workspace | **by itself when resuming** |

The version is called `2.0.0-ota1`: Selkies' version, followed by OTA's revision.

### Upgrading to 2.0

On installation the package replaces a Selkies 1.6.2 that an old base image set up by hand, and
clears away its remains (`packaging/ota-selkies/preinst`). Measured on 2026-10-08: a golden image
from before the switch, upgraded with `apt install ota-selkies`, passes all 18 checks of the new base
image.

- **Ordinary workspaces** are rebuilt from their image on every start. If the template points to
  `ota/base-desktop:1`, rebuilding the base image is enough. If it points to a golden image,
  **Administration → Workspaces → (template) → Software** shows which Selkies is in it and offers
  **"Upgrade to 2.0.0-ota1"**: a build that only adds `ota-selkies`. Everything else in the image
  stays. Then activate the new version.
- **Root workspaces** keep their container. When **resuming**, the agent compares the installed
  version with the one in the package repository, upgrades if needed (also from 1.6.2) and restarts
  the workspace once. What someone installed in the workspace stays — measured, including a file
  under `/opt`. "Rebuild" is no longer needed for this.
- **Running sessions** stay as they are until they end.

Which version is running right now:

```bash
for c in $(docker ps --filter name=ota-s- --format '{{.Names}}'); do
  echo "$c $(docker exec $c dpkg-query -W -f='${Version}' ota-selkies 2>/dev/null || echo 1.6.2)"
done
```

### Changing and rebuilding it yourself

Change the fork (`third_party/selkies/`), the start scripts (`images/base-desktop/dockerstartup/`)
or `packaging/ota-selkies/`, then:

```bash
echo 2 > packaging/ota-selkies/revision          # new revision — mandatory
scripts/build-selkies-deb.sh --hochladen          # build and upload to the package repository
```

It is built in the repo service's image (Debian 13, Python 3.13), the dependencies come with
checksums from the file pool or from PyPI. Duration: about half a minute. **The package repository
does not accept the same version twice** — otherwise two workspaces would have different things
under the same version. From then on root workspaces upgrade themselves at the next resume; the base
image takes the new version at the next `build-desktop-image.sh`, and golden images show "upgrade"
again under Software.

Back to an older version: remove the newer package under **Package sources → Own packages**.
Workspaces that already have it keep it; the agent only upgrades, never downgrades.

`make update` puts the package into the package repository if this version is missing there.
Everything is checked with `scripts/test-selkies-paket.sh` (runs with `make test`).

## What OTA configures in Selkies — and turns off

Everything via settings (`SELKIES_*`), no interventions in the code. They are in one place,
`images/base-desktop/dockerstartup/selkies-starten.sh`, which the main and application screens use
together.

| Setting | Value | Why |
|---|---|---|
| Transport | WebSockets, fixed | one port, through Traefik; WebRTC would not carry here without TURN |
| Sign-in | Basic auth | Traefik sets the header; the password never leaves the server |
| Selkies' sidebar | off | would lie under OTA's handle; OTA governs what is in it |
| File transfer, printing | **off** | bypassing OTA's shelves, permissions and audit log |
| Sharing links, co-players | **off** | a session belongs to one person |
| Commands over the channel | **off** | Selkies' default, explicitly pinned here |
| Microphone, camera, gamepad | off | |
| Second screen | off | several applications are several screens in OTA |
| Clipboard | on, both directions | as before |
| Keyboard layout | before the start (`OTA_KEYBOARD_LAYOUT`) | see [below](#the-keyboard-layout-) |

Selkies 2.0 brings the first five **turned on**. Each of them would have been a new way for data out
of or into the workspace. The base image check reads them back from the running process.

## Checking

```bash
scripts/build-desktop-image.sh --pruefen   # the image, 18 points
scripts/test-streaming.sh                  # through OTA up to the picture, also on an application's screen
```

`test-streaming.sh` creates its own template on the current base image, starts it in a browser in a
foreign network and counts the frames that arrive **decoded** there — on the desktop and on an
application's screen. Measured on 2026-10-07: about 350 frames in 12 seconds, per screen, at window
size.

---

# Appendix: Selkies 1.6.2 (until 2026-10-07)

*Only applies to golden images on the old base image.* There the picture runs as WebRTC over UDP past
Traefik, and everything that follows remains necessary: TURN, its ports, its block list.

`deploy/.env` must state at which address the **browsers** reach this host, and a secret for the
TURN sign-in:

```
OTA_TURN_HOST=192.168.66.224
OTA_TURN_SECRET=…            # openssl rand -base64 32
OTA_TURN_PROTOCOL=udp        # tcp with a small MTU, see below
OTA_TURN_ICE_POLICY=all      # relay with a small MTU, see below
```

Check with `python3 scripts/pruef-turn.py`; the last line must read `TURN vermittelt.` (TURN relays).
Behind a firewall with port forwarding see [chapter 24](24-hinter-nat.md).

## Why the TURN server runs in the stack and not in the session

WebRTC needs a media path over UDP. Session containers lie in an internal Docker network without
published ports — the browser could not get there, and Traefik does not help: it speaks HTTP, not
UDP. Relaying therefore happens through a TURN server.

At first it ran **in the session container**, one per session, with ports the agent passed through to
the outside. That sounded clean — a failure hits one session instead of all — and still cannot work.
A TURN behind a Docker bridge reports the host's address as relay address, but sends the relayed
packets with the container address as sender:

```
2. Allocate mit Anmeldung  -> Relay 192.168.66.224:65502
5. Client -> Relay -> Peer: b'HINAUS' von 192.168.0.4:65502
   Absender != Relay 192.168.66.224:65502  [ausgehend KAPUTT]
```

(The sender does not match the relay address — outgoing broken.)

Every WebRTC stack discards a packet whose sender does not match the candidate it is waiting for.
That is why the service `turn` runs on the **host's network** (`network_mode: host`) — only without
NAT in between do the reported and actual addresses match.

A shared TURN brings along what the previous way could not do: **more than one Selkies session per
host.** The port range is shared once instead of published per container, and the session container
no longer opens any port at all.

Sign-in uses short-lived credentials from an HMAC over `OTA_TURN_SECRET` — Selkies computes them from
the same secret and hands them to the browser with an expiry. The session password is not in them.

The web interface and the signalling still run through Traefik, with the same sign-in and the same
basic auth header as with KasmVNC. **Only the media stream bypasses it.**

## The successor image: Debian 13, without KasmVNC

The first attempt was called `base-selkies` and derived from `base-xfce` — it thereby dragged along
KasmVNC, which never ran there: `Xvnc`, `kasmvncserver`, `kasmvncpasswd` and 3.4 MB of web
interface. That was right as long as Selkies was an experiment on a working foundation, and the wrong
way round once it carried. `images/base-desktop/` therefore starts at `debian:13`:

```bash
scripts/build-desktop-image.sh --pruefen
```

| | Predecessor `base-selkies` | `base-desktop` |
|---|---|---|
| Foundation | Ubuntu 24.04 via `base-xfce` | Debian 13 directly |
| KasmVNC | included, never ran | not present |
| Account / home | `kasm-user` / `/home/kasm-user` | `ota` / `/home/ota` |
| GStreamer | bundle, 1.24.6, 366 MB under `/opt` | from the distribution, 1.26.2 |
| Size | 1.73 GB | 1.78 GB |

The size is the honest drawback: the bundle goes away, but Debian's `gstreamer1.0-plugins-bad` brings
almost the same — CUDA, Vulkan and Wayland parts that a streaming server never touches. Slimming it
down would be a step of its own.

### Selkies 1.6.2 no longer exists on GitHub

Since **2026-10-07** the release addresses of Selkies 1.6.2 return a 404: the project is now called
`selkies-project/selkies`, only carries 2.0 and has removed the old releases. That was the trigger
for the switch to 2.0 and for OTA's own fork (above). A base image with 1.6.2 can no longer be
rebuilt since then; existing images keep running.

### Where the home lives is said by the image

The agent reads `HOME` from the image configuration and mounts the profile there
(`_heimat_aus_env` in `agent/otaagent/main.py`); without it, it stays at `/home/kasm-user`. Foreign
images like `kasmweb/gimp` thus keep running unchanged, and an image of our own determines its path
itself. The value is checked before it serves as a mount target — an image must not determine where
the agent reaches on the host.

In addition, the start script creates a link under the OTA username: `/home/bmetallica` →
`/home/ota`. The same pattern as on the host, where storage is by ID and a readable link is placed
next to it. A rename in Keycloak only moves this link; everything that stored an absolute path in the
profile — editor settings, virtual environments, `git config` — stays valid. Exactly that would break
if the home itself carried the username.

### One application, no desktop

The mode **"Single app"** transmits exactly one application, filling the window, without a panel and
without desktop icons. For that the container only starts a window manager instead of the whole
desktop environment.

Two things interlock:

* The agent passes `OTA_MODE` along. The start script branches on it — before, the container did not
  know its mode and always started XFCE.
* The image builder has the field **Start command**. From it a `custom_startup.sh` is created in the
  built image.

The field is needed because for single applications the image builder deliberately keeps the base
image's start script. For the Kasm application images that is right — they start "their"
application themselves. OTA's own base image, on the other hand, deliberately brings a placeholder
that starts **nothing**; a single-application image built on it therefore showed an empty screen, and
the reason was written nowhere.

The command is put into the Dockerfile via base64 and not written into a `RUN` line: it comes from a
text field and may contain quotes, dollar signs and line breaks.

If the application exits, the start script restarts it after three seconds. For a single application
that is wanted — in the workspace the same supervision once produced 119 empty windows, which is why
a workspace image gets the placeholder.

Checked in the running container: `Xvfb`, `xfwm4`, the application, Selkies, PulseAudio are running
— **no** `xfce4-panel`, `xfdesktop` or `xfce4-session`. The window is at `0 0 1440x900` on a screen of
1440×900, with `_NET_WM_STATE_FULLSCREEN`.

Two pitfalls, both measured:

* **`xfwm4 --daemon` does not exist in Debian.** The window manager exited immediately, and that was
  only visible because `wmctrl` got no window list (`Cannot get client list properties`). Without a
  window manager the application has no frame, does not follow the screen size and cannot be set to
  fill the window. It now runs with `--compositor=off` — without a GPU every redraw happens in
  software, and that compute time belongs to the encoder.
* **`fullscreen`, not `maximized`.** Maximised, the title bar would remain, and with a single
  application there is nothing you would need it for.

### Several applications at the same time — with Selkies too

It once said here that Selkies transmits exactly one screen, so several applications would lie next
to each other on the same one. That was a misunderstanding: it applies to **one** Selkies instance,
not to OTA's workspace model. There every application gets its own screen, filling the window,
switchable in the bar — and several run at the same time from one container.

That is exactly how it now runs with Selkies too, only with different technology behind it:

| | KasmVNC | Selkies |
|---|---|---|
| X server per application | `Xvnc :N` | `Xvfb :N` |
| Stream per application | the same `Xvnc`, port `6900+N` | its own Selkies instance, port `8080+N` |
| Window manager | `xfwm4`, no desktop | same, plus `--compositor=off` |
| Traefik route | `/s/<id>/a/N`, HTTPS | same, HTTP |

Measured on a session with two applications: three displays (`X1 X2 X3`), three `Xvfb`, three Selkies
instances on 8080, 8082 and 8083, the terminal on `:2` and Thunar on `:3` — and both streams deliver
1440×900 in the browser.

The process IDs of `Xvfb` and Selkies are stored per screen. Matching by name fails here: `pkill -f`
searches entire command lines and would find the teardown script itself, whose text contains the
names being searched for.

### The application stays where it belongs

On a screen that belongs to exactly one application, there is no panel through which to get a window
back — neither in a single-application session nor on a workspace's application screens. That is why
in **both** places a supervisor checks every two seconds:

* **Minimised** — comes back up (`_NET_WM_STATE_HIDDEN` → `wmctrl -a`). Measured: `IsUnMapped` right
  after collapsing, `IsViewable` again after five seconds.
* **Not filling the window** — is set to fill it again.
* **Closed** — the application is restarted. In the single-application session the start script's
  supervision does this by running `custom_startup.sh` again; on an application screen the
  supervision in `apps.py`, which runs the start command itself again. Measured: process ended, after
  three seconds a new one runs, window back.

The supervision runs as long as the X socket exists. Whoever ends the application through OTA thereby
tears down its screen — and the supervisor does not start it again. That is the difference between
"I close the window" and "I end this application", and it must be preserved.

Measured on an application screen: minimised `IsUnMapped` until 1.2 s, `IsViewable` again from
1.5 s; un-maximised, maximised again after 600 ms.

### "git — this image does not know it"

The package check reported "unknown" even for obviously present packages, and the suggestions
contradicted themselves:

```
git — kennt dieses Image nicht.
Gemeint war vielleicht: golang-github-awslabs-amazon-ecr-credential-helper-dev …
```

If the suggestion search returns hits, the package list is there. The reason lies one level deeper:
the check reads apt's output and searches it for `Candidate:`. Both are **translated** as soon as the
image sets a language — and OTA's own base image does (`de_DE`):

```
git:  Installiert: (keine)   Installationskandidat: 1:2.47.3-0+deb13u1
```

`Candidate:` does not occur in it, so the field stayed empty and every package counted as unknown.
The suggestion search (`apt-cache search`) reads no labels and kept returning hits — hence the
contradictory picture.

The check now sets `LC_ALL=C LANGUAGE=C LANG=C` before calling apt. That is the rule anyway for
everything whose output is evaluated: whoever parses text pins the language.

### The mouse pointer that sporadically becomes huge

Symptom: the pointer suddenly becomes considerably larger and stays that way for the rest of the
session.

**Why.** Selkies transmits the pointer as an image and the browser draws it via CSS — so its size is
whatever the X server delivers. How large that is, libXcursor decides, and without `XCURSOR_SIZE` it
derives it from the screen size: `min(width, height) / 48`. Measured in this image:

```
Bildschirm 1280x720   ->  Zeigergroesse 15
Bildschirm 3840x2160  ->  Zeigergroesse 45
```

(Screen 1280x720 → pointer size 15; screen 3840x2160 → pointer size 45.)

The Xvfb's frame is 3840×2160, and `--enable_resize` lets the screen grow with the browser window. A
pointer loaded for the first time **afterwards** comes out three times as large as one before — and
the client stores it under its ID and keeps it. Hence "sporadic" (it depends on when a pointer shape
is needed for the first time) and hence "then stays that way".

On a workspace with a full XFCE session it hardly shows: `xfsettingsd` sets the size via XSETTINGS.
On the screens of individual applications it does not run — there is only a window manager, and
nobody announces the size.

**The remedy** is two lines in the image:

```dockerfile
XCURSOR_THEME=Adwaita \
XCURSOR_SIZE=24 \
```

Cross-checked with the same call that showed the bug: 24 at 1280×720 and 24 at 3840×2160.

### Only one bar

The Selkies client brings its own sidebar, whose round button on the right edge lay **exactly under
OTA's handle**. Selkies' gives way: what is in it is almost entirely superfluous here (OTA does
clipboard and scaling), fixed on the server side (relay enforcement) or wrong — *Return to launcher*
leads out of OTA. See `patches/keine-fremde-leiste.py`; the build aborts if the button no longer
occurs exactly once.

### Three traps when switching to Debian

All three had the same shape: the image built green, and the error only showed in the log of the
first session.

1. **`cannot import name '_gi_gst' from 'gi.overrides'`** — The prebuilt Selkies bundle is compiled
   for **Python 3.12**, Debian 13 has 3.13. Distribution and GStreamer are thus linked through Python
   and cannot be swapped individually. Debian's own GStreamer is therefore used.
2. **`Namespace GstWebRTC not available`** — The plugins were there, the introspection data was not.
   It is in `gir1.2-gst-plugins-bad-1.0`.
3. **`ModuleNotFoundError: No module named 'distutils'`** — Removed from the standard library with
   Python 3.12 (PEP 632); Selkies pulls in `GPUtil`, and that needs it. `setuptools` brings the
   replacement.

That is why the Dockerfile now checks itself, and the **build** aborts instead of the first
connection:

```dockerfile
&& gst-inspect-1.0 webrtcbin > /dev/null \
&& gst-inspect-1.0 x264enc > /dev/null \
&& python3 -c "… from gi.repository import Gst, GstWebRTC, GstSdp; …"
…
&& PYTHONPATH="$ORT" python -c "import gpu_monitor, gstwebrtc_app, signalling_web"
```

`selkies-gstreamer --help` is no good as a check, by the way — it requires a running X server.

### The name for the basic auth

From `Session.vnc_user` the API builds the header that Traefik puts in front of the session. **The
name never reached the container until then** — `kasm_user` was hard-coded in the start script there,
and as long as both happened to match, nobody noticed. An image that expects a different name answers
with 401, and the interface shows an empty page.

Now both sides read the same value, and it depends on the streaming engine: `ota` for Selkies,
`kasm_user` for KasmVNC. There the name is not a matter of taste — the Kasm images' password file only
knows this one.

## Networks with a small packet size (VPN)

Whoever accesses through a VPN whose MTU is well below 1500 — WireGuard with 1000, for example — gets
**no picture and no error message**. The session builds up, ICE connects, and then it says "Waiting
for stream".

The reason: **Chrome sends its DTLS handshake with a fixed 1200 bytes per packet and does not adapt
to a smaller path size.** The small ICE checks get through, the big packet does not. The other side
waits for the missing part of the handshake and therefore does not answer at all — that is why no
error appears anywhere. In the session's log it shows in the size pattern of received packets:

```
tragfähiger Weg:  1200, 263, 1200, 263, …
über den Tunnel:  263, 263, 263, …   (und sonst nichts)
```

(Viable path: 1200, 263, …; through the tunnel: 263, 263, … and nothing else.)

The remedy, both lines together:

```
OTA_TURN_PROTOCOL=tcp
OTA_TURN_ICE_POLICY=relay
```

`relay` takes the direct path away from the browser, `tcp` puts the browser–TURN leg into a TCP
stream — and TCP negotiates its segment size with the path itself. The question of packet size no
longer arises.

That costs something: every byte runs through the TURN server, also for users in the same network
who could go directly. As long as only some users come through such a VPN, that is a compromise at
everyone's expense. The clean solution would be to offer the browser both paths and let it choose —
for that Selkies would have to deliver two TURN entries; today it delivers one.

`make test` runs both — the suite `scripts/test-streaming.sh` starts the test browser itself,
measures TURN and stream and cleans up again. It can be demonstrated individually with
`scripts/pruef-selkies.mjs`: the test rig drives a browser that **cannot** reach the session container
directly, and says whether a picture arrives. With a block on large UDP packets
(`iptables … -m length --length 1029:65535 -j DROP`) the error can be reproduced deliberately — it
disappears with the two lines above.

## The keyboard layout ✅

*Found on 2026-09-28 on a fresh installation: no umlauts arrived in VS Code, and `/` did not work.*

Selkies sends not keys but **characters** (keysyms), and the container translates them back into keys
via its X server's key mapping. Xvfb starts with `us`. With a German keyboard in the browser that
meant, measured:

| typed | arrived with `us` | reason |
|---|---|---|
| `ä ö ü ß Ä` | nothing | These characters do not exist on `us` — they are discarded **without a message** |
| `/` (Shift+7) | `?` | Shift stays pressed, and `/` has its own key on `us` |
| `@` (AltGr+Q) | `2` | the same with AltGr |

KasmVNC does not have the problem, it creates missing characters itself. That is why it went
unnoticed for a long time on an installation whose workspaces ran through KasmVNC.

**The setting** is in `deploy/.env` and applies to all Selkies screens:

```bash
OTA_KEYBOARD_LAYOUT=de        # default; ch, fr, us …; empty = do not touch
OTA_KEYBOARD_VARIANT=         # e.g. nodeadkeys
```

It takes effect at the **next start** of a workspace, rebuilding the image is not needed. The agent
passes it to the container, and **Selkies 2.0** gets the layout set before it starts — on the main
screen as on those of the individual applications. Measured on 2026-10-07: typed `aäöüß/Ä@z-`,
arrived `aäöüß/Ä@z-`.

With **Selkies 1.6.2** the agent sets the layout after the start and then restarts Selkies once — it
reads the mapping once at its own start, a layout set later it would never see. Measured with `de`,
but without the restart: `a_²yß` instead of `aäöüß/Ä@z-`, `z` became `y`.

**The layout is one for the whole installation.** It must match the keyboards people sit at, not the
server. Whoever comes to a `de` workspace with a US keyboard has the problem the other way round
(`@` on Shift+2 becomes `"`).

It is checked in `scripts/test-streaming.sh`: `scripts/pruef-tastatur.mjs` types like a German
keyboard into a terminal in the workspace and compares what arrives.

## Five traps, all of them encountered while building

1. **The client builds its addresses from the root.** `fetch("/turn")` and
   `wss://host/<first path segment>/signalling/` — neither points to where an OTA session lives
   (`/s/<id>/`, two segments). Without a fix the page builds up completely, the picture stays black,
   and the console shows a single `401` from OTA's own interface. Both places are replaced when
   building the image (`images/base-desktop/patches/gst-web-pfad.py`) — and if the lines change in
   a new version, **the build aborts** instead of silently doing the wrong thing.

   It is the same bug as back then with KasmVNC, which also appended its WebSocket path to the root
   ([chapter 12](12-fehlersuche.md)).

2. **`cvt` no longer exists in Ubuntu 24.04.** Selkies adapts the resolution to the browser window
   and gets the modeline with it; no package provides it any more (`apt-file` says: none). Without a
   replacement the remote screen stays at the framebuffer's full size — 3840×2160, squeezed into a
   1440 window. The image brings its own calculation, checked against the reference value for
   1920×1080.

3. **coturn may not write to `/var/run`.** As long as it ran in the container, it belonged to user
   1000, and without `pidfile=/tmp/...` it did not start at all — the message was in its own log, not
   where one looks. The service in the stack no longer has the problem; the trap stays here because
   it cost two days.

4. **TURN behind NAT does not relay.** See above. The error shows in three places and in none of them
   as what it is: in the browser "Waiting for stream", in the container `Fatal SSL error` during the
   DTLS handshake, in the TURN log `create_relay_ioa_sockets: no available ports` — the latter only a
   consequence of eleven ports being too few for the many attempts. The cause only becomes visible
   when you send a packet through and compare the sender: `scripts/pruef-turn.py`.

5. **Too small an MTU looks like nothing at all.** See the section above. This bug costs a
   particularly large amount of time because every single layer looks healthy: TURN relays, ICE
   connects, the handshake arrives. Just not entirely. It was only noticed when comparing the packet
   sizes between a working and a failing session.

## What it costs — measured

*Measured with Selkies 1.6.2 (GStreamer, WebRTC). The measurement for 2.0 is still pending.*

For a long time there was a guess here. On **2026-09-03** it was measured, with `make messung`: both
paths at 1280×720, the same load, the same test browser behind the same TURN, on this machine — four
cores, no GPU, x264 in software.

| | Selkies | KasmVNC |
|---|---|---|
| CPU at idle, stream only | **0.34 cores** | **0.00** |
| CPU under load, stream only | 0.38 cores | 0.41 cores |
| Bandwidth at idle | 0.24 Mbit/s | 0.00 |
| Bandwidth under load | **0.45 Mbit/s** | **25.4 Mbit/s** |
| Glass-to-glass response time, median | **46 ms** | 120 ms |
| CPU in the viewer's browser, under load | 0.18 cores | 0.41 cores |

*"Stream only" means: the same load measured once without and once with a viewer, taking the
difference. Both engines only encode when someone is watching; what the application itself costs
cancels out. The load is a full-window terminal with 150 lines of random text per second — enough
for the whole area to change, and little enough that drawing does not eat up the measurement.*

Three things nobody knew beforehand:

**1. Under load Selkies does not cost more — it costs the same.** 0.38 against 0.41 cores. The worry
that H.264 in software is the expensive path was unfounded: KasmVNC does not compress its image
regions for free either.

**2. At idle Selkies costs a third of a core, KasmVNC nothing.** That is the real difference, and it
turns the calculation around: H.264 encodes its 30 frames per second even when nothing moves; VNC
only transmits changes and is otherwise silent. **That is the number capacity depends on** — on four
cores that is about ten idle Selkies sessions, while idle KasmVNC sessions cost practically nothing.

**3. There is a factor of 56 between them in bandwidth.** 0.45 against 25.4 Mbit/s. Whoever sits in
the same network notices nothing. Over a VPN you notice it immediately — and that is exactly where
this installation runs.

Plus two side observations: Selkies' fastest answer was 25 ms and the slowest **2051 ms** — a single
dropout among twelve flashes, probably a lost keyframe. KasmVNC is more even (74 to 136 ms), but
never as fast. And the viewer's browser works more than twice as hard with KasmVNC: it assembles
many small image regions instead of decoding a video stream its hardware knows.

### The obvious knob does not help

`SELKIES_FRAMERATE` in the workspace's environment, default **30**. Half the frame rate should be
half the work — that was the expectation. Measured (same setup, `SELKIES_FRAMERATE=15`):

| at 1280×720 | 30 frames/s | 15 frames/s |
|---|---|---|
| CPU at idle | 0.35 cores | **0.35 cores** |
| CPU under load | 0.46 cores | **0.60 cores** |
| Response time, median | 46 ms | **83 ms** |

**Nothing saved, and everything slower.** At idle the frame rate changes nothing at all, under load
the lower one even costs more — presumably because every frame then carries twice as much change. The
response time dutifully follows the frame interval (66 instead of 33 ms), so the setting did take
effect; it just did not do what it was supposed to.

From this follows: **the base load of a third of a core is not due to encoding.** It must come from
grabbing the screen and the colour conversion, and those run independently of how often encoding
happens. Whoever wants to lower it has to start there — not at the frame rate. That is not measured;
it is the next question, not the answer.

### What follows from it

- **Access via VPN or WAN → Selkies.** A factor of 56 in bandwidth and less than half the response
  time; that is not a matter of taste.
- **Many sessions that mostly idle, on few cores → KasmVNC.** A dozen open but unused workspaces
  cost several cores with Selkies and nothing with KasmVNC. Turning down the frame rate does **not**
  help, see above — that is measured and was a surprise. What helps: setting the idle reaper more
  aggressively, so that idle sessions do not idle in the first place.
- **Kasm images → KasmVNC**, still. They do not bring Selkies.

The raw data is in [`docs/messungen/`](../../messungen/), the measurement rig in
`scripts/mess-streaming.mjs`. The run takes a quarter of an hour and wants a quiet machine — that is
why it is not in `make test`.

## Where it goes from here

The switch was made because the path carries: it runs through Traefik, with OTA's sign-in in front,
behind a VPN with MTU 1000, with several applications at the same time, and the base image manages
without third-party streaming software. The questions that were open here for a long time — what it
costs, how fast it is, whether the model carries — are answered: the first two in the section above,
the third in everyday use. One instance runs per application, and the switcher in the bar has
remained.

**Open since the switch to 2.0** (2026-10-07):

- **What 2.0 costs** is not measured. The numbers in the section "What it costs" come from 1.6.2 with
  GStreamer; 2.0 encodes with `pixelflux` and transmits over TCP. `make messung` still measures the
  WebRTC path and has to be rewritten for 2.0.
- **How many sessions one TURN carries** — only relevant for golden images with 1.6.2 any more. One
  connection occupies four relay ports; the default range of a hundred is enough for about twenty
  concurrent sessions. Calculated, not measured.

Whoever wants to go back sets a workspace to KasmVNC under **Streaming** in the interface. For Kasm
images that is necessary anyway — they do not bring Selkies.
