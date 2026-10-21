# 19 · The own base image

> **Note.** This chapter describes `ota/base-xfce` — Ubuntu + XFCE + KasmVNC. It is **no longer the
> default**: since the switch to Selkies that is `ota/base-desktop` (Debian 13, without KasmVNC),
> described in [chapter 20](20-selkies-versuch.md). `base-xfce` remains and is maintained as long as
> workspaces run on it — for Kasm images it is still the right path.

*For administrators.* ✅ `ota/base-xfce` — Ubuntu 24.04 + XFCE + KasmVNC, without applications.
**Available as a test image** and does not replace anything yet.

## Why have one at all

Until now every workspace derives from a Kasm application image — `kasmweb/vs-code` and relatives.
That brought along three things that get in the way there:

1. **An application that starts by itself.** Kasm images for single applications bring a
   `custom_startup.sh` that starts "their" application, and `vnc_startup.sh` restarts this script
   **every three seconds** as soon as it exits. In a workspace that is devastating: measured on
   2026-08-27 there were 119 empty VS Code windows after six minutes, 2.5 GB used, black screen. OTA
   therefore mounts a script of its own over it.
2. **20 GB for an editor the workspace does not even start.**
3. **The label `com.kasmweb.image`.** In "Aggressive" mode, Kasm's cleaner deletes exactly the images
   that carry it and are not in its database every 30 seconds — a freshly built golden image was gone
   seconds later.

And three small things were missing that the clipboard depends on: `clipnotify`, `xsel`,
`autocutsel` ([chapter 4](04-zwischenablage.md)).

**965 MB instead of 20 GB.** The own base image contains no application — that is added when building
the golden image ([chapter 7](07-golden-images.md)).

## Building and checking

```bash
scripts/build-base-image.sh              # builds ota/base-xfce:test
scripts/build-base-image.sh --pruefen    # builds and checks it afterwards
scripts/build-base-image.sh --nur-pruefen
```

The check is no formality. It starts the container the way OTA starts it and measures 27 points
against the **contract with the agent**:

| What | Why it is checked |
|---|---|
| KasmVNC accepts on **6901** | That is how the agent recognises that the session is ready |
| ID **1000**, home `/home/kasm-user` | That is where the agent mounts the profile; the shelves on disk belong to 1000:1000 |
| `.kasmpasswd` with the name **`kasm_user`** | Before the stream OTA sets a basic auth header with exactly this name. With `kasm-user` (hyphen) the screen asks for a password nobody knows |
| `.vnc/self.pem` | KasmVNC only listens with TLS (`-sslOnly`) |
| `Xvnc`, `xauth`, `mcookie`, `xfwm4`, `wmctrl`, `xdotool` | With these the agent opens further displays and starts applications on them |
| A **second display**, an application on it | The core of the workspace model |
| `clipnotify`, `xsel`, `autocutsel` and the bridge | Clipboard event-driven instead of every half second |
| **No** `com.kasmweb.image` | Otherwise Kasm's cleaner removes it |
| `ota/arbeitsplatz` lies unchanged next to it | The proof that nothing existing was touched |

With `OTA_PRUEFE_JAVA=1` acceptance case 7 is added (Java/AWT, standing in for IntelliJ). It does not
run by itself because it installs a JDK into the **test container** — around 300 MB. That does not
belong in the image: a base image that every workspace derives from does not carry a JDK around just
so a test finds it.

## It is called `:test`, and that is intentional

No template points to it, `ota/arbeitsplatz` stays untouched. Only once a workspace demonstrably runs
on it as before does it become a version without `test` in its name.

Whoever wants to try it creates **their own template** with it (Workspaces → New, `image_ref` to
`ota/base-xfce:test`) and leaves the existing one alone. Two templates with
`persistence_scope: user`, however, share the same home — give the trial template its own profile
under *Persistence*, otherwise OTA refuses the second session.

## KasmVNC stays in — the licence question is checked

KasmVNC is under **GPL-2.0-or-later**; looked up not in a blog post but in
`/usr/share/doc/kasmvncserver/copyright` in the built image. Taking it over unchanged from the
official release and starting it as a program of its own is exactly the case the GPL is made for.

It is even **cleaner than before**: `kasmweb/*` images are MIT only for the build recipes — the
finished image is a bundle of third-party software under "Other". Ubuntu + XFCE + the official
KasmVNC package, by contrast, consists of individually traceable parts. In detail in
[chapter 13](13-lizenzen.md) and in `THIRD-PARTY-NOTICES.md`.

Obligations only apply once an image leaves the building. Then the bill of materials goes with it:

```bash
make sbom          # one bill of materials per image in SPDX and CycloneDX, to sbom/
```

## And something entirely our own instead of KasmVNC?

The question came up while building, and the answer is: **home-grown would mean worse here.** x11vnc
is single-threaded and unmaintained for years; TigerVNC is the trunk KasmVNC branches from — we would
be leaving out precisely the parts that make it (multi-threaded WebP encoding, `DLP_ClipDelay`,
`KasmPasswordFile`). A protocol of our own would be person-years.

Only a **change of method would really be better: WebRTC instead of RFB**, with GStreamer and
H.264/VP8 — lower latency, usable video, GPU encoding. The price is just as real: UDP and a TURN path
through the ingress, an audio chain, and reconnect, idle disconnect and the interface's clipboard
are written against the KasmVNC client's interface. That is a milestone of its own with its own
acceptance — a second test image alongside, and then measured instead of believed (`roadmap.md`).
