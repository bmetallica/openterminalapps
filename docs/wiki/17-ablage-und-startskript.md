# 17 · Ablage und Startskript

*Für Administratoren.* ✅ Gemeinsame Ablage, Skript beim Sessionstart

Zwei Wege, um Dinge in die Arbeitsplätze der Nutzer zu bekommen, ohne dafür jedes Mal ein Image zu
bauen. Sie gehören zusammen: Die Ablage ist die Quelle, das Skript holt sich, was es braucht.

## Was wohin gehört

| | Wohin | Warum |
|---|---|---|
| Software | **Golden Image** ([Kapitel 7](07-golden-images.md)) | Einmal bauen statt bei jedem Start installieren |
| Dateien für alle | **Ablage** | Austauschbar, ohne Image-Bau |
| Einrichtung im Home | **Startskript** | Gilt je Nutzer, läuft in dessen Rechten |
| Eigene Einstellungen | **Nichts davon** | Das persistente Home hält sie ohnehin |

Der letzte Punkt wird oft übersehen: **Was ein Nutzer in seinem Home ändert, bleibt.** Extensions,
Editorkonfiguration, SSH-Schlüssel, Projektordner — das liegt auf dem Host unter
`/srv/ota/profiles/<nutzer>/` und wird bei jedem Start eingehängt. Ein neues Golden Image ändert
daran nichts; das Home liegt *über* dem Image.

## Die gemeinsame Ablage ✅

**Verwaltung → Ablage.**

Ein Ort für Dateien, die in jedem Arbeitsplatz gebraucht werden: ein Firmenzertifikat, ein
Installationspaket, eine Vorlagendatei.

In jedem Container liegt sie an zwei Stellen:

```
/mnt/ota                        der Einhängepunkt
~/Gemeinsam                     ein Verweis darauf, im Home
```

**Für Nutzer ist sie nur lesbar.** Das ist keine Einstellung, sondern der Einhängepunkt selbst
(`read_only`) — ein Schreibversuch scheitert im Dateisystem, nicht an einer Prüfung, die sich
umgehen liesse.

Der Verweis liegt im Home und nicht der Einhängepunkt selbst: Ein Verzeichnis, das man nicht
beschreiben kann, mitten in den eigenen Dateien verwirrt mehr, als es hilft. Wer schon einen eigenen
Ordner „Gemeinsam" hat, behält ihn — der Verweis wird dann nicht angelegt.

### Dateien ablegen

Ziehen und ablegen, oder **Dateien wählen**. Ordner lassen sich anlegen, Dateien herunterladen und
löschen. Höchstens 2 GB je Datei — die Ablage ist für Pakete und Zertifikate gedacht, nicht als
Datengrab.

> **Kein Ort für Vertrauliches.** Was hier liegt, sieht jeder Nutzer in jedem Arbeitsplatz. Ein
> privater Schlüssel gehört nicht hierher, ein öffentliches Zertifikat schon.

Geschrieben wird ausschliesslich über diese Oberfläche, und nur von wem, der Images oder Workspaces
verwalten darf. Sehen darf sie jeder Angemeldete — er hat sie ohnehin in seinem Container, sie im
Browser zu verbergen wäre Kulisse statt Sicherheit.

## Das Startskript ✅

**Workspace-Editor → Umgebung → Skript beim Start.**

Läuft bei jedem Sessionstart **als der Nutzer** im Container, bevor der Arbeitsplatz als bereit
gilt. Gedacht für alles, was ins Home gehört, aber nicht ins Image.

Als Nutzer und nicht als root, und das mit Absicht: Ein Skript, das mit root-Rechten in ein
Nutzerverzeichnis schreibt, hinterlässt Dateien, die der Nutzer nicht mehr ändern kann — ein Fehler,
der erst Wochen später auffällt.

Zwei Variablen stehen bereit:

| Variable | Inhalt |
|---|---|
| `$HOME` | `/home/kasm-user` |
| `$OTA_SHARED` | `/mnt/ota` — die gemeinsame Ablage |

### Beispiel: Firmenzertifikat verteilen

```bash
#!/usr/bin/env bash
set -e
mkdir -p "$HOME/.pki"
cp "$OTA_SHARED"/zertifikate/*.crt "$HOME/.pki/" 2>/dev/null || true
```

Das Zertifikat wird einmal in die Ablage geladen; jeder Start holt sich den aktuellen Stand.

### Was es nicht tun sollte

**Keine Installationen.** Die gehören ins Golden Image. Ein `apt-get install` im Startskript würde
bei jedem Start laufen, jeden Nutzer warten lassen und bei einem Ausfall der Paketquelle den
Arbeitsplatz blockieren.

**Nichts, was lange dauert.** Der Arbeitsplatz gilt erst danach als bereit.

### Wenn es scheitert

Der Arbeitsplatz startet trotzdem. Ihn wegen einer misslungenen Einrichtung ganz zu verweigern wäre
die schlechtere Antwort — die Anwendungen laufen ja.

Die Ausgabe steht im Container:

```bash
docker exec <container> cat /tmp/ota-start.log
```

und der Rückgabewert im Protokoll des Agents:

```bash
docker compose -f deploy/docker-compose.yml logs agent | grep Startskript
```
