# 5 · Workspaces verwalten

*Für Administratoren.* Menüpunkt **Workspaces**.

## Was ein Workspace ist

Eine Vorlage, aus der Sessions entstehen. Sie legt fest: welches Image, wie viele Ressourcen, welche
Rechte, wer sie sehen darf.

Zwei Betriebsarten:

| `mode` | Bedeutung | Wann |
|---|---|---|
| **`workspace`** | Ein Linux je Nutzer, mehrere Apps darin. **Standard** | Der tägliche Arbeitsplatz |
| `single_app` | Eine Anwendung als Wegwerf-Container | Selten genutzte Werkzeuge, eingebundene Kasm-Images |

## Kapazitätsanzeige

Über der Liste stehen drei Messwerte:

- **Arbeitsspeicher frei** — was der Host gerade übrig hat
- **Zugesagt je Session** — die Summe aller aktiven Workspaces, wenn alle gleichzeitig liefen.
  Übersteigt sie den freien Speicher, färbt sich der Balken rot. Das ist **kein Fehler**, sondern
  bewusste Überbuchung — nur soll sie sichtbar sein, nicht überraschend
- **Kerne** — was sich alle Sessions teilen

## Der Editor

Klick auf eine Zeile öffnet den Editor als Seitenleiste; die Liste bleibt sichtbar.

### Allgemein
Anzeigename, Beschreibung, Image, Kategorien, aktiv/inaktiv.

Das **Image** wird aus den auf dem Host vorhandenen ausgewählt, nicht frei getippt. Die Größe steht
daneben.

Ein deaktivierter Workspace verschwindet aus den Dashboards, die Zuweisungen bleiben aber bestehen.

**Streaming** steht ebenfalls hier: `Selkies (WebRTC)` ist die Vorgabe und der Weg des eigenen
Basisimages; `KasmVNC (RFB)` gehört zu Images von Kasm, die kein Selkies mitbringen.

### Netz ✅

Ein Auswahlfeld, und ohne Zutun steht dort **Vorgabe (Internet, kein Firmennetz)**: Der
Arbeitsplatz kommt ins Internet, aber nicht ins Firmennetz, nicht an die Nachbarsitzung und nicht
an den Wirt. Für die meisten Vorlagen ist das die richtige Antwort und nichts zu tun.

Wer mehr oder weniger braucht, legt unter **Netz** ein Profil an und wählt es hier aus — etwa
*Abgeschottet* für eine Vorlage, die nur mit lokalen Daten umgeht, oder ein eigenes mit einer
Freigabe auf den internen Paketspiegel. Ein Profil gilt für **jede Sitzung dieser Vorlage**.

Das Feld wirkt erst beim **nächsten Start** einer Sitzung. Was der Grundregelsatz ohnehin
durchlässt, steht in [Kapitel 23](23-netz.md) — dort auch die Stufe „aus", die jede Einschränkung
aufhebt und deshalb eine Begründung verlangt.

### Apps (nur bei `mode: workspace`) ✅
Der Katalog der im Golden Image installierten Anwendungen. Je App: aktiv/inaktiv und die Quelle ihrer
Extensions.

> **Extensions wandern nicht zwischen den Editoren.** VS Code zieht aus dem Microsoft-Marketplace,
> VSCodium aus Open VSX, Cursor aus einer eigenen Registry. Wer in mehreren arbeitet, pflegt mehrere
> Sätze. Das ist keine Einschränkung von OTA, sondern eine Lizenzbedingung
> ([Kapitel 13](13-lizenzen.md)).

Gesperrte Apps zeigen den Grund an und lassen sich nicht einschalten.

### Ressourcen
Prozessorkerne, Arbeitsspeicher, Auflösung, Inaktivitätszeit und was danach passiert.

Die Regler zeigen auf der Schiene **schraffiert**, ab wo dieser Host überbucht wäre. Wer darüber
hinausgeht, sieht sofort die Folge — statt sie später im OOM-Kill zu erfahren.

Beim Arbeitsplatz gelten die Werte für den **Container als Ganzes**, nicht je App.

*Was nach Inaktivität passiert:*

| | |
|---|---|
| **Pausieren** | Der Arbeitsspeicher bleibt belegt, Fortsetzen dauert unter einer Sekunde |
| **Stoppen** | Der Container wird beendet und beim nächsten Mal neu gestartet |
| **Löschen** | Der Container wird entfernt. **Das persistente Profil bleibt erhalten** |

*Persistenz:*

| | |
|---|---|
| **Pro Nutzer** | Ein gemeinsames Home für alle Workspaces. Der Normalfall |
| **Pro Workspace** | Getrenntes Home je Typ. Wenn Konfigurationen sich stören |
| **Flüchtig** | Nichts wird gespeichert. Jeder Start beginnt beim Golden Image |

### Rechte
Zwischenablage, Dateien, Geräte, Sonstiges — gruppiert, mit Erklärung je Schalter.
Siehe [Kapitel 4](04-zwischenablage.md).

### Umgebung
Umgebungsvariablen für den Container.

> **Keine Geheimnisse hier.** Umgebungsvariablen sind über `docker inspect` für jeden mit
> Docker-Zugriff lesbar und landen in Logs. Zugangsdaten gehören in die Secret-Ablage.

### Zuteilung
Zwei Teile: welche **Gruppen** den Workspace sehen, und welche **Ressourcen je Nutzer** gelten.
→ [Kapitel 6](06-ressourcen-und-zuteilung.md)

Änderungen an der Gruppenzuweisung zeigen sofort ihre Folge („2 Gruppen kommen hinzu. Betroffene
Nutzer sehen den Workspace nach dem Speichern.").

> **Für alle, die die Schnittstelle direkt benutzen:** In einem `PUT /api/templates/{id}` bedeutet
> ein **fehlendes** `group_ids`, dass die Zuweisung bleibt, wie sie ist. Eine **leere Liste**
> bedeutet, dass sie niemand mehr hat. Der Unterschied zwischen *nichts gesagt* und *nichts gewollt*
> ist hier wichtig: Bis zum 2026-08-28 galt beides als „niemand mehr", und ein Aufruf, der nur eine
> Einstellung ändern wollte, liess den Workspace wortlos von allen Dashboards verschwinden.

## Änderungen an laufenden Sessions

Ressourcenänderungen wirken auf die **nächste** Session. Laufende bleiben unberührt — niemandem wird
im Betrieb der Speicher entzogen.

Rechteänderungen wirken sofort.
