# 34 · Bedienung: Bildschirm, Tastatur, Ton

*Für Anwender.* Was du in einer laufenden Session in der Hand hast.

## Die Kontrollleiste ✅

Damit die Anwendung den ganzen Platz bekommt, ist die Leiste eingeklappt. Du öffnest sie über den
**Griff am rechten Rand**. Darin:

| | |
|---|---|
| **Anwendungen** | zwischen den Anwendungen deines Arbeitsplatzes umschalten, oder zum ganzen **Desktop** |
| **Zwischenablage** | ein Textfeld für beide Richtungen, falls der Browser die Zwischenablage nicht freigibt ([Kapitel 4](04-zwischenablage.md)) |
| **Meine Ablage** | Dateien hinein und heraus, ohne die Session zu verlassen ([Kapitel 31](31-dateien.md)) |
| **Vollbild** | die Anwendung bildschirmfüllend. Zurück mit `Esc` |
| **Fokus setzen** | holt die Tastatur zurück in die Anwendung |
| **Neu verbinden** | baut die Bildübertragung neu auf. Die Anwendung läuft dabei weiter |
| **Zurück zum Dashboard** | zur Startseite, die Session läuft weiter |

**Strg + Alt + Shift** öffnet die Leiste auch, aber nur, solange die Tastatur **nicht** in der
Anwendung ist. Sobald du ins Bild geklickt hast, gehört die Tastatur dem fernen Desktop, damit du
dort jede Tastenkombination benutzen kannst. Der Griff geht immer.

## Bildschirm ✅

- **Die Grösse folgt deinem Fenster.** Ziehst du das Browserfenster grösser, wird der ferne
  Bildschirm grösser. Nichts wird gestreckt oder verkleinert, eine Auflösung musst du nicht
  einstellen.
- **Jede Anwendung in einem eigenen Tab.** Mehrere Anwendungen nebeneinander: einfach mehrere Tabs
  oder Fenster. Ein Lesezeichen auf einen Tab bringt dich zurück in dieselbe Anwendung.
- **Mehrere Monitore:** Ein Browserfenster je Monitor, jedes mit einer eigenen Anwendung.

## Tastatur ✅

- **Erst ins Bild klicken.** Ohne Fokus kommen Tastenanschläge nicht an. Nach einem Wechsel
  zwischen Tabs hilft notfalls **Fokus setzen**.
- **Umlaute und Sonderzeichen** kommen an, wenn das Tastaturlayout des Arbeitsplatzes zu deiner
  Tastatur passt. Die Verwaltung stellt es für alle ein, ab Werk deutsch. Fehlen Umlaute oder wird
  aus `/` ein `?`, sag ihr Bescheid.
- Ändere das Layout **nicht selbst** mit `setxkbmap` im Arbeitsplatz. Die Bildübertragung liest es
  nur beim Start, danach passt es nicht mehr zusammen.
- Tastenkürzel wie **Strg+W** oder **Strg+T** fängt der Browser ab, bevor sie die Anwendung
  erreichen, auch im Vollbild. `Esc` beendet im Vollbild zuerst das Vollbild.

## Ton

Was im Arbeitsplatz Ton ausgibt, hörst du im Browser. Ein **Mikrofon** gibt es nicht, auch die
Kamera nicht.

## Langsam oder ruckelig?

Die Bildübertragung rechnet auf dem Server und braucht Rechenzeit, genau wie deine Programme. Laufen
im Arbeitsplatz rechenintensive Dinge, etwa Tests, ein Build oder eine Indexierung in der IDE, kann
das Bild kurz ruckeln. Ruckelt es dauerhaft, sag der Verwaltung, in welchem Arbeitsplatz und wann.
Sie sieht unter Betrieb, ob dein Arbeitsplatz an seiner Grenze läuft
([Kapitel 35](35-wenn-etwas-nicht-geht.md)).
