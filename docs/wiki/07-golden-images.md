# 7 · Golden Images

*Für Administratoren.* ✅ Build-Pipeline mit Live-Protokoll, Rezepte, App-Erkennung, Versionen,
Aktivierung und Rückrollen · ✅ Session einfrieren · ✅ Skeleton-Verwaltung, je Arbeitsplatz und
je Anwendung · ✅ eigenes Basisimage `ota/base-xfce`

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

## Session einfrieren ✅

Golden Images entstehen selten am Reißbrett. Der praktische Weg:

1. **Den eigenen Arbeitsplatz starten** und darin einrichten, was alle bekommen sollen — Pakete
   nachinstallieren, Werkzeuge konfigurieren
2. Unter *Software → Session einfrieren* auf **„Ansehen, was mitkäme"**
3. Die Liste durchgehen
4. **„Als neue Fassung einfrieren"** — danach wie jede andere Fassung aktivieren

Eingefroren wird **die eigene** Session. Eine fremde einzufangen wäre etwas anderes und bräuchte
eine eigene Begründung.

### Was mitkommt — und was nicht

**Das Zuhause kommt nicht mit.** `docker commit` nimmt das Dateisystem des Containers, aber keine
Bind-Mounts, und das Home liegt genau dort. Das ist die richtige Grenze und kein Zufall: Ein
Zuhause gehört einem Menschen und enthält seine Schlüssel. Es in ein Image zu legen, das alle
bekommen, wäre ein Datenleck mit Ansage.

Mit kommt alles ausserhalb: nachinstallierte Pakete, Änderungen in `/etc`, Dateien in `/opt`.

Nicht in der Liste stehen die Verzeichnisse, die sich in jedem Container ändern und niemanden
interessieren — `/tmp`, `/var/log`, `/var/cache`, `/proc`. Ohne diese Kürzung bestünde die Vorschau
zu neun Zehnteln aus Rauschen, und dann läse sie niemand. Womit auch niemand die Warnung darin läse.

### Der Geheimnis-Filter

Auch ausserhalb des Home landen Zugangsdaten: `/etc/ssh`, eine `.netrc` unter `/root`, ein
Kerberos-Ticket. Was danach aussieht, steht **oben in der Liste und farbig**:

```
.ssh/id_*      .gnupg/       *token*        *.pem   *.key
.aws/          .docker/config.json          krb5cc_*
.netrc         .git-credentials             *.keytab
/etc/ssh/ssh_host_*           /etc/shadow
```

**Ohne ausdrückliche Bestätigung wird nicht eingefroren.** Eine Vorschau, die sich übergehen lässt,
ist Dekoration — die Schaltfläche heißt dann „Trotz der Funde einfrieren", und das Protokoll der
Fassung nennt jede einzelne Datei namentlich.

Trotzdem gilt: **Ein Golden Image sollte nie aus einer Session entstehen, in der mit echten
Zugangsdaten gearbeitet wurde.** Der Filter ist ein Netz, keine Garantie.

### Eine Datei wird immer entfernt

`/etc/sudoers.d/ota-admin` — die Datei, die einem Administrator in **seinem** Container `sudo`
erlaubt ([Kapitel 8](08-nutzer-und-gruppen.md)). Bliebe sie im Image, bekäme **jeder** Nutzer des
neuen Golden Image passwortloses root: Aus einer Ausnahme für eine Person wäre stillschweigend die
Voreinstellung für alle geworden.

Sie wird vor dem Einfrieren entfernt und **danach im laufenden Container wieder hingelegt**. Wer
ein Image baut, soll dabei nicht sein eigenes `sudo` verlieren. Für jede weitere Session eines
Administrators wird sie ohnehin neu geschrieben.

### Was danach passiert

Die neue Fassung ist **nicht aktiv**. Erst ein Klick auf *Aktivieren* stellt sie scharf — dieselbe
Reihenfolge wie beim Bauen, und aus demselben Grund: Was alle bekommen, soll niemand versehentlich
ausrollen. Laufende Sessions bleiben unberührt.

Das Kasm-Label wird dabei gelöscht und das Startskript überschrieben, genau wie beim Bauen: Sonst
räumte Kasms Aufräumdienst das Image weg, und der eingefrorene Container brächte das Startskript
mit, das gerade in ihm lief.

## Versionen

Jeder Build erzeugt `ota/<name>:v<N>` mit Digest, Größe und vollständigem Log.

- Genau eine Version ist **aktiv** — neue Sessions nutzen sie
- **Laufende Sessions bleiben unberührt**
- **Rollback** ist ein Klick: eine andere Version aktiv setzen
- Alte Versionen werden aufgeräumt: **die letzten drei bleiben**, dazu immer die aktive, auch wenn
  sie älter ist. Eine Fassung, auf die man zurückfallen könnte, ist der halbe Sinn der Versionierung

Eine einzelne Fassung lässt sich auch **von Hand entfernen** — für einen Fehlversuch, einen
Probelauf, ein Image, dessen Inhalt nicht verteilt werden soll. Die **aktive** nicht: Sie zu löschen
liesse die Vorlage auf ein Image zeigen, das es nicht mehr gibt, und der nächste Start scheiterte
mit einer Meldung, die niemand mit diesem Klick in Verbindung brächte.

> Das Aufräumen lief bis zum 2026-08-28 gar nicht — die Regel stand im Code und wurde nie
> angewendet. Aufgefallen ist es erst, als das Einfrieren dazukam und Fassungen schneller wuchsen
> als beim Bauen. Jede belegt Platz, und auf einem Host mit 25 GB frei ist das nach ein paar Wochen
> das Ende des Betriebs.

Empfehlenswert ist ein **Testlauf**: neue Version zuerst einer kleinen Gruppe zuweisen, dann global.

## Software einbauen und freigeben ✅

**Workspace-Editor → Software.** Zwei Schritte, die untereinander stehen, weil sie in dieser
Reihenfolge passieren.

### 1 · Einbauen

Pakete anklicken oder eintippen, dann **Image bauen**. Das Protokoll läuft **live** mit — es kommt
als Ereignisstrom, Zeile für Zeile, sobald sie entsteht. Der Build dauert je
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

> **Warum das Protokoll live läuft.** Der Server fragt den Agent weiterhin im Zwei-Sekunden-Takt
> ab; anders kommt man an den Fortschritt von `docker build` nicht heran. Was wegfällt, ist die
> Abfrage des Browsers: Er bekommt nur noch den Zuwachs. Bei einem Protokoll, das auf mehrere
> hundert Kilobyte anwächst, ist das der Unterschied zwischen einem ruhigen Fenster und einem, das
> ruckelt. Lässt ein Zwischenstück den Strom nicht durch, fällt die Oberfläche auf die alte Abfrage
> zurück — lieber langsam als blind.

**Nach dem Bauen prüft OTA, wohin die Editoren zeigen.** Am Ende des Protokolls steht, aus welchem
Marktplatz VS Code, VSCodium oder Code-OSS ihre Erweiterungen holen. Zeigt ein Nicht-Microsoft-Editor
auf Microsofts Marktplatz, steht dort eine Warnung — das wäre ein Lizenzverstoss
([Kapitel 13](13-lizenzen.md)). Der Build scheitert deswegen nicht; die Entscheidung, ein solches
Image zu verteilen, gehört einem Menschen.

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
| **Zeichen** | Klick auf das Symbol schaltet weiter. Erscheint nur, wenn das Paket **kein** eigenes Symbol mitbringt — sonst steht dort das echte |

### Das Symbol aus dem Paket ✅

Unter `Icon` steht in der `.desktop`-Datei meist nur ein Name („firefox"), keine Datei. Wo das Bild
dazu liegt, regelt die Freedesktop-Spezifikation, und OTA sucht es dort: unter
`/usr/share/icons/<thema>/<größe>/apps/`, im alten `/usr/share/pixmaps`, notfalls über die ganze
Ablage. Gesucht wird von gross nach klein und PNG vor SVG — gross, weil die Oberfläche skaliert und
ein hochskaliertes 16er-Symbol matschig aussieht.

Gemessen an einem echten Arbeitsplatz-Image: **16 von 16 Anwendungen** brachten ein Symbol mit.

Zwei Dinge passieren dabei automatisch:

- **Verkleinert.** Ein Paket liefert die Grösse, die es für richtig hält: 554 Bytes bei Vim,
  42 KB bei GIMP, **428 KB bei VSCodium**. OTA rechnet alles auf höchstens 128 Pixel Kantenlänge
  herunter. Ohne das läge ein halbes Megabyte in der Datenbank und in jeder Antwort des Katalogs.
- **Geprüft.** Ein SVG mit einem Verweis nach draussen wird nicht übernommen. Sonst riefe das
  Dashboard bei jedem Öffnen einen fremden Server auf — für jeden Betrachter.

> **Bestehende Kataloge bekommen die Symbole nicht von selbst.** Sie stammen aus dem Image, und das
> liest OTA nur beim Durchsehen. Einmal **Im Image nachsehen** und **Freigeben** genügt; danach
> stehen sie überall — im Dashboard, im Umschalter der laufenden Session, im Skeleton-Reiter.

Ausgeliefert werden sie unter einer eigenen Adresse und nicht im Katalog selbst. Der Grund ist
messbar: Ein Katalog mit sechzehn Symbolen als Datenadressen wiegt 140 KB, und das Dashboard lädt
die Vorlagen **alle 15 Sekunden** neu. Als Adresse holt der Browser jedes Bild einmal und legt es
beiseite; ein Fingerabdruck im Anhang sorgt dafür, dass nach einem Image-Update trotzdem das neue
kommt.

Bringt ein Image kein Symbol mit — etwa bei einem selbst gebauten Startskript ohne
`.desktop`-Eintrag —, bleibt es beim Zeichen, und der Zeichenwechsler erscheint wieder.

Zwei Hinweise erscheinen von selbst:

- **„Braucht ein Terminal"** — ein Konsolenprogramm wie `htop` startet allein auf leerem Bildschirm.
- **„Im aktiven Image nicht mehr vorhanden"** — der Katalog kennt es noch, das Image nicht mehr.
  Passiert nach einem Wechsel des Basisimages.

**Die Reihenfolge ist bedeutsam.** Aus ihr leitet sich ab, welches Display eine Anwendung bekommt.
Wer sie ändert, muss laufende Arbeitsplätze neu starten.

### Auflösung je Anwendung ✅

Unter jeder Anwendung stehen zwei Zahlenfelder. Bleiben sie leer, gilt die Auflösung des
Arbeitsplatzes — sie steht als Platzhalter darin, damit der geerbte Wert sichtbar ist, ohne gesetzt
zu sein.

Gedacht ist das für den Fall, dass eine Anwendung mehr Fläche braucht als die übrigen: eine
Entwicklungsumgebung neben einem Terminal. Der Strom passt sich anschliessend ohnehin dem
Browserfenster an — die Auflösung ist der **Anfangswert**, und der entscheidet, wie eine Anwendung
ihre Oberfläche zuerst aufbaut. Manche Programme merken sich diese erste Aufteilung.

**Sie gilt ab dem nächsten Start dieser Anwendung.** Ein laufendes Display wird nicht umgestellt —
wie bei allen Ressourcen in OTA. Wer die Wirkung sofort sehen will, schliesst die Anwendung im
Viewer und öffnet sie erneut.

### Sichtbarkeit je Gruppe ✅

Unter jeder Anwendung steht, wer sie bekommt. Im Normalfall **„Sichtbar für alle"** — gemeint ist:
alle, die diesen Arbeitsplatz überhaupt sehen. Ein Klick öffnet die Gruppen, und sobald eine gewählt
ist, sehen nur deren Mitglieder die Anwendung.

Der Fall, für den das gedacht ist: Eine Lizenz reicht nicht für alle. Die Anwendung ist im Image —
sie muss es sein, es ist ein Image für alle —, aber im Dashboard erscheint sie nur bei denen, die
sie benutzen dürfen.

> **Die Liste im Dashboard ist gefiltert, aber sie ist nicht die Absicherung.**
> Geprüft wird beim Start: Ein Aufruf der Startadresse mit dem Kürzel einer gesperrten Anwendung
> wird abgewiesen, auch wenn der Arbeitsplatz dem Aufrufer gehört. Beides steht als Prüfung in
> `scripts/test-authz.sh`.

**Administratoren sehen immer alles.** Sonst könnten sie einen Katalog verwalten, den sie nicht
sehen.

**Eine gelöschte Gruppe verschwindet aus den Katalogen.** Die Anwendung ist danach wieder für alle
da — die Alternative wäre eine Anwendung, die niemandem mehr gehört und die niemand mehr sieht.

## Der App-Katalog

Beim Arbeitsplatz enthält das Golden Image mehrere Anwendungen. Je App wird hinterlegt:

```
Anzeigename · Icon · Startbefehl und Argumente
bevorzugte Auflösung ✅
Skeleton-Teilbaum   je Anwendung ein eigener Baum ✅
Extension-Liste     wird beim BUILD installiert, nicht beim Start
Sichtbarkeit        je Gruppe zuschaltbar ✅
```

### Der Skeleton-Teilbaum je Anwendung

Unter *Workspaces → Skeleton* steht oben eine Reihe: **Ganzer Arbeitsplatz** und daneben jede
Anwendung. Der Unterschied ist der Zeitpunkt.

| | Ganzer Arbeitsplatz | Je Anwendung |
|---|---|---|
| **Kommt** | beim ersten Start des Arbeitsplatzes, solange das Zuhause leer ist | beim ersten Start **dieser Anwendung**, auch Monate später |
| **Wie oft** | einmal je Zuhause | einmal je Zuhause und Anwendung |
| **„Durchsetzen"** | ja, für einzelne Pfade | nein — dafür ist der Baum des Arbeitsplatzes da |
| **Gedacht für** | `.bashrc`, Firmenzertifikat, Desktop-Verknüpfungen | `.config/Code/User/`, `.config/JetBrains/`, `.config/VSCodium/User/` |

**Warum getrennt.** Ein Arbeitsplatz trägt ein Dutzend Anwendungen, und nicht jeder Mensch startet
jede davon. Die Einstellungen der Entwicklungsumgebung in das Zuhause von jemandem zu legen, der
nur das Terminal benutzt, macht das Zuhause voll und die Fehlersuche schwer — bei einer Beschwerde
steht dann Konfiguration herum, die nie eine Anwendung gelesen hat.

Der Teilbaum kommt **bevor** die Anwendung startet. Andersherum legte sie erst ihre
Voreinstellungen an, und der Teilbaum überschriebe hinterher, was der Mensch schon auf dem
Bildschirm sieht.

Gemerkt wird das im Zuhause selbst, unter `~/.ota/app-skeleton/<anwendung>` — nicht in der
Datenbank. Zwei Gründe: Der Anwendungskatalog wird beim Speichern komplett ersetzt, eine daran
hängende Buchführung wäre nach jeder Katalogänderung weg. Und die Frage lautet ohnehin „hat
**dieses Zuhause** den Teilbaum schon?", die kann nur das Zuhause beantworten. Ein Workspace ohne
persistentes Profil bekommt ihn folgerichtig bei jedem Start neu.

> **Erneut ausrollen** — dieselbe Geste wie „Nochmal" bei den Einmal-Skripten, nur von Hand:
> ```
> docker exec <container> rm -f /home/kasm-user/.ota/app-skeleton/<anwendung>
> ```
> Beim nächsten Start dieser Anwendung kommt der Teilbaum wieder.

**Extensions gehören in den Build, nicht in den Start.** Sonst wartet jeder Nutzer bei jedem Start
auf Downloads, und ein Ausfall des Marketplace legt den Arbeitsplatz lahm. Die Liste steht unter
*Software → VS-Code-Erweiterungen*.

> **Sie landen ausschliesslich in Microsofts VS Code.** VSCodium hat seinen eigenen Satz aus
> Open VSX und sieht sie nicht — dieselbe Kennung ist dort nicht dieselbe Installation, und manche
> Erweiterung gibt es nur auf einem der beiden Marktplätze. Wer beide Editoren anbietet, pflegt
> zwei Sätze ([Kapitel 13](13-lizenzen.md)).

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
