# Datenschutz — Betrachtung nach DSGVO und BDSG

**Stand: 2026-11-25**, am Quelltext geprüft. Die erste Fassung entstand am 2026-09-04 (Commit
`99e9400`); seitdem dazugekommen sind die KI-Nutzungsstatistik, das Gedächtnis für opencode, das
Softwaremonitoring, das Terminal-Protokoll, OTA-Git und der Hinweis „DSGVO“ in der Seitenleiste.

Diese Betrachtung ist **keine Rechtsberatung.** Sie ist eine technische Bestandsaufnahme: **welche
personenbezogenen Daten wo liegen, wie lange, wer sie sieht und was davon fehlt.** Die Bewertung,
ob das im konkreten Unternehmen genügt, gehört zum Datenschutzbeauftragten. Die Punkte, die ihn
sicher interessieren, sind mit 👉 gekennzeichnet.

Die technische Seite steht in `security.md`. Dieses Dokument verweist an einigen Stellen auf deren
Befunde (H4, M2, N3 …); **`security.md` liegt bewusst nicht im Repository** — es beschreibt offene
Schwachstellen samt Weg dorthin und wird beim Betreiber geführt.

---

## 0 · Worum es geht — in drei Sätzen

OTA gibt jedem Beschäftigten einen eigenen Linux-Arbeitsplatz im Browser, mit Programmen wie
VS Code, PyCharm, Firefox und einem Terminal, und einem persönlichen Zuhause für Dateien und
Einstellungen. Es läuft vollständig auf eigener Hardware, mit zentraler Anmeldung (Keycloak, AD),
eigenem Git-Server und optional KI-Assistenten, die nur den eigenen KI-Server ansprechen. Die
Verwaltung steuert Software, Ressourcen und Netzzugriffe zentral; kein Arbeitsplatz erreicht
ungefragt das Firmennetz oder einen anderen Arbeitsplatz.

---

## 1 · Wer ist wofür verantwortlich

OTA ist **selbst gehostete Software**. Es gibt keinen Anbieter, der Daten verarbeitet, und damit
für OTA selbst **keinen Auftragsverarbeitungsvertrag** (Art. 28). **Verantwortlicher im Sinne von
Art. 4 Nr. 7 ist das Unternehmen, das die Anlage betreibt.**

* **Kein Datenfluss nach aussen beim Benutzen.** Die Oberfläche lädt nichts von fremden Hosts
  (Schriften liegen bei, seit 2026-09-04; Abschnitt 7). Keine Telemetrie. Die Telemetrie von
  Continue (KI-Erweiterung im Editor) ist abgeschaltet.
* **KI-Anfragen gehen nur an den eigenen KI-Server.** 👉 Ob **der KI-Server selbst** Anfragen
  oder Inhalte protokolliert, entscheidet seine Konfiguration (vLLM, llama.cpp …), nicht OTA. Das
  gehört gesondert geprüft.
* **Container-Images werden aus fremden Registries geholt** (Docker Hub u. a.). Dabei fliessen
  keine personenbezogenen Daten, nur die Information, dass diese Anlage ein bestimmtes Image lädt.
* **Angebundene Web-Anwendungen** (z. B. Open WebUI) sind eigene Verarbeitungen mit eigenen Daten.
  OTA regelt nur, wer sich dort anmelden darf. Open WebUI ist in **Abschnitt 12** beschrieben.

---

## 2 · Welche personenbezogenen Daten anfallen

### 2.1 Stammdaten der Konten

| Feld | Wo | Bemerkung |
|---|---|---|
| Anmeldename, Anzeigename, E-Mail | `users` (PostgreSQL) **und** Keycloak | E-Mail wird an angebundene Anwendungen weitergereicht |
| Passwort, zweiter Faktor (Passkey, Einmalkennwort) | **Keycloak**, bei Verzeichniskonten das AD | Der Regelweg. OTA selbst sieht keine Passwörter |
| Passwort-Hash (Argon2), TOTP-Startwert, Rückfallcodes | `users.password_hash`, `users.totp_secret` (**Klartext**), `users.totp_recovery` (gehasht) | nur noch für das lokale **Notfallkonto**; siehe `security.md`, M2 |
| Sprache, Gewand | `users.locale`, `users.theme` | |
| Gruppenzugehörigkeit | `group_members`, ggf. aus LDAP-Gruppen abgeglichen | daraus folgen die Rechte |
| Fehlversuche, Sperre, letzte Anmeldung | `users.failed_logins`, `locked_until`, `failed_from`, `last_login_at` | |
| Eigene Namen für Kacheln | `eigene_namen` | |
| Gelesen-Stand der News | `news_gelesen` (ein Zeitpunkt je Konto) | |

### 2.2 Protokoll und Sitzungen

| Datum | Wo | Frist |
|---|---|---|
| Jede Anmeldung, auch fehlgeschlagene — **IP-Adresse nur bei gescheiterten Anmeldungen** | `audit_log` | **90 Tage** |
| Start und Ende von Sitzungen (Arbeitsplätzen) | `audit_log`, `sessions` | `audit_log` 90 Tage; `sessions` mit dem Konto |
| Welche Anwendung gerade auf welchem Bildschirm läuft | `app_streams` | nur solange sie offen ist |
| Verwaltungsvorgänge (wer hat was geändert, Rechte, Freigaben; **mit IP-Adresse**, wenn das Konto Verwaltungsrechte hat), **Aufschalten auf fremde Bildschirme**, KI-Auskünfte, Änderungen am DSGVO-Hinweis | `audit_log` | **365 Tage** |
| Feste Netzadresse je Mensch und Vorlage | `net_leases` | mit dem Konto |
| Fehlerantworten des Reverse Proxy (4xx/5xx) mit IP | Traefik-Protokoll (Container-Ausgabe) | rotiert, 10 MB × 3 |

Fristen über `OTA_PROTOKOLL_VERHALTEN_TAGE` und `OTA_PROTOKOLL_VERWALTUNG_TAGE` einstellbar;
aufgeräumt wird täglich, und das Aufräumen steht selbst im Protokoll. Welche Einträge zur kurzen
Klasse gehören, ist eine ausdrückliche Liste (`audit.py`, `VERHALTEN`); alles andere bleibt 365
Tage. So kann `session.attached` (Aufschalten) nicht versehentlich mit den Sitzungsdaten
verschwinden.

**IP-Adressen** (seit 2026-11-19, `audit.mit_ip`): nur noch bei gescheiterten und auffälligen
Anmeldungen, bei Vorgängen von Konten mit Verwaltungsrechten und bei Vorgängen ohne Konto. Bei
erfolgreichen Anmeldungen, Sitzungen und allem, was normale Nutzer tun, wird keine gespeichert;
die Migration `b7c3e9f1a425` hat sie aus älteren Einträgen entfernt. Die Sperre nach
Fehlversuchen braucht das Protokoll nicht (`users.failed_from`, nach erfolgreicher Anmeldung
geleert).

**Welche Anwendung jemand öffnet** (`app.started`/`app.stopped`), stand bis 2026-11-19 ebenfalls im
Protokoll. Für die Funktion war das nie nötig; die API schreibt es nicht mehr, und die Migration
`a1d9e4b7c362` hat alle vorhandenen Einträge gelöscht (Datenminimierung, Art. 5 Abs. 1 lit. c).

👉 **Aus diesen Daten lässt sich ein Arbeitszeitprofil ablesen** — wann jemand anfängt, aufhört,
wie lange er arbeitet. Dass es nicht dafür gedacht ist, ändert daran nichts (Abschnitt 6).

### 2.3 Terminal-Protokoll der Administratoren

Seit 2026-10-06: Jede **Eingabezeile**, die ein Administrator per Webterminal als root in einem
Arbeitsplatz tippt, mit Zeit, Namen des Administrators, Namen des Nutzers und Vorlage
(`terminal_eintraege`). **Nicht** die Ausgabe — sie enthielte den Inhalt jeder gelesenen Datei.
Für Administratoren lesbar und exportierbar, nicht änderbar; Frist wie die Verwaltungsklasse
(**365 Tage**). Ein Kennwort, das ein Administrator auf der Kommandozeile tippt, steht darin.

### 2.4 Inhaltsdaten — das Zuhause und die Ablagen

Jeder Mensch hat ein persistentes Zuhause unter `/srv/ota/profiles/<konto-id>/…`. Darin liegt
**alles, was er im Arbeitsplatz tut**: Dokumente, Projekte, Browser-Profile samt Verlauf und
gespeicherten Passwörtern, SSH- und GPG-Schlüssel, Konfigurationen, **Gesprächsverläufe der
KI-Assistenten** (`~/.continue/sessions/`, opencode).

Dazu:

* `/srv/ota/userfiles/<konto-id>` — die eigene Ablage
* `/srv/ota/groupfiles/<gruppen-id>` — Gruppenlaufwerke, nur für Mitglieder (auch Administratoren
  nur bei eigener Mitgliedschaft)
* `/srv/ota/shared` — die gemeinsame Ablage, für alle lesbar
* Root-Arbeitsplätze: zusätzlich der angehaltene Container samt Docker-Daten

**Die Zwischenablage** liegt ausschliesslich im Container und wird nirgends zentral gespeichert.

### 2.5 KI-Nutzungsstatistik (optional — in dieser Anlage **eingeschaltet**)

Läuft über den KI-Durchgang `ota-ki`. Gezählt werden **nur Aufrufe eines Modells** (Chat,
Completions, Embeddings …), nie Inhalte.

| Datum | Wo | Frist |
|---|---|---|
| Je Anfrage: Zeit, Konto (Kennung **und Name**), Arbeitsplatz, Vorlage, Quelle, Server, Modell, Anwendung (opencode, PyCharm, Open WebUI …), Pfad, Status, Dauer, Tokens, Bytes | `ki_anfragen` | **30 Tage** (einstellbar) |
| Stundensummen je Konto, Vorlage, Server, Modell, Anwendung | `ki_stunden` | **365 Tage** (einstellbar, 0 = unbegrenzt) |
| Zwischenspeicher bis zur Übernahme | `/srv/ota/runtime/ki/spool/` | Minuten |

Die Person wird über die Absenderadresse des Arbeitsplatzes zugeordnet. **Externe Dienste** wie
Open WebUI melden Name und E-Mail der fragenden Person in Kopfzeilen; geglaubt wird das nur mit
einem gültigen Dienstschlüssel, und an den KI-Server gehen diese Kopfzeilen nicht weiter.

Schutz vor Auswertung einzelner Personen:

* Die Verwaltung sieht zunächst **nur Summen ohne Namen**; Verteilungen je Mensch nur nach Rang
  („Person 1“) und erst ab **drei** Menschen. Gefilterte Ansichten mit weniger als drei Menschen
  zeigen keine Zahlen.
* **Namen und Einzelverläufe** nur nach einer **Begründung** (mind. zehn Zeichen, z. B.
  Ticketnummer), protokolliert als `ki.auskunft` mit dem Namen der fragenden Person, gültig 30
  Minuten. Jeder Blick auf einen einzelnen Menschen steht zusätzlich als `ki.nutzung_angesehen`
  im Protokoll.
* Jeder sieht unter **Meine KI-Nutzung** die eigenen Zahlen (Selbstauskunft).
* **Alle Nutzungsdaten löschen** leert beide Tabellen auf einmal.

👉 Die Zeilen in `ki_anfragen` und `ki_stunden` hängen **nicht** am Konto: Wird ein Konto
gelöscht, bleiben sie mit Namen bis zum Ablauf ihrer Frist stehen.

### 2.6 Gedächtnis für opencode (Erweiterung — in dieser Anlage nur für die Gruppe der opencode-Entwickler)

Eigenständige Anwendung mit eigener Datenbank
([plugin_ota-opencode](https://github.com/bmetallica/plugin_ota-opencode)).

* **Inhalt:** Notizen, die sich der KI-Assistent je Sitzung merkt, ein persönliches
  Hauptgedächtnis und hochgeladene **Dokumente** (PDF, Office, Text). Das sind Inhaltsdaten.
* **Trennung:** Jeder sieht nur Eigenes; die Datenbank erzwingt das selbst (Row Level Security).
  Administratoren sehen nur Mengen (Menschen, Sitzungen, Einträge, Speicherbedarf).
* **Zugangsdaten** werden beim Speichern zurückgewiesen bzw. beim Auslesen von Dokumenten durch
  `[entfernt]` ersetzt (das Original-Dokument bleibt unverändert gespeichert).
* **Frist:** Sitzungen ohne Aktivität werden nach 180 Tagen gelöscht (einstellbar).
* **Kontolöschung** in OTA löscht alle Daten in der Erweiterung; ist sie nicht erreichbar,
  wiederholt OTA den Auftrag alle 15 Minuten. Sperren oder Gruppenentzug sperren, die Daten
  bleiben.

### 2.7 OTA-Git (Forgejo)

Repositories, Issues, Commits — darin **Name und E-Mail** der Autoren. Eigene Datenbank und eigenes
Datenverzeichnis, in der Sicherung enthalten. Konten werden beim Löschen in OTA **gesperrt, nie
gelöscht** (die Repositories gehören womöglich noch jemandem); Zugangstoken je Arbeitsplatz werden
beim Ende widerrufen.

### 2.8 Softwaremonitoring

Stündlich, welche Programme in jedem **laufenden** Arbeitsplatz installiert sind (apt, Startmenü,
Flatpak, Snap), ohne Versionen (`software_funde`, über die Sitzung einer Person zugeordnet). Zweck:
Lizenz- und Sicherheitskontrolle. **Gelöscht, sobald der Arbeitsplatz beendet ist**; Meldungen
verschwinden, wenn das Programm deinstalliert oder freigegeben wird.

### 2.9 Live-Werte

CPU, RAM und Netzdurchsatz je Arbeitsplatz (Betrieb → Arbeitsplätze), verworfene Pakete im Router,
Platzbedarf je Zuhause. **Nirgends als Verlauf gespeichert** — sie stehen live in der Oberfläche
und unter `/metrics` (dort ohne Namen).

👉 **Das ändert sich, sobald jemand sie abholt.** Ein Prometheus, der `/metrics` im Minutentakt
fragt, legt genau die Zeitreihe an, die es hier nicht gibt. Wer das einrichtet, braucht eine
Frist — Vorschlag: Rohwerte 7 Tage, Tagessummen 90 Tage.

### 2.10 Sicherungen

`/srv/ota/backups`: Datenbankabzüge, Zuhause-Archive, Container-Sicherungen, OTA-Git. Eine
Sicherung enthält **eine vollständige Kopie von allem oben**. Aufbewahrung über `keep_daily` und
`keep_weekly`, einstellbar. Dateirechte `0600`/`0700`.

### 2.11 Golden Images

Wer einen Arbeitsplatz einfriert, erzeugt ein Image. Das Zuhause ist ausgenommen, alles ausserhalb
wandert mit. Der Vorgang zeigt vorher an, was nach einem Geheimnis aussieht (`N5`), **verlässt sich
aber darauf, dass jemand die Liste liest.**

### 2.12 Was **nicht** anfällt

* **Keine Inhaltsprotokollierung.** Das Protokoll hält Vorgänge fest, nie Inhalte; die
  KI-Statistik zählt, liest aber keine Fragen und Antworten.
* **Keine Bildschirmaufzeichnung.**
* **Keine Tastatureingaben der Nutzer.** Mitgeschrieben werden nur die Eingaben von
  Administratoren im Webterminal (2.3).
* **Kein Mitschneiden des Netzverkehrs**, kein Aufbrechen von TLS, keine Liste besuchter Adressen.
  Der eigene Namensdienst schreibt Anfragen nicht mit. Direkte HTTPS-Verbindungen an den KI-Server
  reicht der Durchgang ungelesen durch.
* **Keine Telemetrie nach aussen.**
* **Keycloaks Ereignisprotokoll ist aus** — keine zweite Protokollspur.
* Im Browser liegen nur Gewand, Sprache und Marke.

---

## 3 · Rechtsgrundlagen

| Verarbeitung | Grundlage |
|---|---|
| Konten, Gruppen, Arbeitsplätze, Zuhause, Git | **§ 26 Abs. 1 BDSG** / Art. 6 Abs. 1 lit. b — Durchführung des Beschäftigungsverhältnisses |
| Protokoll über Anmeldungen und Sitzungen, Terminal-Protokoll | Art. 6 Abs. 1 lit. f — Nachvollziehbarkeit und IT-Sicherheit. **Interessenabwägung dokumentieren.** |
| KI-Nutzungsstatistik | Art. 6 Abs. 1 lit. f — Kapazität, Kosten, Fehlersuche. **Interessenabwägung dokumentieren**, Zweckbindung (keine Leistungsbewertung) festhalten |
| Softwaremonitoring | Art. 6 Abs. 1 lit. f — Lizenz- und Sicherheitskontrolle |
| Gedächtnis für opencode | § 26 BDSG — Arbeitsmittel für die, die es nutzen |
| Sicherungen | Art. 6 Abs. 1 lit. f, mittelbar Art. 32 Abs. 1 lit. c |
| Verzeichnisanbindung (AD/LDAP) | § 26 BDSG |

**Einwilligung ist hier der falsche Weg.** Im Beschäftigungsverhältnis gilt sie selten als
freiwillig (§ 26 Abs. 2 BDSG), und beim ersten Widerruf wäre die Grundlage weg.

---

## 4 · Aufbewahrung und Löschung

| Datum | Löscht sich | Frist |
|---|---|---|
| `audit_log` Verhalten | ✅ täglich | 90 Tage |
| `audit_log` Verwaltung, Terminal-Protokoll | ✅ täglich | 365 Tage |
| KI-Anfragen / KI-Stundensummen | ✅ täglich | 30 / 365 Tage |
| Gedächtnis (Erweiterung) | ✅ | 180 Tage ohne Aktivität; mit dem Konto |
| Softwaremonitoring | ✅ | mit dem Ende des Arbeitsplatzes |
| Container-Protokolle (auch Traefik) | ✅ rotiert | 10 MB × 3 je Container |
| Sicherungen | ✅ | `keep_daily` / `keep_weekly`; die eines **gelöschten** Kontos nur mit der Einstellung „Löschen“ (4.1) |
| `sessions`, `net_leases` | mit dem Konto | keine eigene Frist |
| `app_streams` (laufende Anwendungen) | beim Schliessen | — |
| Zuhause, Ablagen auf der Platte | ⚙️ **einstellbar** (seit 2026-11-25): beim Löschen des Kontos behalten (Vorgabe) oder nach einer Frist löschen | 0–365 Tage nach dem Löschen des Kontos |
| Konto in Keycloak | wird **gesperrt**, nicht gelöscht | — |
| Konto in OTA-Git, Repositories | wird **gesperrt**, nicht gelöscht | — |

### 4.1 Was beim Löschen eines Kontos passiert

Im Quelltext (`api/ota/routers/admin.py`, `delete_user`):

**Verschwindet:** der Datensatz in `users`, Gruppenmitgliedschaften, Sitzungshistorie, feste
Netzadressen, eigene Kachelnamen (Kaskade); **Root-Arbeitsplätze samt Docker-Daten**; alle Daten im
**Gedächtnis**; Git-Tokens.

**Je nach Einstellung** (*Einstellungen → Löschen von Konten*, seit 2026-11-25; Wiki Kapitel 08):

* **Behalten** (Vorgabe): Zuhause und Ablage bleiben auf der Platte, die Sicherungen des Kontos
  auch, und zwar **unbegrenzt**: Die Aufbewahrung behält die letzten Stände je Name, und für ein
  gelöschtes Konto kommt keiner mehr dazu.
* **Löschen nach N Tagen** (0 = sofort): Zuhause und Ablage wandern in einen Papierkorb und werden
  nach der Frist endgültig gelöscht, **samt den Sicherungen des Kontos**. Jeder Schritt steht im
  Protokoll (`user.daten_entfernt`, `user.daten_geloescht`), die Regel selbst mit Wert und
  Zeitpunkt (`settings.konto_daten`).

**Bleibt in jedem Fall:**

1. Was in `groupfiles/` und `shared/` liegt (gehört der Gruppe bzw. allen).
2. Datenbanksicherungen mit dem Konto, bis sie aus der Aufbewahrung fallen.
3. **Das Konto in Keycloak**, gesperrt (sonst legte die nächste Anmeldung es neu an).
4. **Das Konto in OTA-Git** samt Repositories, gesperrt.
5. **Das Protokoll**: `actor_name` bleibt bis zum Ablauf der Frist stehen.
6. **Die KI-Statistik** mit Namen bis zum Ablauf ihrer Frist (2.5).
7. **Das Konto in Open WebUI** mit allen Chats (Abschnitt 12, W3).

👉 **Mit der Einstellung „Löschen“ erfüllt das Löschen des Kontos ein Löschersuchen nach Art. 17
für OTA weitgehend mit einem Knopf**; offen bleiben Keycloak, OTA-Git und Open WebUI. Mit
„Behalten“ ist es Handarbeit nach einem **Löschkonzept mit Fristen**. Dass Namen in Protokoll und
Statistik bis zum Fristablauf stehen bleiben, ist mit Art. 17 Abs. 3 lit. b/e verteidigbar — weil
es eine dokumentierte Frist gibt.

### 4.2 Vorschlag für ein Löschkonzept

| Datum | Frist | Umsetzung |
|---|---|---|
| Zuhause und Ablagen nach Ausscheiden | **30 Tage archiviert, dann gelöscht** | ✅ Einstellung „Löschen“, Frist 30 Tage (seit 2026-11-25) |
| Keycloak-Konto | nach derselben Frist löschen | Keycloak-Konsole |
| Git-Konto | Repositories übergeben, dann Konto löschen | Forgejo-Verwaltung |
| alles andere | wie in der Tabelle oben | ✅ vorhanden |

---

## 5 · Rechte der betroffenen Personen

| Recht | Heute machbar? |
|---|---|
| **Information** (Art. 13) | ⚠️ Teilweise: Der Punkt **DSGVO** in der Seitenleiste erklärt, was über Arbeitsplätze und KI-Nutzung erfasst wird, wie lange und wer es sieht — **aber nur, solange die KI-Statistik läuft** (in dieser Anlage: ja). Der Text ist anpassbar (Markdown, Fristen werden eingesetzt); **verantwortliche Stelle und Datenschutzbeauftragte müssen eingetragen werden.** |
| **Auskunft** (Art. 15) | ⚠️ Für die KI-Nutzung ✅ (**Meine KI-Nutzung**, ohne Begründung, ohne Protokoll). Für alles andere von Hand: Datenbankabfrage plus Zuhause. Das Gedächtnis exportiert jeder selbst (JSON, Markdown). |
| **Berichtigung** (Art. 16) | ✅ Name und E-Mail über die Verwaltung bzw. Keycloak/AD. |
| **Löschung** (Art. 17) | ⚠️ Teilweise, siehe 4.1. |
| **Einschränkung** (Art. 18) | Teilweise: Konto deaktivieren; die Daten bleiben unberührt. |
| **Datenübertragbarkeit** (Art. 20) | ✅ Faktisch: Archiv des Zuhause über die Sicherung, Git-Repositories klonen, Gedächtnis-Export. |
| **Widerspruch** (Art. 21) | Gegen Protokoll und Statistik nur über die Interessenabwägung; hier helfen kurze Fristen und die Pseudonymisierung der Statistik. |

---

## 6 · Beschäftigtendatenschutz — was mitbestimmungspflichtig ist

Fünf Dinge sind geeignet, Verhalten und Leistung von Beschäftigten zu überwachen, und damit nach
**§ 87 Abs. 1 Nr. 6 BetrVG mitbestimmungspflichtig** — unabhängig davon, ob jemand sie dafür
benutzen will:

1. **Das Protokoll.** Anmeldezeiten und Sitzungsdauer; IP-Adressen nur bei gescheiterten Anmeldungen
   und bei Verwaltungsvorgängen. Welche Anwendung jemand öffnet,
   wird seit 2026-11-19 **nicht** mehr protokolliert (Migration `a1d9e4b7c362` hat die alten
   Einträge gelöscht).
2. **Das Aufschalten auf einen laufenden Bildschirm.** Nur volle Administratoren; jedes Aufschalten
   steht seit 2026-09-04 mit beiden Namen im Protokoll (`session.attached`, 365 Tage). **Der
   Mensch davor merkt es weiterhin nicht** (`H4`).
3. **Das Webterminal und sein Protokoll** (2.3). Eigenes Recht `arbeitsplatz.terminal`. Betrifft
   die Administratoren (ihre Tätigkeit wird lückenlos festgehalten) und mittelbar die Nutzer, deren
   Arbeitsplatz betreten wird, ohne dass sie es merken. Wer es hat, kann jede Datei im Zuhause
   lesen.
4. **Die KI-Nutzungsstatistik** (2.5). Auch ohne Namen auf der ersten Seite eine technische
   Einrichtung, die sich zur Kontrolle eignet. Die Auskunft mit Begründung macht jeden Zugriff auf
   Einzelne nachprüfbar.
5. **Das Softwaremonitoring** (2.8) — zeigt, wer was installiert hat. Kurzlebig, aber einer Person
   zugeordnet.

Dazu die Kennzahlen (`/metrics`): ohne Namen, aber sie zeigen, wie viele Menschen wann arbeiten.

👉 **Empfehlung: eine Betriebsvereinbarung**, die festhält:

* welche Daten erfasst werden und wie lange (Abschnitt 4);
* unter welchen Bedingungen sich jemand aufschalten oder das Webterminal benutzen darf, und wer
  das Terminal-Protokoll auswertet;
* **wofür die KI-Statistik da ist** (Kapazität, Kosten, Fehler — keine Leistungsbewertung) und
  welche Gründe eine personenbezogene Auskunft rechtfertigen.

Alle drei Zugriffe hinterlassen eine Spur im Protokoll; damit ist eine solche Vereinbarung
überprüfbar.

---

## 7 · Drittlandübermittlung: der Zeichensatz von Google — behoben

> **Stand 2026-09-04: erledigt.** Der Abschnitt bleibt stehen, weil er die einzige
> Drittlandübermittlung dokumentiert, die es in dieser Anlage je gab.

`web/index.html` lud **bis** zum 2026-09-04 bei jedem Aufruf der Oberfläche zwei Schriften von
Google. Dabei übermittelte der Browser jedes Nutzers **IP-Adresse, User-Agent und Referer an
Google LLC in den USA** — ohne Einwilligung und ohne Notwendigkeit (vgl. LG München I,
20.01.2022, 3 O 17493/20).

✅ **Behoben am 2026-09-04.** Beide Schriften liegen unter `web/public/fonts/`, die
Google-Herkünfte sind aus `index.html` **und** aus der CSP verschwunden. Im Browser nachgemessen:
keine einzige Anfrage an einen fremden Host. Lizenzen (OFL 1.1) in
[`THIRD-PARTY-NOTICES.md`](THIRD-PARTY-NOTICES.md).

---

## 8 · Technische und organisatorische Massnahmen (Art. 32)

| Anforderung | Stand |
|---|---|
| **Verschlüsselung der Übertragung** | ✅ TLS 1.2 als Untergrenze, gemessen |
| **Verschlüsselung im Ruhezustand** | ❌ **Bewusst nicht** (2026-09-05). Weder Datenbank noch Zuhause noch Sicherungen sind verschlüsselt; bei einer gestohlenen Platte ist alles lesbar. Ersatzweise Dateirechte 0600/0700; ein Abzug, der ausser Haus geht, wird von Hand verschlüsselt |
| **Zugangskontrolle** | ✅ Keycloak, zweiter Faktor (Passkey oder Einmalkennwort) je Gruppe erzwingbar, Kontosperre nach Fehlversuchen je (Konto, Absender), Bremse vor dem Notzugang |
| **Zugriffskontrolle** | ✅ Rechte je Gruppe, serverseitig an jedem Endpunkt geprüft und automatisch getestet; Gruppenlaufwerke nur für Mitglieder; Gedächtnis mit Row Level Security |
| **Trennungskontrolle** | ⚠️ Im Netz vollständig: jeder Arbeitsplatz in einem eigenen Netz, untereinander nicht erreichbar. Im Dateisystem durch getrennte Einhängungen und `0700` — aber **alle normalen Container laufen als dieselbe UID 1000**. Root-Arbeitsplätze laufen unter Sysbox, root im Container ist auf dem Host unprivilegiert |
| **Eingabekontrolle** | ✅ Protokoll über Verwaltungsvorgänge, Aufschalten, Webterminal-Eingaben und KI-Auskünfte |
| **Pseudonymisierung** | ✅ KI-Statistik: Auswertung ohne Namen, Mindestzahl drei, Namen nur mit Begründung |
| **Verfügbarkeit und Wiederherstellbarkeit** | ✅ Sicherung und Rückspielung gebaut und automatisch geprüft |
| **Belastbarkeit** | ✅ Kontingente je Zuhause, Untergrenze für freien Platz, Grenzen für CPU, RAM und Prozesse |
| **Regelmässige Überprüfung** | ✅ über zwanzig automatische Prüfreihen; `make cve` gleicht alle Images gegen Schwachstellenlisten ab; Sicherheitsupdates mit jedem `make update` |

**Die zweite Zeile ist die verbliebene Lücke — und sie ist eine bewusste.** Die Anlage steht im
eigenen Haus, gegen einen kompromittierten Wirt hilft Verschlüsselung im Ruhezustand ohnehin nicht.
**Das gehört in die Risikobetrachtung, nicht in die Mängelliste** — dokumentiert gehört es
trotzdem.

---

## 9 · Braucht es eine Datenschutz-Folgenabschätzung?

Art. 35 Abs. 1 verlangt sie bei „voraussichtlich hohem Risiko“. Dafür sprechen:

* **Systematische Überwachung** ist technisch möglich (Abschnitt 6), mit der KI-Statistik in
  einem Umfang mehr als bei der ersten Fassung;
* verarbeitet werden **Daten von Beschäftigten**.

Dagegen: überschaubare Zahl Betroffener, keine besonderen Kategorien nach Art. 9, keine
automatisierte Entscheidung, keine Übermittlung an Dritte, Pseudonymisierung und Zugriffsspur bei
der Statistik.

👉 **Einschätzung: Eine vollständige Folgenabschätzung ist wahrscheinlich nicht zwingend, eine
dokumentierte Schwellwertanalyse aber schon** — mit der KI-Statistik als eigenem Punkt. Die
Entscheidung gehört zum Datenschutzbeauftragten.

---

## 10 · Wenn etwas passiert (Art. 33/34)

Bei einer Verletzung des Schutzes personenbezogener Daten bleiben **72 Stunden** für die Meldung.

Was hilft: Das `audit_log` sagt, wer wann was getan hat — einschliesslich Aufschalten und
KI-Auskünften; `sessions` sagt, welche Arbeitsplätze liefen; das Terminal-Protokoll, was ein
Administrator in einem Arbeitsplatz eingegeben hat. Die Container-Protokolle rotieren und bleiben
handhabbar.

Was fehlt: Die Protokolle liegen auf demselben Host. Wer root auf dem Wirt hat, kann sie ändern;
eine Kopie an einen getrennten Ort (Syslog-Server) gibt es nicht.

---

## 11 · Was zu tun ist

| # | Aufgabe | Stand |
|---|---|---|
| ~~1~~ | ~~Zeichensatz mitliefern~~ | ✅ 2026-09-04 |
| ~~2~~ | ~~Aufschalten protokollieren~~ | ✅ 2026-09-04 |
| ~~3~~ | ~~Dateirechte auf Sicherungen und Profile~~ | ✅ 2026-09-04 |
| ~~4~~ | ~~Aufbewahrungsfristen für `audit_log` und Container-Protokolle~~ | ✅ 2026-09-04/05 |
| 5 | **Datenschutzhinweis** | ⚠️ teilweise: Punkt „DSGVO“ existiert (sichtbar, solange die KI-Statistik läuft). **Offen: Text prüfen, verantwortliche Stelle und Datenschutzbeauftragte eintragen**; ggf. dauerhaft sichtbar machen |
| ~~6~~ | „Konto endgültig entfernen“ | **abgewählt 2026-09-04**; dafür seit 2026-11-25 die Einstellung, Zuhause, Ablage und Sicherungen gelöschter Konten nach einer Frist zu löschen (4.1). Keycloak und OTA-Git sperren weiterhin nur |
| 7 | **Auskunftsfunktion** je Konto | ⚠️ für die KI-Nutzung vorhanden, sonst offen |
| 8 | **Betriebsvereinbarung** | offen — jetzt mit KI-Statistik und Webterminal (Abschnitt 6) |
| 9 | **Schwellwertanalyse** dokumentieren | offen |
| ~~10~~ | Verschlüsselung im Ruhezustand | **abgewählt 2026-09-05** |
| 11 | **Verzeichnis von Verarbeitungstätigkeiten**: Einträge für OTA, KI-Statistik, Gedächtnis | offen |
| ~~12~~ | **Protokollierung des KI-Servers** prüfen | ✅ 2026-11-25: Der KI-Server ist per Firewall nach außen gesperrt und führt Anfragen in einem rotierenden Protokoll von 100 MB; beim heutigen Durchsatz ist es nach höchstens etwa zwei Stunden überschrieben. Das ist eine Speicherung von Inhalten mit faktischer Frist von Stunden |
| 13 | **Interessenabwägung** für Protokoll, KI-Statistik und Softwaremonitoring dokumentieren | offen |
| 14 | **Open WebUI**: eigene Liste in Abschnitt 12.5 | offen |

Technisch wächst in dieser Anlage **nichts mehr ohne Frist** — ausser dem Zuhause, das als
Arbeitsmittel bewusst keine hat. Offen sind vor allem die organisatorischen Punkte: Hinweistext,
Betriebsvereinbarung, Schwellwertanalyse, Verarbeitungsverzeichnis und das Löschkonzept für
ausgeschiedene Beschäftigte.

## 12 · Open WebUI — eine eigene Verarbeitung neben OTA

*Stand 2026-11-20, beschrieben nach Open WebUI 0.12.*

**Geprüft am 2026-11-20 (Umgebung des Containers `open-webui`):** gesetzt sind nur
`ENABLE_FORWARD_USER_INFO_HEADERS=true` sowie `SCARF_NO_ANALYTICS=true`, `DO_NOT_TRACK=true` und
`ANONYMIZED_TELEMETRY=false`. **Telemetrie ist damit aus.** Alles andere steht auf der Vorgabe
oder in der Datenbank (Admin-Oberfläche, noch zu prüfen): Admin-Zugriff auf Chats, Export,
Community-Teilen, Versionsprüfung, Prüfprotokoll, Websuche. Das **Container-Protokoll** läuft als
`json-file` **ohne Größengrenze und ohne Rotation**.

Open WebUI ist die Chat-Oberfläche für den KI-Server. Es läuft in dieser Anlage als **eigener
Container neben OTA**. OTA richtet es nicht ein und hat keinen Zugriff auf seine Daten. Es ist
deshalb **eine eigene Verarbeitungstätigkeit** mit eigenem Eintrag im Verzeichnis. Und es ist
datenschutzrechtlich **gewichtiger als OTA**: OTA speichert über die KI-Nutzung nur Zahlen. Open
WebUI speichert die **Inhalte**, also jede Frage und jede Antwort.

### 12.1 Wo OTA und Open WebUI sich berühren

| Weg | Was fliesst | Wo es bleibt |
|---|---|---|
| **Anmeldung** über Keycloak (OIDC) | Name, E-Mail, Kennung, Gruppen; bei jeder Anmeldung neu | in Open WebUI als Konto |
| **Zugang**: Wer die Kachel sieht und sich anmelden darf | Gruppen aus OTA | Keycloak |
| **KI-Anfragen** über den KI-Durchgang `ota-ki` (Eingang `OTA_KI_EXTERN_PORT`) | Chat-Inhalt (geht durch, **wird von OTA nicht gespeichert**), dazu Name und E-Mail in Kopfzeilen (`ENABLE_FORWARD_USER_INFO_HEADERS`) | Die Kopfzeilen dienen nur der Zuordnung zum OTA-Konto in der KI-Statistik (2.5) und gehen **nicht** an den KI-Server weiter. Gibt es kein passendes Konto, bleibt die Zeile ohne Person; die E-Mail wird nicht gespeichert |
| **Websuche** über SearXNG (eigener Container) | Suchbegriffe, die das Modell aus dem Chat bildet | SearXNG fragt externe Suchmaschinen, siehe 12.3 |

### 12.2 Was Open WebUI selbst speichert

In seiner Datenbank (Vorgabe: SQLite unter `/app/backend/data`) und seinem Datenverzeichnis:

| Daten | Personenbezug | Frist von Haus aus |
|---|---|---|
| **Konten**: Name, E-Mail, Rolle, Profilbild, letzte Aktivität, OIDC-Kennung, persönliche Einstellungen, API-Schlüssel | direkt | **keine**: bleibt, bis ein Admin das Konto löscht |
| **Chats**: vollständiger Verlauf mit Fragen, Antworten, Modell und Zeitstempeln; Ordner, Schlagworte, archivierte Chats | direkt, **Inhalt kann alles enthalten**, auch Daten Dritter oder Art.-9-Daten | **keine**: bleibt, bis die Person ihn löscht. Ausnahme: der „temporäre Chat“ wird nicht gespeichert |
| **Geteilte Chats** (Link) | direkt | bis zum Widerruf |
| **Hochgeladene Dateien** und daraus erzeugte **Vektoren** (RAG, Wissenssammlungen) | Inhalt der Dateien | **keine** |
| **Erinnerungen** („Memory“), die das Modell sich über die Person merkt | direkt | **keine** |
| **Bewertungen** (Daumen hoch/runter) mit einer Kopie des Chats | direkt | **keine** |
| **Notizen, Kanäle** (Chat zwischen Nutzern), falls eingeschaltet | direkt | **keine** |
| **Prüfprotokoll** (`AUDIT_LOG_LEVEL`), Vorgabe aus | je nach Stufe bis zum vollständigen Anfrage- und Antworttext | nach Einstellung |
| **Container-Protokoll** (stdout) | Anfragepfade, je nach Stufe E-Mail | nach Docker-Einstellung des Containers |

Das ist der Kern: **Open WebUI löscht von sich aus nichts.** Ohne Regel wächst dort ein
vollständiges Archiv aller KI-Gespräche aller Beschäftigten.

### 12.3 Wohin Daten das Haus verlassen können

* **Websuche:** SearXNG reicht die Suchbegriffe an Google, Bing, DuckDuckGo usw. weiter, je nach
  Einstellung, also teils in Drittländer. Die IP-Adresse der Person geht nicht mit, die des
  Servers schon. Suchbegriffe können aus dem Chat stammen und Personenbezug haben.
  👉 Suchmaschinen in SearXNG bewusst wählen; prüfen, ob SearXNG Suchen protokolliert.
* **„Mit der Community teilen“** (`ENABLE_COMMUNITY_SHARING`, Vorgabe an) lädt einen Chat auf
  openwebui.com hoch. 👉 Abschalten.
* **Versionsprüfung, Telemetrie und Modell-Downloads** (`ENABLE_VERSION_UPDATE_CHECK`,
  `SCARF_NO_ANALYTICS`, `DO_NOT_TRACK`, `ANONYMIZED_TELEMETRY`, `OFFLINE_MODE`): ohne Personenbezug,
  verraten aber die Anlage. 👉 Abschalten bzw. `OFFLINE_MODE=true`, wenn die Modelle für die
  Einbettung schon da sind.
* **Externe Engines** für Sprache, Bilder oder Websuche-Loader, falls eingerichtet: Dann gehen
  Audio, Texte oder Seitenadressen an diesen Anbieter. 👉 Nur lokale Engines.
* **Webhooks** (`WEBHOOK_URL`, Nutzer-Webhooks): Benachrichtigungen an fremde Dienste. 👉 Prüfen.
* **Werkzeuge und Funktionen** (Tools/Functions/Pipelines) sind Python-Code, den Admins
  installieren. Sie sehen alles, was durch sie läuft, und können überall hin senden.
  👉 Nur geprüfte Werkzeuge; wer sie installieren darf, ist eine organisatorische Frage.

### 12.4 Wer was sehen kann — Mitbestimmung

* **Admins von Open WebUI können alle Chats aller Nutzer lesen** (`ENABLE_ADMIN_CHAT_ACCESS`,
  Vorgabe an) und die ganze Datenbank exportieren (`ENABLE_ADMIN_EXPORT`, Vorgabe an). Das ist
  eine technische Einrichtung, die Verhalten und Leistung überwachen **kann**, also
  **mitbestimmungspflichtig** (§ 87 Abs. 1 Nr. 6 BetrVG, wie Abschnitt 6). 👉 Abschalten oder in
  der Betriebsvereinbarung regeln; der Kreis der Admins klein halten.
* Die Rechte **in** Open WebUI (Modelle, Werkzeuge, Wissenssammlungen je Gruppe) kommen aus den
  OTA-Gruppen (Wiki, Kapitel 18). Wer in OTA aus einer Gruppe fällt, verliert sie bei der nächsten
  Anmeldung, aber nur, solange das Token noch mindestens eine Gruppe nennt.
* **Viele Einstellungen stehen nach dem ersten Start in der Datenbank** („PersistentConfig“), und
  die Umgebungsvariable gilt dann nicht mehr. Massgeblich ist die Admin-Oberfläche.

### 12.5 Was zu tun ist (Open WebUI)

| # | Aufgabe | Stand |
|---|---|---|
| W1 | **Einstellungen der eingesetzten Instanz prüfen und dokumentieren** (12.3, 12.4), in der Admin-Oberfläche, nicht nur in der Umgebung | ⚠️ Umgebung geprüft 2026-11-20, Admin-Oberfläche offen |
| W2 | **Löschfrist für Chats** festlegen (z. B. 90 Tage ohne Änderung) und umsetzen. Open WebUI kann das nicht selbst; nötig ist eine Aufgabe auf dessen Datenbank oder eine Regel „Nutzer löschen selbst“ | offen |
| W3 | **Ausgeschiedene Beschäftigte:** OTA sperrt das Konto in Keycloak, **das Konto in Open WebUI mit allen Chats, Dateien und Erinnerungen bleibt**. Gehört ins Löschkonzept (4.2): in Open WebUI unter *Administration → Benutzer* löschen | offen |
| W4 | **Admin-Zugriff auf Chats** abschalten oder in der Betriebsvereinbarung regeln | offen |
| W5 | **Community-Teilen, Versionsprüfung** abschalten (Telemetrie ist aus, geprüft 2026-11-20) | ⚠️ teilweise |
| W10 | **Container-Protokoll begrenzen** (`--log-opt max-size=10m --log-opt max-file=3` beim nächsten Neuanlegen von Open WebUI) — läuft heute ohne Grenze | offen |
| W6 | **SearXNG:** Suchmaschinen und eigene Protokollierung prüfen | offen |
| W7 | **Datenschutzhinweis in Open WebUI** (Banner oder Hinweis beim ersten Aufruf): Inhalte werden gespeichert, keine Personendaten Dritter und keine besonderen Kategorien eingeben, temporären Chat nutzen | offen |
| W8 | **Sicherungen** von Open WebUI: Wo liegen sie, wie lange? Gelöschte Chats leben dort weiter | offen |
| W9 | **Eintrag im Verzeichnis von Verarbeitungstätigkeiten** und Teil der **DSFA** (Abschnitt 9): KI mit frei eingegebenen Inhalten ist der wahrscheinlichste Grund, dass eine DSFA nötig wird | offen |

---

## 13 · KI-Sicherheit — Prüfung auf Prompt Injection

*Seit 2026-11-25, Wiki Kapitel 41.* Der KI-Durchgang prüft auf Wunsch, was ein KI-Assistent
liest, bevor es das Modell erreicht: **Ergebnisse von Werkzeugen** (Dateien, Befehlsausgaben,
Webseiten) und **Dokumente**, die Open WebUI mitschickt. **Nicht** geprüft wird, was der Mensch
selbst eintippt, und nicht der Systemprompt.

| Frage | Antwort |
|---|---|
| Werden Inhalte gelesen? | Ja, im Speicher des Durchgangs, während die Anfrage durchläuft (Stufe 1 und 2). Bei Stufe 3 geht der geprüfte Inhalt zusätzlich als eigene Anfrage an ein Modell auf einem **eigenen** KI-Server |
| Wird etwas gespeichert? | Nur Zähler je Stunde (`ki_sicherheit`): Herkunft (alle Arbeitsplätze zusammen oder ein externer Dienst), Anwendung, Stufe, Typ, Aktion. **Kein Text, kein Ausschnitt, keine Person, kein Arbeitsplatz.** Im Speicher des Durchgangs bleibt je geprüftem Abschnitt eine Prüfsumme (SHA-256) mit dem Ergebnis, bis zu 50 000, bis zum Neustart |
| Frist | 365 Tage, täglich aufgeräumt; „Alle Zähler löschen“ sofort |
| Wer sieht es? | Konten mit `settings.manage` (Seite KI-Sicherheit) |
| Verändert OTA Anfragen? | Stufe 1 entfernt unsichtbare Steuerzeichen. In der Betriebsart *Warnen* kommt vor einen auffälligen Inhalt ein Hinweis an das Modell; in *Sperren* wird die Anfrage abgewiesen |
| Rechtsgrundlage | Art. 32 DSGVO (Sicherheit der Verarbeitung); für eine Behörde Art. 6 Abs. 1 lit. e i. V. m. dem Landesrecht. Kein Personenbezug in den gespeicherten Daten |

👉 **Mitbestimmung:** Weil nichts einer Person zugeordnet wird, eignet sich die Einrichtung nicht
zur Leistungs- oder Verhaltenskontrolle. Sie liest aber Inhalte, mit denen Beschäftigte arbeiten,
auch wenn sie nichts davon behält. Das sollte der Personalrat kennen, und es gehört in die
Dokumentation der Verarbeitung.

👉 **Stufe 3 und das Protokoll des KI-Servers:** Die Prüfanfragen landen im Protokoll des
KI-Servers wie jede andere Anfrage (Abschnitt 11, Punkt 12: rotierend, faktisch Stunden).

---

## Nachbemerkung zur Hygiene

Prüfkonten (`kc-pruef`, `ota-testnutzer`, `ki-pruef` u. a.) gehören in einer produktiven Anlage
abgeschaltet, und die Prüfreihen sollten aufräumen, was sie anlegen. Die Zahlen, die `test-ki.sh`
erzeugt, stehen unter dem Testkonto in der KI-Statistik und verfallen mit deren Frist.
