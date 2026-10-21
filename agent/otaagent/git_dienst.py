"""Der Container von OTA-Git (Forgejo) — angelegt, wenn Git im Menü an ist.

Nicht in Compose, sondern hier: Sonst ließe er sich nicht aus der Oberfläche
ein- und ausschalten. Die API sagt, **was** laufen soll (Subdomain,
Zertifikat, Forgejo-Einstellungen); der Agent setzt es um. Die Geheimnisse,
die nur er braucht (Passwort der Datenbank), kommen aus seiner Umgebung.

Ausschalten hält den Container nur an. Die Daten (Volume `ota_git_daten`,
die Datenbank `forgejo`) bleiben immer — ein erneutes Einschalten macht
weiter, wo es aufgehört hat.

Wege hinein, alle über Traefik (Handbuch Kapitel 27):

* `websecure` — der Eingang von OTA; Browser kommen über den Reverse Proxy
  mit dem Namen der Subdomain. Traefik trennt am Namen.
* `git-intern` (:443) und `git-ssh` (:2222) — nur in den Sitzungsnetzen,
  nicht auf dem Host veröffentlicht.
"""
from __future__ import annotations

import hashlib
import json
import logging
import os
import re
import time
from typing import Any

import docker
from docker.errors import APIError, ImageNotFound, NotFound

log = logging.getLogger("otaagent.git")

NAME = "ota-git"
VOLUME = "ota_git_daten"
BILD = os.environ.get("OTA_GIT_IMAGE", "codeberg.org/forgejo/forgejo:15.0.10")
RUNTIME_ROOT = os.environ.get("OTA_RUNTIME_ROOT", "/srv/ota/runtime")
TRAEFIK_DYNAMIC = "/ota/traefik-dynamic"
OEFFENTLICH = os.environ.get("OTA_PUBLIC_NETWORK", "ota_public")
INTERN = "ota_internal"
DOMAIN_OK = re.compile(r"[a-z0-9]([a-z0-9-]{0,61}[a-z0-9])?(\.[a-z0-9]([a-z0-9-]{0,61}[a-z0-9])?)+")


def _ca_ordner() -> str:
    return os.path.join(RUNTIME_ROOT, "git", "ca")


CERTS = "/ota/certs"


def _zertifikat(domain: str) -> None:
    """Ein Serverzertifikat für die Subdomain, ausgestellt von der OTA-CA.

    **Hier und nicht in der API:** Den Schlüssel der CA liest nur, wer ihn
    lesen muss — die API verarbeitet Nutzereingaben und bekommt ihn nicht.
    Hinter einem Reverse Proxy sieht der Browser dessen Zertifikat; dieses
    gilt für die Strecke Proxy → OTA und für die Arbeitsplätze, die Traefik
    direkt erreichen. Ein gültiges für denselben Namen wird weiter benutzt.
    """
    import subprocess
    import tempfile

    ordner = os.path.join(TRAEFIK_DYNAMIC, "git")
    os.makedirs(ordner, exist_ok=True)
    crt, key = os.path.join(ordner, "ota-git.crt"), os.path.join(ordner, "ota-git.key")
    if os.path.exists(crt) and os.path.exists(key):
        san = subprocess.run(["openssl", "x509", "-in", crt, "-noout", "-ext", "subjectAltName"],
                             capture_output=True, text=True).stdout
        noch = subprocess.run(["openssl", "x509", "-in", crt, "-noout", "-checkend",
                               str(30 * 86400)], capture_output=True).returncode == 0
        namen = [t.strip() for t in san.replace("\n", ",").split(",")]
        if f"DNS:{domain}" in namen and noch:
            return
    with tempfile.TemporaryDirectory() as tmp:
        ext = os.path.join(tmp, "ext")
        with open(ext, "w", encoding="utf-8") as fh:
            fh.write("basicConstraints=critical,CA:FALSE\n"
                     "keyUsage=critical,digitalSignature,keyEncipherment\n"
                     "extendedKeyUsage=serverAuth\n"
                     f"subjectAltName=DNS:{domain}\n")
        csr = os.path.join(tmp, "csr")
        schritte = [
            ["openssl", "genrsa", "-out", key + ".neu", "2048"],
            ["openssl", "req", "-new", "-key", key + ".neu", "-subj", f"/CN={domain}", "-out", csr],
            # Unter 398 Tagen: Länger nehmen Browser ein Serverzertifikat nicht.
            ["openssl", "x509", "-req", "-in", csr, "-CA", f"{CERTS}/ota-ca.crt",
             "-CAkey", f"{CERTS}/ota-ca.key", "-CAcreateserial", "-CAserial",
             os.path.join(tmp, "serial"), "-days", "397", "-sha256",
             "-extfile", ext, "-out", crt + ".neu"],
        ]
        for befehl in schritte:
            res = subprocess.run(befehl, capture_output=True, text=True)
            if res.returncode != 0:
                raise RuntimeError(f"Zertifikat für {domain}: {res.stderr.strip()[-200:]}")
    with open(crt + ".neu", "a", encoding="utf-8") as fh, \
            open(f"{CERTS}/ota-ca.crt", encoding="utf-8") as ca:
        fh.write(ca.read())
    os.chmod(key + ".neu", 0o600)
    os.replace(key + ".neu", key)
    os.replace(crt + ".neu", crt)
    log.info("OTA-Git: Zertifikat für %s ausgestellt", domain)


def _dateien_schreiben(domain: str) -> None:
    """Zertifikat für Traefik und die CA, der Forgejo trauen soll."""
    _zertifikat(domain)
    with open(f"{CERTS}/ota-ca.crt", encoding="utf-8") as fh:
        ca = fh.read()
    yml = os.path.join(TRAEFIK_DYNAMIC, "ota-git.yml")
    with open(yml + ".neu", "w", encoding="utf-8") as fh:
        fh.write("# ERZEUGT vom Agent, solange OTA-Git an ist (Kapitel 27).\n"
                 "tls:\n  certificates:\n"
                 "    - certFile: /etc/traefik/dynamic/git/ota-git.crt\n"
                 "      keyFile: /etc/traefik/dynamic/git/ota-git.key\n")
    os.replace(yml + ".neu", yml)

    os.makedirs(_ca_ordner(), exist_ok=True)
    with open(os.path.join(_ca_ordner(), "ota-ca.crt"), "w", encoding="utf-8") as fh:
        fh.write(ca)


def _subnetz(client, netz: str) -> str:
    try:
        cfg = client.networks.get(netz).attrs.get("IPAM", {}).get("Config") or []
        return str(cfg[0].get("Subnet") or "")
    except (NotFound, APIError, IndexError):
        return ""


def _beschriftung(domain: str, fingerabdruck: str) -> dict[str, str]:
    r = "ota-git"
    return {
        "ota.dienst": "git",
        "ota.git.fingerabdruck": fingerabdruck,
        "traefik.enable": "true",
        "traefik.docker.network": OEFFENTLICH,
        # Vor allen Pfadregeln von OTA (/api hat 50): Unter der Subdomain
        # gehört alles Forgejo, auch /api/v1.
        f"traefik.http.routers.{r}.rule": f"Host(`{domain}`)",
        f"traefik.http.routers.{r}.entrypoints": "websecure,git-intern",
        f"traefik.http.routers.{r}.tls": "true",
        f"traefik.http.routers.{r}.priority": "1000",
        f"traefik.http.routers.{r}.service": r,
        f"traefik.http.services.{r}.loadbalancer.server.port": "3000",
        f"traefik.tcp.routers.{r}-ssh.rule": "HostSNI(`*`)",
        f"traefik.tcp.routers.{r}-ssh.entrypoints": "git-ssh",
        f"traefik.tcp.routers.{r}-ssh.service": f"{r}-ssh",
        f"traefik.tcp.services.{r}-ssh.loadbalancer.server.port": "22",
    }


def _bild(client) -> None:
    try:
        client.images.get(BILD)
    except ImageNotFound:
        log.info("Hole %s", BILD)
        client.images.pull(BILD)


def status(client) -> dict[str, Any]:
    try:
        c = client.containers.get(NAME)
    except NotFound:
        return {"container": "fehlt", "bild": BILD}
    gesund = ((c.attrs.get("State") or {}).get("Health") or {}).get("Status")
    return {"container": c.status, "gesund": gesund, "bild": c.image.tags[0] if c.image.tags else BILD,
            "domain": (c.labels or {}).get("ota.git.domain", "")}


def an(client, domain: str, umgebung: dict[str, str]) -> dict[str, Any]:
    """Den Container nach diesen Angaben laufen lassen — anlegen oder ersetzen."""
    domain = domain.strip().lower()
    if not DOMAIN_OK.fullmatch(domain):
        raise ValueError(f"„{domain}“ ist kein gültiger Name.")
    _bild(client)
    _dateien_schreiben(domain)

    env = {str(k): str(v) for k, v in umgebung.items()}
    env["FORGEJO__database__PASSWD"] = os.environ.get("OTA_GIT_DB_PW", "")
    env["FORGEJO__security__REVERSE_PROXY_TRUSTED_PROXIES"] = _subnetz(client, OEFFENTLICH) or "127.0.0.1/8"
    # Der CA von OTA trauen — für Keycloak — und den üblichen ebenso.
    env["SSL_CERT_DIR"] = "/etc/ssl/certs:/etc/ota-ca"
    env.setdefault("USER_UID", "1000")
    env.setdefault("USER_GID", "1000")

    fingerabdruck = hashlib.sha256(json.dumps(
        {"bild": BILD, "domain": domain, "env": sorted(env.items())}, sort_keys=True
    ).encode()).hexdigest()[:16]

    try:
        alt = client.containers.get(NAME)
    except NotFound:
        alt = None
    if alt is not None and (alt.labels or {}).get("ota.git.fingerabdruck") == fingerabdruck:
        if alt.status != "running":
            alt.start()
        return {"neu": False, **status(client)}
    if alt is not None:
        log.info("OTA-Git: Einstellungen geändert — Container wird ersetzt (Daten bleiben)")
        alt.remove(force=True)

    beschriftung = _beschriftung(domain, fingerabdruck)
    beschriftung["ota.git.domain"] = domain
    c = client.containers.create(
        BILD, name=NAME, hostname=NAME, detach=True,
        environment=env, labels=beschriftung,
        volumes={VOLUME: {"bind": "/data", "mode": "rw"},
                 _ca_ordner(): {"bind": "/etc/ota-ca", "mode": "ro"}},
        network=OEFFENTLICH,
        restart_policy={"Name": "unless-stopped"},
        healthcheck={"test": ["CMD-SHELL", "wget -q -O- http://127.0.0.1:3000/api/healthz || exit 1"],
                     "interval": 15_000_000_000, "timeout": 5_000_000_000,
                     "retries": 5, "start_period": 30_000_000_000},
        log_config={"Type": "json-file", "Config": {"max-size": "10m", "max-file": "3"}},
    )
    client.networks.get(INTERN).connect(c)
    c.start()
    return {"neu": True, **status(client)}


def aus(client) -> dict[str, Any]:
    """Anhalten. Container, Volume und Datenbank bleiben."""
    try:
        c = client.containers.get(NAME)
    except NotFound:
        return {"container": "fehlt"}
    if c.status == "running":
        c.stop(timeout=20)
    try:
        os.remove(os.path.join(TRAEFIK_DYNAMIC, "ota-git.yml"))
    except FileNotFoundError:
        pass
    return status(client)


def warten(client, sekunden: int = 120) -> bool:
    ende = time.monotonic() + sekunden
    while time.monotonic() < ende:
        if status(client).get("gesund") == "healthy":
            return True
        time.sleep(2)
    return False


def _cli(c, *argv: str) -> tuple[int, str]:
    res = c.exec_run(["forgejo", "admin", *argv], user="git", demux=False)
    return res.exit_code, (res.output or b"").decode("utf-8", "replace")


def einrichten(client, admin_pw: str, oauth: dict[str, str]) -> dict[str, Any]:
    """Notzugang `ota-admin` und die Anmeldequelle Keycloak — beides so, dass
    ein zweiter Aufruf dasselbe Ergebnis hat."""
    c = client.containers.get(NAME)

    code, out = _cli(c, "user", "list", "--admin")
    if "ota-admin" not in out:
        code, out = _cli(c, "user", "create", "--admin", "--username", "ota-admin",
                         "--password", admin_pw, "--email", "ota-admin@ota.invalid",
                         "--must-change-password=false")
    else:
        code, out = _cli(c, "user", "change-password", "--username", "ota-admin",
                         "--password", admin_pw, "--must-change-password=false")
    if code != 0:
        raise RuntimeError(f"Notzugang: {out.strip()[-300:]}")

    _, liste = _cli(c, "auth", "list")
    quelle = None
    for zeile in liste.splitlines()[1:]:
        teile = zeile.split()
        if len(teile) >= 2 and teile[1] == oauth["name"]:
            quelle = teile[0]
    gemeinsam = ["--name", oauth["name"], "--provider", "openidConnect",
                 "--key", oauth["key"], "--secret", oauth["secret"],
                 "--auto-discover-url", oauth["discovery"],
                 "--scopes", "openid", "--scopes", "profile", "--scopes", "email",
                 "--skip-local-2fa"]
    if quelle is None:
        code, out = _cli(c, "auth", "add-oauth", *gemeinsam)
    else:
        code, out = _cli(c, "auth", "update-oauth", "--id", quelle, *gemeinsam)
    if code != 0:
        raise RuntimeError(f"Anmeldequelle: {out.strip()[-300:]}")
    if quelle is not None:
        # Der laufende Server liest seine Anmeldequellen nur beim Start. Ohne
        # Neustart arbeitete er mit dem alten Geheimnis weiter, und jede
        # Anmeldung endete stumm wieder auf der Anmeldeseite (gemessen).
        c.restart(timeout=20)
        if not warten(client):
            raise RuntimeError("Forgejo kam nach dem Neustart nicht wieder.")
    _, liste = _cli(c, "auth", "list")
    for zeile in liste.splitlines()[1:]:
        teile = zeile.split()
        if len(teile) >= 2 and teile[1] == oauth["name"]:
            return {"quelle": int(teile[0])}
    raise RuntimeError("Die Anmeldequelle ist nach dem Anlegen nicht auffindbar.")


# --------------------------------------------------------------------------
# Im Arbeitsplatz (Kapitel 27, Abschnitt „Vorkonfiguriert“)
# --------------------------------------------------------------------------
#
# Als root, bei jedem Start und Fortsetzen. Alles liegt unter /etc/ota-git und
# wird über die **System**-Konfiguration von Git eingebunden — die mit dem
# niedrigsten Rang: Was der Mensch in seiner ~/.gitconfig setzt, gewinnt.
# Die Regeln gelten nur für die Adresse von OTA-Git; jeder andere Server
# bekommt weder das Token noch die CA.

_EINRICHTEN = r"""
set -e
D=/etc/ota-git
DOMAIN="$1"; IP="$2"; NUTZER="$3"
mkdir -p "$D"; chmod 755 "$D"
# /etc/hosts: der Name zeigt auf Traefik im eigenen Sitzungsnetz.
if [ -w /etc/hosts ]; then
  grep -v ' # ota-git$' /etc/hosts > /tmp/.ota-hosts || true
  [ -n "$DOMAIN" ] && echo "$IP $DOMAIN # ota-git" >> /tmp/.ota-hosts
  cat /tmp/.ota-hosts > /etc/hosts; rm -f /tmp/.ota-hosts
fi
if [ -z "$DOMAIN" ]; then
  rm -rf "$D"
  [ -f /etc/gitconfig ] && sed -i '/# ota-git$/d' /etc/gitconfig
  echo "ota-git aus"; exit 0
fi
cat > "$D/token"; chmod 644 "$D/token"
cat > "$D/hilfe" <<'HILFE'
#!/bin/sh
# Credential-Helper für OTA-Git. Gibt nur bei „get" etwas aus.
[ "$1" = get ] || exit 0
cat >/dev/null
echo "username=$(cat /etc/ota-git/nutzer)"
echo "password=$(cat /etc/ota-git/token)"
HILFE
chmod 755 "$D/hilfe"
printf '%s' "$NUTZER" > "$D/nutzer"; chmod 644 "$D/nutzer"
"""

_GITCONFIG = """# ERZEUGT von OTA (Kapitel 27) — gilt nur für OTA-Git.
[credential "https://{domain}"]
\thelper = /etc/ota-git/hilfe
[http "https://{domain}/"]
\tsslCAInfo = /etc/ota-git/ca.crt
[user]
\tname = {name}
\temail = {email}
"""


def im_container(container, git: dict[str, Any], traefik_ip: str, run_as_root) -> None:
    """OTA-Git im Arbeitsplatz einrichten — oder, bei leerem `git`, entfernen."""
    domain = str(git.get("domain") or "")
    try:
        if not domain:
            run_as_root(container, ["sh", "-c", _EINRICHTEN, "sh", "", "", ""])
            return
        skript = _EINRICHTEN + (
            "cat > \"$D/ca.crt\" <<'CA'\n" + git["ca"].strip() + "\nCA\n"
            "cat > \"$D/gitconfig\" <<'CFG'\n"
            + _GITCONFIG.format(domain=domain, name=git.get("name") or git["nutzer"],
                                email=git.get("email") or "")
            + "CFG\n"
            "touch /etc/gitconfig\n"
            "grep -q '# ota-git$' /etc/gitconfig || "
            "printf '[include] # ota-git\\n\\tpath = /etc/ota-git/gitconfig # ota-git\\n' >> /etc/gitconfig\n"
            "echo ota-git eingerichtet\n")
        # Das Token über stdin, nicht in der Befehlszeile: Die steht in `ps`.
        res = container.client.api.exec_create(
            container.id, ["sh", "-c", skript, "sh", domain, traefik_ip, git["nutzer"]],
            user="root", stdin=True)
        sock = container.client.api.exec_start(res["Id"], socket=True)
        roh = getattr(sock, "_sock", sock)
        roh.sendall(str(git["token"]).encode())
        roh.shutdown(1)
        ausgabe = b""
        while True:
            stueck = roh.recv(4096)
            if not stueck:
                break
            ausgabe += stueck
        roh.close()
        code = container.client.api.exec_inspect(res["Id"]).get("ExitCode")
        if code:
            log.warning("OTA-Git in %s nicht eingerichtet: %s", container.name,
                        ausgabe.decode("utf-8", "replace")[-300:])
    except (APIError, OSError, KeyError) as exc:
        log.warning("OTA-Git in %s nicht eingerichtet: %s", container.name, exc)
