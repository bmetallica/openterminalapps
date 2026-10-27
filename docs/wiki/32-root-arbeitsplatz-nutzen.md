# 32 · Mit einem Root-Arbeitsplatz arbeiten

*Für Anwender.* Ein Root-Arbeitsplatz ist ein eigener kleiner Linux-Rechner: Du darfst darin
`sudo`, Pakete installieren und Docker benutzen, und was du installierst, bleibt. Die Verwaltung
schaltet ihn je Workspace frei. Die Kachel trägt den Zusatz **root**.

## Was anders ist als beim Standard-Arbeitsplatz

| | Standard | Root |
|---|---|---|
| `sudo`, `apt install` | nein | ja |
| Docker, `docker compose` | nein | ja, ohne `sudo` |
| Installiertes ausserhalb des Zuhauses | weg, wenn der Container endet | bleibt, bis du neu aufsetzt |
| Beenden | Container weg, Zuhause bleibt | **anhalten**, alles bleibt |
| Platzgrenze | für das Zuhause | zusätzlich für den Arbeitsplatz selbst |

Root im Arbeitsplatz heisst nicht root auf dem Server: Der Arbeitsplatz läuft abgeschottet in einem
eigenen Benutzerbereich.

## Anhalten und Fortsetzen ✅

- Das **Quadrat** auf der Kachel hält den Arbeitsplatz an. Er steht danach als „angehalten" auf der
  Startseite.
- **Fortsetzen** startet genau diesen Arbeitsplatz wieder, mit allen Paketen, Einstellungen und
  Docker-Images. Beides dauert nur ein paar Sekunden; ein Balken zeigt, wie weit er ist.
- Bei **Leerlauf** wird ein Root-Arbeitsplatz immer nur angehalten, nie gelöscht.
- Stürzt der Desktop darin ab, steht er danach als angehalten da und lässt sich fortsetzen.

## Neu aufsetzen ✅

Für einen verbastelten Stand oder wenn du das neueste Image willst. **Dein Zuhause bleibt immer.**

| Variante | Was bleibt |
|---|---|
| **Neu aufsetzen, Docker-Images behalten** | Zuhause und die Docker-Images, Container und Volumes darin |
| **Neu aufsetzen, auch Docker-Daten löschen** | nur das Zuhause |

Alles, was du mit `apt` installiert oder unter `/etc`, `/opt` usw. geändert hast, ist danach weg.
Ein neues Basisimage kommt **nur** auf diesem Weg in deinen Arbeitsplatz.

## Docker ✅

`docker`, `docker compose` und `docker buildx` gehen ohne `sudo`. Ein veröffentlichter Port, etwa
`ports: ["8080:80"]`, ist im Browser **im Arbeitsplatz** unter `http://localhost:8080` erreichbar.
Von deinem eigenen Rechner aus geht das nur über eine befristete Portfreigabe der Verwaltung.

Nach dem Fortsetzen ist der Desktop da, bevor Docker fertig ist: Docker startet deine Container mit
`restart: always` erst noch. Ein `docker ps` in den ersten Sekunden wartet deshalb kurz.

## Platz

Images wachsen schnell. Überschreitet dein Arbeitsplatz seine Grenze, startet er nicht mehr, und du
bekommst die Meldung „Dieser Root-Arbeitsplatz belegt … GB, erlaubt sind … GB". Dann hilft:

```bash
docker system prune        # ungenutzte Images, Container, Netze
docker system df           # was wie viel belegt
```

Geht er gar nicht mehr an, setzt du ihn neu auf und lässt die Docker-Daten mitlöschen. Oder du
bittest die Verwaltung, die Grenze anzuheben. Die Verwaltung kann ihn auch trotz Grenze starten,
damit du darin aufräumst.

## Mehrere Root-Arbeitsplätze gleichzeitig

Teilen sich zwei Arbeitsplätze dasselbe Zuhause, läuft immer nur einer. Hat die Verwaltung den
Workspace unter Persistenz auf **Gemeinsame Daten** gestellt, laufen sie nebeneinander und
teilen sich deine Datenordner ([Kapitel 31](31-dateien.md#mehrere-arbeitsplätze-ein-zuhause)).

## Was die Verwaltung tut

- **Einmal-Skripte:** Die Verwaltung kann Skripte hinterlegen, die beim nächsten Start oder
  Fortsetzen einmal laufen, etwa um ein Zertifikat einzuspielen. Was ein Skript ausgegeben hat,
  steht in `/tmp/ota-einmal-<nummer>.log`.
- **Webterminal:** Administratoren können eine root-Shell in deinem laufenden Arbeitsplatz öffnen.
  Jede Eingabe darin wird protokolliert.
- **Anhalten, Starten, Löschen** unter Betrieb. Löschen entfernt den Arbeitsplatz samt Docker-Daten,
  dein Zuhause bleibt.

## Git und Selkies im Arbeitsplatz

Git richtet OTA bei jedem Start und Fortsetzen ein ([Kapitel 33](33-entwickeln.md)). Fehlt `git`
in einem älteren Arbeitsplatz, installierst du es einmal mit `sudo apt install git`. Die
Bildübertragung (Selkies) hebt OTA beim Fortsetzen von selbst auf die neueste Fassung.
