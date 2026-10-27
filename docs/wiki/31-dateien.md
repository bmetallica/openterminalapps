# 31 · Dateien — was wo liegt und was bleibt

*Für Anwender.* Wie Dateien in deinen Arbeitsplatz kommen und wieder heraus, und was davon nach dem
Beenden noch da ist.

## Was wo liegt ✅

| Ort im Arbeitsplatz | Was es ist | Bleibt erhalten | Wer es sieht |
|---|---|---|---|
| `~` (dein Zuhause) | deine Projekte, Einstellungen, Schlüssel | ✅ immer | nur du |
| `~/Austausch` | **Meine Ablage**, auch im Browser erreichbar | ✅ | nur du |
| `~/Gruppen/<Gruppe>` | Laufwerk deiner Gruppe | ✅ | alle in der Gruppe |
| `~/Gemeinsam` | Dateien der Verwaltung für alle, **nur lesbar** | ✅ | alle |
| alles andere (`/opt`, `/usr`, `/etc` …) | das System des Arbeitsplatzes | ❌ beim Standard-Arbeitsplatz, ✅ beim Root-Arbeitsplatz | – |

Die drei Ordner im Zuhause sind Verweise. Dieselben Inhalte liegen unter `/mnt/austausch`,
`/mnt/gruppen` und `/mnt/ota`, falls du sie in einem Skript ansprichst. Fehlt einer davon, hat die
Verwaltung ihn für diesen Workspace abgeschaltet.

## Meine Ablage ✅

Der schnelle Weg in den Arbeitsplatz und wieder heraus.

- **Im Browser:** Seitenleiste → **Meine Ablage**. Dateien hineinziehen oder **Dateien wählen**,
  Ordner anlegen, herunterladen, löschen. Was du hier ablegst, liegt eine Sekunde später in
  `~/Austausch`.
- **Während der Arbeit:** Kontrollleiste der Session öffnen (Griff am rechten Rand). Dort steht
  dieselbe Ablage. Ziehe Dateien auf die Leiste, nicht auf das Bild der Anwendung: Der ferne
  Desktop nimmt Dateien vom eigenen Rechner nicht direkt an.
- **Heraus:** Datei im Arbeitsplatz nach `~/Austausch` legen, im Browser herunterladen.

Niemand sonst sieht deine Ablage, auch die Verwaltung nicht.

## Gruppenlaufwerke ✅

Für Dateien, an denen ein Team gemeinsam arbeitet. Unter **Meine Ablage** wählst du oben das
Laufwerk, im Arbeitsplatz liegt es unter `~/Gruppen/<Gruppe>`. Du siehst nur die Laufwerke der
Gruppen, in denen du bist.

Kommst du in eine neue Gruppe, erscheint ihr Laufwerk im Browser sofort, im Arbeitsplatz beim
**nächsten Start**.

## Die gemeinsame Ablage ✅

`~/Gemeinsam` enthält, was die Verwaltung für alle bereitstellt: Zertifikate, Installationspakete,
Vorlagen. Du kannst daraus lesen und kopieren, aber nichts hineinlegen.

## Was nach dem Beenden noch da ist

**Dein Zuhause bleibt immer**, auch wenn der Container gelöscht wird oder ein neues Image kommt.

**Beim Standard-Arbeitsplatz** geht alles ausserhalb des Zuhauses mit dem Container verloren:
Pakete, die du mit `apt` installiert hast, Änderungen an `/etc`. Brauchst du ein Programm dauerhaft,
sag der Verwaltung Bescheid. Es gehört dann ins Image.

**Beim Root-Arbeitsplatz** bleibt auch das System, bis du ihn neu aufsetzt
([Kapitel 32](32-root-arbeitsplatz-nutzen.md)).

## Mehrere Arbeitsplätze, ein Zuhause

Normalerweise teilen sich deine Arbeitsplätze ein Zuhause. Deshalb kann davon nur einer
gleichzeitig laufen; beim zweiten kommt die Meldung „… läuft schon und benutzt dasselbe Zuhause".

Hat die Verwaltung einen Workspace unter Persistenz auf **Gemeinsame Daten** gestellt, hat er
ein eigenes Zuhause für Einstellungen, teilt aber `Desktop`, `Documents`, `Downloads` und weitere
Ordner mit deinem normalen Zuhause. Solche Arbeitsplätze laufen nebeneinander.

## Vertrauliches

- Private Schlüssel und Passwörter gehören in dein Zuhause, nicht in ein Gruppenlaufwerk.
- Was in `~/Gemeinsam` liegt, sehen alle.
- Ob und wie oft dein Zuhause gesichert wird, legt die Verwaltung fest.
