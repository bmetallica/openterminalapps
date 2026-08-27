# OpenTerminalApps

Selbstgehostete Plattform, die jedem Nutzer **einen eigenen Linux-Arbeitsplatz im
Browser** gibt. Darin sind seine Werkzeuge installiert — VS Code, JetBrains,
VSCodium, opencode, ein Terminal —, und jedes lässt sich einzeln formatfüllend
streamen. Alle teilen sich **ein Zuhause**: dieselben Projekte, denselben
SSH-Schlüssel, dieselbe Zwischenablage.

Daneben lassen sich einzelne Anwendungen als Wegwerf-Container starten und
vorhandene Kasm-Images sowie ganze Registries einbinden — als Feature, nicht als
Fundament.

## Schnellstart

```bash
make setup                 # Zertifikat und .env
make up                    # Stack bauen und starten
make admin NAME=deinname   # ersten Administrator
```

Danach: `https://<host>:8443/`

Das Root-Zertifikat aus `deploy/certs/ota-ca.crt` einmalig importieren, dann
zeigt der Browser keine Warnung mehr — auch nach jedem Zertifikatswechsel.

## Was drin ist

| Verzeichnis | Inhalt |
|---|---|
| `web/` | Oberfläche (React, TypeScript, handgeschriebenes CSS) |
| `api/` | REST-API, Anmeldung, Rechte, Sessions (FastAPI, PostgreSQL) |
| `agent/` | **Einziger** Dienst mit Docker-Zugriff; startet Container und Displays |
| `deploy/` | Compose-Stack, Traefik, Zertifikate |
| `docs/wiki/` | Handbuch — wird im Admin-Bereich als Hilfe ausgeliefert |
| `tests/` | Oberflächentest mit echtem Browser |
| `scripts/` | Zertifikat, Autorisierungstests |

## Dokumentation

- **[Handbuch](docs/wiki/README.md)** — Bedienung, Verwaltung, Betrieb, Fehlersuche
- **[plan.md](plan.md)** — Architektur und die Begründungen dahinter
- **[roadmap.md](roadmap.md)** — Umsetzungsstand und was noch fehlt

## Tests

```bash
make test
```

**102 Prüfungen in vier Suiten**, alle stellen ihren Vorzustand selbst her:

| Suite | Prüft |
|---|---|
| `test-authz.sh` | Ein normaler Nutzer kann beweisbar nichts Administratives tun und keine fremde Session sehen |
| `test-clipboard-bridge.sh` | Kopieren zwischen zwei Apps im selben Arbeitsplatz, beide Richtungen, mit Umlauten |
| `tests/e2e.mjs` | Die Oberfläche in einem echten Browser — bis zur Frage, ob der Stream wirklich verbindet |
| `test-backup.sh` | Sicherung und Wiederherstellung von Profil, Container und Datenbank |

## Lizenzhinweis

Der Betrieb im eigenen Unternehmen ist gedeckt; die Grenze verläuft bei der
Weitergabe nach außen. Details in **[Handbuch, Kapitel 13](docs/wiki/13-lizenzen.md)**.
Enthält Container-Images des Kasm-Workspaces-Projekts (MIT) und KasmVNC (GPL-2.0).
„Kasm" ist eine Marke von Kasm Technologies; OTA ist kein Kasm-Produkt.
