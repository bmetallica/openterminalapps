# 42 · Datenschutz: die Seite für Datenschutzbeauftragte ✅

*Seit 2026-11-27.* Dieses Kapitel ist für Datenschutzbeauftragte geschrieben und setzt kein
IT-Wissen voraus. Für die Verwaltung steht am Ende, wie die Gruppe eingerichtet wird.

## Worum es geht

Datenschutzbeauftragte müssen prüfen können, welche Daten über Menschen anfallen, wer darauf
zugreifen darf und wer tatsächlich zugegriffen hat. Dafür brauchen sie keine
Verwaltungsrechte. Sie sollen sie auch nicht haben: Sie kontrollieren die Verwaltung und sind
nicht Teil von ihr.

OTA hat dafür eine eigene Gruppe **datenschutz** und im Menü links den Punkt **Datenschutz**
(Symbol ⚖). Wer in der Gruppe ist, sieht dort alles, was für die Prüfung nötig ist, und kann
nichts an der Anlage verändern. Es gibt nur zwei Ausnahmen:

- eine **Auskunft nach Art. 15 DSGVO** erstellen;
- den **Datenschutzhinweis** bearbeiten, den alle unter „DSGVO“ lesen.

## Die fünf Bereiche der Seite

### Überblick

Jede Verarbeitung, die OTA kennt, als Karte: was sie bedeutet, ob sie eingeschaltet ist und wie
lange die Daten aufbewahrt werden. Dazu gehören:

| Karte | Was dahinter steckt |
|---|---|
| Prüfprotokoll | wer wann was in der Verwaltung getan hat, Anmeldungen, Starts von Arbeitsplätzen; zwei Löschfristen |
| Kopie des Prüfprotokolls auf einem zentralen Server | ob eine zweite, von OTA unabhängige Kopie besteht (Syslog) |
| Statistik über die Nutzung der KI | Anfragen an die KI je Person, ohne Inhalt, mit Fristen |
| Angebundene KI-Programme | z. B. Open WebUI, das Namen oder E-Mail-Adresse an OTA übermittelt |
| Schutz der KI vor Angriffen | zählt verdächtige Texte, ohne Personenbezug |
| Fallberichte zur KI-Sicherheit | kurze Ausschnitte auffälliger Texte, ohne Person, mit Frist |
| Prüfung auf Passwörter im Programmcode | zählt Funde in OTA-Git, ohne Personenbezug |
| Dateien gelöschter Konten | ob und wann sie entfernt werden |
| Sicherungen | wie lange Kopien aufbewahrt werden; Gelöschtes steckt bis dahin noch darin |
| Datenschutzhinweis | eigener Text oder Standardtext, wann und von wem zuletzt geändert |
| Erweiterungen | Zusatzdienste wie ein Gedächtnis für den KI-Assistenten, und für welche Gruppen |

Oben stehen unter **Zur Beachtung** Punkte, die offen sind, zum Beispiel:

- „Der Datenschutzhinweis ist noch der mitgelieferte Standardtext“;
- „Das Prüfprotokoll liegt nur in OTA selbst“;
- „Die Dateien gelöschter Konten werden nicht automatisch entfernt“.

Diese Liste ist ein guter Ausgangspunkt für das Verzeichnis von Verarbeitungstätigkeiten.

### Wer darf was

Welche Gruppen weitreichende Rechte haben, was diese Rechte in Worten bedeuten und wer
Mitglied ist. Oben steht, wie viele aktive Konten jedes Recht haben. Gemeint sind Rechte wie
„Vollzugriff auf alles“, „Befehle in Arbeitsplätzen anderer ausführen und dort alle Dateien
lesen“ oder „Konten anlegen, ändern und sperren“. Rechte ohne Bezug zum Datenschutz, etwa das
Bauen von Images, fehlen hier.

Gruppen ohne ein solches Recht, zum Beispiel die Gruppe aller Nutzer, erscheinen nicht.

### Zugriffe

Die Einträge im Prüfprotokoll, die für den Datenschutz zählen, in vier Arten:

| Art | Beispiele |
|---|---|
| Einsicht in Daten anderer | auf einen Bildschirm aufgeschaltet; Terminal in einem fremden Arbeitsplatz geöffnet; KI-Nutzung eines Menschen angesehen; Fallbericht geöffnet; Auskunft erstellt; Prüfprotokoll exportiert |
| Konten gesperrt oder gelöscht | Konto gesperrt, gelöscht; Dateien eines Kontos entfernt |
| Rechte vergeben | Gruppen angelegt oder geändert; Gruppen aus dem Verzeichnis zugeordnet |
| Datenschutz-Einstellungen | Statistik ein- oder ausgeschaltet; Fristen geändert; Datenschutzhinweis geändert |

Ist eine **Begründung** dabei, steht sie in der Spalte „Einzelheiten“, ebenso das betroffene
Konto. Das gilt etwa für die Einsicht in die KI-Nutzung eines Menschen oder das Öffnen eines
Fallberichts. Ein Klick auf eine Zeile zeigt alle gespeicherten Angaben.

Den **Inhalt** der Fallberichte und die KI-Nutzung einzelner Menschen zeigt diese Seite bewusst
nicht. Für die Kontrolle reicht es zu sehen, wer sie mit welcher Begründung geöffnet hat.

### Prüfprotokoll

Das vollständige Prüfprotokoll, mit diesen Filtern:

- Zeitraum;
- wer gehandelt hat;
- **betroffene Person:** findet alles, was sie selbst getan hat, und alles, was ihr Konto betraf.

Jeweils 100 Einträge je Seite. **Als Tabelle herunterladen (CSV)** liefert die gefilterten
Einträge, höchstens 50 000, als Datei für Excel.

### Auskunft

Die Auskunft nach Art. 15 DSGVO:

1. Person suchen, nach Name, Konto oder E-Mail-Adresse.
2. Eine **Begründung** eintragen, mindestens zehn Zeichen, zum Beispiel Aktenzeichen und
   Datum des Antrags.
3. **Auskunft erstellen und herunterladen.**

Das Ergebnis ist eine ZIP-Datei mit allem, was OTA über den Menschen gespeichert hat:

- Stammdaten und Gruppen;
- Einträge im Prüfprotokoll;
- Arbeitszeiten an Arbeitsplätzen;
- KI-Nutzung;
- Sicherungen;
- OTA-Git;
- eine Liste der eigenen Dateien, ohne deren Inhalt.

Passwörter und Schlüssel sind nicht enthalten. Die Datei `liesmich.txt` darin erklärt jeden Teil.

**Vor dem Herausgeben** ist abzuwägen, ob Namen von Verwaltern geschwärzt werden müssen. Das
Prüfprotokoll in der Auskunft nennt auch sie (Art. 15 Abs. 4 DSGVO).

Die Begründung ist Pflicht. Das gilt seit 2026-11-27 auch für die Verwaltung (*Nutzer → Konto
→ Auskunft erstellen*).

## Was selbst im Prüfprotokoll steht

Auch die Arbeit der Datenschutzbeauftragten ist nachvollziehbar, für die Verwaltung wie für
andere Datenschutzbeauftragte:

| Eintrag | Wann |
|---|---|
| `user.auskunft` | Auskunft erstellt, mit Begründung |
| `datenschutz.protokoll_exportiert` | Prüfprotokoll als CSV heruntergeladen, mit den Filtern |
| `datenschutz.protokoll_person` | Prüfprotokoll nach einer Person gefiltert (einmal je zehn Minuten und Person) |
| `dsgvo.hinweis_geaendert` | Datenschutzhinweis geändert |

Das bloße Ansehen von Überblick, Rechten und Zugriffen wird nicht protokolliert. Dabei geht es
um keine bestimmte Person.

## Handbuch

Mitglieder der Gruppe sehen unter **Hilfe** außer den Kapiteln für alle auch die Kapitel, in
denen steht, was OTA über Menschen erfasst:

- 08 · Nutzer und Gruppen;
- 11 · Betrieb (Prüfprotokoll und Fristen);
- 27 · OTA-Git;
- 28 · IDE-AI und KI-Nutzung;
- 39 · Erweiterungen;
- 41 · KI-Sicherheit.

## Für die Verwaltung: einrichten

1. Die Gruppe **datenschutz** legt OTA beim Start selbst an, mit genau einem Recht:
   `datenschutz.pruefen`. Sie ist fest eingebaut. Ihre Rechte stellt OTA bei jedem Start
   wieder her, falls sie jemand verändert hat.
2. Das Konto der/des Datenschutzbeauftragten unter *Nutzer* der Gruppe **datenschutz**
   zuordnen. Bei Anmeldung über ein Verzeichnis (LDAP, Active Directory) genügt eine
   gleichnamige Gruppe dort, siehe [Kapitel 08](08-nutzer-und-gruppen.md).
3. Das Konto braucht **keine** weitere Gruppe außer der für alle Nutzer. Insbesondere nicht
   `admins`: Wer in der Verwaltung ist, kontrolliert sich sonst selbst.

Das Recht `datenschutz.pruefen` lässt sich auch einer eigenen Gruppe geben. Administratoren
sehen die Seite ohnehin, weil `admin` alle Rechte einschließt.

**Was die Gruppe nicht darf:** Einstellungen ändern, Konten oder Gruppen verwalten, sich auf
Arbeitsplätze aufschalten, Terminals öffnen, die KI-Nutzung einzelner Menschen sehen,
Fallberichte öffnen. Die Prüfreihe `scripts/test-datenschutz.sh` prüft das.

## Technik

- API: `/api/datenschutz/lage`, `/rechte`, `/protokoll`, `/protokoll.csv`, `/personen`,
  `/auskunft/{id}` (`api/ota/datenschutz.py`, `api/ota/routers/datenschutz.py`).
- Oberfläche: `web/src/screens/Datenschutz.tsx`.
- Die Einträge stehen in der langen Frist des Prüfprotokolls ([Kapitel 11](11-betrieb.md)).
