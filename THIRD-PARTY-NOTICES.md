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
| **KasmVNC** | GPL-2.0 | Die Streaming-Engine |
| **Kasm-Workspaces-Images** | MIT **nur für die Baurezepte** | Siehe unten |
| XFCE | GPL-2.0 / LGPL-2.1 | Desktop |
| Ubuntu / Debian | Paketweise verschieden | Basis |
| **Microsoft Visual Studio Code** | Microsoft-EULA | Siehe unten |
| VSCodium | MIT | Erweiterungen über Open VSX |
| JetBrains Community | Apache-2.0 | Nur die Community-Ausgaben |
| Firefox | MPL-2.0 | |
| Google Chrome | Google-Nutzungsbedingungen | Proprietär |
| Sonstige Anwendungen | jeweils eigene | Was im Image installiert wurde |

### KasmVNC — GPL-2.0

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
