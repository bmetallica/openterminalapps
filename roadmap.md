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
| **M6** | Identität & Netzlaufwerke | AD/LDAP, Kerberos, Shares im Arbeitsplatz | 2–3 Wochen |
| **M7** | Migration & Härtung | Profil umgezogen ✅, Härtung, Monitoring | 1–2 Wochen |
| **M8** | Kasm-Kompatibilität | Einzelimages und ganze Registries einbinden | 1–2 Wochen |
| **M9** | Optionale Erweiterungen | OIDC, Guacamole, WebAuthn, code-server | 2–3 Wochen |
| **M10** | Skalierung | Mehrere Hosts, Pools | offen |

Bis zum produktiven Einsatz (M5–M7): **realistisch 4–6 Wochen** in Teilzeit.

**Stand 2026-08-27**: M0 bis M4 laufen, dazu die Build-Pipeline aus M5 und die
Sicherung aus M7. Ein Nutzer meldet sich an, startet seinen
Arbeitsplatz und öffnet darin VS Code, ein Terminal und den Dateimanager — jedes
formatfüllend auf eigenem Display, alle im selben Container mit gemeinsamem
`/home`. Geprüft durch 20 Autorisierungs- und 33 Oberflächentests
(`make test`).

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
- [ ] Erste **Alembic-Migration** erzeugen. Postgres läuft; das Schema entsteht
      derzeit über `create_all`, Schemaänderungen laufen von Hand
- [ ] ADR-Format und ADR-001 dokumentieren

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
- [ ] **Offen**: die restliche Abnahmematrix (`plan.md` §10.5, Fälle 3, 5, 6, 7, 9, 10, 11, 12)
      in Chrome **und** Firefox von Hand durchgehen
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
- [ ] **TOTP-Einrichtung im UI** samt Recovery-Codes. Die *Prüfung* beim Login
      steht bereits — es fehlt der Weg, einen zweiten Faktor zu hinterlegen
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
- [ ] Eigene Einstellungen: Passwort, 2FA, Sprache, Auflösung
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
- [ ] Klassischer XFCE-Desktop zusätzlich als Ansicht auf `:0`
- [x] App-Umschalter im Viewer; laufende und nicht gestartete Apps unterscheidbar

**Zwischenablage** — der kritische Teil dieses Meilensteins
- [x] **Brücke zwischen den Displays** (`plan.md` §10.4): spiegelt CLIPBOARD über alle offenen
      Displays, Schleifenschutz über Prüfsumme, folgt den Rechten des Templates, startet
      automatisch beim ersten App-Start. Geprüft durch `scripts/test-clipboard-bridge.sh`
- [ ] **Offen**: Abfrage im halben Sekundentakt statt XFIXES-Ereignissen. Das Basisimage bringt
      weder `clipnotify` noch python-xlib mit; mit eigenem Basisimage (M5) wird die Schleife
      ereignisgesteuert
- [ ] `xsel`, `xdotool`, `autocutsel` ins eigene Basisimage — im Kasm-Image fehlen sie
- [x] Abnahmefall 8: Kopieren zwischen zwei Apps im Container, beide Richtungen

**Ressourcen**
- [x] Grenzen gelten für den Container als Ganzes (`plan.md` §9.3); Spitzenlast-Dimensionierung
- [ ] `oom_score_adj` so setzen, dass nicht der ganze Arbeitsplatz an einer App stirbt

**Arbeitsgefühl** — nachgezogen am 2026-08-27 nach dem ersten echten Benutzen
- [x] **Der Stream wächst mit dem Fenster.** Der KasmVNC-Client schaltet `resize` im iframe auf
      `off`; der ferne Bildschirm blieb dann auf Startgrösse und sass mit schwarzem Rand mitten im
      Fenster. Die Stream-Adresse trägt jetzt `resize=remote` (`STREAM_ARGS` in
      `api/ota/routers/sessions.py`) — gemessen: Fenster 1600×1000 → Display 1600×1000
- [x] **Jede Anwendung in einem eigenen Tab.** Eigene Adressen `/view/s/<id>[/<display>]`;
      das Dashboard bleibt im ersten Tab stehen
- [x] **Verknüpfung auf dem Desktop** (PWA): Manifest je Vorlage und App aus der API
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
- [ ] Live-Log per SSE in der Oberfläche (derzeit über Abfrage)
- [ ] App-Katalog um **Skeleton-Teilbaum und Auflösung je App** ergänzen.
      Startbefehl, Icon, Sperrgrund und festes Display stehen bereits
- [x] Extensions beim **Build** installieren, nicht beim Start
- [ ] Sichtbarkeit je App und Gruppe (`group_template_apps`)
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
- [ ] Skeleton-Profile: Kopie beim ersten Start, Datei-Browser, „Enforce"-Pfade
- [ ] **„Session einfrieren"**: `docker commit`, Home-Diff, Secret-Filter (`.ssh/id_*`, `.gnupg`,
      `*token*`, `*.pem`, `.aws`, `.docker/config.json`, `krb5cc_*`, `.smbcredentials`, `keytab`)
- [ ] **Eigenes Basisimage** `ota/base-xfce` (Ubuntu + XFCE + KasmVNC aus offiziellem Release)
- [ ] UI benennt, dass Extensions nicht zwischen VS Code, VSCodium und Cursor wandern

**Vorher zu klären**
- [x] ~~Cursor-Lizenz klären~~ — Cursor bleibt draussen (`plan.md` §17.10)
- [ ] Sicherstellen, dass VSCodium **nicht** auf den MS-Marketplace zeigt

---

## M6 — Identität & Netzlaufwerke · 2–3 Wochen

Erst mit dem Arbeitsplatz sinnvoll (`plan.md` §9.4).

- [ ] **LDAP/AD**: `ldap3` mit LDAPS/StartTLS, Login-Attribut wählbar, Gruppen-Mapping,
      JIT-Anlage, nächtlicher Sync, **Test-Button mit Vorschau der gemappten Gruppen**
- [ ] `identity_configs` mit den vier Modi; Standard ist `none`
- [ ] **Weg 2 (Kerberos-Ticket-Injektion)** als Standard, Mount per `sec=krb5`
- [ ] Ticket-Erneuerung im Container per `k5start`
- [ ] UID/GID aus dem Verzeichnis (`uidNumber`/`gidNumber`) beim Start setzen
- [ ] Weg 3 (Nutzer verbindet selbst) immer verfügbar
- [ ] Weg 4 (Passwort-Durchreichung) **standardmässig aus**, mit Warntext im Admin-UI
- [ ] Zugangsdaten nur über `tmpfs` mit `0600` — **nie** als Umgebungsvariable, nie ins Profil,
      nie ins Image
- [ ] Weg 1 (S4U2Proxy) evaluieren, falls die AD-Konfiguration es hergibt

---

## M7 — Migration & Härtung · 1–2 Wochen

- [x] Nutzer `bmetallica` in `admins` + `users` (über `make admin`)
- [x] `scripts/migrate-kasm-profile.sh` — idempotent, mit Probelauf und Abnahmemodus
- [x] Profil in einen **Arbeitsplatz** überführt (805 MB Rohdaten → 63 MB)
- [x] Abnahme bestanden: Einstellungen, Extensions, SSH- und GPG-Schlüssel, XFCE-Layout
- [ ] Container-Härtung: `no-new-privileges`, Capabilities gedroppt, seccomp, `pids_limit`, `shm_size`
- [ ] Netzsegmentierung final; `ota_sessions` ohne Zugriff auf `ota-db`
- [ ] Security-Review der Auth- und Autorisierungspfade
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
- [ ] Monitoring: `/healthz`, Prometheus-Metriken
- [ ] Storage-Quotas, Kapazitäts-Preflight statt OOM-Kill
- [x] ~~HSTS~~ — entfällt, solange es bei der lokalen CA bleibt (`plan.md` §17.2)
- [x] ~~Umzug auf 443~~ — entfällt. OTA bleibt auf 8443, der Port ist frei
      einstellbar, und Kasm läuft dauerhaft daneben weiter (`plan.md` §17.13)
- [x] ~~Rollback-Plan~~ — entfällt, weil Kasm gar nicht erst abgeschaltet wird

---

## M8 — Kasm-Kompatibilität · 1–2 Wochen

Das Feature aus `plan.md` §1.2 und §9.8. Schema und Adressen sind verifiziert.

- [ ] `registries` und `registry_entries` nach `plan.md` §9.7
- [ ] Katalog von `{url}/{schema}/list.json` laden, cachen, per `modified` aktualisieren
- [ ] Durchsuchbarer Katalog im Admin-UI mit Kategorien und Icons
- [ ] Import erzeugt ein Template mit `mode: single_app`
- [ ] **Architektur des Hosts prüfen** — nur passende Einträge anbieten
- [ ] **`uncompressed_size_mb` anzeigen und warnen**, bevor gezogen wird
- [ ] Hinweis im Import-Dialog: Registries sind eine Vertrauensentscheidung; Lizenz des Images
      gilt unverändert (`plan.md` §3)
- [ ] Vorkonfiguriert, aber abschaltbar: Kasm Technologies (86), Kasm AI (11), LinuxServer.io (2)
- [x] ~~Signaturprüfung~~ — entschieden: keine, Registries sind eine Vertrauensentscheidung

---

## M9 — Optionale Erweiterungen · 2–3 Wochen

- [ ] **OIDC** mit PKCE, Claim→Gruppen-Mapping
- [ ] **WebAuthn/Passkeys**
- [ ] **Guacamole-Engine** für RDP/VNC-Ziele — löst `HauptPC` und `VNC-HauptPC` ab
- [ ] **code-server** als leichte Engine für reine Editor-Sessions (Extensions dann über Open VSX)
- [ ] Gemeinsame Gruppenlaufwerke
- [ ] Branding, helles Theme, GPU-Durchreichung

---

## M10 — Skalierung · offen

Erst mit Hardware für die Zielgröße (`plan.md` §17.1).

- [ ] Mehrere Hosts; `sessions.host_id` ist vorgesehen
- [ ] Agent je Host, Scheduler mit Platzierungsstrategie
- [ ] Geteilte Registry, geteilter Profil-Storage oder Host-Pinning
- [ ] Vorgewärmte Pools

---

## Querschnittsthemen (laufend)

- **Tests**: je Endpunkt ein Autorisierungstest; Integrationstest „Session starten → verbinden →
  stoppen" gegen echtes Docker; CI vor jedem Merge
- **Wiki**: `docs/wiki/` wird mit jedem Meilenstein fortgeschrieben und im Admin-Bereich ausgeliefert
- **ADRs** in `docs/adr/`
- **`plan.md` aktuell halten**: Weicht die Realität ab, gewinnt die Realität

---

## Nächster Schritt

M1. Offen bleiben aus `plan.md` §17 vor allem **Hardware** (§17.1) und **Domain/Zertifikat** (§17.2) —
Letzteres bestimmt, ob die lokale CA eine Zwischenlösung bleibt oder dauerhaft trägt.
