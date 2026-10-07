"""Das eigene Paket-Repository in Container eintragen (Handbuch Kapitel 26).

Ein Skript fuer beide Wege: Der Agent fuehrt es beim Start eines
Arbeitsplatzes als root aus, der Bildbauer setzt es als erste `RUN`-Zeile in
den Bau (und das Gegenstueck als letzte). So sehen laufende Arbeitsplaetze
und Bauten dieselben Quellen — und kein Image muss dafuer neu gebaut werden.

**Nur bei Debian 13.** Das Skript liest `/etc/os-release` und tut sonst
nichts. Kasm-Images (Ubuntu) bleiben unveraendert.

**Die CA nur fuer apt, nur fuer diese Adresse.** Das Repo liegt unter OTAs
eigener Adresse mit OTAs eigener CA. Die steht in keinem Basisimage; sie
systemweit einzutragen hiesse, ihr fuer alles zu vertrauen. Statt dessen
`Acquire::https::<host>::CaInfo` — apt vertraut ihr genau hier.

Die drei Betriebsarten:

  aus      nichts eingetragen (und was frueher eingetragen war, entfernt)
  zuerst   eigene Quellen mit Vorrang 900, die des Images bleiben als
           Rueckfall — das Internet wird nur fuer Fehlendes benutzt
  nur      nur die eigenen; die des Images werden stillgelegt (umbenannt,
           nicht geloescht — ein spaeterer Wechsel stellt sie wieder her)
"""

from __future__ import annotations

import base64
import os
import shlex
from typing import Any

ENDUNG = ".ota-aus"

# **`00-` vorn ist kein Schmuck.** apt laedt bei gleicher Version von der
# Quelle, die es zuerst gelesen hat — der Vorrang (Pin 900) entscheidet nur,
# *welche Version*, nicht *woher*. `debian.sources` kam alphabetisch vor
# `ota-repo.sources`, und gemessen am 2026-10-07 holte apt `hello` trotz
# Vorrang aus dem Internet. Mit `00-` liest apt die eigene Quelle zuerst.


def basis_url() -> tuple[str, str]:
    """(URL des Repos, Rechnername) — unter OTAs Adresse von innen."""
    from .main import _wirt  # spaet, um Kreisimporte zu vermeiden

    host = _wirt(os.environ.get("OTA_SELF_ADDRESS", "")) or "127.0.0.1"
    port = os.environ.get("OTA_HTTPS_PORT", "8443")
    return f"https://{host}:{port}/repo", host


def _b64(text: str) -> str:
    return base64.b64encode(text.encode("utf-8")).decode("ascii")


def einrichten_skript(repo: dict[str, Any], snapshot: str = "") -> str:
    """Shell-Skript, das die Quellen dem Modus nach eintraegt (als root)."""
    modus = repo.get("modus", "aus")
    url, host = basis_url()
    quellen = [q for q in repo.get("quellen", [])
               if (q["prefix"].startswith(f"snap/{snapshot}/") if snapshot
                   else not q["prefix"].startswith("snap/"))]
    bloecke = []
    for prefix in sorted({q["prefix"] for q in quellen}):
        suiten = " ".join(sorted(q["dist"] for q in quellen if q["prefix"] == prefix))
        komp = next(q["comp"] for q in quellen if q["prefix"] == prefix)
        bloecke.append(f"Types: deb\nURIs: {url}/{prefix}\nSuites: {suiten}\n"
                       f"Components: {komp}\nSigned-By: /etc/apt/keyrings/ota-repo.asc\n")
    sources = "\n".join(bloecke)
    praefs = (f"Package: *\nPin: origin \"{host}\"\nPin-Priority: 900\n"
              if modus == "zuerst" else "")
    aptconf = f'Acquire::https::{host}::CaInfo "/etc/apt/ota-repo-ca.crt";\n'
    # Ohne Umweg ueber einen Firmenproxy: Die Paketquelle ist OTA selbst. Der
    # Agent traegt fuer apt nur http-Ausnahmen ein; ueber https lief die
    # eigene Quelle sonst an den Proxy, und der kennt sie nicht (gefunden
    # 2026-10-08 auf einer Anlage hinter einem Proxy).
    aptconf += (f'Acquire::https::Proxy::{host} "DIRECT";\n'
                f'Acquire::http::Proxy::{host} "DIRECT";\n')

    return f"""set -e
[ -r /etc/os-release ] || exit 0
. /etc/os-release
if [ "${{ID:-}}" != "debian" ] || [ "${{VERSION_CODENAME:-}}" != "trixie" ]; then
  echo "ota-repo: kein Debian 13 — nichts eingetragen"; exit 0
fi
# Was ein frueherer Modus „nur" stillgelegt hat, wieder herstellen.
for f in /etc/apt/sources.list{ENDUNG} /etc/apt/sources.list.d/*{ENDUNG}; do
  if [ -e "$f" ]; then mv -f "$f" "${{f%{ENDUNG}}}"; fi
done
rm -f /etc/apt/sources.list.d/00-ota-repo.sources /etc/apt/preferences.d/ota-repo \\
      /etc/apt/apt.conf.d/50ota-repo /etc/apt/keyrings/ota-repo.asc /etc/apt/ota-repo-ca.crt
MODUS={shlex.quote(modus)}
if [ "$MODUS" = "aus" ]; then echo "ota-repo: aus"; exit 0; fi
mkdir -p /etc/apt/keyrings /etc/apt/sources.list.d /etc/apt/preferences.d /etc/apt/apt.conf.d
printf '%s' {shlex.quote(_b64(repo.get("schluessel", "")))} | base64 -d > /etc/apt/keyrings/ota-repo.asc
printf '%s' {shlex.quote(_b64(repo.get("ca", "")))} | base64 -d > /etc/apt/ota-repo-ca.crt
printf '%s' {shlex.quote(_b64(aptconf))} | base64 -d > /etc/apt/apt.conf.d/50ota-repo
printf '%s' {shlex.quote(_b64(sources))} | base64 -d > /etc/apt/sources.list.d/00-ota-repo.sources
chmod 644 /etc/apt/keyrings/ota-repo.asc /etc/apt/ota-repo-ca.crt \\
          /etc/apt/apt.conf.d/50ota-repo /etc/apt/sources.list.d/00-ota-repo.sources
if [ "$MODUS" = "zuerst" ]; then
  printf '%s' {shlex.quote(_b64(praefs))} | base64 -d > /etc/apt/preferences.d/ota-repo
fi
if [ "$MODUS" = "nur" ]; then
  for f in /etc/apt/sources.list /etc/apt/sources.list.d/*.list /etc/apt/sources.list.d/*.sources; do
    if [ ! -e "$f" ] || [ "$f" = /etc/apt/sources.list.d/00-ota-repo.sources ]; then continue; fi
    mv -f "$f" "$f{ENDUNG}"
  done
fi
echo "ota-repo: $MODUS"
"""


def aufraeumen_skript() -> str:
    """Gegenstueck fuer den Bau: Ein fertiges Image traegt die Adresse dieses
    Wirts nicht — auf einem zweiten Wirt liefe es sonst ins Leere."""
    return f"""rm -f /etc/apt/sources.list.d/00-ota-repo.sources /etc/apt/preferences.d/ota-repo \\
      /etc/apt/apt.conf.d/50ota-repo /etc/apt/keyrings/ota-repo.asc /etc/apt/ota-repo-ca.crt
for f in /etc/apt/sources.list{ENDUNG} /etc/apt/sources.list.d/*{ENDUNG}; do
  if [ -e "$f" ]; then mv -f "$f" "${{f%{ENDUNG}}}"; fi
done
true
"""


def als_run(skript: str) -> str:
    """Eine Dockerfile-Zeile, die das Skript ausfuehrt — base64, damit keine
    Anfuehrungszeichen und Zeilenumbrueche im Dockerfile etwas anderes tun."""
    return f"RUN printf '%s' {shlex.quote(_b64(skript))} | base64 -d | sh"
