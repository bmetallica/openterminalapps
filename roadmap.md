# OpenTerminalApps — Roadmap

Ergänzt [`plan.md`](./plan.md) um die zeitliche Umsetzung.
Bezugsdatum: 2026-08-27 · Annahme: ein Entwickler, Teilzeit.

**Leitprinzip**: Nach jedem Meilenstein ist das System benutzbar. Kein Big-Bang.
Kasm läuft dauerhaft daneben weiter — OTA auf 8443, Kasm auf 443. Der letzte
Konflikt zwischen beiden ist beseitigt (`plan.md` §17.12).

**Reihenfolge folgt der Neuausrichtung** (`plan.md` §1): Der **Arbeitsplatz** ist der Kern und kommt
früh. Die Einbindung vorhandener **Kasm-Images und -Registries** ist ein Feature und kommt später.

---

## Meilensteinübersicht

| M | Titel | Ergebnis | Aufwand |
|---|---|---|---|
| **M0** | Fundament & HTTPS | Repo, Stack, TLS, Oberflächenentwurf | ✅ **erledigt** |
| **M1** | Erster Stream im Browser | Ein Container im Browser, Zwischenablage geprüft | ✅ **erledigt** |
| **M2** | Nutzerverwaltung & RBAC | Login, Gruppen, Admin/User-Trennung | ✅ **erledigt** |
| **M3** | Oberfläche | Entwurf an echte Daten angeschlossen | ✅ **erledigt** |
| **M4** | **Der Arbeitsplatz** | Ein Linux je Nutzer, Apps einzeln gestreamt | ✅ **Grundfunktion steht** |
| **M5** | Golden Images | Build-Pipeline, Versionen, App-Katalog, Skeleton | 2–3 Wochen |
| **M6** | Identität ~~& Netzlaufwerke~~ | AD/LDAP ✅ — mit M11 abgelöst; Kerberos und Shares **gestrichen** | ✅ **erledigt** |
| **M7** | Migration & Härtung | Profil umgezogen ✅, Härtung, Monitoring | 1–2 Wochen |
| **M8** | Kasm-Kompatibilität | Einzelimages und ganze Registries einbinden | ✅ **erledigt** |
| **M9** | Optionale Erweiterungen | WebAuthn ✅, Gruppenlaufwerke ✅; ~~Guacamole~~, ~~code-server~~ **gestrichen** | ✅ **erledigt** |
| **M10** | Skalierung | Mehrere Hosts, Pools | offen |
| **M11** | **Zentrale Identität** | Keycloak als Anmeldung, OTA als sein Verwalter und Portal | ✅ **erledigt** |
| **M12** | **Das Netz der Arbeitsplätze** | Ein Netz je Sitzung, ein Router davor, Firewall in der Oberfläche | ✅ **erledigt** |
| **M13** | **Härtung für den Betrieb** | Schriften, Protokollgrenzen und -fristen, Anmeldebremse, Dateirechte | ✅ **erledigt** |

Bis zum produktiven Einsatz (M5–M7): **realistisch 4–6 Wochen** in Teilzeit.

**Stand 2026-09-05**: M0 bis M4, M8, M11, M12 und M13 laufen, dazu die Build-Pipeline aus M5 und
die Sicherung aus M7.

Ein Nutzer meldet sich über die **zentrale Anmeldung** an, startet seinen Arbeitsplatz und öffnet
darin VS Code, ein Terminal und den Dateimanager — jedes formatfüllend auf eigenem Display, alle
im selben Container mit gemeinsamem `/home`. Er legt einzelne Anwendungen als **Symbol auf dem
Desktop** ab, die in einem eigenen Fenster starten. Dateien schiebt er über seine **eigene Ablage**
in den Container und wieder heraus.

Ein Administrator baut Software ins Image, bindet fremde Kataloge ein, stellt Sicherungen wieder
her, richtet ein **Active Directory** in OTAs Oberfläche ein und bindet **fremde Web-Anwendungen**
an, die dieselbe Anmeldung benutzen.

Und sein Arbeitsplatz kommt dabei **weder ins Firmennetz noch an die Sitzung eines Kollegen** —
nicht, weil eine Regel es verbietet, sondern weil er in einem eigenen Netz hängt, dessen einziger
Ausgang ein Router ist (M12).

Geprüft durch **446 automatische Prüfungen in sieben Reihen**, davon 107 in einem echten Browser
(`make test`). Ein voller Lauf dauert rund eine halbe Stunde — er baut Container, friert ein
Image ein, zieht ein Wegwerf-Verzeichnis hoch und misst im Browser nach.

---

## M0 — Fundament & HTTPS · ✅ erledigt am 2026-08-27

- [x] Entscheidungen aus `plan.md` §17 aufgenommen; Hardware (§17.1) und Domain (§17.2) bleiben offen
- [x] Lizenzen am Originaltext verifiziert: MS-VS-Code-EULA erlaubt internes Deployment ausdrücklich,
      Kasm-Images MIT, KasmVNC GPL-2.0 — `plan.md` §3
- [x] Monorepo-Struktur: `web/`, `deploy/`, `docs/`, `scripts/`
- [x] **Lokale CA statt nacktem selbstsigniertem Zertifikat** (`scripts/make-cert.sh`) — Root einmal
      importieren, danach ist der Zertifikatswechsel frei. SAN enthält Hostname und LAN-IP;
      Docker-Bridge-Adressen werden bewusst ausgelassen
- [x] Traefik v3.7 auf **8443** (443 gehört noch Kasm), HTTP-Umleitung auf 8081
- [x] Sicherheits-Header inklusive `Permissions-Policy` für die Zwischenablage; **HSTS bewusst aus**,
      solange die CA nicht verteilt ist
- [x] Oberflächenentwurf lauffähig (`web/`), Design-System nach `plan.md` §13
- [x] Erste **Alembic-Migration** erzeugt und beim Start ausgeführt (`api/ota/migrate.py`).
      Gegen eine leere Datenbank erzeugt, damit sie wirklich alles aufbaut — nachgewiesen: 18
      Tabellen aus dem Nichts. Eine bestehende Anlage wird auf den Ausgangsstand gestempelt statt
      migriert. `create_all` und `schema_sync` bleiben als Netz fürs Weiterbauen, nicht als Ersatz
- [x] **ADR-Format und die ersten vier ADRs** (`docs/adr/`): Format, wann überhaupt eines fällig
      ist, und die Entscheidungen, die ein Leser am ehesten hinterfragt — Arbeitsplatz statt
      Einzel-Container, Docker nur im Agent, KasmVNC mit einem Display je Anwendung, keine
      Signaturprüfung für Registries. Ein ADR wird nicht überschrieben, wenn die Entscheidung
      fällt; es bekommt einen Nachfolger

**Erreicht**: `https://<host>:8443/` liefert die Oberfläche mit gültiger Kette, Kasm läuft unbeeinträchtigt.

---

## M1 — Erster Stream im Browser · ✅ erledigt am 2026-08-27

**Ziel**: Der technische Kernbeweis, inklusive der Funktion, an der alles hängt.

- [x] Postgres, SQLAlchemy, Alembic; Zustandsautomat `starting → running → stopped/failed`
- [x] `ota-agent`: Container starten, stoppen, inspizieren; Ressourcenlimits setzen
- [x] Traefik-Labels dynamisch; `serversTransport` mit `insecureSkipVerify` für KasmVNC-HTTPS
- [x] `basicauth`-Header-Injection, damit das VNC-Passwort nie den Browser erreicht
- [x] `forwardAuth` `/api/internal/authz` (in M1 noch mit Testnutzer)
- [x] Profil-Mount, UID/GID 1000
- [x] **Zwischenablage in beide Richtungen** (`plan.md` §10): iframe mit
      `allow="clipboard-read; clipboard-write"`, Fokus-Rückgabe ans iframe, Panel als Rückfall
- [x] **Client-Schalter im iframe erzwingen** (`plan.md` §10.2 Punkt 5): KasmVNC setzt
      `clipboard_up`/`clipboard_down` auf `false`, sobald er nicht die oberste Seite ist, und
      verwirft danach lautlos alles, was der Server schickt. Die API hängt deshalb
      `clipboard_up=1&clipboard_down=1&clipboard_seamless=0` an die Stream-Adresse
- [x] **Brücke im Elternfenster** (`web/src/lib/clipboardBridge.ts`): steuert den Client von
      aussen an — Panel lesen → System-Zwischenablage, System-Zwischenablage → Panel + `change`.
      Zweiter Anlauf bei der nächsten Nutzergeste, weil Firefox ohne sie nicht schreiben lässt
- [x] Abnahmefälle 1, 2 und 4 laufen automatisiert in `tests/e2e.mjs` gegen den Viewer.
      Die frühere Annahme, Headless-Chromium verweigere `navigator.clipboard` grundsätzlich,
      war falsch: Puppeteers `overridePermissions('clipboard-write')` trifft nur nicht das Recht,
      das `writeText()` prüft. Über `Browser.grantPermissions` mit `clipboardReadWrite` und
      `clipboardSanitizedWrite` läuft der vollständige Weg im Test durch
- [x] **Firefox-Erweiterung** (`extension/firefox/`): Firefox gibt Webseiten den Lesezugriff auf
      die Zwischenablage grundsätzlich nicht. Die Erweiterung reicht ihn an genau eine Adresse
      weiter — und zwar erst nach einem Klick auf ihr Symbol, sie kommt ohne jede
      Seitenberechtigung ins Haus. OTA erkennt Firefox, prüft per Handschlag, ob sie da ist, und
      bietet sie sonst in der Kontrollleiste zum Herunterladen an
      (`/api/help/extension/firefox`)
- [ ] **Offen**: Signatur oder Unternehmensrichtlinie für die dauerhafte Installation der
      Erweiterung. Beides liegt ausserhalb von OTA; die Wege stehen im Handbuch Kapitel 4
- [x] **Abnahmematrix zu zehn Zwölfteln automatisiert** (`plan.md` §10.5): 5 (1 MB, vollständig),
      6 (Bild — die Brücke trägt jetzt auch `image/png`), 9 (PRIMARY, und die Prüfung, dass es die
      Displaygrenze **nicht** überschreitet), 10 (abgeschaltet heisst abgeschaltet) und 11 (nach
      Pause und Fortsetzen) sind dazugekommen
- [x] **Alle zwölf Fälle laufen** (2026-09-01). Zuletzt dazugekommen: Fall 3 (zwischen zwei
      Sessions — `tests/e2e.mjs` startet einen zweiten Container mit eigenem Profil und schickt
      den Text über die System-Zwischenablage des Browsers), Fall 7 (Java/AWT mit einem laufenden
      AWT-Prozess, auf Zuruf über `OTA_PRUEFE_JAVA=1`) und Fall 12 (in Chromium mit abgeschaltetem
      `readText` — kein Ersatz für einen Lauf in Firefox, aber es prüft genau den Pfad, der dort
      greift, und zwar bei jedem Lauf)
- [x] Heartbeat, Idle-Reaper, Orphan-GC

**Fertig, wenn**: Ein Klick startet einen Container, der Desktop erscheint, die Abnahmematrix läuft in
beiden Browsern durch, ein Refresh verbindet ohne Neustart, ein Stopp räumt auf, Änderungen im Home
überleben den Neustart.

**Das Risiko hat sich bestätigt** — und zwar anders als erwartet: Nicht Traefik war das Problem,
sondern der KasmVNC-Client. Er hängt seinen WebSocket-Pfad an die Wurzel der Seite, nicht an den
aktuellen Pfad. Ohne Gegenmaßnahme versucht er `wss://host/websockify`, landet bei der
Weboberfläche und bekommt HTTP 200 statt eines Upgrades — die Seite lädt, es fliesst aber kein
Bild, und im Server-Log steht nichts. Gelöst über den URL-Parameter `?path=s/<id>/websockify`.
Siehe Handbuch, Kapitel 12.

---

## M2 — Nutzerverwaltung & Rechtekonzept · ✅ erledigt am 2026-08-27

- [x] `users`, `groups`, `group_members`, `permissions`, `group_permissions`, `audit_log`
- [x] Argon2id, Passwort-Policy, Brute-Force-Backoff, Lockout
- [x] JWT im `HttpOnly`/`Secure`/`SameSite`-Cookie, Refresh-Rotation, serverseitige Invalidierung
- [x] Systemgruppen `admins` und `users`, Schutz des letzten Admins
- [x] `require_permission(...)` an **jedem** Admin-Endpunkt; Query-Scoping für Nicht-Admins
- [x] `template_overrides` (Ressourcen je Gruppe und je Nutzer) samt Auflösung nach `plan.md` §5;
      Referenz ist `effectiveResources()` aus dem Oberflächenentwurf
- [x] Aufgelöste Werte beim Session-Start festschreiben und als `--cpus`/`--memory` setzen
- [x] **Zwei-Faktor im UI einrichten**, mit QR-Code als SVG, Geheimnis zum Abtippen und zehn
      Rückfallcodes. Gespeichert wird erst nach bestandener Probe; abschalten verlangt Passwort
      **und** Code. Niemand kann den zweiten Faktor eines anderen entfernen — deshalb sind die
      Rückfallcodes Pflicht und nicht Zubehör. Acht Prüfungen in `test-authz.sh`
- [x] **Ein Administrator kann den zweiten Faktor abnehmen.** Der Fall dafür: Telefon **und**
      Rückfallcodes weg — ohne diesen Weg käme der Mensch nie wieder herein, und das Konto wäre nur
      noch zu löschen. Aufgefallen ist die Lücke beim Testen, nicht beim Entwerfen: Ein
      abgebrochener Lauf liess den zweiten Faktor am Prüfkonto stehen, und es gab keinen Weg
      zurück. Alle Sitzungen des Kontos werden dabei beendet, und es steht mit Namen im Protokoll
- [x] **Zwei-Faktor je Gruppe erzwingen** (`groups.require_totp`). Durchgesetzt beim **Start einer
      Session**, nicht bei der Anmeldung: Wer sich nicht anmelden kann, kommt nicht an „Mein Konto"
      und kann den Faktor gar nicht erst einrichten — eine Sperre an der Anmeldung wäre eine Sperre
      gegen ihre eigene Auflösung. Im Dashboard steht ein Streifen mit dem Weg dorthin
- [x] Seed-Skript für den ersten Admin
- [x] **Autorisierungstests**: je Admin-Endpunkt ein Test, der mit Nutzer-Token 403 erwartet

**Fertig, wenn**: Ein normaler Nutzer kann per API und UI beweisbar nichts Administratives tun und
keine fremde Session sehen — verifiziert durch Tests, nicht durch Hinsehen.

---

## M3 — Oberfläche an echte Daten · ✅ erledigt am 2026-08-27

Der Entwurf steht bereits (`web/`, `plan.md` §13). Hier wird er verkabelt.

- [x] Mock-Daten durch die API ersetzen; Lade-, Leer- und Fehlerzustände real bedienen
- [x] Login-Seite, Session-Handling, Rollen-Routing (Admin-Bereich nur für `admins`)
- [x] Session-Viewer mit echter Kontrollleiste: Vollbild, Auflösung, Zwischenablage-Panel,
      Upload/Download, Ton, Verbindungsqualität, `Strg+Alt+Shift`
- [x] Startvorgang mit echten Phasen statt Spinner
- [x] **Mein Konto** für jeden Angemeldeten: Passwort selbst ändern, Zwei-Faktor, Sprache am
      Konto gemerkt. Ein normaler Nutzer konnte sein Passwort vorher nicht ändern — nur ein
      Administrator konnte es für ihn setzen. Eine Auflösung braucht es nicht mehr: Der ferne
      Bildschirm folgt dem Browserfenster
- [x] Admin: Nutzer, Gruppen, Sessions, Audit-Log — inklusive Anlegen und Ändern
- [x] Entwurfsleiste entfernt

---

## M4 — Der Arbeitsplatz · ✅ Grundfunktion erledigt am 2026-08-27

**Das Kernmodell** nach `plan.md` §9: ein persistenter Linux je Nutzer, Werkzeuge einzeln gestreamt.

**Streaming**
- [x] `template_apps` und `app_streams` nach `plan.md` §9.7
- [x] Agent startet Displays **bei Bedarf**: `Xvnc` auf freiem `DISPLAY=:N` mit eigenem
      Websocket-Port, App darin formatfüllend; Abbau bei Schliessen oder Leerlauf
- [x] Routing `/s/<sid>/a/<app-slug>` → `690N`, abgesichert über dasselbe `forwardAuth`
- [x] Einzelnes Display neu startbar, ohne den Container zu verlieren
- [x] **Klassischer XFCE-Desktop zusätzlich als Ansicht** — auf `:1` und nicht auf `:0`: Das
      Kasm-Basisimage macht `:1` selbst auf, und ein zweites Display daneben wäre ein zweiter
      Desktop ohne Zweck. Fenstermanager, Leiste und Schreibtisch laufen dort; geprüft in
      `scripts/test-clipboard-bridge.sh`, weil genau das einmal fehlte — `xfce4-panel` war aus dem
      gebauten Image gefallen, und übrig blieb ein schwarzes Bild mit Mauszeiger
- [x] App-Umschalter im Viewer; laufende und nicht gestartete Apps unterscheidbar
- [x] **Abbruch heilt von selbst** (2026-08-28): Der Viewer erkennt am Verschwinden von
      `noVNC_connected`, dass der Stream weg ist, lädt ihn mit wachsendem Abstand höchstens acht
      Mal neu und sagt es, wenn die Session wirklich beendet ist. Vorher blieb KasmVNCs
      ausgeblendeter Abbruchbildschirm stehen — sichtbar war nur ein eingefrorenes Bild
- [x] **Die Leerlaufuhr gehört OTA, nicht dem Client** (2026-08-28): KasmVNC trennte nach 20
      Minuten ohne Maus oder Tastatur; Zusehen zählte dort als Nichtstun. Der Viewer stellt sie
      jetzt beim Verbinden auf ein Jahr, die Stream-Adresse hebt sie zusätzlich auf das erlaubte
      Maximum. Über die Laufzeit entscheidet `idle_minutes` der Vorlage
- [x] **Der Aufräumer entfernte startende Container** (2026-09-02): Die Session-Zeile wurde nur
      geflusht und erst nach dem vollständigen Start committet — für den minütlichen Aufräumer gab
      es sie in dieser Zeit nicht, und er hielt den Container für eine Waise. Unter Last über eine
      Minute Fenster. Die Symptome sahen jedes Mal anders aus: Startskript mit Rückgabe 137,
      Einmal-Skript ohne Ausgabe, „KasmVNC nach 40s nicht bereit", 409er hinterher. Behoben an
      beiden Enden — committen vor dem Containerstart, und der Aufräumer vergleicht zusätzlich die
      Session-Kennung aus dem Container-Label. Geprüft wird die Ursache, nicht das Symptom
- [x] **Totes Display wird wiederbelebt** (2026-08-28): War das `Xvnc` einer Anwendung
      abgestürzt, führte OTA sie weiter als `running`, und der Start kehrte wortlos zurück — die
      Anwendung war für immer tot. Der Start sieht jetzt beim Agent nach

**Zwischenablage** — der kritische Teil dieses Meilensteins
- [x] **Brücke zwischen den Displays** (`plan.md` §10.4): spiegelt CLIPBOARD über alle offenen
      Displays, Schleifenschutz über Prüfsumme, folgt den Rechten des Templates, startet
      automatisch beim ersten App-Start. Geprüft durch `scripts/test-clipboard-bridge.sh`
- [x] **Ereignisse statt Abfragen** (2026-09-01): `clipnotify -l` je Display meldet jede Änderung,
      statt dass die Brücke im halben Sekundentakt nachfragt. Die Brücke entscheidet **im
      Container**, ob sie das kann — in den Kasm-Images fehlt `clipnotify`, dort bleibt es beim
      Takt. Der Gewinn ist nicht die Last (acht Aufrufe je Sekunde tun keinem weh), sondern die
      Verzögerung: statt bis zu einer halben Sekunde nun Millisekunden. Gemessen in
      `scripts/build-base-image.sh`
- [x] `xsel`, `xdotool`, `autocutsel`, `clipnotify` im eigenen Basisimage — im Kasm-Image fehlen sie
- [x] Abnahmefall 8: Kopieren zwischen zwei Apps im Container, beide Richtungen
- [x] Abnahmefall 3 (zwischen zwei Sessions), 7 (Java/AWT) und 12 (ohne `readText()`) — siehe
      `plan.md` §10.5

**Ressourcen**
- [x] Grenzen gelten für den Container als Ganzes (`plan.md` §9.3); Spitzenlast-Dimensionierung
- [x] `oom_score_adj=500` für jede gestartete Anwendung und ihre Kindprozesse; die Infrastruktur
      bleibt bei 0. Bei Speichernot trifft es damit eine Anwendung statt Xvnc. Nachgemessen an
      VS Code: alle Prozesse erben den Wert. Gesetzt in einer Zwischen-Shell, die sich per `exec`
      ersetzt — Erhöhen darf jeder Prozess für sich, Senken bräuchte CAP_SYS_RESOURCE

**Arbeitsgefühl** — nachgezogen am 2026-08-27 nach dem ersten echten Benutzen
- [x] **Der Stream wächst mit dem Fenster.** Der KasmVNC-Client schaltet `resize` im iframe auf
      `off`; der ferne Bildschirm blieb dann auf Startgrösse und sass mit schwarzem Rand mitten im
      Fenster. Die Stream-Adresse trägt jetzt `resize=remote` (`STREAM_ARGS` in
      `api/ota/routers/sessions.py`) — gemessen: Fenster 1600×1000 → Display 1600×1000
- [x] **Jede Anwendung in einem eigenen Tab.** Eigene Adressen `/view/s/<id>[/<display>]`;
      das Dashboard bleibt im ersten Tab stehen
- [x] **Verknüpfung auf dem Desktop** (PWA): Manifest je Vorlage und App aus der API
- [x] **Einmal-Skripte je Workspace** (2026-08-28): Laufen je Nutzer genau einmal, beim nächsten
      Start — für Änderungen am Zuhause, die das Skeleton nicht mehr erreicht (es ist nicht leer)
      und die das Startskript bei jedem Start wiederholen würde. Gebucht je Nutzer und Skript;
      ein neues Skript läuft wieder für alle. Ein gescheiterter Lauf wird verbucht und sichtbar
      gemacht, damit ein kaputtes Skript nicht bei jedem Start jedes Nutzers erneut anläuft;
      „Nochmal" nimmt die Buchführung zurück, ausgeführt wird beim nächsten Start
- [x] **Zwei getrennte Ablagen** (2026-08-28): Die gemeinsame gehört der Verwaltung — sichtbar
      und beschreibbar nur für die, die Images oder Vorlagen verwalten, im Container weiterhin
      `/mnt/ota` nur lesbar. Die eigene gehört je einem Nutzer, liegt beschreibbar unter
      `/mnt/austausch` und als `~/Austausch` im Home, und ist je Workspace abschaltbar
      (Vorgabe an). Der Eigentümer kommt aus dem Anmeldecookie, nie aus der Anfrage: Es gibt
      keinen Weg in eine fremde Ablage, auch nicht für Administratoren. Zusätzlich in der
      Kontrollleiste einer laufenden Session, mit Ziehen und Ablegen
- [x] **Jede Anwendung einzeln ablegbar** (2026-08-28): Katalog im Dashboard, eigene Ablage-Seite
      je Anwendung unter `/launch/<vorlage>/<app>?ablegen`, eigene Kennung im Manifest. Der
      frühere Knopf im Viewer konnte nicht halten, was er versprach: Der Browser liest das
      Manifest einmal beim Laden, ein späterer Austausch aus React heraus änderte daran nichts —
      abgelegt wurde das Dashboard. Gemessen mit `Page.getInstallabilityErrors`: keine Hindernisse,
      Kennung `ota-<vorlage>-<app>`, und die Ablage startet keinen Container
      (`api/ota/routers/pwa.py`), Startadresse `/launch/<vorlage>/<app>` startet notfalls den
      Container, Anmeldung davor bleibt erhalten
- [x] **Administratoren sind root im eigenen Container.** Ohne `no-new-privileges`, ohne
      `cap_drop`, mit `sudo`-Regel — sonst liesse sich dort nichts nachinstallieren.
      Für alle anderen bleibt beides scharf
- [x] **Rollende Anmeldung** mit einstellbarer Frist (30 min – 48 h, ab Werk 8 h).
      Vorher lief der Zugang nach 15 Minuten ab, egal ob jemand arbeitete
- [x] **Vier Fehler behoben**, alle erst beim echten Benutzen sichtbar. Sie stehen mit Symptom,
      Ursache und Reparatur im Handbuch Kapitel 12:
      1. Sessions meldeten sich als `running`, bevor Traefik ihre Route kannte → Schutzwall-Seite
         „Diese Sitzung läuft nicht mehr" direkt nach dem Start
      2. Ein zweiter Container desselben Nutzers überschrieb `~/.kasmpasswd` des ersten → 401 aus
         dem Nichts auf einer laufenden Session
      3. Das geerbte `custom_startup.sh` des Basisimages startete VS Code alle drei Sekunden neu
         → 119 leere Fenster, 2,5 GB belegt, schwarzer Bildschirm. Arbeitsplatz-Images bringen
         jetzt ein Startskript mit, das nichts startet; bereits gebaute Images bekommen es als
         Bind-Mount
      4. Die API startete Anwendungen mit festem Display gar nicht, weil sie annahm, das Image
         habe es schon getan — was nur stimmte, solange Fehler 3 bestand
- [x] **Ein Zuhause, ein laufender Container**: OTA lehnt eine zweite Session ab, die sich dasselbe
      Profil teilt, und nennt den Ausweg (eigenes Profil unter Persistenz). Zwei Container auf einem
      Home haben zweimal Schaden angerichtet — die Ablehnung ist die ehrlichere Antwort
- [x] **Fenstersturm-Wache** in `tests/e2e.mjs`: prüft im Container nach, wie viele
      Anwendungsfenster auf Display :1 offen sind. Fehler 3 war an der Oberfläche unsichtbar

**Erreicht**: Ein Nutzer öffnet seinen Arbeitsplatz und startet darin VS Code, ein Terminal und
den Dateimanager — jedes formatfüllend auf einem eigenen Display, alle im selben Container mit
gemeinsamem `/home`. Displays entstehen erst beim Klick und werden beim Schliessen abgebaut.

Die **Zwischenablage-Brücke** steht ebenfalls: Kopieren in einer App, Einfügen in der anderen
funktioniert in beide Richtungen, mit Umlauten und mehrzeiligem Code. Sie startet automatisch beim
ersten App-Start und folgt den Rechten des Workspace.

**Nachgezogen am 2026-08-27**, nachdem der Arbeitsplatz das erste Mal wirklich benutzt wurde: Der
Stream wächst jetzt mit dem Fenster, jede Anwendung bekommt einen eigenen Tab und lässt sich als
Verknüpfung auf den Desktop legen, Administratoren sind in ihrem Container root, und die Anmeldung
läuft nicht mehr nach 15 Minuten ab. Zwei Fehler, die nur im echten Betrieb auftraten, sind behoben.

**Noch offen in M4**: Der klassische XFCE-Desktop als zusätzliche Ansicht, `oom_score_adj` für die
Session-Prozesse, und die ereignisgesteuerte statt abfragende Brücke (braucht ein eigenes Basisimage).

---

## M5 — Golden Images · 2–3 Wochen

> **Gelöst am 2026-08-27.** Kasm löschte unsere Golden Images, weil sie das Label
> `com.kasmweb.image=true` vom Basisimage erbten. Der Builder löscht das Label jetzt —
> damit laufen OTA und Kasm nebeneinander, ohne dass an Kasm etwas umgestellt wird
> (`plan.md` §17.12).

- [x] `image_builds` mit Versionen, Digest, Größe, Build-Log, `is_current`
- [x] Build-Runner im Agent über **`docker buildx build --load`**, serialisiert,
      Timeout 45 min. Der klassische Builder legt auf einem Host mit
      containerd-Image-Store bei Multi-Plattform-Basisimages kein benutzbares Image ab
- [x] Nachprüfung 45 s nach dem Build, ob das Image noch im Store liegt — sonst
      gilt der Build als fehlgeschlagen und erklärt den Grund
- [x] Deklarativer Build-Layer: APT-Pakete, **VS-Code-Extension-Listen**, freies Setup-Skript
- [x] Version aktivieren und Rollback über die API; laufende Sessions bleiben unberührt
- [x] **Software einbauen über die Oberfläche** (Workspace-Editor → Software): Pakete als Chips,
      eigenes Skript, Build starten, Protokoll mitlesen, Fassung aktivieren. Bis dahin gab es die
      Build-Pipeline nur als API
- [x] **Pakete vorher prüfen**: OTA fragt das Image, ob es einen Namen kennt, bevor gebaut wird —
      und erkennt Ubuntus Snap-Platzhalter (`firefox` ist dort kein Programm, sondern ein Verweis).
      Erspart den häufigsten Fehlschlag: Debian-Name auf Ubuntu-Image
- [x] **Rezepte** für Software ohne brauchbares Paket (Firefox aus dem Mozilla-Depot, Chrome,
      VSCodium). Sie hängen ihre Schritte sichtbar an das eigene Skript an
- [x] **Anwendungen im Image finden** (`agent/otaagent/discover.py`): liest die `.desktop`-Dateien
      des gebauten Images und schlägt Name, Zeichen und Startbefehl vor. Niemand muss mehr wissen,
      wo eine Binärdatei liegt. Zuordnung zum bestehenden Katalog über Kennung **und** Binärname
- [x] **Image-Verwaltung** (Verwaltung → Images): Liste nach Herkunft (OTA / Kasm / Übrige), mit
      der Angabe, welcher Workspace ein Image benutzt. Holen per Adresse mit Fortschritt,
      Entfernen nur für Unbenutztes und Nicht-Kasm. Im Editor lässt sich die Adresse frei eintragen
- [x] **Workspace löschen** über die Oberfläche, mit Nennung der Folgen. Der Endpunkt gab es
      bereits, der Knopf fehlte — und er verweigert jetzt, solange Sessions laufen
- [x] **Rezept-Bauer** (`api/ota/recipes.py`, `web/src/screens/RecipeBuilder.tsx`): Rezepte liegen
      in der Datenbank statt fest im Frontend und entstehen aus wenigen Fragen. Fünf Muster —
      APT-Depot, `.deb` von einer Adresse, Archiv nach `/opt`, AppImage, freies Skript. Das
      erzeugte Skript steht daneben und lässt sich ändern; erzeugt wird auf dem Server, damit
      Vorschau und Bau nicht auseinanderlaufen
- [x] **Eigene Registry** im Stack (`registry:2`): Jedes gebaute Golden Image landet dort, und
      fehlt es lokal, holt der Agent es beim Sessionstart von dort. Gemessen: Image entfernt,
      Session gestartet, Image wieder da. Auf 127.0.0.1 veröffentlicht — Docker verlangt für
      localhost kein TLS, das erspart Zertifikat und `daemon.json`
- [x] **Bearbeiten im Hauptfenster** statt in einer 560-px-Seitenleiste: `Workspaces / Arbeitsplatz`
      mit Reitern, 1116 px Arbeitsfläche. Die Seitenleiste bleibt für kurze Formulare
- [x] **Drei Fehler beim echten Benutzen gefunden und behoben** (Handbuch Kapitel 12):
      Electron-Anwendungen brauchen `--no-sandbox` — ohne den Schalter bleibt der Bildschirm
      schwarz, und die `.desktop`-Datei sagt nichts darüber; erkannt wird es jetzt an der Datei
      `chrome-sandbox` neben dem Programm. Mehrere `.desktop`-Dateien auf dasselbe Programm
      lieferten den falschen Aufruf (`thunar --bulk-rename` statt `thunar`) — es gewinnt jetzt der
      schlichteste. Und die Displaynummer kam aus der Katalogposition, wodurch die Grenze von sechs
      für die Kataloggrösse galt statt für gleichzeitig offene Anwendungen
- [x] **Live-Log per SSE** (`/builds/{id}/stream`). Was sich ändert und was nicht: Der Server fragt
      den Agent weiterhin im Zwei-Sekunden-Takt ab — anders kommt man an den Fortschritt von
      `docker build` nicht heran. Weg ist die Abfrage des *Browsers*: Er bekommt nur noch den
      Zuwachs, und zwar sobald er da ist. Bei einem Protokoll von mehreren hundert Kilobyte ist das
      der Unterschied zwischen einem ruhigen Fenster und einem, das ruckelt. Fällt der Strom aus,
      übernimmt die alte Abfrage — lieber langsam als blind
- [x] **Auflösung je App** im Katalog: NULL erbt die des Arbeitsplatzes. Sie gilt ab dem
      **nächsten** Start dieser Anwendung — ein laufendes Display wird nicht umgestellt, wie bei
      allen Ressourcen in OTA. Geprüft in `scripts/test-clipboard-bridge.sh`: setzen, Anwendung neu
      starten, im Container nachmessen, zurückstellen
- [x] **Skeleton-Teilbaum je App** (2026-09-01) — unter *Workspaces → Skeleton* oben umschaltbar.
      Er kommt beim **ersten Start dieser Anwendung**, nicht beim Start des Arbeitsplatzes, und
      bevor die Anwendung läuft: andersherum legte sie erst ihre Voreinstellungen an und der
      Teilbaum überschriebe hinterher, was der Mensch schon sieht. Gemerkt wird das im Zuhause
      (`~/.ota/app-skeleton/<app>`) und nicht in der Datenbank — `set_apps` ersetzt den Katalog
      komplett, eine daran hängende Buchführung wäre nach jeder Änderung weg
- [x] **Symbole aus den Paketen** (2026-09-02) — bisher trug jede Anwendung nur ein Zeichen aus
      einer festen Liste. Das echte Symbol steht in derselben `.desktop`-Datei, die OTA ohnehin
      liest; wo die Datei dazu liegt, regelt die Freedesktop-Spezifikation. Gemessen an einem
      echten Arbeitsplatz-Image: **16 von 16** brachten eins mit.

      Zwei Entscheidungen dabei, beide gemessen statt geraten. **Verkleinert wird in der API**, auf
      128 Pixel: VSCodium liefert 428 KB, und ungeprüft läge das in der Datenbank und in jeder
      Antwort. Und ausgeliefert wird es unter einer **eigenen Adresse** statt als Datenadresse im
      Katalog — der wiegt sonst 140 KB, und das Dashboard lädt ihn alle 15 Sekunden neu. Ein
      Fingerabdruck im Anhang sorgt dafür, dass nach einem Image-Update trotzdem das neue kommt.

      Das Dekodieren liegt bewusst in der API und nicht im Agent: Hier wird ein Bild aus einem
      fremden Paket verarbeitet, und der Agent ist der einzige Dienst mit dem Docker-Socket
      ([ADR-002](docs/adr/002-nur-der-agent-fasst-docker-an.md))
- [x] Extensions beim **Build** installieren, nicht beim Start
- [x] **Sichtbarkeit je App und Gruppe** — für den Fall, dass eine Lizenz nicht für alle reicht.
      Leer heisst „für alle", sonst wäre jeder bestehende Katalog mit dem Einführen der Regel
      leergeräumt worden. Die Liste im Dashboard ist gefiltert, **die Absicherung sitzt beim
      Start**: Ein Aufruf mit fremdem Kürzel wird abgewiesen, auch am eigenen Arbeitsplatz.
      Nicht als `group_template_apps`-Tabelle, sondern als Liste an der App: `set_apps` ersetzt
      den ganzen Katalog, die Zeilen bekämen bei jedem Speichern neue Kennungen, und eine daran
      hängende Zuordnung wäre jedes Mal weg. Beim Löschen einer Gruppe wird ihre Kennung aus den
      Katalogen genommen
- [x] **Gemeinsame Ablage** (`agent/otaagent/shared.py`, Verwaltung → Ablage): ein Ort für
      Dateien, die in jeden Arbeitsplatz sollen. Liegt dort unter `/mnt/ota` **am Einhängepunkt
      schreibgeschützt** und als Verweis `~/Gemeinsam`. Hochladen per Ziehen und Ablegen, nur für
      Berechtigte; ausgeführt im Agent, weil die API das Dateisystem des Hosts nicht anfasst
- [x] **Skript beim Sessionstart** je Workspace (`start_script`): läuft als Nutzer im Container,
      mit `$OTA_SHARED` auf die Ablage. Für alles, was ins Home gehört, aber nicht ins Image.
      Scheitert es, startet der Arbeitsplatz trotzdem
- [x] **Fehlende Spalten beim Start ergänzen** (`api/ota/schema_sync.py`): `create_all` legt
      Tabellen an, aber keine Spalten — eine neue Spalte legte am 2026-08-27 eine laufende Anlage
      lahm. Ergänzt wird nur; Löschen, Umbenennen und Typwechsel bleiben Alembic vorbehalten
- [x] **Skeleton-Profile** (`agent/otaagent/skeleton.py`, Workspace-Editor → *Skeleton*): ein
      Verzeichnisbaum je Workspace mit Datei-Browser, Ziehen und Ablegen. Kommt beim **ersten**
      Start ins leere Zuhause; einzelne Pfade lassen sich **durchsetzen** und überschreiben dann bei
      jedem Start. Dass Letzteres die Ausnahme ist, steht auch so in der Oberfläche — ein Zuhause
      gehört dem Menschen, der darin arbeitet. Punktdateien sind hier erlaubt (anders als in der
      gemeinsamen Ablage): Ein Skeleton besteht grösstenteils aus ihnen
- [x] **Eine einzelne Fassung von Hand entfernen** — für einen Fehlversuch oder einen Probelauf.
      Die aktive nicht: Sie zu löschen liesse die Vorlage auf ein Image zeigen, das es nicht mehr
      gibt. Nebenbei räumt der Testlauf damit hinter sich auf, statt bei jedem Durchgang eine
      „Prüflauf"-Fassung in der Liste des Administrators zu hinterlassen
- [x] **Alte Fassungen werden wirklich aufgeräumt.** `KEEP_VERSIONS = 3` stand seit dem ersten Tag
      im Code und wurde nie angewendet; aufgefallen ist das erst, als das Einfrieren dazukam und
      Fassungen schneller wuchsen als beim Bauen. Die aktive bleibt immer, auch wenn sie älter ist.
      Nebenbei ein Fehler um genau eine Fassung: Über die geladene Beziehung `tpl.builds` gerechnet
      kennt die Liste die eben angelegte Fassung noch nicht — jetzt wird ausdrücklich abgefragt
- [x] **Paketlisten fliegen aus der Container-Sicherung** (`/var/lib/apt/lists`,
      `/var/lib/dpkg/info`). Ein einziges `apt-get update` legte dort 60 MB ab, und in einer
      Sicherung ist davon nichts wert: in Sekunden wieder geholt, beim Zurückspielen ohnehin
      veraltet. Aufgefallen, weil eine Container-Sicherung ohne erkennbaren Grund von 2 MB auf
      68 MB sprang, nachdem jemand im Container etwas nachinstalliert hatte
- [x] **`start_script` wurde in der Oberfläche nie gespeichert.** Das Feld liess sich bearbeiten,
      und `toPayload` liess es weg — die Eingabe verschwand beim Speichern stillschweigend.
      Aufgefallen beim Anbau des Skeleton-Reiters
- [x] **„Session einfrieren"** (`agent/otaagent/freeze.py`): Im eigenen Arbeitsplatz einrichten,
      Vorschau ansehen, als neue Fassung einfrieren. Drei Dinge sind dabei wichtiger als der
      `docker commit` selbst:
      1. **Das Zuhause kommt nicht mit** — es ist ein Bind-Mount, und `docker commit` nimmt keine.
         Das ist die richtige Grenze: Ein Zuhause enthält Schlüssel, und ein Image bekommen alle
      2. **Der Geheimnis-Filter warnt, und ohne ausdrückliche Bestätigung wird abgelehnt.** Eine
         Vorschau, die sich übergehen lässt, ist Dekoration. Verdächtige Pfade stehen oben und
         farbig; das Protokoll der Fassung nennt jeden einzeln
      3. **Ein pausierter Container laesst `docker commit` unbegrenzt haengen** — ohne Fehler,
         ohne Meldung. Zwei Wege dorthin, beide gemessen: vorher pausiert (der Leerlauf-Aufräumer),
         oder mittendrin pausiert. Behoben an zwei Stellen: Der Agent prüft den Zustand selbst und
         weckt den Container — er traut der Sicht der API nicht ([ADR-002](docs/adr/002-nur-der-agent-fasst-docker-an.md)) —,
         und der Aufräumer lässt Sessions in Ruhe, an deren Workspace gerade gebaut wird
      4. **`/etc/sudoers.d/ota-admin` wird immer entfernt** — sonst bekäme jeder Nutzer des Images
         root, und aus einer Ausnahme für eine Person wäre die Voreinstellung für alle geworden.
         Danach wird sie im laufenden Container wieder hingelegt: Wer ein Image baut, soll dabei
         nicht sein eigenes `sudo` verlieren
- [x] **Eigenes Basisimage** `ota/base-xfce` (2026-09-01) — Ubuntu 24.04 + XFCE + KasmVNC 1.4.0
      aus dem offiziellen Release, **965 MB statt 20 GB**. Es trägt vorerst `:test`, keine Vorlage
      zeigt darauf, `ota/arbeitsplatz` bleibt unberührt. `scripts/build-base-image.sh --pruefen`
      misst 27 Punkte gegen den Vertrag mit dem Agent: Port 6901, Kennung 1000, `.kasmpasswd`
      unter dem Namen `kasm_user` (das ist die Schnittstelle — OTA setzt vor dem Stream einen
      Basic-Auth-Header damit), ein zweites Display, eine Anwendung darauf, die Zwischenablage
      ereignisgesteuert. Mit `OTA_PRUEFE_JAVA=1` kommt Abnahmefall 7 dazu.
      **Lizenz geprüft**: KasmVNC ist GPL-2+, das Einbauen ist erlaubt und sauberer als das
      Ableiten von `kasmweb/*` (THIRD-PARTY-NOTICES.md)
- [x] **Erweiterungen in der Oberfläche**, mit dem Hinweis daneben, dass sie ausschliesslich in
      Microsofts VS Code landen: VSCodium hat seinen eigenen Satz aus Open VSX, und dieselbe
      Kennung ist dort nicht dieselbe Installation. Vorher nahm die Schnittstelle die Liste
      entgegen, die Oberfläche bot sie aber nicht an — der Hinweis hatte gar keinen Ort

**Vorher zu klären**
- [x] ~~Cursor-Lizenz klären~~ — Cursor bleibt draussen (`plan.md` §17.10)
- [x] **Sicherstellen, dass VSCodium nicht auf den MS-Marketplace zeigt** — geprüft und dauerhaft
      abgesichert: Jeder Build liest nach dem Bauen die `product.json` der gefundenen Editoren und
      protokolliert deren `extensionsGallery.serviceUrl`; zeigt ein Nicht-Microsoft-Editor auf
      Microsofts Marktplatz, steht eine Warnung im Protokoll. Im aktuellen Image zeigt VSCodium auf
      `open-vsx.org`. Ein `grep` allein taugt dafür nicht — der Name steht auch unter
      `extensionAllowedBadgeProviders` und ist dort harmlos

---

## M6 — Identität ~~& Netzlaufwerke~~ · abgelöst und gestrichen

Erst mit dem Arbeitsplatz sinnvoll (`plan.md` §9.4).

> **Die Identitäts-Hälfte ist mit M11 erledigt und ersetzt.** Die eigene LDAP-Anbindung
> (`directory.py`) war ab 2026-08-28 eingefroren und ist am **2026-09-04 wirklich entfernt** —
> samt Tabelle, Endpunkten, Formular und der halben Prüfreihe; ein
> Verzeichnis bindet man jetzt in Keycloak an, eingerichtet über OTAs Oberfläche
> ([`auth-roadmap.md`](auth-roadmap.md), Etappe C).
>
> **Die andere Hälfte — Kerberos und Netzlaufwerke — ist am 2026-09-03 gestrichen** (Entscheidung
> des Betreibers). Sie bräuchte ein KDC und einen Dateiserver; ohne beides liesse sich nichts davon
> ehrlich prüfen, und ungeprüft gebaut ist genau der Teil, den man nicht ungeprüft bauen darf. Die
> Analyse der vier Wege bleibt unten stehen — sie erklärt, warum die Passwort-Durchreichung
> draussen bleibt, und die gilt weiter. **M6 ist damit abgeschlossen.**

- [x] **Eine Session ohne Container stand für immer im Weg.** Sie zählte als „live", der nächste
      Startversuch bekam sie zurück statt einer neuen — und der Arbeitsplatz liess sich nicht mehr
      starten, während die Oberfläche „starting" zeigte. Dorthin führte ein Zeitablauf beim Warten
      auf die Traefik-Route; danach prüfte nichts mehr nach. Jetzt sieht der Start selbst nach, ob
      der Container überhaupt noch existiert, und der Aufräumer räumt solche Leichen weg
- [x] **LDAP/AD** (`api/ota/directory.py`, `api/ota/identity.py`): LDAPS und StartTLS,
      Login-Attribut wählbar, Gruppen-Zuordnung, Anlage beim ersten Anmelden, Auffrischen bei
      jeder Anmeldung, nächtlicher Abgleich um 3 Uhr, Prüf-Knopf mit Vorschau der Gruppen.
      Geprüft gegen ein echtes OpenLDAP im Container (`scripts/test-ldap.sh`, 29 Prüfungen)
- [x] **Ein lokales Konto ist unantastbar.** Wo ein Passwort geprüft wird, entscheidet allein
      `users.auth_provider` — nie die Anfrage, nie das Verzeichnis. Ein gleichnamiger
      Verzeichniseintrag kann ein lokales Konto weder übernehmen noch verändern. Das
      Testverzeichnis enthält deshalb absichtlich einen Eintrag `bmetallica`; die Prüfung besteht
      darin, dass er **nicht** hereinkommt
- [x] **Ein Ausfall des Verzeichnisses reisst die lokale Anmeldung nicht mit** — und läuft nicht
      in einen Zeitablauf: gemessen 33 ms bis zur Ablehnung. Ein Ausweichen auf einen lokal
      gespeicherten Hash gibt es bewusst nicht; das wäre ein zweiter Weg genau dann offen, wenn
      das Verzeichnis nicht widersprechen kann
- [x] **Wer im Verzeichnis verschwindet, wird deaktiviert — nicht gelöscht.** Zuhause,
      Sicherungen und Protokollspur bleiben; Löschen entscheidet ein Mensch
- [x] `identity_configs`; Standard ist **abgeschaltet** — die einzige Einstellung, bei der ein
      Fehler Menschen aussperrt
**Kerberos und Netzlaufwerke — gestrichen (2026-09-03).** Dafür reicht ein LDAP-Server nicht: es
bräuchte ein echtes AD mit KDC und Dateiservern, und ohne eines liesse sich nichts davon ehrlich
prüfen. Wer Laufwerke im Arbeitsplatz braucht, verbindet sie dort selbst (Weg 3) oder hängt sie
über den Container-Start ein.

- ~~Weg 2 (Kerberos-Ticket-Injektion) als Standard, Mount per `sec=krb5`~~ — **gestrichen**
- ~~Ticket-Erneuerung im Container per `k5start`~~ — **gestrichen**
- ~~UID/GID aus dem Verzeichnis (`uidNumber`/`gidNumber`) beim Start setzen~~ — **gestrichen**
- Weg 3 (Nutzer verbindet selbst) bleibt der Weg — er braucht nichts von OTA
- ~~Weg 4 (Passwort-Durchreichung)~~ — **wird nicht gebaut.** Ausdrücklich verworfen; mit Keycloak
      dazwischen ist sie noch weniger zu rechtfertigen als vorher. Ein Punkt, den man „später mal"
      offenhält, wird irgendwann gebaut — deshalb steht er hier als Nein und nicht als Kästchen
- Zugangsdaten nur über `tmpfs` mit `0600` — **nie** als Umgebungsvariable, nie ins Profil, nie
      ins Image. Die Regel bleibt stehen, auch ohne Kerberos: sie gilt für jedes Geheimnis, das
      jemals in einen Container gerät
- ~~Weg 1 (S4U2Proxy) evaluieren~~ — **gestrichen** mit dem Rest

---

## M7 — Migration & Härtung · 1–2 Wochen

- [x] **Die Sicherung war unvollständig** (behoben 2026-08-28). `make backup` sicherte die
      Datenbank und die Zuhause — nicht aber `skeletons`, `shared` und `userfiles`, also genau
      das, was jemand von Hand angelegt hat und was sich weder aus Code noch aus einem Image
      wiederherstellen lässt. Ein zurückgespielter Stand kam ohne all das zurück, und es wäre erst
      aufgefallen, wenn man es braucht. Dazu Keycloaks eigene Datenbank; ohne sie kämen Nutzer aus
      einer Wiederherstellung zurück, die auf Identitäten ohne Gegenstück zeigen
- [x] Nutzer `bmetallica` in `admins` + `users` (über `make admin`)
- [x] `scripts/migrate-kasm-profile.sh` — idempotent, mit Probelauf und Abnahmemodus
- [x] Profil in einen **Arbeitsplatz** überführt (805 MB Rohdaten → 63 MB)
- [x] Abnahme bestanden: Einstellungen, Extensions, SSH- und GPG-Schlüssel, XFCE-Layout
- [x] **Container-Härtung**: `no-new-privileges`, `cap_drop: ALL`, seccomp-Standardfilter,
      `pids_limit: 4096`, `shm_size: 1g`, eigenes Netz. Für Administratoren fallen die ersten
      beiden weg, sonst liefe `sudo` nicht (`plan.md` §15.1)
- [x] **`SYS_ADMIN` entfernt.** Die Fähigkeit stand vom ersten Tag an für jeden Arbeitsplatz im
      Code, ohne Begründung — sie erlaubt Einhängungen und eigene Namespaces und ist praktisch
      gleichbedeutend mit root auf dem Host. Sie neben `no-new-privileges` zu setzen und dann zu
      behaupten, ein Nicht-Administrator komme nicht an root, war ein Widerspruch. Der Verdacht,
      Chrome und Electron brauchten sie, stimmt nicht: die laufen über `--no-sandbox`. Zwei
      Folgen, beide geprüft: Firefox fällt auf eine schwächere interne Sandbox zurück und startet
      normal; AppImages hängen sich nicht mehr per FUSE ein, weshalb das Rezept jetzt
      `APPIMAGE_EXTRACT_AND_RUN=1` setzt (Handbuch, Kapitel 11)
- [x] **Netzsegmentierung** — erste Fassung: Session-Container hingen in `ota_sessions` und
      zusätzlich im öffentlichen Netz (für Traefik); die Datenbank lag in keinem von beiden.
      Geprüft in `scripts/test-authz.sh` mit einem `/dev/tcp`-Versuch auf `ota-db:5432`.
      **Das hat nicht gereicht** und ist mit M12 ersetzt: Auf derselben Brücke greift `iptables`
      gar nicht, solange `br_netfilter` nicht geladen ist — die Arbeitsplätze erreichten einander,
      den Wirt und das ganze Firmennetz. Ein Sammelnetz gibt es nicht mehr
- [x] **Security-Review der Auth- und Autorisierungspfade** — drei Befunde, alle behoben und alle
      mit einer Prüfung in `scripts/test-authz.sh` festgenagelt:
      1. **`sessions.view_all` reichte bis auf den fremden Bildschirm.** Das Recht heisst in der
         Oberfläche „Alle Sessions sehen und beenden", benutzte für `/s/<id>/` aber dieselbe
         Funktion wie die Liste. Getrennt in `owns_session` (verwalten) und
         `may_attach_to_session` (daransitzen); Letzteres verlangt Eigentum oder vollen Admin
      2. **Fehlversuche beim zweiten Faktor zählten nicht mit.** Bei bekanntem Passwort war ein
         sechsstelliger Code damit beliebig oft ratbar — drei davon zu jedem Zeitpunkt gültig.
         Gleiches galt für die Rückfallcodes. Sie zählen jetzt auf dieselbe Sperre ein
      3. **Ein unbekanntes Konto antwortete schneller als ein bekanntes.** Die Meldung war schon
         gleich, die Dauer nicht: ohne Argon2-Durchlauf war die Antwort messbar früher da. Jetzt
         läuft ein Leerlauf gegen einen Blindhash
      4. **Ein `PUT` ohne Gruppenzuweisung nahm sie allen weg** — der Workspace verschwand wortlos
         von jedem Dashboard. `group_ids` ist jetzt `None`-fähig: nicht mitgeschickt heisst „lass
         stehen", eine leere Liste heisst „niemand mehr"
- [x] **Sicherung und Wiederherstellung** (`plan.md` §11.2): ein Wurzelverzeichnis für
      alles, damit später ein NFS ohne Änderung an OTA darunterpasst. Profile ohne
      Caches, Container nur als Differenz, Zeitplan mit Nachholen, Aufbewahrung
      täglich und wöchentlich. Wiederherstellung lehnt bei laufender Session ab und
      legt den bisherigen Stand beiseite statt ihn zu löschen.
      Geprüft durch `scripts/test-backup.sh`
- [x] **Datenbanksicherung im Zeitplan** — `pg_dump` über `docker exec` im DB-Container,
      damit der Agent weder Client noch Zugangsdaten braucht
- [x] **Wiederherstellung der Datenbank vollständig durchgespielt** (2026-08-27):
      Markierungsnutzer angelegt, zurückgespielt, Nutzer verschwunden, alles Übrige
      unversehrt. `scripts/restore-db.sh` legt vorher eine Sicherheitskopie an
- [x] **Container-Sicherungen zurückspielen** über die Oberfläche, in den laufenden
      Arbeitsplatz
- [x] **Monitoring**: `/healthz` prüft jetzt wirklich etwas (Datenbank und Agent; 503 nur, wenn
      die Datenbank fehlt — ohne Agent lässt sich anmelden und nachsehen, nur nichts starten).
      `/metrics` im Prometheus-Textformat, hinter einem Merkmal (`OTA_METRICS_TOKEN`) oder einer
      Admin-Anmeldung: Die Zahlen verraten, wie viele Menschen hier arbeiten und wann
- [x] **Kontingent je Zuhause und Untergrenze für den freien Plattenplatz**, beide im
      Verwaltungsbereich einstellbar, 0 schaltet ab. Wirkt beim Start einer Session, nicht beim
      Schreiben einer Datei — kein Dateisystem-Kontingent, sondern eine verständliche Ablehnung
      statt eines Containers, der mitten in der Arbeit stehenbleibt. Gemessen werden belegte
      Blöcke, im Agent zehn Minuten gepuffert. Ab 80 % steht ein Hinweis auf dem Dashboard, ab
      100 % steht dort, warum nichts mehr startet. Der Speicher-Preflight gegen einen OOM-Kill
      stand schon
- [x] ~~HSTS~~ — entfällt, solange es bei der lokalen CA bleibt (`plan.md` §17.2)
- [x] ~~Umzug auf 443~~ — entfällt. OTA bleibt auf 8443, der Port ist frei
      einstellbar, und Kasm läuft dauerhaft daneben weiter (`plan.md` §17.13)
- [x] ~~Rollback-Plan~~ — entfällt, weil Kasm gar nicht erst abgeschaltet wird

---

## M8 — Kasm-Kompatibilität · ✅ erledigt

Das Feature aus `plan.md` §1.2 und §9.8. Gegen alle drei echten Registries geprüft.

- [x] `registries` und `registry_entries` nach `plan.md` §9.7
- [x] Katalog von `{url}/{schema}/list.json` laden, ablegen, per `modified` aktualisieren.
      Gelesen wird im Agent — es ist ein Griff nach draussen, dieselbe Trennung wie bei Docker
- [x] Durchsuchbarer Katalog im Admin-UI mit Kategorien und Icons
- [x] **Icons über einen eigenen Umweg** — `img-src 'self'` lässt keine fremde Bildquelle zu, und
      sie je Registry aufzuweichen wäre für ein Symbol ein schlechter Tausch. Der Umweg holt nur,
      was unterhalb der Adresse dieser Registry liegt, und nur Bilder
- [x] Import erzeugt ein Template mit `mode: single_app`, abgeschaltet, mit eigenem Profil
- [x] **Nicht die neueste Fassung, sondern die neueste stabile** — bei AlmaLinux 8 zeigen die
      beiden neuesten auf `:develop`, die letzte davon mit Grösse 0
- [x] **Architektur des Hosts prüfen** — unpassende Einträge werden gezeigt, aber nicht zum
      Übernehmen angeboten; sie zu verschweigen erzeugt nur die Frage, warum sie fehlen
- [x] **`uncompressed_size_mb` anzeigen und warnen**, bevor gezogen wird
- [x] Hinweis im Import-Dialog: Registries sind eine Vertrauensentscheidung; Lizenz des Images
      gilt unverändert (`plan.md` §3)
- [x] **Vorgeschlagen statt vorkonfiguriert**: Kasm Technologies (86), Kasm AI (11),
      LinuxServer.io (2). Eingetragen wird keine von selbst — das ist eine Entscheidung
- [x] Fehler beim Aktualisieren bleiben an der Registry stehen, statt nur einmal zu blinken
- [x] Registry entfernen lässt übernommene Vorlagen bestehen
- [x] ~~Signaturprüfung~~ — entschieden: keine. Der Schlüssel liegt bei Kasm; ohne ihn wäre die
      Prüfung Theater. Registries sind eine Vertrauensentscheidung

**Offen bleibt:** Beim Import eine andere Fassung wählen. Die Schnittstelle kann es
(`available_tags`), die Oberfläche bietet es noch nicht an.

---

## M11 — Zentrale Identität · ✅ erledigt am 2026-08-29

**Eigenes Dokument:** [`auth-roadmap.md`](auth-roadmap.md).

Der Umbau von „OTA ist sein eigener Identity Provider" zu „OTA ist das Anwendungsportal über einem
zentralen **Keycloak**" (entschieden 2026-08-28; Zitadel, Authelia, Dex, Ory und Kanidm sind an
OTAs Anforderungen gescheitert, authentik unterlag der konservativeren Wahl). Anlass ist Open WebUI: Sobald eine zweite Anwendung dazukommt, gibt es nur
noch schlechte Antworten — dreimal dieselben Menschen pflegen, Passwörter weiterreichen, oder
selbst OIDC-Provider werden.

Betrifft M6 unmittelbar: Die eigene LDAP-Anbindung ist ab 2026-08-28 **eingefroren** und fällt mit
dem Umstieg weg. Neue Wünsche an die AD-Anbindung sind ab jetzt Argumente für M11, keine Arbeit an
`directory.py`.

Sechs Entscheidungen sind getroffen (2026-08-28): Keycloak als Identity Provider, mitgeliefert im
Stack und wahlweise ein vorhandenes anbindbar — Bestandskonten werden übernommen und bekommen
einmalig neue Passwörter; es bleibt ein lokales Notfallkonto mit eigener zweiter Stufe; die zweite
Stufe wandert im Übrigen nach Keycloak; die eigene LDAP-Anbindung bleibt bis zur letzten Etappe als
Rückweg. Alles Weitere steht im eigenen Dokument.

- [x] **Etappe A erledigt am 2026-08-28**: Keycloak 26.7 im Stack unter `/auth`, Realm `ota`,
      Dienstkonto mit benannten Rechten, Rechteprüfung in der Oberfläche, in `/healthz` und in
      der Sicherung. **Die Anmeldung ist unverändert** — sie läuft weiterhin über OTA selbst
- [x] **Etappe B erledigt am 2026-08-28**: OTA meldet sich über Keycloak an — Code-Fluss mit
      PKCE, Token-Tausch ohne Browser für die Prüfreihen, Back-Channel-Logout, zweite Stufe je
      Rolle. Die Desktop-Verknüpfungen überstehen es, weil Keycloak unter `/auth` **derselben**
      Herkunft liegt; das ist im e2e-Lauf gemessen. `/login` bleibt bis Etappe E die lokale Maske
- [x] **Etappe C erledigt am 2026-08-28**: Die AD-Anbindung lässt sich in OTAs Oberfläche
      einrichten, prüfen und abgleichen; Konten und Gruppen verwaltet OTA über die Admin-API —
      die Keycloak-Konsole bleibt für den Alltag zu
- [x] **Etappe D erledigt am 2026-08-28** (bis auf einen Schritt auf dem anderen Rechner): Fremde
      Web-Anwendungen im Katalog, eigenes Recht, Liste erlaubter Ziele, OIDC-Client aus OTA heraus.
      Open WebUI 0.9.6 nimmt OIDC nur über Umgebungsvariablen — die muss jemand dort eintragen
- [x] **Etappe E erledigt am 2026-08-28**: Vier Bestandskonten übernommen, Notzugang `notfall`
      eingerichtet und geprüft, Rückweg je Konto vorhanden. Die Prüfreihen melden sich als
      Notzugang an — damit steht kein persönliches Passwort mehr in `deploy/.env`

**Danach, aus dem ersten echten Betrieb** (2026-08-29). Alles hier kam nicht aus dem Entwurf,
sondern daraus, dass jemand es benutzt hat:

- [x] **Abmelden meldet ab** — auch bei Keycloak. Vorher endete nur OTAs Sitzung, und der nächste
      Klick meldete denselben Menschen wortlos wieder an
- [x] **E-Mail ist Pflichtfeld**, geprüft und eindeutig — mit internen Adressen (`chef@firma.local`).
      Eine angebundene Anwendung erkennt Menschen daran wieder; ohne Adresse kommt niemand hinein
- [x] **Änderungen an Konten wandern nach Keycloak** (E-Mail, Sperre, Gruppen, zweite Stufe). Das
      war die eigentliche Lücke hinter „email is missing"
- [x] **`/ca.crt`** — OTA gibt seine CA heraus, ohne Anmeldung. Eine fremde Anwendung ruft die
      Anmeldung serverseitig auf; dort gibt es kein „trotzdem fortfahren". Dazu die vollständige
      Konfiguration zum Übertragen im Anwendungs-Bildschirm
- [x] **Die Anmeldemaske trägt OTAs Farben** (`deploy/keycloak-theme/ota`), Themenspeicher
      abschaltbar — sonst ändert man eine Datei und sieht nichts
- [x] **Betrieb hinter einem weiteren Reverse Proxy**: `OTA_TRUSTED_PROXIES` in `deploy/.env`,
      daraus wird Traefiks statische Konfiguration erzeugt. Ohne das führte die Anmeldung an die
      interne Adresse — eine andere Herkunft, an der die Desktop-Verknüpfungen hängen
- [x] **`make admin` legt zwei Konten an**: den Alltagszugang in Keycloak und den Notzugang lokal.
      Vorher entstand ein lokales Konto, während die Startseite zu Keycloak führte — man richtete
      eines ein, mit dem man sich nicht anmelden konnte
- [x] **`make up` wartet auf Keycloak**, bevor es den Realm einrichtet

---

## M9 — Optionale Erweiterungen · abgeschlossen

- [x] ~~**OIDC** mit PKCE, Claim→Gruppen-Mapping~~ — mit M11 erledigt (`auth-roadmap.md`)
- [x] **WebAuthn/Passkeys** (2026-09-02) — als zweiter Faktor neben dem Einmalkennwort, nicht
      statt seiner. Entschieden: **angeboten, nicht verlangt.** Wer einen Passkey hinterlegt, weist
      sich damit aus; wer keinen hat, bekommt weiter die Codeabfrage. In OTA war dafür keine Zeile
      nötig — der Fluss steht in `scripts/keycloak-init.sh`, idempotent.

      **Der naheliegende Aufbau sperrt aus.** Beide Verfahren nebeneinander auf ALTERNATIVE zu
      stellen, gemessen am 2026-09-02: Wer die Rolle trägt und noch keins von beiden eingerichtet
      hat, kommt gar nicht mehr herein — die Anmeldung endet mit „Invalid username or password".
      Eine vorgemerkte Ersteinrichtung hilft nicht, denn vorgemerkte Aktionen laufen **nach** der
      Anmeldung. Deshalb zwei Unterflüsse: `ota-passkey` (mit der Bedingung „beim Nutzer
      eingerichtet") und `ota-einmalkennwort`, beide ALTERNATIVE. Der Aussperrfall wird bei jedem
      Testlauf gemessen, nicht geglaubt
- [x] **Nebenbefund**: Die Idempotenzprüfung der Rollenbedingung griff nie — sie suchte nach
      `authenticationConfig`, der einzelne Schritt heisst das Feld aber `authenticatorConfig`. Bei
      jedem `make identity` entstand eine neue Konfiguration, die alte blieb verwaist liegen
- ~~**Guacamole-Engine** für RDP/VNC-Ziele~~ — **gestrichen (2026-09-03).** Ein eigener
      Meilenstein mit eigener Abnahme für zwei Direktverbindungen; `HauptPC` und `VNC-HauptPC`
      laufen weiter als Kasm-Images
- ~~**code-server** als leichte Engine für reine Editor-Sessions~~ — **gestrichen (2026-09-03).**
      Überschneidet sich fast vollständig mit dem, was der Arbeitsplatz ohnehin kann; die
      Erweiterungen müssten zudem über Open VSX gehen (`plan.md` §3.1)
- [x] **Gemeinsame Gruppenlaufwerke** (2026-09-02) — die dritte Ablage neben der gemeinsamen und
      der eigenen. Je Gruppe ein Verzeichnis, in jedem Arbeitsplatz seiner Mitglieder unter
      `/mnt/gruppen/<name>` beschreibbar eingehängt, im Zuhause als „Gruppen". **Die
      Mitgliedschaft entscheidet, und sonst nichts** — auch ein Administrator kommt nur an die
      Laufwerke seiner eigenen Gruppen; wer wirklich hinein muss, trägt sich ein, und das steht im
      Protokoll. Ein Entzug wirkt im Browser sofort, im laufenden Container beim nächsten Start
      (einen Bind-Mount kann man einem laufenden Container nicht entziehen, ohne ihn zu beenden).
      Benannt nach der Kennung, nicht nach dem Namen — dieselbe Lehre wie bei den Profilen.
      Abschaltbar je Workspace, Vorgabe an
- [x] **Helles Gewand** (2026-09-02) — dunkel, hell oder „wie der Rechner", umschaltbar in der
      Leiste **und** auf der Anmeldemaske. Es liegt im Browser (`localStorage`) und nicht am
      Konto: eine Frage des Arbeitsplatzes, nicht der Identität. Nicht die Umkehrung des dunklen,
      sondern derselbe Gedanke in Hell — die vier Zustandsfarben bleiben, was sie sind, nur ihre
      Hintergründe werden kräftiger, weil ein Schleier auf Weiss verschwindet.
      Dafür mussten erst dreizehn Festfarben aus dem Regelwerk in Merkmale wandern; genau die
      wären beim Umschalten stehengeblieben. `tests/e2e.mjs` misst deshalb nicht das Aussehen,
      sondern den **Kontrast** in beiden Gewändern: Text muss sich überall vom Grund abheben.

      Zwei Funde beim Messen: Die Vorgabe musste **dunkel** werden statt „wie der Rechner" — die
      meisten Rechner melden hell, und OTA wäre beim nächsten Aufruf für fast alle plötzlich hell
      gewesen. Und die Keycloak-Anmeldemaske folgt jetzt mit: Sie liegt auf derselben Herkunft und
      liest denselben `localStorage`. Dort stand der Schriftzug im hellen Gewand weiss auf weiss —
      PatternFly setzt ihn mit `!important`; behoben über die Variable, mit der diese Regel
      rechnet, nicht mit einem Gegen-`!important`
- [x] **Branding** (2026-09-03) — Name, Akzentfarbe und Zeichen der Anlage, umstellbar unter
      **Einstellungen → Marke**. Drei Dinge und keins mehr: wie die Anlage heisst, welche Farbe
      heraussticht, welches Zeichen oben steht. Ein Farbwähler für Flächen, Text und Rahmen wäre
      der nächste naheliegende Schritt gewesen und hätte vor allem unlesbare Anlagen erzeugt.
      Das Zeichen liegt in der Datenbank und ist damit ohne Zutun mitgesichert; die Farbe geht
      über eine Zwischenstufe im Stylesheet (`--brand-accent`), damit beide Gewänder auf einmal
      folgen. **Die Anmeldemaske von Keycloak nimmt die Farbe mit** — über denselben
      `localStorage`-Weg wie das Gewand, also ohne Anfrage und ohne Aufblitzen; beim allerersten
      Besuch steht dort noch die Vorgabe. Handbuch [Kapitel 22](docs/wiki/22-marke.md)
- [ ] GPU-Durchreichung. Lässt sich hier nicht ehrlich bauen — die Maschine hat eine
      QEMU-Standard-VGA, keine GPU

---

## M12 — Das Netz der Arbeitsplätze · ✅ erledigt am 2026-09-04

Entstanden aus der Sicherheitsbetrachtung: Ein Arbeitsplatz erreichte den Wirt, das ganze
Firmennetz, die Sitzung des Kollegen und den Agent — und der Agent ist der einzige Dienst mit
schreibendem Docker-Socket. Das war die kürzeste Strecke von einem beliebigen Nutzer zu root auf
dem Wirt.

Der Entwurf mit allen Messungen steht in [`firewall.md`](firewall.md), die Bedienung im Handbuch,
[Kapitel 23](docs/wiki/23-netz.md).

- [x] **Ein `internal`-Netz je Sitzung**, angelegt vom Agent, mit fester Adresse je Paar aus Mensch
      und Vorlage (`net_leases`). Ohne feste Adresse liesse sich weder eine dauerhafte Portfreigabe
      setzen noch eine vorgelagerte Firewall auf einen Arbeitsplatz einstellen
- [x] **Ein Router** (`ota-firewall`) mit nftables, NAT, Routing und eigenem Namensdienst. Er ist
      der einzige Weg nach draussen — erreichbar für den Agent nur über einen **Unix-Socket**,
      nicht über einen Port: Er hängt in jedem Sitzungsnetz, und wer ihn erreicht, schreibt das
      Regelwerk
- [x] **Grundregelsatz, sichtbar in der Oberfläche** — TURN, die eigene Adresse, Namensdienst,
      Firmenproxy, Zeitserver. Je Zeile mit Grund und Herkunft, abgeleitet aus der `.env` und
      deshalb nicht änderbar. Eine unsichtbare Grundregel wäre eine Firewall, von der niemand
      weiss, was sie ohnehin durchlässt
- [x] **Profile je Vorlage** in drei Stufen (`abgeschottet` / `internet` / `aus`), zwei davon
      mitgeliefert. Die Stufe „aus" verlangt eine Begründung und steht im Protokoll; ein
      mitgeliefertes Profil dafür gibt es bewusst **nicht**
- [x] **Freigaben nach Adresse, Bereich oder Name**, global oder je Profil, Notiz verpflichtend.
      Namen funktionieren, weil der Router zugleich der Namensdienst ist und seine eigenen
      Antworten in die Regel schreibt — mit deren Lebensdauer
- [x] **Portfreigaben („+ NAT")** mit Frist, die durchgesetzt wird; sie hängen an Mensch und
      Vorlage und überleben den Feierabend
- [x] **Übersicht** mit Durchsatz und verworfenen Paketen je Arbeitsplatz. Live, nichts gespeichert
      — eine Zeitreihe daraus wären personenbezogene Daten
- [x] **19 Prüfungen, von innen gemessen** (`scripts/test-firewall.sh`), inklusive eines Neustarts
      des Routers. Am Regelwerk zu messen hätte nichts gebracht: Es stand dreimal vollständig da,
      und die Brücke des Wirts war trotzdem erreichbar
- [x] **Fünf animierte Diagramme** (2026-09-05, `scripts/netzfluss.py`) — die Reise eines Pakets je
      Stufe und je Freigabeart, in der README und in Kapitel 23. Sie beantworten die Frage, die in
      Prosa mühsam ist: *wo endet ein Paket, und warum?* Dafür kann das Handbuch **im Programm**
      jetzt Bilder darstellen — der Renderer kannte nur Links

**Was offen bleibt:** Der Router ist eine einzelne Stelle, an der alles hängt — startet er neu,
sind alle Arbeitsplätze kurz ohne Netz. Das ist der Preis dafür, dass es keinen Weg an ihm vorbei
gibt, und mit `restart: unless-stopped` plus Selbstheilung im Abgleich der beste Kompromiss, den
dieser Aufbau hergibt.

---

## M13 — Härtung für den Betrieb · ✅ erledigt am 2026-09-05

Aus der Sicherheits- und Datenschutzbetrachtung, nach Wirkung geordnet abgearbeitet. Die Befunde
selbst führt der Betreiber; hier steht, was daraus gebaut wurde.

- [x] **Zeichensatz mitgeliefert** statt von Google geladen — die einzige Drittlandübermittlung,
      die es je gab. Nachgemessen: keine Anfrage an einen fremden Host mehr
- [x] **Aufschalten wird protokolliert** (`session.attached`, ein Eintrag je Viertelstunde und
      Paar). Ohne das ist eine Betriebsvereinbarung über Fernhilfe nicht überprüfbar
- [x] **Dateirechte**: 0700 auf den Wurzeln, 0600 auf Archiven und Datenbankabzügen. Zwei
      Zuhause standen auf 777
- [x] **Passwortregel in Keycloak** — der Hauptweg war schwächer als der Notzugang
- [x] **Protokolle begrenzt**: 10 MB × 3 je Container, Dienste **und** Arbeitsplätze. Ohne Grenze
      schreibt Docker, bis die Platte voll ist — und dann steht alles gleichzeitig
- [x] **Bremse vor der lokalen Anmeldung**: zehn Versuche je Minute und Absender an Traefik, die
      Kontosperre je (Konto, Absender) statt je Konto, und ein Zähler **vor** dem Argon2-Durchlauf
- [x] **Aufbewahrungsfristen im Protokoll**: 90 Tage Verhalten, 365 Tage Verwaltung, täglich
      angewendet. Damit wächst in der Anlage nichts mehr ohne Frist
- [x] **Ungenutzten Endpunkt gelöscht**, der beliebige Befehle in beliebigen Containern ausführte

**Ausdrücklich nicht gebaut**, jeweils als Entscheidung festgehalten: Verschlüsselung im
Ruhezustand samt der TOTP-Startwerte, ein Streifen im Bild während des Aufschaltens (ein
Administrator sieht auch ohne OTA zu — ein Signal, dessen Fehlen nichts bedeutet, wäre eine falsche
Entwarnung), „Konto endgültig entfernen", und das Zumauern von Keycloaks Konsole.

---

## M10 — Skalierung · offen

Erst mit Hardware für die Zielgröße (`plan.md` §17.1).

- [ ] Mehrere Hosts; `sessions.host_id` ist vorgesehen — **vom Betreiber auf später gelegt (2026-09-03)**
- [ ] Agent je Host, Scheduler mit Platzierungsstrategie
- [ ] Geteilte Registry, geteilter Profil-Storage oder Host-Pinning
- [ ] Vorgewärmte Pools

---

## Querschnittsthemen (laufend)

- **Stückliste (SBOM) für veröffentlichte Images** ✅ (2026-09-01) — `make sbom` bzw.
  `scripts/sbom.sh` erzeugt je Image eine Stückliste in **SPDX und CycloneDX** (`syft` als
  Container, nichts zu installieren; der Docker-Socket geht nur lesend hinein). Gemessen:
  `ota/api:dev` 137 Pakete, `ota/agent:dev` 359. Die Dateien landen unter `sbom/` und gehören
  nicht ins Repository — sie gelten für genau den Stand, aus dem sie stammen. Gebraucht werden
  sie, sobald ein Image das Haus verlässt; für den Betrieb im eigenen Haus stellt sich die Frage
  nicht ([THIRD-PARTY-NOTICES.md](THIRD-PARTY-NOTICES.md))

- **Tests**: je Endpunkt ein Autorisierungstest; Integrationstest „Session starten → verbinden →
  stoppen" gegen echtes Docker; CI vor jedem Merge
- **Wiki**: `docs/wiki/` wird mit jedem Meilenstein fortgeschrieben und im Admin-Bereich ausgeliefert
- **ADRs** in [`docs/adr/`](docs/adr/README.md) — für Entscheidungen, die umstritten waren, teuer
  rückgängig zu machen sind und in einem Jahr die Frage „warum eigentlich?" auslösen
- **`plan.md` aktuell halten**: Weicht die Realität ab, gewinnt die Realität

---

## Nächster Schritt

**Zuerst: eine Weile benutzen.** Fast alles, was seit M11 dazukam, kam nicht aus dem Entwurf,
sondern daraus, dass jemand die Anlage benutzt hat — das Abmelden, die E-Mail-Pflicht, die
Nachführung nach Keycloak, das Aussehen der Anmeldemaske. Der nächste Fund kommt vermutlich genauso.

~~**Die Profilpfade**~~ ✅ **erledigt.** Sie heissen jetzt nach der unveränderlichen Kennung
(`users.id`), daneben liegt ein Verweis unter dem Anmeldenamen, damit im Dateisystem trotzdem
jemand etwas findet ([`auth-roadmap.md`](auth-roadmap.md) §4, Entscheidung 5). Ein Konto in
Keycloak umzubenennen ist damit gefahrlos; `scripts/migrate-profilpfade.sh` zieht Bestände nach.

Dann, in dieser Reihenfolge:

~~**Netzlaufwerke** (der Rest von M6)~~ — **gestrichen (2026-09-03)**, zusammen mit der
Guacamole-Engine und code-server. Kerberos bräuchte ein KDC und einen Dateiserver; ohne beides
liesse sich nichts davon ehrlich prüfen. **Die Passwort-Durchreichung bleibt draussen** (§17.9) —
das war nie eine Frage des Aufwands und bleibt auch nach dem Streichen die Antwort.

**Die Streaming-Maschine** ✅ **umgestellt.** `ota/base-desktop` überträgt einen H.264-Strom über
WebRTC statt rechteckiger Ausschnitte über RFB und ist die **Vorgabe**. Der Weg über KasmVNC bleibt
bestehen und ist für Images von Kasm weiterhin nötig; umschaltbar je Arbeitsplatz unter
**Streaming**. Ausführlich in [Kapitel 20](docs/wiki/20-selkies-versuch.md).

Was der Versuch schon beantwortet: **Es geht** — durch Traefik, mit OTAs Anmeldung davor, die
Auflösung folgt dem Browserfenster, und er läuft beim Nutzer. Fünf Fallen lagen auf dem Weg, alle
gemessen und behoben: Der Client baut zwei Adressen aus der Wurzel statt aus dem Pfad (derselbe
Fehler wie damals bei KasmVNC); `cvt` gibt es weder in Ubuntu 24.04 noch in Debian 13; coturn darf
als Nutzer 1000 nicht nach `/var/run` schreiben; **ein TURN-Server hinter einer Docker-Bridge kann
nicht vermitteln** (er meldet die Adresse des Hosts und verschickt mit der des Containers — er läuft
deshalb als Dienst im Stack); und **Chrome verschickt DTLS mit fest 1200 Byte je Paket**, was hinter
einem VPN mit MTU 1000 nie ankommt (`OTA_TURN_PROTOCOL=tcp` mit `OTA_TURN_ICE_POLICY=relay`).

Seither ist der Weg zweimal weitergegangen. `ota/base-desktop` ist der Nachfolger und die Vorgabe: **Debian 13,
XFCE, Selkies, ohne KasmVNC**, Konto `ota` unter `/home/ota`, GStreamer 1.26 aus der Distribution
statt aus dem Bündel. Und die Betriebsart **„Einzelne App"** überträgt jetzt wirklich nur die
Anwendung — nur ein Fenstermanager, formatfüllend, mit einem Startbefehl aus dem Bildbauer.

**Und seit 2026-09-03 ist der Weg vermessen** (`make messung`, Zahlen in `docs/messungen/`, Auswertung
in [Kapitel 20](docs/wiki/20-selkies-versuch.md#was-es-kostet--gemessen)). Das Ergebnis dreht die
Erwartung um: Unter Last kostet Selkies **nicht mehr** als KasmVNC (0,38 gegen 0,41 Kerne) — die
Sorge um x264 in Software war unbegründet. Der Unterschied liegt woanders, an zwei Stellen. Im
**Leerlauf** kostet Selkies 0,34 Kerne und KasmVNC nichts, denn H.264 kodiert seine 30 Bilder je
Sekunde auch für ein stehendes Bild; das ist die Zahl, an der die Kapazität hängt. **Die
naheliegende Stellschraube dagegen hilft nicht**: Mit `SELKIES_FRAMERATE=15` blieb die Grundlast
bei 0,35 Kernen, unter Last stieg sie sogar auf 0,60, und die Reaktionszeit verdoppelte sich —
die Grundlast liegt also nicht am Kodieren, sondern am Abgreifen des Bildschirms. Und bei der
**Bandbreite** liegt Faktor 56
dazwischen (0,45 gegen 25,4 Mbit/s) — im selben Netz belanglos, über ein VPN entscheidend. Die
Reaktionszeit von Glas zu Glas: 46 gegen 120 Millisekunden im Mittel.

Der Messstand war dabei der schwierigere Teil. Drei Fehler steckten im ersten Lauf, jeder für sich
genug, um die Zahlen wertlos zu machen: Die Last rannte ungebremst und trieb **beide** Container an
ihre Kerngrenze, sodass die Differenz — das eigentlich Gesuchte — null war. Die Bandbreitenzählung
sah nur `eth0`, während der Strom über die zweite Netzkarte lief (gemeldet: 0,00 Mbit/s). Und die
Grundlast wurde ohne Betrachter gemessen, wo Xvfb noch auf 3840×2160 steht — also auf achtfacher
Fläche. Alle drei stehen als Warnung im Skript.

Zwei Prüfwerkzeuge sind dabei entstanden, die dem Weg vorher fehlten: `scripts/pruef-turn.py`
schickt ein Paket durch den TURN und vergleicht Absender mit Relay-Adresse, und
`scripts/pruef-selkies.mjs` fährt einen Browser, der den Session-Container **nicht** direkt
erreichen kann, durch Anmeldung und Sitzung und liest aus, ob ein Bild ankommt.

Was er **nicht** beantwortet und was vor einer Entscheidung gemessen gehört: wie viel besser es
wirklich ist (Latenz und Bild nebeneinander), was es an CPU kostet (x264 in Software, ohne GPU
zahlt das jede Sitzung), und ob das Modell „ein Bildschirm je Sitzung" den Alltag trägt — den
Anwendungsumschalter je Display gibt es dort nicht. Offen ausserdem: das Image ist mit 1,78 GB
nicht kleiner geworden, und `OTA_TURN_ICE_POLICY=relay` schickt **jede** Sitzung über den
TURN-Server, auch die im selben Netz.

Die alte Notiz dazu, unverändert gültig als Begründung, warum es Selkies ist und nichts
Selbstgebautes:

**Die Streaming-Maschine** — die einzige Richtung, in der „etwas Eigenes" wirklich besser wäre.
Nicht ein selbstgebautes Protokoll (x11vnc ist einfädig und ungepflegt, TigerVNC ist der Stamm,
von dem KasmVNC abzweigt — wir würden gerade die Teile weglassen, die ihn ausmachen), sondern ein
**Wechsel des Verfahrens: WebRTC statt RFB**, mit GStreamer und H.264/VP8. Der Gewinn wäre echt:
deutlich niedrigere Latenz, brauchbares Video, GPU-Kodierung. Der Preis ebenso: UDP und ein
TURN-Weg durch Traefik, eine Audiokette — und vor allem sind Reconnect-Automat,
Leerlauf-Abschaltung und Zwischenablage in `SessionViewer.tsx` gegen die postMessage-Schnittstelle
des KasmVNC-Clients geschrieben. Deshalb ein eigener Meilenstein mit eigener Abnahme und nicht
nebenbei: ein zweites Testimage `ota/base-webrtc:test` neben dem heutigen, dann wird **gemessen**
statt geglaubt.

Aus `plan.md` §17 bleibt **Hardware** (§17.1). **Domain und Zertifikat** (§17.2) haben sich in der
Praxis entschieden: Die Anlage läuft hinter einem Reverse Proxy mit einem Zertifikat der
Firmen-CA, und OTAs eigene CA bleibt für den direkten Weg und für angebundene Anwendungen
(`/ca.crt`). Beide Wege funktionieren nebeneinander und sind geprüft.

**Nicht als Nächstes**: M10. Er ist sauber beschrieben und wartet auf eine zweite Maschine. M9 ist
zu; was dort noch offen stand — die Guacamole-Engine und code-server — ist am 2026-09-03
gestrichen. Nichts davon fehlt heute jemandem.
