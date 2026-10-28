# 11 · Operations, backup and updates

## Services

| Container | Task | Status |
|---|---|---|
| `ota-traefik` | Ingress, TLS, routing to the sessions | ✅ |
| `ota-web` | Interface (served statically) | ✅ |
| `ota-api` | REST API, sign-in, permissions, business logic | ✅ |
| `ota-agent` | The **only** service with Docker access; starts containers and displays | ✅ |
| `ota-db` | PostgreSQL 16 | ✅ |
| `ota-firewall` | **The router of all workspaces**: nftables, NAT, name service, port forwards. Without it no workspace has network | ✅ |
| `ota-turn` | Relays the media stream for golden images with Selkies 1.6.2 (WebRTC). Selkies 2.0 does not need it | ✅ |
| `ota-repo`, `ota-repo-web` | The own package repository, with `ota-selkies`; the mirror in it only with `OTA_REPO_SPIEGEL=1` ([chapter 26](26-paketquellen.md)) | ✅ |
| `ota-registry` | Own registry for the built images | ✅ |
| `ota-keycloak` | Identity provider, shipped or turned off | ✅ |
| `ota-worker` | The idle and orphan reapers currently run inside `ota-api` | ✅ partly |

**What a restart costs**, per service:

| Restart of | Effect on running workspaces |
|---|---|
| `ota-api`, `ota-web`, `ota-agent` | **none.** The video stream goes directly through Traefik to the container |
| `ota-traefik` | The video stream hangs for a few seconds, then the viewer reconnects |
| `ota-firewall` | The workspaces are **briefly without network**. The sync restores the connection by itself (every 30 s); whoever is downloading at that moment sees an abort |
| `ota-db` | The interface reports errors; running streams notice nothing |

### Why the agent is separate

The Docker socket is equivalent to root on the host. The API processes user input and therefore
does **not** get it. Only the agent talks to Docker, through a narrow internal interface. Traefik
gets the socket read-only.

## Networks

| Network | Who | Purpose |
|---|---|---|
| `ota_public` | Traefik, web, API, Keycloak, TURN | reachable from outside |
| `ota_internal` | API, DB, agent, registry | `internal` — no way out |
| `ota_uplink` | The router | its **only** way out |
| `ota-n-<session>` | one workspace + the router each | one per session, `internal`, without a default route |

**A shared network for all sessions no longer exists since 2026-09-04.** It was the reason why
workspaces could reach each other and the agent: on the **same** bridge `iptables` does not apply at
all as long as `br_netfilter` is not loaded — so a rule against it would have achieved nothing.
Every session now gets its own network, created by the agent, and all end in the router. Structure
and usage: [chapter 23](23-netz.md), reasoning: [`firewall.md`](../../../firewall.md).

The session networks are `internal` and the host's bridge has **no address** there. A workspace can
therefore not be pinged from the host — that is not a bug but the point. Whoever wants to look
inside:

```bash
docker exec -it ota-s-<id> bash
docker exec ota-firewall nft list table inet ota | less    # the whole rule set
```

## Everyday

```bash
cd /opt/openterminalapps/deploy

docker compose ps                  # state
docker compose logs -f ota-api     # logs
docker compose restart ota-api     # restart one service
docker compose down                # stop everything (sessions keep running!)
```

> A restart of API or interface **does not interrupt running sessions**. Traefik routes directly to
> the session containers; the application is not involved in the data stream. That is a deliberate
> advantage of the design and makes updates during operation uncritical.

## Logs ✅

Every container keeps **10 MB in three files**, then Docker throws away the oldest. Configurable via
`OTA_LOG_MAX_SIZE` and `OTA_LOG_MAX_FILE` in `deploy/.env` — for the services **and** for every
workspace.

```bash
docker compose logs -f ota-api          # follow
docker inspect ota-traefik --format '{{.HostConfig.LogConfig.Config}}'
du -sh $(docker inspect ota-traefik --format '{{.LogPath}}')
```

**Without this limit Docker writes until the disk is full**, and that is no grey theory: on this
installation Traefik's log was at 23 MB after four days, because every rejected request lands there
with its sender address — around two gigabytes a year, for a single service. If the disk fills up,
everything stops at once, the database first.

A workspace is the chattiest container of all: X server, window manager and every application write
to stdout. An application in a crash loop would thereby fill the **host's** disk — and hit all
workspaces, not just its own.

> **The setting only takes effect when a container is recreated** (`make update`), not on a mere
> restart. Running workspaces keep theirs until their next start.

**That is also the retention period.** The logs contain IP addresses; without a limit an
installation keeps them forever. They now disappear when the file is overwritten, and not only when
someone cleans up ([`dsgvo.md`](../../../dsgvo.md), section 4). Whoever wants to look back further
sends the logs to a collector — this driver is not meant for that.

### Where it shows: Operations → Audit log ✅

**Operations** has three tabs: *Sessions* (who is working right now), *Audit log* and *Backup*. The
audit log shows the last 120 events, newest first, in five columns:

| Column | What it contains |
|---|---|
| **Time** | Day and time to the second |
| **Who** | The acting person's username — a dash for events without an account |
| **What** | The event **in plain language**, not as a technical name |
| **Concerns** | What it was about, if that can be named (the object's ID) |
| **From where** | The sender address |

Failures are shown in the warning colour — *Sign-in failed*, *Second factor wrong*, *Recovery code
wrong*. Whoever sees a cluster at one address sees an attempt.

> **The plain language is not decoration.** Until 2026-09-05, 23 of 78 occurring events had a
> readable label; the rest showed as a raw identifier — among them precisely `session.attached`,
> the entry an affected person or a works council must be able to read. It is now called
> **"Connected to someone else's screen"**. Whoever logs a new event enters its plain-language
> label in `web/src/screens/Monitor.tsx` — otherwise it shows there as an endpoint name again.

### And the audit log in the database ✅

The `audit_log` has its own retention, actually two — because it contains two different things:

| Class | Retention | Configurable |
|---|---|---|
| **Behaviour** — sign-ins, sessions, app starts | 90 days | `OTA_PROTOKOLL_VERHALTEN_TAGE` |
| **Administration** — who changed what, and who connected to a screen | 365 days | `OTA_PROTOKOLL_VERWALTUNG_TAGE` |

`0` means "never delete". Cleanup runs once a day, in chunks of 5,000 rows — a `DELETE` over
hundreds of thousands would lock the table, and every sign-in writes to it. The cleanup itself is in
the log (`protokoll.aufgeraeumt`), otherwise a gap in the data would later look like an outage.

Triggering it by hand, without waiting until midnight:

```bash
docker compose exec api python -c "
from ota.db import SessionLocal
from ota import audit
with SessionLocal() as db: print(audit.aufraeumen(db))"
```

> **`session.attached` belongs to the long class**, even though the name starts with `session.`.
> The short class is therefore an explicit list in `api/ota/audit.py` and not a rule about
> prefixes. Whoever introduces a new, frequent action enters it there — what is not on the list is
> kept when in doubt.

## What is under "Settings" ✅

Five things apply to the whole installation and not to a session: the **language** for everyone who
does not switch themselves, the **sign-in timeout** and **storage** (both further down in this
chapter), the **directory** ([chapter 8](08-nutzer-und-gruppen.md)) and the **brand** — name,
colour and logo of the installation, [chapter 22](22-marke.md). All of it needs the permission
`settings.manage`.

## News ✅

Announcements to all users: maintenance windows, new workspaces, changes. The **News** entry is in
the sidebar for everyone, right below Start.

Whoever has `settings.manage` may **write**. On the News page:

1. **New post**, enter title and text in **Markdown**. **Preview** shows what it looks like. The same
   notation as in the handbook applies: `**bold**`, `*italic*`, code in backticks, `## heading`,
   lists with `-` and links `[text](https://…)`. Plus two things the handbook does not have:
   - **Line breaks** stay, as in an e-mail. A blank line starts a new paragraph.
   - **HTML** works: `<center>`, `<font color="red">`, `<span style="color:#c00">`, `<u>`,
     `<br>`, tables, `<details>` and the like. Markdown inside keeps working when the tags are on
     lines of their own. Images only from OTA itself or as a `data:` address; the browser blocks
     others.
2. **Pin to top** keeps a post above all others, for example an ongoing maintenance.
3. **Draft** saves without users seeing anything.
4. **Publish.**

**The badge in the sidebar** shows everyone how many posts were published since their last visit to
the News page. Opening the page marks everything as read. Whoever has never opened it sees the posts
of the last 30 days as new. The state is kept in the database, not in the browser, and therefore
applies on every computer. The sidebar checks every five minutes.

**Corrections do not count again:** the publication date is set by the first publishing. Fixing a
typo does not send anyone the badge again. The change is shown under the date ("changed on …").

**Safe:** the text is rendered in the browser, and the HTML in it goes through an allowlist. It may
style, not execute: scripts, `on…` attributes, `javascript:` links, forms, frames and `position` in
`style` are dropped. Creating, changing and deleting are logged (Operations → Log).

API: `GET /api/news`, `GET /api/news/ungelesen`, `POST /api/news/gelesen` for everyone;
`POST /api/news`, `PUT` and `DELETE /api/news/{id}` with `settings.manage`.

## Language ✅

**Administration → Settings → Language → Default language.**

OTA speaks German and English. Everyone can switch with the small **DE | EN** switch at the top
right; the choice applies in that browser and is remembered on the account, so that it applies again
on another computer. The **default language** applies to everyone who has never chosen:

- the interface, including the sign-in page of OTA itself,
- the Keycloak sign-in page — OTA passes the language along with every sign-in (`ui_locales`), and
  sets the realm's default language for when Keycloak is opened without OTA,
- the manual: chapters come from `docs/wiki/en/` in English, otherwise from `docs/wiki/`.

Messages from the server are written in German in the source and translated in the browser, the
same way as the interface (`web/src/lib/i18n.en.ts`). Whoever adds a text checks with
`python3 scripts/i18n-pruefen.py` that it has an English entry; `make test` runs this check first.

## Sign-in timeout ✅

**Administration → Settings → Sign out after inactivity.**

How long someone stays signed in without doing anything. The slider has eight steps between 30
minutes and 48 hours; by default it is eight hours — a working day, so signing in once in the
morning.

The timeout measures **inactivity**. Every request of the interface pushes it forward, and the
interface asks for the state of the sessions every 15 seconds. Whoever has a tab open and works in
it is therefore not signed out.

The change applies from the next sign-in and to every session extended afterwards. Already issued
sessions keep their old timeout until the next extension — whoever cuts the timeout drastically and
needs immediate effect additionally resets the sessions (Users → account → change password makes
all existing sessions invalid).

> Not to be confused with the **automatic ending of sessions**. That is set per workspace under
> *Resources → Session ends after inactivity* and concerns the container, not the sign-in.

## Schema and migrations ✅

When the API starts, three steps run, and each covers what the previous one cannot:

1. **Migrations** (`alembic upgrade head`). On an empty database this builds everything. If a
   schema already exists without Alembic knowing it — such as an installation from before that
   time — it is **stamped** at the starting state instead of migrated; a `CREATE TABLE` on existing
   tables would only fail.
2. **`create_all`** for tables that have no migration yet.
3. **Adding missing columns** (`schema_sync.py`). `create_all` does not do that — and exactly that
   made a running installation fail on 2026-08-27.

Steps 2 and 3 are the safety net for further development, **not a replacement for a migration**.
What they added is in the log and should be backfilled:

```bash
docker compose -f deploy/docker-compose.yml logs api | grep "Spalte ergänzt"
```

**If the migration fails, the service starts anyway.** A service that does not even come up because
of a migration problem cannot be repaired any more.

Writing a new migration:

```bash
docker compose -f deploy/docker-compose.yml exec -w /app api \
  alembic revision --autogenerate -m "what changes"
docker cp ota-api:/app/migrations/versions/. api/migrations/versions/
```

The second command is needed because the directory lives in the image and is not mounted.

## Memory: who dies first ✅

All applications of a user share **one** memory limit. If one of them breaks it, the kernel looks
for a victim — and left alone it likes to hit the largest process. That can be Xvnc; then the whole
workspace dies of a single application.

OTA therefore sets `oom_score_adj=500` on every application and all its child processes when it
starts. The infrastructure in the container stays at 0. When memory runs out, it hits an
application, not the workspace.

This can be checked like this:

```bash
docker exec <container> bash -lc \
  'for p in $(pgrep -f code/code | head -3); do echo "$p $(cat /proc/$p/oom_score_adj)"; done'
```

> **One exception you should know:** applications that hand their work over to an already running
> service instead of working themselves — `xfce4-terminal`, for instance, passes on to its own
> background service — escape the value. For the memory hogs (everything based on Electron or
> Chromium) it applies, and that is what matters.

## Update

```bash
sudo make backup     # back up first
git pull
sudo make update     # complete .env, build, start
```

Migrations run by themselves when the API starts and are never destructive. What `make update` does
in detail and what it does not touch is in the README under *Updating*.

### Security vulnerabilities (CVEs) ✅

*Since 2026-10-26.* `make update` brings security updates:

* **Third-party services** (Postgres, Keycloak, Traefik, Registry …) are pulled again —
  within the version line named in `deploy/docker-compose.yml` (`postgres:16-alpine` stays 16).
* **Own images** (api, agent, web, firewall, repo, turn) are built on a fresh base (`--pull`) and
  with `apt-get upgrade` or `apk upgrade`. So that the build cache does not freeze this layer, it
  depends on the calendar week (`OTA_PAKETSTAND`): it is rebuilt at least weekly.
* **The workspaces' base image** is built the same way by `scripts/build-desktop-image.sh
  --pruefen`, the root base image by `make root-image`. Then rebuild the workspace images under
  **Software**.

What remains is shown by

```bash
make cve                              # overview per image
scripts/cve-pruefen.sh --liste        # every affected package with the fixing version
```

Scanning uses [grype](https://github.com/anchore/grype) as a throwaway container and counts only
what can be fixed. Its database lives under `/srv/ota/runtime/grype`. What remains after an update
sits in third-party programs — e.g. Go libraries in `registry` or in Docker's `buildx` — and comes
with their next version.

The Python dependencies are pinned in `api/requirements.txt`, `agent/requirements.txt`,
`firewall/requirements.txt` and — with checksums — `third_party/selkies/ota-abhaengigkeiten.txt`.
They can be checked without the stack:

```bash
docker run --rm -v "$PWD/api/requirements.txt:/r.txt:ro" python:3.13-slim \
  sh -c 'pip install -q pip-audit && pip-audit -r /r.txt'
```

### The banner during an update ✅

*Since 2026-10-12.* From the first step of `make update`, **every OTA page** shows a banner at the
top — dashboard, sign-in and every session, also in its own tab:

> **Attention!** OTA update in progress, please reload all OTA pages once this message has
> disappeared.

It only disappears when the new API is healthy; whoever reloads then gets the new version and no
error page. While API and web interface restart, it stays — no answer is no reason to hide it.
Clicks go through: whoever is working can keep working.

* **How it works:** `scripts/wartung.sh an` sets a marker in the database (`settings`, key
  `wartung.update`) — the database keeps running during the update, the API does not. Every page
  asks `GET /api/wartung` every 15 seconds (without sign-in, `no-store`). `scripts/wartung.sh aus`
  waits until `ota-api` is healthy and removes the marker.
* **If an update fails, the banner stays** — then the message is true. After the fix, the next
  successful `make update` removes it, or by hand: `scripts/wartung.sh aus` (waits for the API) or
  `scripts/wartung.sh aus --sofort`.
* For maintenance without an update it can be set by hand the same way: `scripts/wartung.sh an`.

## Backup ✅

Backup and restore have their own chapter: **[chapter 14](14-sicherung.md)** — it also explains how
the shelf moves to an NFS share.

### By hand, without the interface

Two things need backing up:

**Database** — users, groups, workspaces, assignments, audit log.

```bash
docker compose exec -T ota-db pg_dump -U ota ota | zstd > backup-$(date +%F).sql.zst
```

**Profiles** — the users' actual work, under `/srv/ota/profiles/`.

```bash
tar --zstd -cf profiles-$(date +%F).tar.zst \
    --exclude='.cache' --exclude='core.*' --exclude='*.sock' \
    --exclude='*/Cache*' /srv/ota/profiles/
```

Excluding caches saves considerable space and time — they can be regenerated at any time.

Intended retention: seven daily, four weekly states.

> **A backup whose restore was never tested is not a backup.**
> The restore should be played through completely at least once and documented. It is an
> acceptance criterion for M7.

The golden images do not need to be backed up — they can be reproduced from the blueprint. Their
**definitions** live in the database and are therefore covered by the DB backup.

## Storage space

Profiles grow. A quota per user is intended (default 20 GB) with a warning from 80 % and refusal of
new sessions at 100 % — with an understandable message, not with an error.

Old golden image versions are cleaned up automatically (default: keep the last three).

## What locks in a session container ✅

Every container that does not belong to an administrator runs with:

| | |
|---|---|
| `no-new-privileges:true` | prevents **any** privilege escalation, including via setuid. `sudo` does not even start with it |
| `cap_drop: ALL` | not a single Linux capability. In particular no `SYS_ADMIN` |
| seccomp | Docker's default filter; it blocks around 40 system calls an application container does not need |
| `pids_limit: 4096` | a fork bomb paralyses its own container, not the host |
| `mem_limit`, `nano_cpus` | configurable per user and workspace ([chapter 6](06-ressourcen-und-zuteilung.md)) |
| own network | An `internal` network **per session** whose only exit is the router. Neither the database nor the agent nor the neighbouring session lies in it ([chapter 23](23-netz.md)) |
| `shm_size: 1g` | generous, because browsers and Electron applications otherwise crash abruptly |

For administrators the first two lines are dropped — otherwise `sudo` would not run
([chapter 8](08-nutzer-und-gruppen.md)).

### No `SYS_ADMIN`, and what it costs

Until 2026-08-27 this capability was in the code for every workspace, without justification. It
allows mounts and own namespaces and is thus practically equivalent to root on the host. Setting it
next to `no-new-privileges` while claiming that a non-administrator cannot get root was a
contradiction. It is gone.

Two things behave differently since — both are tested and both are the better trade:

**Firefox writes "CanCreateUserNamespace() clone() failure: EPERM" to the log** and starts
normally. Docker's default seccomp filter only allows own user namespaces with `SYS_ADMIN`, and
without them Firefox falls back to a weaker internal sandbox. That is acceptable: this sandbox
protects against a malicious website, and in the worst case that lands in exactly the container
where the user has a terminal anyway. `SYS_ADMIN`, on the other hand, is a way **out of** the
container.

**AppImages no longer mount themselves via FUSE.** That is why the AppImage recipe now creates a
launcher with `APPIMAGE_EXTRACT_AND_RUN=1`: the AppImage unpacks itself and starts from there. It
costs a moment at start and nothing else — and saves `libfuse2` in the image.

## Monitoring ✅

### Live utilisation: Operations → Workspaces ✅

At the top there are two bars for the **host**: cores in use with load, and memory in use. In the
table, the **Live** column shows for each running workspace:

| | |
|---|---|
| **CPU** | cores in use. The bar reaches up to the upper limit; the line in it marks the allocated cores, i.e. the weight ([chapter 5](05-workspaces-verwalten.md#resources)) |
| **RAM** | memory in use without page cache, against the container's limit |
| **Throttled X % of the time** | shown in red when the CPU limit stops the container. Users see that as stutter even when the host is idle. Remedy: allocate more cores |
| **↓ ↑** and **processes** | network in bytes per second and the number of processes |

The values refresh every 3 seconds while the tab is open and the browser window is visible.
Nothing is stored. Below 1050 pixels the table scrolls sideways, the page itself does not. The
values come from `GET /api/admin/arbeitsplaetze/auslastung` (permission `sessions.view_all`).

### `GET /healthz`

Answers **one** question: can the application work right now? Without sign-in, so a load balancer
or a Docker health check can ask it.

```json
{"status": "ok", "db": "ok", "agent": "ok"}
```

If the **database** is missing, it returns `503` — nothing works without it. If the **agent** is
missing, it stays `200`: signing in and looking around still works, only nothing can be started.
Showing that in the result and still not reporting it as dead is the difference between an alert
and a false alarm.

> Until 2026-08-27 this endpoint returned a fixed `{"status":"ok"}` without checking anything. A
> health check that always says "ok" is none.

### `GET /metrics`

Prometheus text format. **Not open** — two ways in:

| Way | What for |
|---|---|
| `Authorization: Bearer <OTA_METRICS_TOKEN>` | a collector. The token is in `deploy/.env`; if it is empty, this way does not exist |
| signed in as administrator (or with *Change settings*) | a human who takes a look |

The numbers reveal little on their own — but they reveal how many people work here and when. That
does not belong on the open network.

```
ota_sessions{status="running"}          sessions per state
ota_users, ota_users_active,
ota_users_totp                          accounts, of those able to sign in, of those with second factor
ota_templates, ota_templates_enabled    workspaces
ota_registries                          registered catalogs
ota_builds{status="…"}                  image builds per state
ota_host_memory_bytes,
ota_host_memory_available_bytes,
ota_host_disk_free_bytes, ota_host_cores
ota_agent_up                            1 or 0
```

The host state is buffered for 15 seconds. Without that the agent would be busy answering several
collectors the same thing over and over.

Example of an alert rule:

```yaml
- alert: OTAAgentWeg
  expr: ota_agent_up == 0
  for: 2m
- alert: OTAPlatteKnapp
  expr: ota_host_disk_free_bytes < 10e9
  for: 10m
- alert: OTABuildHaengt
  expr: ota_builds{status="building"} > 0
  for: 45m
```

Worth watching:

| Value | Why |
|---|---|
| Free memory | The scarcest resource. Below 15 % it gets tight |
| Free disk space | A full file system brings running workspaces to a halt |
| Failed builds | Usually a package name the image does not know |
| `ota_agent_up` | Without the agent nothing starts, and the interface only says so on the attempt |

## Storage: quota and lower limit ✅

Under **Administration → Settings → Storage** there are two numbers:

| | Default | Effect |
|---|---|---|
| **Quota per home** | 20 GB | Whoever is above it starts **no new session** |
| **Lower limit for free disk space** | 5 GB | If the host drops below it, **nobody** starts a session any more |

**0 turns the respective limit off.**

Both take effect **when a session starts, not when a file is written**. It is not a file system
quota: whoever is already inside can keep writing, and a running session is not cut off. The purpose
is an understandable refusal instead of a container that at some point stalls in the middle of work
while writing.

It is measured with `du` over the profile directory, counting **allocated blocks** — the question
is how much space on the disk is gone. The value is buffered in the agent for **ten minutes**; a
profile does not grow by gigabytes between two starts. Whoever looks in the user administration
triggers a fresh measurement.

**From 80 % a notice appears on the dashboard**, from 100 % it says that nothing starts any more.
The value is loaded afterwards and is not part of the first page load — otherwise everyone would wait
for a measurement when signing in.

The message at start names the number and a way out:

> Your home uses 21.4 GB, the full 20 GB you are allowed. Clean up — downloads, caches, old container
> images — or ask your administrator for more space.

The **user administration** shows the usage per account — freshly measured there, because someone
is explicitly looking.

**The account's whole folder is counted**, `/srv/ota/profiles/<id>/`: the shared home `user/` and
the separate home of every template and every root workspace, including deleted workspaces (the
home always stays on deletion). In the container the user only sees one of them. Whoever wants to
know where the space is:

```bash
du -sh /srv/ota/profiles/<id>/* | sort -h
```

### OTA cleans up core dumps itself ✅

`dockerd` runs with `LimitCORE=infinity`, every container inherited that, and with
`core_pattern = core` the host writes a dump of every crashed program as `core.<pid>` into the
current directory — almost always the home. Measured on 2026-10-20: 24 dumps of Firefox child
processes in one home, which die whenever a session is stopped; on one installation a single one of
4.3 GB. Nobody created them, and they locked the user out.

Since then:

- **New containers** start with `ulimit -c 0` — no more dumps are created. An existing root
  workspace keeps its container and thus the old limit; the second point cleans it up.
- **Before every measurement** (that is, before every start) the agent removes the dumps in the
  account's folder, and **once a day** in all homes. The API log names count and size.
- **Only what is provably a dump** is deleted: name `core` or `core.<number>`, a regular file (not a
  link), older than five minutes and an ELF file of type `ET_CORE` in its header. A user's file that
  happens to be called `core` stays.

Whoever needs a dump for debugging takes it within the five minutes or turns it on in the root
workspace with `ulimit -c unlimited` for that shell — the daily run still cleans it up afterwards.

## Software monitoring ✅

**Administration → Software monitoring** shows which application is installed in which workspace of
which user. The goal is to notice sprawl, not to prevent it: whatever the workspace's permissions
allow can still be installed.

**Once an hour** OTA reads every **running** workspace, and immediately at the push of a button
(**Collect now**). Applications are recorded, not versions:

| Source | What |
|---|---|
| apt | Debian packages installed by hand, like `apt-mark showmanual`. What apt marked as automatically installed is left out. A `.deb` installed via `dpkg -i` counts |
| Start menu | Programs with a start entry (`*.desktop`), system-wide and in the home, such as AppImages. Hidden entries (`NoDisplay`) do not count |
| Flatpak, Snap | Recognised by the start entries both create |

Only the name matters: the package `gimp` and the start entry `gimp.desktop` are the same
application.

**Read, not executed.** The agent fetches dpkg's and apt's status files through the Docker API
(like `docker cp`) and reads the home directly on the host. No command runs in the container for
this. Calling `apt-mark` would mean trusting a program that the user can replace themselves in a
root workspace.

### Whitelist and alerts

- **One whitelist for all workspaces.** What the image brings must be on it too.
- **Fill from the current state** takes in everything that is installed anywhere right now. That is
  the starting point. A workspace image quickly brings a few hundred packages.
- Whatever is not on it appears under **Not on the whitelist**, with user, template and time.
  Administrators additionally see it on their **dashboard**.
- After talking to the user, there are two ways:
  - Take it **into the whitelist**.
  - The user uninstalls the application. At the next collection it is missing, and the alert
    disappears by itself.
- A stopped root workspace is not read and keeps its last state. An ended workspace loses it,
  because its container no longer exists.

Whoever may see all sessions may see software monitoring. Whoever changes the settings changes the
whitelist. Every change is in the audit log: `software.freigegeben`, `software.entzogen` and
`software.whitelist_befuellt`.

## Falling back to Kasm

As long as Kasm is installed in parallel, the way back is short:

```bash
cd /opt/openterminalapps/deploy && docker compose down
sudo /opt/kasm/bin/start
```

The rollback plan should be written down and **rehearsed once** before OTA moves to port 443.
