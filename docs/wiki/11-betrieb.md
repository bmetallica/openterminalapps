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
| `ota-turn` | Vermittelt den Medienstrom zwischen Browser und Arbeitsplatz (Selkies/WebRTC) | ✅ |
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

## Was unter „Einstellungen" steht ✅

Vier Dinge gelten für die ganze Anlage und nicht für eine Sitzung: die **Anmeldefrist** und der
**Platz** (beide unten in diesem Kapitel), das **Verzeichnis**
([Kapitel 8](08-nutzer-und-gruppen.md)) und die **Marke** — Name, Farbe und Zeichen der Anlage,
[Kapitel 22](22-marke.md). Alles davon braucht das Recht `settings.manage`.

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
git pull
cd web && npm install && npm run build && cd ../deploy
docker compose pull
docker compose up -d
docker compose exec ota-api alembic upgrade head    # läuft beim Start automatisch
```

Migrationen werden beim Start geprüft und nie automatisch destruktiv ausgeführt.

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

## Rückfall auf Kasm

Solange Kasm parallel installiert ist, ist der Rückweg kurz:

```bash
cd /opt/openterminalapps/deploy && docker compose down
sudo /opt/kasm/bin/start
```

Der Rollback-Plan gehört schriftlich festgehalten und **einmal geprobt**, bevor OTA auf Port 443
umzieht.
