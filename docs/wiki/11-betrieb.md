# 11 · Betrieb, Backup und Updates

## Dienste

| Container | Aufgabe | Status |
|---|---|---|
| `ota-traefik` | Ingress, TLS, Routing zu den Sessions | ✅ |
| `ota-web` | Oberfläche (statisch ausgeliefert) | ✅ |
| `ota-api` | REST-API, Anmeldung, Rechte, Geschäftslogik | ✅ |
| `ota-agent` | **Einziger** Dienst mit Docker-Zugriff; startet Container und Displays | ✅ |
| `ota-db` | PostgreSQL 16 | ✅ |
| `ota-firewall` | **Der Router aller Arbeitsplätze**: nftables, NAT, Namensdienst, Portfreigaben. Ohne ihn hat kein Arbeitsplatz Netz | ✅ |
| `ota-turn` | Vermittelt den Medienstrom für Golden Images mit Selkies 1.6.2 (WebRTC). Selkies 2.0 braucht ihn nicht | ✅ |
| `ota-repo`, `ota-repo-web` | Die eigene Paketquelle, mit `ota-selkies`; der Spiegel darin nur mit `OTA_REPO_SPIEGEL=1` ([Kapitel 26](26-paketquellen.md)) | ✅ |
| `ota-registry` | Eigene Registry für die gebauten Images | ✅ |
| `ota-keycloak` | Identitätsanbieter, mitgeliefert oder abgeschaltet | ✅ |
| `ota-worker` | Leerlauf- und Waisen-Aufräumer laufen derzeit in `ota-api` mit | ✅ teilweise |

**Was ein Neustart kostet**, nach Dienst getrennt:

| Neustart von | Wirkung auf laufende Arbeitsplätze |
|---|---|
| `ota-api`, `ota-web`, `ota-agent` | **keine.** Der Bildstrom geht direkt über Traefik zum Container |
| `ota-traefik` | Der Bildstrom hängt für ein paar Sekunden, dann verbindet sich der Betrachter neu |
| `ota-firewall` | Die Arbeitsplätze sind **kurz ohne Netz**. Der Abgleich zieht die Anbindung selbst nach (alle 30 s); wer währenddessen lädt, sieht einen Abbruch |
| `ota-db` | Die Oberfläche meldet Fehler; laufende Ströme merken nichts |

### Warum der Agent getrennt ist

Der Docker-Socket ist gleichbedeutend mit Root auf dem Host. Die API verarbeitet Nutzereingaben und
bekommt ihn deshalb **nicht**. Nur der Agent spricht mit Docker, über eine schmale interne
Schnittstelle. Traefik erhält den Socket nur lesend.

## Netze

| Netz | Wer | Zweck |
|---|---|---|
| `ota_public` | Traefik, Web, API, Keycloak, TURN | von aussen erreichbar |
| `ota_internal` | API, DB, Agent, Registry | `internal` — kein Weg nach draussen |
| `ota_uplink` | Der Router | sein **einziger** Weg nach draussen |
| `ota-n-<sitzung>` | je ein Arbeitsplatz + der Router | eines je Sitzung, `internal`, ohne Standardroute |

**Ein Sammelnetz für alle Sitzungen gibt es seit dem 2026-09-04 nicht mehr.** Es war der Grund,
aus dem sich Arbeitsplätze gegenseitig und den Agent erreichen konnten: Auf **derselben** Brücke
greift `iptables` gar nicht, solange `br_netfilter` nicht geladen ist — eine Regel dagegen hätte
also nichts genützt. Jede Sitzung bekommt jetzt ihr eigenes Netz, angelegt vom Agent, und alle
enden im Router. Aufbau und Bedienung: [Kapitel 23](23-netz.md), Begründung:
[`firewall.md`](../../firewall.md).

Die Sitzungsnetze sind `internal` und die Brücke des Wirts hat dort **keine Adresse**. Vom Host aus
ist ein Arbeitsplatz deshalb nicht anzupingen — das ist kein Fehler, sondern der Punkt. Wer
hineinsehen will:

```bash
docker exec -it ota-s-<id> bash
docker exec ota-firewall nft list table inet ota | less    # das ganze Regelwerk
```

## Alltag

```bash
cd /opt/openterminalapps/deploy

docker compose ps                  # Zustand
docker compose logs -f ota-api     # Logs
docker compose restart ota-api     # Neustart eines Dienstes
docker compose down                # Alles stoppen (Sessions laufen weiter!)
```

> Ein Neustart von API oder Oberfläche **unterbricht laufende Sessions nicht**. Traefik leitet direkt
> zu den Session-Containern; die Anwendung ist am Datenstrom nicht beteiligt. Das ist ein bewusster
> Vorteil des Aufbaus und macht Updates im laufenden Betrieb unkritisch.

## Protokolle ✅

Jeder Container behält **10 MB in drei Dateien**, dann wirft Docker die älteste weg. Einstellbar
über `OTA_LOG_MAX_SIZE` und `OTA_LOG_MAX_FILE` in `deploy/.env` — für die Dienste **und** für jeden
Arbeitsplatz.

```bash
docker compose logs -f ota-api          # mitlesen
docker inspect ota-traefik --format '{{.HostConfig.LogConfig.Config}}'
du -sh $(docker inspect ota-traefik --format '{{.LogPath}}')
```

**Ohne diese Grenze schreibt Docker, bis die Platte voll ist**, und das ist keine graue Theorie:
Auf dieser Anlage stand Traefiks Protokoll nach vier Tagen bei 23 MB, weil dort jede abgelehnte
Anfrage mit Absenderadresse landet — rund zwei Gigabyte im Jahr, für einen einzigen Dienst. Läuft
die Platte voll, steht alles gleichzeitig, und die Datenbank zuerst.

Ein Arbeitsplatz ist dabei der gesprächigste Container überhaupt: X-Server, Fenstermanager und
jede Anwendung schreiben nach stdout. Eine Anwendung in einer Absturzschleife füllte damit die
Platte des **Wirts** — und träfe alle Arbeitsplätze, nicht nur den eigenen.

> **Die Einstellung wirkt erst, wenn ein Container neu erzeugt wird** (`make update`), nicht beim
> blossen Neustart. Laufende Arbeitsplätze behalten ihre bis zum nächsten Start.

**Das ist zugleich die Aufbewahrungsfrist.** In den Protokollen stehen IP-Adressen; ohne Grenze
bewahrt eine Anlage sie ewig auf. Sie verschwinden jetzt, wenn die Datei überschrieben wird, und
nicht erst, wenn jemand aufräumt ([`dsgvo.md`](../../dsgvo.md), Abschnitt 4). Wer länger
zurückschauen will, schickt die Protokolle an einen Sammler — dafür ist dieser Treiber nicht
gedacht.

### Wo es steht: Betrieb → Protokoll ✅

**Betrieb** hat drei Reiter: *Sessions* (wer arbeitet gerade), *Protokoll* und *Sicherung*. Das
Protokoll zeigt die letzten 120 Vorgänge, neueste zuerst, in fünf Spalten:

| Spalte | Was darin steht |
|---|---|
| **Zeit** | Tag und Uhrzeit auf die Sekunde |
| **Wer** | Der Anmeldename des Handelnden — bei Vorgängen ohne Konto ein Strich |
| **Was** | Der Vorgang **im Klartext**, nicht als technischer Name |
| **Betrifft** | Woran, sofern sich das benennen lässt (Kennung des Objekts) |
| **Von wo** | Die Absenderadresse |

Fehlschläge stehen in der Warnfarbe — *Anmeldung fehlgeschlagen*, *Zweiter Faktor falsch*,
*Rückfallcode falsch*. Wer eine Häufung an einer Adresse sieht, sieht einen Versuch.

> **Der Klartext ist kein Beiwerk.** Bis zum 2026-09-05 hatten 23 von 78 vorkommenden Vorgängen
> eine lesbare Beschriftung; der Rest stand als roher Bezeichner da — darunter ausgerechnet
> `session.attached`, der Eintrag, den ein Betroffener oder ein Betriebsrat lesen können muss. Er
> heisst jetzt **„Auf fremden Bildschirm geschaltet"**. Wer einen neuen Vorgang protokolliert,
> trägt seinen Klartext in `web/src/screens/Monitor.tsx` ein — sonst steht er dort wieder als
> Endpunktname.

### Und das Protokoll in der Datenbank ✅

Das `audit_log` hat eine eigene Frist, und zwar zwei — weil darin zwei verschiedene Dinge stehen:

| Klasse | Frist | Einstellbar |
|---|---|---|
| **Verhalten** — Anmeldungen, Sitzungen, App-Starts | 90 Tage | `OTA_PROTOKOLL_VERHALTEN_TAGE` |
| **Verwaltung** — wer was geändert hat, und wer sich aufgeschaltet hat | 365 Tage | `OTA_PROTOKOLL_VERWALTUNG_TAGE` |

`0` heisst „nie löschen". Aufgeräumt wird einmal täglich, in Häppchen von 5.000 Zeilen — ein
`DELETE` über Hunderttausende hielte die Tabelle fest, und in die schreibt jede Anmeldung. Der
Vorgang steht selbst im Protokoll (`protokoll.aufgeraeumt`), sonst sähe eine Lücke in den Daten
später aus wie ein Ausfall.

Von Hand anstossen, ohne bis Mitternacht zu warten:

```bash
docker compose exec api python -c "
from ota.db import SessionLocal
from ota import audit
with SessionLocal() as db: print(audit.aufraeumen(db))"
```

> **`session.attached` gehört in die lange Klasse**, obwohl der Name mit `session.` anfängt. Die
> kurze Klasse ist deshalb eine ausdrückliche Liste in `api/ota/audit.py` und keine Regel über
> Präfixe. Wer eine neue, häufige Aktion einführt, trägt sie dort ein — was nicht in der Liste
> steht, wird im Zweifel behalten.

## Was unter „Einstellungen" steht ✅

Fünf Dinge gelten für die ganze Anlage und nicht für eine Sitzung: die **Sprache** für alle, die
nicht selbst umschalten, die **Anmeldefrist** und der **Platz** (beide unten in diesem Kapitel),
das **Verzeichnis** ([Kapitel 8](08-nutzer-und-gruppen.md)) und die **Marke** — Name, Farbe und
Zeichen der Anlage, [Kapitel 22](22-marke.md). Alles davon braucht das Recht `settings.manage`.

## Sprache ✅

**Verwaltung → Einstellungen → Sprache → Standardsprache.**

OTA spricht Deutsch und Englisch. Jeder schaltet mit dem kleinen Umschalter **DE | EN** oben rechts
um; die Wahl gilt in diesem Browser und wird am Konto gemerkt, damit sie an einem anderen Rechner
wieder gilt. Die **Standardsprache** gilt für alle, die nie gewählt haben:

- die Oberfläche, auch die Anmeldeseite von OTA selbst,
- die Anmeldeseite von Keycloak — OTA gibt die Sprache bei jeder Anmeldung mit (`ui_locales`) und
  setzt die Vorgabe des Realms für den Fall, dass Keycloak ohne OTA aufgerufen wird,
- das Handbuch: Kapitel kommen auf Englisch aus `docs/wiki/en/`, sonst aus `docs/wiki/`.

Meldungen des Servers stehen im Quelltext auf Deutsch und werden im Browser übersetzt, genau wie die
Oberfläche (`web/src/lib/i18n.en.ts`). Wer einen Text hinzufügt, prüft mit
`python3 scripts/i18n-pruefen.py`, dass er einen englischen Eintrag hat; `make test` läuft diese
Prüfung als Erstes.

## Anmeldefrist ✅

**Verwaltung → Einstellungen → Abmelden nach Untätigkeit.**

Wie lange jemand angemeldet bleibt, ohne etwas zu tun. Der Regler kennt acht Stufen zwischen
30 Minuten und 48 Stunden; ab Werk sind es acht Stunden — ein Arbeitstag, also einmal anmelden am
Morgen.

Die Frist misst **Untätigkeit**. Jede Anfrage der Oberfläche schiebt sie nach vorn, und die
Oberfläche fragt im 15-Sekunden-Takt nach dem Zustand der Sessions. Wer einen Tab offen hat und
darin arbeitet, wird also nicht abgemeldet.

Die Änderung wirkt ab der nächsten Anmeldung und für jede Sitzung, die danach verlängert wird.
Bereits ausgestellte Zugänge behalten ihre alte Frist bis zur nächsten Verlängerung — wer die
Frist drastisch kürzt und sofortige Wirkung braucht, setzt zusätzlich die Sitzungen zurück
(Nutzer → Konto → Passwort ändern macht alle bestehenden Zugänge ungültig).

> Nicht zu verwechseln mit dem **automatischen Beenden von Sessions**. Das steht je Workspace unter
> *Ressourcen → Sitzung endet nach Inaktivität* und betrifft den Container, nicht die Anmeldung.

## Schema und Migrationen ✅

Beim Start der API laufen drei Schritte, und jeder deckt ab, was der vorige nicht kann:

1. **Migrationen** (`alembic upgrade head`). Auf einer leeren Datenbank baut das alles auf.
   Steht schon ein Schema da, ohne dass Alembic es kennt — etwa eine Anlage aus der Zeit davor —,
   wird es auf den Ausgangsstand **gestempelt** statt migriert; ein `CREATE TABLE` auf bestehende
   Tabellen würde nur scheitern.
2. **`create_all`** für Tabellen, zu denen es noch keine Migration gibt.
3. **Fehlende Spalten ergänzen** (`schema_sync.py`). `create_all` tut das nämlich nicht — und
   genau daran ist am 2026-08-27 eine laufende Anlage gescheitert.

Schritt 2 und 3 sind das Netz fürs Weiterbauen, **nicht der Ersatz für eine Migration**. Was sie
ergänzt haben, steht im Protokoll und gehört nachgetragen:

```bash
docker compose -f deploy/docker-compose.yml logs api | grep "Spalte ergänzt"
```

**Scheitert die Migration, startet der Dienst trotzdem.** Ein Dienst, der wegen eines
Migrationsproblems gar nicht erst hochkommt, lässt sich auch nicht mehr reparieren.

Eine neue Migration schreiben:

```bash
docker compose -f deploy/docker-compose.yml exec -w /app api \
  alembic revision --autogenerate -m "was sich ändert"
docker cp ota-api:/app/migrations/versions/. api/migrations/versions/
```

Der zweite Befehl ist nötig, weil das Verzeichnis im Abbild liegt und nicht eingehängt ist.

## Speicher: wer zuerst stirbt ✅

Alle Anwendungen eines Nutzers teilen sich **ein** Speicherlimit. Reisst eine davon es, sucht der
Kernel ein Opfer — und ohne Zutun trifft es gern den grössten Prozess. Das kann Xvnc sein; dann
stirbt der ganze Arbeitsplatz an einer einzigen Anwendung.

OTA setzt deshalb beim Start jeder Anwendung `oom_score_adj=500` auf sie und alle ihre
Kindprozesse. Die Infrastruktur im Container bleibt bei 0. Bei Speichernot trifft es damit eine
Anwendung, nicht den Arbeitsplatz.

Nachsehen lässt sich das so:

```bash
docker exec <container> bash -lc \
  'for p in $(pgrep -f code/code | head -3); do echo "$p $(cat /proc/$p/oom_score_adj)"; done'
```

> **Eine Ausnahme, die man kennen sollte:** Anwendungen, die ihre Arbeit an einen bereits laufenden
> Dienst übergeben statt selbst zu arbeiten — `xfce4-terminal` etwa reicht an seinen eigenen
> Hintergrunddienst weiter —, entkommen dem Wert. Bei den Speicherfressern (allem auf
> Electron- oder Chromium-Basis) greift er, und darauf kommt es an.

## Update

```bash
sudo make backup     # erst sichern
git pull
sudo make update     # .env ergänzen, bauen, starten
```

Migrationen laufen beim Start der API von selbst und nie destruktiv. Was `make update` im Einzelnen
tut und was es nicht anfasst, steht in der README unter *Aktualisieren*.

### Sicherheitslücken (CVEs) ✅

*Seit dem 2026-10-26.* `make update` bringt Sicherheitsupdates mit:

* **Fremde Dienste** (Postgres, Keycloak, Traefik, Registry …) zieht es neu — innerhalb
  der Versionsreihe, die `deploy/docker-compose.yml` nennt (`postgres:16-alpine` bleibt 16).
* **Eigene Images** (api, agent, web, firewall, repo, turn) baut es auf frischer Basis
  (`--pull`) und mit `apt-get upgrade` bzw. `apk upgrade`. Damit der Build-Cache diese Schicht
  nicht einfriert, hängt sie an der Kalenderwoche (`OTA_PAKETSTAND`): Sie wird spätestens
  wöchentlich neu gebaut.
* **Das Basisimage der Arbeitsplätze** baut `scripts/build-desktop-image.sh --pruefen` ebenso, das
  Root-Basisimage `make root-image`. Danach die Arbeitsplatz-Images unter **Software** neu bauen.

Was übrig bleibt, zeigt

```bash
make cve                              # Übersicht je Image
scripts/cve-pruefen.sh --liste        # jedes betroffene Paket mit behebender Fassung
```

Gescannt wird mit [grype](https://github.com/anchore/grype) als Wegwerf-Container, gezählt nur,
was sich beheben lässt. Seine Datenbank liegt unter `/srv/ota/runtime/grype`. Was nach einem
Update bleibt, steckt in fremden Programmen — etwa Go-Bibliotheken in `registry` oder in Dockers
`buildx` — und kommt mit deren nächster Fassung.

Die Python-Abhängigkeiten stehen fest in `api/requirements.txt`, `agent/requirements.txt`,
`firewall/requirements.txt` und — mit Prüfsumme — `third_party/selkies/ota-abhaengigkeiten.txt`.
Prüfen lassen sie sich ohne Stack:

```bash
docker run --rm -v "$PWD/api/requirements.txt:/r.txt:ro" python:3.13-slim \
  sh -c 'pip install -q pip-audit && pip-audit -r /r.txt'
```

### Das Banner während des Updates ✅

*Seit dem 2026-10-12.* Ab dem ersten Schritt von `make update` zeigt **jede OTA-Seite** oben ein
Banner — Dashboard, Anmeldung und jede Sitzung, auch im eigenen Tab:

> **Achtung!** OTA Update im Gange, bitte laden Sie alle OTA-Seiten neu, sobald diese Meldung
> verschwunden ist.

Es verschwindet erst, wenn die neue API gesund ist; wer dann neu lädt, bekommt die neue Fassung und
keine Fehlerseite. Während API und Weboberfläche neu starten, bleibt es stehen — keine Antwort ist
kein Grund, es auszublenden. Klicks gehen hindurch: Wer gerade arbeitet, kann weiterarbeiten.

* **So funktioniert es:** `scripts/wartung.sh an` setzt eine Marke in der Datenbank (`settings`,
  Schlüssel `wartung.update`) — die Datenbank läuft während des Updates durch, die API nicht.
  Jede Seite fragt alle 15 Sekunden `GET /api/wartung` (ohne Anmeldung, `no-store`).
  `scripts/wartung.sh aus` wartet, bis `ota-api` gesund ist, und nimmt die Marke weg.
* **Scheitert ein Update, bleibt das Banner stehen** — dann ist die Meldung wahr. Nach der Behebung
  nimmt es der nächste erfolgreiche `make update` weg, oder von Hand: `scripts/wartung.sh aus`
  (wartet auf die API) bzw. `scripts/wartung.sh aus --sofort`.
* Für eine Wartung ohne Update lässt es sich genauso von Hand setzen: `scripts/wartung.sh an`.

## Backup ✅

Sicherung und Wiederherstellung haben ein eigenes Kapitel:
**[Kapitel 14](14-sicherung.md)** — dort steht auch, wie die Ablage auf ein
NFS umzieht.

### Von Hand, ohne Oberfläche

Zwei Dinge sind zu sichern:

**Datenbank** — Nutzer, Gruppen, Workspaces, Zuweisungen, Audit-Log.

```bash
docker compose exec -T ota-db pg_dump -U ota ota | zstd > backup-$(date +%F).sql.zst
```

**Profile** — die eigentliche Arbeit der Nutzer, unter `/srv/ota/profiles/`.

```bash
tar --zstd -cf profiles-$(date +%F).tar.zst \
    --exclude='.cache' --exclude='core.*' --exclude='*.sock' \
    --exclude='*/Cache*' /srv/ota/profiles/
```

Caches auszuschließen spart erheblich Platz und Zeit — sie sind jederzeit neu erzeugbar.

Vorgesehene Aufbewahrung: sieben tägliche, vier wöchentliche Stände.

> **Ein Backup, dessen Wiederherstellung nie getestet wurde, ist kein Backup.**
> Die Wiederherstellung gehört mindestens einmal vollständig durchgespielt und dokumentiert. Sie ist
> Abnahmekriterium für M7.

Nicht gesichert werden müssen die Golden Images — sie sind aus dem Blueprint reproduzierbar. Ihre
**Definitionen** stecken in der Datenbank und sind damit vom DB-Backup erfasst.

## Speicherplatz

Profile wachsen. Vorgesehen ist eine Quote je Nutzer (Vorgabe 20 GB) mit Warnung ab 80 % und
Ablehnung neuer Sessions bei 100 % — mit einer verständlichen Meldung, nicht mit einem Fehler.

Alte Golden-Image-Versionen werden automatisch aufgeräumt (Vorgabe: die letzten drei behalten).

## Was einen Session-Container einsperrt ✅

Jeder Container, der nicht einem Administrator gehört, läuft mit:

| | |
|---|---|
| `no-new-privileges:true` | verhindert **jede** Rechteerhöhung, auch die über setuid. `sudo` läuft damit gar nicht erst an |
| `cap_drop: ALL` | keine einzige Linux-Fähigkeit. Insbesondere kein `SYS_ADMIN` |
| seccomp | der Standardfilter von Docker; er sperrt rund 40 Systemaufrufe, die ein Anwendungscontainer nicht braucht |
| `pids_limit: 4096` | eine Fork-Bombe legt den eigenen Container lahm, nicht den Host |
| `mem_limit`, `nano_cpus` | je Nutzer und Workspace einstellbar ([Kapitel 6](06-ressourcen-und-zuteilung.md)) |
| eigenes Netz | Ein `internal`-Netz **je Sitzung**, dessen einziger Ausgang der Router ist. Weder die Datenbank noch der Agent noch die Nachbarsitzung liegen darin ([Kapitel 23](23-netz.md)) |
| `shm_size: 1g` | grosszügig, weil Browser und Electron-Anwendungen sonst unvermittelt abstürzen |

Für Administratoren fallen die ersten beiden Zeilen weg — sonst liefe `sudo` nicht
([Kapitel 8](08-nutzer-und-gruppen.md)).

### Kein `SYS_ADMIN`, und was das kostet

Diese Fähigkeit stand bis zum 2026-08-27 für jeden Arbeitsplatz im Code, ohne Begründung. Sie
erlaubt Einhängungen und eigene Namespaces und ist damit praktisch gleichbedeutend mit Root auf dem
Host. Sie neben `no-new-privileges` zu setzen und gleichzeitig zu behaupten, ein
Nicht-Administrator komme nicht an Root, war ein Widerspruch. Sie ist weg.

Zwei Dinge verhalten sich seitdem anders — beide sind geprüft und beide sind der bessere Tausch:

**Firefox schreibt „CanCreateUserNamespace() clone() failure: EPERM" ins Protokoll** und startet
normal. Der Standard-seccomp-Filter von Docker lässt eigene User-Namespaces nur mit `SYS_ADMIN` zu,
und ohne sie fällt Firefox auf eine schwächere interne Sandbox zurück. Das ist zu verkraften: Diese
Sandbox schützt vor einer bösartigen Webseite, und die landet im schlimmsten Fall in genau dem
Container, in dem der Nutzer ohnehin ein Terminal hat. `SYS_ADMIN` dagegen ist ein Weg **aus** dem
Container heraus.

**AppImages hängen sich nicht mehr selbst per FUSE ein.** Deshalb legt das AppImage-Rezept jetzt
einen Starter mit `APPIMAGE_EXTRACT_AND_RUN=1` an: Das AppImage entpackt sich und startet daraus.
Kostet einen Moment beim Start und sonst nichts — und spart `libfuse2` im Image.

## Überwachung ✅

### Live-Auslastung: Betrieb → Arbeitsplätze ✅

Oben stehen zwei Balken für den **Host**: belegte Kerne mit Last und belegter Arbeitsspeicher. In
der Tabelle zeigt die Spalte **Live** je laufendem Arbeitsplatz:

| | |
|---|---|
| **CPU** | genutzte Kerne. Der Balken reicht bis zur Obergrenze, der Strich darin sind die zugeteilten Kerne, also das Gewicht ([Kapitel 5](05-workspaces-verwalten.md#ressourcen)) |
| **RAM** | belegter Speicher ohne Seitencache, gegen die Grenze des Containers |
| **Gebremst in X % der Zeit** | erscheint rot, wenn die CPU-Grenze den Container anhält. Das sieht man als Ruckeln, auch wenn der Host frei ist. Abhilfe: mehr Kerne zuteilen |
| **↓ ↑** und **Prozesse** | Netz in Byte pro Sekunde und Zahl der Prozesse |

Die Werte kommen alle 3 Sekunden, solange der Reiter offen und das Browserfenster sichtbar ist.
Gespeichert wird nichts. Unter 1050 Pixel Breite rollt die Tabelle seitwärts, die Seite selbst
nicht. Die Werte liefert `GET /api/admin/arbeitsplaetze/auslastung` (Recht `sessions.view_all`).

### `GET /healthz`

Beantwortet **eine** Frage: Kann die Anwendung gerade arbeiten? Ohne Anmeldung, damit ein
Lastverteiler oder ein Docker-Healthcheck sie stellen kann.

```json
{"status": "ok", "db": "ok", "agent": "ok"}
```

Fehlt die **Datenbank**, kommt `503` — ohne sie geht nichts. Fehlt der **Agent**, bleibt es bei
`200`: Anmelden und Nachsehen funktioniert weiter, nur starten lässt sich nichts. Das im Ergebnis zu
zeigen und trotzdem nicht als tot zu melden, ist der Unterschied zwischen einer Alarmierung und
einem Fehlalarm.

> Bis zum 2026-08-27 gab dieser Endpunkt fest `{"status":"ok"}` zurück, ohne irgendetwas zu prüfen.
> Ein Health-Check, der immer „ok" sagt, ist keiner.

### `GET /metrics`

Prometheus-Textformat. **Nicht offen** — zwei Wege herein:

| Weg | Wofür |
|---|---|
| `Authorization: Bearer <OTA_METRICS_TOKEN>` | ein Sammler. Das Merkmal steht in `deploy/.env`; ist es leer, gibt es diesen Weg nicht |
| angemeldet als Administrator (oder mit *Einstellungen ändern*) | ein Mensch, der einmal nachsieht |

Die Zahlen verraten für sich genommen wenig — aber sie verraten, wie viele Menschen hier arbeiten
und wann. Das gehört nicht ins offene Netz.

```
ota_sessions{status="running"}          Sessions je Zustand
ota_users, ota_users_active,
ota_users_totp                          Konten, davon anmeldefähig, davon mit zweitem Faktor
ota_templates, ota_templates_enabled    Workspaces
ota_registries                          eingetragene Kataloge
ota_builds{status="…"}                  Image-Builds je Zustand
ota_host_memory_bytes,
ota_host_memory_available_bytes,
ota_host_disk_free_bytes, ota_host_cores
ota_agent_up                            1 oder 0
```

Der Zustand des Hosts wird 15 Sekunden gepuffert. Ohne das wäre der Agent damit beschäftigt,
mehreren Sammlern immer wieder dasselbe zu antworten.

Beispiel für eine Alarmregel:

```yaml
- alert: OTAAgentWeg
  expr: ota_agent_up == 0
  for: 2m
- alert: OTAPlatteKnapp
  expr: ota_host_disk_free_bytes < 10e9
  for: 10m
- alert: OTABuildHaengt
  expr: ota_builds{status="building"} > 0
  for: 45m
```

Beobachtenswert:

| Wert | Warum |
|---|---|
| Freier Arbeitsspeicher | Der knappste Posten. Unter 15 % wird es eng |
| Freier Plattenplatz | Ein volles Dateisystem bringt laufende Arbeitsplätze zum Stehen |
| Fehlgeschlagene Builds | Meist ein Paketname, den das Image nicht kennt |
| `ota_agent_up` | Ohne Agent startet nichts, und die Oberfläche sagt es erst beim Versuch |

## Platz: Kontingent und Untergrenze ✅

Unter **Verwaltung → Einstellungen → Platz** stehen zwei Zahlen:

| | Standard | Wirkung |
|---|---|---|
| **Kontingent je Zuhause** | 20 GB | Wer darüber liegt, startet **keine neue Session** mehr |
| **Untergrenze freier Plattenplatz** | 5 GB | Fällt der Host darunter, startet **niemand** mehr eine Session |

**0 schaltet die jeweilige Grenze ab.**

Beides wirkt **beim Start einer Session, nicht beim Schreiben einer Datei**. Es ist kein
Dateisystem-Kontingent: Wer schon drin sitzt, kann weiter schreiben, und eine laufende Session wird
nicht abgeschnitten. Der Zweck ist eine verständliche Ablehnung statt eines Containers, der
irgendwann mitten in der Arbeit beim Schreiben stehenbleibt.

Gemessen wird mit `du` über das Profilverzeichnis, gezählt werden **belegte Blöcke** — die Frage
lautet ja, wie viel Platz auf der Platte weg ist. Der Wert wird im Agent **zehn Minuten** gepuffert;
ein Profil wächst zwischen zwei Starts nicht um Gigabytes. Wer in der Nutzerverwaltung nachsieht,
löst eine frische Messung aus.

**Ab 80 % steht ein Hinweis auf dem Dashboard**, ab 100 % steht dort, dass nichts mehr startet.
Der Wert wird nachgeladen und ist nicht Teil des ersten Seitenaufbaus — sonst wartete jeder beim
Anmelden auf eine Messung.

Die Meldung beim Start nennt Zahl und Ausweg:

> Dein Zuhause belegt 21,4 GB und damit die gesamten 20 GB, die dir zustehen. Räume auf —
> Downloads, Caches, alte Container-Abbilder — oder bitte deinen Administrator um mehr Platz.

In der **Nutzerverwaltung** steht der Verbrauch je Konto — dort frisch gemessen, weil jemand
ausdrücklich nachsieht.

**Gezählt wird der ganze Ordner des Kontos**, `/srv/ota/profiles/<kennung>/`: das gemeinsame
Zuhause `user/` und das eigene Zuhause jeder Vorlage und jedes Root-Arbeitsplatzes, auch von
gelöschten Arbeitsplätzen (das Zuhause bleibt beim Löschen immer). Im Container sieht der Nutzer
nur eines davon. Wer wissen will, wo der Platz liegt:

```bash
du -sh /srv/ota/profiles/<kennung>/* | sort -h
```

### Speicherabbilder räumt OTA selbst ✅

`dockerd` läuft mit `LimitCORE=infinity`, jeder Container erbte das, und der Wirt schreibt mit
`core_pattern = core` ein Abbild jedes abgestürzten Programms als `core.<pid>` ins aktuelle
Verzeichnis — fast immer das Zuhause. Gemessen am 2026-10-20: 24 Abbilder von
Firefox-Unterprozessen in einem Zuhause, die beim Anhalten jeder Sitzung sterben; auf einer
Anlage ein einzelnes von 4,3 GB. Niemand hat sie angelegt, und sie sperrten den Nutzer aus.

Seither:

- **Neue Container** starten mit `ulimit -c 0` — es entstehen keine Abbilder mehr. Ein bestehender
  Root-Arbeitsplatz behält seinen Container und damit die alte Grenze; ihn räumt der zweite Punkt.
- **Vor jeder Messung** (also vor jedem Start) entfernt der Agent die Abbilder im Ordner des
  Kontos, und **einmal am Tag** in allen Zuhausen. Das Protokoll der API nennt Anzahl und Größe.
- Gelöscht wird **nur, was nachweislich ein Abbild ist**: Name `core` oder `core.<Zahl>`, eine
  gewöhnliche Datei (kein Verweis), älter als fünf Minuten und im Kopf eine ELF-Datei vom Typ
  `ET_CORE`. Eine Datei des Nutzers, die zufällig `core` heisst, bleibt liegen.

Wer ein Abbild zur Fehlersuche braucht, holt es sich innerhalb der fünf Minuten oder schaltet es im
Root-Arbeitsplatz mit `ulimit -c unlimited` für diese Shell an — der tägliche Lauf räumt es danach
trotzdem.

## Softwaremonitoring ✅

Unter **Verwaltung → Softwaremonitoring** steht, welche Anwendung in welchem Arbeitsplatz welches
Nutzers installiert ist. Ziel ist, Wildwuchs zu bemerken, nicht ihn zu verhindern: Installiert
werden kann weiter, was die Rechte des Arbeitsplatzes erlauben.

**Einmal je Stunde** liest OTA jeden **laufenden** Arbeitsplatz, auf Knopfdruck auch sofort
(**Jetzt erfassen**). Erfasst werden Anwendungen, keine Versionen:

| Herkunft | Was |
|---|---|
| apt | Von Hand installierte Debian-Pakete, wie `apt-mark showmanual`. Was apt als automatisch mitinstalliert vermerkt hat, fällt weg. Ein per `dpkg -i` eingespieltes `.deb` zählt mit |
| Startmenü | Programme mit Starteintrag (`*.desktop`), systemweit und im Zuhause, etwa AppImages. Versteckte Einträge (`NoDisplay`) zählen nicht |
| Flatpak, Snap | Erkannt an den Starteinträgen, die beide anlegen |

Massgeblich ist nur der Name: Das Paket `gimp` und der Starteintrag `gimp.desktop` sind dieselbe
Anwendung.

**Gelesen, nicht ausgeführt.** Der Agent holt die Statusdateien von dpkg und apt über die
Docker-Schnittstelle (wie `docker cp`) und liest das Zuhause direkt auf dem Wirt. Im Container
läuft dafür kein Befehl. Ein `apt-mark` aufzurufen hiesse, einem Programm zu glauben, das in einem
Root-Arbeitsplatz der Nutzer selbst austauschen kann.

### Whitelist und Meldungen

- **Eine Whitelist für alle Arbeitsplätze.** Auch was das Image mitbringt, muss darauf stehen.
- **Aus dem aktuellen Stand befüllen** nimmt alles auf, was gerade irgendwo installiert ist.
  Das ist der Startpunkt. Ein Arbeitsplatz-Image bringt schnell einige hundert Pakete mit.
- Was nicht darauf steht, erscheint unter **Nicht auf der Whitelist**, mit Nutzer, Vorlage und
  Zeitpunkt. Administratoren sehen es zusätzlich auf ihrem **Dashboard**.
- Nach Rücksprache mit dem Nutzer gibt es zwei Wege:
  - **In die Whitelist** übernehmen.
  - Der Nutzer deinstalliert die Anwendung. Bei der nächsten Erfassung fehlt sie dann, und
    die Meldung verschwindet von selbst.
- Ein angehaltener Root-Arbeitsplatz wird nicht gelesen und behält seinen letzten Stand. Ein
  beendeter Arbeitsplatz verliert ihn, weil es seinen Container nicht mehr gibt.

Sehen darf das Softwaremonitoring, wer alle Sitzungen sehen darf. Die Whitelist ändert, wer die
Einstellungen ändert. Jede Änderung steht im Protokoll: `software.freigegeben`,
`software.entzogen` und `software.whitelist_befuellt`.

## Rückfall auf Kasm

Solange Kasm parallel installiert ist, ist der Rückweg kurz:

```bash
cd /opt/openterminalapps/deploy && docker compose down
sudo /opt/kasm/bin/start
```

Der Rollback-Plan gehört schriftlich festgehalten und **einmal geprobt**, bevor OTA auf Port 443
umzieht.
