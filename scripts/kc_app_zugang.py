#!/usr/bin/env python3
"""Meldet sich wie ein Browser bei einer **fremden Anwendung** an — und sagt,
ob Keycloak hineinlässt. Für die Prüfreihen (scripts/test-verzeichnis.sh).

    kc_app_zugang.py BASIS CLIENT REDIRECT KEKSDOSE [NAME PASSWORT]

Ohne Name und Passwort zählt nur die SSO-Sitzung in der Keksdose — der Fall
„in OTA angemeldet, jetzt zur Anwendung". Ausgabe, eine Zeile:

    ZUGANG       Keycloak schickt einen Code an die Anwendung
    VERWEIGERT   Keycloak weist ab („Kein Zugang zu dieser Anwendung")
    FORMULAR     Keycloak will eine Anmeldung, und es wurde keine mitgegeben
    ? …          etwas anderes, mit dem, was zu sehen war

Die Anwendung selbst wird nie aufgerufen: Die Weiterleitung zu ihr wird nur
gelesen, nicht befolgt.
"""
from __future__ import annotations

import html
import http.cookiejar
import re
import ssl
import sys
import urllib.error
import urllib.parse as up
import urllib.request

basis, client, redirect, dose_pfad = sys.argv[1:5]
name = sys.argv[5] if len(sys.argv) > 5 else None
passwort = sys.argv[6] if len(sys.argv) > 6 else None

dose = http.cookiejar.MozillaCookieJar(dose_pfad)
try:
    dose.load(ignore_discard=True, ignore_expires=True)
except (OSError, http.cookiejar.LoadError):
    pass

ctx = ssl.create_default_context()
ctx.check_hostname = False
ctx.verify_mode = ssl.CERT_NONE


class NichtZurAnwendung(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, hdrs, newurl):
        if newurl.startswith(redirect):
            return None
        return super().redirect_request(req, fp, code, msg, hdrs, newurl)


oeffner = urllib.request.build_opener(urllib.request.HTTPSHandler(context=ctx),
                                      urllib.request.HTTPCookieProcessor(dose),
                                      NichtZurAnwendung())


def hole(url: str, daten: dict | None = None):
    try:
        r = oeffner.open(url, up.urlencode(daten).encode() if daten else None, timeout=30)
        return r.status, r.read().decode("utf-8", "replace"), None
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode("utf-8", "replace"), e.headers.get("Location")


def deute(code: int, seite: str, ziel: str | None) -> str:
    if ziel and ziel.startswith(redirect) and "code=" in ziel:
        return "ZUGANG"
    if "Kein Zugang" in seite or (ziel and "error=access_denied" in ziel):
        return "VERWEIGERT"
    if 'id="kc-form-login"' in seite:
        return "FORMULAR"
    m = re.search(r'kc-feedback-text">\s*([^<]+)', seite) or re.search(r"<title>([^<]+)", seite)
    return f"? {code} {ziel or ''} {m.group(1).strip() if m else seite[:120]}"


url = f"{basis}/auth/realms/ota/protocol/openid-connect/auth?" + up.urlencode({
    "client_id": client, "response_type": "code", "scope": "openid",
    "redirect_uri": redirect, "state": "pruefung"})
code, seite, ziel = hole(url)
ergebnis = deute(code, seite, ziel)
if ergebnis == "FORMULAR" and name:
    aktion = html.unescape(re.search(r'action="([^"]+)"', seite).group(1))
    code, seite, ziel = hole(aktion, {"username": name, "password": passwort, "credentialId": ""})
    ergebnis = deute(code, seite, ziel)
dose.save(ignore_discard=True, ignore_expires=True)
print(ergebnis)
sys.exit(0 if ergebnis in ("ZUGANG", "VERWEIGERT", "FORMULAR") else 1)
