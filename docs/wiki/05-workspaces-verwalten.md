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

**Streaming** steht ebenfalls hier: `Selkies` ist die Vorgabe und der Weg des eigenen
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

**Kerne sind ein Gewicht, keine harte Grenze** (seit 2026-10-27). Hat der Host Luft, darf ein
Container bis zum Vierfachen seiner Kerne nutzen, höchstens alle Kerne des Hosts. Wird es eng, teilt
der Kernel die Rechenzeit im Verhältnis der eingestellten Kerne auf: Ein Workspace mit 4 Kernen
bekommt dann doppelt so viel wie einer mit 2. Den Faktor setzt `OTA_CPU_BURST` in `deploy/.env`
(Vorgabe `4`; `1` heißt harte Grenze wie früher), gültig für neu angelegte Container und bei jeder
Ressourcenänderung. Der Grund steht in [Fehlersuche](12-fehlersuche.md#alles-ruckelt-obwohl-der-host-nicht-ausgelastet-ist).
Arbeitsspeicher bleibt eine harte Grenze.

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
| **Gemeinsame Daten** | Eigene Einstellungen je Typ, die Datenordner aus dem gemeinsamen Home. Läuft **gleichzeitig** mit den anderen Workspaces des Nutzers |
| **Pro Workspace** | Getrenntes Home je Typ. Wenn Konfigurationen sich stören |
| **Flüchtig** | Nichts wird gespeichert. Jeder Start beginnt beim Golden Image |

**Zwei Workspaces auf einem Home starten nicht gleichzeitig.** Der zweite wird mit einer Meldung
abgewiesen. Das ist Absicht: Programme wie VS Code oder Chrome legen Sperren und Sockets im Home ab
und greifen sonst in den anderen Container hinüber. Wer mehrere gleichzeitig braucht, zum Beispiel
zwei Root-Arbeitsplätze, stellt sie auf **Gemeinsame Daten**:

- Jeder Workspace hat sein eigenes Home unter `/srv/ota/profiles/<id>/<kennung>`, mit eigenen
  Einstellungen sowie eigenem Browser- und IDE-Profil.
- Die Ordner unter **Gemeinsame Ordner** kommen aus dem gemeinsamen Home (`…/<id>/user`). Was ein
  Arbeitsplatz dort ablegt, sieht der andere sofort. Vorgabe: `Desktop`, `Documents`, `Downloads`,
  `Music`, `Pictures`, `Videos`, `Templates`, `Public`. Eigene Ordner gehen auch, etwa
  `Projekte` oder `Projekte/kunde-a`. Sie müssen relativ sein, ohne `..` und nicht versteckt.
- Ablage, Gruppenlaufwerke und `~/Gemeinsam` sind wie immer dabei.
- Beim Umstellen beginnt der Workspace mit frischen Einstellungen aus dem Skeleton. Die alten
  Punktdateien bleiben im gemeinsamen Home liegen. Ein **angehaltener Root-Arbeitsplatz** braucht
  einmal *Neu aufsetzen* ([Kapitel 25](25-root-arbeitsplatz.md)), weil die Ordner beim Anlegen
  des Containers eingehängt werden. Was darin installiert ist, vorher einfrieren
  ([Kapitel 7](07-golden-images.md)).

**OTA-Git** (unter Ressourcen): Ist [OTA-Git](27-git.md) an, bekommen Arbeitsplätze aus diesem
Workspace Git für die Git-Subdomain vorkonfiguriert: Adresse, Token, Name und E-Mail. Vorgabe ist
an. Ausschalten lohnt sich für Workspaces, die mit Git nichts zu tun haben. Es wirkt beim nächsten
Start eines Arbeitsplatzes.

### Rechte
Zwischenablage, Dateien, Geräte, Sonstiges — gruppiert, mit Erklärung je Schalter.
Siehe [Kapitel 37](37-zwischenablage-verwaltung.md).

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

## Duplizieren ✅

Im Editor oben steht **Duplizieren**. Das ist der Weg, einen fertig eingerichteten Workspace — etwa
einen Root-Arbeitsplatz mit Apps, Netzprofil und Startskript — als Ausgangspunkt für einen zweiten
zu nehmen. Gefragt wird nur der Name (Vorgabe: „… (Kopie)").

| Kommt mit | Kommt nicht mit |
|---|---|
| alle Einstellungen: Image, Klasse, Streaming, Ressourcen, Netzprofil, Rechte, Umgebung, Startskript, Ablagen, Git | die **Fassungsliste** unter Images — die Kopie zeigt auf dasselbe Image, bis sie eine eigene Fassung gebaut oder eingefroren bekommt |
| der App-Katalog samt Symbolen, Auflösungen und Sichtbarkeit je Gruppe | was Menschen **in** ihren Arbeitsplätzen haben: Zuhause, installierte Software im Root-Container |
| Einmal-Skripte — sie laufen in der Kopie für jeden noch einmal | eigene Namen der Nutzer |
| Zuteilungen je Gruppe und Nutzer, die Gruppen | ungespeicherte Änderungen im offenen Editor |
| das Skeleton, auch die Teilbäume der Anwendungen | |

Die Kopie ist **ausgeschaltet**. Sonst stünde bei allen zugewiesenen Menschen sofort eine zweite,
gleich aussehende Kachel. Anpassen, dann unter Allgemein einschalten.

Weil sich Original und Kopie ein Image teilen können, räumt OTA beim Löschen und Aufräumen alter
Fassungen **kein Image weg, auf das eine andere Vorlage noch zeigt** — nur den Eintrag in der Liste.

> Wer auch **das darin Installierte** mitnehmen will, friert zuerst die eigene Session ein
> ([Kapitel 7](07-golden-images.md#session-einfrieren-)), dupliziert dann die Vorlage und stellt
> die Kopie auf die eingefrorene Fassung. Bei einem Root-Arbeitsplatz kommen dabei die
> Docker-Daten (Images und Container darin) **nicht** mit — sie liegen in einem eigenen Volume.

## Änderungen an laufenden Sessions

Ressourcenänderungen wirken **sofort, auch auf laufende, pausierte und angehaltene Container**. Nur
wenn der Arbeitsspeicher unter das sinken soll, was ein laufender Container gerade belegt, wartet
dieser Teil bis zum nächsten Start — niemandem wird im Betrieb Speicher entzogen, den er braucht.
Einzelheiten in [Kapitel 6](06-ressourcen-und-zuteilung.md#wirksamwerden).

Rechteänderungen wirken sofort.
