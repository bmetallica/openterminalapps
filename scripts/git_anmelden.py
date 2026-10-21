#!/usr/bin/env python3
"""Meldet sich wie ein Browser bei OTA-Git an — über Keycloak, mit der
SSO-Sitzung aus OTA. Für die Prüfreihe scripts/test-git.sh.

    git_anmelden.py GIT_NAME GIT_IP KEKSDOSE

GIT_NAME ist die Subdomain (git.ota.test), GIT_IP die Adresse, auf die sie
zeigen soll — in der Prüfung Traefik in einem seiner Netze, so wie in einem
Arbeitsplatz. Die Keksdose braucht die SSO-Sitzung (scripts/kc_anmelden.py).

Ausgabe, eine Zeile JSON:

    {"ergebnis": "ZUGANG", "login": "...", "is_admin": true}
    {"ergebnis": "VERWEIGERT"}         Keycloak: „Kein Zugang zu dieser Anwendung"
    {"ergebnis": "?", "seite": "…"}
"""
from __future__ import annotations

import http.cookiejar
import json
import re
import socket
import ssl
import sys
import urllib.error
import urllib.request

name, ip, dose_pfad = sys.argv[1:4]

_echt = socket.getaddrinfo


def _aufloesen(host, *rest, **kw):
    return _echt(ip if host == name else host, *rest, **kw)


socket.getaddrinfo = _aufloesen

dose = http.cookiejar.MozillaCookieJar(dose_pfad)
try:
    dose.load(ignore_discard=True, ignore_expires=True)
except (OSError, http.cookiejar.LoadError):
    pass
ctx = ssl.create_default_context()
ctx.check_hostname = False
ctx.verify_mode = ssl.CERT_NONE
oeffner = urllib.request.build_opener(urllib.request.HTTPSHandler(context=ctx),
                                      urllib.request.HTTPCookieProcessor(dose))


def hole(url: str):
    try:
        r = oeffner.open(url, timeout=30)
        return r.status, r.geturl(), r.read().decode("utf-8", "replace")
    except urllib.error.HTTPError as e:
        return e.code, e.url, e.read().decode("utf-8", "replace")


code, ziel, seite = hole(f"https://{name}/user/oauth2/ota")
aus: dict = {"ergebnis": "?"}
if "Kein Zugang" in seite:
    aus["ergebnis"] = "VERWEIGERT"
else:
    # Die API nimmt die Browser-Sitzung nicht an; die Seite sagt, wer man ist.
    _, _, profil = hole(f"https://{name}/user/settings")
    treffer = re.search(r'name="name" value="([^"]+)"', profil)
    if code == 200 and treffer and "/user/login" not in (ziel or ""):
        login = treffer.group(1)
        a_code, _, _ = hole(f"https://{name}/admin")
        aus = {"ergebnis": "ZUGANG", "login": login, "is_admin": a_code == 200}
    else:
        aus["seite"] = (ziel or "") + " " + seite[:200]
dose.save(ignore_discard=True, ignore_expires=True)
print(json.dumps(aus, ensure_ascii=False))
