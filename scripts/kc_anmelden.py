#!/usr/bin/env python3
"""Meldet sich wie ein Browser über Keycloak bei OTA an — für die Prüfreihen.

Seit dem 2026-10-08 entstehen Konten in Keycloak, und lokal meldet sich nur
noch das Notfallkonto an. Eine Prüfreihe, die ein gewöhnliches Konto braucht,
geht deshalb denselben Weg wie ein Mensch: OTA → Keycloaks Anmeldemaske →
zurück zu OTA, das sein Cookie setzt.

    kc_anmelden.py BASIS NAME PASSWORT KEKSDOSE [--neu NEUES] [--aktion AKTION]

Die Keksdose ist im Netscape-Format, wie `curl -b/-c` sie liest. Verlangt
Keycloak ein neues Passwort (erstes Anmelden, oder `--aktion UPDATE_PASSWORD`),
wird `--neu` eingesetzt. Ausgabe: `ok <angemeldet als>` oder `fehler: <grund>`;
Rückgabewert 0 bzw. 1.
"""
from __future__ import annotations

import argparse
import html
import http.cookiejar
import json
import re
import ssl
import sys
import urllib.parse
import urllib.request

ap = argparse.ArgumentParser()
ap.add_argument("basis")
ap.add_argument("name")
ap.add_argument("passwort")
ap.add_argument("keksdose")
ap.add_argument("--neu", default="")
ap.add_argument("--aktion", default="")
a = ap.parse_args()

dose = http.cookiejar.MozillaCookieJar(a.keksdose)
try:
    dose.load(ignore_discard=True, ignore_expires=True)
except (OSError, http.cookiejar.LoadError):
    pass
ktx = ssl.create_default_context()
ktx.check_hostname = False
ktx.verify_mode = ssl.CERT_NONE
oeffner = urllib.request.build_opener(
    urllib.request.HTTPCookieProcessor(dose), urllib.request.HTTPSHandler(context=ktx))


def holen(url: str, daten: dict | None = None) -> tuple[str, str]:
    """GET oder POST, folgt Weiterleitungen. (Endadresse, Seite)"""
    roh = urllib.parse.urlencode(daten).encode() if daten is not None else None
    try:
        with oeffner.open(url, data=roh, timeout=30) as r:
            return r.geturl(), r.read().decode("utf-8", "replace")
    except urllib.error.HTTPError as e:
        return e.geturl(), e.read().decode("utf-8", "replace")


def formular(seite: str, kennung: str) -> str | None:
    m = re.search(r'<form[^>]*id="' + kennung + r'"[^>]*action="([^"]+)"', seite)
    return html.unescape(m.group(1)) if m else None


def fehlermeldung(seite: str) -> str:
    for muster in (r'id="input-error[^"]*"[^>]*>\s*([^<]+)<', r'class="[^"]*kc-feedback-text[^"]*"[^>]*>\s*([^<]+)<',
                   r'class="pf-v5-c-alert__title[^"]*"[^>]*>\s*([^<]+)<', r"<title>([^<]+)</title>"):
        m = re.search(muster, seite)
        if m and m.group(1).strip():
            return html.unescape(m.group(1).strip())
    return "unbekannt"


frage = {"next": "/"}
if a.aktion:
    frage["aktion"] = a.aktion
url, seite = holen(f"{a.basis}/api/auth/oidc/start?{urllib.parse.urlencode(frage)}")

for _ in range(6):
    if "/auth/realms/" not in url:
        break                                    # zurück bei OTA
    ziel = formular(seite, "kc-form-login")
    if ziel:
        url, seite = holen(ziel, {"username": a.name, "password": a.passwort, "credentialId": ""})
        continue
    ziel = formular(seite, "kc-passwd-update-form")
    if ziel:
        if not a.neu:
            print("fehler: Keycloak verlangt ein neues Passwort (--neu fehlt)")
            sys.exit(1)
        url, seite = holen(ziel, {"password-new": a.neu, "password-confirm": a.neu})
        continue
    print(f"fehler: {fehlermeldung(seite)}")
    sys.exit(1)
else:
    print(f"fehler: kein Ende bei Keycloak ({fehlermeldung(seite)})")
    sys.exit(1)

dose.save(ignore_discard=True, ignore_expires=True)
_, ich = holen(f"{a.basis}/api/auth/me")
try:
    print("ok", json.loads(ich)["username"])
except (ValueError, KeyError):
    print(f"fehler: zurück bei OTA, aber nicht angemeldet ({url})")
    sys.exit(1)
