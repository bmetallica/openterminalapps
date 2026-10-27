# 36 · Begriffe

*Für Anwender.* Die Wörter, die in OTA und in diesem Handbuch vorkommen, in einfachen Worten.

| Begriff | Bedeutung |
|---|---|
| **Workspace** | eine Vorlage, die die Verwaltung anlegt: welche Programme, wie viel Rechenleistung, welche Rechte. Auf deiner Startseite ist das eine Kachel |
| **Arbeitsplatz** | ein ganzer Linux-Desktop mit mehreren Programmen, gestartet aus einem Workspace |
| **Einzelne Anwendung** | ein Workspace mit genau einem Programm, ohne Desktop drumherum |
| **Session** | ein gestarteter Workspace, der gerade läuft oder pausiert ist |
| **Container** | die abgeschottete Umgebung auf dem Server, in der deine Session läuft. Endet die Session, kann der Container verschwinden, dein Zuhause nicht |
| **Zuhause**, Home | dein persönlicher Ordner `/home/…`. Bleibt immer erhalten |
| **Persistenz** | was einen Neustart überlebt. Bei dir: das Zuhause, beim Root-Arbeitsplatz auch das System |
| **Image** | die Grundausstattung eines Workspaces: Betriebssystem und Programme. Aktualisiert die Verwaltung das Image, bekommst du beim nächsten Start die neuen Programme, dein Zuhause bleibt |
| **Root-Arbeitsplatz** | ein Arbeitsplatz, in dem du Administrator bist, mit Docker ([Kapitel 32](32-root-arbeitsplatz-nutzen.md)) |
| **Anhalten / Fortsetzen** | beim Root-Arbeitsplatz: schlafen legen und genau so wieder aufwecken |
| **Pausieren** | die Session friert ein, der Arbeitsspeicher bleibt belegt. Weiter geht es in unter einer Sekunde |
| **Neu aufsetzen** | einen Root-Arbeitsplatz aus dem aktuellen Image neu bauen. Das Zuhause bleibt |
| **Meine Ablage** | dein Austauschordner zwischen Browser und Arbeitsplatz (`~/Austausch`) |
| **Gemeinsame Ablage** | Dateien der Verwaltung für alle, nur lesbar (`~/Gemeinsam`) |
| **Gruppenlaufwerk** | ein Ordner für alle Mitglieder einer Gruppe (`~/Gruppen/…`) |
| **Kontrollleiste** | die einklappbare Leiste am rechten Rand einer Session ([Kapitel 34](34-bedienung.md)) |
| **Zentrale Anmeldung** | die Anmeldeseite deiner Firma, über die du auch in OTA kommst |
| **Zweiter Faktor** | ein Code aus einer App oder ein Passkey zusätzlich zum Passwort ([Kapitel 30](30-mein-konto.md)) |
| **Kern**, CPU | Rechenleistung. Die Zahl auf der Kachel ist dein Anteil, wenn der Server voll ist. Ist er es nicht, darfst du mehr nutzen |
| **Arbeitsspeicher**, RAM | was deine Programme gleichzeitig im Speicher halten dürfen. Wird es mehr, beendet der Server das grösste Programm |
| **Selkies** | die Technik, die das Bild deines Arbeitsplatzes in den Browser überträgt |
| **OTA-Git**, Forgejo | der Git-Server von OTA ([Kapitel 33](33-entwickeln.md)) |
| **IDE-AI**, Continue | der KI-Assistent im Editor ([Kapitel 33](33-entwickeln.md)) |
| **News** | Meldungen der Verwaltung an alle, in der Seitenleiste |

## Häufige Fragen

**Kann die Verwaltung sehen, was ich tue?**
Ein Administrator kann sich auf deinen Bildschirm schalten oder ein Terminal in deinem Arbeitsplatz
öffnen. Beides steht im Protokoll ([Kapitel 3](03-arbeitsplatz.md#wer-sonst-noch-auf-deinen-bildschirm-sehen-kann)).
In deine **Meine Ablage** sieht niemand.

**Geht etwas verloren, wenn ich den Tab schliesse?**
Nein. Die Session läuft weiter, bis du sie beendest oder sie wegen Leerlauf endet. Auf der
Startseite öffnest du sie wieder.

**Geht etwas verloren, wenn die Session endet?**
Dein Zuhause nicht. Beim Standard-Arbeitsplatz alles, was du ausserhalb davon installiert hast
([Kapitel 31](31-dateien.md#was-nach-dem-beenden-noch-da-ist)).

**Kann ich von zu Hause arbeiten?**
Wenn die Verwaltung OTA von aussen erreichbar gemacht hat: ja, mit jedem aktuellen Browser. Auf dem
eigenen Rechner musst du nichts installieren.

**Welcher Browser?**
Chrome, Edge oder Firefox, jeweils aktuell. In Firefox braucht das automatische Einfügen eine kleine
Erweiterung ([Kapitel 4](04-zwischenablage.md#firefox-)).
