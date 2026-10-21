# 24 · Operating behind a firewall with NAT ✅

*For administrators. Since 2026-09-25.*

This chapter describes the setup in which **browser and OTA are not in the same network**: OTA runs
in its own network behind a firewall, the users come from outside and only know the firewall's
address. The firewall forwards individual ports (port forwarding, DNAT), in front of or behind it
there is a reverse proxy with the certificate everyone trusts, and the directory (OpenLDAP or AD) is
on the other side of the firewall.

The example throughout the chapter:

| | Address |
|---|---|
| Firewall, from outside | `10.50.0.33` |
| OTA host, inside | `192.168.1.22` |
| Reverse proxy, inside | `192.168.1.23` |
| OpenLDAP, outside | `10.50.0.1` |
| Name for the users | `https://ota.ai.vermkv.local` (DNS `*.ai.vermkv.local` → `10.50.0.33`) |

```
  Users in the 10 network                      OTA network 192.168.1.0/24
  ───────────────────────                      ─────────────────────────────────────────
                          ┌──────────────┐
  Browser ──443/tcp──────▶│   Firewall   │──443──▶ Reverse proxy .23 ──8443──▶ OTA .22
          ──3478/tcp─────▶│  10.50.0.33  │──3478─────────────────────────────▶ OTA .22 (coturn)
                          │              │
  OpenLDAP 10.50.0.1 ◀────│──636/tcp─────│◀──────── Keycloak on OTA .22
                          └──────────────┘
```

**Since Selkies 2.0 (2026-10-07) the video stream also goes through the reverse proxy** — over
WebSockets, on the same port 443 as everything else ([chapter 20](20-selkies-versuch.md)). Workspaces
on the current base image need **no TURN forwarding any more**. The reverse proxy must pass WebSockets
through for that (`Upgrade`/`Connection`, see the example below) — it always had to do that for
KasmVNC.

**Only golden images with Selkies 1.6.2** (built on the old base image) still transmit over WebRTC
past Traefik, through the TURN server `coturn` on the OTA host. As long as such images exist, the
forward of 3478 remains necessary — otherwise the page loads, the sign-in works, and then it says
"Waiting for stream". An image gets to 2.0 via **Software → "Upgrade"**, a root workspace already by
resuming ([chapter 20](20-selkies-versuch.md#upgrading-to-20)).

## 1 · Port forwards on the firewall (from outside to inside)

| External | Target inside | Proto | What for | Required |
|---|---|---|---|---|
| `10.50.0.33:443` | `192.168.1.23:443` (reverse proxy) | TCP | Interface, API, sign-in (`/auth`), KasmVNC streams, WebSockets | yes |
| `10.50.0.33:3478` | `192.168.1.22:3478` (OTA host, **not** the proxy) | TCP | TURN — the video stream of Selkies **1.6.2** | only for golden images on the old base image |
| `10.50.0.33:80` | `192.168.1.23:80` | TCP | only the redirect to HTTPS | no |
| `10.50.0.33:30000–30019` | `192.168.1.22:30000–30019` | TCP | time-limited port forwards from a workspace ("+ NAT", [chapter 23](23-netz.md)) | only if used |

- **Keycloak needs no port of its own.** It lives under `/auth` on the same address as OTA. The API
  talks to Keycloak internally, not through the firewall.
- **3478 as TCP only is enough** if `OTA_TURN_PROTOCOL=tcp` and `OTA_TURN_ICE_POLICY=relay` are set
  (see below). Then the browser talks exclusively to this one port. Whoever switches to UDP
  additionally needs `3478/udp`.
- **The relay range `49160–49260` stays closed.** With `relay` only coturn itself uses it, on the OTA
  host, between itself and the workspace. It is never addressed from outside.
- **Hairpin NAT is not needed.** The workspace gets the same TURN address as the browser
  (`10.50.0.33`); the workspaces' router redirects it to the host before a packet even reaches the
  firewall.

The leg reverse proxy → OTA (`192.168.1.23` → `192.168.1.22:8443`) lies in the same network and does
not go through the firewall.

**Do not forward:** 8449 (Traefik dashboard), 5000 (registry), 5432 (database), 8080 and 9000
(Keycloak directly), 8100 (agent), 49160–49260 (TURN relay).

## 2 · Rules from the OTA host into the outer network

| Source | Destination | Port | What for |
|---|---|---|---|
| `192.168.1.22` | `10.50.0.1` | **636/TCP** | Keycloak reads the directory (ldaps) |
| `192.168.1.22` | DNS server | 53/UDP+TCP | Name resolution — the directory's name, `*.ai.vermkv.local` |
| `192.168.1.22` | NTP server | 123/UDP | Time — a wrong clock breaks TLS and the one-time passwords |
| `192.168.1.22` | Internet or corporate proxy | **80 and 443** or the proxy port | Pulling and building images ([chapter 21](21-firmenproxy.md)). **80 is no mistake:** `apt` fetches Debian packages over HTTP; without port 80 `make update` fails when building the services |

- **636 and not 389.** OTA creates the connection with `startTls: false`; StartTLS on 389 cannot be
  set in the interface. `ldap://…:389` would mean: the service account's password and every sign-in
  in plain text through the firewall.
- **Read-only.** The connection is `READ_ONLY`: Keycloak reads accounts and groups and checks
  passwords via bind, but never writes back. The service account therefore only needs read access.
- **The sender is `192.168.1.22`.** Keycloak runs in a Docker network, Docker translates outgoing
  connections to the host's address. If the firewall additionally applies source NAT in this
  direction, the directory sees `10.50.0.33`. The ACLs on the LDAP server go by that.
- **Workspaces** also appear as `192.168.1.22` in the outer network. Whoever should reach something
  in the 10 network from a workspace needs the rule **twice**: on the firewall and in the workspaces'
  router (interface → Network, [chapter 23](23-netz.md)).

## 3 · What to configure in OTA

### `deploy/.env` on the OTA host

```bash
# The reverse proxy — the address it connects from.
OTA_TRUSTED_PROXIES=192.168.1.23/32

# TURN: under which address browsers reach it, and which one it binds to.
# Without NAT both are the same and OTA_TURN_BIND stays empty.
OTA_TURN_HOST=10.50.0.33
OTA_TURN_BIND=192.168.1.22
OTA_TURN_PORT=3478
OTA_TURN_PROTOCOL=tcp
OTA_TURN_ICE_POLICY=relay

# If the host does not resolve the names in the 10 network by itself:
OTA_FW_DNS_UPSTREAM=<DNS server in the 10 network>
OTA_NTP_HOST=<NTP server>
```

Then `make up`. That regenerates `traefik.yml` and `turnserver.conf` and starts what has changed.

- **`OTA_TURN_HOST` may also be a name** (`ota.ai.vermkv.local`) if it resolves to the firewall from
  outside. `OTA_TURN_BIND` must be an address of the host — `scripts/turn-config.sh` warns if not. An
  IP is the more robust way: the router resolves the name at every sync, and without a name service
  the redirect fails.
- **`OTA_SELF_ADDRESS`** stays empty — and if set, then as an **address, not a URL**. It follows
  `OTA_TURN_BIND` — under this address a workspace reaches OTA itself on `OTA_HTTPS_PORT` to load the
  clipboard extension.
- **`relay` and `tcp` belong together** and are the right choice behind a firewall: a single TCP
  port, no questions about packet size ([chapter 20](20-selkies-versuch.md), "Networks with a small
  packet size").
- **`OTA_SESSION_POOL`** (default `10.99.0.0/16`) must not overlap with the outer network. If a whole
  `10.0.0.0/8` lies there, the pool belongs elsewhere — otherwise the session network wins, and the
  real destination is no longer reachable.

### The reverse proxy (`192.168.1.23`)

It terminates TLS with the certificate for `*.ai.vermkv.local` and passes on to OTA. Four things must
be right:

1. **Target `https://192.168.1.22:8443`.** The proxy must trust OTA's certificate — store
   `deploy/certs/ota-ca.crt`. `make cert` enters the host's addresses by itself.
2. Set **`X-Forwarded-Proto: https`, `X-Forwarded-Host` and `X-Forwarded-Port: 443`**. Without the
   port Traefik enters `8443`, and for an OIDC client that is a different issuer.
3. Pass **WebSocket upgrades** through. Without them there is no picture and no clipboard.
4. **Long timeouts.** A stream is a connection lasting hours.

With nginx:

```nginx
server {
    listen 443 ssl;
    http2 on;
    server_name ota.ai.vermkv.local;
    ssl_certificate     /etc/nginx/certs/ai.vermkv.local.crt;
    ssl_certificate_key /etc/nginx/certs/ai.vermkv.local.key;

    location / {
        proxy_pass https://192.168.1.22:8443;
        proxy_ssl_trusted_certificate /etc/nginx/certs/ota-ca.crt;
        proxy_ssl_verify on;

        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
        proxy_set_header Host $host;
        proxy_set_header X-Forwarded-Host $host;
        proxy_set_header X-Forwarded-Proto https;
        proxy_set_header X-Forwarded-Port 443;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;

        proxy_buffering off;
        proxy_read_timeout 12h;
        proxy_send_timeout 12h;
        client_max_body_size 0;
    }
}
```

The example with Caddy is in [chapter 10](10-zertifikate-und-https.md).

### And the OTA Git subdomain

If [OTA Git](27-git.md) is on, a second `server` is added, **to the same target**. Traefik separates
OTA and Git by name. Two lines are added: the name must also be in the TLS handshake to OTA (SNI).
OTA issues the certificate there for the subdomain itself, from the same CA.

```nginx
server {
    listen 443 ssl;
    http2 on;
    server_name git.ai.vermkv.local;
    ssl_certificate     /etc/nginx/certs/ai.vermkv.local.crt;
    ssl_certificate_key /etc/nginx/certs/ai.vermkv.local.key;

    location / {
        proxy_pass https://192.168.1.22:8443;
        proxy_ssl_trusted_certificate /etc/nginx/certs/ota-ca.crt;
        proxy_ssl_verify on;
        proxy_ssl_server_name on;
        proxy_ssl_name $host;

        proxy_http_version 1.1;
        proxy_set_header Host $host;
        proxy_set_header X-Forwarded-Host $host;
        proxy_set_header X-Forwarded-Proto https;
        proxy_set_header X-Forwarded-Port 443;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        client_max_body_size 0;      # large pushes
        proxy_read_timeout 1h;
    }
}
```

The same applies to other proxies (Caddy set up this way on 2026-10-21, Nginx Proxy Manager by its
default configuration):

- **Nginx Proxy Manager:** its own proxy host for the subdomain, scheme `https`, the same target as
  for OTA. It passes the `Host` through by itself. Under *Advanced* the four lines
  `proxy_ssl_server_name on;`, `proxy_ssl_name $host;`, `client_max_body_size 0;` and
  `proxy_read_timeout 1h;`.
- **Caddy on OPNsense:** handler with protocol **`https://`** (not `http://`, port 8443 only accepts
  HTTPS), plus an "upstream" header `Host` = `{host}`. Without this header OTA appears under the
  subdomain, and Keycloak reports `Invalid parameter: redirect_uri`.

SSH for Git only works from the workspaces. There is nothing to set up for it on the proxy or the
firewall.

**Which address belongs in `OTA_TRUSTED_PROXIES`** is shown by Traefik itself — look it up instead of
guessing:

```bash
curl -sk https://ota.ai.vermkv.local/api/gibtsnicht -o /dev/null
docker logs ota-traefik --tail 5 | grep gibtsnicht     # first column = sender
```

### The directory (interface → Settings → Directory in Keycloak)

```
Address          ldaps://<name of the LDAP server>:636
Base             ou=people,dc=…
Service account  cn=<read-only>,dc=…
Kind             OpenLDAP        (username: uid)
```

**Test connection**, save, **Sync now**. Afterwards the accounts come from the directory at sign-in
and at every sync; changes happen there, not in OTA.

**The directory's CA belongs in Keycloak's truststore.** Keycloak checks the LDAP server's
certificate (`useTruststoreSpi: always`) and by default only knows the public CAs of the Java
runtime. A certificate from the company PKI is otherwise rejected:

```bash
cp company-ca.pem deploy/keycloak-truststore/       # PEM, one or more files
docker restart ota-keycloak
docker logs ota-keycloak 2>&1 | grep -i truststore  # "Found the following truststore files …"
```

The directory is mounted to `/opt/keycloak/conf/truststores`; Keycloak reads every file in it by
itself. It belongs to the installation and is not in the repository (`.gitignore`).

**The certificate must match the address.** Whoever enters `ldaps://10.50.0.1:636` needs a
certificate with the IP in `subjectAltName`. Usually only the name is there — then enter the name and
make sure the host resolves it.

The test in the interface says what the cause is: "encrypted connection fails" means truststore or
certificate, "name cannot be resolved" means DNS, "unreachable" means firewall.

## 4 · What changed in OTA for this

Until 2026-09-25 OTA could not be operated with Selkies behind NAT. Four places:

1. **Two TURN addresses instead of one.** `OTA_TURN_HOST` controlled both what coturn binds to and
   which address the browsers get. Behind NAT those are two different ones: with the firewall's
   address coturn did not start, with its own the browsers got one they could not reach. New:
   `OTA_TURN_BIND` (`scripts/turn-config.sh`, base rules in the agent).
2. **Redirect in the workspaces' router.** Selkies in the workspace gets the same address as the
   browser. The router redirects `OTA_TURN_HOST:3478` to `OTA_TURN_BIND`; visible under **Network →
   What applies without any action** as a row with the origin `OTA_TURN_HOST → OTA_TURN_BIND`.
3. **`OTA_SELF_ADDRESS` is a setting of its own.** It was tied to `OTA_TURN_HOST` and would have
   pointed to `10.50.0.33:8443` behind NAT — a port that is not even open there.
4. **Truststore for Keycloak** (`deploy/keycloak-truststore/`). Before, a directory with a
   certificate from a company CA could not be connected encrypted at all. In addition the connection
   test now says **why** it fails — before, every case said "unreachable", even when the server had
   long answered and only the CA was missing.

While building, three further bugs came up that have nothing to do with NAT and could hit any
installation ([chapter 12](12-fehlersuche.md), "After a host restart no workspace has network"):
Traefik took the router's address after a host restart, a failed attachment left an entry that later
prevented Traefik from starting, and the list of containers per session network arrived empty.

## Checking

```bash
make up
./scripts/test-streaming.sh    # picture through the NAT — see below
./scripts/test-firewall.sh     # among others "the published TURN address leads to the host"
```

`test-streaming.sh` simulates the NAT itself: if `OTA_TURN_BIND` is set and different, it creates a
DNAT rule on the host for the duration of the suite that plays the firewall's role for the test
browser's network (`OTA_TURN_HOST:3478 → OTA_TURN_BIND`). The browser then only knows the published
address, Selkies in the workspace goes through the redirect in the router. Measured on 2026-09-25
with `OTA_TURN_HOST=10.50.0.33`: 1311 frames, the redirect's counters in the router rose.

From outside — on a computer in the 10 network:

```bash
curl -s -o /dev/null -w "%{http_code}\n" https://ota.ai.vermkv.local/healthz   # 200
nc -zv 10.50.0.33 3478                                                          # open
```

On the OTA host:

```bash
python3 scripts/pruef-turn.py      # checks coturn under OTA_TURN_BIND
docker exec ota-firewall nft list chain inet ota prerouting   # the redirect with counters
```

Against the directory: **Test connection** in the interface. Simulated on 2026-09-25 with an
OpenLDAP whose certificate came from a CA of its own: without the CA in the truststore "encrypted
connection fails" (in Keycloak's log `PKIX path building failed`), with it the connection and the
service account's sign-in succeeded.

## When something does not work

| Picture | Cause |
|---|---|
| Page loads, "Waiting for stream" | 3478/TCP not forwarded, or to the reverse proxy instead of the OTA host |
| Sign-in jumps to `https://192.168.1.22:8443` | `OTA_TRUSTED_PROXIES` is missing or names the wrong address |
| Sign-in fails with "invalid issuer" in a third-party application | The proxy does not send `X-Forwarded-Port` |
| `turn-config.sh` warns "no address of this host" | `OTA_TURN_BIND` is missing or wrong |
| Directory test: "encrypted connection fails" | CA missing in `deploy/keycloak-truststore/`, or the certificate does not match the address |
| Directory test: "unreachable" | 636 closed on the firewall, or the directory only accepts 389 |
| Agent reports `Firewall-Abgleich fehlgeschlagen: Firewall meldet 500`, new workspaces without network and without picture | An address in `deploy/.env` is not an address — measured with `OTA_SELF_ADDRESS=https://…`. Only enter the host, or leave `OTA_SELF_ADDRESS` empty. Since 2026-10-05 OTA cleans this up itself and only discards that one line (`docker logs ota-agent \| grep gelesen`, `docker logs ota-firewall \| grep Ziel`) |
| Workspaces resolve no names, even at level "off" | The router asks a server the firewall does not let through. Before 2026-10-06 that was always `9.9.9.9`, regardless of what the host uses. Set `OTA_FW_DNS_UPSTREAM` to the internal DNS, or update |
| `make update` fails while building: `deb.debian.org … 400 Bad Request`, then timeouts | No way to the internet on port 80 — or a transparent proxy/web filter on the firewall intercepts it. Open port 80 and exclude the OTA host from the transparent proxy, or enter the proxy explicitly ([chapter 21](21-firmenproxy.md)). The running installation stays untouched: replacing only happens once everything is built |
