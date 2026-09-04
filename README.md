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

**Jeder Arbeitsplatz hängt in einem eigenen Netz** hinter einem Router: kein Firmennetz, keine
Nachbarsitzung, kein Wirt — bis jemand es ausdrücklich freigibt ([firewall.md](firewall.md)).

> **Stand:** läuft und wird benutzt. 439 automatische Prüfungen, davon 107 in einem echten Browser.
> Was noch fehlt, steht offen in [roadmap.md](roadmap.md) — nichts davon ist beschönigt.

---

## Schnellstart

**Voraussetzungen** auf einem Linux-Host: `docker` mit dem Compose-Plugin (`docker compose version`
muss antworten), dazu `git`, `make` und `openssl`. Die Ports **8443** und **8081** müssen frei sein
— 443 bleibt bewusst unbelegt, damit ein bestehendes Kasm daneben weiterlaufen kann. Beide sind über
`OTA_HTTPS_PORT` und `OTA_HTTP_PORT` in `deploy/.env` änderbar.

Dazu, sobald gestreamt wird: **3478** (TURN) und **49160–49260/UDP** für den Medienweg, sowie
**30000–30019** als Vorrat für Portfreigaben. Und ein Adressbereich für die Arbeitsplatznetze, ab
Werk `10.99.0.0/16` — er darf sich **nicht** mit dem Firmennetz überschneiden. Alles einstellbar,
alles erklärt in [`deploy/.env.example`](deploy/.env.example) und
[Kapitel 2](docs/wiki/02-erste-schritte.md).

```bash
git clone https://github.com/bmetallica/openterminalapps.git
cd openterminalapps

sudo make setup                  # .env mit Geheimnissen, Zertifikat, Verzeichnisse
sudo make up                     # Stack bauen und starten (beim ersten Mal einige Minuten)
sudo make admin NAME=deinname    # erstes Administratorkonto
```

**Hinter einem Firmenproxy** kommen drei Zeilen in `deploy/.env` dazu — `OTA_HTTP_PROXY`,
`OTA_HTTPS_PROXY` und vor allem `OTA_NO_PROXY`, damit die Dienste untereinander **nicht** über den
Proxy reden. Ohne Proxy ist nichts zu tun; das ist die Vorgabe.
[Handbuch, Kapitel 21](docs/wiki/21-firmenproxy.md) beschreibt auch, was OTA dabei *nicht* lösen
kann: `docker pull` macht der Docker-Daemon und braucht seine eigene Konfiguration.

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

## Aktualisieren

Eine neue Fassung aus dem Repository holen:

```bash
cd openterminalapps
sudo make backup          # erst sichern, dann ändern
git pull
sudo make update          # .env ergänzen, bauen, starten
```

`make update` macht drei Dinge in dieser Reihenfolge, und die Reihenfolge ist nicht beliebig:

1. **Fehlende Einstellungen ergänzen.** Bringt eine Fassung neue Werte in `deploy/.env.example`
   mit, trägt `make update` sie mit sinnvollen Vorgaben nach. **Vorhandene Werte bleiben
   unangetastet** — auch die Geheimnisse. Passierte das erst nach dem Bauen, startete ein Dienst
   gegen eine Variable, die es noch nicht gibt.
2. **Bauen und starten.** Die Datenbank wandert dabei von selbst mit: Alembic beim Start der API,
   und fehlende Spalten zieht OTA aus dem Modell nach. Es gibt keinen Migrationsschritt von Hand.
3. **Sagen, was *nicht* von selbst passiert.** Siehe unten.

### Was ein Update nicht anfasst

| | Warum, und was zu tun ist |
|---|---|
| **Laufende Sitzungen** | Sie behalten ihr Abbild, bis sie beendet werden. Das ist Absicht: Niemand soll mitten in der Arbeit unterbrochen werden. Wer die Neuerungen sofort will, beendet seinen Arbeitsplatz und startet ihn neu. |
| **Das Basisimage** | Wird nicht bei jedem Update neu gebaut — es dauert Minuten, und die meisten Fassungen fassen es nicht an. `make update` **prüft** aber, ob die Bauanleitung neuer ist als das gebaute Abbild, und sagt es dann. Bauen mit `scripts/build-desktop-image.sh --pruefen`. |
| **Die Arbeitsplatz-Images** | Ein neues Basisimage wirkt erst, wenn die davon abgeleiteten Images neu gebaut werden — in der Verwaltung unter **Software**. |
| **`deploy/.env`** | Wird nur ergänzt, nie überschrieben. Wer eine Einstellung ändern will, tut das selbst; die Vorlage daneben erklärt jede. |

### Später auf einen Firmenproxy umstellen

Derselbe Weg, im laufenden Betrieb und ohne Neuaufsetzen: die drei Zeilen in `deploy/.env`
eintragen, `sudo make update`. Dienste und **neue** Sitzungen übernehmen ihn sofort; laufende
behalten ihren Stand bis zum nächsten Start. Das Basisimage muss dafür **nicht** neu gebaut
werden — der Proxy steckt nie im Image. Zurückstellen ist derselbe Weg.

Gemessen in beide Richtungen; die Stolperstellen stehen in
[Kapitel 21](docs/wiki/21-firmenproxy.md).

### Wenn etwas schiefgeht

```bash
sudo make ps              # welcher Dienst steht nicht?
sudo make logs            # was sagt er?
```

Die Sicherung von oben spielt `scripts/restore-db.sh` zurück. Die **Profile der Nutzer** liegen
unter `/srv/ota/profiles` und werden von einem Update nicht angefasst — sie überstehen auch ein
vollständiges Neuaufsetzen des Stacks.

Ein Rückschritt auf die vorige Fassung ist `git checkout <alter-stand> && sudo make update`. Was
dabei **nicht** zurückwandert, ist die Datenbank: Neue Spalten bleiben stehen. Sie stören eine
ältere Fassung nicht, aber Daten, die es vorher nicht gab, sind dann eben da.

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
  ein, die Keycloak-Konsole bleibt für den Alltag zu — **erreichbar ist sie trotzdem**
  (`/auth/admin/`), und das mit Absicht: Wer sie zumauert, sperrt sich im Fehlerfall selbst aus.
  Was der Betrieb dafür schuldet, steht in [Kapitel 18](docs/wiki/18-zentrale-anmeldung.md)
- **Notzugang** unter `/notfall`: ein lokales Konto, das ohne Keycloak funktioniert. Ohne ihn wäre
  eine Anlage nach einer kaputten Anmeldekonfiguration nicht mehr zu betreten. Davor eine Bremse
  (zehn Versuche je Minute und Absender), und die Sperre nach Fehlversuchen gilt je **(Konto,
  Absender)** — sie lässt sich damit nicht gegen einen Kollegen richten
- Ein Verzeichniseintrag kann **kein bestehendes Konto übernehmen** — auch nicht mit demselben Namen
- **Fremde Web-Anwendungen** im Katalog (Open WebUI, Grafana, …): OTA legt den OIDC-Zugang an und
  entscheidet, wer die Kachel sieht. Was jemand darin darf, entscheidet die Anwendung — OTA baut
  ihr Rechtemodell nicht nach
- Anmeldefrist einstellbar (30 min bis 48 h), rollend — wer arbeitet, wird nicht abgemeldet
- Oberfläche auf Deutsch und Englisch, **dunkel oder hell** (oder wie der Rechner) — beides
  umschaltbar auch vor der Anmeldung
- Das Handbuch liegt **im Programm**, gefiltert nach Rechten
- **Mein Konto** für jeden: Passwort selbst ändern, Zwei-Faktor mit Rückfallcodes einrichten

**Das Netz der Arbeitsplätze**
- **Ein eigenes Netz je Arbeitsplatz**, alle enden in einem Router. Kein Firmennetz, keine
  Nachbarsitzung, kein Wirt — und das nicht, weil eine Regel es verbietet, sondern weil es keinen
  anderen Weg gibt: Die Netze sind `internal`, Docker richtet dort weder NAT noch Standardroute ein
- **Der Grundregelsatz steht sichtbar in der Oberfläche** — was OTA für sich selbst öffnet (TURN,
  die eigene Adresse, Namensdienst, Proxy, Zeitserver), je Zeile mit Ziel, Ports, **Grund und
  Herkunft**. Abgeleitet aus der `.env`, deshalb zu sehen und nicht zu ändern
- **Profile je Vorlage** in drei Stufen: *abgeschottet* (nur was OTA braucht), *internet* (die
  Vorgabe) und *aus* — letzteres hebt alles auf, verlangt eine Begründung und steht im Protokoll
- **Freigaben nach Adresse, Bereich oder Name**, global für alle oder je Profil. Namen funktionieren,
  weil der Router zugleich der Namensdienst ist: Was er beantwortet, trägt er selbst in die Regel
  ein — Freigabe und Verbindung stammen aus derselben Auskunft
- **„+ NAT"**: einen Port eines Arbeitsplatzes zeitlich begrenzt über den Wirt veröffentlichen, für
  den, der seine eigene Anwendung vorführen will. Der Ablauf wird durchgesetzt, nicht nur angezeigt
- **Feste Adressen** je Mensch und Vorlage — auch nach Feierabend und nach einem Neustart. Ohne das
  liesse sich eine vorgelagerte Firewall nicht auf einen Arbeitsplatz einstellen
- **Übersicht mit Durchsatz und verworfenen Paketen** je Arbeitsplatz. Ein Portscan sieht in dieser
  Zahl genau so aus, wie er ist

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
- **Firmenproxy** durchgängig: beim Bauen der Dienste, beim Bauen der Images, in jeder Sitzung und
  in API und Agent. Auch dort, wo keine Umgebungsvariable hinreicht — `apt` bekommt seine eigene
  Konfiguration. Umschaltbar im laufenden Betrieb, ohne Neuaufsetzen; ohne Proxy ist nichts zu tun
- **Stückliste je Image** (`make sbom`) in SPDX und CycloneDX — gebraucht, sobald ein Image das
  Haus verlässt
- Eigene Registry im Stack; fehlt ein Image lokal, wird es beim Start von dort geholt
- Sicherung und Wiederherstellung von Profil, Container und Datenbank, manuell und nach Plan
- HTTPS ab Werk, eigene kleine CA, austauschbar oder hinter einem Reverse Proxy
- **Kein Nachladen von fremden Hosts.** Schriften liegen bei, die Oberfläche fordert nichts aus
  dem Internet an — sie sieht offline und hinter einem Firmenproxy gleich aus, und die IP-Adresse
  keines Nutzers verlässt das Haus
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
| `firewall/` | Der Router aller Arbeitsplätze: nftables, NAT, Namensdienst, Portfreigaben |
| `extension/` | Firefox-Erweiterung für die Zwischenablage |
| `docs/wiki/` | Handbuch — wird im Programm als Hilfe ausgeliefert |
| `images/` | Eigene Basisimages: `base-desktop` (Debian + XFCE + Selkies, Vorgabe) und `base-xfce` (Ubuntu + KasmVNC) |
| `tests/`, `scripts/` | Prüfungen, Zertifikat, Migration aus Kasm, Stückliste |

## Dokumentation

- **[Handbuch](docs/wiki/README.md)** — Bedienung, Verwaltung, Betrieb, Fehlersuche (23 Kapitel)
- **[plan.md](plan.md)** — Architektur **und die Begründungen dahinter**, samt der Sackgassen
- **[docs/adr/](docs/adr/README.md)** — Entscheidungen, die teuer rückgängig zu machen sind, mit den
  Alternativen, die nicht getragen hätten
- **[roadmap.md](roadmap.md)** — Umsetzungsstand, ehrlich
- **[dsgvo.md](dsgvo.md)** — welche personenbezogenen Daten wo liegen, wie lange, wer sie sieht —
  und die vier Stellen, an denen heute etwas fehlt
- **[firewall.md](firewall.md)** — die Netzabsicherung der Arbeitsplätze: ein Netz je Sitzung, ein
  Router davor, Profile und Portfreigaben in der Oberfläche — samt der vier Dinge, die beim Bauen
  anders kamen als geplant

Ein Hinweis zur Fehlersuche: [Kapitel 12](docs/wiki/12-fehlersuche.md) beschreibt echte Fehler aus
dem Betrieb mit Symptom, Ursache und Reparatur — darunter mehrere, die tagelang nach etwas anderem
aussahen, als sie waren.

## Prüfungen

```bash
make test
```

**439 Prüfungen in sieben Suiten**, jede stellt ihren Vorzustand selbst her:

| Suite | Prüft |
|---|---|
| `test-authz.sh` | Ein normaler Nutzer kann beweisbar nichts Administratives tun und an keinem fremden Bildschirm sitzen; dazu Container-Härtung, Kennzahlen, Kontingente und zweiter Faktor |
| `test-clipboard-bridge.sh` | Kopieren zwischen zwei Anwendungen im selben Arbeitsplatz: beide Richtungen, Umlaute, ein Bild, ein Megabyte, nach Pause, und abgeschaltet |
| `tests/e2e.mjs` | Die Oberfläche in einem echten Browser — bis zur Frage, ob der Stream wirklich verbindet |
| `test-ldap.sh` | Verzeichnis-Anbindung **über Keycloak** gegen ein echtes OpenLDAP im Container — vor allem, dass ein Verzeichniseintrag kein lokales Konto übernimmt und ein Ausfall den Notzugang nicht mitreisst |
| `test-streaming.sh` | Der Medienweg: Vermittelt der TURN-Server wirklich, und kommt im Browser ein Bild an? Der Prüfbrowser läuft in einem Netz, aus dem der Session-Container **nicht** direkt erreichbar ist — wie ein Arbeitsplatz im Firmennetz |
| `test-firewall.sh` | Die Netzabsicherung, **von innen gemessen**: Nachbar, Wirt, Firmennetz, TURN, Namensdienst, Internet je Stufe, Freigabe nach Namen, Portfreigabe — und alles noch einmal nach einem Neustart des Routers |
| `test-backup.sh` | Sicherung und Wiederherstellung von Profil, Container und Datenbank. Beendet dafür Sitzungen — **nur die eigenen**, und prüft das ausdrücklich nach |

Die Zugangsdaten der Prüfung stehen in `deploy/.env` und nicht im Quelltext; die Reihen lesen sie
von dort selbst, ein `make` davor ist also nicht nötig.

Daneben steht `make messung` — **keine Prüfung, sondern eine Messung**: Sie vergleicht die beiden
Streaming-Wege unter derselben Last und sagt, was eine Sitzung an CPU, Bandbreite und Reaktionszeit
kostet. Sie dauert eine Viertelstunde und braucht eine ruhige Maschine, deshalb läuft sie nicht bei
`make test` mit. Ergebnisse und Auswertung: [Kapitel 20](docs/wiki/20-selkies-versuch.md#was-es-kostet--gemessen).

Ein voller Lauf dauert **rund eine halbe Stunde**: Er startet Container, friert ein Image ein und
misst im Browser nach. Jede Suite lässt sich einzeln starten (`bash scripts/test-authz.sh`).

Die Reihe für den Medienweg gibt es, weil die teuersten Fehler dieses Projekts genau dort lagen und
keine andere sie gefunden hätte: ein TURN-Server hinter einer Docker-Bridge, der die falsche
Absenderadresse verschickt; ein DTLS-Paket, das an einer kleinen MTU zerschellt. Beide sahen im
Browser gleich aus — „Waiting for stream" — und standen in keinem Protokoll.

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
anbieten, die fünf Selkies-Patches beilegen (MPL-2.0 wirkt dateiweise), Lizenztexte im Image
lassen und eine Stückliste mitliefern. Fertige Arbeitsplätze mit Microsoft VS Code oder Google
Chrome dagegen **nicht** — dieselben mit VSCodium und Firefox schon.

**Für die Anwendungen in einem Golden Image gilt deren eigene Lizenz.** Bei Microsoft VS Code ist
der Betrieb im eigenen Unternehmensnetz ausdrücklich erlaubt, die Weitergabe an Dritte nicht.
Mit Originalzitaten geprüft in [Handbuch, Kapitel 13](docs/wiki/13-lizenzen.md) — keine
Rechtsberatung, aber am Lizenztext und nicht aus dem Gedächtnis.

„Kasm" ist eine Marke von Kasm Technologies. OTA ist kein Kasm-Produkt und steht in keiner
Verbindung zu Kasm Technologies.
