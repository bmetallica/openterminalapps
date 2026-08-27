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
- [ ] **Offen**: Abnahmematrix (`plan.md` §10.5) in Chrome **und** Firefox von Hand durchgehen.
      Automatisiert nicht prüfbar — Headless-Chromium verweigert `navigator.clipboard`
      grundsätzlich. Der Test prüft alle Voraussetzungen, den vollständigen Weg muss ein
      Mensch einmal gehen
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

**Erreicht**: Ein Nutzer öffnet seinen Arbeitsplatz und startet darin VS Code, ein Terminal und
den Dateimanager — jedes formatfüllend auf einem eigenen Display, alle im selben Container mit
gemeinsamem `/home`. Displays entstehen erst beim Klick und werden beim Schliessen abgebaut.

Die **Zwischenablage-Brücke** steht ebenfalls: Kopieren in einer App, Einfügen in der anderen
funktioniert in beide Richtungen, mit Umlauten und mehrzeiligem Code. Sie startet automatisch beim
ersten App-Start und folgt den Rechten des Workspace.

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
- [ ] Live-Log per SSE in der Oberfläche (derzeit über Abfrage)
- [ ] App-Katalog um **Skeleton-Teilbaum und Auflösung je App** ergänzen.
      Startbefehl, Icon, Sperrgrund und festes Display stehen bereits
- [x] Extensions beim **Build** installieren, nicht beim Start
- [ ] Sichtbarkeit je App und Gruppe (`group_template_apps`)
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
