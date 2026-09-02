# 17 · Ablagen und Startskript

*Für Administratoren.* ✅ Gemeinsame Ablage, eigene Ablage, Gruppenlaufwerke, Skeleton-Profil,
Skript beim Sessionstart

Wege, um Dinge in die Arbeitsplätze der Nutzer zu bekommen, ohne dafür jedes Mal ein Image zu bauen.
Sie gehören zusammen: Die gemeinsame Ablage ist die Quelle, das Skeleton legt den Grundstand, das
Skript holt sich, was es braucht. Die **eigene Ablage** steht daneben und gehört nicht der
Verwaltung, sondern dem Nutzer — sie ist sein Weg, Dateien in seinen Container und wieder heraus zu
bekommen.

## Was wohin gehört

| | Wohin | Warum |
|---|---|---|
| Software | **Golden Image** ([Kapitel 7](07-golden-images.md)) | Einmal bauen statt bei jedem Start installieren |
| Dateien für alle | **Gemeinsame Ablage** | Austauschbar, ohne Image-Bau |
| Dateien eines Nutzers, hin und zurück | **Eigene Ablage** | Sein Weg in den Container und heraus |
| Dateien eines Teams | **Gruppenlaufwerk** | Dieselben Dateien für alle Mitglieder, beide Richtungen |
| Womit ein Home anfängt | **Skeleton** | Dateien, die einfach da sein sollen — im Browser sichtbar |
| Einrichtung im Home | **Startskript** | Für alles, was *ausgeführt* werden muss |
| Einmalige Umstellung im Home | **Einmal-Skript** | Für eine Änderung, die je Nutzer genau einmal nötig ist |
| Eigene Einstellungen | **Nichts davon** | Das persistente Home hält sie ohnehin |

Der letzte Punkt wird oft übersehen: **Was ein Nutzer in seinem Home ändert, bleibt.** Extensions,
Editorkonfiguration, SSH-Schlüssel, Projektordner — das liegt auf dem Host unter
`/srv/ota/profiles/<nutzer>/` und wird bei jedem Start eingehängt. Ein neues Golden Image ändert
daran nichts; das Home liegt *über* dem Image.

## Das Skeleton-Profil ✅

Im Workspace-Editor unter **Skeleton** liegt ein Verzeichnisbaum. Er kommt beim **ersten** Start in
das Zuhause eines Nutzers — solange es noch leer ist. Danach gehört das Zuhause ihm.

Damit fängt niemand mit einem nackten Desktop an: Editor-Einstellungen, ein Wurzelzertifikat, eine
Vorlagendatei, eine `.bashrc`. **Punktdateien sind ausdrücklich erlaubt** und der Normalfall — anders
als in der gemeinsamen Ablage, wo sie nichts zu suchen haben.

### „Durchsetzen"

Neben jedem Eintrag steht ein Schalter *durchsetzen*. Ist er an, kommt dieser Pfad bei **jedem**
Start und **überschreibt**, was der Nutzer geändert hat.

> **Das ist mit Bedacht die Ausnahme.** Ein Zuhause gehört dem Menschen, der darin arbeitet; ihm bei
> jedem Start Einstellungen zu überschreiben, muss man begründen können. Für eine
> Proxy-Konfiguration oder ein Wurzelzertifikat ist es richtig. Für ein Farbschema nicht.

Was durchgesetzt wird, steht als Warnung unter der Liste — mit den Pfaden, damit niemand raten muss.

Wird eine Datei gelöscht, verschwindet sie auch aus der Durchsetzungsliste. Ein Pfad, den es nicht
mehr gibt, wäre eine Einstellung, die nichts mehr tut, und beim nächsten Hinsehen eine Frage.

### Skeleton oder Startskript?

| | |
|---|---|
| **Skeleton** | Dateien, die einfach da sein sollen |
| **Startskript** | Alles, was *ausgeführt* werden muss — etwas holen, erzeugen, abfragen |

Wer die Wahl hat, nimmt das Skeleton: Eine Datei, die man im Browser sieht, ist leichter zu prüfen
als eine Zeile Shell.

Die Reihenfolge beim Start ist Skeleton → Verweis auf die Ablage → Startskript. Das Skript darf den
Grundstand also überschreiben; es ist das spezifischere Werkzeug.

Alles landet als `1000:1000` im Home — kopiert wird als root, und ohne diesen Schritt gehörte dem
Nutzer sein eigenes Zuhause nicht mehr.


## Die drei Ablagen ✅

Sie beantworten verschiedene Fragen. Wer sie verwechselt, legt Vertrauliches an den falschen Ort —
deshalb sind sie auch in der Oberfläche getrennt.

| | Gemeinsame Ablage | Eigene Ablage | Gruppenlaufwerk |
|---|---|---|---|
| Gehört | der Verwaltung | je einem Nutzer | je einer Gruppe |
| Sieht sie im Browser | wer Images oder Workspaces verwaltet | nur der Eigentümer | jedes Mitglied |
| Im Container | `/mnt/ota`, **nur lesbar** | `/mnt/austausch`, **beschreibbar** | `/mnt/gruppen/<name>`, **beschreibbar** |
| Im Home | `~/Gemeinsam` | `~/Austausch` | `~/Gruppen` |
| Wozu | Zertifikate, Pakete, Vorlagen für alle | Dateien hinein und wieder heraus | dieselben Dateien für ein Team |
| Abschaltbar | nein | ja, je Workspace | ja, je Workspace |

## Die gemeinsame Ablage ✅

**Verwaltung → Gemeinsame Ablage.**

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

Geschrieben und **gesehen** wird ausschliesslich über diese Oberfläche, und nur von wem, der Images
oder Workspaces verwalten darf. Bis zum 2026-08-28 durfte jeder Angemeldete den Inhalt lesen, mit
dem Argument, er sehe ihn ohnehin in seinem Container. Das Argument stimmt weiterhin — es taugt nur
nicht als Bauplan für die Oberfläche: Zwei Ablagen nebeneinander, von denen eine nur zum Zusehen da
ist, erklären sich nicht.

## Die eigene Ablage ✅

**Meine Ablage** — im Menü ganz oben, für jeden, auch für Administratoren.

Der schnelle Weg in den eigenen Container und wieder heraus. Was dort abgelegt wird, liegt eine
Sekunde später im Container; was der Nutzer im Container hineinlegt, findet er im Browser.

```
/mnt/austausch                  der Einhängepunkt, beschreibbar
~/Austausch                     ein Verweis darauf, im Home
```

**Jeder sieht nur seine eigene.** Es gibt keinen Weg, über den jemand eine fremde benennen könnte —
auch nicht als Administrator. Der Name kommt nie aus der Anfrage, sondern aus dem Anmeldecookie.
Das ist Absicht und keine Lücke: Wer an fremde Dateien muss, hat mit Sicherung und
Wiederherstellung einen Weg, der im Protokoll steht ([Kapitel 14](14-sicherung.md)). Ein stiller
Blick ins Zuhause eines Kollegen soll keiner sein.

Sie liegt neben dem Home und nicht darin — aus zwei Gründen: Der Browser und der Container sollen
denselben Ort sehen, und beim Sichern des Profils soll sie nicht ein zweites Mal auftauchen.

### Auch während der Arbeit

In der Kontrollleiste einer laufenden Session (Griff am rechten Rand) steht dieselbe Ablage: ziehen
und ablegen, herunterladen, löschen. Wer mitten in der Arbeit eine Datei braucht, muss nicht zurück
ins Dashboard.

Das Ziehen funktioniert dabei im **Fenster**, nicht im Bild der Session. Das ist keine Bequemlichkeit
weniger, sondern die Grenze des eingebetteten Streams: Ein Ziehvorgang aus dem Betriebssystem endet
dort, wo der ferne Desktop anfängt. Die Leiste liegt davor und fängt ihn auf.

### Abschalten je Workspace

Im Workspace-Editor unter **Ressourcen → Eigene Ablage**. Vorgabe ist **an**. Aus ergibt Sinn für
Arbeitsplätze, aus denen bewusst nichts herausgetragen werden soll; dann fehlt der Einhängepunkt
ganz, und ein Verweis aus einem früheren Start wird beim nächsten Start aufgeräumt.

Der Schalter wirkt beim **nächsten** Start der Session — ein laufender Container wird nicht
umgehängt.

## Gruppenlaufwerke ✅

**Meine Ablage** — oben stehen die Laufwerke der eigenen Gruppen zur Auswahl. Die Umschaltung
erscheint nur, wenn es überhaupt eine gibt; ein Wähler mit einem einzigen Eintrag ist kein Wähler.

```
/mnt/gruppen/<gruppenname>      der Einhängepunkt, beschreibbar
~/Gruppen                       ein Verweis auf das Elternverzeichnis
```

Ein Ordner je Gruppe, in der der Mensch ist, und nur diese. Wer in drei Gruppen ist, sieht drei
Ordner; wer in keiner ist, sieht `~/Gruppen` gar nicht — ein Verweis, der ins Leere zeigt, wird
beim nächsten Start aufgeräumt.

**Die Mitgliedschaft entscheidet, und sonst nichts.** Auch ein Administrator kommt nur an die
Laufwerke der Gruppen, in denen er selbst ist. Das ist Absicht: Wer Gruppen verwaltet, verwaltet
Zugehörigkeiten — das heisst nicht, dass er in die Dateien sehen soll. Wer wirklich hinein muss,
trägt sich in die Gruppe ein, und das steht im Protokoll.

### Wann ein Entzug wirkt

| | Wirkt |
|---|---|
| Im Browser | **sofort** — die nächste Anfrage wird abgewiesen |
| Im laufenden Container | beim **nächsten Sessionstart** |

Der Unterschied ist keine Nachlässigkeit. Einem laufenden Container einen Bind-Mount zu entziehen
ginge nur, indem man ihn beendet — jemanden mitten in der Arbeit hinauszuwerfen wäre schlimmer als
die Stunde bis zum nächsten Start. Dieselbe Regel gilt für die übrigen Rechte
(`auth-roadmap.md`).

### Auf der Platte

```
/srv/ota/groupfiles/<kennung>/        das Verzeichnis
/srv/ota/groupfiles/<gruppenname>     ein Verweis darauf, für Menschen
```

Benannt nach der **Kennung** der Gruppe, nicht nach ihrem Namen — aus demselben Grund wie bei den
Profilen: Ein Gruppenname lässt sich in der Verwaltung ändern, und ab diesem Moment zeigte der Pfad
woanders hin. Im Container trägt der Ordner trotzdem den Namen; wird die Gruppe umbenannt, heisst
er ab dem nächsten Start anders, und die Daten bleiben, wo sie sind.

Das Verzeichnis trägt das **setgid-Bit**. Ohne das könnte ein Container Dateien anlegen, die ein
anderer nicht mehr ändern kann — und genau das ist bei einem gemeinsamen Laufwerk der Normalfall,
nicht die Ausnahme.

Gesichert wird es mit `make backup` zusammen mit den übrigen Inhalten ([Kapitel 14](14-sicherung.md)).

### Abschalten je Workspace

Im Workspace-Editor unter **Ressourcen → Gruppenlaufwerke**. Vorgabe ist **an**. Aus ergibt Sinn
für Arbeitsplätze, die bewusst abgeschottet sein sollen.

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


## Einmal-Skripte ✅

**Workspace-Editor → Einmal.**

Der Fall, für den es sie gibt: Ein neues Golden Image bringt eine Anwendung in einer neuen Fassung
mit, und die braucht eine Änderung im Zuhause — eine umgezogene Einstellungsdatei, ein neuer Pfad.

* Das **Skeleton** hilft nicht: Es greift nur, solange das Zuhause leer ist, und das ist es längst
  nicht mehr.
* Das **Startskript** hilft, läuft dann aber bei jedem Start wieder — obwohl die Sache nach dem
  ersten Mal erledigt ist.

Ein Einmal-Skript läuft **je Nutzer genau einmal**, beim nächsten Start dieses Workspace.

```bash
#!/usr/bin/env bash
set -euo pipefail
# $OTA_SHARED = gemeinsame Ablage,  $OTA_FILES = eigene Ablage des Nutzers
mkdir -p "$HOME/.config/Code/User"
cp "$OTA_SHARED/vscode/settings.json" "$HOME/.config/Code/User/settings.json"
```

### Die Buchführung

Gebucht wird je **Nutzer und Skript**, nicht je Session: Wer drei Arbeitsplätze derselben Vorlage
nacheinander startet, bekommt es einmal. Ein **neues** Skript ist ein neuer Eintrag und läuft wieder
für alle — genau so ist es gemeint.

**Eine Änderung am Text lässt es nicht erneut laufen.** Das ist die unbequeme, aber ehrliche
Antwort: Ein Skript, das nach jeder Korrektur an einem Tippfehler bei allen erneut liefe, wäre keine
Einmal-Sache mehr, und niemand traute sich, es anzufassen. Wer den Lauf wirklich wiederholen will,
sagt das ausdrücklich — dafür gibt es **Nochmal**.

**Nochmal** führt nichts aus. Ein Einmal-Skript läuft im Container, und der läuft vielleicht gerade
gar nicht; der Knopf nimmt nur die Notiz „ist schon gelaufen" zurück. Nachgeholt wird es beim
nächsten Start jedes betroffenen Nutzers.

### Wenn es scheitert

Der Arbeitsplatz startet trotzdem — ihn wegen einer misslungenen Einrichtung zu verweigern wäre die
schlechtere Antwort.

Der Lauf wird **trotzdem als erledigt verbucht.** Sonst liefe ein kaputtes Skript bei jedem Start
jedes Nutzers erneut, und aus einem Fehler würde eine Dauerbelastung. Sichtbar bleibt er: Im
Editor stehen Rückgabewert, betroffene Nutzer und die letzten Zeilen der Ausgabe.

Eine Ausnahme davon: Kam der Lauf gar nicht erst zustande — der Container antwortete nicht —, wird
nichts gebucht. Dann war nicht das Skript das Problem, sondern der Weg dorthin, und der nächste
Start versucht es wieder.

### Was es nicht tun sollte

Dasselbe wie beim Startskript: **keine Installationen.** Die gehören ins Golden Image. Und nichts,
was root braucht — es läuft als Nutzer im Container, damit die Dateien ihm gehören und er sie
später noch ändern kann.
