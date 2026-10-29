# 26 · The own package repository ✅

*For administrators. Since 2026-10-07. The own package repository always runs, the mirror is an
add-on — off by default.*

OTA brings **its own package repository for Debian 13**:

- **Always:** your own `.deb` packages, pinned snapshots, and in it the package **`ota-selkies`** —
  the workspaces' streaming server. Through it, it gets into the base image, into upgraded golden
  images and, when resuming, into root workspaces
  ([chapter 20](20-selkies-versuch.md#the-package-ota-selkies)). It needs hardly any space. Since
  2026-10-22 it also holds the packages of **IDE-AI** (`ota-ide-ai-vscode`, `ota-ide-ai-jetbrains`,
  [chapter 28](28-ide-ai.md)); the agent fetches them itself and also brings them into workspaces
  without Debian 13.
- **As an add-on:** a **mirror** of the official Debian sources and of Docker's package repository
  (`OTA_REPO_SPIEGEL=1`). Workspaces and the image builder then also install Debian packages from
  here.

Until 2026-10-08 both were an add-on behind `OTA_REPO=1`. Since `ota-selkies` the own package
repository is part of operations; `OTA_REPO=1` still counts as the switch for the mirror.

Two reasons are behind it:

- **Resilience.** If something is gone outside — a mirror, a version, the internet — the workspaces
  keep installing. That this is no theory showed while building this chapter: the release files of
  **Selkies 1.6.2**, on which OTA's base image was based, were no longer on GitHub on 2026-10-07.
  Since then OTA builds Selkies 2.0 from a fork of its own, and its dependencies lie in the
  [file pool](#the-file-pool).
- **Own packages.** Upload a self-built `.deb`, and every workspace installs it with `apt install` —
  without a server of your own and without `curl | sh`.

## What is mirrored (only with the mirror)

| Source | Contents | Address in OTA |
|---|---|---|
| `deb.debian.org/debian trixie main` | the Debian 13 archive | `/repo/debian trixie` |
| `deb.debian.org/debian trixie-updates main` | point updates | `/repo/debian trixie-updates` |
| `security.debian.org trixie-security main` | security updates | `/repo/debian-security trixie-security` |
| `download.docker.com/linux/debian trixie stable` | Docker, Compose, Buildx — **only the newest version** | `/repo/docker trixie` |
| own packages | what administrators upload | `/repo/ota ota` |

Only `amd64`, no source packages. For Docker only the newest version per package is mirrored:
otherwise there are around 160 versions there with 2.8 GB together, and one is needed.

Everything is signed with **a key of its own** that OTA creates at the first start. The signatures of
Debian and Docker are **checked during the sync** — what does not match does not get into the
mirror.

## The services

Two services that run with every `make up`: `ota-repo` (the control service with
[aptly](https://www.aptly.info/)) and `ota-repo-web` (serves `/repo/`). Their data lives under
`OTA_REPO_ROOT` (default `/srv/ota/repo`).

## Turning on the mirror

In `deploy/.env`:

```bash
OTA_REPO_SPIEGEL=1
OTA_REPO_ROOT=/srv/ota/repo      # mirror, own packages, key
OTA_REPO_FILTER=                 # empty = full mirror
```

Then `make update`.

**Space.** A full mirror needs roughly **100 to 130 GB**. A sync clears away old versions; what grows
are the pinned snapshots, because each keeps its versions. A disk of its own or an NFS share can be
mounted under `OTA_REPO_ROOT`.

**For trying it out** a filter is enough. Then only these packages including dependencies are
mirrored — a few MB instead of 100 GB:

```bash
OTA_REPO_FILTER="Name (= hello) | Name (= jq) | Name (= curl)"
```

The quotes are mandatory: the scripts read `.env`, and a bracket without them trips up the shell.

Then once under **Administration → Package sources** click **Sync now**. The first full sync takes
hours depending on the line; the log runs on the page.

## What happens in the workspaces

When a workspace starts — and when a stopped root workspace resumes — the agent enters the source,
**only in Debian 13 images**. Other images (Ubuntu, Kasm images, Alpine) stay untouched; the agent's
log then says `kein Debian 13 — nichts eingetragen` (no Debian 13 — nothing entered).

Entered are:

| File | Contents |
|---|---|
| `/etc/apt/sources.list.d/00-ota-repo.sources` | the sources, with `Signed-By` |
| `/etc/apt/keyrings/ota-repo.asc` | OTA's public key |
| `/etc/apt/ota-repo-ca.crt` + `/etc/apt/apt.conf.d/50ota-repo` | OTA's CA — **only for apt** and only for this address |
| `/etc/apt/preferences.d/ota-repo` | priority (mode "mirror first") |

The CA only applies to apt and only to OTA's address. The workspace does not trust it otherwise.

### The own source — always

The **own source** (`ota-selkies`, own packages) is entered into every Debian 13 workspace and every
build, with priority 900. Root workspaces upgrade themselves from it when resuming. This cannot be
turned off — Selkies without a source would mean that no workspace can update any more.

### The mode — only for the mirror

With the mirror turned on, a setting for the whole installation, at the very top under **Package
sources**. It applies from the next start of a workspace. Without a mirror it does not exist.

| Mode | What happens |
|---|---|
| **Mirror first** (default) | Debian packages come from the mirror. What is missing there comes from the internet as before. |
| **Mirror only** | The internet sources in the workspace are turned off (`*.ota-aus`). What is missing in the mirror cannot be installed. |
| **Do not use the mirror** | Debian packages come from the internet. The own source stays entered. |

Until 2026-10-08 they were called "own first", "own only" and "off", and **"off" also removed the own
source** — a root workspace then never upgraded Selkies. Found on the production installation; since
then the setting only concerns the mirror.

> **Important about "mirror first":** the priority is a *priority*, not a fallback only when
> missing. If a package exists here in an older version and outside in a newer one, apt takes **the
> one from here**. A security update therefore only reaches the workspaces once the mirror is
> synced. That is exactly why the mirror's age is shown at the top of the page and on the dashboard.

Why `00-` in the file name: with the same version, apt downloads from the source it reads first. With
`ota-repo.sources` the own package was there, and apt still fetched it from `deb.debian.org`.

### The image builder

The image builder (Administration → Software) enters the source **at the beginning of the build and
removes it at the end**. The finished image carries no trace of it — no key, no CA, no source. If it
starts later as a workspace, the agent enters what applies then.

Under **Snapshots → Image builder builds against** a pinned snapshot can be chosen. Then the image
builder builds against exactly these versions, even after later syncs: **reproducible images**.

## Syncing

**Only by hand**, with **Sync now**. That way operations decides when something changes in the
workspaces. Every sync:

1. fetches the lists and packages and checks the signatures of Debian and Docker,
2. pins the result as a snapshot and publishes it (switching, not overwriting — an aborted sync
   leaves the old state in place),
3. clears away versions that are no longer needed.

So that "by hand" does not become "never", the **mirror's age** is shown at the top of the page. From
**7 days** it is yellow, from **30** red; both are configurable. Administrators also see it on the
dashboard from yellow.

## Own packages

Under **Own packages**, drag in or choose a `.deb`.

- **Administrators only.** A package runs as root in every workspace when installed.
- **It is checked** that it is a valid `.deb` (`dpkg-deb`) and for `amd64` or `all`.
- **The same version twice** is rejected. A new version needs a new version number — otherwise
  workspaces would have different contents under the same version.
- Every action is in the **audit log** (Operations → Audit log), on upload with name, version and
  checksum.

In the workspace then simply:

```bash
sudo apt update && sudo apt install my-package
```

## Snapshots

A snapshot pins the state of **all mirrors and the own packages**, under its own address
`/repo/snap/<name>/…`. It stays until someone deletes it.

| Action | Effect |
|---|---|
| **Pin** | Name of lower-case letters, digits, hyphens, e.g. `2026-10-before-update` |
| **Image builder builds against** | Images are created from exactly this state (see above) |
| **Roll back** | The mirrors serve this state again — for example when an update broke something. Own packages stay as they are. The next sync switches to new again. |
| **Delete** | Final. Refused as long as the image builder builds against it or the mirrors are rolled back to it. |

## The file pool

Some things OTA needs for setting up are in no package repository. **Fetch files** stores them under
`/repo/dateien/`:

| Path | What | Who takes it |
|---|---|---|
| `selkies/2.0.0/raeder/` | the 33 Python packages Selkies needs — among them `pixelflux` and `pcmflux` —, each checked against its checksum | `scripts/build-desktop-image.sh` |
| `clipnotify/` | sources of clipnotify | `scripts/build-desktop-image.sh` |
| `sysbox/` | `sysbox-ce_0.7.1` (checksum checked) | `scripts/sysbox-einrichten.sh` |

**Selkies itself** does not lie here, but as source code in OTA's repository
(`third_party/selkies/`, [chapter 20](20-selkies-versuch.md#otas-fork)). Which packages go into the
pool is determined by its list `ota-abhaengigkeiten.txt` — with version and checksum; it is mounted
into the service, and the build checks against the same values.

The base image's build script passes the pool in as a build context of its own
(`--build-context ota-dateien=…`). If everything is there, the build installs Selkies and its
dependencies **without internet** (`pip --no-index --require-hashes`). If the pool is missing, they
come from PyPI, against the same checksums. The Sysbox script likewise takes the package from the
pool first.

Under `selkies/v1.6.2/` the development installation still has the two files of the old version that
no longer exist on GitHub — as an archive; they are no longer needed.

### What works without internet — and what does not

| | without internet |
|---|---|
| `apt install` in Debian 13 workspaces | ✅ with "mirror only" (full mirror required) |
| Docker packages in root workspaces | ✅ |
| Image builder (apt packages) | ✅ |
| Selkies (from OTA's repository), its dependencies, clipnotify in the base image | ✅ from the pool |
| Setting up Sysbox | ✅ from the pool |
| **apt in the build of the base image itself** | ❌ still goes to `deb.debian.org` (or through the corporate proxy) |
| VS Code extensions, `npm`, `pip` in workspaces | ❌ not part of this chapter |

## Who reaches the package repository

`/repo/` lies under OTA's HTTPS address and is readable **without sign-in** — as apt needs it. Anyone
who reaches OTA's HTTPS port can therefore download the mirrored and the **own packages**. Debian and
Docker are public anyway. If an own package contains something confidential, it does not belong here,
or OTA's port belongs behind a firewall (see [chapter 24](24-hinter-nat.md)).

**It can be restricted at the reverse proxy**, without touching OTA: the workspaces fetch their
packages through OTA's **own** address (`OTA_SELF_ADDRESS`), not through the proxy. The proxy can
therefore block `/repo/` for everyone — or restrict it to the networks that need it. For nginx, for
example:

```nginx
location /repo/ {
    allow 10.50.0.0/24;      # who may fetch packages from outside (example)
    deny  all;
    proxy_pass https://192.168.1.22:8443;
}
```

Uploading, deleting, syncing and all settings only work through the API and only for administrators.

## Network and firewall

For the sync, the service `ota-repo` needs outgoing HTTP/HTTPS to:

- `deb.debian.org`, `security.debian.org`, `download.docker.com`
- for **Fetch files** additionally `github.com` with its download addresses
  (`*.githubusercontent.com`), `pypi.org` and `files.pythonhosted.org`

A corporate proxy from `OTA_HTTP_PROXY` / `OTA_HTTPS_PROXY` is used ([chapter 21](21-firmenproxy.md)).
For the workspaces nothing changes in the network rules: they reach the package repository through
OTA's own address, like the interface.

## Backup

Under `OTA_REPO_ROOT` lie three things of different value:

| Directory | Value |
|---|---|
| `gpg/` | **the signing key.** If it is lost, no workspace and no image trusts a new source until the new key is entered (that happens by itself at the next start — but built images with the old state are affected). **Back it up.** |
| `aptly/` | Mirror and own packages. The mirror comes back with a sync, the **own packages do not**. |
| `aptly/public/dateien/` | the file pool; can be fetched again as long as PyPI and GitHub carry the files |

OTA's built-in backup (chapter 14) does **not** cover `OTA_REPO_ROOT`. Easiest: take `gpg/`,
`meta.json`, `aptly/db`, `aptly/pool` and `aptly/public/dateien` along with the host's backup.

## Turning off the mirror

`OTA_REPO_SPIEGEL=0` and `make update`. From the next start, the workspaces only get the own
repository entered; Debian packages come from the internet again. "Mirror only" cannot be set without
a mirror — there would otherwise be no Debian packages any more. The mirrored stock stays under
`OTA_REPO_ROOT` until someone deletes it.

The own package repository itself cannot be turned off; it stays entered in every Debian 13 workspace.

## Checking

```bash
scripts/test-repo.sh           # runs with `make test`; mirror parts only with a mirror
scripts/test-selkies-paket.sh  # the package ota-selkies, chapter 20
```

28 checks: service and signature, upload (duplicate 409, broken 422, crafted names), snapshots
including protection against deletion, a real Debian 13 workspace installs an own package **from
here**, "own only" no longer calls `deb.debian.org`, the image builder adds and removes the source,
an Ubuntu image stays untouched, and a root workspace picks up the current setting when resuming.

## Troubleshooting

| Sign | Cause | Remedy |
|---|---|---|
| Mirror tab says "not turned on" | `OTA_REPO_SPIEGEL` not `1` | `.env`, then `make update` |
| Root workspace does not upgrade Selkies | `ota-selkies` missing in the package repository, or the API does not reach the repo service | `scripts/build-selkies-deb.sh --hochladen`; `docker logs ota-api \| grep -i paketquelle` |
| "The package repository service is not responding" | `ota-repo` is not running | `docker logs ota-repo` |
| Sync: `NO_PUBKEY` / signature | Key of Debian/Docker missing or mirror manipulated | Read the log; do **not** bypass with `-ignore-signatures` |
| Sync hangs in a timeout | no way outside | Proxy ([chapter 21](21-firmenproxy.md)), firewall (above) |
| Workspace does not know the own packages | started before turning on or before changing the mode | Restart the workspace (root: stop, resume) |
| apt downloads from `deb.debian.org` despite "mirror first" | the package is missing here (filter?) | Check the filter, sync |
| Own package: "already in the repository" | the same version exists | Raise the version number |
| `.env`: `Syntaxfehler beim unerwarteten Symbol „("` (syntax error near unexpected token) | Filter without quotes | `OTA_REPO_FILTER="…"` |

## Technology in brief

- **Control service** `repo/otarepo/main.py` (FastAPI, port 8200, only in the internal network).
  Talks to the API with the same service token as the agent. No Docker socket.
- **aptly 1.6.1** from Debian 13: mirror → snapshot → `publish switch`. One job at a time.
- **nginx** (`ota-repo-web`, image `ota/repo-web`) serves `aptly/public` under `/repo/`; `Release`
  and `Packages` without caching. The image is `nginx:1.30-alpine` plus `apk upgrade`, fresh on
  every `make update`: the official image lags behind Alpine's security updates.
- **Agent** `agent/otaagent/paketquelle.py` generates the add and remove script; the same version for
  workspaces and image builder.
- **Settings** in the database (`REPO_MODUS`, `REPO_BAU_SNAPSHOT`, `REPO_ALTER_GELB`,
  `REPO_ALTER_ROT`); everything else in `OTA_REPO_ROOT/meta.json`.
