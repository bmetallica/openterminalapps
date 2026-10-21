# 21 · Operating behind a corporate proxy

*For administrators.* Without a proxy there is nothing to do — that is the default and stays so.
This chapter only applies to networks in which the way to the internet goes through a proxy.

## The three lines in `deploy/.env`

```
OTA_HTTP_PROXY=http://proxy.company.example:3128
OTA_HTTPS_PROXY=http://proxy.company.example:3128
OTA_NO_PROXY=localhost,127.0.0.1,::1,api,agent,db,keycloak,web,traefik,turn,registry,ota-api,ota-agent,ota-db,ota-keycloak,ota-web,ota-traefik,ota-turn,ota-registry,.local,10.0.0.0/8,172.16.0.0/12,192.168.0.0/16
```

Then `sudo make update`. Leaving them empty means: no proxy, and everything behaves as before.

**`make setup` assembles `OTA_NO_PROXY` itself** if nothing is there: the own services, the loopback,
**this host under every name it knows itself by**, and the private network ranges. The host name is
the reason the template cannot contain it fixed — it does not know it. The private ranges cover every
Docker bridge without listing them individually; Docker only creates those at start, long after
`make setup`. Whoever maintains the line by hand keeps it.

> **`OTA_NO_PROXY` is the most important of the three.** Without it the API sends its calls to the
> agent, to Keycloak and to its own registry through the corporate proxy. It does not know these names
> and lets them run into a timeout — the error then looks like OTA and is not. What it contains must
> cover everything that lies **inside** the installation.

One peculiarity that surprises: not every program understands CIDR ranges in `no_proxy`. Go programs
(Docker, Traefik) do, Python's `urllib` does not — there only names and single addresses count. That
is why the default contains both forms side by side.

## Where OTA passes the proxy on

| Place | What for | How |
|---|---|---|
| **Building the services** | `pip`, `npm` in api, agent, web | Build arguments in `deploy/docker-compose.yml` |
| **Building the images** | `apt`, `curl`, `git clone` | `scripts/build-desktop-image.sh` and the image builder |
| **Session containers** | Users install things | the agent sets them at start |
| **API and agent** | Catalogs of foreign registries | Environment in the Compose file |

Each is set in **lower and upper case**. That is not redundancy: `curl` reads `http_proxy`, many Java
programs `HTTP_PROXY`. Whoever sets only one spelling has covered half the installation.

When **building**, the build arguments are enough, and without an `ARG` line in the Dockerfile:
Docker knows these six names in advance, passes them into every `RUN` and does **not** write them
into the finished image. Checked on 2026-09-03. That is exactly why the proxy has to be set
separately for session containers — what applied while building no longer applies at runtime.

### Why ICE does not find the viable path by itself

The obvious idea would be: offer the browser both paths and let it choose. OTA does that too — the
TURN server appears twice in the information, over UDP and over TCP. **It still does not solve this
problem.**

Measured under simulated tunnel conditions (MTU 1000, large UDP packets dropped), with `udp` as the
default and both paths on offer:

```
Gewaehlte Kandidatenpaare:
  host/:44991 -> relay/192.168.66.224:49185  empfangen=0B gesendet=14630B
KEIN BILD.
```

(Selected candidate pairs: … received 0 B, sent 14630 B. NO PICTURE.)

The reason lies in ICE itself: it tests paths with **small** packets. The UDP path thus looks viable
and wins because of its higher priority — that it breaks at the 1200-byte DTLS handshake, ICE never
learns. An MTU limit is invisible to ICE.

That is why the two lines above remain necessary. That both transports are offered additionally
helps in a *different* case: when UDP is **completely** blocked. Against a path that only partly
works, it does not help.

The same experiment with `OTA_TURN_PROTOCOL=tcp` and `OTA_TURN_ICE_POLICY=relay` delivers **1250
frames** — the configured transport comes first and wins.

## Switching later — without reinstalling

The usual case: OTA already runs without a proxy, and the network changes. That works while running.

```bash
# enter the three lines in deploy/.env, then
sudo make update
```

Simulated and measured on 2026-09-03, in both directions:

| What | Takes effect from |
|---|---|
| **API and agent** | immediately after `make update` |
| **New sessions** | immediately — variables, `/etc/profile.d`, apt configuration |
| **Running sessions** | only after ending and restarting. Intentional: nobody is interrupted in the middle of their work. |
| **The base image** | does **not** have to be rebuilt — the proxy is never in the image. Only if the proxy breaks up TLS is a rebuild with the CA needed. |
| **Golden images** | stay valid. The next build picks up the proxy automatically. |

Switching back is the same way: empty the lines, `make update`. Afterwards everything is as before —
in new sessions too.

> **If a change does not seem to arrive:** `sudo make restart` or
> `docker compose -f deploy/docker-compose.yml up -d --force-recreate api agent`.
> Compose only recreates a container when it detects a change.

### The trap this test found

While simulating, the first version of this chapter failed: after turning it on, the API reported
**503 — "The container service is unreachable"**. The reason was in the default for
`OTA_NO_PROXY`:

In the Compose network the services reach each other under their **service name** (`agent`), not
under the container name (`ota-agent`). The API calls `http://agent:8100`. Only `ota-agent` was in the
list — so the call went through the corporate proxy, which does not know the name.

Since then **both forms** are in it, and `make setup` enters both. Whoever maintains the line by hand
should do the same:

```
…,api,agent,db,keycloak,web,traefik,turn,registry,ota-api,ota-agent,…
```

That is the most expensive sort of bug: the message points to the agent, and it is completely
healthy.

## What arrives in the session

The environment variables are in **every** session container, regardless of which image it comes
from — including foreign ones from Kasm. That covers everything that reads them: `curl`, `wget`,
`pip`, `git`, and via GLib's resolver also Firefox and Chrome.

Two common cases, however, do **not** read them, and both hit exactly what users do all the time:

| | Why | What OTA puts in place |
|---|---|---|
| **`apt`** | knows no environment variables, only its own configuration | `/etc/apt/apt.conf.d/99ota-proxy` |
| **Login shells** | whoever gets a new shell through a terminal does not necessarily inherit the environment | `/etc/environment` and `/etc/profile.d/ota-proxy.sh` |

This happens **deliberately blind**: OTA writes the files into every session without checking whether
the image reads them at all. A file nobody looks at does no harm; a missing setting costs the user an
hour of searching. If writing them fails, the workspace runs anyway — only the convenience is then
missing.

The exceptions also end up in the apt configuration: every name from `OTA_NO_PROXY` gets a `DIRECT`.
Without it, even access to the own registry would go through the corporate proxy. Ranges like
`10.0.0.0/8` drop out — apt knows no network ranges, only individual host names.

### And the proxy is allowed in the router

A corporate proxy almost always sits in the company network — and that is exactly what is closed for
a workspace by default ([chapter 23](23-netz.md)). Without an exception the workspace would have the
proxy's address in its environment and could not reach it.

**There is none to enter.** OTA takes `OTA_HTTP_PROXY` apart itself and enters address and port into
the base rule set; under **Network → What applies without any action** the line is shown with its
origin. If there is no proxy in `.env`, the line does not exist.

Only if the proxy is reachable for the workspaces under a **different** address than for the services
do two additional lines belong in `.env`: `OTA_PROXY_HOST` and `OTA_PROXY_PORT`. They then take
precedence.

**Where it can still get stuck:** programs with a proxy setting of their own in their interface.
Firefox is set to "Use system proxy settings" by default and is thus covered; whoever changed it by
hand once has to change it back themselves. No automation helps against that — only a skeleton
profile that brings the setting along ([chapter 17](17-ablage-und-startskript.md)).

## What OTA cannot solve: `docker pull`

Images are pulled by the **Docker daemon**, not by a container. It does not read `deploy/.env` and
needs its own configuration on the host:

```bash
sudo install -d /etc/systemd/system/docker.service.d
sudo tee /etc/systemd/system/docker.service.d/proxy.conf > /dev/null <<'EOF'
[Service]
Environment="HTTP_PROXY=http://proxy.company.example:3128"
Environment="HTTPS_PROXY=http://proxy.company.example:3128"
Environment="NO_PROXY=localhost,127.0.0.1,::1,.local,10.0.0.0/8,172.16.0.0/12,192.168.0.0/16"
EOF
sudo systemctl daemon-reload && sudo systemctl restart docker
```

**The own registry belongs in `NO_PROXY`.** OTA runs it under `127.0.0.1:5000`; if access went
through the proxy, no golden image would come in any more.

## Proxies that break up TLS

Some corporate proxies replace certificates with their own instead of passing connections through.
Then no image knows the issuer, and even the first `apt-get update` fails — with a message about an
invalid certificate that looks as if the package repository were broken.

Remedy: put the company's CA into `images/base-desktop/ca/`, extension `.crt`, format PEM.

```bash
cp /path/to/company-ca.pem images/base-desktop/ca/company.crt
scripts/build-desktop-image.sh --pruefen
```

The build then says what it took over; if the directory is empty, it says "Keine eigene
Zertifizierungsstelle — Normalfall." (no own certificate authority — the normal case).

Two things that additionally need the same CA:

* **The Docker daemon** for the own registry — `/etc/docker/certs.d/<registry>/ca.crt` on the host.
* **`pip`**, if it is used in the image builder: it trusts its own store and not the system's.
  `pip install --cert /etc/ssl/certs/ca-certificates.crt` or `PIP_CERT` in the environment.

## Checking that it works

```bash
# Does the agent get outside?
docker exec ota-agent sh -c 'echo $HTTP_PROXY; curl -sS -o /dev/null -w "%{http_code}\n" https://deb.debian.org/'

# And does the way inside bypass the proxy?
docker exec ota-api sh -c 'echo $NO_PROXY | tr "," "\n" | grep -c ota-agent'
```

The second line must return `1`. If it says `0`, the API's calls to the agent go through the proxy —
and that is the bug that is hardest to find, because it looks like an outage of the agent.
