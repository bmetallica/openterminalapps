# Datenschutz — Betrachtung nach DSGVO und BDSG

**Stand: 2026-09-04**, Commit `99e9400`, betrachtet an der laufenden Anlage.

Diese Betrachtung ist **keine Rechtsberatung.** Sie ist eine technische Bestandsaufnahme durch den,
der die Software gebaut hat: Sie sagt, **welche personenbezogenen Daten wo liegen, wie lange, wer
sie sieht und was davon fehlt.** Die Bewertung, ob das im konkreten Unternehmen genügt, gehört zum
Datenschutzbeauftragten — und die Punkte, bei denen ich mir sicher bin, dass sie ihn interessieren,
sind ausdrücklich als solche gekennzeichnet.

Die technische Seite steht daneben in [`security.md`](security.md); beide Dokumente verweisen
aufeinander, statt sich zu wiederholen.

---

## 1 · Wer ist wofür verantwortlich

OTA ist **selbst gehostete Software**. Es gibt keinen Anbieter, der Daten verarbeitet, und damit
für OTA selbst **keinen Auftragsverarbeitungsvertrag** (Art. 28) — es gibt niemanden, mit dem man
ihn schliessen könnte. **Verantwortlicher im Sinne von Art. 4 Nr. 7 ist das Unternehmen, das die
Anlage betreibt.**

Zwei Einschränkungen dazu:

* **Der Zeichensatz kommt von Google** (siehe Abschnitt 7). Das ist der einzige Datenfluss aus der
  Anlage heraus — und ausgerechnet einer in ein Drittland.
* **Container-Images werden aus fremden Registries geholt** (Docker Hub, Kasm). Dabei fliessen
  keine personenbezogenen Daten heraus; es fliesst nur die Information, dass diese Anlage ein
  bestimmtes Image lädt. Kein Auftragsverarbeitungsverhältnis, aber ein Punkt für das
  Verzeichnis.

---

## 2 · Welche personenbezogenen Daten anfallen

Das ist der Kern. Erhoben an der laufenden Anlage — die Zahlen sind der Stand von heute.

### 2.1 Stammdaten der Konten

| Feld | Wo | Bemerkung |
|---|---|---|
| Anmeldename, Anzeigename, E-Mail | `users` (PostgreSQL) **und** Keycloak | E-Mail ist Pflicht, seit sie an angebundene Anwendungen weitergereicht wird |
| Passwort-Hash (Argon2) | `users.password_hash` | nur für lokale Konten; der Regelweg läuft über Keycloak |
| TOTP-Startwert, Rückfallcodes | `users.totp_secret` (**Klartext**), `users.totp_recovery` (gehasht) | siehe [`security.md` M2](security.md#m2) |
| Sprache, Gewand | `users.locale`, `users.theme` | keine besondere Kategorie |
| Gruppenzugehörigkeit | `group_members` | daraus folgen die Rechte |
| Fehlversuche, Sperre bis, letzte Anmeldung | `users.failed_logins`, `locked_until`, `last_login_at` | |

**Stand heute:** 5 Konten, davon 3 Prüfkonten (`notfall`, `kc-pruef`, `ota-testnutzer`).

### 2.2 Nutzungs- und Verhaltensdaten

Das ist der datenschutzrechtlich empfindliche Teil, und er ist grösser, als es auf den ersten
Blick aussieht.

| Datum | Wo | Umfang heute |
|---|---|---|
| Jede Anmeldung, auch jede fehlgeschlagene, **mit IP-Adresse** | `audit_log` | 9.608 Einträge seit 2026-08-26, davon 1.543 `login.ok`, 460 `login.failed` |
| Jeder Sitzungsstart und -stopp, mit Zeitpunkt und Vorlage | `audit_log`, `sessions` | 518 Sitzungen |
| **Welche Anwendung wann gestartet wurde** | `audit_log` (`app.started`), `app_streams` | 449 Einträge, 275 Ströme |
| Verwaltungsvorgänge (wer hat was geändert) | `audit_log` | |
| Fehlerantworten des Reverse Proxy, mit IP | Traefik-Zugriffsprotokoll (nur 4xx/5xx) | unbegrenzt, siehe [N3](security.md#n3) |

**Aus diesen Daten lässt sich ein Arbeitszeitprofil ablesen** — wann jemand anfängt, wann er
aufhört, wie lange er womit arbeitet. Dass es nicht dafür gedacht ist, ändert daran nichts.
👉 **Das ist der Punkt für den Datenschutzbeauftragten und den Betriebsrat** (Abschnitt 6).

### 2.3 Inhaltsdaten — das Zuhause

Jeder Mensch hat ein persistentes Zuhause unter `/srv/ota/profiles/<konto-id>/user`. Darin liegt
**alles, was er in seinem Arbeitsplatz tut**: Dokumente, Downloads, Browser-Profile samt Verlauf
und Anmeldedaten, SSH- und GPG-Schlüssel, Konfigurationen, E-Mail-Postfächer, Zwischenstände.

**Gemessen:** vier Zuhause, zusammen rund 1,3 GB, das grösste 776 MB.

Dazu die Ablagen:

* `/srv/ota/userfiles/<konto-id>` — die eigene Ablage
* `/srv/ota/groupfiles/<gruppen-id>` — Gruppenlaufwerke, sichtbar für alle Mitglieder
* `/srv/ota/shared` — die gemeinsame Ablage, für alle lesbar

**Die Zwischenablage** wird zwischen den Bildschirmen eines Arbeitsplatzes gespiegelt, liegt dabei
aber ausschliesslich **im Container** (`/tmp/ota-clipboard-state`) und wird nirgends zentral
gespeichert. Das ist gut gelöst und bleibt so.

### 2.4 Sicherungen

`/srv/ota/backups`, heute **1,8 GB**: Datenbankabzüge, Zuhause-Archive, Container-Sicherungen. Eine
Sicherung enthält damit **eine vollständige Kopie von allem oben** — einschliesslich Passwort-Hashes,
TOTP-Startwerten und dem AD-Kennwort des Dienstkontos.

Aufbewahrung: `keep_daily` und `keep_weekly` je Nutzer und Art, einstellbar. **Das ist die einzige
Stelle in der ganzen Anlage, an der Daten automatisch verschwinden.**

### 2.5 Golden Images

Wer einen Container einfriert, erzeugt ein Image. Das Zuhause ist dabei ausgenommen, aber alles
ausserhalb wandert mit. Der Vorgang zeigt vorher an, was nach einem Geheimnis aussieht
([N5](security.md#n5)) — **er verlässt sich darauf, dass jemand die Liste liest.** Ein Image, das
später weitergegeben wird, kann personenbezogene Daten enthalten.

### 2.6 Was **nicht** anfällt

Ehrlichkeitshalber, denn es spricht für die Anlage:

* **Keine Inhaltsprotokollierung.** Das Protokoll hält Vorgänge fest, nie Inhalte
  (`audit.py`: „Inhalte werden nie erfasst, nur Vorgänge").
* **Keine Tastatur- oder Bildschirmaufzeichnung.** Nichts im Code nimmt einen Bildschirm auf.
* **Keine Telemetrie nach aussen**, mit der einen Ausnahme aus Abschnitt 7.
* **Keine Namen in den Kennzahlen.** `/metrics` liefert Summen, keine Personen.
* **Keycloaks Ereignisprotokoll ist aus** (`eventsEnabled: false`) — dort wächst also keine zweite
  Protokollspur.
* Im Browser liegen nur `ota.theme`, `ota.lang` und `ota.marke` — Gewand, Sprache, Marke. Keine
  personenbezogenen Daten.

---

## 3 · Rechtsgrundlagen

Für den Betrieb in einem Unternehmen mit Beschäftigten:

| Verarbeitung | Grundlage |
|---|---|
| Konten, Gruppen, Arbeitsplätze, Zuhause | **§ 26 Abs. 1 BDSG** / Art. 6 Abs. 1 lit. b — Durchführung des Beschäftigungsverhältnisses. Ohne Konto kein Arbeitsplatz. |
| Protokoll über Anmeldungen und Sitzungen | Art. 6 Abs. 1 lit. f — berechtigtes Interesse an Nachvollziehbarkeit und IT-Sicherheit. **Die Interessenabwägung gehört dokumentiert**, gerade weil sich daraus ein Arbeitszeitprofil ergibt. |
| Sicherungen | Art. 6 Abs. 1 lit. f, mittelbar auch Art. 32 Abs. 1 lit. c — Wiederherstellbarkeit ist selbst eine Pflicht. |
| Verzeichnisanbindung (AD/LDAP) | § 26 BDSG — dieselbe Grundlage wie die Kontoführung. |

**Einwilligung ist hier der falsche Weg.** Im Beschäftigungsverhältnis gilt sie wegen des
Abhängigkeitsverhältnisses als selten freiwillig (§ 26 Abs. 2 BDSG). Wer die Protokollierung auf
eine Einwilligung stützt, hat sie beim ersten Widerruf nicht mehr.

---

## 4 · Aufbewahrung und Löschung — die grösste Lücke

**Art. 5 Abs. 1 lit. e verlangt, dass Daten nicht länger als nötig aufbewahrt werden. OTA hat
dafür heute nur einen einzigen Mechanismus** — die Aufbewahrungsregel der Sicherungen.

| Datum | Löscht sich heute | Was fehlt |
|---|---|---|
| `audit_log` | **nie** | eine Frist. 9.608 Einträge seit dem ersten Tag, mit IP-Adressen. |
| `sessions`, `app_streams` | mit dem Konto (Kaskade) | eine Frist unabhängig vom Konto. |
| Zuhause auf der Platte | **nie**, auch nicht beim Löschen des Kontos | siehe unten. |
| Sicherungen | ✅ `keep_daily` / `keep_weekly` | — |
| Container-Protokolle (Docker) | **nie** (`json-file` ohne Grenze) | Rotation, [N3](security.md#n3). |
| Konto in Keycloak | wird beim Löschen in OTA **nicht** entfernt | siehe unten. |

### 4.1 Was beim Löschen eines Kontos wirklich passiert

Gemessen im Quelltext (`api/ota/routers/admin.py`) — die API sagt es selbst:

> `{"status": "… gelöscht. Das Profil auf der Platte bleibt bestehen."}`

Es verschwinden: der Datensatz in `users`, die Gruppenmitgliedschaften, die Sitzungshistorie
(Kaskade). Es bleiben:

1. **Das Zuhause** unter `/srv/ota/profiles/<konto-id>/user` — mit allem darin.
2. **Die Ablagen** unter `userfiles/` und was in `groupfiles/` und `shared/` liegt.
3. **Die Sicherungen** — bis die Aufbewahrungsregel greift.
4. **Das Protokoll**: `actor_user_id` wird auf `NULL` gesetzt, **`actor_name` bleibt stehen**.
   Der Name steht damit weiter im Protokoll.
5. **Das Konto in Keycloak**, samt Anmeldedaten.

👉 **Ein Löschersuchen nach Art. 17 lässt sich heute nicht mit einem Knopf erfüllen.** Es braucht
fünf Schritte an fünf Stellen, und es gibt keine Anleitung dafür. Das ist die dringendste Lücke
dieses Dokuments.

Dass `actor_name` im Protokoll stehen bleibt, ist **verteidigbar** (Art. 17 Abs. 3 lit. b/e:
Nachweispflichten, Rechtsansprüche) — aber nur mit einer dokumentierten Frist. Ohne Frist ist es
keine Aufbewahrung, sondern ein Versäumnis.

### 4.2 Vorschlag für ein Löschkonzept

Zahlen als Ausgangspunkt für die Abstimmung, nicht als Vorgabe:

| Datum | Frist | Umsetzung |
|---|---|---|
| `audit_log`: Anmeldungen, Sitzungen | **90 Tage** | nächtlicher Auftrag; die Sicherungsroutine gibt es schon, das Muster ist da |
| `audit_log`: Verwaltungsvorgänge | **1 Jahr** | Nachvollziehbarkeit von Rechteänderungen |
| Traefik-Zugriffsprotokoll, Container-Protokolle | **14 Tage** | `max-size`/`max-file` je Dienst |
| Zuhause nach Ausscheiden | **30 Tage archiviert, dann gelöscht** | heute Handarbeit; gehört als „Konto endgültig entfernen" in die Oberfläche |
| Sicherungen | wie eingestellt | ✅ vorhanden |
| Keycloak-Konto | mit dem OTA-Konto | Aufruf beim Löschen ergänzen |

---

## 5 · Rechte der betroffenen Personen

| Recht | Heute machbar? |
|---|---|
| **Auskunft** (Art. 15) | Nur von Hand: Datenbankabfrage über fünf Tabellen plus das Zuhause. Es gibt keine Auskunftsfunktion. |
| **Berichtigung** (Art. 16) | ✅ Name und E-Mail über die Verwaltung; bei Keycloak-Konten dort. |
| **Löschung** (Art. 17) | ⚠️ Nur teilweise, siehe 4.1. |
| **Einschränkung** (Art. 18) | Teilweise: Ein Konto lässt sich deaktivieren (`is_active`), die Daten bleiben unberührt. |
| **Datenübertragbarkeit** (Art. 20) | ✅ Faktisch: `make backup` erzeugt ein Archiv des Zuhause. Als bewusste Funktion für den Betroffenen gedacht ist es nicht. |
| **Widerspruch** (Art. 21) | Gegen die Protokollierung praktisch nicht durchsetzbar, solange sie auf lit. f gestützt ist — hier hilft nur eine saubere Abwägung und eine kurze Frist. |
| **Information** (Art. 13) | ❌ **Es gibt keinen Datenschutzhinweis in der Anwendung.** Niemand erfährt beim Anmelden, was protokolliert wird. |

👉 Zwei konkrete, kleine Schritte mit grosser Wirkung: ein **Datenschutzhinweis** als eigenes
Kapitel im Handbuch (es wird in der Anwendung ausgeliefert, der Weg ist also schon da), und eine
**Auskunftsfunktion**, die zu einem Konto alles zusammenstellt, was OTA über ihn hat.

---

## 6 · Beschäftigtendatenschutz — was mitbestimmungspflichtig ist

Drei Dinge in dieser Anlage sind geeignet, Verhalten und Leistung von Beschäftigten zu überwachen.
Damit sind sie nach **§ 87 Abs. 1 Nr. 6 BetrVG mitbestimmungspflichtig** — unabhängig davon, ob
jemand sie dafür benutzen will:

1. **Das Protokoll.** Anmeldezeiten, Sitzungsdauer, gestartete Anwendungen, IP-Adressen. Daraus
   lässt sich ablesen, wer wann wie lange gearbeitet hat.
2. **Das Aufschalten auf einen laufenden Bildschirm.** Ein Administrator kann jede Sitzung öffnen —
   **ohne Protokolleintrag und ohne dass der Mensch davor es merkt** ([H4](security.md#h4)).
   Gemessen: Es gibt keinen einzigen Eintrag dazu in `audit_log`, weil keiner geschrieben wird.
3. **Die Kennzahlen.** `/metrics` nennt keine Namen, zeigt aber, wie viele Menschen wann arbeiten.

👉 **Empfehlung:** Eine Betriebsvereinbarung, die drei Dinge festhält — welche Daten protokolliert
werden, wie lange sie bleiben, und unter welchen Bedingungen sich jemand aufschalten darf. Für den
dritten Punkt ist die technische Lösung schon beschrieben: protokollieren, sichtbar machen,
Zustimmung einholen ([H4](security.md#h4)). **Ohne Protokoll über das Aufschalten ist jede
Vereinbarung dazu unüberprüfbar.**

---

## 7 · Drittlandübermittlung: der Zeichensatz von Google

`web/index.html` lädt bei **jedem** Aufruf der Oberfläche zwei Schriften von Google:

```html
<link href="https://fonts.googleapis.com/css2?family=Archivo…" rel="stylesheet" />
```

Dabei übermittelt der Browser jedes Nutzers **IP-Adresse, User-Agent und Referer an Google LLC in
den USA** — ohne Einwilligung und ohne dass es für die Funktion nötig wäre.

Das ist der bekannteste vermeidbare Datenschutzfehler im Web. Das **LG München I** hat am
20.01.2022 (3 O 17493/20) genau dafür Schadensersatz zugesprochen; seither ist es Gegenstand
serienmässiger Abmahnungen. Dass OTA intern läuft, verkleinert den Kreis der Betroffenen — es macht
die Übermittlung nicht rechtmässig.

👉 **Das ist der Punkt mit dem besten Verhältnis von Aufwand zu Wirkung in diesem ganzen Dokument.**
Die beiden Schriften mitliefern (`web/public/fonts/`, `@font-face` in `app.css`), die beiden
Google-Herkünfte aus der CSP streichen — eine halbe Stunde. Danach gibt es **keinen** Datenfluss
aus dieser Anlage heraus, und die Oberfläche funktioniert auch offline und hinter einem
Firmenproxy unverändert.

---

## 8 · Technische und organisatorische Massnahmen (Art. 32)

Was vorhanden ist — die Nachweise stehen in [`security.md`](security.md):

| Anforderung | Stand |
|---|---|
| **Verschlüsselung der Übertragung** | ✅ TLS 1.2 als Untergrenze, gemessen; TLS 1.1 wird abgelehnt |
| **Verschlüsselung im Ruhezustand** | ❌ Weder Datenbank noch Zuhause noch Sicherungen sind verschlüsselt. Bei einer gestohlenen Platte ist alles lesbar. |
| **Zugangskontrolle** | ✅ Keycloak, zweiter Faktor möglich, Kontosperre nach 8 Fehlversuchen, Argon2 |
| **Zugriffskontrolle** | ✅ Rechte je Gruppe, serverseitig an jedem Endpunkt geprüft; 226 automatische Prüfungen genau dazu |
| **Trennungskontrolle** | ⚠️ Zwischen Nutzern durch getrennte Einhängungen — aber **alle Container laufen als dieselbe UID 1000**, und sie erreichen einander im Netz ([H2](security.md#h2)) |
| **Eingabekontrolle** | ✅ Protokoll über Verwaltungsvorgänge — ⚠️ **ausser dem Aufschalten** |
| **Verfügbarkeit und Wiederherstellbarkeit** | ✅ Sicherung und Rückspielung sind gebaut **und geprüft** (39 automatische Prüfungen) |
| **Belastbarkeit** | ✅ Kontingente je Nutzer, Untergrenze für freien Plattenplatz, Leerlauf-Aufräumer |
| **Regelmässige Überprüfung** | ⚠️ 434 automatische Prüfungen bei jeder Änderung — aber kein Abgleich gegen Schwachstellenlisten |

**Die grösste Lücke in dieser Tabelle ist die zweite Zeile.** Ein Datenbankabzug enthält
Passwort-Hashes, TOTP-Startwerte und das AD-Kennwort — und liegt heute für jeden Benutzer des
Wirts lesbar da ([M2](security.md#m2)). Das ist zugleich der billigste Punkt: ein `chmod`.

---

## 9 · Braucht es eine Datenschutz-Folgenabschätzung?

Art. 35 Abs. 1 verlangt sie bei „voraussichtlich hohem Risiko". Zwei Merkmale der Liste der
deutschen Aufsichtsbehörden treffen zu:

* **Systematische Überwachung** ist technisch möglich (Abschnitt 6),
* verarbeitet werden **Daten von Beschäftigten**, also in einem Abhängigkeitsverhältnis.

Gegen ein hohes Risiko spricht: kleine Zahl Betroffener, keine besonderen Kategorien nach Art. 9,
keine automatisierte Entscheidung, keine Übermittlung an Dritte (nach Behebung von Abschnitt 7).

👉 **Meine Einschätzung: Eine vollständige Folgenabschätzung ist wahrscheinlich nicht zwingend, eine
dokumentierte Schwellwertanalyse aber schon** — und die kostet eine Seite. Diese Entscheidung
gehört zum Datenschutzbeauftragten, nicht in dieses Dokument.

---

## 10 · Wenn etwas passiert (Art. 33/34)

Bei einer Verletzung des Schutzes personenbezogener Daten bleiben **72 Stunden** für die Meldung an
die Aufsichtsbehörde.

Was dabei hilft: Das `audit_log` sagt, wer wann was getan hat, und `sessions` sagt, welche
Arbeitsplätze liefen. Was fehlt: **Es steht nirgends, wer sich auf welchen Bildschirm geschaltet
hat** — ausgerechnet der Vorgang mit dem grössten Schadenspotenzial hinterlässt keine Spur
([H4](security.md#h4)). Und die Container-Protokolle rotieren nicht, sind also nach langer Laufzeit
unbrauchbar gross.

---

## 11 · Was zu tun ist

Nach Wirkung geordnet, nicht nach Aufwand.

| # | Aufgabe | Aufwand | Warum |
|---|---|---|---|
| 1 | **Zeichensatz mitliefern**, Google aus der CSP streichen | ½ Stunde | Beseitigt die einzige Drittlandübermittlung (Abschnitt 7) |
| 2 | **Aufschalten protokollieren** | 2 Zeilen | Ohne das ist keine Betriebsvereinbarung überprüfbar (Abschnitt 6) |
| 3 | **Dateirechte** auf Sicherungen und Profile (`0700`/`0600`) | ein `chmod` | Datenbankabzüge sind heute für alle lesbar (Abschnitt 8) |
| 4 | **Aufbewahrungsfristen** für `audit_log` und Container-Protokolle | ½ Tag | Art. 5 Abs. 1 lit. e (Abschnitt 4) |
| 5 | **Datenschutzhinweis** als Kapitel im Handbuch | 1 Stunde | Art. 13 (Abschnitt 5) |
| 6 | **„Konto endgültig entfernen"** — Zuhause, Ablagen, Keycloak, Protokollnamen | 1 Tag | Art. 17 (Abschnitt 4.1) |
| 7 | **Auskunftsfunktion** je Konto | 1 Tag | Art. 15 (Abschnitt 5) |
| 8 | **Betriebsvereinbarung** anstossen | organisatorisch | § 87 Abs. 1 Nr. 6 BetrVG (Abschnitt 6) |
| 9 | **Schwellwertanalyse** dokumentieren | 1 Seite | Art. 35 (Abschnitt 9) |
| 10 | **Verschlüsselung im Ruhezustand** prüfen | Konzept | Abschnitt 8, zweite Zeile |

Die Punkte 1 bis 3 sind an einem Vormittag erledigt und beheben die drei Befunde, bei denen der
Abstand zwischen Aufwand und Wirkung am grössten ist.

---

## Nachbemerkung zur Hygiene

Beim Durchsehen aufgefallen und hier festgehalten, weil es zur Datensparsamkeit gehört: Im Zuhause
des Notfallkontos liegen **38 Rückstände aus Prüfläufen** (`ota-pruef-skeleton-*`). Kein
personenbezogener Schaden — das Konto ist ein Prüfkonto —, aber ein Hinweis darauf, dass die
Prüfreihen aufräumen sollten, was sie anlegen. Ebenso stehen in der Anlage neben dem einen echten
Konto drei Prüfkonten. **Vor dem Produktivgang gehören sie weg** oder zumindest abgeschaltet.
