# 7 · Golden Images

*Für Administratoren.* ✅ Build-Pipeline, Versionen und Aktivierung ·
🔨 Skeleton-Verwaltung und „Session einfrieren" (M5)

> **Kasm auf demselben Host stört nicht mehr.** Sein Agent löschte anfangs jedes
> gebaute Golden Image, weil es das Label `com.kasmweb.image=true` vom Basisimage
> erbte. Der Builder löscht dieses Label jetzt — Images ohne es betrachtet Kasm
> gar nicht erst. Details in [Kapitel 12](12-fehlersuche.md).

## Was ein Golden Image ist

Ein vorkonfigurierter Arbeitsplatz, den alle Nutzer identisch bekommen. Er besteht aus vier Schichten:

| Schicht | Inhalt |
|---|---|
| **Basis** | Ein Ausgangsimage — `ota/base-xfce` oder ein fertiges Kasm-Image |
| **Build-Layer** | Pakete, **Extension-Listen je Editor**, freies Setup-Skript |
| **Skeleton-Profil** | Was beim *ersten* Start ins Home kopiert wird: `settings.json`, Git-Vorlage, Zertifikate, Desktop-Verknüpfungen |
| **Laufzeit-Richtlinie** | Ressourcen, Auflösung, Rechte, Timeouts |

## Der übliche Weg: Session einfrieren

Golden Images entstehen selten am Reißbrett. Der praktische Weg:

1. Arbeitsplatz starten
2. Alles interaktiv einrichten — Extensions installieren, Einstellungen setzen, Werkzeuge
   konfigurieren
3. **„Als Golden Image speichern"**

OTA nimmt dann ein Abbild des Containers, vergleicht das Home mit dem bisherigen Skeleton und schlägt
die Änderungen vor.

### Der Geheimnis-Filter

Vor dem Speichern werden Zugangsdaten **automatisch aussortiert**:

```
.ssh/id_*      .gnupg/       *token*        *.pem
.aws/          .docker/config.json          krb5cc_*
.smbcredentials              keytab         Browser-Cookies
```

Was gefunden wurde, wird angezeigt. Trotzdem gilt: **Ein Golden Image sollte nie aus einer Session
entstehen, in der mit echten Zugangsdaten gearbeitet wurde.** Der Filter ist ein Netz, keine Garantie.

## Versionen

Jeder Build erzeugt `ota/<name>:v<N>` mit Digest, Größe und vollständigem Log.

- Genau eine Version ist **aktiv** — neue Sessions nutzen sie
- **Laufende Sessions bleiben unberührt**
- **Rollback** ist ein Klick: eine andere Version aktiv setzen
- Alte Versionen werden nach Regel aufgeräumt (Vorgabe: die letzten drei)

Empfehlenswert ist ein **Testlauf**: neue Version zuerst einer kleinen Gruppe zuweisen, dann global.

## Software einbauen und freigeben ✅

**Workspace-Editor → Software.** Zwei Schritte, die untereinander stehen, weil sie in dieser
Reihenfolge passieren.

### 1 · Einbauen

Pakete anklicken oder eintippen, dann **Image bauen**. Das Protokoll läuft mit; der Build dauert je
nach Paket ein paar Minuten. Danach steht die neue Fassung unter *Fassungen* und wird mit
**Aktivieren** in Betrieb genommen. Laufende Sessions bleiben unberührt — die neue Fassung gilt ab
dem nächsten Start.

**Pakete werden vorher geprüft.** OTA fragt das Image, ob es einen Namen kennt, bevor der Build
startet. Das erspart den häufigsten Fehlschlag: einen Debian-Namen auf einem Ubuntu-Image. Wer
`firefox-esr` einträgt, bekommt sofort „kennt dieses Image nicht" und Vorschläge statt zehn Minuten
später eine Zeile im Protokoll.

Eine zweite Prüfung ist unauffälliger und wichtiger: **Ubuntu 22.04 führt `firefox` nur noch als
Verweis auf ein Snap.** In einem Container läuft kein Snap; installiert würde ein Platzhalter ohne
Programm — der Build meldete Erfolg, und erst der Nutzer merkte, dass nichts da ist. OTA erkennt das
und sagt es.

### Rezepte ✅

Für Software, die kein einfaches Paket ist. Mitgeliefert sind **Firefox** (aus dem APT-Depot von
Mozilla), **Google Chrome** und **VSCodium**. Ein Klick hängt die Schritte an das eigene Skript an —
sichtbar und änderbar, nicht als verstecktes Verhalten.

#### Ein eigenes Rezept bauen

**Neues Rezept** öffnet eine Führung. Links die Fragen, rechts sofort das Ergebnis: Man sieht, was
eine Antwort bewirkt, während man sie gibt. Fünf Arten decken fast alles ab:

| Art | Wofür | Was gefragt wird |
|---|---|---|
| **APT-Depot** | Der häufigste Fall. So kommen Firefox, Chrome und VSCodium ins Image | Schlüssel-Adresse, Depot-Zeile, Paket, Vorrang |
| **.deb-Datei** | Software, die als Datei statt über ein Depot ausgeliefert wird | Adresse der Datei |
| **Archiv** | Alles mit eigenem Verzeichnis — JetBrains, Blender | Adresse, Kennung, Programm im Archiv, Anzeigename |
| **AppImage** | Eine einzelne AppImage-Datei | Adresse, Kennung, Anzeigename |
| **Eigenes Skript** | Wenn keine Art passt | nur der Text |

Zwei Dinge nimmt die Führung dabei ab, die sonst übersehen werden:

- **Der Schlüssel wird an die Depot-Zeile geheftet.** Den Teil mit `signed-by` schreibt niemand
  selbst; er wird eingesetzt.
- **Archiv und AppImage bekommen einen Menüeintrag.** Das ist kein Beiwerk: An der `.desktop`-Datei
  erkennt OTA die Anwendung später beim *Im Image nachsehen*. Ohne sie wäre sie zwar installiert,
  aber nicht auffindbar.

**Der Schalter „Vorrang"** ist der unscheinbarste und wichtigste. Er wird gebraucht, wenn die
Distribution ein gleichnamiges Paket führt — sonst gewinnt deren Fassung. Genau der Fall bei Firefox
auf Ubuntu.

Das erzeugte Skript ist kein Geheimnis: Es steht daneben und lässt sich ändern. Wer das tut, dessen
Fassung gilt — die Felder überschreiben den Text dann nicht mehr.

**Mitgelieferte Rezepte lassen sich nicht ändern**, nur kopieren. So bleibt das Original als
Vergleich stehen. Selbst gebaute lassen sich ändern und löschen.

Rezepte holen Software aus fremden Depots. Wer das nicht will, baut aus einem internen Spiegel; die
Schritte stehen im Skript und lassen sich umschreiben.

### 2 · Freigeben

**Im Image nachsehen** listet, was installiert ist. Niemand muss dafür einen Startbefehl kennen:
Jedes Linux-Paket bringt eine `.desktop`-Datei mit, in der Name, Symbol und Aufruf stehen — OTA
liest sie aus dem gebauten Image.

Was bleibt, ist eine Liste mit Schaltern. Zusätzlich lässt sich je Eintrag ändern:

| | |
|---|---|
| **Name** | direkt in der Zeile. „GNU Image Manipulation Program" heißt bei euch vielleicht schlicht „GIMP" |
| **Zeichen** | Klick auf das Symbol schaltet weiter. Die Auswahl ist bewusst klein — die Oberfläche hat eine feste Zeichensprache |

Zwei Hinweise erscheinen von selbst:

- **„Braucht ein Terminal"** — ein Konsolenprogramm wie `htop` startet allein auf leerem Bildschirm.
- **„Im aktiven Image nicht mehr vorhanden"** — der Katalog kennt es noch, das Image nicht mehr.
  Passiert nach einem Wechsel des Basisimages.

**Die Reihenfolge ist bedeutsam.** Aus ihr leitet sich ab, welches Display eine Anwendung bekommt.
Wer sie ändert, muss laufende Arbeitsplätze neu starten.

## Der App-Katalog

Beim Arbeitsplatz enthält das Golden Image mehrere Anwendungen. Je App wird hinterlegt:

```
Anzeigename · Icon · Startbefehl und Argumente
bevorzugte Auflösung
Skeleton-Teilbaum   .config/Code/User/       für VS Code
                    .config/JetBrains/        für IntelliJ
                    .config/VSCodium/User/    für VSCodium
Extension-Liste     wird beim BUILD installiert, nicht beim Start
Sichtbarkeit        je Gruppe zuschaltbar
```

**Extensions gehören in den Build, nicht in den Start.** Sonst wartet jeder Nutzer bei jedem Start
auf Downloads, und ein Ausfall des Marketplace legt den Arbeitsplatz lahm.

### Einzelinstanz-Anwendungen

VS Code, Chrome und Thunderbird lassen sich nur einmal je Nutzer starten. Ein zweiter Aufruf meldet
sich bei der laufenden Instanz und beendet sich — ohne Fenster, ohne Fehlermeldung. Im Katalog
bekommt eine solche Anwendung deshalb ihr **festes Display** eingetragen: „diese Anwendung gehört
auf genau diesen Bildschirm".

> Das hiess bis zum 2026-08-27 versehentlich etwas anderes, nämlich „sie läuft dort schon" — OTA
> startete sie dann gar nicht. Das ging nur gut, solange das geerbte Startskript des Basisimages
> sie im Drei-Sekunden-Takt neu startete. Beides ist behoben; die Geschichte steht in
> [Kapitel 12](12-fehlersuche.md).

Erkennbar am schwarzen Bild trotz „läuft": Prüfe mit
`docker exec <container> pgrep -a <anwendung>`, ob sie bereits auf einem anderen Display läuft.

## Profil und Drift

Nutzer verändern ihre Umgebung — das ist erwünscht. Für die Fälle, in denen etwas verbindlich bleiben
muss:

- **„Enforce"-Pfade**: definierte Dateien werden bei *jedem* Start aus dem Skeleton überschrieben.
  Für Firmen-Zertifikate, Proxy-Einstellungen, Registry-URLs. Sparsam einsetzen — jede Datei hier ist
  eine, die der Nutzer nicht anpassen kann
- **Profil zurücksetzen**: für einzelne Nutzer oder ganze Gruppen, mit automatischer Sicherung

## Builds

Builds laufen **serialisiert** — nur einer gleichzeitig, damit der Host nicht einbricht. Das Log
läuft live mit, Timeout 45 Minuten, jederzeit abbrechbar.

Ein nächtlicher Rebuild zur Aufnahme von Sicherheitsupdates ist optional. Er meldet, was sich
geändert hat, und aktiviert die neue Version **nicht** von selbst.

## Größe im Blick behalten

Ein Arbeitsplatz mit fünf Werkzeugen landet bei 12–18 GB. Er liegt **einmal** auf dem Host,
unabhängig von der Zahl der Nutzer. Trotzdem: vor dem Aufnehmen einer weiteren Anwendung prüfen, ob
sie den Alltag wirklich trägt.
