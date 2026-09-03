# Fremde Software in und um OpenTerminalApps

OTA besteht aus eigenem Code, betreibt fremde Dienste und **startet fremde
Container-Images**. Diese drei Dinge unterliegen verschiedenen Lizenzen, und
sie sauber auseinanderzuhalten ist der Zweck dieser Datei.

> **Fremde Software behält ihre eigene Lizenz.** OTA lizenziert nichts davon
> unter Apache-2.0 neu. Dass ein Bestandteil hier aufgeführt ist, heißt: Er
> wird verwendet — nicht: Er gehört zu OTA.

Diese Datei ist eine Orientierung, keine Rechtsberatung, und sie ist bei
Ebene 3 naturgemäß unvollständig — siehe [Grenzen](#grenzen).

---

## Ebene 1 — dieses Repository

**Apache-Lizenz 2.0**, siehe [LICENSE](LICENSE).

| Verzeichnis | Inhalt |
|---|---|
| `api/` | REST-API, Anmeldung, Rechte, Sessions |
| `agent/` | Der einzige Dienst mit Docker-Zugriff |
| `web/` | Oberfläche |
| `extension/` | Firefox-Erweiterung für die Zwischenablage |
| `scripts/`, `tests/`, `deploy/` | Prüfungen, Zertifikat, Stack |
| `docs/` | Handbuch und Architekturentscheidungen |

**Hier liegt keine fremde Software.** Abhängigkeiten werden beim Bauen
geholt und sind nicht eingecheckt (`node_modules/` ist ausgeschlossen). Die
Repository-Grenze ist damit zugleich die Lizenzgrenze — deshalb tragen die
einzelnen Dateien keine SPDX-Kopfzeilen: Sie würden dieselbe Aussage
hundertfach wiederholen.

---

## Ebene 2 — mitbetriebene Dienste und Bibliotheken

Werden zur Laufzeit als Images bezogen oder beim Bauen installiert. Sie sind
**nicht Bestandteil dieses Repositories**.

### Im Stack

| Bestandteil | Lizenz | Wofür |
|---|---|---|
| Traefik | MIT | Eingang, TLS, Routen |
| PostgreSQL | PostgreSQL-Lizenz | Datenbank |
| Docker Distribution (Registry) | Apache-2.0 | Eigene Registry |
| nginx | BSD-2-Clause | Auslieferung der Oberfläche |

### In der API und im Agent (Python)

FastAPI, Uvicorn, SQLAlchemy, Alembic, Pydantic (alle MIT bzw. BSD),
`psycopg` (LGPL-3.0), `argon2-cffi` (MIT), `PyJWT` (MIT), `httpx` (BSD-3),
`pyotp` (MIT), `qrcode` (BSD), `ldap3` (LGPL-3.0), `docker` (Apache-2.0).

### In der Oberfläche (Node)

React (MIT), Vite (MIT), TypeScript (Apache-2.0) und deren Abhängigkeiten.
Maßgeblich ist der jeweilige Stand in `web/package-lock.json`.

> Die Aufstellung nennt die unmittelbaren Abhängigkeiten. Die vollständige,
> transitive Liste steht in den Lock-Dateien (`api/requirements.txt`,
> `web/package-lock.json`) und ist dort auch die verlässlichere Quelle.

---

## Ebene 3 — Inhalt der Workspace-Images

**Das ist die Ebene, bei der Missverständnisse teuer werden.** Ein
Arbeitsplatz-Image ist ein zusammengesetztes Werk aus hunderten Paketen.
Nichts davon wird durch OTA neu lizenziert.

| Bestandteil | Lizenz | Anmerkung |
|---|---|---|
| **Selkies** | **MPL-2.0** | Die Streaming-Engine des Vorgabe-Images. **OTA ändert sie** — siehe unten |
| **libx264** | **GPL-2.0+** | Der Kodierer, über `gstreamer1.0-plugins-ugly` |
| GStreamer (base/good/bad/ugly) | LGPL-2.0+ (die Pakete) | Einzelne Plugins binden GPL-Bibliotheken ein |
| **KasmVNC** | GPL-2.0 | Nur noch im alten Image `base-xfce` |
| **Kasm-Workspaces-Images** | MIT **nur für die Baurezepte** | Siehe unten |
| XFCE | GPL | Desktop |
| Debian 13 / Ubuntu | Paketweise verschieden | Basis |
| Adwaita-Symbole | CC-BY-SA-3.0 oder LGPL-3, und CC-BY-SA-4.0 | Zeiger und Symbole |
| DejaVu-Schriften | Bitstream Vera | |
| **Microsoft Visual Studio Code** | Microsoft-EULA | Siehe unten |
| VSCodium | MIT | Erweiterungen über Open VSX |
| JetBrains Community | Apache-2.0 | Nur die Community-Ausgaben |
| Firefox | MPL-2.0 | |
| Google Chrome | Google-Nutzungsbedingungen | Proprietär |
| Sonstige Anwendungen | jeweils eigene | Was im Image installiert wurde |

Alle Angaben oben sind am 2026-09-03 aus dem gebauten Image abgelesen
(`/usr/share/doc/<paket>/copyright` bzw. die Metadaten des Python-Pakets),
nicht aus dem Gedächtnis.

### Selkies — MPL-2.0, und OTA ändert es

Das ist der Punkt, der beim Wechsel auf das eigene Basisimage **neu
hinzugekommen** ist und der leicht übersehen wird.

OTA startet Selkies nicht nur, sondern **verändert es beim Bauen des Images**.
Vier Eingriffe, alle in `images/base-desktop/patches/`:

| Patch | Was er ändert |
|---|---|
| `gst-web-pfad.py` | zwei Adressen im Client, die sonst an der Wurzel des Hosts hängen |
| `kein-fremd-stun.py` | nimmt `stun.l.google.com` aus der Konfiguration |
| `ice-nur-vermittelt.py` | macht `iceTransportPolicy` einstellbar |
| `keine-fremde-leiste.py` | entfernt den Knopf für Selkies' eigene Seitenleiste |

Die MPL-2.0 verlangt (§3.1/3.2): Wer die Software weitergibt, muss die
**geänderten Dateien im Quelltext** unter derselben Lizenz verfügbar machen.
Für OTA heisst das bei Weitergabe eines Images:

* Die vier Patch-Dateien mitliefern — sie beschreiben die Änderung
  vollständig und sind selbst lesbar.
* Auf das verwendete Release verweisen
  (`github.com/selkies-project/selkies-gstreamer`, Tag `v<SELKIES_VERSION>`).
* Den Lizenztext der MPL-2.0 beilegen.

Was die MPL **nicht** verlangt: dass OTAs eigener Code unter MPL steht. Sie
wirkt dateiweise, nicht auf das ganze Werk.

### libx264 — GPL-2.0+, und damit die eigentliche Pflicht

Die GStreamer-Pakete selbst sind LGPL. Der Kodierer dahinter ist es nicht:
`gstreamer1.0-plugins-ugly` bringt `libgstx264.so`, und das bindet **libx264
(GPL-2.0+)** ein. Wer ein Image weitergibt, in dem der H.264-Kodierer steckt —
und das ist jedes Selkies-Image —, übernimmt damit die Pflichten der GPL:
Lizenztext beilegen, auf die Quellen verweisen oder sie anbieten.

Praktisch ist das dasselbe wie bei KasmVNC vorher, nur mit einem anderen
Programm. Das Debian-Paket verweist auf `deb-src`; das ist ein gangbarer Weg,
den Bezug der Quellen zu belegen.

### KasmVNC — GPL-2.0 (nur noch im alten Image)

Seit `ota/base-desktop` die Vorgabe ist, steckt KasmVNC **nur noch in
`images/base-xfce`** — dem Image des bisherigen Weges, das weiter
gepflegt wird, solange Arbeitsplätze darauf laufen. Für das neue Image
gilt nichts davon; es enthält keine Zeile KasmVNC.

Der folgende Abschnitt bleibt trotzdem stehen: Er begründet, warum das
eigene Image überhaupt gebaut wurde, und gilt unverändert für jeden,
der den KasmVNC-Weg weiter benutzt.


OTA **startet** KasmVNC als eigenständiges Programm (`/usr/bin/Xvnc`) und
spricht mit ihm über Netz und Prozessgrenze. Es wird kein KasmVNC-Quellcode
in OTA übernommen und nichts damit gelinkt. Deshalb bleibt OTA Apache-2.0 und
KasmVNC bleibt GPL-2.0 — zwei Programme, die nebeneinander laufen.

> **Wer ein Image weitergibt, gibt KasmVNC mit weiter.** Dann greifen die
> Pflichten der GPL-2.0 für diesen Bestandteil: Lizenztext und Hinweise
> müssen erhalten bleiben, und der zugehörige Quellcode muss verfügbar sein.
> Das macht nicht das ganze Image zu GPL — es heißt, dass der GPL-Teil ein
> GPL-Teil bleibt.
>
> KasmVNC führt neben der GPL noch eine eigene Liste von Drittanbieter-
> Hinweisen. Wer ein KasmVNC-haltiges Image verteilt, sollte die
> Lizenz- und Hinweisdateien der jeweiligen KasmVNC-Fassung mitgeben, statt
> sich auf „KasmVNC = GPL-2.0" zu verlassen.

#### Darf KasmVNC in ein eigenes Image? — Ja, und es ist sauberer als vorher

Geprüft am 2026-09-01, weil die Frage beim Bau von `images/base-xfce` aufkam.

**Die Lizenz.** KasmVNC steht unter **GPL-2.0-or-later**. Nachgesehen nicht in
einem Blogeintrag, sondern in der Datei, die im Paket selbst liegt —
`/usr/share/doc/kasmvncserver/copyright` im gebauten Image sagt `License:
GPL-2+`, und `LICENSE.TXT` im Quell-Repository ist der GPL-2-Text. Die
Urheberzeile führt Kasm Technologies neben AT&T, RealVNC, TightVNC, Sun,
TigerVNC und anderen: KasmVNC ist ein TigerVNC-Abkömmling und erbt dessen
Lizenz.

**Was das erlaubt.** Ein GPL-Programm in ein Image zu legen und zu starten,
ist genau der Fall, für den die GPL gemacht ist. Das Paket wird unverändert
aus dem offiziellen Release übernommen — kein Patch, kein Fork, kein Linken.
OTA spricht mit ihm über Netz und Prozessgrenze (siehe oben), und im Image
liegt es neben anderer Software, ohne sie anzustecken (*mere aggregation*,
GPL-2.0 §2 letzter Absatz).

**Was zu tun ist, wenn ein Image das Haus verlässt.** Dann — und nur dann —
greifen die Pflichten: Lizenztext und Hinweise bleiben drin (sie liegen
ohnehin unter `/usr/share/doc/kasmvncserver/`), und der Quellcode dieser
Fassung muss verfügbar sein. Für ein unverändertes Release-Paket genügt der
Verweis auf `https://github.com/kasmtech/KasmVNC/releases/tag/v<Fassung>` —
die Fassung steht im Dockerfile als `KASMVNC_VERSION`. Dazu die erzeugte
Stückliste (`scripts/sbom.sh`), die ohnehin jedes Paket im Image nennt.

**Der eigentliche Punkt: es ist sauberer als der bisherige Weg.** Bisher
leitet jeder Arbeitsplatz von einem `kasmweb/*`-Image ab. Dessen fertiges
Abbild ist gerade **nicht** MIT (siehe der nächste Abschnitt) — es ist ein
Bündel aus fremder Software unter „Other", und was darin unter welchen
Bedingungen steht, muss man Paket für Paket herausfinden. Ein eigenes Image
aus Ubuntu, XFCE und dem offiziellen KasmVNC-Paket besteht dagegen aus
Bestandteilen mit bekannten, einzeln nachlesbaren Lizenzen.

**Was nicht geht:** Kasms *Workspaces*-Plattform ist proprietär — Agent,
Manager, API, die Weboberfläche des Produkts. Davon kommt nichts in ein
OTA-Image, und der Name gehört ebenfalls Kasm: Ein Image von OTA heißt
`ota/base-xfce` und nicht „Kasm" irgendetwas.

### Kasm-Workspaces-Images — MIT nur für die Rezepte

Kasm schreibt in die **erste Zeile** seiner Lizenzdatei:

> *„This license applies only to the source code that is directly maintained
> in this git repository, it does not extend to dependencies from outside of
> this repository, to include other projects owned and/or maintained by Kasm
> Technologies."*

Die MIT-Lizenz deckt also die Dockerfiles und Baurezepte. Das **fertige
Image** ist damit nicht MIT: Ubuntu, XFCE, KasmVNC, Schriften, Werkzeuge und
Anwendungen behalten jeweils ihre eigenen Bedingungen.

GitHub führt die Repositorien folgerichtig nicht als „MIT", sondern als
*Other* — nachgeprüft am 2026-08-28.

### Microsoft Visual Studio Code — der praktisch heikelste Punkt

Die Lizenzbedingungen erlauben beliebig viele Kopien **einschließlich der
Bereitstellung im eigenen Unternehmensnetz**. Sie untersagen zugleich, die
Software zu teilen, zu veröffentlichen, zu vermieten oder als eigenständiges
Angebot für Dritte bereitzustellen.

Für OTA heißt das:

| | |
|---|---|
| Eigenes Unternehmensnetz, eigene Mitarbeitende | ✅ gedeckt |
| Veröffentlichtes Image mit VS Code | ❌ nicht gedeckt |
| Angebot für Dritte / gehostet als Dienst | ❌ nicht gedeckt |

Wer diese Grenze nicht braucht, nimmt **VSCodium** (MIT) — es ist im Golden
Image vorhanden und bezieht seine Erweiterungen aus Open VSX. OTA prüft nach
jedem Build nach, wohin die gefundenen Editoren zeigen, und warnt, wenn ein
Nicht-Microsoft-Editor auf Microsofts Marktplatz zeigt.

Mit Originalzitaten geprüft in [Handbuch, Kapitel 13](docs/wiki/13-lizenzen.md).

### Darf das Basisimage weitergegeben werden? — Ja, mit vier Pflichten

Gemeint ist `ota/base-desktop`: Debian 13 + XFCE + Selkies, **ohne KasmVNC und
ohne Anwendungen**. Es besteht ausschliesslich aus Bestandteilen mit
einzeln nachlesbaren Lizenzen, und keine davon verbietet die Weitergabe.

Wer es weitergibt, hat vier Dinge zu tun:

1. **Quellen für die GPL-Teile** anbieten oder auf sie verweisen — allen voran
   libx264, dazu XFCE und ein grosser Teil von Debian.
2. **Die Selkies-Patches mitliefern** (`images/base-desktop/patches/`) und auf
   das verwendete Release verweisen. MPL-2.0, siehe oben.
3. **Lizenztexte drinlassen.** Sie liegen ohnehin unter
   `/usr/share/doc/<paket>/copyright`; ein `rm -rf /usr/share/doc` im
   Dockerfile wäre bequem und wäre ein Lizenzverstoss.
4. **Eine Stückliste beilegen** (`scripts/sbom.sh`). Ein Image aus hunderten
   Paketen lässt sich nicht von Hand auflisten, und diese Datei versucht es
   auch nicht.

**Was nicht weitergegeben werden darf**, sind fertige Arbeitsplatz-Images mit
Microsoft Visual Studio Code oder Google Chrome darin. Beides ist proprietär
und für das eigene Unternehmensnetz lizenziert, nicht für die Verteilung.
Dieselben Arbeitsplätze mit **VSCodium** (MIT) und **Firefox** (MPL-2.0) sind
dagegen unbedenklich — die Rezepte dafür liegen bei.

Kein Bestandteil von OTA trägt „Kasm" im Namen, und `ota/base-desktop` enthält
keine Zeile davon. Das ist keine Lizenzfrage, sondern eine Markenfrage: Der
Name gehört jemand anderem, und eine Verbindung, die es nicht gibt, soll auch
nicht suggeriert werden.

### Eingebundene Registries

OTA kann fremde Kataloge einbinden ([Kapitel 9](docs/wiki/09-kasm-images-und-registries.md)).
**Dass ein Katalog ein Image listet, ist keine Aussage über dessen Lizenz.**
Die Prüfung bleibt bei dem, der es einbindet.

---

## Grenzen

Diese Datei ist **auf Ebene 3 notwendigerweise unvollständig**. Ein
Arbeitsplatz-Image enthält hunderte Pakete, und eine von Hand gepflegte Liste
kann damit nicht Schritt halten — sie wäre in dem Moment veraltet, in dem
jemand ein Paket nachinstalliert.

Wer ein Image **weitergibt**, sollte für genau dieses Image eine Stückliste
erzeugen (SPDX oder CycloneDX, etwa mit `syft` oder `docker sbom`) und sie
mitliefern. Das ist die einzige Form, die dem Gegenstand gerecht wird. OTA
erzeugt sie derzeit **nicht** — das steht offen in [roadmap.md](roadmap.md).

Für den Betrieb im eigenen Haus, für den OTA gebaut ist, stellt sich die
Frage nicht: Dort wird nichts weitergegeben.
