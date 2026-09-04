# 8 · Nutzer, Gruppen und Rechte

> **Seit dem 2026-08-28 kommen die Konten aus Keycloak.** OTA führt sie weiter als Projektion —
> Gruppen, Rechte und Zuteilungen bleiben hier —, aber angelegt und geprüft werden sie dort.
> Wie das zusammenhängt und was der Notzugang ist, steht in
> [Kapitel 18](18-zentrale-anmeldung.md).
>
> **Die E-Mail ist Pflichtfeld.** Sie war es lange nicht; seit sie an angebundene Anwendungen
> weitergereicht wird, ist ein Konto ohne Adresse eines, das sich dort nicht anmelden kann. Interne
> Adressen (`chef@firma.local`) sind ausdrücklich erlaubt — OTA ist ein Werkzeug fürs interne Netz
> und setzt dort keine Internet-Regeln durch. Zwei Konten mit derselben Adresse gehen nicht:
> Angebundene Anwendungen erkennen Menschen daran wieder, und zwei wären dort ein Mensch.

*Für Administratoren.* AD-Anbindung ✅, Kerberos gestrichen

## Grundsatz

Die Nutzerverwaltung von OTA ist **eigenständig**. LDAP/AD und OIDC sind zuschaltbare Zusätze, keine
Voraussetzung. Es gibt keinen Zwang zu einem externen Identity-Provider.

## Rollen

Zwei Systemgruppen, nicht löschbar:

| Gruppe | Darf |
|---|---|
| **`admins`** | Alles: Workspaces, Golden Images, Nutzer, Gruppen, Zuweisungen, Registries, alle Sessions, Audit-Log, globale Einstellungen |
| **`users`** | Nur das Eigene: zugewiesene Workspaces starten, eigene Sessions verwalten, eigene Einstellungen |

Weitere Gruppen sind frei anlegbar und dienen der Zuweisung und den Ressourcen-Abweichungen
([Kapitel 6](06-ressourcen-und-zuteilung.md)).

Im Datenmodell existieren feingranulare Rechte (`images.manage`, `users.manage`, `sessions.view_all`,
`settings.manage`, `audit.view`), damit später Rollen wie „Support" (darf Sessions sehen, nichts
konfigurieren) ohne Schemaänderung möglich sind.

### Durchsetzung

An drei Stellen, nicht nur im Menü:

1. Route-Schutz im Frontend — Komfort
2. Prüfung an **jedem** API-Endpunkt — die Wahrheit
3. Abfrage-Beschränkung: Nicht-Admins bekommen ausschließlich die eigenen Datensätze; nicht „alles
   holen und im Frontend filtern"

## Administratoren sind root in ihrem Container ✅

Wer in OTA administriert, bekommt in **seinen eigenen** Session-Containern passwortloses `sudo`.
Ohne das liesse sich dort nichts nachinstallieren und nichts prüfen — und genau dafür meldet sich
ein Administrator ja an einem Arbeitsplatz an.

Technisch heisst das zweierlei: Der Container läuft ohne `no-new-privileges`, und ihm werden die
Linux-Fähigkeiten nicht entzogen. Beides ist nötig, damit `sudo` überhaupt anläuft. Für alle
anderen Nutzer bleibt beides scharf.

**Was das bedeutet, in aller Deutlichkeit:** Root in einem Container ist nicht Root auf dem Host,
aber der Abstand dazwischen ist kleiner als bei einem unprivilegierten Container. Diese Rechte
gehören deshalb an dieselbe wenige Personen wie der Zugang zum Docker-Host — nicht an „alle, die
mal etwas verwalten müssen". Wer Nutzer nur anlegen und Workspaces pflegen soll, bekommt dafür die
einzelnen Rechte (*Nutzer anlegen und ändern*, *Workspaces anlegen und ändern*) statt
*Vollzugriff auf alles*.

Änderungen an `/etc` und nachinstallierte Pakete überleben den Container nicht — sie liegen
ausserhalb von `/home`. Was dauerhaft dabei sein soll, gehört ins Golden Image
([Kapitel 7](07-golden-images.md)).

## Was ein Recht bedeutet — und was nicht

*Alle Sessions sehen und beenden* (`sessions.view_all`) heisst genau das: In der Verwaltung stehen
alle laufenden Sessions, und sie lassen sich beenden. Es heisst **nicht**, dass man sich auf einen
fremden Bildschirm schalten kann.

Bis zum 2026-08-27 tat es das doch. Die Prüfung vor jedem Aufruf von `/s/<id>/` benutzte dieselbe
Funktion wie die Liste, und damit reichte das Recht bis auf den laufenden Bildschirm eines anderen
Menschen — mit seinem offenen Terminal und seinem entsperrten Passwortspeicher. Zwischen „sehen,
dass etwas läuft" und „daran sitzen" liegt der ganze Unterschied.

Auf einen fremden Bildschirm kommt jetzt nur ein **voller Administrator**, und der sitzt ohnehin am
Docker-Host und erreicht dort dasselbe. Eine Fernhilfe mit ausdrücklicher Einwilligung des Nutzers
wäre der richtige Weg dafür; die gibt es noch nicht.

## Passwörter und Anmeldung

- **Argon2id**, Mindestlänge 12, Abgleich gegen bekannt kompromittierte Passwörter
- Sitzung über `HttpOnly`/`Secure`/`SameSite`-Cookie, kurze Gültigkeit, Erneuerung mit Rotation
- Bei Fehlversuchen exponentiell steigende Wartezeit je Konto und IP, Sperre nach N Versuchen
- Alles im Audit-Log

## Mein Konto ✅

Jeder Angemeldete verwaltet sein eigenes Konto unter **Mein Konto** (unten in der Leiste). Das
braucht keine Verwaltungsrechte — es geht um die eigene Person.

| Reiter | Was dort geht |
|---|---|
| **Passwort** | Selbst ändern. Der Wechsel meldet alle *anderen* Sitzungen ab, die eigene bleibt |
| **Zwei-Faktor** | Einrichten, Rückfallcodes erneuern, abschalten |
| **Sprache** | Deutsch oder Englisch, am Konto gemerkt statt nur im Browser |

Daneben, unten in der Leiste und **auch schon auf der Anmeldemaske**: die Sprache und das
**Gewand** — dunkel, hell oder „wie der Rechner". Beide liegen im Browser und nicht am Konto: Sie
sind eine Frage des Arbeitsplatzes, nicht der Identität. Dieselbe Person am hellen Bildschirm im
Büro und am dunklen zu Hause soll dafür nicht ihr Konto umstellen müssen.

„Wie der Rechner" ist die Vorgabe und folgt dem Betriebssystem, auch wenn es abends von selbst
umschaltet. Wer sich festlegt, überschreibt das dauerhaft.

> Eine Auflösung lässt sich nicht einstellen, und das ist kein Versehen: Der ferne Bildschirm folgt
> der Grösse des Browserfensters ([Kapitel 3](03-arbeitsplatz.md)).

## Zwei-Faktor ✅

**Mein Konto → Zwei-Faktor.** Einrichten mit einer Authenticator-App: Code abscannen, sechs Ziffern
zur Probe eintippen, fertig. Wer nicht scannen kann, trägt das Geheimnis von Hand ein — es steht
daneben.

Gespeichert wird erst, wenn die Probe besteht. Sonst schaltete man sich mit einem Tippfehler aus.

### Rückfallcodes

Bei der Einrichtung entstehen **zehn Codes**. Sie erscheinen genau einmal; danach liegen sie nur
noch gehasht auf dem Server, wie Passwörter. **Jeder gilt einmal** und wird beim Einlösen entfernt.

Sie sind kein Zubehör, sondern die Antwort auf ein verlorenes Telefon. Die Alternative wäre „ein
Administrator schaltet den zweiten Faktor ab" — und genau das wäre die Hintertür, die er verhindern
soll. **In OTA kann niemand den zweiten Faktor eines anderen entfernen.**

Bei der Anmeldung wird ein Rückfallcode einfach statt der sechs Ziffern eingetippt.

Gehen sie zur Neige, erzeugt *Codes erneuern* zehn neue; die alten gelten dann nicht mehr.

### Wenn Telefon und Rückfallcodes weg sind ✅

Dann kommt der Mensch nicht mehr herein — und niemand könnte helfen. Deshalb kann ein Administrator
im Nutzer-Editor unter **Zweiter Faktor** auf *„Zweiten Faktor abnehmen"* klicken. Danach genügt
wieder das Passwort, und der Nutzer richtet den Faktor neu ein.

**Das ist eine bewusste Schwächung, und sie steht so im Protokoll.** Wer Konten verwaltet, kann
damit den zweiten Faktor eines anderen aushebeln. Die Alternative — niemand kann helfen — ist
schlechter: Sie führt in der Praxis dazu, dass niemand den zweiten Faktor einschaltet.

Zwei Dinge machen es nachvollziehbar:

- **Alle Sitzungen des Kontos werden beendet.** Wer den zweiten Faktor verloren hat, hat vielleicht
  mehr verloren.
- Der Vorgang steht mit **Namen des Administrators** im Audit-Log.

### Abschalten

Verlangt **Passwort und einen gültigen Code**. Wer nur das Passwort hat — etwa an einem
unbeaufsichtigten Rechner —, soll den zweiten Faktor nicht entfernen können; sonst wäre er keiner.

### Was noch fehlt

**Raten wird gesperrt.** Acht Fehlversuche sperren das Konto für 15 Minuten. Seit dem 2026-08-27
zählen Fehlversuche beim **zweiten Faktor** genauso mit — vorher taten sie es nicht, und damit war
der zweite Faktor bei bekanntem Passwort beliebig oft ratbar: sechs Ziffern, davon drei zu jedem
Zeitpunkt gültig. Dasselbe galt für die Rückfallcodes.

### Zwang je Gruppe ✅

Im Gruppen-Editor steht **„Zweiter Faktor ist Pflicht"**. Ist er an, gilt für jedes Mitglied:

- **Die Anmeldung bleibt möglich.** Wer sich nicht anmelden kann, kommt nicht an *Mein Konto* und
  kann den zweiten Faktor gar nicht erst einrichten — eine Sperre an der Anmeldung wäre eine Sperre
  gegen ihre eigene Auflösung.
- **Es startet kein Arbeitsplatz.** Der Versuch endet mit dem Hinweis, den Faktor einzurichten.
- Im Dashboard steht ein Streifen mit einer Schaltfläche, die direkt zur Einrichtung führt.

Der Zwang lässt sich auch für die Systemgruppen setzen — gerade für sie: *„admins muss
Zwei-Faktor haben"* ist der häufigste Wunsch.

WebAuthn und Passkeys stehen ✅ zur Verfügung — als zweiter Faktor neben dem Einmalkennwort,
nicht als Ersatz für das Passwort.

## Active Directory und LDAP ✅

**Ein Weg, nicht zwei.** Ein Verzeichnis wird in **Keycloak** angebunden — dort liegt die
Anmeldung, dort werden die Konten geführt, und OTA übernimmt sie und ordnet ihre Gruppen zu.
Eingerichtet wird das aus OTAs Oberfläche heraus: **Verwaltung → Einstellungen → Anmeldung und
Verzeichnis**. Die Keycloak-Konsole braucht man dafür nicht.

Wie das im Einzelnen geht, steht in [Kapitel 18](18-zentrale-anmeldung.md#ein-active-directory-anbinden).

> **Bis zum 2026-09-04 gab es einen zweiten Weg:** OTA sprach selbst LDAP — eigene Anbindung,
> eigener nächtlicher Abgleich, eigene Anmeldung. Er ist entfallen. Zwei Wege zu derselben Sache
> waren einer zu viel, und der alte war der, den niemand mehr gepflegt hat
> (`auth-roadmap.md`, Entscheidung 4).

### Die Regel, die über allem steht

> **Ein lokales Konto wird niemals über das Verzeichnis angemeldet, und ein Verzeichniseintrag kann
> ein lokales Konto niemals übernehmen.**

Wo ein Passwort geprüft wird, entscheidet allein das Konto selbst (`auth_provider`) — nicht die
Anfrage und nicht das Verzeichnis. Dieser Wert ändert sich nie von selbst.

Der Angriff, gegen den das steht, ist unspektakulär und deshalb leicht zu übersehen: Wer im
Verzeichnis einen Eintrag anlegen darf, legt einen mit dem Namen des ersten Administrators an und
meldet sich mit seinem eigenen Passwort als dieser an. Ohne diese Regel funktioniert das.

Das Testverzeichnis (`scripts/ldap-test-server.sh`) enthält deshalb absichtlich einen Eintrag mit
dem Namen eines bestehenden lokalen Kontos und einem anderen Passwort. Die Prüfung besteht darin,
dass er **nicht** hereinkommt — weder bei OTA noch bei Keycloak.

### Selbst ausprobieren

```bash
scripts/ldap-test-server.sh start     # OpenLDAP mit vier Einträgen
scripts/test-ldap.sh                  # die ganze Reihe, von Anbinden bis Ausfall
scripts/ldap-test-server.sh stop
```

Der Testserver gehört **nicht** zum Stack: Ein Verzeichnisdienst, der beim `make up` mitstartet,
wäre eine Einladung, gegen ihn zu produzieren.

### Was nicht kommt

**Kerberos und Netzlaufwerke** (`sec=krb5`, `k5start`, UID/GID aus dem Verzeichnis) sind **am
2026-09-03 gestrichen**. Dafür reicht ein LDAP-Server nicht — es bräuchte ein echtes AD mit KDC
und Dateiservern, und ohne eines liesse sich nichts davon ehrlich prüfen. Wer im Arbeitsplatz ein
Netzlaufwerk braucht, verbindet es dort selbst (Weg 3 unten).

**Die Passwort-Durchreichung bleibt draußen.** Sie wäre der kürzeste Weg zu eingehängten
Laufwerken und der einzige, bei dem OTA das Anmeldepasswort eines Menschen aufbewahren müsste
(`plan.md` §17.9).

## Netzlaufwerke im Arbeitsplatz — gestrichen

**Gestrichen am 2026-09-03.** OTA reicht keine Anmeldedaten an Dateiserver weiter und wird das
nicht tun. Wer im Arbeitsplatz ein Netzlaufwerk braucht, verbindet es dort selbst — das ist Weg 3
in der folgenden Tabelle, und er braucht von OTA nichts.

Die Abwägung bleibt hier stehen, weil sie erklärt, **warum** Weg 4 draußen bleibt — diese
Entscheidung gilt unabhängig davon, ob Kerberos je gebaut wird. Vier Wege, geordnet nach
Sauberkeit:

| Weg | Was passiert | Bewertung |
|---|---|---|
| **1 · Kerberos-SSO mit Delegation** | Browser meldet sich per Negotiate an, OTA holt per eingeschränkter Delegation ein Ticket für den Fileserver | Sauberste Lösung. **Ein Passwort erreicht OTA nie.** Verlangt SPNs und konfigurierte Delegation |
| **2 · Kerberos-Ticket-Injektion** | OTA prüft gegen AD, holt dabei ein Ticket und legt es in den Container. Mount per `sec=krb5` | **Standardweg.** Kein Passwort im Container, Ticket läuft nach ~10 h ab |
| **3 · Nutzer verbindet selbst** | Knopf im Container, Passworteingabe dort | **Immer verfügbar.** Null Risiko für die Plattform |
| **4 · Passwort-Durchreichung** | OTA hält das Passwort für die Sitzungsdauer | **Standardmäßig aus.** Macht OTA zum Passwortspeicher |

**Weg 4 ist bewusst nicht die Voreinstellung.** Er ist bequem, aber er vergrößert den Schadensradius
erheblich: Wer OTA kompromittiert, bekommt Passwörter statt nur Sitzungen. Wer ihn einschalten will,
sieht im Admin-UI einen unmissverständlichen Hinweis.

**Wenn jemals wieder jemand daran denkt, gilt unabhängig vom Weg:**
- Zugangsdaten niemals als Umgebungsvariable — über `docker inspect` lesbar und in Logs sichtbar
- Niemals ins Golden Image und nie ins persistente Profil
- Ablage in einer `tmpfs`-Datei mit `0600`, die nie auf Platte geht
- Damit Dateirechte auf den Shares stimmen, wird die UID/GID aus dem Verzeichnis übernommen

## Offboarding

Beim Ausscheiden: Konto deaktivieren, Sessions beenden, Profil archivieren, dann löschen. Profile
enthalten personenbezogene Daten (SSH-Schlüssel, Browser-Verlauf) und unterliegen der DSGVO.

## Audit-Log

Erfasst Anmeldungen, Session-Start und -Ende sowie alle administrativen Änderungen — **keine
Inhalte**. Aufbewahrung konfigurierbar, Vorgabe 90 Tage, CSV-Export.

Session-Recording und Tastaturprotokollierung sind **bewusst nicht implementiert**. Falls später
gewünscht: vorher Mitbestimmung und Zweckbindung klären.
