# 25 · Root-Arbeitsplatz — root und Docker im Container ✅

*Für Administratoren. Seit dem 2026-10-06.*

Ein **Root-Arbeitsplatz** ist eine eigene Klasse von Arbeitsplatz, gedacht für Entwickler:

| | Standard | Root mit Docker |
|---|---|---|
| root im Container | nur Administratoren (`sudo`) | **jeder mit dem Recht**, `sudo` ohne Kennwort |
| Docker, `docker compose`, `buildx` | — | ✅ eigener `dockerd` im Arbeitsplatz |
| Beim Beenden | Container wird **gelöscht** | Container wird **angehalten** — alles darin bleibt |
| Was ausserhalb des Zuhauses installiert wird | weg beim nächsten Start | **bleibt**, bis „Neu aufsetzen" |
| Adresse im Browser | je Sitzung neu | **fest** — Verknüpfungen und Lesezeichen bleiben gültig |
| Laufzeit | `runc`, gehärtet (`cap_drop: ALL`) | **Sysbox** (`sysbox-runc`) |

Das Zuhause, die Ablagen und die Gruppenlaufwerke sind in beiden Klassen dieselben.

## Warum Sysbox — und was das sicherheitlich heisst

Docker in einem Container braucht unter Dockers normaler Laufzeit `--privileged`. Damit hätte der
Arbeitsplatz alle Rechte des Kernels, und wer darin root ist, wäre es mit wenig Aufwand auf dem
Wirt. Den Docker-Socket des Wirts einzuhängen wäre noch schlimmer: Jeder Nutzer wäre root auf dem
Wirt und sähe Keycloak, die Datenbank und die Arbeitsplätze der anderen.

**Sysbox** ist eine zusätzliche Laufzeit für Docker (Open Source, Apache-2.0, von Docker Inc.).
Jeder Sysbox-Container bekommt einen eigenen Benutzer-Namensraum: **root im Container ist auf dem
Wirt ein unprivilegierter Nutzer.** Gemessen am 2026-10-06:

```
uid_map:  0 → 296608 (65536)        root im Container = UID 296608 auf dem Wirt
```

Darin laufen `dockerd`, `docker compose` und `sudo`, ohne `--privileged`. Nur Vorlagen der Klasse
Root laufen mit Sysbox; alle anderen bleiben bei `runc` und unverändert gehärtet. Die Entscheidung
und die verworfenen Wege stehen in [ADR-007](../adr/007-root-und-docker-ueber-sysbox.md).

**Das Netz bleibt OTAs Netz.** Die inneren Container hängen hinter dem Arbeitsplatz (NAT darin)
und kommen deshalb nur über den Router der Arbeitsplätze nach draussen — mit demselben Netzprofil
wie der Arbeitsplatz selbst ([Kapitel 23](23-netz.md)). Gemessen: aus einem inneren Container
Internet ja, Firmennetz nein, Wirt nein.

## Einrichten

### 1 · Sysbox auf dem Wirt

Einmal je Wirt, als root:

```bash
sudo scripts/sysbox-einrichten.sh --pruefen          # nur prüfen
sudo scripts/sysbox-einrichten.sh --live-restore     # einrichten (empfohlen)
```

Das Skript lädt Sysbox 0.7.1, prüft die Prüfsumme und installiert es — **ohne einen Container
anzufassen**:

- Das Paket will normalerweise Docker neu starten, um zwei Netzwerkwerte in
  `/etc/docker/daemon.json` zu setzen, und verweigert die Einrichtung, solange auch nur ein
  Container existiert. Es **schlägt** dann `docker rm $(docker ps -a -q) -f` vor. **Diesen Befehl
  nie ausführen** — er löscht jeden Container des Wirts. Das Paket führt ihn selbst nicht aus.
- Das Skript trägt deshalb vorher die Werte ein, **die heute schon gelten**: die Adresse von
  `docker0` als `bip` und Dockers eingebaute Adressbereiche. Danach trägt das Paket nur noch die
  Laufzeit ein und lässt Docker die Konfiguration per `SIGHUP` neu lesen. Gemessen auf der
  Entwicklungsmaschine: vorher 45 laufende Container, danach 45.
- Eine vorhandene `daemon.json` wird gesichert (`daemon.json.vor-sysbox.<Zeit>`) und nur
  **ergänzt** — was dort steht, bleibt.
- `--live-restore` setzt zusätzlich `"live-restore": true`: Container laufen weiter, wenn Docker
  selbst neu startet, etwa bei einem Update des Docker-Pakets. Empfohlen, aber es ändert das
  Verhalten künftiger Docker-Updates — deshalb eine eigene Option.

Danach muss `docker info` die Laufzeit nennen:

```bash
docker info | grep -i runtimes          # … sysbox-runc
systemctl is-active sysbox              # active
```

> **Sysbox nicht unbeaufsichtigt aktualisieren.** Ein Update des Pakets startet die Sysbox-Dienste
> neu — und damit jeden laufenden Root-Arbeitsplatz. Ins Wartungsfenster damit. Weil das Paket aus
> einer einzelnen Datei kommt und nicht aus einer Paketquelle, aktualisiert `unattended-upgrades`
> es ohnehin nicht; wer sicher gehen will: `apt-mark hold sysbox-ce`.

Voraussetzungen: amd64, Kernel ab 5.12 (für ID-gemappte Mounts — sonst gehörten die Dateien im
Zuhause im Container `nobody`). Geprüft mit Docker 29.7, containerd 2.2, Kernel 6.12, Debian 13.

### 2 · Das Root-Image

```bash
make up                 # baut ota/base-desktop-root:1, sobald Sysbox da ist und es fehlt
make root-image         # von Hand neu bauen und unter Sysbox prüfen
```

`ota/base-desktop-root:1` ist das Desktop-Basisimage plus `docker-ce`, `containerd`,
`docker-buildx-plugin` und `docker-compose-plugin` aus Dockers eigener Paketquelle. Der Nutzer
`ota` ist in der Gruppe `docker` und hat `sudo` ohne Kennwort. Das Startskript startet `dockerd`
als root, danach den Desktop als UID 1000.

Golden Images für Root-Arbeitsplätze baut man darauf auf (Software, Rezepte — wie bei jedem anderen
Image, [Kapitel 7](07-golden-images.md)).

### 3 · Die Vorlage

**Workspaces → Workspace → Allgemein → Klasse: „Root mit Docker".**

- **Image:** `ota/base-desktop-root:1` oder ein darauf gebautes. Auf einem anderen Image gibt es
  root, aber kein Docker — der Editor sagt das.
- **Platzgrenze:** wie viel ein Root-Arbeitsplatz höchstens belegen darf, Container und
  Docker-Daten zusammen. Vorgabe 50 GB. Darüber startet er nicht mehr, bis aufgeräumt oder neu
  aufgesetzt ist (die Verwaltung kann ihn trotzdem starten, um darin aufzuräumen).
- **Ressourcen:** Innere Container teilen sich Kerne und Speicher des Arbeitsplatzes. Für
  Compose-Stacks mit Datenbanken eher 4 Kerne und 8 GB als 2 × 2.

Fehlt Sysbox auf dem Wirt, warnt der Editor, und ein Start wird mit einer Erklärung abgelehnt —
**nie** auf `runc` mit `--privileged` zurückgefallen.

### 4 · Das Recht

**Nutzer → Gruppe → Rechte: „Root-Arbeitsplatz nutzen"** (`arbeitsplatz.root`). Wer es nicht hat,
bekommt beim Start einer Root-Vorlage eine Erklärung statt eines Arbeitsplatzes. Administratoren
haben es immer. Es ist bewusst ein eigenes Recht und nicht an „Administrator" gebunden: Es ist ein
Werkzeug für Entwickler, kein Verwaltungsrecht.

## Für den Nutzer

- **Beenden heisst anhalten.** Das Quadrat in der Kachel hält den Arbeitsplatz an; er steht danach
  als „angehalten" im Dashboard. **Fortsetzen** startet genau diesen Container wieder — mit allen
  installierten Paketen, Einstellungen und Docker-Images, unter derselben Adresse. Gemessen: rund
  3 Sekunden zum Anhalten (sauber, Exit 0), 3 Sekunden zum Fortsetzen.
- **Neu aufsetzen** baut den Arbeitsplatz aus dem aktuellen Image neu — für ein neues Basisimage
  oder einen verbastelten Stand. Das Zuhause bleibt immer. Zwei Varianten:
  - *Docker-Images behalten* — die Images und Volumes im Arbeitsplatz bleiben.
  - *auch Docker-Daten löschen* — alles ausser dem Zuhause ist weg.

  Ein neues Basisimage kommt **nur** über „Neu aufsetzen" in einen bestehenden Root-Arbeitsplatz
  (Entscheidung des Betreibers, 2026-10-06).
- **Docker:** `docker`, `docker compose`, `docker buildx` ohne `sudo`. Ein veröffentlichter Port
  (`ports: ["8080:80"]`) ist im Browser des Arbeitsplatzes unter `http://localhost:8080` erreichbar.
  Von ausserhalb des Arbeitsplatzes über eine befristete Portfreigabe („+ NAT", [Kapitel 23](23-netz.md)).
- **Leerlauf:** Ein Root-Arbeitsplatz wird bei Leerlauf **angehalten**, nie gelöscht — gleich, was
  in der Vorlage unter „Was dann passiert" steht.

## Für die Verwaltung: Betrieb → Arbeitsplätze

Die Liste zeigt **alle** Arbeitsplätze — laufende beider Klassen und angehaltene
Root-Arbeitsplätze — mit Nutzer, Klasse, Zustand, zuletzt aktiv und dem belegten Platz
(Container + Docker-Daten, gegen die Grenze der Vorlage). Je Zeile:

| Knopf | Wirkung | Recht |
|---|---|---|
| **Terminal** | root-Shell im Browser, im laufenden Arbeitsplatz | `arbeitsplatz.terminal` |
| **Starten** | angehaltenen Root-Arbeitsplatz starten, ohne dass der Nutzer eine Sitzung öffnet | `sessions.view_all` |
| **Anhalten** | laufenden Root-Arbeitsplatz anhalten | `sessions.view_all` |
| **Terminal-Protokoll** / **CSV** | Protokoll der Terminal-Eingaben dieses Arbeitsplatzes herunterladen | `sessions.view_all` |
| **Löschen** (Root) / **Beenden** (Standard) | Container weg — bei Root samt Docker-Daten. Das Zuhause bleibt immer | `sessions.view_all` |

Automatisch gelöscht wird nichts, auch kein Root-Arbeitsplatz, der lange nicht benutzt wurde
(„zuletzt aktiv" zeigt es).

### Das Webterminal

- **Wo:** in **jedem laufenden Arbeitsplatz**, Standard wie Root. **Nie** in einen Dienst des
  Stacks (API, Datenbank, Keycloak, Agent, Router) — der Agent nimmt nur Container mit der
  Kennzeichnung einer Sitzung an. Gemessen: ein Versuch auf `ota-db` wird abgewiesen.
- **Als root.** Bei Root-Arbeitsplätzen root im Namensraum des Containers; bei
  Standard-Arbeitsplätzen root mit deren Härtung (`cap_drop: ALL`) — Nachsehen und Reparieren geht,
  `apt install` kann dort an fehlenden Rechten scheitern.
- **Recht:** „Per Webterminal als root in laufende Arbeitsplätze" (`arbeitsplatz.terminal`). Es ist
  mächtiger als das Aufschalten auf den Bildschirm: Wer es hat, liest jede Datei im Zuhause des
  Nutzers. Ein zweiter Faktor ist dafür **nicht** Pflicht (Entscheidung des Betreibers); wer ihn
  will, erzwingt ihn je Gruppe ([Kapitel 8](08-nutzer-und-gruppen.md)).
- **Kein Hinweis für den Nutzer**, dass ein Administrator verbunden ist — wie beim Aufschalten
  (Entscheidung des Betreibers).

### Das Terminal-Protokoll

- **Was:** je Arbeitsplatz jede Shell-Sitzung (wer, wann, von wo) und jede **Eingabezeile** mit
  Zeitstempel. **Keine Ausgaben** — die enthielten jede gelesene Datei des Nutzers.
  Rücktaste wird angewandt, Strg+C/Strg+D stehen als `^C`/`^D` da, Pfeiltasten fallen weg. Was die
  Shell daraus macht (Vervollständigung mit Tab, Verlauf mit Pfeil hoch), steht nicht darin.
- **Achtung:** Was getippt wird, steht im Protokoll — auch ein Kennwort auf der Kommandozeile
  (`mysql -pGeheim`). Das Terminal sagt das über dem Eingabefeld.
- **Wer es sieht:** jeder Administrator (`sessions.view_all`). Es ist **nur lesbar**: Es gibt keinen
  Weg, Einträge zu ändern oder zu löschen. Weg kommen sie ausschliesslich über die Frist der
  Verwaltungsklasse (`OTA_PROTOKOLL_VERWALTUNG_TAGE`, Vorgabe 365 Tage).
- **Überdauert den Arbeitsplatz:** Nach dem Löschen eines Arbeitsplatzes bleibt sein Protokoll.
- **Export:** Text oder CSV (`zeit_utc;verbindung;administrator;nutzer;vorlage;art;text`). Jeder
  Export steht selbst im Audit-Log.

## Speicher und Sicherung

| Was | Wo | Gesichert |
|---|---|---|
| Zuhause | `/srv/ota/profiles/<id>` (wie immer) | ✅ mit den Profilen |
| Was ausserhalb des Zuhauses installiert wurde | die Schicht des Containers | ✅ **immer**, auch angehalten, auch wenn der Sicherungsplan Container sonst nicht sichert |
| Docker-Images, -Container, -Volumes im Arbeitsplatz | Volume `ota-platz-docker-<kennung>` | ❌ — lassen sich neu bauen und holen |
| Anlagenwerte (TURN, Proxy, Tastatur) | `/srv/ota/runtime/plaetze/<kennung>/umgebung.sh` | — wird bei jedem Start neu geschrieben |

**Anlagenwerte von jetzt.** Ein angehaltener Arbeitsplatz wird nicht neu erzeugt, seine Umgebung
stammt vom ersten Start. Damit eine geänderte TURN-Adresse, ein neuer Proxy oder ein anderes
Tastaturlayout trotzdem ankommen, schreibt der Agent sie vor jedem Start in eine eingehängte Datei,
die das Startskript liest.

**Platz auf dem Wirt.** Docker-Images wachsen schnell. Die Liste unter Betrieb zeigt je
Arbeitsplatz, was er belegt; die Grenze der Vorlage verhindert, dass einer die Platte füllt.
Gemessen wird `docker ps --size` plus `docker system df` (eine Minute zwischengespeichert).

## Zwei Dinge, die beim Bauen anders kamen

- **DNS in inneren Containern.** Im Arbeitsplatz steht als Nameserver Dockers eingebauter Resolver
  `127.0.0.11`. Der innere `dockerd` kann eine Loopback-Adresse nicht an seine Container
  weitergeben und fiel still auf `8.8.8.8` zurück — den der Router sperrt (fremde Resolver sind zu,
  sonst wären Freigaben nach Namen wirkungslos). Ergebnis: `docker run alpine wget example.com` →
  „bad address". Seither bekommt `dockerd` den Router als DNS (`--dns 10.99.x.2`); die Adresse
  reicht der Agent als `OTA_ROUTER` hinein, weil die Standardroute erst nach dem Start entsteht.
- **Sauberes Anhalten.** Das Startskript des Basisimages wartet im Vordergrund auf ein
  `sleep 3600` und führt seinen TERM-Handler erst danach aus. Der erste Versuch endete deshalb nach
  der Wartezeit mit SIGKILL (Exit 137) — mitten in laufenden inneren Containern. Jetzt beendet das
  Startskript des Root-Images beim Anhalten alle Prozesse von UID 1000 und lässt `dockerd` seine
  Container geordnet herunterfahren: Exit 0 nach rund 3 Sekunden.

## Prüfen

```bash
./scripts/test-root-arbeitsplatz.sh        # 33 Prüfungen, auch Teil von make test
```

Sie legen eine Root-Vorlage an und gehen den ganzen Weg: Sysbox (UID-Abbildung), `sudo`, Rechte
im Zuhause, Docker und Compose, Netz der inneren Container, Anhalten (Exit 0) und Fortsetzen mit
erhaltenem Stand, Platzmessung, Anhalten/Starten durch die Verwaltung, Webterminal samt Protokoll
und CSV, die Abweisung eines Terminals in einen Dienst des Stacks, Neu aufsetzen, Löschen samt
Docker-Daten — und dass das Protokoll den Arbeitsplatz überdauert. Ohne Sysbox wird übersprungen
statt rot.

## Eine bestehende Anlage aktualisieren

```bash
cd /opt/openterminalapps
sudo make backup                                   # erst sichern
git pull
sudo make update                                   # Dienste bauen und starten
sudo scripts/sysbox-einrichten.sh --pruefen        # Voraussetzungen ansehen
sudo scripts/sysbox-einrichten.sh --live-restore   # Sysbox einrichten (kein Container wird angefasst)
sudo make up                                       # baut jetzt ota/base-desktop-root:1
./scripts/test-root-arbeitsplatz.sh                # optional: der ganze Weg, 33 Prüfungen
```

Danach: eine Vorlage der Klasse „Root mit Docker" anlegen und das Recht „Root-Arbeitsplatz nutzen"
an die Gruppe(n) vergeben, die es bekommen sollen. Das Terminal-Recht ist für Administratoren schon
da; für andere Gruppen eigens vergeben.

**Was das Update mit laufenden Arbeitsplätzen tut:** nichts Neues. Bestehende Vorlagen bleiben
Klasse Standard und verhalten sich wie bisher. Der Reiter „Sessions" unter Betrieb heisst jetzt
„Arbeitsplätze" und zeigt dieselben Sitzungen, dazu angehaltene Root-Arbeitsplätze.

## Wenn etwas nicht geht

| Bild | Ursache |
|---|---|
| Start: „Root-Arbeitsplätze brauchen Sysbox …" | Sysbox fehlt oder Docker kennt die Laufzeit nicht: `docker info \| grep -i runtimes` |
| Start: „Dafür braucht es das Recht „Root-Arbeitsplatz nutzen“" | Recht der Gruppe fehlt |
| Start: „… belegt X GB, erlaubt sind Y GB" | Platzgrenze: aufräumen (`docker system prune` im Arbeitsplatz), „Neu aufsetzen", oder Grenze der Vorlage anheben. Die Verwaltung kann ihn unter Betrieb trotzdem starten |
| Im Arbeitsplatz `docker: command not found` | Image ist nicht `ota/base-desktop-root:1` oder darauf gebaut |
| `docker run …` → „bad address" | Image älter als der 2026-10-06 (ohne `--dns`): `make root-image`, dann „Neu aufsetzen" |
| Fortsetzen: „Das Netz dieses Arbeitsplatzes gibt es nicht mehr" | Das Sitzungsnetz wurde von Hand gelöscht: „Neu aufsetzen" |
| `apt install sysbox-ce` verlangt `docker rm …` | Ohne das Skript installiert. **Nicht ausführen** — `scripts/sysbox-einrichten.sh` benutzen |
| Terminal schliesst sofort mit „Dafür fehlt das Recht" | Recht `arbeitsplatz.terminal` fehlt |
