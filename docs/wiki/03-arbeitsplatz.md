# 3 · Der Arbeitsplatz

*Für Anwender.*

## Dein Dashboard

Nach der Anmeldung siehst du zwei Bereiche:

**Deine Sessions** — was gerade läuft oder pausiert ist. Das steht oben, weil der Alltag nicht
„eine App aussuchen" ist, sondern „zurück in meine Maschine".

**Deine Apps** — was du starten kannst.

Eine Session-Karte zeigt Laufzeit, letzte Aktivität, CPU und Arbeitsspeicher. Die farbige Kante links
und die Leuchtpunkte sagen den Zustand:

| Farbe | Zustand |
|---|---|
| Grün, pulsierend | läuft |
| Blau | pausiert — Arbeitsspeicher bleibt belegt, Fortsetzen dauert unter einer Sekunde |
| Grau | gestoppt — das Profil bleibt erhalten, der Start dauert wieder etwas |
| Rot | fehlgeschlagen |

## Apps im Arbeitsplatz starten ✅

Der Arbeitsplatz trägt eine **App-Leiste**. Ein Klick startet die Anwendung oder holt sie in den
Vordergrund. Apps mit Leuchtpunkt laufen bereits.

Nicht gestartete Apps kosten **nichts** — ihr Display wird erst beim ersten Klick erzeugt und beim
Schließen wieder abgebaut.

Alle Apps teilen sich:
- dasselbe `/home` mit deinen Projekten
- deine SSH-Schlüssel und die Git-Konfiguration
- **dieselbe Zwischenablage** — kopieren in VS Code, einfügen in IntelliJ funktioniert
  ([Kapitel 4](04-zwischenablage.md))

Wer lieber einen vollständigen Desktop mit Fensterleiste möchte statt einzelner Vollbild-Apps,
findet ihn in der Leiste als eigenen Eintrag.

## Session-Ansicht

Die Kontrollleiste ist eingeklappt, damit die Anwendung den Platz bekommt. Geöffnet
wird sie über den **Griff am rechten Rand**.

> Das Tastenkürzel **Strg + Alt + Shift** wirkt nur, solange der Fokus *nicht* im
> Stream liegt. Sobald du in die Anwendung geklickt hast, beansprucht der ferne
> Desktop die Tastatur für sich — zu Recht, sonst könntest du dort keine
> Tastenkombination benutzen. Der Griff funktioniert immer.

Darin: der **Umschalter zwischen deinen Anwendungen**, das Zwischenablage-Panel,
Vollbild, Fokus zurücksetzen, neu verbinden und der Weg zurück zum Dashboard.

### Jede Anwendung in ihrem eigenen Tab ✅

Beim Öffnen aus dem Dashboard bekommt eine Anwendung einen eigenen Browsertab. Das Dashboard bleibt
im ersten Tab stehen — du wechselst zwischen deinen Anwendungen wie zwischen Fenstern auf dem
Desktop, statt jedes Mal die laufende Anwendung zu verlassen.

Jeder Tab hat eine eigene Adresse (`/view/s/…`). Ein Lesezeichen darauf führt zurück in dieselbe
Anwendung.

### Die Anwendung wächst mit dem Fenster ✅

Der ferne Bildschirm passt sich der Fenstergrösse an. Ziehst du das Browserfenster grösser, wird
auch der Arbeitsbereich der Anwendung grösser — es bleibt kein schwarzer Rand, und nichts wird
skaliert. Was du siehst, ist die echte Auflösung.

### Auf den Desktop legen ✅

Im Dashboard steht über den Kacheln der Abschnitt **Auf dem Desktop** mit dem Knopf **Verknüpfung
anlegen**. Darunter liegt jede Anwendung einzeln: Terminal, VS Code, Firefox, GIMP — und für
Vorlagen ohne Apps der ganze Arbeitsplatz. Ein Klick öffnet die Ablage-Seite dieser einen
Anwendung; dort legst du sie ab.

Danach hast du ein Symbol wie bei einem lokalen Programm. Ein Klick darauf öffnet **ein eigenes
Fenster ohne Adressleiste und ohne Tabs**, startet den Container, falls noch keiner läuft, und
öffnet die Anwendung darin. Bist du nicht angemeldet, kommt zuerst die Anmeldung — in demselben
Fenster, und danach geht es direkt weiter. Die Adresse bleibt dabei stehen; es wird nichts
umgeleitet.

**Warum eine eigene Seite und kein Knopf an Ort und Stelle:** Der Browser entscheidet über die
Ablage anhand des Manifests, das beim Laden im Dokument steht — was danach hineingetauscht wird,
ändert an seiner Entscheidung nichts mehr. Ein Knopf mitten im Viewer, der „diese Anwendung"
verspricht, legte in Wahrheit das Dashboard ab. Deshalb hat jede Anwendung ihre eigene Adresse,
deren Manifest von Anfang an sie meint: `/launch/<workspace>/<app>?ablegen`. Ohne `?ablegen` ist
dieselbe Adresse der Start — das ist die, auf die das Symbol zeigt.

Auf der Ablage-Seite wird **nichts gestartet**. Wer ein Symbol anlegt, will noch nicht arbeiten.

Bietet der Browser die Ablage nicht selbst an, steht dort der Weg über sein Menü: in Chrome und
Edge über das Symbol rechts in der Adressleiste, in Firefox über „Diese Seite installieren".

## Die gemeinsame Ablage ✅

In deinem Home liegt ein Ordner **Gemeinsam**. Darin steht, was die Administration für alle
bereitstellt — Zertifikate, Installationspakete, Vorlagen. Er ist **nur zum Lesen**: Kopiere heraus,
was du brauchst.

Derselbe Ordner ist auch unter `/mnt/ota` erreichbar, falls du ihn in einem Skript ansprichst.

## Was mit deiner Arbeit passiert

**Persistiert** wird dein Home-Verzeichnis — Projekte, Einstellungen, Extensions, Schlüssel. Es
überlebt Stopp, Neustart und **Updates des Golden Image**: Dein Home liegt auf dem Host und wird bei
jedem Start über das Image gelegt. Neue Software im Image ändert nichts an deinen Einstellungen.

**Nicht persistiert** wird alles außerhalb von `/home`: systemweit installierte Pakete, Änderungen an
`/etc`. Wer dauerhaft ein Systempaket braucht, wendet sich an den Administrator — es gehört ins
Golden Image ([Kapitel 7](07-golden-images.md)).

## Wer sonst noch auf deinen Bildschirm sehen kann

**Ein Administrator kann sich auf eine laufende Sitzung schalten** und sieht dann dasselbe wie du —
dein offenes Terminal, deinen entsperrten Passwortspeicher, deine Mail. Technisch lässt sich das
kaum verhindern: Wer die Maschine verwaltet, auf der dein Arbeitsplatz läuft, erreicht dasselbe
ohnehin über andere Wege.

Was OTA daraus macht:

* **Ein Supporter kann es nicht.** Das Recht *Alle Sessions sehen und beenden* reicht dafür
  ausdrücklich **nicht** aus — sehen, dass etwas läuft, und daran sitzen sind zwei verschiedene
  Dinge. Nur ein voller Administrator kommt heran.
* **Es steht im Protokoll.** Jedes Aufschalten erzeugt einen Eintrag mit Zeitpunkt, mit dem Namen
  dessen, der zusieht, und deinem. Nachlesbar unter **Betrieb → Protokoll**, dort als „Auf fremden
  Bildschirm geschaltet" — und damit überprüfbar, etwa gegen eine Betriebsvereinbarung. Der Eintrag
  bleibt ein Jahr stehen; die täglichen Anmelde- und Sitzungsdaten verfallen nach 90 Tagen.
* **Du merkst es heute nicht.** Ein Hinweis im Bild, solange jemand Fremdes zusieht, ist geplant
  und noch nicht gebaut. Bis dahin ist das Protokoll der Weg, es nachzusehen.

## Automatisches Abmelden ✅

Bleibt OTA eine Weile unbenutzt, wirst du abgemeldet und musst dich neu anmelden. Wie lange das
dauert, legt die Administration fest ([Kapitel 11](11-betrieb.md)); ab Werk sind es acht Stunden.

Die Frist zählt **Untätigkeit**, nicht Zeit: Solange du arbeitest, wird sie mit jeder Anfrage neu
gestartet. Mitten im Tippen abgemeldet zu werden kann also nicht passieren.

Davon unberührt läuft dein Container weiter — dafür gilt die eigene Frist im nächsten Abschnitt.

## Automatisches Beenden

Ohne Aktivität wird die Session nach einer eingestellten Zeit pausiert, gestoppt oder gelöscht. Was
gilt, steht auf der Karte. Zehn Minuten vorher erscheint ein Hinweis mit der Möglichkeit zu
verlängern, sofern die Richtlinie das zulässt.

**In allen drei Fällen bleibt dein Profil erhalten.** „Gelöscht" bezieht sich auf den Container,
nicht auf deine Dateien.

## Profil zurücksetzen

Unter *Einstellungen* gibt es **Profil zurücksetzen**. Das stellt den Auslieferungszustand des
Golden Image wieder her. Vorher wird automatisch gesichert — aber es ist ein Eingriff, kein
Aufräumknopf.
