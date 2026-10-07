# 26 · Die eigene Paketquelle ✅

*Für Administratoren. Seit dem 2026-10-07. Ein Zusatz — ab Werk aus.*

OTA kann eine **eigene Paketquelle für Debian 13** mitbringen: einen Spiegel der offiziellen
Debian-Quellen und von Dockers Paketquelle, dazu **eigene `.deb`-Pakete** und **festgehaltene
Stände**. Arbeitsplätze und Bildbauer installieren dann von hier.

Zwei Gründe stehen dahinter:

- **Ausfallsicherheit.** Ist draussen etwas weg — ein Spiegel, eine Fassung, das Internet —,
  installieren die Arbeitsplätze weiter. Dass das keine Theorie ist, zeigte sich beim Bau dieses
  Kapitels: Die Release-Dateien von **Selkies 1.6.2**, auf denen OTAs Basisimage beruhte, lagen am
  2026-10-07 nicht mehr bei GitHub. Seither baut OTA Selkies 2.0 aus einem eigenen Fork, und dessen
  Abhängigkeiten liegen im [Datei-Vorrat](#der-datei-vorrat).
- **Eigene Pakete.** Ein selbst gebautes `.deb` hochladen, und jeder Arbeitsplatz installiert es
  mit `apt install` — ohne eigenen Server und ohne `curl | sh`.

## Was gespiegelt wird

| Quelle | Inhalt | Adresse in OTA |
|---|---|---|
| `deb.debian.org/debian trixie main` | das Debian-13-Archiv | `/repo/debian trixie` |
| `deb.debian.org/debian trixie-updates main` | Punkt-Updates | `/repo/debian trixie-updates` |
| `security.debian.org trixie-security main` | Sicherheitsupdates | `/repo/debian-security trixie-security` |
| `download.docker.com/linux/debian trixie stable` | Docker, Compose, Buildx — **nur die neueste Fassung** | `/repo/docker trixie` |
| eigene Pakete | was Administratoren hochladen | `/repo/ota ota` |

Nur `amd64`, keine Quellpakete. Bei Docker wird je Paket nur die neueste Fassung gespiegelt: Dort
liegen sonst rund 160 Fassungen mit zusammen 2,8 GB, und gebraucht wird eine.

Alles ist mit einem **eigenen Schlüssel** signiert, den OTA beim ersten Start erzeugt. Die
Signaturen von Debian und Docker werden **beim Abgleich geprüft** — was nicht stimmt, kommt nicht
in den Spiegel.

## Einschalten

In `deploy/.env`:

```bash
OTA_REPO=1
OTA_REPO_ROOT=/srv/ota/repo      # Spiegel, eigene Pakete, Schlüssel
OTA_REPO_FILTER=                 # leer = Vollspiegel
```

Danach `make update`. Es kommen zwei Dienste dazu: `ota-repo` (der Steuerdienst mit
[aptly](https://www.aptly.info/)) und `ota-repo-web` (liefert `/repo/` aus). Ohne `OTA_REPO=1`
startet keiner von beiden — `make` setzt dafür das Compose-Profil `repo`.

**Platz.** Ein Vollspiegel braucht grob **100 bis 130 GB**. Ein Abgleich räumt alte Fassungen
weg; was wächst, sind die festgehaltenen Stände, weil jeder seine Fassungen behält. Eine eigene
Platte oder ein NFS lässt sich unter `OTA_REPO_ROOT` einhängen.

**Zum Ausprobieren** reicht ein Filter. Dann werden nur diese Pakete samt Abhängigkeiten
gespiegelt — wenige MB statt 100 GB:

```bash
OTA_REPO_FILTER="Name (= hello) | Name (= jq) | Name (= curl)"
```

Die Anführungszeichen sind Pflicht: Die Skripte lesen `.env` ein, und eine Klammer ohne sie lässt
die Shell stolpern.

Danach unter **Verwaltung → Paketquellen** einmal **Jetzt abgleichen**. Der erste Vollabgleich
dauert je nach Leitung Stunden; das Protokoll läuft auf der Seite mit.

## Was in den Arbeitsplätzen passiert

Beim Start eines Arbeitsplatzes — und beim Fortsetzen eines angehaltenen Root-Arbeitsplatzes —
trägt der Agent die Quelle ein, **nur in Debian-13-Images**. Andere Images (Ubuntu, Kasm-Images,
Alpine) bleiben unberührt; im Protokoll des Agents steht dann `kein Debian 13 — nichts
eingetragen`.

Eingetragen wird:

| Datei | Inhalt |
|---|---|
| `/etc/apt/sources.list.d/00-ota-repo.sources` | die Quellen, mit `Signed-By` |
| `/etc/apt/keyrings/ota-repo.asc` | OTAs öffentlicher Schlüssel |
| `/etc/apt/ota-repo-ca.crt` + `/etc/apt/apt.conf.d/50ota-repo` | OTAs CA — **nur für apt** und nur für diese Adresse |
| `/etc/apt/preferences.d/ota-repo` | Vorrang (Betriebsart „Eigene zuerst") |

Die CA gilt nur für apt und nur für OTAs Adresse. Der Arbeitsplatz vertraut ihr sonst nicht.

### Die Betriebsart

Eine Einstellung für die ganze Anlage, unter **Paketquellen** ganz oben. Sie gilt ab dem nächsten
Start eines Arbeitsplatzes.

| Betriebsart | Was passiert |
|---|---|
| **Eigene zuerst** (Vorgabe) | Pakete kommen von hier. Was hier fehlt, kommt wie bisher aus dem Internet. |
| **Nur eigene** | Die Internetquellen im Arbeitsplatz werden abgeschaltet (`*.ota-aus`). Was hier fehlt, lässt sich nicht installieren. |
| **Aus** | Nichts wird eingetragen. Schon Eingetragenes wird beim nächsten Start entfernt. |

> **Wichtig zu „Eigene zuerst":** Der Vorrang ist ein *Vorrang*, kein Rückfall nur bei Fehlen.
> Gibt es ein Paket hier in einer älteren Fassung und draussen in einer neueren, nimmt apt
> **die von hier**. Ein Sicherheitsupdate kommt also erst in die Arbeitsplätze, wenn der Spiegel
> abgeglichen ist. Genau dafür steht das Alter des Spiegels oben auf der Seite und im Dashboard.

Warum `00-` im Dateinamen: Bei gleicher Fassung lädt apt aus der Quelle, die es zuerst liest. Mit
`ota-repo.sources` lag das eigene Paket bereit, und apt holte es trotzdem von `deb.debian.org`.

### Der Bildbauer

Der Bildbauer (Verwaltung → Software) trägt die Quelle **am Anfang des Baus ein und am Ende wieder
aus**. Das fertige Image trägt keine Spur davon — kein Schlüssel, keine CA, keine Quelle. Startet es
später als Arbeitsplatz, trägt der Agent ein, was dann gilt.

Unter **Snapshots → Bildbauer baut gegen** lässt sich ein festgehaltener Stand wählen. Dann baut der
Bildbauer gegen genau diese Fassungen, auch nach späteren Abgleichen: **reproduzierbare Images**.

## Abgleichen

**Nur von Hand**, mit **Jetzt abgleichen**. So entscheidet der Betrieb, wann sich in den
Arbeitsplätzen etwas ändert. Jeder Abgleich:

1. holt die Listen und Pakete und prüft die Signaturen von Debian und Docker,
2. hält das Ergebnis als Snapshot fest und liefert es aus (umschalten, nicht überschreiben — ein
   abgebrochener Abgleich lässt den alten Stand stehen),
3. räumt nicht mehr gebrauchte Fassungen weg.

Damit „von Hand" nicht „nie" wird, steht das **Alter des Spiegels** oben auf der Seite. Ab
**7 Tagen** ist es gelb, ab **30** rot; beides ist einstellbar. Administratoren sehen es ab gelb auch
im Dashboard.

## Eigene Pakete

Unter **Eigene Pakete** ein `.deb` hineinziehen oder wählen.

- **Nur Administratoren.** Ein Paket läuft bei der Installation als root in jedem Arbeitsplatz.
- **Geprüft wird**, dass es ein gültiges `.deb` ist (`dpkg-deb`) und für `amd64` oder `all`.
- **Dieselbe Fassung zweimal** wird abgewiesen. Eine neue Fassung braucht eine neue
  Versionsnummer — sonst hätten Arbeitsplätze unter derselben Version verschiedene Inhalte.
- Jeder Vorgang steht im **Audit-Log** (Betrieb → Protokoll), beim Hochladen mit Name, Fassung und
  Prüfsumme.

Im Arbeitsplatz dann einfach:

```bash
sudo apt update && sudo apt install mein-paket
```

## Snapshots

Ein Snapshot hält den Stand **aller Spiegel und der eigenen Pakete** fest, unter eigener Adresse
`/repo/snap/<name>/…`. Er bleibt, bis jemand ihn löscht.

| Aktion | Wirkung |
|---|---|
| **Festhalten** | Name aus Kleinbuchstaben, Ziffern, Bindestrichen, z. B. `2026-10-vor-update` |
| **Bildbauer baut gegen** | Images entstehen aus genau diesem Stand (siehe oben) |
| **Zurückdrehen** | Die Spiegel liefern wieder diesen Stand aus — etwa wenn ein Update etwas zerbrochen hat. Eigene Pakete bleiben, wie sie sind. Der nächste Abgleich schaltet wieder auf neu. |
| **Löschen** | Endgültig. Verweigert, solange der Bildbauer dagegen baut oder die Spiegel darauf zurückgedreht sind. |

## Der Datei-Vorrat

Manches, was OTA zum Aufsetzen braucht, steht in keiner Paketquelle. **Dateien holen** legt es unter
`/repo/dateien/` ab:

| Pfad | Was | Wer es nimmt |
|---|---|---|
| `selkies/2.0.0/raeder/` | die 33 Python-Pakete, die Selkies braucht — darunter `pixelflux` und `pcmflux` —, jedes gegen seine Prüfsumme geprüft | `scripts/build-desktop-image.sh` |
| `clipnotify/` | Quellen von clipnotify | `scripts/build-desktop-image.sh` |
| `sysbox/` | `sysbox-ce_0.7.1` (Prüfsumme geprüft) | `scripts/sysbox-einrichten.sh` |

**Selkies selbst** liegt nicht hier, sondern als Quellcode in OTAs Repository
(`third_party/selkies/`, [Kapitel 20](20-selkies-versuch.md#otas-fork)). Welche Pakete in den
Vorrat kommen, bestimmt dessen Liste `ota-abhaengigkeiten.txt` — mit Fassung und Prüfsumme; sie ist
in den Dienst eingehängt, und der Bau prüft gegen dieselben Werte.

Das Bauskript des Basisimages reicht den Vorrat als eigenen Baukontext hinein
(`--build-context ota-dateien=…`). Liegt dort alles, installiert der Bau Selkies und seine
Abhängigkeiten **ohne Internet** (`pip --no-index --require-hashes`). Fehlt der Vorrat, kommen sie
von PyPI, gegen dieselben Prüfsummen. Das Skript für Sysbox nimmt das Paket ebenfalls zuerst aus
dem Vorrat.

Unter `selkies/v1.6.2/` liegen auf der Entwicklungsanlage noch die beiden Dateien der alten
Fassung, die es bei GitHub nicht mehr gibt — als Archiv; gebraucht werden sie nicht mehr.

### Was ohne Internet geht — und was nicht

| | ohne Internet |
|---|---|
| `apt install` in Debian-13-Arbeitsplätzen | ✅ mit „Nur eigene" (Vollspiegel vorausgesetzt) |
| Docker-Pakete in Root-Arbeitsplätzen | ✅ |
| Bildbauer (apt-Pakete) | ✅ |
| Selkies (aus OTAs Repository), seine Abhängigkeiten, clipnotify im Basisimage | ✅ aus dem Vorrat |
| Sysbox einrichten | ✅ aus dem Vorrat |
| **apt im Bau des Basisimages selbst** | ❌ geht noch zu `deb.debian.org` (oder über den Firmenproxy) |
| VS-Code-Erweiterungen, `npm`, `pip` in Arbeitsplätzen | ❌ nicht Teil dieses Kapitels |

## Wer die Paketquelle erreicht

`/repo/` liegt unter OTAs HTTPS-Adresse und ist **ohne Anmeldung** lesbar — so wie apt es braucht.
Jeder, der OTAs HTTPS-Port erreicht, kann also die gespiegelten und die **eigenen Pakete**
herunterladen. Debian und Docker sind ohnehin öffentlich. Liegt in einem eigenen Paket etwas
Vertrauliches, gehört es nicht hierher, oder OTAs Port gehört hinter eine Firewall (siehe
[Kapitel 24](24-hinter-nat.md)).

Hochladen, Löschen, Abgleichen und alle Einstellungen gehen nur über die API und nur für
Administratoren.

## Netz und Firewall

Der Dienst `ota-repo` braucht für den Abgleich ausgehend HTTP/HTTPS zu:

- `deb.debian.org`, `security.debian.org`, `download.docker.com`
- für **Dateien holen** zusätzlich `github.com` mit seinen Download-Adressen
  (`*.githubusercontent.com`), `pypi.org` und `files.pythonhosted.org`

Ein Firmenproxy aus `OTA_HTTP_PROXY` / `OTA_HTTPS_PROXY` wird verwendet ([Kapitel 21](21-firmenproxy.md)).
Für die Arbeitsplätze ändert sich an den Netzregeln nichts: Sie erreichen die Paketquelle über
OTAs eigene Adresse, wie die Oberfläche.

## Sicherung

Unter `OTA_REPO_ROOT` liegen drei Dinge mit verschiedenem Wert:

| Verzeichnis | Wert |
|---|---|
| `gpg/` | **der Signierschlüssel.** Geht er verloren, vertraut kein Arbeitsplatz und kein Image einer neuen Quelle, bis der neue Schlüssel eingetragen ist (das passiert beim nächsten Start von selbst — aber gebaute Images mit altem Stand sind betroffen). **Sichern.** |
| `aptly/` | Spiegel und eigene Pakete. Der Spiegel kommt mit einem Abgleich wieder, die **eigenen Pakete nicht**. |
| `aptly/public/dateien/` | der Datei-Vorrat; lässt sich neu holen, solange PyPI und GitHub die Dateien führen |

OTAs eingebaute Sicherung (Kapitel 14) erfasst `OTA_REPO_ROOT` **nicht**. Am einfachsten:
`gpg/`, `meta.json`, `aptly/db`, `aptly/pool` und `aptly/public/dateien` mit der Sicherung des
Wirts mitnehmen.

## Ausschalten

`OTA_REPO=0` und `make update`. Die Arbeitsplätze tragen beim nächsten Start nichts mehr ein — **aber
was schon eingetragen ist, bleibt in laufenden Root-Arbeitsplätzen stehen**, bis sie fortgesetzt
werden. Wer sauber aussteigen will, stellt vorher die Betriebsart auf **Aus**, setzt die
Root-Arbeitsplätze einmal fort und schaltet dann ab. Die beiden Dienste laufen nach dem Ausschalten
weiter, bis sie gestoppt werden:

```bash
docker compose -f deploy/docker-compose.yml --profile repo stop repo repo-web
```

Das Verzeichnis `OTA_REPO_ROOT` bleibt stehen.

## Prüfen

```bash
scripts/test-repo.sh       # läuft auch in `make test` mit; ohne OTA_REPO=1 übersprungen
```

28 Prüfungen: Dienst und Signatur, Hochladen (doppelt 409, kaputt 422, präparierte Namen), Snapshots samt Schutz vor
dem Löschen, ein echter Debian-13-Arbeitsplatz installiert ein eigenes Paket **von hier**, „Nur
eigene" ruft `deb.debian.org` nicht mehr, der Bildbauer trägt ein und wieder aus, ein Ubuntu-Image
bleibt unberührt, und ein Root-Arbeitsplatz übernimmt beim Fortsetzen die aktuelle Einstellung.

## Fehlersuche

| Zeichen | Ursache | Abhilfe |
|---|---|---|
| Menüpunkt sagt „nicht eingeschaltet" | `OTA_REPO` nicht `1` | `.env`, dann `make update` |
| „Der Dienst der Paketquelle antwortet nicht" | `ota-repo` läuft nicht | `docker logs ota-repo` |
| Abgleich: `NO_PUBKEY` / Signatur | Schlüssel von Debian/Docker fehlt oder Spiegel manipuliert | Protokoll lesen; **nicht** mit `-ignore-signatures` umgehen |
| Abgleich hängt im Zeitablauf | kein Weg nach draussen | Proxy ([Kapitel 21](21-firmenproxy.md)), Firewall (oben) |
| Arbeitsplatz kennt die eigenen Pakete nicht | vor dem Einschalten oder vor dem Wechsel der Betriebsart gestartet | Arbeitsplatz neu starten (Root: anhalten, fortsetzen) |
| apt lädt trotz „Eigene zuerst" von `deb.debian.org` | das Paket fehlt hier (Filter?) | Filter prüfen, abgleichen |
| Eigenes Paket: „schon im Repository" | dieselbe Fassung gibt es | Versionsnummer erhöhen |
| `.env`: `Syntaxfehler beim unerwarteten Symbol „("` | Filter ohne Anführungszeichen | `OTA_REPO_FILTER="…"` |

## Technik in Kürze

- **Steuerdienst** `repo/otarepo/main.py` (FastAPI, Port 8200, nur im internen Netz). Spricht mit
  der API über denselben Dienst-Token wie der Agent. Kein Docker-Socket.
- **aptly 1.6.1** aus Debian 13: Spiegel → Snapshot → `publish switch`. Ein Auftrag zur Zeit.
- **nginx** (`ota-repo-web`) liefert `aptly/public` unter `/repo/` aus; `Release` und `Packages`
  ohne Zwischenspeicher.
- **Agent** `agent/otaagent/paketquelle.py` erzeugt das Ein- und Austragsskript; dieselbe Fassung
  für Arbeitsplätze und Bildbauer.
- **Einstellungen** in der Datenbank (`REPO_MODUS`, `REPO_BAU_SNAPSHOT`, `REPO_ALTER_GELB`,
  `REPO_ALTER_ROT`); alles andere in `OTA_REPO_ROOT/meta.json`.
