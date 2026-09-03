<!-- Sprachen: Deutsch (hier) · English -->
**Deutsch** · [English](README.en.md)

<p align="center">
  <img src="Logo-Banner.svg" alt="OpenTerminalApps" width="620">
</p>

# OpenTerminalApps

Selbstgehostete Plattform, die jedem Nutzer **einen eigenen Linux-Arbeitsplatz im Browser** gibt.
Darin sind seine Werkzeuge installiert — VS Code, VSCodium, JetBrains, Firefox, ein Terminal —, und
jedes lässt sich einzeln formatfüllend streamen. Alle teilen sich **ein Zuhause**: dieselben
Projekte, denselben SSH-Schlüssel, dieselbe Zwischenablage.

Daneben lassen sich einzelne Anwendungen als Wegwerf-Container starten und vorhandene Kasm-Images
sowie ganze Registries einbinden — als Zusatz, nicht als Fundament.

> **Stand:** läuft und wird benutzt. 251 automatische Prüfungen, davon 76 in einem echten Browser.
> Was noch fehlt, steht offen in [roadmap.md](roadmap.md) — nichts davon ist beschönigt.

---

## Schnellstart

**Voraussetzungen** auf einem Linux-Host: `docker` mit dem Compose-Plugin (`docker compose version`
muss antworten), dazu `git`, `make` und `openssl`. Die Ports **8443** und **8081** müssen frei sein
— 443 bleibt bewusst unbelegt, damit ein bestehendes Kasm daneben weiterlaufen kann. Beide sind über
`OTA_HTTPS_PORT` und `OTA_HTTP_PORT` in `deploy/.env` änderbar.

```bash
git clone https://github.com/bmetallica/openterminalapps.git
cd openterminalapps

sudo make setup                  # .env mit Geheimnissen, Zertifikat, Verzeichnisse
sudo make up                     # Stack bauen und starten (beim ersten Mal einige Minuten)
sudo make admin NAME=deinname    # erstes Administratorkonto
```

`make setup` **erzeugt die Geheimnisse und trägt sie selbst ein** — nachträglich ist nichts von Hand
zu ergänzen. Ein zweiter Aufruf lässt vorhandene Werte unangetastet.

`sudo` braucht es, weil OTA Verzeichnisse unter `/srv/ota` anlegt und mit dem Docker-Socket spricht.
Wer in der Gruppe `docker` ist und `/srv/ota` selbst angelegt hat, kann es weglassen.

`make admin` legt **zwei** Konten an und druckt beide Passwörter — sie werden nur dieses eine Mal
gezeigt:

| Konto | Wo es liegt | Wofür |
|---|---|---|
| `<deinname>` | in Keycloak | der Alltagszugang; die Anmeldung verlangt sofort ein eigenes Passwort |
| `notfall` | lokal in OTA | der Ausweg, wenn Keycloak einmal nicht antwortet |

Das zweite ist keine Dreingabe: Ab dem Moment, in dem die Anmeldung über einen weiteren Dienst
läuft, braucht es einen Weg herein, der ohne ihn funktioniert. Er ist unter `/notfall` erreichbar,
und jede Anmeldung darüber steht im Protokoll.

```
https://<host>:8443/            # leitet zur zentralen Anmeldung weiter
https://<host>:8443/notfall     # der lokale Notzugang
```

**Einmalig das Wurzelzertifikat importieren**, dann warnt der Browser nicht mehr — auch nach jedem
späteren Zertifikatswechsel:

```bash
sudo cp deploy/certs/ota-ca.crt /usr/local/share/ca-certificates/ota-ca.crt   # Linux, systemweit
sudo update-ca-certificates
```

Im Browser: Einstellungen → Zertifikate → Zertifizierungsstellen → `deploy/certs/ota-ca.crt`
importieren, „Websites vertrauen" ankreuzen.

**Läuft es?**

```bash
make ps                          # alle Dienste sollten "healthy" sein
curl -k https://localhost:8443/healthz
```

Die Antwort nennt vier Dinge: `db`, `agent`, `keycloak` und den Gesamtzustand. Steht dort
`"keycloak":"nicht erreichbar"`, ist der Realm noch nicht eingerichtet oder der Dienst noch nicht
oben — nachholen mit:

```bash
sudo make identity               # Realm, Clients, Rollen; idempotent
```

`make up` tut das von selbst und wartet dafür, bis Keycloak antwortet (beim ersten Start rund eine
halbe Minute).

Wenn etwas klemmt: `make logs` und [Handbuch, Kapitel 12](docs/wiki/12-fehlersuche.md) — dort stehen
echte Fehler aus dem Betrieb mit Symptom, Ursache und Reparatur.

### Der erste Arbeitsplatz

Nach der Anmeldung: **Workspaces → Anlegen**, ein Image eintragen (etwa
`kasmweb/core-ubuntu-jammy:1.16.0`), der Gruppe `users` zuweisen, einschalten. Danach unter **Start**
starten und über **Software → Im Image nachsehen** die Anwendungen freigeben.
Ausführlich in [Handbuch, Kapitel 2](docs/wiki/02-erste-schritte.md).

## Was es kann

**Der Arbeitsplatz**
- Ein Container je Nutzer, jede Anwendung auf ihrem eigenen Bildschirm, gestartet erst bei Bedarf
- Jede Anwendung in einem eigenen Browsertab, mit eigener Adresse — und als Verknüpfung auf dem
  Desktop ablegbar (PWA)
- Der ferne Bildschirm **wächst mit dem Fenster**, kein schwarzer Rand, keine Skalierung
- Zwischenablage in beide Richtungen, auch zwischen zwei Anwendungen im selben Container
- Klassischer XFCE-Desktop als zusätzliche Ansicht

**Verwaltung**
- Ressourcen **je Nutzer und Workspace**: Nutzer A bekommt 2 Kerne, Nutzer B einen
- **Kontingent je Zuhause** und eine Untergrenze für den freien Plattenplatz — eine verständliche
  Ablehnung statt eines Containers, der mitten in der Arbeit beim Schreiben stehenbleibt
- **Sichtbarkeit je Anwendung und Gruppe**, für den Fall, dass eine Lizenz nicht für alle reicht
- **Zwei-Faktor je Gruppe erzwingbar**, wahlweise mit **Passkey** (Fingerabdruck, Gesicht,
  Sicherheitsschlüssel) oder Einmalkennwort — angeboten, nicht verlangt; `/healthz` und `/metrics`
  für die Überwachung
- Nutzer, Gruppen und Rechte; Administratoren sind in ihrem eigenen Container `root`
- **Zentrale Anmeldung über Keycloak**, mitgeliefert im Stack — oder ein vorhandenes anbinden. OTA
  ist dessen Verwalter: Konten, Gruppen und die **AD-Anbindung** richtet man in OTAs Oberfläche
  ein, die Keycloak-Konsole bleibt für den Alltag zu
- **Notzugang** unter `/notfall`: ein lokales Konto, das ohne Keycloak funktioniert. Ohne ihn wäre
  eine Anlage nach einer kaputten Anmeldekonfiguration nicht mehr zu betreten
- Ein Verzeichniseintrag kann **kein bestehendes Konto übernehmen** — auch nicht mit demselben Namen
- **Fremde Web-Anwendungen** im Katalog (Open WebUI, Grafana, …): OTA legt den OIDC-Zugang an und
  entscheidet, wer die Kachel sieht. Was jemand darin darf, entscheidet die Anwendung — OTA baut
  ihr Rechtemodell nicht nach
- Anmeldefrist einstellbar (30 min bis 48 h), rollend — wer arbeitet, wird nicht abgemeldet
- Oberfläche auf Deutsch und Englisch, **dunkel oder hell** (oder wie der Rechner) — beides
  umschaltbar auch vor der Anmeldung
- Das Handbuch liegt **im Programm**, gefiltert nach Rechten
- **Mein Konto** für jeden: Passwort selbst ändern, Zwei-Faktor mit Rückfallcodes einrichten

**Software in die Arbeitsplätze bringen**
- Pakete anklicken, Image bauen, Fassung aktivieren — mit Protokoll und Rückrollen
- **Pakete werden vorher geprüft**: kennt das Image den Namen, und taugt er überhaupt?
  (Ubuntus `firefox` ist nur ein Verweis auf ein Snap und im Container nutzlos)
- **Rezepte** für alles, was kein einfaches Paket ist — mit geführtem Bauer für eigene
- **Anwendungen im Image finden**: OTA liest die `.desktop`-Dateien und schlägt Name, Zeichen und
  Startbefehl vor. Niemand muss wissen, wo eine Binärdatei liegt
- **Das echte Symbol aus dem Paket** — den Fuchs, nicht einen Kreis. OTA sucht es dort, wo die
  Freedesktop-Spezifikation es hinlegt, rechnet es auf 128 Pixel herunter (VSCodium liefert 428 KB)
  und liefert es zwischenspeicherbar aus
- **Drei Ablagen**: die gemeinsame für Dateien, die in jeden Arbeitsplatz sollen (im Container nur
  lesbar), eine **eigene je Nutzer** unter `/mnt/austausch` — beschreibbar, der Weg hinein und
  wieder heraus —, und ein **Laufwerk je Gruppe** unter `/mnt/gruppen/<name>`: dieselben Dateien
  für ein Team. Alle drei auch in der Kontrollleiste einer laufenden Session, mit Ziehen und
  Ablegen. Über ein Gruppenlaufwerk entscheidet die Mitgliedschaft und sonst nichts — auch ein
  Administrator kommt nur an die Gruppen, in denen er selbst ist
- **Skeleton-Profil** je Workspace: womit ein Zuhause anfängt. Einzelne Pfade auf Wunsch bei jedem
  Start durchgesetzt — die Ausnahme, nicht die Regel. Dazu **je Anwendung ein eigener Teilbaum**,
  der erst kommt, wenn diese Anwendung zum ersten Mal startet: Wer nur das Terminal benutzt,
  braucht die Einstellungen der Entwicklungsumgebung nicht in seinem Zuhause
- **Session einfrieren**: im eigenen Arbeitsplatz einrichten, Vorschau ansehen, als neue Fassung
  übernehmen. Das Home bleibt draussen, Geheimnisse werden markiert, die sudo-Ausnahme entfernt
- **Skript beim Sessionstart** je Workspace, für alles, was ins Home gehört, aber nicht ins Image
- **Einmal-Skripte** je Workspace: laufen je Nutzer genau einmal — für eine Umstellung im Zuhause,
  die das Skeleton nicht mehr erreicht und die das Startskript sonst bei jedem Start wiederholte

**Betrieb**
- **Eigenes Basisimage** `ota/base-desktop`: Debian 13 + XFCE + **Selkies**, ohne Anwendung und
  **ohne fremde Streaming-Software** — H.264 über WebRTC statt rechteckiger Ausschnitte über RFB.
  Das Konto heisst `ota` und wohnt unter `/home/ota`; kein Bestandteil trägt „Kasm" im Namen.
  `scripts/build-desktop-image.sh --pruefen` misst 19 Punkte gegen den Vertrag mit dem Agent
- **Der ältere Weg bleibt** — `ota/base-xfce` (Ubuntu + KasmVNC) für Images von Kasm, die kein
  Selkies mitbringen. Umschaltbar je Arbeitsplatz unter **Streaming**;
  `scripts/build-base-image.sh --pruefen` prüft ihn weiterhin
- **Stückliste je Image** (`make sbom`) in SPDX und CycloneDX — gebraucht, sobald ein Image das
  Haus verlässt
- Eigene Registry im Stack; fehlt ein Image lokal, wird es beim Start von dort geholt
- Sicherung und Wiederherstellung von Profil, Container und Datenbank, manuell und nach Plan
- HTTPS ab Werk, eigene kleine CA, austauschbar oder hinter einem Reverse Proxy
- **Läuft neben einer bestehenden Kasm-Installation** auf demselben Host, ohne dort etwas
  umzustellen

## Wie es gebaut ist

```
Browser ──HTTPS──▶ Traefik ──┬──▶ web       Oberfläche (nginx)
                             ├──▶ api       REST, Anmeldung, Rechte, Sessions
                             └──▶ /s/<id>   Stream einer Session (forwardAuth)
                                     │
                    api ──HTTP──▶ agent ──▶ Docker-Socket
                                     │
                          Session-Container (Selkies)
                                     │
                          turn ◀─WebRTC─ Browser
```

**Nur `agent` fasst Docker an.** Die API verarbeitet Nutzereingaben und bekommt den Socket deshalb
nicht — dieselbe Trennung gilt für das Dateisystem des Hosts.

| Verzeichnis | Inhalt |
|---|---|
| `web/` | Oberfläche (React, TypeScript, handgeschriebenes CSS, keine UI-Bibliothek) |
| `api/` | REST-API, Anmeldung, Rechte, Sessions (FastAPI, PostgreSQL) |
| `agent/` | **Einziger** Dienst mit Docker-Zugriff; Container, Displays, Images, Ablage |
| `deploy/` | Compose-Stack, Traefik, Registry, Zertifikate |
| `extension/` | Firefox-Erweiterung für die Zwischenablage |
| `docs/wiki/` | Handbuch — wird im Programm als Hilfe ausgeliefert |
| `images/` | Eigene Basisimages: `base-desktop` (Debian + XFCE + Selkies, Vorgabe) und `base-xfce` (Ubuntu + KasmVNC) |
| `tests/`, `scripts/` | Prüfungen, Zertifikat, Migration aus Kasm, Stückliste |

## Dokumentation

- **[Handbuch](docs/wiki/README.md)** — Bedienung, Verwaltung, Betrieb, Fehlersuche (19 Kapitel)
- **[plan.md](plan.md)** — Architektur **und die Begründungen dahinter**, samt der Sackgassen
- **[docs/adr/](docs/adr/README.md)** — Entscheidungen, die teuer rückgängig zu machen sind, mit den
  Alternativen, die nicht getragen hätten
- **[roadmap.md](roadmap.md)** — Umsetzungsstand, ehrlich

Ein Hinweis zur Fehlersuche: [Kapitel 12](docs/wiki/12-fehlersuche.md) beschreibt echte Fehler aus
dem Betrieb mit Symptom, Ursache und Reparatur — darunter mehrere, die tagelang nach etwas anderem
aussahen, als sie waren.

## Prüfungen

```bash
make test
```

**251 Prüfungen in fünf Suiten**, jede stellt ihren Vorzustand selbst her:

| Suite | Prüft |
|---|---|
| `test-authz.sh` | Ein normaler Nutzer kann beweisbar nichts Administratives tun und an keinem fremden Bildschirm sitzen; dazu Container-Härtung, Kennzahlen, Kontingente und zweiter Faktor |
| `test-clipboard-bridge.sh` | Kopieren zwischen zwei Anwendungen im selben Arbeitsplatz: beide Richtungen, Umlaute, ein Bild, ein Megabyte, nach Pause, und abgeschaltet |
| `tests/e2e.mjs` | Die Oberfläche in einem echten Browser — bis zur Frage, ob der Stream wirklich verbindet |
| `test-ldap.sh` | Verzeichnis-Anmeldung gegen ein echtes OpenLDAP im Container — vor allem, dass ein lokales Konto unantastbar bleibt und ein Ausfall es nicht mitreisst |
| `test-backup.sh` | Sicherung und Wiederherstellung von Profil, Container und Datenbank |

Die Zugangsdaten der Prüfung stehen in `deploy/.env` als `OTA_TEST_ADMIN_PW`, nicht im Quelltext.

Ein voller Lauf dauert **rund eine halbe Stunde**: Er startet Container, friert ein Image ein und
misst im Browser nach. Jede Suite lässt sich einzeln starten (`bash scripts/test-authz.sh`).

## Lizenz

**Apache-2.0** (siehe [LICENSE](LICENSE)). Gewählt, weil OTA Infrastruktur ist: keine Auflagen für
den Betreiber, ausdrückliche Patentfreigabe, und dieselbe Wahl wie beim nächstverwandten offenen
Projekt (Apache Guacamole).

OTA **enthält** keine fremde Software: Abhängigkeiten werden beim Bauen geholt, Bestandteile zur
Laufzeit als Container-Images bezogen. **Sie behalten ihre eigenen Lizenzen und werden von OTA nicht
neu lizenziert** — aufgeschlüsselt in drei Ebenen in
[THIRD-PARTY-NOTICES.md](THIRD-PARTY-NOTICES.md), knapp in [NOTICE](NOTICE).

Ein Arbeitsplatz-**Image** ist ein zusammengesetztes Werk: OTA-Konfiguration, Selkies (MPL-2.0,
**von OTA verändert**), libx264 (GPL-2.0+), XFCE, hunderte Distributionspakete, die installierten
Anwendungen. Es ist **nicht** „Apache-2.0".

Das Basisimage **darf weitergegeben werden** — mit vier Pflichten: Quellen für die GPL-Teile
anbieten, die vier Selkies-Patches beilegen (MPL-2.0 wirkt dateiweise), Lizenztexte im Image
lassen und eine Stückliste mitliefern. Fertige Arbeitsplätze mit Microsoft VS Code oder Google
Chrome dagegen **nicht** — dieselben mit VSCodium und Firefox schon.

**Für die Anwendungen in einem Golden Image gilt deren eigene Lizenz.** Bei Microsoft VS Code ist
der Betrieb im eigenen Unternehmensnetz ausdrücklich erlaubt, die Weitergabe an Dritte nicht.
Mit Originalzitaten geprüft in [Handbuch, Kapitel 13](docs/wiki/13-lizenzen.md) — keine
Rechtsberatung, aber am Lizenztext und nicht aus dem Gedächtnis.

„Kasm" ist eine Marke von Kasm Technologies. OTA ist kein Kasm-Produkt und steht in keiner
Verbindung zu Kasm Technologies.
