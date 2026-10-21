# 2 · First steps

> **Two accounts after `make admin`.** Everyday access lives in Keycloak, the emergency access
> `notfall` locally in OTA. Both passwords are printed **once**. The start page leads to the
> central sign-in; the emergency access is at `/notfall`. Why that is so:
> [chapter 18](18-zentrale-anmeldung.md).

## Requirements

| | |
|---|---|
| Operating system | Debian 12/13 or comparable |
| Docker | ≥ 25, with Compose v2. **Docker 29** requires API ≥ 1.40 — see [troubleshooting](12-fehlersuche.md) |
| RAM | 8 GB for a pilot, **64 GB** for ~20 workspaces |
| CPU | 4 cores for a pilot, **16+** for the target size |
| Disk | 100 GB for a pilot, **1 TB** for the target size |

**These ports must be free on the host** — and, where a firewall sits in front, reachable for the
workspaces:

| Port | What for | Configurable via |
|---|---|---|
| **8443** (TCP) | The interface and the video stream | `OTA_HTTPS_PORT` |
| **8081** (TCP) | Only redirects to HTTPS | `OTA_HTTP_PORT` |
| **3478** (UDP/TCP) | The TURN server — **only for golden images with Selkies 1.6.2**; Selkies 2.0 streams over 8443 | `OTA_TURN_PORT` |
| **49160–49260** (UDP) | What TURN relays the media stream over — likewise only for 1.6.2 | `OTA_TURN_MIN/MAX` |
| **30000–30019** (TCP) | The pool for port forwards ("+ NAT", [chapter 23](23-netz.md)). Only what someone forwards is used | `OTA_NAT_MIN/MAX` |

**If a firewall with port forwarding sits between users and OTA**, it looks different: from the
outside 443 is enough (to the reverse proxy, with WebSockets). Only for golden images with Selkies
1.6.2 is 3478/TCP added directly to the OTA host, along with two TURN addresses in `deploy/.env` —
[chapter 24](24-hinter-nat.md).

Plus a **free address range for the workspace networks**: `10.99.0.0/16` by default. It must not
overlap with the company network — otherwise the session network wins, and the real destination is
no longer reachable from the workspace. Change it via `OTA_SESSION_POOL`, **before** the first
session runs.

A workspace is budgeted at 4 cores and 6 GB. The container must be sized for the **peak** — for
everything a user has open at the same time.

## Installation ✅

The host needs **only Docker** — no Node, no Python. Everything is built and run in containers.

```bash
git clone <repo> /opt/openterminalapps
cd /opt/openterminalapps

sudo make setup            # certificate, deploy/.env, secrets, directories
sudo make up               # build and start the stack
sudo make admin NAME=yourname   # create the first administrator
```

**`make setup` generates the secrets itself** and fills them in — nothing has to be added by hand.
Running it a second time leaves existing values untouched and only adds what came with a new
version; that is why it also runs with every `make update`.

`sudo` is needed for the directories under `/srv/ota` and the Docker socket. Anyone in the `docker`
group who created `/srv/ota` themselves can leave it out.

`make help` shows all commands.

Afterwards reachable at `https://<host>:8443/`.

### Why 8443 and not 443

As long as Kasm runs in parallel, it occupies port 443. After the switch-over, change it in
`deploy/.env`:

```ini
OTA_HTTPS_PORT=443
OTA_HTTP_PORT=80
```

The HTTP port only redirects to HTTPS. On this host 8080 is taken by another service, hence the
default 8081.

## Trusting the certificate

On the first visit the browser warns because the CA is unknown. Import the root certificate
**once**, and then there is peace — even after every certificate change:

```bash
# Linux, system-wide
sudo cp deploy/certs/ota-ca.crt /usr/local/share/ca-certificates/ota-ca.crt
sudo update-ca-certificates
```

Firefox brings its own store: *Settings → Privacy → View Certificates → Import*, tick "Trust this
CA to identify websites".

Details and switching to a real certificate: [chapter 10](10-zertifikate-und-https.md).

## First administrator ✅

```bash
make admin NAME=<username>
```

Prints a one-time password that must be changed at the first sign-in.
The user ends up in the groups `admins` and `users`.

## The first workspace ✅

**Before the first workspace, a workspace image must be on the host** — and since 2026-09-10
`make up` takes care of that itself: if `ota/base-desktop:1` is missing, it builds the image while
starting up (Debian 13 + XFCE + Selkies, without KasmVNC). That takes a few minutes and only
happens the first time.

Rebuilding or checking works by hand at any time:

```bash
scripts/build-desktop-image.sh --pruefen   # builds and checks 19 points against the contract with the agent
```

**A Kasm image is not needed for this.** Those remain possible — for ready-made catalogs and for
migrating ([chapter 9](09-kasm-images-und-registries.md)) — but they are the exception, not the
way.

> **Why this is here:** until 2026-09-10 `make up` only built the services, and
> **Workspaces → Create** then took the host's alphabetically first image — on a fresh
> installation `coturn`. Creation failed with a message about streaming engines, and whoever read
> it looked for a switch where an image was missing. Found while setting up on fresh Debian.

Then **Workspaces → Create**. The button creates the template immediately and opens the editor —
there is no form before it. There you find display name, image, mode, **Streaming** and
**Network**; whoever changes the image sets streaming to match
([chapter 5](05-workspaces-verwalten.md)).

## The media path — and access through a VPN ✅

**Since Selkies 2.0 (2026-10-07) the video stream runs through Traefik**, over WebSockets, and
needs none of what follows. It only applies to golden images built on the old base image with
Selkies 1.6.2 ([chapter 20](20-selkies-versuch.md)).

There the video stream does **not run through Traefik**, but through the stack's TURN service. It
needs an address at which the **browsers** reach it — not that of a Docker network, not `0.0.0.0`.
`make setup` suggests the host's first own address and generates the secret for it:

```ini
OTA_TURN_HOST=192.168.66.224   # suggestion from make setup — check it!
OTA_TURN_SECRET=…              # is generated
```

**Without `OTA_TURN_HOST` no picture arrives**, and without any error message: the session starts,
the tab stays empty.

### Through WireGuard or another VPN

Two things are different then, and both produce the same picture — namely none at all:

1. **The address.** `OTA_TURN_HOST` must be the one the client reaches **inside the tunnel**. The
   suggestion from `make setup` is the host's LAN address; if that does not work in the tunnel,
   the tunnel address belongs here.
2. **The packet size.** A tunnel with MTU 1000 does not let the DTLS handshake through — Chrome
   sends it with a fixed 1200 bytes and does **not** adapt. The small ICE checks get through, the
   big packet does not, and nobody reports an error. The remedy, **both lines together**:

```ini
OTA_TURN_PROTOCOL=tcp
OTA_TURN_ICE_POLICY=relay
```

Then `sudo make up`. Why ICE does not find the viable path by itself is explained with measurements
in [chapter 21](21-firmenproxy.md#why-ice-does-not-find-the-viable-path-by-itself); the symptoms
and the packet pattern in [chapter 20](20-selkies-versuch.md#networks-with-a-small-packet-size-vpn).

## What already works today

| Component | Status |
|---|---|
| Traefik with TLS, HTTP redirect, security headers | ✅ |
| Local CA and certificate generation | ✅ |
| Sign-in, users, groups, permissions | ✅ |
| Creating and assigning workspaces | ✅ |
| Resources per user (overrides) | ✅ |
| Starting, streaming, pausing, ending containers | ✅ |
| **Workspace with several apps** | ✅ basic function |
| **Clipboard bridge between the apps** | ✅ |
| Idle reaper, orphan reaper | ✅ |
| **Its own network per workspace, behind a router** | ✅ [chapter 23](23-netz.md) |
| **Firewall in the interface**: profiles, rules, port forwards, overview | ✅ |
| Golden images with build pipeline, recipes, app discovery | ✅ |
| LDAP/AD | ✅ (through Keycloak) |
| Network drives, Kerberos | dropped — see [chapter 8](08-nutzer-und-gruppen.md#network-drives-in-the-workspace--dropped) |
| Connecting Kasm registries | ✅ |
| Own brand (name, colour, logo) | ✅ |

Check whether everything runs:

```bash
make test
```
