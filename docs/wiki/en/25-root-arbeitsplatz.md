# 25 · Root workspace — root and Docker in the container ✅

*For administrators. Since 2026-10-06.*

A **root workspace** is a class of workspace of its own, meant for developers:

| | Standard | Root with Docker |
|---|---|---|
| root in the container | only administrators (`sudo`) | **everyone with the permission**, `sudo` without a password |
| Docker, `docker compose`, `buildx` | — | ✅ its own `dockerd` in the workspace |
| On ending | the container is **deleted** | the container is **stopped** — everything inside stays |
| What is installed outside the home | gone at the next start | **stays** until "Rebuild" |
| Address in the browser | new per session | **fixed** — shortcuts and bookmarks stay valid |
| Runtime | `runc`, hardened (`cap_drop: ALL`) | **Sysbox** (`sysbox-runc`) |

The home, the shelves and the group drives are the same in both classes. **Several root
workspaces at once:** the *Shared data* persistence gives each its own home with the data folders
from the shared one ([chapter 5](05-workspaces-verwalten.md#resources)).

## Why Sysbox — and what it means for security

Docker in a container needs `--privileged` under Docker's normal runtime. That would give the
workspace all of the kernel's rights, and whoever is root inside would be root on the host with
little effort. Mounting the host's Docker socket would be even worse: every user would be root on the
host and see Keycloak, the database and the other people's workspaces.

**Sysbox** is an additional runtime for Docker (open source, Apache-2.0, by Docker Inc.). Every
Sysbox container gets its own user namespace: **root in the container is an unprivileged user on the
host.** Measured on 2026-10-06:

```
uid_map:  0 → 296608 (65536)        root in the container = UID 296608 on the host
```

`dockerd`, `docker compose` and `sudo` run inside it, without `--privileged`. Only templates of the
class Root run with Sysbox; all others stay with `runc` and unchanged hardening. The decision and the
rejected paths are in [ADR-007](../../adr/007-root-und-docker-ueber-sysbox.md).

**The network stays OTA's network.** The inner containers hang behind the workspace (NAT inside it)
and therefore only get outside through the workspaces' router — with the same network profile as the
workspace itself ([chapter 23](23-netz.md)). Measured: from an inner container internet yes, company
network no, host no.

## Setting up

### 1 · Sysbox on the host

Once per host, as root:

```bash
sudo scripts/sysbox-einrichten.sh --pruefen          # check only
sudo scripts/sysbox-einrichten.sh --live-restore     # set up (recommended)
```

The script downloads Sysbox 0.7.1 (or takes it from the own package repository's file pool,
[chapter 26](26-paketquellen.md#the-file-pool)), checks the checksum and installs it — **without
touching a container**:

- The package normally wants to restart Docker to set two network values in
  `/etc/docker/daemon.json`, and refuses to install as long as even one container exists. It then
  **suggests** `docker rm $(docker ps -a -q) -f`. **Never run this command** — it deletes every
  container on the host. The package does not run it itself.
- The script therefore enters beforehand the values **that already apply today**: the address of
  `docker0` as `bip` and Docker's built-in address ranges. Afterwards the package only enters the
  runtime and lets Docker re-read the configuration via `SIGHUP`. Measured on the development
  machine: 45 running containers before, 45 after.
- An existing `daemon.json` is backed up (`daemon.json.vor-sysbox.<time>`) and only **extended** —
  what is in it stays.
- `--live-restore` additionally sets `"live-restore": true`: containers keep running when Docker
  itself restarts, for example during an update of the Docker package. Recommended, but it changes
  the behaviour of future Docker updates — hence a separate option.

Afterwards `docker info` must name the runtime:

```bash
docker info | grep -i runtimes          # … sysbox-runc
systemctl is-active sysbox              # active
```

> **Do not update Sysbox unattended.** An update of the package restarts the Sysbox services — and
> with them every running root workspace. Do it in the maintenance window. Because the package comes
> from a single file and not from a package repository, `unattended-upgrades` does not update it
> anyway; whoever wants to be sure: `apt-mark hold sysbox-ce`.

Requirements: amd64, kernel from 5.12 (for ID-mapped mounts — otherwise the files in the home would
belong to `nobody` in the container). Tested with Docker 29.7, containerd 2.2, kernel 6.12, Debian 13.

### 2 · The root image

```bash
make up                 # builds ota/base-desktop-root:1 as soon as Sysbox is there and it is missing
make root-image         # rebuild by hand and check under Sysbox
```

`ota/base-desktop-root:1` is the desktop base image plus `docker-ce`, `containerd`,
`docker-buildx-plugin` and `docker-compose-plugin` from Docker's own package repository. The user
`ota` is in the group `docker` and has `sudo` without a password. The start script starts `dockerd`
as root, then the desktop as UID 1000.

Golden images for root workspaces are built on top of it (software, recipes — as for any other
image, [chapter 7](07-golden-images.md)).

> **Golden images from before 2026-10-07.** Until then the image builder wrote a fixed `USER 1000`
> at the end of every image. On the root image that meant: the start script did not run as root,
> waited 30 seconds in vain for `dockerd` and ended the container (exit 127) — in the browser a long
> greyed-out workspace and then "Internal Server Error". Measured on the production installation.
> Since then the image builder takes over the base image's user, and the agent starts every image
> with the marker `ota.klasse=root` explicitly as root — **including ones already built**, a rebuild
> is not needed. A root workspace whose container still dates from before is **rebuilt** once.

### 3 · The template

**Workspaces → workspace → General → Class: "Root with Docker".**

- **Image:** `ota/base-desktop-root:1` or one built on it. On another image there is root, but no
  Docker — the editor says so.
- **Storage limit:** how much a root workspace may use at most, container and Docker data together.
  Default 50 GB. Above that it no longer starts until it is cleaned up or rebuilt (administration can
  still start it to clean up inside).
- **Resources:** inner containers share the workspace's cores and memory. For Compose stacks with
  databases rather 4 cores and 8 GB than 2 × 2.

If Sysbox is missing on the host, the editor warns, and a start is refused with an explanation —
**never** falling back to `runc` with `--privileged`.

### 4 · The permission

**Users → group → Permissions: "Use root workspace"** (`arbeitsplatz.root`). Whoever does not have it
gets an explanation instead of a workspace when starting a root template. Administrators always have
it. It is deliberately a permission of its own and not tied to "administrator": it is a tool for
developers, not an administrative right.

## For the user

- **Ending means stopping.** The square in the tile stops the workspace; it is then shown as
  "stopped" on the dashboard. **Resume** starts exactly this container again — with all installed
  packages, settings and Docker images, under the same address. Measured: about 3 seconds to stop
  (clean, exit 0), 3 seconds to resume.
- **Rebuild** builds the workspace anew from the current image — for a new base image or a
  tinkered-up state. The home always stays. Two variants:
  - *Keep Docker images* — the images and volumes in the workspace stay.
  - *Also delete Docker data* — everything except the home is gone.

  A new base image only gets into an existing root workspace through "Rebuild" (operator's decision,
  2026-10-06). **Selkies is the exception:** when **resuming**, the agent upgrades the package
  `ota-selkies` to the version in the own package repository and restarts the workspace once for it
  — everything else in the workspace stays (operator's decision, 2026-10-08;
  [chapter 20](20-selkies-versuch.md#upgrading-to-20)).
- **`.bashrc` and `.profile`** are in the home since 2026-10-19. An existing workspace gets them at
  the next resume, without "Rebuild". Existing files stay as they are
  ([chapter 17](17-ablage-und-startskript.md#bashrc-profile-and-bash_logout-)).
- **Docker:** `docker`, `docker compose`, `docker buildx` without `sudo`. A published port
  (`ports: ["8080:80"]`) is reachable in the workspace's browser at `http://localhost:8080`. From
  outside the workspace through a time-limited port forward ("+ NAT", [chapter 23](23-netz.md)).
- **Git:** if [OTA Git](27-git.md) is on, OTA sets it up on every start **and every resume**, as in
  every workspace. The token is revoked when stopping, and there is a new one when resuming. A new Git
  subdomain also arrives with resuming, without "Rebuild". It requires `git` in the workspace: the
  base image has it since 2026-10-21, otherwise `apt install git` once.
- **Idle:** a root workspace is **stopped** when idle, never deleted — regardless of what the
  template says under "What happens then".
- **If the container ends by itself** (the desktop in it crashed), the workspace is shown as stopped
  afterwards and is **resumed** at the next start — not replaced by a new one. Until 2026-10-07 OTA
  created a new workspace in this case, and what was installed in the old one was no longer
  reachable for the user.

## For administration: Operations → Workspaces

The list shows **all** workspaces — running ones of both classes and stopped root workspaces — with
user, class, state, last active and the storage used (container + Docker data, against the
template's limit), plus live CPU, RAM and network usage as bars
([chapter 11](11-betrieb.md#live-utilisation-operations--workspaces-)). Per row:

| Button | Effect | Permission |
|---|---|---|
| **Terminal** | root shell in the browser, in the running workspace | `arbeitsplatz.terminal` |
| **Start** | start a stopped root workspace without the user opening a session | `sessions.view_all` |
| **Stop** | stop a running root workspace | `sessions.view_all` |
| **Terminal log** / **CSV** | download the log of this workspace's terminal input | `sessions.view_all` |
| **Delete** (root) / **End** (standard) | container gone — for root including Docker data. The home always stays | `sessions.view_all` |

Nothing is deleted automatically, not even a root workspace that was not used for a long time
("last active" shows it).

### The web terminal

- **Where:** in **every running workspace**, standard and root. **Never** into a service of the
  stack (API, database, Keycloak, agent, router) — the agent only accepts containers with a session's
  marker. Measured: an attempt on `ota-db` is rejected.
- **As root.** In root workspaces root in the container's namespace; in standard workspaces root with
  their hardening (`cap_drop: ALL`) — looking around and repairing works, `apt install` can fail
  there for lack of rights.
- **Permission:** "Web terminal as root into running workspaces" (`arbeitsplatz.terminal`). It is
  more powerful than connecting to the screen: whoever has it reads every file in the user's home. A
  second factor is **not** required for it (operator's decision); whoever wants it enforces it per
  group ([chapter 8](08-nutzer-und-gruppen.md)).
- **No notice for the user** that an administrator is connected — as with connecting to the screen
  (operator's decision).

### The terminal log

- **What:** per workspace every shell session (who, when, from where) and every **input line** with
  a timestamp. **No output** — it would contain every file of the user that was read. Backspace is
  applied, Ctrl+C/Ctrl+D appear as `^C`/`^D`, arrow keys are dropped. What the shell makes of it
  (completion with Tab, history with arrow up) is not in it.
- **Attention:** what is typed is in the log — including a password on the command line
  (`mysql -pSecret`). The terminal says so above the input field.
- **Who sees it:** every administrator (`sessions.view_all`). It is **read-only**: there is no way to
  change or delete entries. They only go away through the retention of the administration class
  (`OTA_PROTOKOLL_VERWALTUNG_TAGE`, default 365 days).
- **Outlives the workspace:** after a workspace is deleted, its log stays.
- **Export:** text or CSV (`zeit_utc;verbindung;administrator;nutzer;vorlage;art;text`). Every export
  is itself in the audit log.

## Storage and backup

| What | Where | Backed up |
|---|---|---|
| Home | `/srv/ota/profiles/<id>` (as always) | ✅ with the profiles |
| What was installed outside the home | the container's layer | ✅ **always**, also when stopped, even if the backup schedule does not back up containers otherwise |
| Docker images, containers, volumes in the workspace | volume `ota-platz-docker-<id>` | ❌ — can be rebuilt and pulled |
| Installation values (TURN, proxy, keyboard) | `/srv/ota/runtime/plaetze/<id>/umgebung.sh` | — is rewritten on every start |

**Installation values of now.** A stopped workspace is not recreated, its environment dates from the
first start. So that a changed TURN address, a new proxy or another keyboard layout still arrive, the
agent writes them into a mounted file before every start, which the start script reads.

**Space on the host.** Docker images grow quickly. The list under Operations shows per workspace what
it uses; the template's limit prevents one from filling the disk. It is measured with
`docker ps --size` plus `docker system df` (cached for a minute).

## Two things that turned out differently while building

- **DNS in inner containers.** In the workspace the name server is Docker's built-in resolver
  `127.0.0.11`. The inner `dockerd` cannot pass a loopback address on to its containers and silently
  fell back to `8.8.8.8` — which the router blocks (foreign resolvers are closed, otherwise rules by
  name would be ineffective). Result: `docker run alpine wget example.com` → "bad address". Since then
  `dockerd` gets the router as DNS (`--dns 10.99.x.2`); the agent passes the address in as
  `OTA_ROUTER`, because the default route only appears after the start.
- **Clean stopping.** The base image's start script waits in the foreground on a `sleep 3600` and
  only runs its TERM handler afterwards. The first attempt therefore ended after the waiting time with
  SIGKILL (exit 137) — in the middle of running inner containers. Now the root image's start script
  ends all processes of UID 1000 when stopping and lets `dockerd` shut down its containers in order:
  exit 0 after about 3 seconds.

## Checking

```bash
./scripts/test-root-arbeitsplatz.sh        # 37 checks, also part of make test
```

They create a root template and go the whole way: Sysbox (UID mapping), `sudo`, permissions in the
home, Docker and Compose, network of the inner containers, stopping (exit 0) and resuming with
preserved state, storage measurement, stopping/starting by administration, web terminal including log
and CSV, the rejection of a terminal into a service of the stack, rebuild, deletion including Docker
data — and that the log outlives the workspace. Plus a golden image with `USER 1000` that still
starts and runs as root, and the user the image builder sets. Without Sysbox it is skipped instead of
red.

## Updating an existing installation

```bash
cd /opt/openterminalapps
sudo make backup                                   # back up first
git pull
sudo make update                                   # build and start services
sudo scripts/sysbox-einrichten.sh --pruefen        # look at the prerequisites
sudo scripts/sysbox-einrichten.sh --live-restore   # set up Sysbox (no container is touched)
sudo make up                                       # now builds ota/base-desktop-root:1
./scripts/test-root-arbeitsplatz.sh                # optional: the whole way, 37 checks
```

Afterwards: create a template of the class "Root with Docker" and grant the permission "Use root
workspace" to the group(s) that should get it. Administrators already have the terminal permission;
grant it to other groups separately.

**What the update does to running workspaces:** nothing new. Existing templates stay class Standard
and behave as before. The "Sessions" tab under Operations is now called "Workspaces" and shows the
same sessions, plus stopped root workspaces.

## When something does not work

| Picture | Cause |
|---|---|
| Start: "Root workspaces need Sysbox …" | Sysbox is missing or Docker does not know the runtime: `docker info \| grep -i runtimes` |
| Start: "It needs the permission "Use root workspace"" | The group lacks the permission |
| Start: "… uses X GB, Y GB are allowed" | Storage limit: clean up (`docker system prune` in the workspace), "Rebuild", or raise the template's limit. Administration can still start it under Operations |
| Start takes long, apps stay greyed out, clicking an app: "Internal Server Error", the container is off shortly after | Golden image with `USER 1000` from before 2026-10-07 (`docker logs ota-s-…` shows `setpriv: initgroups failed`). `git pull`, `make update`, then **rebuild** the workspace |
| In the workspace `docker: command not found` | The image is not `ota/base-desktop-root:1` or built on it |
| `docker run …` → "bad address" | Image older than 2026-10-06 (without `--dns`): `make root-image`, then "Rebuild" |
| Resume: "The network of this workspace no longer exists" | The session network was deleted by hand: "Rebuild" |
| `apt install sysbox-ce` asks for `docker rm …` | Installed without the script. **Do not run it** — use `scripts/sysbox-einrichten.sh` |
| The terminal closes immediately with "You lack the permission for this" | The permission `arbeitsplatz.terminal` is missing |
