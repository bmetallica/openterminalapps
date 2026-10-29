# 33 · Entwickeln: Git und KI im Editor

*Für Anwender.* Was OTA für Entwickler vorbereitet, wenn die Verwaltung es eingeschaltet hat. Ob
es bei dir an ist, siehst du an einer Kachel **Git** unter „Weitere Anwendungen" und am
KI-Assistenten in deinem Editor.

## Git (OTA-Git) ✅

OTA bringt einen eigenen Git-Server mit ([Forgejo](https://forgejo.org)).

**Im Browser:** Die Kachel **Git** öffnet ihn, angemeldet bist du mit deinem OTA-Konto. Dort legst
du Repositories an. Neue sind privat.

**Im Arbeitsplatz** ist Git fertig eingerichtet, bei jedem Start und jedem Fortsetzen:

```bash
git clone https://git.firma.de/dein-name/projekt.git    # ohne Passwortabfrage
git push
```

- Name und E-Mail für Commits kommen aus OTA. Was du selbst in `~/.gitconfig` setzt, gilt vorrangig.
- Der Zugang gilt **nur für diesen Arbeitsplatz** und endet mit ihm. Beim nächsten Start gibt es
  einen neuen. Du musst nichts davon aufbewahren.
- Andere Git-Server (GitHub, ein Firmenserver) gehen daneben wie gewohnt, mit deinen eigenen
  Zugangsdaten oder SSH-Schlüsseln.

**SSH statt HTTPS:** Deinen öffentlichen Schlüssel trägst du im Browser in Forgejo ein
(Einstellungen → SSH-Schlüssel). Danach geht `git clone ssh://git@git.firma.de:2222/…`, aber
**nur aus Arbeitsplätzen**. Von deinem eigenen Rechner aus nimmst du HTTPS.

Der genaue Name des Servers steht auf der Git-Kachel und in der Adresszeile, wenn du sie öffnest.

## Der KI-Assistent im Editor (IDE-AI) ✅

In **VS Code**, **VSCodium** und den **JetBrains-IDEs** (IntelliJ IDEA, PyCharm …) steckt
[Continue](https://continue.dev), verbunden mit dem KI-Server eurer Firma. Deine Daten gehen an
diesen Server, nicht an einen Dienst im Internet.

Was er kann:
- **Chat** über deinen Code, mit Auswahl des Modells
- **Bearbeiten:** Code markieren und sagen, was sich ändern soll
- **Agent-Modus:** Das Modell liest und ändert Dateien und schlägt Befehle vor, jedes Mal mit
  deiner Bestätigung

**In VS Code** sitzt Continue rechts in der Seitenleiste und öffnet sich beim ersten Öffnen eines
Ordners von selbst. Hast du sie geschlossen, holt **Strg+Alt+B** sie zurück. Der eingebaute
Copilot ist abgeschaltet.

**In JetBrains-IDEs** findest du Continue als Werkzeugfenster am Rand.

Beim ersten Start eines Arbeitsplatzes kann es ein, zwei Minuten dauern, bis der Assistent da ist:
OTA installiert ihn im Hintergrund, damit der Start nicht wartet. Ist der Editor schon offen,
startest du ihn danach einmal neu.

**Eigene Einstellungen:** OTA schreibt die Konfiguration `~/.continue/config.yaml` bei jedem Start
neu. Willst du sie selbst pflegen, löschst du die erste Zeile (`# Verwaltet von OTA …`). Danach
fasst OTA sie nicht mehr an. Löschst du die ganze Datei, kommt beim nächsten Start wieder die
Fassung von OTA.

### Continue ist weg oder verhält sich anders ✅

Erst nachsehen, ob nur das Symbol fehlt: In JetBrains-IDEs **View → Tool Windows → Continue**, in
VS Code **Strg+Alt+B**. Neue Plugins schieben ein Symbol gern ins **⋯** am Rand.

Fehlt Continue wirklich, hat meist etwas unsere Fassung verdrängt: ein Update aus dem Marketplace,
ein abgeschaltetes Plugin oder eine eigene Konfiguration. Dann im Dashboard in der Kachel des
laufenden Arbeitsplatzes **⋯ → KI-Werkzeuge neu einrichten**. Schliesse PyCharm und VSCodium vorher.
Das dauert bis zu einer Minute und

- entfernt eine Continue-Kopie aus dem Marketplace (JetBrains und VS Code/VSCodium),
- schaltet Continue wieder ein, wenn es abgeschaltet war,
- legt eine eigene `~/.continue/config.yaml` als `config.yaml.vor-ota-<Datum>` beiseite und schreibt
  die von OTA,
- installiert die Pakete von OTA noch einmal.

Danach den Editor starten. Andere Plugins und Erweiterungen bleiben, wie sie sind. Den Eintrag gibt
es nur, wenn IDE-AI für dich eingeschaltet ist.

**Bitte kein Update für Continue aus dem Marketplace annehmen**, wenn der Editor eins anbietet. Die
Fassung von OTA ist auf euren KI-Server eingestellt und an die IDE angepasst.

## Docker

Docker gibt es nur in **Root-Arbeitsplätzen** ([Kapitel 32](32-root-arbeitsplatz-nutzen.md#docker-)).
