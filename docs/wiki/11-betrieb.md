# 11 · Betrieb, Backup und Updates

## Dienste

| Container | Aufgabe | Status |
|---|---|---|
| `ota-traefik` | Ingress, TLS, Routing zu den Sessions | ✅ |
| `ota-web` | Oberfläche (statisch ausgeliefert) | ✅ |
| `ota-api` | REST-API, Anmeldung, Rechte, Geschäftslogik | ✅ |
| `ota-agent` | **Einziger** Dienst mit Docker-Zugriff; startet Container und Displays | ✅ |
| `ota-db` | PostgreSQL 16 | ✅ |
| `ota-worker` | Leerlauf- und Waisen-Aufräumer laufen derzeit in `ota-api` mit | ✅ teilweise |

### Warum der Agent getrennt ist

Der Docker-Socket ist gleichbedeutend mit Root auf dem Host. Die API verarbeitet Nutzereingaben und
bekommt ihn deshalb **nicht**. Nur der Agent spricht mit Docker, über eine schmale interne
Schnittstelle. Traefik erhält den Socket nur lesend.

## Netze

| Netz | Wer | Zweck |
|---|---|---|
| `ota_public` | Traefik, Web, API | von außen erreichbar |
| `ota_internal` | API, DB, Agent | kein Weg nach draußen |
| `ota_sessions` | Session-Container | erreicht `ota-db` **bewusst nicht** |

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

## Überwachung 🔨 M7

Jeder Dienst bringt `/healthz` mit. Vorgesehene Metriken: aktive Sessions, Startdauer, Fehlerquote,
Host-Auslastung. Prometheus-Format, Grafana optional.

Beobachtenswert:

| Wert | Warum |
|---|---|
| Freier Arbeitsspeicher | Der knappste Posten. Unter 15 % wird es eng |
| Startdauer der Sessions | Steigt sie, ist meist die Platte der Grund |
| Fehlgeschlagene Starts | Meist Kapazität oder ein fehlendes Image |
| Profilgrößen | Frühwarnung vor der Quote |

## Rückfall auf Kasm

Solange Kasm parallel installiert ist, ist der Rückweg kurz:

```bash
cd /opt/openterminalapps/deploy && docker compose down
sudo /opt/kasm/bin/start
```

Der Rollback-Plan gehört schriftlich festgehalten und **einmal geprobt**, bevor OTA auf Port 443
umzieht.
