# 12 · Troubleshooting

The cases documented here actually occurred while building. What they have in common is that they
fail **silently** — nothing crashes, it just does not work.

## "This session is no longer running", although it was just started

This page comes from the guard in `deploy/traefik/dynamic/session-guard.yml`. It answers when **no**
session router matches an `/s/…` path.

This used to happen right after start: Traefik's Docker provider only notices a new container on its
next pass, but the interface opened the stream immediately. In the gap between, there was no route.

**Fixed:** the API only reports a session as `running` once Traefik knows its route
(`_wait_for_route()` in `api/ota/routers/sessions.py`), and the agent additionally waits until
KasmVNC in the container accepts connections. If the route does not appear, the session stays on
`starting` instead of `running` — the dashboard then keeps trying instead of showing a dead end.

If the page still appears, the session really is gone: ended, cleaned up or the container died. A
look at **Operations → Sessions** shows what applies.

## Sessions fail erratically — and somewhere else every time

This was the nastiest case so far, because it never looked the same twice. The symptoms, all from
the same cause:

- `Startskript in ota-s-… endete mit 137` (start script ended with 137) — that is SIGKILL
- a one-time script that returns nothing, and OTA consequently records it as "not run"
- `KasmVNC in ota-s-… war nach 40s noch nicht bereit` (not ready after 40 s)
- three 409s right afterwards: `container … is not running`
- in the interface: "The workspace is not running right now", although it was just started

All they had in common was that it happened more often **under load** and hardly on a quiet
machine. Exactly that leads astray: it looks like lack of memory. It was not — the container used
231 MB of 3 GB, and nothing was killed by the kernel for memory.

**The cause** lay two levels higher. The API created the session row with `flush`, not with
`commit`. A `flush` only writes *within* its own transaction; for every other connection the session
did not exist until the final `commit` — and that only came when the container was fully up:
skeleton copied, one-time scripts run, start script through, KasmVNC ready. Under load that takes
more than a minute.

In exactly this window the **reaper** runs (`_reap_once` in `api/ota/main.py`, every minute). It sees
a container with an OTA label, finds no session for it in the database — and removes it. In the
middle of starting. The longer the start took, the more likely the hit.

**Fixed** at both ends:

1. The session row is **committed before the container is created**. From then on it exists for
   every connection.
2. The reaper additionally compares the **session ID** from the container label, not only the
   `container_id` — that is not in the row yet during start.

The cause is checked, not the symptom: `scripts/test-authz.sh` starts a session in the background
and meanwhile looks in the database with a **second** connection whether the row is there.

> **The lesson**, in case something similar shows up: when failures are erratic and more frequent
> under load, the temptation is great to turn timeouts. Here that would only have shifted the
> window. The question that helped was not "why is it too slow", but "who is killing the process".

## The stream breaks off after minutes, although the limit is set to hours

Two causes that together produced exactly this picture: you watch a build or read a long document,
touching neither mouse nor keyboard — and at some point the picture is gone and does not come back.
In **Operations → Sessions** the session is still `running`.

**First: the client had its own clock.** KasmVNC disconnects by itself after 20 minutes *without
input*; only mouse and keyboard count, not the picture content. Watching counts as doing nothing
there. Because `reconnect` is off in the client, it stayed black afterwards.

```js
// from the client, /usr/share/kasmvnc/www/assets/ui-*.js
const s = (Date.now() - rfb.lastActiveAt) / 1000
let l = 1200                                     // 20 minutes if nothing is set
if (Number.isFinite(parseFloat(rfb.idleDisconnect))) l = parseFloat(rfb.idleDisconnect) * 60
if (s > l) window.location.replace("disconnect…")
```

**Fixed:** OTA decides about a session's lifetime, not the client. The viewer sets the clock to a
year when connecting (`set_idle_timeout` in `web/src/screens/SessionViewer.tsx`), and the stream
address additionally raises it to 60 minutes (`STREAM_ARGS` in `api/ota/routers/sessions.py`). As
long as a window is open, a heartbeat comes every 30 seconds; only when it stops does the template's
`idle_minutes` apply.

One trap: `idle_disconnect` is a selection field in the client with exactly four values (10, 20, 30,
60). Another value in the address is not taken over but falls back to the **first** entry — a
well-meant `525600` became a measured 10 minutes. A `0` is even worse: the limit is then zero
seconds, and the connection drops immediately. Hence the detour via the message to the running
client, which bypasses the selection field.

**Second: a disconnect did not heal.** If the connection broke for a reason OTA does not know — an
intermediary in the network that clears out a silent connection, a computer going to sleep —
KasmVNC's own disconnect screen stayed in the iframe. It is hidden; in the window you only saw a
frozen picture.

**Fixed:** the viewer watches the connection from outside. As long as it stands, the root element in
the iframe carries the class `noVNC_connected`; its disappearance is the signal. Then it reloads the
stream, with growing intervals and at most eight times, and meanwhile shows a banner with a "try
now" button. If the session has really ended in the meantime, it says so instead of trying further.

Measured: disconnect detected after 5 seconds, reconnected on the second attempt, banner gone by
itself. The whole path is checked in `tests/e2e.mjs` (section session viewer).

## An application can no longer be started and the tab stays dead

If an application's X display in the workspace dies — crash, `Xvnc` gone — OTA kept listing it as
`running`. The start button then seemingly did nothing: the call saw the entry, considered
everything fine and returned immediately. That left the application dead forever.

**Fixed:** the start checks with the agent whether the display really still exists
(`_display_lebt()` in `api/ota/routers/sessions.py`). If it is missing, the entry is set to `stopped`
and the application is opened anew. If the agent does not answer at all, the display counts as
alive — a disturbance while checking must not clear away a running application.

## Clipboard does not work

Check in this order:

**1 · Is the page served over HTTPS?**
`navigator.clipboard` only exists in a secure context. Over `http://` the clipboard is technically
unavailable. → [chapter 10](10-zertifikate-und-https.md)

**2 · Does the iframe allow it?**
The session viewer embeds the stream. Without `allow="clipboard-read; clipboard-write"` the
permissions policy blocks access — **without an error message**. That is the most common cause in
home-grown solutions.

**2b · Has the client turned off the clipboard in the iframe?**
KasmVNC does that by itself as soon as it is not the top page. Open the stream's control bar in the
viewer and check, or in the browser console:

```js
const d = document.querySelector('.viewer__frame').contentDocument
d.getElementById('noVNC_setting_clipboard_down').checked   // must be true
```

If the value is `false`, the parameters are missing from the stream address. It must contain
`…&clipboard_up=1&clipboard_down=1`. The way **out of the session** is otherwise dead, and
completely silently: no error, no console message, the field stays empty. The way **into the
session** keeps working independently — so if only one direction is missing, this is the first
suspicion.

**3 · Does the server take it back?**
```bash
curl -sI --cacert deploy/certs/ota-ca.crt https://<host>:8443/ | grep -i permissions-policy
```
Expected: `clipboard-read=(self), clipboard-write=(self), …`
If the header is missing or restrictive, it makes everything else ineffective.

**4 · Firefox?**
Firefox does not give web pages `navigator.clipboard.readText()`. Whoever only develops against
Chrome only notices with the first Firefox user. OTA uses the `paste` event there.

**5 · Does the session have focus?**
Without focus in the iframe, keystrokes do not reach the stream.

**6 · Is it allowed in the workspace?**
Permissions → Clipboard. Copy and paste can be switched separately.

**7 · Between two apps in the same workspace?**
Every app runs on its own X display with its own clipboard. That is what the bridge in the container
is for. Check whether it runs — and whether copying is allowed in the permissions at all, because
otherwise it deliberately does not start. → [chapter 4](04-zwischenablage.md)

## VS Code opens, but the screen stays empty

**Symptom:** VS Code starts in the workspace, the stream connects — and no picture comes. Or: the
container fills up with memory for no recognisable reason.

**Cause (fixed on 2026-08-27), two layers:**

**1 · The inherited start script.** Kasm images for single applications bring a
`/dockerstartup/custom_startup.sh` that starts "their" application. `vnc_startup.sh` supervises this
script and **restarts it every three seconds** as soon as it exits. In a workspace image derived
from it, that is devastating: the script called `code`, VS Code is single-instance, the second
instance passed the call on to the first and exited — whereupon the supervisor started it again.
After six minutes: 119 empty VS Code windows, 2.5 GB used, black screen.

OTA now mounts a replacement script over it in workspace containers that starts nothing, and newly
built workspace images bring it along. The agent starts applications on request.

**2 · The saved window state.** VS Code remembers its open windows and restores them on the next
start. After such a window storm the number is in the profile — and the storm repeats on every
start, even after the cause is fixed.

**Repairing an affected profile.** The order matters: first end VS Code, then change the file.
Otherwise VS Code writes its old state back when exiting.

```bash
CN=<container>   # docker ps --filter "label=ota.session_id"

docker exec -u 1000 "$CN" pkill -f /usr/share/code/code
sleep 3

docker exec -i -u 1000 "$CN" python3 - <<'EOF'
import json, pathlib
p = pathlib.Path("/home/kasm-user/.config/Code/User/globalStorage/storage.json")
d = json.loads(p.read_text())
d.setdefault("windowsState", {})["openedWindows"] = []
p.write_text(json.dumps(d))
EOF
```

Then restart the application from the dashboard. How many windows are really open is shown by

```bash
docker exec "$CN" bash -lc 'export HOME=/home/kasm-user XAUTHORITY=$HOME/.Xauthority
  DISPLAY=:1 wmctrl -l'
```

Exactly two lines are right: `Desktop` (the wallpaper) and the application.

## Two workspaces cannot be started at the same time

**Message:** "… is already running and uses the same home."

That is not a fault but intentional. All workspaces with persistence **per user** share the same
`/home/kasm-user`. Two running containers on one home caused damage twice in practice:

- The startup of the Kasm images rewrites `~/.kasmpasswd` — the second container thereby invalidated
  the credentials of the first (see the section on 401).
- VS Code places its control channel as a socket in the profile. The second container found it and
  sent its windows into the *first* container.

**What to do:** either end the other workspace — or give the second workspace the setting **per
workspace** under *Resources → Persistent profile*. Then it gets its own home and both run side by
side. The price: separate settings and projects.

## "The data could not be loaded" after an update

**Cause (fixed on 2026-08-27):** `Base.metadata.create_all()` creates missing **tables**, but not
missing **columns**. A new column in the model therefore meant: the start reported "schema ready",
and afterwards every query on this table failed with

```
column templates.start_script does not exist
```

For the user it looked like "Unexpected error. The operation was aborted."

**Fixed:** missing columns are added at start (`api/ota/schema_sync.py`). What happens is in the
log:

```bash
docker compose -f deploy/docker-compose.yml logs api | grep "Spalte ergänzt"
```

It only completes, **adds** — never deletes, never renames, never changes a type. A column missing
from the model can be a forgotten leftover or the sign that the database is newer than the code; in
the second case deleting would be data loss. What cannot be added safely — a column without a
default that must not be empty — is reported and requires a manual migration.

## "At most 6 applications can be open at once", although none is running

**Cause (fixed on 2026-08-27):** the display number was derived from the **position in the app
catalog**. So the limit did not apply to applications open at the same time but to the size of the
catalog: from the seventh entry on, an application could never be started. Alphabetically it mostly
hit VS Code and VSCodium.

**Fixed:** the first free display is assigned, measured by the running streams. The catalog may be
of any size; at most six are open at the same time, as before.

## An application opens, the screen stays black

First look at the application's log in the container:

```bash
docker exec <container> cat /tmp/ota-app-<slug>.log
```

**The most common finding with Electron and Chromium applications** (VS Code, VSCodium, Chrome,
many chat programs):

```
Failed to move to new namespace: ... errno = Operation not permitted
FATAL: Check failed: . : Invalid argument (22)
```

These programs set up their sandbox via PID namespaces; in the container that fails. They need
`--no-sandbox`. The `.desktop` file says nothing about it — it is written for a normal desktop.

OTA now recognises this when *looking inside the image*: a program next to which a file
`chrome-sandbox` lies gets the switch by itself. If it is not yet in an older catalog entry, looking
through again and taking over is enough.

## The desktop is empty — no menu, no panel

Then `xfce4-panel` is missing from the golden image. Early workspace images had deliberately removed
it, because applications are started through OTA; for the desktop as a view, however, the panel is
needed.

Add it via *Software → Packages*: `xfce4-panel` and `xfce4-whiskermenu-plugin`, build, activate.
Running sessions get it on their next start.

## A running session suddenly answers with 401

**Symptom:** a workspace is running, the picture was there a moment ago — and suddenly every one of
its streams returns `401`. Signing in again does not help. The container keeps running, `docker ps`
shows it, the applications in it are working.

**Cause (fixed on 2026-08-27):** all sessions of a user share the same `/home/kasm-user` — that is
the point of the persistent profile. The startup of the Kasm images, however, rewrites
`~/.kasmpasswd` from `VNC_PW` on *every* container start. If someone started a second session, it
thereby overwrote the password of the first one that was already running. Its Traefik rule kept
sending the old credentials — KasmVNC rejected them.

The bug was inconspicuous because nothing had happened to the running session: no restart, no error
in the log, just 401 out of nowhere.

**Fix:** the VNC password is now tied to the profile and no longer to the session (`vnc_secret()` in
`api/ota/security.py`). Whoever shares the same home shares the access — and an overwrite writes the
same value.

**Checking whether it happens again:**

```bash
# If the container shows a PID file with a foreign host name, another
# container has written into the same profile.
docker exec <container> bash -c 'hostname; ls /home/kasm-user/.vnc/*.pid'
```

If host name and PID file do not match, two containers are on the same profile — that is normal. If
401 still comes then, the passwords have drifted apart; end the affected sessions once and start
them again.

## Traefik creates no route — everything returns 404

**Cause A: Docker API version.**
Docker 29 removed all API versions below 1.40. Older Traefik versions announce themselves with a
fixed 1.24. The Docker provider then stays **completely silent** — no route is created, without
anything looking wrong in the configuration.

```bash
docker logs ota-traefik 2>&1 | grep "too old"
# "client version 1.24 is too old. Minimum supported API version is 1.40"
```

Remedy: Traefik ≥ v3.7 (negotiates the version) and `DOCKER_API_VERSION` in `deploy/.env`.

**Cause B: the container counts as not healthy.**
Traefik ignores containers whose health check is not green — without comment.

```bash
docker logs ota-traefik 2>&1 | grep -i "filtering"
# "Filtering unhealthy or starting container: web-ota-…"
docker inspect ota-web --format '{{.State.Health.Status}}'
```

**Cause D: Docker was restarted, Traefik was not.** ✅ *found on 2026-10-19*
With `live-restore` the containers survive a restart of the Docker service. The service, however,
creates `/var/run/docker.sock` **anew**, and Traefik stays attached to the old socket. From then on
it no longer sees any new container. Running sessions stay reachable, every new one stays on
"starting". The log says so continuously:

```bash
docker logs --since 5m ota-traefik 2>&1 | grep -c "Cannot connect to the Docker daemon"
systemctl show docker -p ActiveEnterTimestamp       # later than the start of ota-traefik?
docker inspect ota-traefik -f '{{.State.StartedAt}}'
```

Remedy: `docker restart ota-traefik`. All sessions are reachable again afterwards. The agent hangs on
the same socket, but is recreated with every `make update` and therefore rarely affected. When in
doubt, restart it as well.

**Cause C: CLI arguments are ignored.**
Traefik reads the static configuration from **exactly one source**. As soon as a `traefik.yml`
exists, `command:` arguments in Compose are **completely ignored** — they are not merged. Everything
static belongs in the file.

## Container stays "unhealthy", although the service is running

A classic: the health check asks `http://localhost/...`, but in the container `localhost` resolves
to `::1` first, while the service only listens on IPv4.

```bash
docker inspect <container> --format '{{range .State.Health.Log}}{{.Output}}{{end}}'
# "wget: can't connect to remote host: Connection refused"
docker exec <container> sh -c 'netstat -tln'
# tcp 0.0.0.0:80 LISTEN   ← IPv4 only
```

Remedy: in the health check use **`127.0.0.1`** instead of `localhost`.

For Traefik itself, `traefik healthcheck --ping` additionally needs an enabled `ping:` section in the
static configuration — if it is missing, the container stays unhealthy permanently.

## Browser warns about the certificate

Normal as long as the local CA is not imported. → [chapter 10](10-zertifikate-und-https.md)

If the warning remains **after** importing, the matching name is usually missing from the
certificate:

```bash
openssl x509 -in deploy/certs/ota.crt -noout -ext subjectAltName
```

Modern browsers ignore the common name completely — the name being called must be in the SAN.
Whoever accesses via an IP needs an `IP Address:` entry there, not `DNS:`.

## Session does not start

**Not enough memory.** OTA checks the actually free memory before starting and refuses with a
message instead of letting the host run into the OOM killer. Check: `free -h` and the capacity
gauge above the workspace list.

**Image missing.** On the first start of a new workspace it is pulled. A 6 GB image takes its time;
the start dialog shows the phase.

**Too many sessions.** The limit per user is in the group settings.

## No picture, although the session is running

Almost always the WebSocket connection. If an additional reverse proxy sits in front, it must let
WebSocket upgrades through and set `X-Forwarded-Proto: https`. Without that no picture appears.


## Session loads, but no picture comes

The page appears but stays black or shows "Connecting…". Almost always the WebSocket.

**Cause A: the client looks for the WebSocket in the wrong place.**
The KasmVNC client appends its path to the **root** of the page, not to the current path. Without a
countermeasure it tries `wss://host/websockify` — that lands at the web interface, which delivers
the application with HTTP 200 for every path. No upgrade, no picture, and **no error message in the
server log**.

OTA therefore gives the client the full path as a URL parameter:

```
/s/<session-id>/?path=s/<session-id>/websockify
```

Recognisable in the browser console:
```
WebSocket connection to 'wss://…/websockify' failed:
Error during WebSocket handshake: Unexpected response code: 200
```

**Cause B: an upstream proxy does not pass WebSockets through.**
It must forward upgrade requests and set `X-Forwarded-Proto: https`.

## All session routes disappear at once

Symptom: `/s/<id>/` suddenly answers with the web interface instead of the stream, and all session
routers are missing in the Traefik dashboard.

```bash
docker logs ota-traefik 2>&1 | grep "cannot be linked"
# "Router s-… cannot be linked automatically with multiple Services: [...]"
```

**Cause**: as soon as a container defines more than one Traefik service — for a workspace there is
one per app display — **every router must name its service explicitly**
(`traefik.http.routers.<name>.service=<name>`). If that is missing, Traefik discards **all** routers
of this container, not only the ambiguous ones.

Because such a request otherwise lands at the web interface and is answered there with 200, from
the outside it would look like a session without sign-in. OTA therefore puts a guard over `/s/`
(`deploy/traefik/dynamic/session-guard.yml`): it only applies when no session router matches, still
requires a sign-in, and then answers with an understandable message instead of the application.

## An app in the workspace does not start

```bash
docker exec <session-container> ls /tmp/.X11-unix/     # which displays are running
docker exec <session-container> cat /tmp/ota-display-3.log
docker exec <session-container> cat /tmp/ota-app-<slug>.log
```

If the file `ota-app-<slug>.log` is missing completely, the application was never started. If
`X<n>` is missing under `/tmp/.X11-unix/`, the display did not come up.

**Two common causes:**

*The application is single-instance.* VS Code, Chrome and Thunderbird only run once per user. A
second call reports to the running instance and exits — the log file stays empty, the display black.
Check with `docker exec <container> pgrep -a <application>`. Solution: enter the fixed display in
the app catalog (manual, chapter 7).

*The self-hit in process matching.* `pgrep -f <name>` finds the start script itself, because its
command line contains the name — the script then considers itself the running application and exits.
OTA therefore checks via the display's window list, not via process names. The same trap applies to
`pkill -f`: it kills its own shell. That is why the clipboard bridge is controlled exclusively via
its PID file.

## Umlauts do not arrive, `/` becomes `?`

Only for workspaces with **Selkies**. The keyboard layout in the container does not match the
keyboard in the browser: umlauts disappear without a message, characters on Shift or AltGr arrive
wrong.

```bash
grep KEYBOARD deploy/.env                            # OTA_KEYBOARD_LAYOUT=de ?
docker exec -u 1000 <ota-s-…> sh -c 'DISPLAY=:1 setxkbmap -query'   # layout: de ?
```

If the line is missing (installations before 2026-09-28): `git pull`, `sudo make update`, end the
workspace and start it again. If the layout is right and it still does not work, it was set **after**
Selkies had started. That happens, for example, when someone calls `setxkbmap` by hand: Selkies only
reads the mapping at start. Restart the workspace. Background in [chapter 20](20-selkies-versuch.md),
"The keyboard layout".

## The shortcut Ctrl+Alt+Shift does not work in the stream

That is how it is and cannot be fixed. The remote desktop claims the keyboard for itself — otherwise
you could not use any key combination there. Measured: Control and Alt still reach the embedded
window, Shift and letter keys no longer do.

**The handle on the right edge** lies in the parent window and always works. It is the actual way to
the control bar; the shortcut is the shortcut for everything outside the stream.

## Golden image has disappeared again after the build

The build runs through, reports success — and on the first session start it says "Image is not on
this host".

**Cause**: if Kasm Workspaces runs on the same Docker host, its agent cleans up every 30 seconds in
"Aggressive" mode. It deletes **exactly the images that carry the label `com.kasmweb.image=true`**
and are not in its database. A golden image derived from a Kasm image **inherits this label** and is
therefore classified as an orphaned workspace version.

```bash
docker logs kasm_agent --since 5m | grep -i prune
# "Docker image id (...): with tags (['ota/...']): is not needed."
# "Successfully pruned unneeded Docker image id (...)"
```

**Fixed.** OTA's builder deletes the label in every generated Dockerfile:

```dockerfile
LABEL com.kasmweb.image="" \
      org.opencontainers.image.title="OpenTerminalApps Golden Image"
```

Kasm does not even look at images without this label. That way OTA and Kasm run side by side
permanently, **without anything having to be changed in Kasm**.

This can be checked on the built image:

```bash
docker image inspect ota/<name>:v1 \
  --format '{{index .Config.Labels "com.kasmweb.image"}}'
# empty = right.  "true" = the image will be deleted.
```

OTA also notices it itself: 45 seconds after a successful build it checks whether the image is still
there. If it is missing, the build counts as failed and the log names the reason.

**Fallback**, in case another system cleans up by other rules: a build can pause foreign cleanup
services for its duration (`pause_foreign_cleanup`, default `kasm_agent`). They are started again in
any case — even if the build fails.

## Build reports success, the image never shows up in `docker images`

Different symptom, different cause: on a host with the **containerd image store**, the classic
Docker builder does not store a usable image for multi-platform base images.

```bash
docker info | grep -i snapshotter
#   driver-type: io.containerd.snapshotter.v1
```

OTA therefore builds via `docker buildx build --load`. Whoever writes their own build scripts should
do the same — `DOCKER_BUILDKIT=0` or the Python SDK are not enough here.

## A workspace suddenly is on nobody's dashboard any more

**Symptom.** The workspace is listed in administration, is turned on, the image is there — and still
no user sees it. No error either, anywhere.

**Cause.** Its group assignment is empty. Until 2026-08-28 a `PUT /api/templates/{id}` that did not
mention `group_ids` at all was enough: a missing field counted as an empty list, and whoever only
wanted to change one setting took the assignment away from everyone.

**Checking.**

```bash
curl -sk -b cookies.txt https://<host>:8443/api/templates \
  | python3 -c 'import sys,json;[print(t["slug"], t["group_ids"]) for t in json.load(sys.stdin)]'
```

If it says `[]`, that is it.

**Repair.** In the workspace editor under *Allocation*, set the group again.

**Fixed.** `group_ids` is now `None`-capable: not sent means "leave it", an empty list means "nobody
any more". A check in `scripts/test-authz.sh` pins that down.

## Firefox reports "CanCreateUserNamespace() clone() failure: EPERM"

**Symptom.** This line is in the log under `/tmp/ota-app-firefox.log`. Firefox starts anyway and
works.

**This is not an error**, but the consequence of a deliberate decision: since 2026-08-27 the
workspace container no longer gets `CAP_SYS_ADMIN`. Docker's default seccomp filter only allows own
user namespaces with this capability, and without them Firefox falls back to a weaker internal
sandbox.

The trade is deliberate: Firefox's sandbox protects against a malicious website, and in the worst
case that lands in exactly the container where the user has a terminal anyway. `SYS_ADMIN`, on the
other hand, is a way **out of** the container ([chapter 11](11-betrieb.md)).

## An AppImage no longer starts

**Symptom.** An AppImage installed via recipe aborts, often with a message about FUSE or
`/dev/fuse`.

**Cause.** The same as above: no `CAP_SYS_ADMIN`. An AppImage normally mounts itself via FUSE at
start, and that needs this capability.

**Repair.** Since 2026-08-27 the AppImage recipe creates a launcher that sets
`APPIMAGE_EXTRACT_AND_RUN=1` — the AppImage unpacks itself and starts from there. Whoever has an
older recipe adds to their script:

```bash
cat > /usr/local/bin/<name> <<'RUN'
#!/bin/sh
export APPIMAGE_EXTRACT_AND_RUN=1
exec /opt/<name>.AppImage "$@"
RUN
chmod +x /usr/local/bin/<name>
```

It costs a moment at start and nothing else.

## Freezing hangs and never comes back

**Symptom.** *Freeze session* runs and runs. No error, no message, no progress. `docker ps` shows the
container as **Paused**.

**Cause.** `docker commit` pauses the container itself for the duration of the capture — and an
already paused container cannot be paused a second time. The call then waits for something that
never happens.

Two ways led there, both measured on 2026-08-28:

1. The container was **already** paused before — usually by the idle reaper.
2. The reaper paused it **in the middle of the capture**.

**Fixed, in two places:** the agent checks the container's state before freezing and wakes it up —
it does not rely on what the API believes it knows about the container. And the reaper leaves
sessions alone whose workspace is currently being built or frozen.

**If it does hang:**

```bash
docker ps --filter "name=ota-s-" --format '{{.Names}} {{.Status}}'
docker unpause <container>     # the capture then continues
```

## A workspace can no longer be started, it only says "starting"

**Symptom.** The start button does nothing visible. The session is on `starting` and stays there —
even after minutes, even after reloading. No container is to be seen.

**Cause.** An earlier session of the same template is still listed as alive in the database, but its
container is gone. At start OTA returns an already running session instead of creating a second one
— and so got the same corpse every time.

A timeout led there: if Traefik does not report the route of a new container within 25 seconds, the
session stays on `starting`. Afterwards nothing checked again.

**Checking.**

```bash
docker compose -f deploy/docker-compose.yml exec -T db psql -U ota -d ota \
  -c "SELECT id, status, container_id FROM sessions WHERE status IN ('starting','running');"
docker ps --filter "label=ota.session_id" --format '{{.Names}}'
```

If there is a session there without a container, that is it.

**Fixed on 2026-08-28**, in two places: the start itself checks whether the container still exists
and closes the session if not. And the reaper clears away such corpses on every run — even without
anyone attempting a start.

## `pruef-turn.py` reports "403 Forbidden IP"

**Symptom.** The session starts, the tab stays empty, and the check says:

```
3. Erlaubnis für 192.168.1.22:59236 -> ABGELEHNT: 403 Forbidden IP
```

The TURN server refuses the permission for the peer because its address is in its **block list**.
Check which range applies:

```bash
grep denied-peer-ip deploy/turn/turnserver.conf
```

The file is generated by `scripts/turn-config.sh` and contains only two things: the universally
unusable ranges (0.x, loopback, link-local) and the **concrete** subnets of `ota_internal` and
`ota_public`, read from `docker network inspect`. If your own address lies in one of them, the LAN
overlaps with a Docker network — then the Docker network should be moved, not the block list
changed.

> **How this came about:** until 2026-09-10 the list was fixed in the Compose file, with guessed
> ranges. One read `192.168.0.0-192.168.15.255` and was wrong twice over: it blocked none of the own
> networks (those were elsewhere), and it broke **every installation whose LAN is in 192.168.0.x or
> 192.168.1.x** — that is, the most common addressing of all. Found while setting up on fresh
> Debian. Nothing is guessed any more, and `scripts/test-streaming.sh` checks that the own address
> lies in no blocked range.

**The uplink explicitly does not belong in the list.** A workspace's traffic reaches the TURN
service behind the router's NAT, so under its uplink address. Whoever blocks this network blocks the
very video stream they are trying to set up.

## Old audit log entries have disappeared

**Symptom.** The audit log has nothing from three months ago any more, and the entry you are looking
for is gone.

That is no loss but the retention period: **90 days for behavioural data** (sign-ins, sessions, app
starts), **365 days for administrative actions**. Check whether and when cleanup happened:

```sql
SELECT ts, detail FROM audit_log
 WHERE action = 'protokoll.aufgeraeumt' ORDER BY ts DESC LIMIT 5;
```

If there is an entry with the numbers, the cleaner has worked — the action logs itself, so that a
gap in the data does not look like an outage. Whoever needs to look back further raises
`OTA_PROTOKOLL_VERHALTEN_TAGE` in `deploy/.env` or sends the entries to a collector; `0` turns
deletion off and is then a decision ([chapter 11](11-betrieb.md), [`dsgvo.md`](../../../dsgvo.md)).

**What never disappears, because it is in the long class:** who created whom, which permissions were
granted, which rule was entered — and who connected to someone else's screen.

## "Too many failed attempts", although nobody mistyped

**Symptom.** The local sign-in answers with **429**, even with the right password.

Two different brakes can be behind it, and they sit in different places:

| Answer | Who brakes | What helps |
|---|---|---|
| `Too many failed attempts. Please try again in N minutes.` | OTA: eight failed attempts from **this** address | Wait, or sign in from another place — the lockout applies per sender |
| Empty answer with 429, without a message | Traefik: more than ten attempts per minute from this address | Wait a minute |

**The second case hits a whole company at once** if a reverse proxy sits in front and its address is
**not** in `OTA_TRUSTED_PROXIES`: then for Traefik every request comes from the same address, and
everyone shares ten attempts per minute. Check:

```bash
grep OTA_TRUSTED_PROXIES deploy/.env
cat deploy/traefik/dynamic/anmeldebremse.yml     # is the proxy under excludedIPs?
```

If it is not there: enter it, `sudo make up`. The file is regenerated in the process.

Lifting a lockout by hand:

```bash
docker compose exec db psql -U ota -d ota \
  -c "UPDATE users SET locked_until = NULL, failed_logins = 0, failed_from = NULL
      WHERE username = 'notfall';"
```

## Suddenly nothing reaches the network from the workspace

**Symptom.** The workspace is running, the picture arrives, but no page loads in the browser inside
it — or `apt` hangs.

The picture does **not** go through the router; that it arrives says nothing about the workspace's
network. In order:

```bash
docker ps --filter name=ota-firewall            # is the router running at all?
docker logs --tail 50 ota-firewall              # what does it say?
docker exec ota-firewall nft list table inet ota | head -40
```

| Picture | Cause |
|---|---|
| The router is not running | Without it **no** workspace has network. `docker compose up -d firewall` |
| It is running, but the session is in none of its networks | Happens after a restart of the router. The sync catches up by itself every 30 seconds — if it stays that way, the reason is in the agent's log |
| Only a particular destination does not work | Default: the company network is closed. Enter a rule, globally or in the profile ([chapter 23](23-netz.md)) |
| An allowed **name** does not work | The application asks via encrypted DNS (DoH) and thus not the router's name service. Allow the address instead of the name |
| Nothing works at all, not even name resolution | The profile is set to **isolated**. It says so on the user's dashboard too |
| No name resolution, although everything is allowed | The router asks the wrong server: `docker exec ota-firewall grep ^server= /etc/dnsmasq.d/ota.conf`. If it says `9.9.9.9`, the installation is older than 2026-10-06 (the router did not read the host's servers) — `git pull`, `make update`, or set `OTA_FW_DNS_UPSTREAM` immediately. **Rules change nothing about it**: name resolution always goes through the router |

> **Where a packet ends, and why** — [chapter 23](23-netz.md) has five diagrams for that, one each
> for the three levels, a rule by name and a port forward. They answer the question faster than any
> rule set dump.

**A workspace can in principle not be pinged from the host** — the session networks are `internal`,
the host's bridge has no address there. That is not a bug but the design. Whoever wants to look
inside goes through `docker exec`.

## After a host restart no workspace has network

**Symptom.** After a restart of the host everything runs — except `ota-firewall`. `docker ps -a`
shows it as `Exited (128)` or `(255)`, `docker inspect ota-firewall -f '{{.State.Error}}'` says:

```
failed to set up container networking: Address already in use
```

**Cause (fixed on 2026-09-25).** Router and Traefik hang in every session network. The router has a
fixed address there (`.2`), Traefik got an arbitrary one until then. If Traefik starts before the
router after a restart, `.2` is free — Traefik takes it, and Docker can no longer attach the router
with its address. It then **does not start at all**, and `restart: unless-stopped` does not try
again. Since then Traefik has the last address in the network (`.254`), the agent moves old
attachments once at the first sync and starts a router left lying like that itself.

By hand, on an installation of an older state:

```bash
docker inspect ota-traefik -f '{{range $k,$v := .NetworkSettings.Networks}}{{$k}} {{$v.IPAddress}}{{"\n"}}{{end}}'
docker network disconnect -f <network with .2> ota-traefik
docker start ota-firewall
```

## Traefik does not start: "network ota-n-… not found"

A failed `docker network connect` stays in the container's configuration (`invalid IP` in
`docker inspect`). If the network is removed afterwards, Docker refuses the next start. Since
2026-09-25 the agent removes such a half entry immediately. On an affected installation it helps to
recreate the container — the agent attaches the session networks again at the next sync:

```bash
docker compose -f deploy/docker-compose.yml --env-file deploy/.env up -d --force-recreate traefik
```

## A root workspace does not start, or Docker inside it does not work

See the table at the end of [chapter 25](25-root-arbeitsplatz.md). The most common cases: Sysbox is
missing (`docker info | grep -i runtimes`), the permission "Use root workspace" is missing, the
storage limit is reached, or the image is not `ota/base-desktop-root:1`.

**"Your home uses … GB", although `du` in the container shows much less.** The account's whole
folder is counted, that is the homes of all templates and workspaces, including deleted ones. Until
2026-10-20 core dumps (`core.<pid>`) of crashed programs came on top, up to several GB each; OTA
cleans those up itself now ([chapter 11](11-betrieb.md#ota-cleans-up-core-dumps-itself-)). Where
the rest is: `du -sh /srv/ota/profiles/<id>/* | sort -h`. As an administrator the workspace can still
be started under Operations — the limit does not apply there.

**`apt install sysbox-ce` asks for `docker rm $(docker ps -a -q) -f`.** Do not run it — that deletes
every container on the host. `scripts/sysbox-einrichten.sh` sets up Sysbox without a restart.

## Useful commands

```bash
cd /opt/openterminalapps/deploy

docker compose ps                                   # state of all services
docker compose logs -f --tail=100 ota-traefik       # follow Traefik
curl -s http://127.0.0.1:8449/api/http/routers | python3 -m json.tool   # active routes
docker inspect <container> --format '{{.State.Health.Status}}'

# Traefik verbose when routes are missing: level: DEBUG in traefik.yml,
# afterwards set it back to INFO — DEBUG is very chatty.
```
