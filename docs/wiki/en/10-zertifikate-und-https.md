# 10 · Certificates and HTTPS

✅ available

## Why HTTPS is not optional

Without TLS the **clipboard does not work in the browser**. `navigator.clipboard` is only available
in a secure context. That cannot be worked around in the application and is not negotiable — HTTPS
is a prerequisite in OTA, not a hardening measure.

## Why a local CA instead of a self-signed certificate

Both cause a browser warning on the first visit. The difference shows with the **second**
certificate:

| | Self-signed | Local CA |
|---|---|---|
| First visit | warning | warning until the CA is imported |
| After import | — | no more warning |
| Renewing the certificate | **every user has to accept again** | nothing to do |
| Adding a second host | accept everywhere again | nothing to do |

For a certificate that is going to be replaced anyway, the CA is clearly the better choice.

## Generating the certificate

```bash
./scripts/make-cert.sh
```

Creates in `deploy/certs/`:

| File | Purpose |
|---|---|
| `ota-ca.crt` | Root certificate — **this is what gets distributed** |
| `ota-ca.key` | The CA's key — stays secret, `0600` |
| `ota.crt` / `ota.key` | Server certificate, valid for 825 days |

The CA is created only once and reused afterwards. Running it again issues **only** a new server
certificate — the CA stays, and nobody has to import anything again.

### Additional names

The script automatically includes the host name and all LAN addresses; Docker bridge addresses are
left out. Further names:

```bash
OTA_DNS=ota.company.local OTA_IP=10.0.0.50 ./scripts/make-cert.sh
```

> **SAN is mandatory.** Modern browsers ignore the common name completely. A certificate without a
> matching subject alternative name is rejected, no matter what is in the CN. The script always sets
> SAN — with hand-made certificates it is the most common source of errors.

## Distributing the CA

```bash
# Linux, system-wide
sudo cp deploy/certs/ota-ca.crt /usr/local/share/ca-certificates/ota-ca.crt
sudo update-ca-certificates
```

**Firefox** has its own store: *Settings → Privacy → View Certificates → Import*, tick "Trust this
CA to identify websites".

**Windows**: `certlm.msc` → Trusted Root Certification Authorities → Import. This can be rolled out
domain-wide by group policy — the recommended way in a company.

**macOS**: Keychain Access → System → import → set to "Always Trust".

## Replacing the certificate

The whole point of the setup. Overwrite both files:

```bash
cp new.crt deploy/certs/ota.crt
cp new.key deploy/certs/ota.key
chmod 600 deploy/certs/ota.key
```

Traefik watches the directory and reloads by itself. **No restart needed.**

When switching to a certificate from a real CA — Let's Encrypt or the company PKI — `ota-ca.crt` is
no longer needed and can be removed from the clients.

## Operating behind a reverse proxy

If a proxy with a valid certificate already sits in front, there are two ways:

**Pass TLS through to OTA** (recommended): the upstream proxy forwards to 8443 without breaking up
the encryption. OTA keeps its own certificate, end-to-end stays encrypted.

**Terminate at the proxy**: the proxy holds the valid certificate and talks to OTA internally. Then
the proxy must set `X-Forwarded-Proto: https`, otherwise OTA considers the connection unencrypted.
WebSockets must be let through — without them no picture appears.

In both cases: the browser must see the page as `https://`, otherwise the clipboard fails.

**The Selkies 2.0 video stream goes through the proxy**, over WebSockets — the proxy must pass them
through. Only golden images with Selkies 1.6.2 send the picture past the proxy through the TURN
server on port 3478; if a firewall with port forwarding sits in between, it needs its own forward
directly to the OTA host — [chapter 24](24-hinter-nat.md) with a complete port list and an nginx
example.

## HSTS

**Off by default.** The reason is practical: as long as the CA is not imported everywhere, HSTS
would remove the "proceed anyway" escape in the browser and lock users out completely.

Turn it on as soon as the CA is distributed or a real certificate is active — in
`deploy/traefik/dynamic/middlewares.yml` the middleware `ota-hsts` is already prepared and only has
to be added to the router.

## Checking

```bash
# Chain valid? ssl_verify_result must be 0
curl -o /dev/null -w "%{http_code} %{ssl_verify_result}\n" \
  --cacert deploy/certs/ota-ca.crt https://<host>:8443/

# Does the certificate contain the right names?
openssl x509 -in deploy/certs/ota.crt -noout -subject -dates -ext subjectAltName
```


## OTA behind another reverse proxy ✅

*Measured on 2026-08-28 with Caddy under `ota.boden.home`.*

If yet another reverse proxy sits in front of OTA — because it holds a certificate all computers
trust anyway — two settings are needed. Without them OTA still runs, but the sign-in leads to the
**internal address**, and that is more than a cosmetic flaw: it is a different origin, and whether
the desktop shortcuts stay in their own window depends on it ([chapter 3](03-arbeitsplatz.md)).

### 1 · The proxy sends name and port along

```caddy
ota.boden.home {
	reverse_proxy https://192.168.66.224:8443 {
		transport http {
			tls_trusted_ca_certs /etc/caddy/ota-ca.crt
		}
		# Without this line Traefik enters its own port, and the issuer of the
		# sign-in is then called "…:8443" instead of "…". For an OIDC client
		# that is a different issuer, and it refuses.
		header_up X-Forwarded-Port 443
		flush_interval -1
	}
}
```

Caddy sets `X-Forwarded-Host` by itself; the port it does not.

### 2 · Traefik must believe the proxy

In **`deploy/.env`**:

```bash
OTA_TRUSTED_PROXIES=192.168.66.251/32
```

Then `make up` (or `./scripts/traefik-config.sh` and restart Traefik).

> Why not directly in `traefik.yml`? Because the file is generated. Traefik reads its static
> configuration from **exactly one** source: as soon as it exists, it ignores environment variables
> and command-line arguments completely — measured on 2026-08-29, when
> `TRAEFIK_ENTRYPOINTS_..._TRUSTEDIPS` had no effect. A value that differs per installation must
> therefore be written in before the start. `scripts/traefik-config.sh` does that from
> `traefik.yml.vorlage`; manual edits belong in the template.

Several addresses separated by commas and **in quotes** —
`OTA_TRUSTED_PROXIES="192.168.66.251/32,10.0.0.5/32"`. The file is read by scripts, and a space
without quotes turns the rest of the line into a command.

Without this entry Traefik **replaces** the proxy's headers with its own — it does not trust them,
and that is the right default. Whoever is listed here may claim where a request comes from,
including the sender IP that ends up in logs and lockouts. Therefore: only your own proxy.

> **The address the name resolves to is not necessarily the one the request comes from.**
> Here `ota.boden.home` resolved to `192.168.66.1`, but `192.168.66.251` connected.
> Look it up instead of guessing:
>
> ```bash
> curl -sk https://<name>/api/gibtsnicht -o /dev/null
> docker logs ota-traefik --tail 5 | grep gibtsnicht
> ```
>
> The first column is the sender.

### Checking that it is right

```bash
curl -sk https://<name>/auth/realms/ota/.well-known/openid-configuration \
  | python3 -c "import json,sys; print(json.load(sys.stdin)['issuer'])"
```

It must show **exactly** the address under which the browser sees OTA — without a port if it is
443. If it shows the internal IP, point 2 is missing; if it shows `:8443`, point 1 is missing.


## Third-party applications and the certificate ✅

*Measured on 2026-08-28 with Open WebUI 0.9.6.*

A third-party application that signs in through OTA calls the sign-in service **server-side** — it
fetches the discovery document and later exchanges the code for tokens. There is no "proceed
anyway" there as in the browser: if it does not trust the certificate, the call aborts, and before
anyone can click anything.

This is what it looks like:

```
httpx.ConnectError: [SSL: CERTIFICATE_VERIFY_FAILED] certificate verify failed:
self-signed certificate in certificate chain
```

The application then answers its own sign-in button with **HTTP 500** — not with an error message
that points to certificates.

### The way: fetch the CA, do not turn off verification

OTA hands out its CA at **`/ca.crt`**, without sign-in. That is intentional: a CA certificate
contains a public key and names, nothing else, and it must be reachable *before* trust — a sign-in
in front of it would be a circle.

```bash
# on the third-party application's machine
curl -o ota-ca.crt https://<host>/ca.crt
cat /etc/ssl/certs/ca-certificates.crt ota-ca.crt > ca-bundle.crt
```

```yaml
volumes:
  - ./ca-bundle.crt:/etc/ssl/certs/ca-certificates.crt:ro
environment:
  SSL_CERT_FILE: /etc/ssl/certs/ca-certificates.crt
  REQUESTS_CA_BUNDLE: /etc/ssl/certs/ca-certificates.crt
```

The exact values for a configured application are in OTA under **Applications → Configuration for
the application** — with the address under which OTA was just opened.

Three things you can get wrong:

* **Only the CA instead of the combined bundle.** Then the application trusts this installation and
  nobody else any more — every connection to a public service breaks.
* **Putting the CA into the system store and hoping.** Python applications often use `httpx` or
  `requests`, and those do not read the same thing as `curl`. Hence the two environment variables.
* **Turning off verification.** The client secret and the code-for-token exchange go through this
  path. Whoever turns off verification there leaves exactly the connection unprotected that
  carries the identities.

### "But I don't have a CA of my own"

Yes you do. `make setup` creates one — it is at `deploy/certs/ota-ca.crt` and is exactly the one
`/ca.crt` delivers. A fresh installation therefore always has a certificate to distribute; the
question is never "self-signed or CA", only whether the other side knows whom to trust.

If OTA runs behind a public or company certificate that the computers trust anyway, `/ca.crt`
answers with 404 — then there is nothing to distribute either.
