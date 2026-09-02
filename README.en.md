<!-- Languages: Deutsch · English (here) -->
[Deutsch](README.md) · **English**

<p align="center">
  <img src="Logo-Banner.svg" alt="OpenTerminalApps" width="620">
</p>

# OpenTerminalApps

A self-hosted platform that gives every user **their own Linux workspace in the browser**. Their
tools are installed inside it — VS Code, VSCodium, JetBrains, Firefox, a terminal — and each one
streams on its own, filling the window. They all share **one home**: the same projects, the same SSH
key, the same clipboard.

Alongside that, single applications can run as throwaway containers, and existing Kasm images and
whole registries can be attached — as an addition, not as the foundation.

> **Status:** running and in use. 251 automated checks, 76 of them in a real browser. What is still
> missing is listed openly in [roadmap.md](roadmap.md) — nothing there is dressed up.
>
> The documentation is written in German. This file is the exception.

---

## Quick start

**Prerequisites** on a Linux host: `docker` with the compose plugin (`docker compose version` must
answer), plus `git`, `make` and `openssl`. Ports **8443** and **8081** must be free — 443 is left
alone on purpose so an existing Kasm can keep running alongside. Both are changeable via
`OTA_HTTPS_PORT` and `OTA_HTTP_PORT` in `deploy/.env`.

```bash
git clone https://github.com/bmetallica/openterminalapps.git
cd openterminalapps

sudo make setup                  # .env with secrets, certificate, directories
sudo make up                     # build and start (a few minutes the first time)
sudo make admin NAME=yourname    # first administrator account
```

`make setup` **generates the secrets and writes them in itself** — nothing to fill in by hand
afterwards. Running it again leaves existing values untouched.

`sudo` is needed because OTA creates directories under `/srv/ota` and talks to the Docker socket.
If you are in the `docker` group and created `/srv/ota` yourself, you can drop it.

`make admin` creates the account and **prints a generated password**. It is good exactly once: OTA
asks for a new one at first sign-in. Then:

```
https://<host>:8443/
```

**Import the root certificate once** and the browser stops warning — also after any later
certificate change:

```bash
sudo cp deploy/certs/ota-ca.crt /usr/local/share/ca-certificates/ota-ca.crt   # Linux, system-wide
sudo update-ca-certificates
```

In the browser: Settings → Certificates → Authorities → import `deploy/certs/ota-ca.crt` and tick
"trust this CA to identify websites".

**Is it running?**

```bash
make ps                          # every service should be "healthy"
curl -k https://localhost:8443/healthz
```

If something is stuck: `make logs` and [handbook chapter 12](docs/wiki/12-fehlersuche.md) — real
failures from operation with symptom, cause and repair.

### Your first workspace

After signing in: **Workspaces → Create**, enter an image (for example
`kasmweb/core-ubuntu-jammy:1.16.0`), assign it to the `users` group, enable it. Then start it under
**Start** and publish its applications via **Software → Look inside the image**.
In detail in [handbook chapter 2](docs/wiki/02-erste-schritte.md) (German).

## What it does

**The workspace**
- One container per user, each application on its own screen, started only when asked for
- Every application in its own browser tab with its own address — and installable as a desktop
  shortcut (PWA)
- The remote screen **grows with the window**: no black border, no scaling
- Clipboard in both directions, including between two applications in the same container
- A classic XFCE desktop as an additional view

**Administration**
- Resources **per user and workspace**: user A gets 2 cores, user B gets one
- **A quota per home directory** and a floor for free disk space — a comprehensible refusal instead
  of a container that stalls mid-work on a write
- **Visibility per application and group**, for when a licence does not cover everyone
- **Two-factor enforceable per group**; `/healthz` and `/metrics` for monitoring
- Users, groups and permissions; administrators are `root` inside their own container
- **Sign-in against LDAP or Active Directory**, with group mapping and a check button. Local
  accounts stay untouched — an entry of the same name cannot take one over
- Sign-in limit configurable (30 min to 48 h), rolling — nobody working is ever signed out
- Interface in German and English, switchable before signing in as well
- The handbook lives **inside the application**, filtered by permission
- **My account** for everyone: change your own password, set up two-factor with recovery codes

**Getting software into the workspaces**
- Pick packages, build the image, activate the version — with a log and a way back
- **Packages are checked first**: does the image know the name, and is it any good?
  (On Ubuntu, `firefox` is only a pointer to a snap and useless in a container)
- **Recipes** for anything that is not a plain package — with a guided builder for your own
- **Find applications inside the image**: OTA reads the `.desktop` files and suggests name, symbol
  and start command. Nobody has to know where a binary lives
- **Shared storage** for files that belong in every workspace — read-only inside the container
- **A skeleton profile** per workspace: what a home directory starts out as. Individual paths can be
  enforced at every start — the exception, not the rule. Plus **a subtree per application** that
  only arrives the first time that application starts: whoever only uses the terminal does not need
  the IDE's settings in their home
- **Freeze a session**: set it up in your own workspace, review the preview, adopt it as a new
  version. The home stays out, secrets are flagged, the sudo exception is removed
- **A script at session start**, per workspace, for anything that belongs in the home directory but
  not in the image

**Operations**
- **An own base image** `ota/base-xfce`: Ubuntu 24.04 + XFCE + KasmVNC, **965 MB instead of 20 GB** —
  no application, no Kasm label, and none of the inherited start script that restarted an
  application every three seconds. It carries `:test` and replaces nothing yet;
  `scripts/build-base-image.sh --pruefen` measures 27 points against the agent's contract
- **A bill of materials per image** (`make sbom`) in SPDX and CycloneDX — needed as soon as an image
  leaves the building
- Own registry in the stack; if an image is missing locally it is fetched from there at start
- Backup and restore of profile, container and database, by hand and on a schedule
- HTTPS out of the box with a small own CA, replaceable or behind a reverse proxy
- **Runs next to an existing Kasm installation** on the same host, without changing anything there

## How it is built

```
Browser ──HTTPS──▶ Traefik ──┬──▶ web       interface (nginx)
                             ├──▶ api       REST, sign-in, permissions, sessions
                             └──▶ /s/<id>   a session's stream (forwardAuth)
                                     │
                    api ──HTTP──▶ agent ──▶ Docker socket
                                     │
                            session container (KasmVNC)
```

**Only `agent` touches Docker.** The API processes user input and therefore does not get the socket —
the same separation applies to the host filesystem.

| Directory | Contents |
|---|---|
| `web/` | Interface (React, TypeScript, hand-written CSS, no UI library) |
| `api/` | REST API, sign-in, permissions, sessions (FastAPI, PostgreSQL) |
| `agent/` | The **only** service with Docker access; containers, displays, images, shared storage |
| `deploy/` | Compose stack, Traefik, registry, certificates |
| `extension/` | Firefox add-on for the clipboard |
| `docs/wiki/` | Handbook — served inside the application as help |
| `images/` | The own base image `ota/base-xfce` (Ubuntu + XFCE + KasmVNC) |
| `tests/`, `scripts/` | Checks, certificate, migration from Kasm, bill of materials |

## Documentation

- **[Handbook](docs/wiki/README.md)** — use, administration, operations, troubleshooting (19
  chapters, German)
- **[plan.md](plan.md)** — architecture **and the reasoning behind it**, dead ends included
- **[docs/adr/](docs/adr/README.md)** — decisions that are expensive to reverse, with the
  alternatives that would not have held (German)
- **[roadmap.md](roadmap.md)** — what is done and what is not

One pointer: [chapter 12](docs/wiki/12-fehlersuche.md) documents real failures from operation with
symptom, cause and repair — several of which looked for days like something other than what they
were.

## Checks

```bash
make test
```

**251 checks in five suites**, each one setting up its own preconditions:

| Suite | Checks |
|---|---|
| `test-authz.sh` | An ordinary user provably cannot do anything administrative and cannot sit at anyone else's screen; plus container hardening, metrics, quotas and two-factor |
| `test-clipboard-bridge.sh` | Copying between two applications in one workspace: both directions, umlauts, an image, a megabyte, after a pause, and switched off |
| `tests/e2e.mjs` | The interface in a real browser — down to whether the stream actually connects |
| `test-ldap.sh` | Directory sign-in against a real OpenLDAP in a container — above all that a local account stays untouchable and an outage does not take it down |
| `test-backup.sh` | Backup and restore of profile, container and database |

The test credentials live in `deploy/.env` as `OTA_TEST_ADMIN_PW`, not in the source.

A full run takes **about half an hour**: it starts containers, freezes an image and measures in a
real browser. Each suite can be run on its own (`bash scripts/test-authz.sh`).

## Licence

**Apache-2.0** (see [LICENSE](LICENSE)). Chosen because OTA is infrastructure: no obligations on the
operator, an explicit patent grant, and the same choice as the closest related open project (Apache
Guacamole).

OTA does **not** bundle third-party software: dependencies are fetched at build time, components
pulled at runtime as container images. **They keep their own licences and are not relicensed under
Apache-2.0 by OTA** — broken down into three layers in
[THIRD-PARTY-NOTICES.md](THIRD-PARTY-NOTICES.md), briefly in [NOTICE](NOTICE).

A workspace **image** is a composite work: OTA configuration, KasmVNC (GPL-2.0), XFCE, hundreds of
distribution packages, the installed applications. It is **not** "Apache-2.0".

**Applications inside a golden image keep their own licence.** For Microsoft VS Code, use within
your own corporate network is explicitly permitted; passing it on to third parties is not. Checked
against the licence text, with quotations, in
[handbook chapter 13](docs/wiki/13-lizenzen.md) — not legal advice, but read rather than
remembered.

“Kasm” is a trademark of Kasm Technologies. OTA is not a Kasm product and is not affiliated with
Kasm Technologies.
