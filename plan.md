# OpenTerminalApps (OTA) — Architektur- und Umsetzungsplan

> Selbstgehostete, containerbasierte Workspace-Plattform als Ersatz für Kasm Workspaces.
> Fokus: VS Code (Desktop-Variante im Browser), Golden Images, eigene Nutzerverwaltung,
> AD/LDAP nur optional, dunkles modernes UI, striktes Admin/User-Rechtekonzept.

Stand: 2026-08-26 · Host: `RAG` (192.168.66.224) · Projektverzeichnis: `/opt/openterminalapps`

---

## 1. Ziel und Abgrenzung

### 1.1 Der Kern: ein persönlicher Linux-Arbeitsplatz im Browser

OTA gibt jedem Nutzer **einen eigenen, dauerhaften Linux-Arbeitsplatz**, den er im Browser bedient.
Darin sind seine Werkzeuge installiert — VS Code, JetBrains, VSCodium, opencode, ein Terminal —, und
jedes davon lässt sich einzeln formatfüllend in den Browser holen. Alle teilen sich **ein Zuhause**:
dieselben Projektverzeichnisse, denselben SSH-Schlüssel, dieselbe Git-Konfiguration, dieselbe
Zwischenablage.

Das ist der Unterschied, auf den es ankommt. Andere Plattformen geben dir *pro Anwendung* einen
Container: VS Code hier, IntelliJ dort, und derselbe Repository-Klon liegt dreimal herum, mit drei
Schlüsselbunden und drei Konfigurationen. OTA dreht das um — **eine Maschine pro Mensch, viele
Werkzeuge darin.**

Daraus folgt der Rest fast von selbst:
- **Vorkonfiguration ist zentral.** Admins bauen den Arbeitsplatz als Golden Image: gesetzte
  Extensions, fertige Einstellungen, Firmen-Zertifikate, Proxy-Konfiguration. Ausgerollt in Versionen,
  mit Rollback.
- **Identität wird sinnvoll.** Ein Nutzer, ein Container, eine Identität — erst damit lohnt es sich,
  AD-Anmeldedaten hineinzureichen und Netzlaufwerke zu mounten (§9.4).
- **Ressourcen sind pro Mensch begrenzbar**, nicht pro Werkzeug: Nutzer A bekommt 4 Kerne, Nutzer B
  einen (§5).

### 1.2 Als Feature: vorhandene Kasm-Images und -Registries einbinden

Neben dem Arbeitsplatz kann OTA **einzelne Anwendungen als eigenen Wegwerf-Container** starten —
das Modell, das Kasm Workspaces verwendet. Das ist bewusst **ein Feature, kein zweites Fundament**:

- Es öffnet ein riesiges vorhandenes Ökosystem. Allein die offizielle Kasm-Registry führt
  **86 fertige Workspaces**, dazu kommen die AI-Registry und LinuxServer.io (§9.8).
- Es passt für Anwendungen, die man selten und isoliert braucht — GIMP, LibreOffice, ein
  Wegwerf-Browser, ein OSINT-Werkzeug — und die im persönlichen Arbeitsplatz nur Platz kosten würden.
- Es sichert den Umstieg ab: Was heute in Kasm läuft, läuft am ersten Tag auch in OTA.

**OTA ist damit kein Kasm-Klon.** Kasm ist ein Katalog isolierter Anwendungen. OTA ist ein
Arbeitsplatz, der einen solchen Katalog *mitbenutzen kann*.

### 1.3 Weiterhin gültig
- **Eigene Nutzerverwaltung** als Kern (lokale Users, Gruppen, Rollen, 2FA). LDAP/AD und OIDC sind
  *optionale, zuschaltbare* Provider — kein Keycloak-Zwang.
- **Rollentrennung**: Nur die Gruppe `admins` sieht Konfiguration, Images, Zuweisungen und fremde
  Sessions. Normale Nutzer sehen ihren Arbeitsplatz und ihre Apps, sonst nichts.
- **Keine künstlichen Session-Limits**, keine Lizenzserver, keine Concurrent-User-Zählung.
- **Zwischenablage in beide Richtungen** als nicht verhandelbare Grundfunktion (§10).

### 1.4 Was OTA (vorerst) nicht ist
- Kein Kubernetes-Zwang — Docker und Compose auf einem oder wenigen Debian-Hosts.
- Kein Multi-Tenant-SaaS mit Abrechnung.
- Kein eigener VNC-Stack — bewährte Engines werden orchestriert, nicht neu gebaut.
- Keine Cloud-Autoscaling-Provider in v1.

### 1.5 Dimensionierung
Zielgröße ~20 Entwickler. **Realität auf diesem Host**: 4 vCPU / 15 GB RAM / 60 GB frei. Ein
Arbeitsplatz ist mit 4 Kernen / 6 GB veranschlagt. Für 20 parallele Arbeitsplätze braucht es
**mindestens 64 GB RAM, 16+ Kerne und 1 TB SSD**. Dieser Host trägt Entwicklung und einen Piloten mit
zwei bis drei Arbeitsplätzen, nicht die Zielgröße. → §17.1

## 2. Ist-Analyse dieses Hosts (verifiziert)

Alle Angaben wurden auf dem Host geprüft, nicht angenommen.

### 2.1 Plattform
| Sache | Wert |
|---|---|
| OS | Debian GNU/Linux 13 (trixie) |
| Docker | 29.7.0, Compose v5.3.1 |
| CPU / RAM / Swap | 4 Cores / 15 GB / 10 GB |
| Disk `/` | 186 GB, 117 GB belegt, **60 GB frei** |
| Hostname / IP | `RAG` / 192.168.66.224 |
| Tooling | git 2.47.3, Node 20.19.2, Python 3.13.5 |

### 2.2 Laufendes Kasm (1.19.0)
Container: `kasm_proxy` (**belegt 0.0.0.0:443**), `kasm_api`, `kasm_manager`, `kasm_agent`, `kasm_db` (Postgres), `kasm_guac`, `kasm_rdp_gateway` (**3389**), `kasm_rdp_https_gateway`.
Installation unter `/opt/kasm/current -> /opt/kasm/1.19.0`, Alt-Version `1.18.1` liegt daneben.
Zertifikat: self-signed, `CN=RAG`, gültig bis 2031.

**Bereits belegte Ports auf dem Host** (Auswahl): 22, 443, 2222, 3000, 3001, 3389, 5440, 6080, 6661, 6662, 7634, 7878, 7999, 8000, 8080, 8088, 8090, 8091, 8096, 8420.
→ OTA nimmt im Parallelbetrieb **8443/tcp** (HTTPS) und übernimmt 443 erst bei der Abschaltung von Kasm.

### 2.3 Der VS-Code-Workspace (das zu erhaltende Kernstück)
Image `kasmweb/vs-code:1.18.0-rolling-weekly` (6,21 GB):
- Basis: Ubuntu + **XFCE4-Desktop**, gestartet via `/dockerstartup/vnc_startup.sh` → `kasm_startup.sh` → `custom_startup.sh`
- `custom_startup.sh` startet `code --no-sandbox` und maximiert das Fenster (`MAXIMIZE_NAME="Visual Studio Code"`)
- **Remoting-Engine: KasmVNC 1.4.1** — liefert selbst einen HTTPS-Webclient auf **Port 6901** (zusätzlich 5901 VNC, 4901 Audio)
- Läuft als `User 1000`, `HOME=/home/kasm-user`, `DISPLAY=:1`
- Wichtige ENV-Schalter: `VNC_PW`, `VNC_RESOLUTION`, `MAX_FRAME_RATE`, `VNCOPTIONS`, `START_XFCE4`, `START_PULSEAUDIO`, `APP_ARGS`
- Installiertes VS Code: **`code` 1.134.0 — der offizielle Microsoft-Build**, also die Desktop-Version inkl. Zugriff auf den echten VS-Code-Marketplace

Kasm-DB-Konfiguration dieses Images:
```
friendly_name           = "Visual Studio Code"
cores                   = 2
memory_bytes            = 2902458368  (~2,7 GB)
persistent_profile_path = /srv/kasm_profiles/{username}
categories              = ["Development"]
```

### 2.4 Nutzer und Daten von `bmetallica`
- Kasm-User `bmetallica` (`f7e0f6f9-…`, realm `local`, aktiv), Mitglied in **`All Users` UND `Administrators`**
- Profil auf dem Host: **`/srv/kasm_profiles/bmetallica`, 805 MB**, Owner `bmetallica:bmetallica`
- Inhalt u. a.:
  - `.config/Code/` (VS-Code-User-Data, 726 MB inkl. Chrome-Profil in `.config/google-chrome`)
  - `.config/Code/User/settings.json` — enthält reale Einstellungen: `twinny.*` (Ollama auf `http://192.168.66.225`), `continue.*`, `myfeed.gatewayUrl`, `claudeCode.preferredLocation`
  - `.vscode/extensions/` (Remote-SSH-Extensions), `.vscode-shared/`
  - `.continue/` (3,7 MB), `.copilot/`, `.dotnet/`
  - `.ssh/`, `.gnupg/`, `.pki/` — **Schlüsselmaterial, migrationskritisch**
  - XFCE-Desktop-Einstellungen (`.config/xfce4`), Thunar, GTK-Theme
  - Ballast: `core.1087` (20 MB Coredump), `.cache/` (52 MB) — beim Umzug ausschließen
- Weitere Images in Kasm: Obsidian, Thunderbird, GIMP, Inkscape, LibreOffice, IntelliJ IDEA (`linuxserver/intellij-idea`), zwei VNC-Direktverbindungen (`HauptPC`, `VNC-HauptPC`), Easy Diffusion (deaktiviert)
- Relevante Gruppen-Settings, die OTA nachbilden muss: `allow_persistent_profile`, `allow_kasm_clipboard_up/down/seamless`, `allow_kasm_uploads/downloads`, `allow_kasm_audio`, `allow_kasm_microphone`, `max_kasms_per_user=5`, `keepalive_expiration=3600`, `keepalive_expiration_action=delete`, `idle_disconnect`, `allow_totp_2fa`, `allow_webauthn_2fa`

---

## 3. Rechtliche Bewertung

**Status: am Originaltext verifiziert** (2026-08-26). Die Lizenztexte wurden aus dem Image bzw. aus den
Upstream-Repositories gelesen, nicht aus dem Gedächtnis zitiert. Keine Rechtsberatung — aber belegt.

### 3.0 Kurzantwort: Ja, der Unternehmenseinsatz ist zulässig
Für **unternehmensinterne Nutzung durch eigene Mitarbeiter** ist der geplante Stack lizenzrechtlich in Ordnung.
Alle drei kritischen Komponenten erlauben das ausdrücklich. Die Grenze verläuft nicht bei der Anzahl der Nutzer,
sondern bei der **Weitergabe nach außen**: Sobald die Plattform Dritten (Kunden, anderen Firmen) als Dienst
angeboten würde, kippt die Bewertung bei VS Code. Details unten.

### 3.1 Microsoft VS Code — internes Deployment ist ausdrücklich erlaubt
Die EULA liegt im Image unter `/usr/share/code/resources/app/LICENSE.rtf`. Wörtlich, §1a:

> **"INSTALLATION AND USE RIGHTS. a. General.** You may use any number of copies of the software to develop and
> test your applications, **including deployment within your internal corporate network**."

Das ist genau der Anwendungsfall — beliebig viele Kopien, ausdrücklich im internen Firmennetz, ohne Nutzerlimit
und ohne Lizenzgebühr. Keine 20-User-Grenze, keine Named-User-Lizenzen.

Die Verbote stehen in §5 (Scope of License):

> "You may not ... share, publish, rent or lease the software, or **provide the software as a stand-alone
> offering for others to use**."

Praktische Konsequenzen:

| Vorhaben | Zulässig? |
|---|---|
| VS-Code-Container für eigene Mitarbeiter im Firmennetz betreiben | **Ja**, §1a explizit |
| Eigenes Golden Image mit VS Code bauen, in **private/interne** Registry pushen | **Ja** — internes Deployment |
| Beliebig viele Nutzer, beliebig viele parallele Sessions | **Ja** — kein Limit in der EULA |
| Image in eine **öffentliche** Registry (Docker Hub) pushen | **Nein** — „share, publish" |
| OTA als Produkt/Hosting **an Kunden** verkaufen, inkl. MS-VS-Code | **Nein** — „stand-alone offering for others" |
| Marketplace-Extensions nutzen | **Ja**, §1d — aber nur aus dem MS-gebrandeten Build |

Zwei Nebenpunkte, die im Golden Image gesetzt werden sollten:
- **§1d Extensions**: Der Marketplace unterliegt zusätzlich `https://aka.ms/VSMarketplace-ToU`. Diese ToU erlauben
  den Zugriff nur aus MS-gebrandeten VS-Code-Produkten. Du nutzt genau so einen Build → zulässig. `code-server`
  und `openvscode-server` dürften ihn **nicht** nutzen und müssten auf Open VSX ausweichen. **Das ist der Grund,
  warum die Desktop-Variante hier nicht nur funktional, sondern auch rechtlich der bessere Weg ist.**
- **§2 Data**: VS Code sendet Telemetrie an Microsoft. Bei betrieblicher Nutzung ist das ein DSGVO-Thema.
  Empfehlung: im Golden-Skeleton `"telemetry.telemetryLevel": "off"` vorbelegen (siehe §8.1).

### 3.2 Kasm Workspace-Images — MIT, verifiziert
`kasmtech/workspaces-images`, Datei `LICENSE.md`, vorhanden auch im Branch `release/1.18.0` (der Branch deines
Images): **wörtlicher MIT-Lizenztext**, Copyright 2022 Kasm Technologies Inc. Nutzen, Ändern, Weitergeben,
sogar Verkaufen ist erlaubt, solange der Copyright-Vermerk erhalten bleibt.

Damit ist die Vorab-Aussage „Apache 2.0" zwar falsch, aber im Ergebnis sogar **günstiger** als angenommen —
MIT ist die permissivere Lizenz.

Wichtige Einschränkung, die im Disclaimer der Datei selbst steht:

> "This license applies **only to the source code that is directly maintained in this git repository**, it does
> not extend to dependencies from outside of this repository, **to include other projects owned and/or
> maintained by Kasm Technologies**."

Das heißt: MIT gilt für die **Dockerfiles und Build-Skripte**, nicht für den Inhalt der fertigen Images. Jedes
enthaltene Paket behält seine eigene Lizenz (VS Code → MS-EULA, XFCE → GPL/LGPL, Chrome → Google-ToS …).
Und KasmVNC ist als „anderes Kasm-Projekt" ausdrücklich **ausgenommen** → siehe §3.3.

### 3.3 KasmVNC — GPL-2.0, Eigenbetrieb uneingeschränkt frei
Zweifach verifiziert: das installierte Paket `kasmvncserver 1.4.1` weist in seiner Debian-Copyright-Datei
**GPL-2+** aus, und das Upstream-Repo `kasmtech/KasmVNC` ist laut GitHub-Lizenzerkennung und `LICENSE.TXT`
**GPL-2.0**.

Was das für dich bedeutet:
- **Betrieb im Unternehmen: uneingeschränkt frei.** Die GPL kennt keine Nutzerlimits und keine Gebühren.
- **Copyleft-Pflichten entstehen nur bei Weitergabe** („conveying") der Software. Deine Mitarbeiter über den
  Browser auf eine intern betriebene Instanz zugreifen zu lassen, ist **keine Weitergabe**. GPLv2 hat auch keine
  Netzwerk-Klausel — das wäre die AGPL, und die ist hier nicht im Spiel.
- **OTA selbst muss nicht GPL werden.** Dein Dashboard spricht ausschließlich über HTTPS/WebSocket mit KasmVNC,
  linkt keinen GPL-Code und bettet keinen ein. Das ist Aggregation, kein abgeleitetes Werk.
- Nur wenn du **KasmVNC patchst und das Ergebnis weitergibst**, musst du den geänderten Quellcode unter GPL-2+
  bereitstellen. Vermeide Patches, dann entsteht die Pflicht gar nicht erst.

### 3.3b Was du hinter dir lässt: der Kasm-Server ist proprietär
Zur Einordnung, warum dieses Projekt überhaupt Sinn ergibt: `/opt/kasm/current/LICENSE.txt` ist ein
**„KASM WORKSPACES END USER LICENSE AGREEMENT"** — ein kommerzieller EULA mit Order-/Lizenzgebühren-Logik,
kein Open-Source-Lizenztext. Genau **dieser** Teil wird durch OTA ersetzt. Die Images und KasmVNC, die du
weiterverwendest, sind die freien Bestandteile (MIT bzw. GPL-2.0) und von diesem EULA nicht betroffen.

### 3.3c Marken
„Kasm" und „Kasm Workspaces" sind geschützte Kennzeichen. Die MIT-Lizenz erteilt **keine** Markenrechte.
OTA darf sie nicht im Produktnamen, Logo, UI oder in Domains führen und nicht suggerieren, ein offizielles
Kasm-Produkt zu sein. Ein sachlicher Hinweis („nutzt Container-Images des Kasm-Workspaces-Projekts, MIT")
ist zulässig und wegen der MIT-Namensnennungspflicht sogar geboten: **Der MIT-Copyright-Vermerk muss in
abgeleiteten Dockerfiles erhalten bleiben.**

### 3.4 Weitere Komponenten
| Komponente | Lizenz | Bewertung |
|---|---|---|
| Docker Engine | Apache-2.0 | frei |
| Traefik | MIT | frei |
| PostgreSQL | PostgreSQL License | frei |
| Apache Guacamole | Apache-2.0 | frei (nur falls RDP/SSH-Gateway gebraucht wird) |
| Keycloak | Apache-2.0 | frei — in OTA **optional**, nicht Kern |
| XFCE | GPL/LGPL | Eigenbetrieb frei |
| IntelliJ IDEA **Community**, PyCharm CE | Apache-2.0 | kommerziell kostenfrei nutzbar |
| JetBrains **Ultimate** | proprietär | **Named-User-Lizenz pro Entwickler nötig**; Aktivierung durch den Nutzer im Container, OTA speichert keine Lizenzschlüssel |
| `linuxserver/intellij-idea` | Image GPL-3.0, Inhalt JetBrains-EULA | Lizenzpflicht bleibt beim Nutzer |
| Google Chrome (im VS-Code-Image enthalten) | proprietär, Google-ToS | interner Betrieb frei; bei Zweifeln Chromium (BSD) nutzen |
| XFCE, Thunar, GTK | GPL/LGPL | Eigenbetrieb frei |

**Regel für jedes neue Golden Image**: Vor der Aufnahme einer Anwendung deren Lizenz prüfen und in
`docs/licenses.md` dokumentieren. Faustregel — Distributionspakete aus Debian/Ubuntu-Repos sind unkritisch,
Vendor-Binaries (Chrome, JetBrains Ultimate, Docker Desktop, MS-Produkte) brauchen einen Einzelblick.

### 3.5 Datenschutz (DSGVO), falls Mitarbeiter die Plattform nutzen
- Session-Recording und Keystroke-Logging: in v1 **bewusst nicht implementiert**. Falls später gewünscht → Betriebsrat/Mitbestimmung und Zweckbindung vorher klären.
- Audit-Log erfasst Admin-Aktionen und Session-Start/-Stop, keine Inhalte. Retention konfigurierbar (Default 90 Tage).
- Nutzerprofile enthalten personenbezogene Daten (SSH-Keys, Browser-Historie) → Löschkonzept beim Offboarding (Roadmap M6).

---

## 4. Architektur

### 4.1 Überblick

```
                     Browser (HTTPS, Port 8443 → später 443)
                                    │
                         ┌──────────▼───────────┐
                         │  Traefik (Ingress)   │  TLS-Terminierung, HTTP/2, WSS
                         │  - Router /          │──► ota-web    (React SPA, statisch)
                         │  - Router /api       │──► ota-api    (FastAPI)
                         │  - Router /s/{sid}   │──► Session-Container:6901
                         │    + forwardAuth     │      (dynamisch via Docker-Labels)
                         └──────────┬───────────┘
                                    │ forwardAuth: "Darf dieser Cookie diese Session sehen?"
                         ┌──────────▼───────────┐
                         │      ota-api         │  FastAPI + SQLAlchemy
                         │  Auth · RBAC · CRUD  │
                         │  Session-Orchestr.   │
                         │  Audit · Metrics     │
                         └───┬──────────────┬───┘
                             │              │
                  ┌──────────▼───┐   ┌──────▼────────────┐
                  │  ota-db      │   │  ota-agent        │  einziger Container mit
                  │  PostgreSQL  │   │  Docker-Steuerung │  Zugriff auf docker.sock
                  └──────────────┘   └──────┬────────────┘
                                            │
                  ┌─────────────────────────▼──────────────────────────┐
                  │  Session-Container (pro Nutzer, isoliert)          │
                  │  kasmweb/vs-code | ota/vscode-golden:v3 | …        │
                  │  KasmVNC:6901 · XFCE · VS Code                     │
                  │  /home/kasm-user ◄── /srv/ota/profiles/{user}/…    │
                  └────────────────────────────────────────────────────┘

                  ota-worker: Idle-Reaper · Image-Builds · GC · Backups
```

### 4.2 Komponenten

| Dienst | Technologie | Aufgabe |
|---|---|---|
| `ota-web` | React 18 + TypeScript + Vite + Tailwind, ausgeliefert als statische Dateien | Dashboard, Admin-UI, Session-Viewer |
| `ota-api` | Python 3.12 + FastAPI + SQLAlchemy 2 + Alembic + Pydantic v2 | REST-API, Auth, RBAC, Geschäftslogik |
| `ota-agent` | Python + `docker` SDK, gRPC/REST intern | **Einziger** Dienst mit `docker.sock`; startet/stoppt Container, baut Images, setzt Traefik-Labels |
| `ota-worker` | Celery *oder* APScheduler im API-Prozess | Idle-Timeout, Session-GC, Image-Builds, Profil-Backups |
| `ota-db` | PostgreSQL 16 | Persistenz |
| `traefik` | Traefik v3 | TLS, Routing, `forwardAuth`, dynamische Session-Routen über Docker-Provider |
| *(optional)* `ota-guac` | guacd | Nur falls RDP/SSH-Targets gebraucht werden (`HauptPC`-Verbindungen aus Kasm) |

**Begründung der Stack-Wahl**
- *Python/FastAPI statt Node*: Das Docker-SDK für Python ist ausgereifter als dockerode, async/await passt zu WebSocket-Handling, und Alembic gibt saubere Migrationen. Python 3.13 ist bereits auf dem Host.
- *Traefik statt eigenem WS-Proxy*: KasmVNC spricht HTTPS+WSS auf 6901. Einen eigenen Proxy dafür zu schreiben ist die häufigste Fehlerquelle (Backpressure, Binary-Frames, Reconnect). Traefik löst das mit `serversTransport.insecureSkipVerify` und Docker-Labels — und `forwardAuth` gibt uns trotzdem die volle Autorisierungskontrolle vor jedem Frame-Handshake.
- *`ota-agent` als einziger Socket-Besitzer*: Der Docker-Socket ist Root-Äquivalent. Die API (die Nutzereingaben verarbeitet) bekommt ihn nicht.

### 4.3 Zugriffsweg einer Session (Detail)

1. Nutzer klickt „VS Code starten" → `POST /api/sessions {template_id}`
2. API prüft: Ist Template dem Nutzer über eine Gruppe zugewiesen? Session-Limit erreicht? Ressourcen frei?
3. API erzeugt `session_id` (UUID), ein **einmaliges VNC-Passwort** und einen Session-Token
4. API → Agent: Container starten mit
   - Image, `cpus`, `mem_limit`, `shm_size=1g`
   - `VNC_PW=<random>`, `VNC_RESOLUTION`, App-spezifische ENV
   - Mount: `/srv/ota/profiles/{user}/{profile_scope}` → `/home/kasm-user`
   - Netzwerk `ota_sessions` (internes Bridge-Netz, kein Zugriff auf `ota-db`)
   - Labels:
     ```
     traefik.enable=true
     traefik.http.routers.s-<sid>.rule=PathPrefix(`/s/<sid>`)
     traefik.http.routers.s-<sid>.middlewares=ota-auth@file,s-<sid>-strip,s-<sid>-basic
     traefik.http.services.s-<sid>.loadbalancer.server.port=6901
     traefik.http.services.s-<sid>.loadbalancer.server.scheme=https
     traefik.http.services.s-<sid>.loadbalancer.serverstransport=insecure@file
     ota.session_id=<sid>   ota.user_id=<uid>   ota.created=<ts>
     ```
   - Das `basicauth`-Header-Middleware injiziert die KasmVNC-Credentials, sodass das Passwort **nie im Browser** landet
5. API antwortet mit `/s/<sid>/` → SPA öffnet die Session in einem `<iframe>` mit eigener Kontrollleiste
6. Jeder Request auf `/s/<sid>/*` läuft durch `forwardAuth` → `GET /api/internal/authz?sid=<sid>` prüft Cookie-Identität gegen Session-Eigentümer. Fremde Session = 403.
7. Heartbeat vom Client alle 30 s → `last_seen`. Kein Heartbeat > `idle_timeout` → Worker stoppt/löscht Container gemäß Policy.

### 4.3b Drei Stolpersteine, die beim Bauen auftraten

Alle drei scheitern **lautlos** — nichts stürzt ab, es funktioniert nur nicht. Sie sind hier
dokumentiert, weil sie sonst bei jeder Erweiterung erneut zuschlagen.

**1 · Der KasmVNC-Client sucht den WebSocket an der Wurzel.**
Er hängt seinen Pfad an `/`, nicht an den aktuellen Pfad. Unter `/s/<id>/` versucht er also
`wss://host/websockify`, landet bei der Weboberfläche und bekommt HTTP 200 statt eines Upgrades.
Die Seite lädt, das Bild bleibt schwarz, und im Server-Log steht nichts. Gelöst über den
URL-Parameter, den die API mitgibt:

```
/s/<session-id>/?path=s/<session-id>/websockify
```

**2 · Mehrere Dienste je Container verlangen eine ausdrückliche Zuordnung.**
Sobald ein Container mehr als einen Traefik-Dienst definiert — beim Arbeitsplatz einer je
App-Display —, muss **jeder** Router seinen Dienst benennen
(`traefik.http.routers.<name>.service=<name>`). Fehlt das, verwirft Traefik **alle** Router dieses
Containers, nicht nur die mehrdeutigen. Der Stream ist dann weg, ohne dass an der Konfiguration
etwas falsch aussieht.

**3 · Ein fehlender Router darf nicht auf der Weboberfläche landen.**
Weil die Weboberfläche auf `PathPrefix('/')` liegt und für jeden Pfad die Anwendung mit HTTP 200
ausliefert, sähe Fall 2 von aussen aus wie eine Session ohne Anmeldung. Deshalb liegt über `/s/`
ein **Schutzwall** (`deploy/traefik/dynamic/session-guard.yml`) mit Priorität 50 — unter den echten
Session-Routern (100 und 200), über der Weboberfläche (1). Er greift nur, wenn kein Session-Router
passt, verlangt trotzdem eine Anmeldung und antwortet dann mit einer verständlichen Meldung.
Geprüft in `scripts/test-authz.sh`.

### 4.4 Warum kein direkter Container-Port-Mapping-Ansatz
Kein `-p 690x:6901` pro Session: Das würde Ports leaken, TLS pro Session erzwingen und die Autorisierung umgehbar machen. Alles läuft ausschließlich durch Traefik.

---

## 5. Datenmodell

```
users              (id, username, email, display_name, password_hash[argon2id],
                    auth_provider[local|ldap|oidc], external_id, is_active, is_locked,
                    must_change_password, totp_secret, webauthn_credentials,
                    locale, theme, timezone, last_login_at, created_at)

groups             (id, name, slug, description, is_system, priority, created_at)
group_members      (group_id, user_id, source[manual|ldap|oidc])
permissions        (id, key, description)              -- z.B. "images.manage"
group_permissions  (group_id, permission_id)

templates          (id, slug, friendly_name, description, icon, categories[],
                    engine[kasmvnc|codeserver|guac_rdp|guac_vnc],
                    image_ref, image_version_id, cores, memory_bytes, gpu,
                    x_res, y_res, env{}, volumes[], persistent_profile_scope,
                    enforce_persistence, session_time_limit, idle_timeout,
                    is_enabled, is_hidden, created_at, updated_at)

group_templates    (group_id, template_id)             -- Zuweisung = Sichtbarkeit
user_templates     (user_id, template_id)              -- Einzelzuweisung (Ausnahme)

-- Abweichende Vorgaben je Gruppe oder je Nutzer für EINEN Workspace.
-- Nur gesetzte Spalten überschreiben; NULL bedeutet "erben".
template_overrides (id, template_id, scope[group|user], target_id,
                    cores, memory_bytes, x_res, y_res, gpu,
                    session_time_limit, idle_timeout, idle_action,
                    env_patch{}, rights_patch{},
                    created_by, created_at, updated_at,
                    UNIQUE(template_id, scope, target_id))

image_builds       (id, template_id, version, base_image, dockerfile, build_args{},
                    setup_script, skeleton_source, status[queued|building|ok|failed],
                    log, digest, size_bytes, built_by, built_at, is_current)

sessions           (id, user_id, template_id, image_version_id, container_id,
                    status[starting|running|paused|stopping|stopped|failed],
                    host_id, vnc_secret_hash, profile_path,
                    started_at, last_seen_at, ended_at, end_reason)

profiles           (id, user_id, scope, path, size_bytes, last_backup_at)

settings           (key, value_json, scope[global|group|user], owner_id)
auth_providers     (id, type[ldap|oidc], name, config_json, is_enabled,
                    group_mapping_json, auto_create_users)
audit_log          (id, ts, actor_user_id, action, object_type, object_id,
                    ip, user_agent, detail_json)
```

**Vererbungsreihenfolge für Settings**: `global` → `group` (nach `priority`) → `user` → `template`. Genau wie in Kasm, damit Admins ein mentales Modell behalten.

**Auflösung der Ressourcen für ein konkretes Paar (Nutzer, Workspace)** — das Spezifischste gewinnt:

```
1. templates.cores / memory_bytes                     Vorgabe der Vorlage
2. template_overrides (scope=group)                   je Gruppe des Nutzers,
                                                      in Reihenfolge groups.priority
3. template_overrides (scope=user)                    Zuteilung für genau diesen Nutzer
```

Damit bekommt derselbe VS-Code-Workspace für Nutzer A 4 Kerne / 4 GB, für Nutzer B 1 Kern / 1 GB und
für die Gruppe `externe` pauschal 1 Kern / 1,5 GB — ohne dass dafür Kopien der Vorlage angelegt werden
müssen. Eine Kopie wäre der naheliegende, aber falsche Weg: Sie vervielfacht die Pflege von Image,
Rechten und Golden-Image-Version. Ein Override lässt genau die drei Zahlen abweichen und erbt alles
andere weiter.

Referenzimplementierung der Auflösung: `web/src/mock/data.ts` → `effectiveResources()`.
Sie ist bewusst so geschrieben, dass sie 1:1 in die API übernommen werden kann.

**Durchsetzung**: Der aufgelöste Wert wird beim Session-Start in `sessions` festgeschrieben und als
`--cpus` / `--memory` an den Container übergeben. Eine spätere Änderung des Overrides wirkt erst auf
die nächste Session — laufende bleiben unberührt, damit niemandem im Betrieb der Speicher entzogen wird.

---

## 6. Authentifizierung und Rechtekonzept

### 6.1 Eigene Nutzerverwaltung (Kern, immer aktiv)
- Passwörter: **Argon2id** (`argon2-cffi`), Mindestlänge 12, Prüfung gegen eine Liste kompromittierter Passwörter
- Sessions: **JWT im `HttpOnly`+`Secure`+`SameSite=Lax`-Cookie**, kurze Access-Lifetime (15 min) + Refresh-Token mit Rotation und serverseitiger Sperrliste
- **2FA optional pro Nutzer/Gruppe erzwingbar**: TOTP (v1), WebAuthn/Passkeys (v2)
- Self-Service: Passwortwechsel, 2FA-Verwaltung, Theme/Sprache — mehr nicht
- Brute-Force-Schutz: exponentielles Backoff pro Account und IP, Lockout nach N Fehlversuchen, alles im Audit-Log
- Admin-Funktionen: Anlegen, Deaktivieren, Sperren, Passwort-Reset erzwingen, Gruppenmitgliedschaft, Session-Kill

### 6.2 Optionale Provider (zuschaltbar, nie Voraussetzung)
- **LDAP/AD** (`ldap3`, LDAPS/StartTLS): Bind-DN + Search-Base, Login-Attribut wählbar (`sAMAccountName` / `userPrincipalName`), **Gruppen-Mapping AD-Gruppe → OTA-Gruppe**, Just-in-Time-User-Anlage optional, nächtlicher Sync-Job für Deaktivierungen
- **OIDC** (Keycloak, Entra ID, Authentik …): Standard-Authorization-Code-Flow mit PKCE, Claim→Gruppen-Mapping
- **Fallback-Regel**: Mindestens ein lokaler Admin-Account bleibt immer aktiv, damit ein LDAP-Ausfall dich nicht aussperrt. Das UI verhindert das Löschen des letzten lokalen Admins.

### 6.3 Rollen und Sichtbarkeit
Zwei Systemgruppen, nicht löschbar:

| Gruppe | Rechte |
|---|---|
| `admins` | Alles: Templates, Golden Images, Builds, Nutzer, Gruppen, Zuweisungen, globale Settings, alle Sessions, Audit-Log, Host-Status |
| `users` | Nur eigenes Dashboard: zugewiesene Templates starten, eigene Sessions verwalten, eigene Profileinstellungen |

Feingranulare Permissions existieren im Modell (`images.manage`, `users.manage`, `sessions.view_all`, `settings.manage`, `audit.view`), damit später Rollen wie „Support" (darf Sessions sehen, nicht konfigurieren) ohne Schemaänderung möglich sind.

**Durchsetzung an drei Stellen — nicht nur im UI:**
1. Route-Guard im Frontend (Komfort)
2. FastAPI-Dependency `require_permission(...)` an **jedem** Admin-Endpunkt (Wahrheit)
3. Query-Level-Scoping: Nicht-Admins bekommen ausschließlich `WHERE user_id = me` — kein „Filter im Frontend"

---

## 7. Session-Lifecycle

| Ereignis | Verhalten |
|---|---|
| Start | Preflight: Ressourcen (RAM/CPU/Disk) prüfen, sonst freundliche Fehlermeldung statt OOM-Kill |
| Verbinden | Reconnect auf laufende Session statt Neustart (Browser-Refresh darf nichts kosten) |
| Pause | `docker pause` — RAM bleibt belegt, Wiederaufnahme in <1 s |
| Stopp | `docker stop` mit Grace-Period; Profil bleibt auf Platte |
| Idle-Timeout | Kein Heartbeat > `idle_timeout` (Default 60 min) → Aktion je nach Policy: `pause` \| `stop` \| `delete` |
| Hard-Limit | `session_time_limit` — Warnbanner 10 min vorher im Session-Viewer |
| Crash | Agent erkennt `exited`, markiert Session `failed`, hält Logs 7 Tage vor, bietet „Neu starten" |
| Orphan-GC | Container mit `ota.session_id`-Label ohne DB-Eintrag werden nach 10 min entfernt |

Alle Timeouts sind pro Gruppe und pro Template überschreibbar.

---

## 8. Golden-Image-Konzept

Das ist der Teil, der über Kasm hinausgeht, und deshalb bewusst ausführlich.

### 8.1 Was ein Golden Image bei OTA ist
Ein **Blueprint** besteht aus vier Schichten:

1. **Basis** — ein bestehendes Image (`kasmweb/vs-code:…`, `ubuntu:24.04`, ein eigenes `ota/base-xfce`)
2. **Build-Layer** — deklarativ im UI gepflegt und zu einem Dockerfile gerendert:
   - APT-/PIP-/NPM-Pakete
   - **VS-Code-Extensions als Liste** (`code --install-extension …` beim Build, nicht beim Start)
   - freies Setup-Skript (Bash) für alles Weitere
   - Build-Args und Proxy-Einstellungen
3. **Skeleton-Profil** — ein Verzeichnisbaum, der beim *ersten* Start eines Nutzers in dessen persistentes Profil kopiert wird: vorkonfigurierte `settings.json`, `keybindings.json`, Git-Config-Vorlage, Zertifikate, Desktop-Verknüpfungen, XFCE-Theme
4. **Runtime-Policy** — CPU/RAM, Auflösung, ENV, Volumes, Clipboard-/Upload-/Audio-Rechte, Timeouts

### 8.2 Versionierung
- Jeder Build erzeugt `ota/<slug>:v<N>` plus Digest, Größe und vollständiges Build-Log in der DB
- Genau eine Version ist `is_current` → neue Sessions nutzen sie; **laufende Sessions bleiben unberührt**
- **Rollback** = eine andere Version auf `current` setzen, ein Klick
- Optionaler „Canary": Version einer Testgruppe zuweisen, bevor sie global wird
- Alte Versionen werden nach Aufbewahrungsregel (Default: letzte 3) automatisch geprunt

### 8.3 „Session einfrieren" — der schnelle Weg zum Golden Image
Realistisch arbeitet man iterativ: Admin startet eine Session, richtet alles interaktiv ein, klickt dann **„Als Golden Image speichern"**. OTA macht:
1. `docker commit` des laufenden Containers → Zwischen-Image
2. Diff des Home-Verzeichnisses gegen das Basis-Skeleton → Vorschlag für das neue Skeleton-Profil
3. Anzeige der Änderungen zur Bestätigung (**Geheimnisse werden herausgefiltert**: `.ssh/id_*`, `.gnupg`, `*token*`, `*.pem`, `.aws`, `.docker/config.json`, Browser-Cookies)
4. Speichern als neue Version mit Kommentar

Das ist die Funktion, die in Kasm am meisten fehlt, und sie ist der Hauptgrund, warum sich die Eigenentwicklung lohnt.

### 8.4 Profil-Reset und Drift
- Nutzer: **„Mein Profil zurücksetzen"** — legt eine Sicherung an und stellt das Skeleton wieder her
- Admin: Reset für einzelne Nutzer oder ganze Gruppen erzwingen
- „Enforce"-Modus pro Template: Bestimmte Dateien werden bei **jedem** Start aus dem Skeleton überschrieben (z. B. Firmen-CA, Proxy-Config), der Rest bleibt persistent

### 8.4b Kasm und OTA vertragen sich beim Bauen nicht

**Gemessen am 2026-08-27, und es kostet sonst viel Zeit:** Kasms Agent räumt
Docker-Images auf. Im Modus **„Aggressive"** — der Voreinstellung — läuft er etwa alle
30 Sekunden und **löscht jedes Image, das er nicht kennt**. Auch unsere Golden Images.

```
[DEBUG] Searching for images to prune with mode: (Aggressive)
[DEBUG] Docker image id (sha256:8956eb…): with tags (['ota/arbeitsplatz:v1']): is not needed.
[INFO]  Successfully pruned unneeded Docker image id (sha256:8956eb…)
```

Das Fehlerbild ist tückisch, weil nichts schiefzugehen scheint: Der Build läuft durch,
meldet Erfolg, das Image ist sofort danach abfragbar — und Sekunden später weg. Der
erste Sessionstart scheitert dann mit „Image liegt nicht auf diesem Host", und im
Build-Log steht kein Fehler.

**OTA erkennt das inzwischen selbst.** 45 Sekunden nach einem erfolgreichen Build wird
nachgesehen, ob das Image noch im Store liegt. Ist es verschwunden, wird der Build auf
`failed` gesetzt und das Log erklärt Ursache und Abhilfe im Klartext, statt einen
rätselhaften Erfolg stehenzulassen.

**Abhilfe, eine von beiden:**
1. In Kasm unter *Infrastructure → Servers* die Aufräum-Einstellung
   (`servers.prune_images_mode`, derzeit auf allen drei Einträgen `Aggressive`) auf eine
   mildere Stufe setzen. Die gültigen Alternativwerte ließen sich aus der laufenden
   Installation nicht ableiten — sie stehen in Kasms Oberfläche zur Auswahl.
2. Golden Images erst bauen, **nachdem** Kasm abgelöst ist (Roadmap M7).

**Was das für den Plan bedeutet:** Der Parallelbetrieb aus §16 gilt weiterhin für alles
Übrige — Sessions, Streams, Nutzer, Zuweisungen laufen unbeeinträchtigt nebeneinander.
Nur das **Bauen** von Golden Images ist blockiert, solange Kasm aggressiv aufräumt. Das
verschiebt M5 hinter eine Entscheidung, die dir gehört (§17.12).

### 8.5 Build-Ausführung
- Builds laufen im `ota-agent` über **`docker buildx build --load`**, nicht über die
  klassische Build-API des Python-SDK. Auf einem Host mit **containerd-Image-Store** legt
  der klassische Builder bei Multi-Plattform-Basisimages — und das sind die Kasm-Images —
  kein benutzbares Image im Store ab. Er meldet Erfolg, `images.get()` findet das Image
  noch, `docker images` listet es nie. Der Agent bringt dafür `docker-ce-cli` und
  `docker-buildx-plugin` mit
- Erfolg gilt erst, wenn das Image **nachweislich im Store liegt** — nicht schon, wenn der
  Builder Erfolg meldet
- Serialisiert (max. 1 paralleler Build), damit die 4-Core-Maschine nicht kollabiert
- Timeout 45 min, abbrechbar
- Optional: nächtlicher Rebuild zur Aufnahme von Sicherheitsupdates, mit Diff-Benachrichtigung

---

## 9. Der Arbeitsplatz — das Kernmodell

Der **Arbeitsplatz** ist das, wofür OTA gebaut wird: ein persistenter Linux-Container pro Nutzer, in
dem mehrere Anwendungen installiert sind und einzeln in den Browser gestreamt werden.

Die vorangegangenen Abschnitte (§4 Architektur, §5 Datenmodell, §7 Lifecycle, §8 Golden Images) gelten
für beide Betriebsarten. Ein Template trägt das Feld `mode`:
- `workspace` — der Arbeitsplatz, **Standard**
- `single_app` — eine Anwendung als Wegwerf-Container, für eingebundene Kasm-Images (§9.8)

### 9.1 Warum der Arbeitsplatz das richtige Kernmodell ist
- **Ein Zuhause statt vieler Inseln.** Alle Werkzeuge teilen sich `/home`, SSH-Keys, Git-Konfiguration,
  Projektverzeichnisse und die Zwischenablage der Sitzung. Heute liegt derselbe Klon dreimal herum,
  wenn jemand VS Code, JetBrains und ein Terminal nutzt.
- **AD-Anmeldung wird sinnvoll.** Ein Nutzer, ein Container, eine Identität — erst damit lohnt es sich,
  Kerberos-Tickets hineinzureichen und Netzlaufwerke zu mounten (§9.4).
- **Golden Images werden mächtiger.** Ein Blueprint stattet mehrere Anwendungen gleichzeitig aus.
- **Weniger Grundlast.** Die Ersparnis ist real, aber kleiner als sie wirkt — siehe §9.3.
- **Ressourcen gehören zum Menschen, nicht zum Werkzeug.** Ein Kontingent pro Nutzer ist das, was
  Admins ohnehin verwalten wollen. Pro-App-Grenzen sind eine Buchhaltung, die niemand braucht.

### 9.2 Wie einzelne Apps gestreamt werden

Die Kernfrage ist die Streaming-Engine. Drei Wege wurden geprüft:

| Weg | Wie | Bewertung |
|---|---|---|
| **A · KasmVNC, ein Display je App** | Pro App ein eigenes `Xvnc` auf `DISPLAY=:N` mit eigenem Websocket-Port; die App läuft dort formatfüllend | **Empfehlung.** Nutzt die komplette bestehende Strecke weiter: gleiche Proxy-Route, gleiche Zwischenablage, gleicher Ton, gleiche Kontrollleiste |
| **B · Xpra seamless** | Ein Server, einzelne Fenster werden weitergereicht (`xpra seamless`, GPL-2.0, HTML5-Client vorhanden) | Eleganter für „viele Fenster, eine Verbindung", **und hätte nur eine Zwischenablage** (§10.4). Aber **zweite Engine** mit eigenem Client, eigenem Audiopfad und eigener Kontrollleiste. Dauerhafte Mehrkosten in der Pflege |
| **C · Ein Desktop, App per Fenstermanager fokussieren** | Alles auf `:1`, das UI schickt Fokus-Kommandos | Billigste Variante, aber der Nutzer sieht fremde Fenster aufblitzen. Verworfen |

Zusätzlich bleibt der **klassische Desktop** als Ansicht erhalten: Wer lieber einen kompletten
XFCE-Desktop mit Fensterleiste sehen will statt einzelner Vollbild-Apps, bekommt ihn auf `:0`.
Beides parallel, der Nutzer entscheidet.

**Entscheidung: Weg A.** Der ausschlaggebende Punkt ist nicht Eleganz, sondern dass Modus A und Modus B
sich **dieselbe Engine teilen**. Jede Abweichung dort verdoppelt Fehlersuche, Zwischenablage-Logik und
Kontrollleiste auf Dauer. Xpra bleibt als dokumentierte Alternative in §17.8 (offener Punkt), falls echte Einzelfenster
statt formatfüllender Apps zur Anforderung werden.

**Ein Preis, der zu Weg A gehört**: Jedes Display bringt seine eigene X-Zwischenablage mit. Kopieren
in VS Code auf `:1` und Einfügen in IntelliJ auf `:2` funktioniert ohne Gegenmaßnahme **nicht**. Weg A
braucht deshalb zwingend die Zwischenablage-Brücke aus §10.4 — eingeplant, nicht nachgereicht.

**Einzelinstanz-Anwendungen brauchen eine Sonderbehandlung.** VS Code, Chrome und Thunderbird
erlauben nur eine Instanz je Nutzer: Ein zweiter Aufruf meldet sich bei der laufenden Instanz und
beendet sich, ohne ein Fenster zu öffnen. Wer das nicht einplant, bekommt ein schwarzes Display
und keinerlei Fehlermeldung. Zwei Wege:

- Startet das Image die Anwendung ohnehin selbst — wie `kasmweb/vs-code` es mit VS Code auf `:1`
  tut —, trägt sie im Katalog ihr festes Display ein (`fixed_display`). OTA startet sie dann nicht
  erneut, sondern blendet sie nur ein.
- Soll eine solche Anwendung mehrfach laufen, braucht jede Instanz einen eigenen
  Konfigurationspfad (`--user-data-dir` bei VS Code). Das trennt aber auch die Einstellungen und
  ist deshalb selten das, was man will.

**Displays werden bei Bedarf gestartet, nicht auf Vorrat.** Beim Containerstart läuft kein einziger
X-Server. Klickt jemand auf „VS Code", startet der Agent `Xvnc` auf dem nächsten freien Display und die
App darin. Wird die App geschlossen oder ist sie lange unbenutzt, fällt das Display wieder weg. Ein
leerlaufender Multi-App-Container kostet damit fast nichts.

```
Container ota-user-bmetallica
  ├─ :1  6901  Visual Studio Code   ← läuft
  ├─ :2  6902  IntelliJ IDEA CE     ← läuft
  ├─ :3  6903  VSCodium             ← nicht gestartet, kostet nichts
  └─ /home/bmetallica              gemeinsames Zuhause aller Apps
```

Routing analog zu §4.3: `/s/<sid>/a/<n>` → Port `690N`, abgesichert über dasselbe `forwardAuth`.

**Umsetzungsstand (2026-08-27): gebaut und geprüft.** Weil sich Traefik-Labels an einem laufenden
Container nicht mehr ändern lassen, werden die Routen für sechs App-Displays beim Containerstart
**auf Vorrat** angelegt. Sie kosten nichts, solange kein Display dahinter läuft. Die Displaynummer
ergibt sich aus der Reihenfolge im App-Katalog und ist damit über Neustarts hinweg stabil.

### 9.3 Ressourcenersparnis bei CPU und RAM

Die Ersparnis ist real, sitzt aber woanders, als man zuerst vermutet. Ehrlich aufgeschlüsselt.

#### Arbeitsspeicher

Was ein Ein-App-Container an **Grundlast** mitbringt, bevor die Anwendung überhaupt startet:

| Bestandteil | grob |
|---|---|
| Xvnc / KasmVNC-Server | 50–150 MB |
| XFCE-Sitzung (`xfwm4`, `xfdesktop`, Panel, `xfsettingsd`) | 150–300 MB |
| PulseAudio | 20–40 MB |
| dbus, Init, Hilfsdienste | 30–60 MB |
| **Summe je Container** | **250–550 MB** |

Im Arbeitsplatz fällt davon der größte Teil **nur einmal** an: eine PulseAudio-Instanz, ein dbus, ein
Init, ein Satz Hintergrunddienste. Übrig bleibt pro geöffneter App ein eigener `Xvnc` und ein
minimaler Fenstermanager — die vollständige XFCE-Sitzung mit Desktop und Panel braucht eine
formatfüllende Anwendung nicht.

Bei drei gleichzeitig geöffneten Werkzeugen: grob **400–800 MB gespart**, bei fünf entsprechend mehr.
Auf einem Host mit 15 GB ist das ein knapper Arbeitsplatz mehr.

**Was nicht gespart wird**, und das ist der ehrliche Teil: der Speicher der Anwendungen selbst. Wer
VS Code, IntelliJ und einen Browser gleichzeitig offen hat, zahlt deren Speicher in Summe — in beiden
Modellen. Der Container muss deshalb auf die **Spitze** ausgelegt werden.

**Ein Effekt, der die Rechnung dämpft**: Container aus demselben Image teilen sich auf dem Host den
Page-Cache der identischen Dateien — glibc, GTK, Qt liegen physisch nur einmal im RAM, auch bei zehn
Containern. Der oft genannte „jede Kopie lädt die Bibliotheken neu"-Effekt gilt so nicht. **Sehr wohl**
gilt er zwischen *verschiedenen* Images: `kasmweb/vs-code` und `linuxserver/intellij-idea` teilen sich
nichts. Genau hier gewinnt der Arbeitsplatz, weil alle Werkzeuge aus **einem** Image kommen.

#### Prozessor

Hier ist der Gewinn deutlicher, und er hat einen anderen Grund als erwartet.

**Der teure Posten ist die Videokodierung, nicht die Anwendung.** KasmVNC kodiert den Framebuffer nur,
wenn ein Client verbunden ist und sich etwas ändert. Ein Display ohne angehängten Browser kostet
praktisch nichts.

Im Arbeitsplatz schaut ein Nutzer **auf ein Werkzeug zur Zeit**. Es läuft also genau ein Encoder.
Bei getrennten Containern mit mehreren offenen Browser-Tabs laufen mehrere Encoder gleichzeitig,
obwohl der Mensch nur auf einen Tab blickt. Das ist bei bewegtem Inhalt der mit Abstand größte
CPU-Posten des ganzen Systems.

Dazu die Leerlaufkosten: Jede XFCE-Sitzung, jeder Compositor, jedes Panel pollt vor sich hin —
je Container grob ein halbes bis zwei Prozent eines Kerns. Bei fünf Containern also gut ein
Zehntel Kern, der nichts tut. Im Arbeitsplatz fällt das einmal an.

**Der eigentliche Gewinn ist aber ein anderer: der Admin bekommt die Kontrolle zurück.** Bei fünf
Containern à 2 Kernen kann ein einzelner Nutzer auf **10 Kerne** hochlaufen — auf einem 4-Kern-Host
eine Überbuchung um das Zweieinhalbfache. Ein Arbeitsplatz mit `--cpus=4` deckelt denselben Nutzer bei
4, egal wie viele Werkzeuge er öffnet. Das Kontingent gehört zum Menschen, nicht zum Werkzeug — und
genau das lässt sich verwalten.

#### Was dagegen spricht

1. **Ein Container ist ein gemeinsamer Absturzradius.** Ein OOM-Kill oder ein hängender X-Server reißt
   alle Werkzeuge des Nutzers mit; bei getrennten Containern stirbt nur eines. Gegenmittel:
   großzügiges `mem_limit`, `oom_score_adj` für die Session-Prozesse, und Displays einzeln neu
   startbar halten, ohne den Container zu verlieren.
2. **Die Zwischenablage braucht eine Brücke** — siehe §10.4.
3. **Plattenplatz**, der kleinste der drei Punkte: Ein Image mit fünf Werkzeugen landet bei 12–18 GB.
   Es liegt aber **einmal** auf dem Host, unabhängig von der Zahl der Nutzer, während fünf getrennte
   Images zusammen ähnlich viel belegen. Auf diesem Host mit 60 GB frei ist es zu budgetieren, aber
   kein Argument gegen das Modell.

### 9.4a Anmeldung gegen ein Verzeichnis — umgesetzt

**Stand 2026-08-28: gebaut und geprüft** (`api/ota/directory.py`, `api/ota/identity.py`,
Oberfläche unter *Einstellungen → Verzeichnis*). Geprüft gegen ein echtes OpenLDAP im Container;
`scripts/ldap-test-server.sh` startet es, `scripts/test-ldap.sh` fährt 29 Prüfungen dagegen und
räumt hinterher auf.

**Die eine Regel, die alles andere überlagert:**

> Ein lokales Konto wird niemals über das Verzeichnis angemeldet, und ein Verzeichniseintrag kann
> ein lokales Konto niemals übernehmen.

Wo ein Passwort geprüft wird, entscheidet allein `users.auth_provider` — nicht die Anfrage, nicht
das Verzeichnis, und der Wert ändert sich nie von selbst. Der Angriff dahinter ist unspektakulär
und deshalb leicht zu übersehen: Wer im Verzeichnis einen Eintrag anlegen darf, legt einen mit dem
Namen des ersten Administrators an und meldet sich mit seinem eigenen Passwort als dieser an. Das
Testverzeichnis enthält deshalb absichtlich einen Eintrag `bmetallica`; die Prüfung besteht darin,
dass er **nicht** hereinkommt.

**Drei Entscheidungen, die beim Bauen gefallen sind:**

*Der Code liegt in der API, nicht im Agent.* Das widerspricht
[ADR-002](docs/adr/002-nur-der-agent-fasst-docker-an.md), und der Grund ist der Inhalt: Beim
Anmelden wandert das Passwort eines Menschen durch diesen Code. Es zusätzlich über eine interne
HTTP-Verbindung an einen zweiten Dienst zu reichen, verteilt ein Geheimnis auf mehr Stellen, statt
es zu schützen. Die Trennung dient der Angriffsfläche; sie hier anzuwenden würde ihr schaden.

*Kein Ausweichen auf einen lokalen Hash, wenn das Verzeichnis ausfällt.* Das wäre ein zweiter Weg
an der Stelle, an der es genau einen geben soll — und er wäre genau dann offen, wenn das
Verzeichnis nicht widersprechen kann. Lokale Konten sind von einem Ausfall ohnehin nicht betroffen;
gemessen 33 ms bis zur Ablehnung eines Verzeichniskontos, kein Zeitablauf.

*Ein leeres Passwort wird abgelehnt, bevor es hingeht.* Ein LDAP-Bind ohne Passwort gilt als
anonyme Anmeldung und **gelingt**. Wer das übersieht, baut eine Anmeldung, bei der ein leeres Feld
jeden hereinlässt.

**Wer im Verzeichnis verschwindet, wird deaktiviert — nicht gelöscht.** Zuhause, Sicherungen und
Protokollspur bleiben. Löschen ist eine Entscheidung, die ein Mensch trifft.

### 9.4 AD-Anmeldedaten in den Container reichen — offen

Das ist der sicherheitskritischste Teil des ganzen Projekts, deshalb ausführlich.
Ziel: Der Nutzer erreicht im Container seine gewohnten Netzlaufwerke.

**Nichts davon ist gebaut.** Dafür reicht ein LDAP-Server nicht: Es braucht ein echtes AD mit KDC
und Dateiservern, und ohne eines lässt sich keiner der vier Wege ehrlich prüfen.

**Vier Wege, absteigend nach Sauberkeit:**

| Weg | Was passiert | Bewertung |
|---|---|---|
| **1 · Kerberos-SSO mit Delegation** (S4U2Proxy) | Browser meldet sich per Negotiate an OTA an, OTA holt sich per eingeschränkter Delegation ein Ticket für den Fileserver | **Sauberste Lösung. Ein Passwort erreicht OTA nie.** Verlangt SPNs, konfigurierte Delegation und domänengebundene Clients |
| **2 · Kerberos-Ticket-Injektion** | OTA prüft die Anmeldung gegen AD, holt dabei ein TGT und legt den Credential-Cache in den Container. Mount per `sec=krb5` | **Praktischer Standardweg.** Kein Passwort im Container, Ticket läuft nach ~10 h ab. OTA sieht das Passwort aber kurz beim Login |
| **3 · Nutzer verbindet selbst** | Im Container ein Knopf „Laufwerk verbinden", Passworteingabe dort | **Immer verfügbarer Rückfall.** Null Risiko für die Plattform, minimal unbequem |
| **4 · Passwort-Durchreichung** | OTA hält das Passwort für die Sitzungsdauer und mountet damit | **Nur als ausdrückliches Opt-in.** Macht OTA zum Passwortspeicher — eine erhebliche Vergrößerung des Schadensradius |

**Empfehlung**: Weg 2 als Standard, Weg 1 wo die AD-Konfiguration es hergibt, Weg 3 immer verfügbar.
Weg 4 bleibt abschaltbar und ist **standardmäßig aus**, mit einem unmissverständlichen Warntext im
Admin-UI. Ich baue ihn nicht heimlich ein, weil er bequem ist.

**Harte Regeln, unabhängig vom gewählten Weg:**
- **Niemals als Umgebungsvariable.** `-e SMBPASS=…` ist über `docker inspect` für jeden mit Docker-Zugriff
  lesbar und landet in Logs. Zugangsdaten gehören in eine `tmpfs`-Datei mit `0600`, die nie auf Platte geht.
- **Niemals ins Golden Image.** Der Secret-Filter aus §8.3 greift auch hier, erweitert um `krb5cc_*`,
  `.smbcredentials` und `keytab`.
- **Nie ins persistente Profil**, sonst überlebt das Ticket die Sitzung.
- **Identitätsabbildung**: Damit Dateirechte auf den Shares stimmen, braucht der Containernutzer die
  UID/GID aus AD. Leichter Weg: `uidNumber`/`gidNumber` beim Start aus dem Verzeichnis lesen und setzen.
  Schwerer Weg: SSSD im Container. Empfehlung ist der leichte Weg, SSSD als Option.
- **Ticket-Erneuerung** läuft im Container per `k5start`, nicht durch erneutes Nachfragen bei OTA.

### 9.5 Golden Images für Multi-App-Container

Der Blueprint aus §8 wird um einen **App-Katalog** erweitert. Jede App im Katalog trägt:

```
slug · Anzeigename · Icon · Startbefehl + Argumente
Engine (kasmvnc)   · bevorzugte Auflösung
Skeleton-Teilbaum  · z. B. .config/Code/User/ für VS Code,
                          .config/JetBrains/ für IntelliJ,
                          .config/VSCodium/User/ für VSCodium
Extensions-Liste   · wird beim Build installiert, nicht beim Start
Sichtbarkeit       · je Gruppe zuschaltbar
```

Damit lässt sich genau das erreichen, was du beschrieben hast: ein vorkonfiguriertes VS Code mit
gesetzten Extensions und Einstellungen für alle Anwender, ausgerollt über eine Version, mit Rollback.
„Session einfrieren" (§8.3) funktioniert unverändert — es erfasst jetzt nur mehrere App-Konfigurationen
auf einmal.

**Ein Stolperstein, der dokumentiert gehört**: Extensions wandern **nicht** zwischen den Editoren.
VS Code zieht aus dem Microsoft-Marketplace, VSCodium und Cursor aus Open VSX bzw. eigenen Registries
(§9.6). Wer in beiden arbeitet, pflegt zwei Extension-Sätze. Das UI muss das benennen, statt es
den Nutzer selbst herausfinden zu lassen.

### 9.6 Lizenzlage der genannten Apps

Geprüft am 2026-08-27:

| App | Lizenz | Im Multi-App-Container |
|---|---|---|
| **VS Code** (MS-Build) | proprietär, MS-EULA | **Ja** — §3.1 erlaubt internes Deployment ausdrücklich. Marketplace nutzbar |
| **VSCodium** | **MIT** (verifiziert) | **Ja**, uneingeschränkt. Nur Open VSX, keine MS-Extensions wie Remote-SSH oder Pylance |
| **IntelliJ IDEA Community** | Apache-2.0 | **Ja**, kommerziell kostenfrei |
| **opencode** | **MIT** (verifiziert, `sst/opencode`) | **Ja**, uneingeschränkt |
| **Cursor** | **proprietär** | **Vor Aufnahme prüfen** — siehe unten |

**Zu Cursor, ausdrücklich**: Cursor ist Closed Source mit eigener EULA und kostenpflichtigen Stufen mit
Nutzerkonten. Zwei Dinge sind vor der Aufnahme zu klären, und ich kann sie dir nicht abnehmen:
1. Erlaubt Cursors EULA den Betrieb in einer zentral bereitgestellten Mehrbenutzer-Umgebung, und
   brauchen die Nutzer je eine eigene Lizenz? Bei Pro-Abos ist von Named-User auszugehen.
2. Cursor ist ein VS-Code-Fork und damit **kein MS-gebrandetes Produkt**. Der Microsoft-Marketplace
   darf daraus nach dessen ToU **nicht** angesprochen werden (§3.1). Cursor bringt eine eigene
   Registry mit — es darf keinesfalls per Konfiguration auf den MS-Marketplace umgebogen werden.

Bis diese Punkte geklärt sind, steht Cursor im Katalog auf `deaktiviert`. Die anderen vier sind
unbedenklich.

### 9.7 Auswirkungen auf das Datenmodell

```
templates          + mode [workspace | single_app]     -- workspace ist der Standard

template_apps      (id, template_id, slug, name, icon, exec, args,
                    engine, x_res, y_res, skeleton_path, extensions[],
                    is_enabled, sort_order)

group_template_apps (group_id, template_app_id, allowed)   -- App-Sichtbarkeit je Gruppe

app_streams        (id, session_id, template_app_id, display_num, port,
                    status, started_at, last_seen_at)      -- ein Eintrag je laufender App

identity_configs   (id, mode [none | krb_ccache | krb_delegation | password_optin],
                    realm, kdc_hosts[], uid_source, share_mounts[],
                    is_enabled, updated_by, updated_at)

-- Eingebundene Kataloge (§9.8). Der Inhalt wird gecacht, nicht bei jedem Blick geladen.
registries         (id, name, url, schema_version, channel, icon_url,
                    is_enabled, auto_update, last_fetched_at, last_modified,
                    workspace_count, fetch_error, added_by, added_at)

registry_entries   (id, registry_id, sha, friendly_name, description,
                    categories[], architectures[], icon_url, docker_registry,
                    image_ref, available_tags[], uncompressed_size_mb,
                    imported_template_id)        -- NULL, solange nicht importiert
```

Die Ressourcen-Overrides aus §5 gelten unverändert — sie beziehen sich beim Multi-App-Container auf den
Container als Ganzes, nicht auf die einzelne App. Das ist die richtige Ebene: begrenzt wird, was der
Nutzer insgesamt verbrauchen darf.

### 9.8 Kasm-Kompatibilität: Images und ganze Registries einbinden

Das Feature aus §1.2. Verifiziert am 2026-08-27 an der laufenden Kasm-Installation.

**Einzelne Images** einzubinden ist trivial: Ein Template mit `mode: single_app` und einer
Image-Referenz. Das ist der Weg, den die aktuellen Vorlagen (GIMP, LibreOffice, Obsidian …) schon gehen.

**Ganze Registries** sind der interessante Teil. Kasm veröffentlicht seinen Katalog als schlichte
JSON-Datei unter einer festen Adresse:

```
{registry_url}/{schema_version}/list.json
```

Verifiziert erreichbar (HTTP 200):
| Registry | URL | Workspaces |
|---|---|---|
| Kasm Technologies | `https://registry.kasmweb.com/1.1/list.json` | **86** |
| Kasm AI Images | `https://ai.registry.kasmweb.com/1.1/list.json` | 11 |
| LinuxServer.io | `https://kasmregistry.linuxserver.io/1.1/list.json` | 2 |

**Schema (1.1), am echten Dokument abgelesen:**

```jsonc
{
  "name": "Kasm Technologies",
  "description": "...",
  "icon": "https://…/icon.svg",
  "list_url": "…", "contact_url": "…",
  "workspacecount": 86,
  "modified": 1782309356658,
  "channels": ["develop", "1.16.0", "1.18.0-rolling-weekly", …],
  "default_channel": "…",
  "signature": "<JWT, ES256 — Hash über den Katalog>",
  "workspaces": [{
    "sha": "65ca92c…",                       // Kennung des Eintrags
    "friendly_name": "AlmaLinux 8",
    "description": "…",
    "categories": ["Desktop", "Productivity", "Development"],
    "architecture": ["amd64", "arm64"],
    "image_src": "almalinux.svg",            // relativ zur Registry-URL
    "docker_registry": "https://index.docker.io/v1/",
    "compatibility": [{
      "version": "1.16.x",
      "image": "kasmweb/almalinux-8-desktop:1.16.1-rolling-daily",
      "available_tags": ["develop", "1.16.0", …],
      "uncompressed_size_mb": 6528
    }]
  }]
}
```

Vorhandene Kategorien im offiziellen Katalog: Browser, Chat, Communication, Desktop, Development,
Games, Mobile, Multimedia, OSINT, Office, Privacy, Productivity, Remote Access, Security.
Kein einziger Eintrag verlangt eine GPU.

**Was OTA daraus baut:**
1. Admin trägt eine Registry-URL ein, OTA lädt `list.json` und zeigt den Katalog durchsuchbar an.
2. Beim Import wird ein Eintrag zu einem Template mit `mode: single_app` — `friendly_name`,
   `description`, `categories` und Icon werden übernommen, die Image-Referenz aus `compatibility`
   passend zur gewählten Kanalversion.
3. **Architektur prüfen**: Nur Einträge anbieten, die die Architektur des Hosts unterstützen.
4. **Größe anzeigen, bevor gezogen wird.** `uncompressed_size_mb` steht im Katalog — bei 60 GB freiem
   Platz auf diesem Host ist ein 6,5-GB-Image eine Entscheidung, keine Nebensache. Das UI warnt, wenn
   der Import den freien Platz nennenswert angreift.
5. `modified` erlaubt einen Aktualisierungs-Check, ohne den ganzen Katalog neu zu verarbeiten.
6. **Signatur**: Der Katalog trägt ein ES256-JWT über einen Hash des Inhalts. Ob OTA das prüft, ist
   entschieden (§17.11, [ADR-004](docs/adr/004-keine-signaturpruefung-fuer-registries.md)): **nein**
   — der öffentliche Schlüssel liegt bei Kasm, und ohne ihn wäre die Prüfung Theater. Es gilt:
   **Registries sind eine Vertrauensentscheidung des Admins**, und das UI sagt das auch so.
   Ein importiertes Image kommt aus einer fremden Quelle und läuft anschließend im eigenen Netz.

**Rechtlicher Hinweis**: Der Katalog verweist nur auf Images; deren Lizenzen gelten unverändert (§3).
Dass eine Registry ein Image listet, ist keine Aussage über dessen Lizenz. Der Import-Dialog verlinkt
deshalb auf §3 und markiert Images, die eine Einzelprüfung brauchen.

**Umgesetzt (2026-08-27).** Vier Dinge sind beim Bauen anders entschieden worden, als es hier stand:

*Gelesen wird im Agent, nicht in der API.* Es ist ein Griff nach draußen ins Netz — dieselbe
Trennung wie bei Docker und beim Dateisystem. Nebenbei kennt nur der Agent die Architektur des Hosts.

*Vorgeschlagen statt vorkonfiguriert.* Die drei bekannten Registries stehen als Vorschlag bereit,
eingetragen wird keine von selbst. Wenn eine Registry eine Vertrauensentscheidung ist, kann sie
nicht die Voreinstellung sein. Der Katalog wird beim Eintragen sofort gelesen — lässt er sich nicht
laden, entsteht kein Eintrag.

*Nicht die neueste Fassung, sondern die neueste stabile.* Punkt 2 oben („passend zur gewählten
Kanalversion") war zu naiv: Bei AlmaLinux 8 zeigen die beiden neuesten `compatibility`-Einträge auf
`kasmweb/almalinux-8-desktop:develop`, der letzte davon mit `uncompressed_size_mb: 0` — also noch
gar nicht gebaut. Vorgeschlagen wird deshalb die neueste Fassung, die kein `develop` ist und eine
echte Größe hat.

*Icons laufen über die API.* Die Inhaltsregel der Anwendung lässt keine fremde Bildquelle zu
(`img-src 'self'`), und sie je eingetragener Registry aufzuweichen wäre für ein Symbol ein
schlechter Tausch. Der Umweg ist gefesselt: Geholt wird nur, was unterhalb der Adresse **dieser**
Registry liegt, und nur, wenn ein Bild zurückkommt — sonst wäre er ein Werkzeug, mit dem sich über
OTA beliebige Adressen im internen Netz abrufen ließen. Dabei ist auch die Adresse der Symbole
korrigiert worden: Sie liegen nicht in der Wurzel der Registry, sondern neben dem Katalog unter
`{schema}/icons/`. Am echten Katalog nachgesehen — `registry.kasmweb.com/almalinux.svg` gibt 404,
`registry.kasmweb.com/1.1/icons/almalinux.svg` gibt das Bild.

Zu Punkt 6: **Entschieden — OTA prüft die Signatur nicht.** Der öffentliche Schlüssel liegt bei
Kasm; ohne ihn wäre die Prüfung Theater, und Theater ist schlechter als ein ehrlicher Hinweis.

Ein importiertes Template ist **abgeschaltet** und bekommt ein **eigenes Profil**
(`persistence_scope: template`): Ein Import soll nicht ungefragt auf allen Dashboards auftauchen,
und ein fremdes Image bekommt nicht den Schlüssel zum gemeinsamen `/home` des Arbeitsplatzes. Beim
Entfernen einer Registry bleiben übernommene Templates bestehen — der Katalog war nur der Weg, wie
sie entstanden sind.

### 9.9 Ein Arbeitsplatz startet nichts von selbst

Kasm-Images für einzelne Anwendungen bringen ein `/dockerstartup/custom_startup.sh` mit, das „ihre"
Anwendung startet. `vnc_startup.sh` beaufsichtigt dieses Skript und **startet es alle drei Sekunden
neu**, sobald es sich beendet — der Kommentar dort sagt ausdrücklich: *„custom startup scripts track
the target process on their own, they should not exit."*

Für ein Einzelanwendungs-Image ist das genau richtig: Stirbt die Anwendung, kommt sie zurück.

Für einen davon abgeleiteten Arbeitsplatz ist es verheerend. Gemessen am 2026-08-27 mit einem von
`kasmweb/vs-code` abgeleiteten Image:

1. Das geerbte Skript rief `code` auf.
2. VS Code ist einzelinstanzig. Die zweite Instanz reichte den Aufruf an die laufende weiter — das
   öffnete dort ein **neues, leeres Fenster** — und beendete sich.
3. Die Aufsicht sah ein beendetes Skript und startete es erneut. Alle drei Sekunden.

Nach sechs Minuten: 119 leere Fenster, 2,5 GB belegt, der Bildschirm zeigte nur noch Schwarz. Und
weil VS Code seine offenen Fenster im Profil merkt und beim Start wiederherstellt, überlebte der
Schaden jeden Neustart.

Ein Arbeitsplatz startet seine Anwendungen selbst, auf Zuruf, jede auf ihrem Display. Das geerbte
Skript wird deshalb überdeckt — durch eines, das einfach wartet und damit die Aufsicht
zufriedenstellt. Zweifach: beim Bauen eines Arbeitsplatz-Images (`render_dockerfile`) und beim Start
eines Containers als Bind-Mount (`WORKSPACE_STARTUP` im Agent), damit auch bereits gebaute Images
sofort in Ordnung sind.

**Was daraus folgt, über diesen Fall hinaus:** Ein Kasm-Image mitzubenutzen heisst nicht nur, seine
Software zu erben, sondern auch sein Startverhalten. Beim Einbinden fremder Images (§9.8) gehört die
Frage „was startet dieses Image von sich aus, und was tut es, wenn das stirbt?" zur Prüfung dazu.

### 9.10 Software einbauen, freigeben — und Rezepte selbst bauen

Der Weg von „ich hätte gern GIMP" bis „GIMP steht im Dashboard" hat zwei Schritte, und beide waren
lange nur als API vorhanden.

**Einbauen.** Pakete auswählen, Image bauen, Fassung aktivieren. Zwei Prüfungen davor, beide aus
gemessenen Fehlschlägen entstanden:

- **Kennt das Image dieses Paket?** Ein Build dauert Minuten und scheitert an einem Debian-Namen auf
  einem Ubuntu-Image (`firefox-esr`) erst am Ende, mit einer Zeile in hundert Zeilen Protokoll.
- **Taugt das Paket überhaupt?** Ubuntu 22.04 führt `firefox` nur noch als Verweis auf ein Snap. In
  einem Container läuft kein Snap; installiert würde ein Platzhalter ohne Programm. Der Build meldete
  Erfolg — und erst der Nutzer merkte, dass nichts da ist.

**Freigeben.** Niemand soll einen Startbefehl kennen müssen. Jedes Linux-Paket bringt eine
`.desktop`-Datei mit, in der Name, Symbol und Aufruf stehen — OTA liest sie aus dem gebauten Image
(`agent/otaagent/discover.py`) und macht daraus eine Liste mit Schaltern. Zugeordnet wird über
Kennung **und** Binärnamen: Der Katalog kennt `vscode`, die Datei heisst `visual-studio-code`, und
gemeint ist dasselbe Programm.

**Rezepte.** Für Software, die kein einfaches Paket ist. Anfangs drei fest eingebaute — das war zu
wenig: Wer eine vierte Anwendung brauchte, sass wieder vor einem leeren Skriptfeld, also genau dem,
was diese Oberfläche vermeiden soll.

Rezepte liegen jetzt in der Datenbank und entstehen aus wenigen Fragen (`api/ota/recipes.py`). Fünf
Muster decken fast alles ab: fremdes APT-Depot, `.deb` von einer Adresse, Archiv nach `/opt`,
AppImage, freies Skript. Zwei Entscheidungen darin sind bewusst:

- **Das Skript wird nicht versteckt.** Es steht neben den Fragen und lässt sich ändern; wer das tut,
  dessen Fassung gilt. Der Sinn der Führung ist nicht, Bash zu verbergen, sondern es nicht von Hand
  schreiben zu müssen.
- **Erzeugt wird auf dem Server**, obwohl eine Vorschau im Browser schneller wäre. Zwei Erzeuger für
  dasselbe laufen irgendwann auseinander, und dann stimmt die Vorschau nicht mehr mit dem überein,
  was gebaut wird.

Archiv und AppImage legen zusätzlich eine `.desktop`-Datei an. Das ist kein Beiwerk, sondern die
Verbindung zum zweiten Schritt: Ohne sie wäre die Anwendung installiert, aber beim *Im Image
nachsehen* nicht auffindbar.

### 9.11 Was ins Image gehört, was ins Home, und was dazwischen

Drei Wege führen Dinge in einen Arbeitsplatz, und sie zu verwechseln kostet Zeit oder Geduld:

| Was | Wohin | Warum dorthin |
|---|---|---|
| Software | Golden Image (§8) | Einmal bauen statt bei jedem Start installieren |
| Dateien für alle | Gemeinsame Ablage | Austauschbar, ohne Image-Bau |
| Einrichtung je Nutzer | Startskript | Läuft in dessen Rechten, in dessen Home |
| Eigene Einstellungen | gar nichts davon | Das persistente Home hält sie ohnehin |

Der letzte Punkt ist der, der am ehesten übersehen wird — auch von uns: **Das persistente Home
liegt über dem Image.** Extensions, Editorkonfiguration, Schlüssel und Projekte liegen unter
`/srv/ota/profiles/<nutzer>/` auf dem Host und werden bei jedem Start eingehängt. Ein neues Golden
Image ändert daran nichts. Nachgeprüft am 2026-08-27: 3,5 MB VS-Code-Extensions im Profil, über
mehrere Image-Fassungen hinweg unverändert.

**Die gemeinsame Ablage** hängt in jedem Container unter `/mnt/ota` — **schreibgeschützt am
Einhängepunkt**, nicht durch eine Prüfung, die sich umgehen liesse. Dazu ein Verweis `~/Gemeinsam`
im Home, damit sie auffindbar ist; der Einhängepunkt selbst liegt bewusst ausserhalb des Home, weil
ein unbeschreibbares Verzeichnis mitten in den eigenen Dateien mehr verwirrt als hilft.

Geschrieben wird ausschliesslich über die Oberfläche, und ausgeführt wird das im **Agent**
(`agent/otaagent/shared.py`) — die API fasst das Dateisystem des Hosts nicht an, sie entscheidet
nur, wer was darf. Dieselbe Aufteilung wie bei Containern und Images.

Die kritische Stelle dieser Datei ist `_resolve()`: Jeder Pfad kommt aus dem Browser. Aufgelöst wird
**zuerst**, geprüft **danach** — ein `..` fällt so genauso auf wie ein Symlink, der aus der Ablage
herauszeigt. Vorher zu prüfen genügt nicht.

**Das Startskript** läuft bei jedem Sessionstart als der Nutzer, nicht als root. Ein Skript, das mit
root-Rechten in ein Nutzerverzeichnis schreibt, hinterlässt Dateien, die der Nutzer nicht mehr
ändern kann — ein Fehler, der erst Wochen später auffällt. Scheitert es, startet der Arbeitsplatz
trotzdem: Ihn wegen einer misslungenen Einrichtung ganz zu verweigern wäre die schlechtere Antwort.

### 9.12 Die Displaynummer gehört zum Zustand, nicht zum Katalog

Ein Fehler, der erst mit einem gewachsenen App-Katalog auftrat.

Die Nummer des Displays wurde aus der **Position im Katalog** abgeleitet (`index + 2`). Damit galt
die Grenze von sechs gleichzeitigen Anwendungen in Wirklichkeit für die **Grösse des Katalogs**:
Bei zehn eingetragenen Anwendungen liessen sich die letzten vier nie starten — mit der Meldung
„höchstens 6 gleichzeitig", obwohl keine einzige lief. Alphabetisch traf es ausgerechnet VS Code
und VSCodium.

Vergeben wird jetzt das erste freie Display aus 2–7, gemessen an den *laufenden* Streams. Die
Traefik-Routen dafür legt der Containerstart ohnehin auf Vorrat an; welche Anwendung auf welcher
Nummer liegt, darf sich von Start zu Start unterscheiden — die Adresse kommt aus der API.

**Die Lehre dahinter:** Eine Nummer, die eine Laufzeitressource bezeichnet, darf nicht aus einer
Konfigurationsliste abgeleitet werden. Sonst begrenzt die Konfiguration die Laufzeit.

## 10. Zwischenablage und Datenaustausch

Kopieren und Einfügen ist die Funktion, an der eine Remote-Desktop-Plattform im Alltag scheitert oder
überzeugt. Sie bekommt deshalb einen eigenen Abschnitt und eigene Abnahmekriterien. Die Angaben unten
sind an KasmVNC 1.4.1 im vorhandenen Image geprüft, nicht angenommen.

### 10.1 Was die Engine kann (verifiziert)

`Xvnc` bringt die nötigen Schalter mit:

| Parameter | Bedeutung | Standard |
|---|---|---|
| `SendCutText` | Änderungen vom Container zum Browser | `1` (an) |
| `AcceptCutText` | Änderungen vom Browser zum Container | `1` (an) |
| `SendPrimary` / `SetPrimary` | zusätzlich die PRIMARY-Auswahl (Mittelklick) | im Desktop-Profil aktiv |
| `DLP_ClipTypes` | erlaubte Binär-MIME-Typen | s. u. |
| `DLP_ClipSendMax` / `DLP_ClipAcceptMax` | Größenlimits je Richtung | unbegrenzt |
| `DLP_ClipDelay` | Mindestabstand zwischen Aktionen | im Image auf `0` gesetzt |

Und `kasmvnc_defaults.yaml` zeigt die tatsächliche Voreinstellung:

```yaml
clipboard:
  delay_between_operations: none
  allow_mimetypes: [ chromium/x-web-custom-data, text/html, image/png ]
  server_to_client: { enabled: true, size: unlimited, primary_clipboard_enabled: false }
  client_to_server: { enabled: true, size: unlimited }
```

**Beide Richtungen sind ab Werk an, ohne Größenlimit, und `image/png` ist erlaubt** — Bilder
funktionieren also ebenfalls, nicht nur Text. Die PRIMARY-Auswahl (Markieren und Mittelklick) ist
dagegen **aus**; das ist ein bewusst zu setzender Schalter, kein Fehler.

Im Image vorhanden: `xclip`, `wmctrl`. Es fehlen `xsel`, `xdotool` und `autocutsel` — die brauchen wir
für die Brücke in §10.4 und nehmen sie ins eigene Basisimage auf.

### 10.2 Die Browser-Seite — hier liegen die echten Stolpersteine

Die Engine ist nicht das Problem. Vier Dinge auf der Browser-Seite entscheiden, ob es funktioniert:

1. **HTTPS ist Pflicht, nicht Empfehlung.** `navigator.clipboard` existiert nur im Secure Context.
   Über `http://` gibt es keine nahtlose Zwischenablage — das ist der Grund, warum TLS in §12 als
   Pflicht steht und nicht als Härtungsmaßnahme.
2. **Das iframe braucht die Berechtigung ausdrücklich.** Der Session-Viewer bettet den Stream in ein
   `<iframe>` ein. Ohne
   ```html
   <iframe allow="clipboard-read; clipboard-write" …>
   ```
   blockiert die Permissions-Policy den Zugriff — und zwar **stillschweigend**. Das ist der häufigste
   Grund, warum Copy-Paste in selbstgebauten Portalen nicht geht, obwohl die Engine korrekt läuft.
3. **Firefox liest die Zwischenablage nicht auf Zuruf.** `navigator.clipboard.readText()` steht dort
   normalen Webseiten nicht zur Verfügung. Einfügen muss deshalb über das **`paste`-Ereignis** laufen:
   Der Nutzer drückt Strg+V, der Browser feuert `paste`, die Seite liest `e.clipboardData`. Dieser Pfad
   funktioniert in allen Browsern und muss der Standardweg sein — `readText()` nur als Zusatz, wo
   verfügbar. Chrome verlangt zudem eine Nutzerfreigabe für `clipboard-read`.
4. **Das iframe muss den Fokus haben**, sonst erreichen Tastenereignisse den Stream nie. Der Viewer
   setzt den Fokus beim Verbinden und nach jedem Schließen der Kontrollleiste zurück.
5. **Firefox gibt den Lesezugriff überhaupt nicht her — dafür gibt es eine Erweiterung.**
   Das ist keine Einstellung, sondern eine Festlegung des Browsers, und der Weg über das
   `paste`-Ereignis bleibt der Rückfall. Für ein Arbeitsgefühl wie auf dem Desktop reicht er nicht:
   Er verlangt bei jedem Einfügen ein Strg+V im richtigen Fenster.

   `extension/firefox/` schliesst genau diese Lücke und sonst nichts. Zwei Entscheidungen darin
   sind bewusst:

   - **Keine Seitenberechtigung bei der Installation.** Die Erweiterung darf zunächst nirgends
     mitlesen; erst ein Klick auf ihr Symbol gibt sie für die gerade offene Adresse frei
     (`optional_host_permissions` plus `scripting.registerContentScripts`). Eine Erweiterung, die
     sich beim Installieren Zugriff auf jede Seite nimmt, wäre für diese Aufgabe völlig überzogen.
   - **Die Seite fragt, die Erweiterung antwortet.** Das Protokoll über `window.postMessage` ist
     einseitig; die Erweiterung ruft von sich aus nie etwas auf und schickt nichts weiter.

   OTA erkennt Firefox, prüft per Handschlag, ob die Erweiterung da ist, und bietet sie sonst in der
   Kontrollleiste zum Herunterladen an. Fehlt sie, verhält sich alles wie zuvor.

   **Offen bleibt die dauerhafte Installation.** Firefox nimmt unsignierte Erweiterungen nur
   temporär an. Die beiden Wege — Unternehmensrichtlinie oder Signatur durch Mozilla — liegen
   ausserhalb von OTA und stehen im Handbuch Kapitel 4.

6. **Der KasmVNC-Client schaltet die Zwischenablage im iframe von sich aus ab.** Das ist der
   Stolperstein, der uns tatsächlich Zeit gekostet hat, und er steht in keiner Dokumentation.
   In `ui.js` entscheidet der Client anhand von `window.self !== window.top`:

   ```js
   window.self !== window.top && !readSetting("show_control_bar")
       ? (initSetting("clipboard_up",   false),
          initSetting("clipboard_down", false),
          initSetting("clipboard_seamless", false))
       : (initSetting("clipboard_up",   true), …)
   ```

   `clipboardReceive()` prüft anschliessend `rfb.clipboardDown` und **verwirft** alles, was der
   Server schickt. Nach aussen sieht das aus wie ein kaputter Server: kein Fehler, keine Meldung in
   der Konsole, das Feld bleibt leer. Gemessen am 2026-08-27 mit demselben Container einmal als
   eigene Seite und einmal im Viewer — als eigene Seite kam der Text an, im iframe nie.

   OTA hängt deshalb `clipboard_up=1&clipboard_down=1&clipboard_seamless=0` an die Stream-Adresse
   (`STREAM_ARGS` in `api/ota/routers/sessions.py`). **Derselbe iframe-Zweig setzt auch `resize` auf
   `off`** — der ferne Bildschirm blieb dadurch auf Startgrösse und sass mit schwarzem Rand mitten
   im Fenster. `resize=remote` gehört deshalb in dieselbe Liste; damit wächst der Arbeitsbereich mit
   dem Browserfenster, wie man es von einer Desktopanwendung erwartet. `initSetting()` liest zuerst die Adresse und
   erst danach den gespeicherten Vorgabewert, also gewinnt der Parameter. `clipboard_seamless`
   bleibt bewusst **aus**: Den Abgleich mit der System-Zwischenablage macht die Brücke im
   Elternfenster, das dafür auch die Berechtigung besitzt.

**Eine Sackgasse, die hier festgehalten sei**, damit sie niemand noch einmal geht: Der Verdacht fiel
zuerst auf die Cross-Origin-Isolation, weil `crossOriginIsolated` im iframe `false` war und oben
`true`. COOP und COEP wurden ergänzt, die Isolation stimmte danach in beiden Fällen — am Ergebnis
änderte sich nichts. `Cross-Origin-Embedder-Policy: require-corp` ist deshalb wieder draussen: Der
Client dekodiert über `ImageDecoder`, nicht über `SharedArrayBuffer`, hat also von der Isolation
nichts — der Header hätte nur den Preis, dass jede fremde Ressource ohne CORP kommentarlos
ausfällt, und genau solche kommen mit den Kasm-Registries noch dazu. `Cross-Origin-Opener-Policy`
ist geblieben; die kostet nichts.

Ergänzend bleibt das **Zwischenablage-Panel** in der Kontrollleiste erhalten: ein Textfeld in beide
Richtungen. Es ist der Rückfall, wenn ein Browser die API verweigert, und der einzige Weg für Nutzer,
die den nahtlosen Modus abgeschaltet haben.

### 10.3 Die X11-Seite im Container

- X kennt **zwei Auswahlen**: `CLIPBOARD` (Strg+C/V) und `PRIMARY` (markieren, Mittelklick). Beide
  werden gebrückt, PRIMARY ist per Schalter zuschaltbar.
- **JetBrains-IDEs sind der Sonderfall.** Javas AWT-Zwischenablage über X11 gilt seit Jahren als
  anfällig — Besitzwechsel der Selection werden nicht immer bemerkt. Das ist der Grund, warum
  IntelliJ in der Abnahme (§10.5) eine **eigene Zeile** bekommt und nicht unter „Editoren" mitläuft.
- Electron-Anwendungen (VS Code, VSCodium, Cursor) sind unauffällig.

### 10.4 Modus B: das Problem, das die Multi-App-Idee mitbringt

**Jedes X-Display hat seine eigene Zwischenablage.** In Modus B läuft VS Code auf `:1` und IntelliJ auf
`:2`. Ohne Gegenmaßnahme heißt das: Kopieren in VS Code, Einfügen in IntelliJ — **funktioniert nicht**,
obwohl beide im selben Container laufen. Genau das würde niemand erwarten, und es wäre der erste
Fehlerbericht nach dem Rollout.

Das ist kein Grund gegen Modus B, aber es ist Arbeit, die eingeplant gehört:

**Zwischenablage-Brücke** — ein kleiner Dienst im Container, der `CLIPBOARD` über alle aktiven Displays
spiegelt:
- lauscht per XFIXES auf Besitzwechsel der Selection je Display (`clipnotify`-Muster), nicht per Polling
- schreibt Änderungen mit `xclip -d :N` auf alle übrigen Displays
- **Schleifenschutz**: jede Übernahme merkt sich Hash und Ursprungsdisplay, damit A→B→A nicht endlos kreist
- respektiert die Rechte-Einstellungen des Templates; ist die Zwischenablage abgeschaltet, läuft die
  Brücke nicht
- startet und stoppt mit den Displays

**Umsetzungsstand (2026-08-27): gebaut und geprüft.** `agent/otaagent/clipboard.py` schreibt die
Brücke in den Container und startet sie automatisch, sobald die zweite Anwendung geöffnet wird.
Geprüft durch `scripts/test-clipboard-bridge.sh` — beide Richtungen, Umlaute, mehrzeiliger Code
mit Tabulatoren.

**Nachtrag 2026-09-01: die Brücke ist ereignisgesteuert** — dort, wo das Image es hergibt. Sie
startet je Display ein `clipnotify -l`, das bei jeder Änderung eine Zeile schreibt, und wartet
darauf, statt im halben Sekundentakt nachzufragen. Entschieden wird das **im Container**: Fehlt
`clipnotify` (so in allen Kasm-Images), bleibt es beim Takt. Beide Wege teilen sich denselben
Abgleich darunter; was sich unterscheidet, ist ausschliesslich das Warten.

Der Gewinn ist nicht die Last — acht Aufrufe je Sekunde tun keinem weh —, sondern die
Verzögerung: Im Takt liegt zwischen Kopieren und Einfügen bis zu eine halbe Sekunde, in der die
Nachbaranwendung noch den alten Inhalt hat. Wer schnell genug ist, fügt das Vorherige ein, und
das sieht aus wie ein Fehler, den niemand reproduzieren kann. Über Ereignisse sind es
Millisekunden.

**Zwei Fallen beim Bauen**, beide derselbe Fehler in zwei Gewändern: Ein Abgleich über
`pgrep -f <muster>` findet das **eigene Skript**, weil dessen Kommandozeile das Muster enthält —
das Skript hält sich dann selbst für die laufende Anwendung, oder `pkill` bringt die eigene Shell
um. Beides passiert wortlos. Deshalb prüft OTA App-Starts über die Fensterliste des Displays und
steuert die Brücke ausschliesslich über eine PID-Datei.

**Ehrlicher Nachtrag zur Engine-Wahl aus §9.2**: Xpra hätte dieses Problem nicht — ein Server, eine
Zwischenablage, keine Brücke. Das ist ein echtes Argument dafür, das ich in §9.2 unterschlagen hatte.
Es dreht die Empfehlung nicht um, weil eine getestete Brücke billiger ist als eine zweite Engine mit
eigenem Client, eigenem Audiopfad und eigener Kontrollleiste. Aber die Rechnung ist knapper, als sie
dort aussah, und wenn sich die Brücke in der Praxis als zickig erweist, ist Xpra der vorgesehene Ausweg.

### 10.5 Abnahme — ohne diese Matrix gilt die Zwischenablage nicht als fertig

„Copy-Paste geht" ist keine prüfbare Aussage. Jede Zeile wird in **Chrome und Firefox** durchgegangen:

| # | Fall | Erwartung |
|---|---|---|
| 1 | Text Browser → Session, per Strg+V | kommt an |
| 2 | Text Session → Browser, per Strg+C | kommt an |
| 3 | Text zwischen **zwei Sessions** desselben Nutzers | kommt an |
| 4 | Mehrzeiliger Code mit Tabs und Umlauten | Formatierung und Zeichen bleiben erhalten |
| 5 | Sehr großer Inhalt (~1 MB Text) | kommt an oder scheitert **mit Meldung**, nie stumm |
| 6 | Bild (`image/png`) in beide Richtungen | kommt an |
| 7 | **IntelliJ** (Java/AWT) in beide Richtungen | kommt an — eigene Zeile, weil Java der Sonderfall ist |
| 8 | **Modus B**: VS Code `:1` → IntelliJ `:2` | kommt an, über die Brücke aus §10.4 |
| 9 | PRIMARY: markieren, Mittelklick einfügen | funktioniert, wenn der Schalter an ist |
| 10 | Zwischenablage im Template **abgeschaltet** | beide Richtungen bleiben wirkungslos, das Panel sagt warum |
| 11 | Nach Reconnect und nach Pause/Fortsetzen | funktioniert weiterhin |
| 12 | Firefox ohne `readText()` | Einfügen läuft über das `paste`-Ereignis, Nutzer merkt keinen Unterschied |

Fall 8 und 12 sind die, die erfahrungsgemäß durchrutschen.

**Stand 2026-09-01:** Alle zwölf Fälle laufen automatisiert mit — elf bei jedem Lauf, einer
(Java/AWT) auf Zuruf.

| Fall | Wo | Stand |
|---|---|---|
| 1, 2, 4 | `tests/e2e.mjs`, gegen den Viewer im iframe | ✅ |
| 5 (1 MB) | `test-clipboard-bridge.sh` | ✅ vollständig, nicht abgeschnitten. `DLP_ClipSendMax` und `DLP_ClipAcceptMax` stehen auf 0, also ohne Grenze |
| 6 (Bild) | `test-clipboard-bridge.sh` | ✅ — die Brücke trägt seit dem 2026-08-28 auch `image/png` |
| 8 (Modus B) | `test-clipboard-bridge.sh` | ✅ |
| 9 (PRIMARY) | `test-clipboard-bridge.sh` | ✅ auf demselben Display; **nicht** über Displays hinweg, und das mit Absicht |
| 10 (abgeschaltet) | `test-clipboard-bridge.sh` | ✅ Brücke läuft nicht, und kommt beim Wiedereinschalten zurück |
| 11 (nach Pause) | `test-clipboard-bridge.sh` | ✅ |
| 3 (zwei Sessions) | `tests/e2e.mjs` | ✅ mit zwei echten Containern: kopieren in Session A, über die System-Zwischenablage des Browsers, ankommen in Session B. Der Test legt sich dafür eine eigene Vorlage mit **eigenem Profil** an — zwei Vorlagen mit `persistence_scope: user` teilen sich ein Zuhause, und OTA lehnt die zweite Session zu Recht ab |
| 7 (Java/AWT) | `scripts/build-base-image.sh` mit `OTA_PRUEFE_JAVA=1` | ✅ beide Richtungen, mit einem laufenden AWT-Prozess. Nicht bei jedem Lauf: Der Test installiert ein JDK in den Prüfcontainer (~300 MB). Ins **Image** gehört das nicht — ein Basisimage, von dem jeder Arbeitsplatz abstammt, trägt kein JDK mit sich herum, nur damit ein Test es vorfindet |
| 12 (ohne `readText()`) | `tests/e2e.mjs` | ✅ in Chromium **mit abgeschaltetem `readText`**. Das ist kein Ersatz für einen Lauf in Firefox und soll keiner sein: Es prüft genau den Pfad, der dort greift, und zwar bei jedem Lauf. Ohne das fiele ein Bruch erst jemandem in Firefox auf |

**Zu Fall 6.** Ein Bild kommt nicht als Text aus der Zwischenablage. Wer nur `xclip -o` fragt,
bekommt nichts und hält sie für leer — ein Screenshot wäre in der Nachbaranwendung unerreichbar,
ohne dass irgendwo etwas dazu stünde. Die Brücke prüft deshalb erst die angebotenen `TARGETS` und
liest dann mit dem passenden Typ. Der Typ geht in die Prüfsumme ein; sonst gälte ein Bild, das
zufällig dieselben Bytes hat wie der letzte Text, als schon bekannt.

**Zu Fall 9.** PRIMARY wird bewusst **nicht** über Displays gespiegelt. Das ist die flüchtige
Markierung, nicht die Zwischenablage: Wer in einer Anwendung Text markiert, würde sonst die
Markierung in jeder anderen überschreiben. Der Test prüft beides — dass PRIMARY auf demselben
Display funktioniert, und dass es die Displaygrenze nicht überschreitet.

**Was noch offen ist.** Fall 3 (zwischen zwei Sessions) braucht zwei Container gleichzeitig im
Browser; Fall 7 (IntelliJ, Java/AWT) braucht einen Start, der Minuten dauert; Fall 12 (Firefox ohne
`readText()`) braucht einen echten Firefox, und der Testbrowser ist Chromium.

## 11. Persistenz und Storage

### 11.1 Layout
```
/srv/ota/
  profiles/<username>/<scope>/     # Nutzer-Home, gemountet nach /home/kasm-user
  skeletons/<template-slug>/v<N>/  # Golden-Skeleton je Version
  shared/<group-slug>/             # gemeinsame Gruppenlaufwerke (ro/rw)
  backups/profiles/<username>/     # rotierende Tarballs
  builds/<build-id>/               # Build-Kontext, Logs
```

`scope` ist konfigurierbar:
- `user` — **ein** Home für alle Templates (Kasm-kompatibles Verhalten, aktuelle Einstellung von `bmetallica`)
- `template` — getrenntes Home je Workspace-Typ (verhindert, dass GIMP-Configs den VS-Code-Desktop stören)

### 11.2 Sicherung und Wiederherstellung

**Umsetzungsstand (2026-08-27): gebaut und geprüft.** Endpunkte unter `/api/backups`,
Oberfläche unter *Betrieb → Sicherung*, Tests in `scripts/test-backup.sh`.

#### Ein Wurzelverzeichnis, damit NFS später nichts kostet

Alles landet unter **einem** Pfad, `OTA_BACKUP_ROOT` (Vorgabe `/srv/ota/backups`):

```
/srv/ota/backups/
  profiles/<nutzer>/<zeitstempel>.tar.zst
  containers/<nutzer>/<vorlage>-<zeitstempel>.tar.zst
```

Das ist der ganze Trick: Wer später ein NFS unter diesen Pfad hängt, ändert an OTA
**nichts** — die Anwendung sieht weiterhin nur ein Verzeichnis. Die Oberfläche zeigt
an, ob dort bereits ein Netzlaufwerk liegt (`nfs`, `cifs`) oder noch die lokale Platte,
damit man es nicht raten muss.

#### Was gesichert wird, und warum nicht mehr

Am laufenden System gemessen: Das Profil eines Nutzers ist **326 MB**, die Schreibschicht
seines Containers **340 MB**, ein vollständiger Container-Export wäre **4,8 GB**. Von den
326 MB Profil sind 306 MB ein heruntergeladener SDK-Cache, den niemand sichern will.

| Art | Inhalt | Grösse im Test |
|---|---|---|
| **`profile`** | Das Home ohne Caches. Projekte, Einstellungen, Schlüssel — die eigentliche Arbeit | 327 KB aus 326 MB Rohdaten |
| `container` | Nur was `docker diff` ausserhalb des Home meldet | **4 KB** im Test |
| `database` | Nutzer, Gruppen, Vorlagen, Zuweisungen, Audit | 17 KB |

Ein voller Container-Export bestünde fast nur aus dem Basisimage, das aus dem Golden
Image ohnehin reproduzierbar ist. Ihn zu sichern hiesse, dieselben Gigabyte pro Nutzer
und pro Lauf erneut abzulegen. Deshalb nur die Differenz — und auch die nur auf
ausdrücklichen Wunsch.

**Eine Falle bei der Differenz, die im Test 269 MB kostete:** `docker diff` meldet nicht
nur die geänderte Datei, sondern **jedes Verzeichnis darüber** als geändert. Wer die
ungefiltert einsammelt, zieht ganze Bäume mit — für eine einzige geänderte Logdatei kamen
so 269 MB unveränderter Binärdateien aus `/dockerstartup` mit. OTA sortiert deshalb alle
Pfade aus, die Präfix eines anderen gemeldeten Pfades sind. Danach: 4 KB statt 269 MB.

Der zweite Stolperstein: `get_archive("/etc/datei")` liefert die Einträge relativ zum
**Elternverzeichnis**. Wer den Pfad selbst als Präfix nimmt, erzeugt `etc/etc/datei`.

Ausgeschlossen sind Browser- und Editor-Caches, `node_modules`, `__pycache__`, Sockets
und Sperrdateien. Im Test schrumpfte das Archiv dadurch von 6.754 auf 355 Einträge, ohne
dass eine einzige Nutzerdatei fehlte.

#### Die Datenbank läuft über die Kommandozeile, nicht über einen Knopf

`pg_dump` läuft über `docker exec` **im Datenbank-Container**. Damit braucht der Agent
weder einen Postgres-Client noch die Zugangsdaten — beides wäre zusätzliche
Angriffsfläche für einen Dienst, der ohnehin den Docker-Socket hält. Der Dump entsteht
mit `--clean --if-exists`, lässt sich also über eine bestehende Datenbank legen.

Die **Wiederherstellung** ist bewusst kein Knopf in der Oberfläche: Die Datenbank trägt
die Anmeldung, mit der man gerade in dieser Oberfläche steht. Sie unter der laufenden
Anwendung auszutauschen bricht jede offene Verbindung mittendrin. `scripts/restore-db.sh`
macht es richtig — Sicherheitskopie anlegen, API und Agent anhalten, offene Verbindungen
beenden, einspielen, Dienste starten, Gesundheit prüfen. Schlägt das Einspielen fehl,
nennt es den Weg zurück. Die Oberfläche zeigt den fertigen Befehl an.

**Ein Nebeneffekt, der dokumentiert gehört:** Nach einer Wiederherstellung kann ein
Session-Container laufen, den die zurückgespielte Datenbank nicht kennt. Der
Waisen-Aufräumer (§7) entfernt ihn beim nächsten Durchlauf — das ist gewollt, sollte
aber niemanden überraschen.

#### Wiederherstellung — zwei Regeln, beide nicht verhandelbar

1. **Nicht bei laufender Session.** Ein Profil unter einem geöffneten Editor
   auszutauschen führt auf beiden Seiten zu Datenverlust. Die API lehnt ab und nennt
   die Zahl der offenen Sessions.
2. **Der bisherige Stand wird nicht gelöscht, sondern beiseitegelegt** als
   `user.vor-wiederherstellung-<zeitstempel>`. Eine Wiederherstellung, die im Fehlerfall
   nichts übriglässt, ist keine. Schlägt das Entpacken fehl, wird der alte Stand
   automatisch zurückgeschoben.

Nach dem Entpacken wird die Eigentümerschaft auf **UID/GID 1000** gesetzt — sonst kann
der Container nicht in sein eigenes Home schreiben.

#### Zeitplan und Aufbewahrung

Ein Lauf je Tag zur eingestellten Uhrzeit, wahlweise nur an bestimmten Wochentagen. Der
Zeitplaner prüft minütlich und **holt einen Lauf nach**, wenn der Dienst zur geplanten
Minute gerade neu gestartet wurde.

Aufbewahrt werden die letzten *n* täglichen Stände je Nutzer und Art, dazu aus den
älteren je Kalenderwoche der neueste — bis zur eingestellten Zahl. Fehlgeschlagene Läufe
verschwinden nach 30 Tagen; sie belegen nichts, verstellen aber die Sicht.

#### Container-Sicherungen gehen den umgekehrten Weg

Beim Profil gilt: **keine Wiederherstellung bei laufender Session**. Bei Container-
Sicherungen ist es genau andersherum — die Dateien werden in den **laufenden** Container
gelegt (`put_archive`). Läuft keiner, lehnt die API ab und sagt, dass der Arbeitsplatz
zuerst zu starten ist.

Weil die zurückgespielten Dateien ausserhalb des Home liegen, lesen bereits geöffnete
Anwendungen sie nicht mehr. Die Rückmeldung sagt das ausdrücklich.

#### Geprüft

`scripts/test-backup.sh` deckt alle drei Arten ab — 31 Prüfungen, darunter:

- Ein normaler Nutzer sieht die Sicherungen nicht und kann keine auslösen (403)
- Profil: Markierung anlegen, sichern, wiederherstellen, Markierung ist weg und liegt
  im beiseitegelegten Stand
- Container: Markierung ausserhalb des Home, Archiv bleibt unter 5 MB, keine
  verdoppelten Pfade, Markierung ist nach dem Zurückspielen wieder da
- Datenbank: gültiger `pg_dump` mit `--clean`, Nutzertabelle enthalten, die
  Wiederherstellung verweist auf das Skript statt sie zu versuchen
- Wiederherstellung bei laufender Session wird abgelehnt

Die **Datenbank-Wiederherstellung selbst wurde am 2026-08-27 einmal vollständig
durchgespielt**: Markierungsnutzer angelegt, zurückgespielt, Nutzer verschwunden,
Anmeldung und alle übrigen Daten unversehrt.

### 11.3 Regeln
- Eigentümerschaft **UID/GID 1000** (Kasm-Images laufen als User 1000) — der Agent korrigiert das beim Anlegen
- Quota pro Nutzer (Default 20 GB), Warnung ab 80 %, Sperre neuer Sessions bei 100 % mit klarer Meldung
- Nächtliches Backup: `tar --zstd` der Profile, 7 tägliche + 4 wöchentliche Stände, `.cache`, `core.*`, `*.sock`, Browser-Caches ausgeschlossen
- Beim Offboarding: Profil archivieren, dann löschen (DSGVO)

---

## 12. Netzwerk, Routing, TLS

- **TLS ist Pflicht**, nicht optional: Die Clipboard-API des Browsers (`navigator.clipboard`) funktioniert nur in Secure Contexts. Ohne HTTPS kein nahtloses Copy/Paste.
- Parallelbetrieb mit Kasm: OTA auf **8443**, danach Umzug auf 443
- Zertifikate: Für den internen Betrieb eine eigene CA oder Let's-Encrypt-DNS-01 (die Domain `home-bmetallica.de` ist offenbar vorhanden). Self-signed erzeugt bei jedem Nutzer Browserwarnungen — beim Rollout vermeiden.
- Netzsegmentierung:
  - `ota_public` — Traefik ↔ web/api
  - `ota_internal` — api ↔ db ↔ agent (kein Internet)
  - `ota_sessions` — nur Session-Container; **kein** Zugriff auf `ota-db`
  - Pro Template optional `internet: yes/no` und Egress-Whitelist
- Security-Header zentral in Traefik: HSTS, `X-Frame-Options` für die App, aber **`frame-ancestors 'self'`** für die Session-Routen (der Viewer nutzt ein iframe), `Referrer-Policy`, CSP

---

## 13. UI/UX-Konzept

> Umgesetzt in `web/`. Screenshots und lauffähiger Entwurf: `npm run dev` in `web/`.

### 13.0 Leitidee: eine Bedienoberfläche, kein Formular
Die Anforderung „Regler, Auswahlen und Schalter statt Textfelder" ist nicht nur eine Widget-Wahl, sondern
bestimmt, was das Produkt sein will: **ein Gerät, das Sessions betreibt.** Daraus folgt alles Weitere.

Die zentrale Regel des Systems: **Farbe ist Information, nie Dekoration.** Das gesamte Chrome — Flächen,
Rahmen, Text, sogar die Primäraktion — bleibt neutral. Gesättigte Farbe tritt ausschliesslich als *Zustand*
auf. Dadurch sind die Status-LEDs die einzigen farbigen Pixel im Layout und ohne Suchen lesbar.

Diese Regel wird konsequent durchgehalten, auch wo es unbequem ist: Ein aktivierter Schalter im
Rechte-Reiter ist **hell und unbunt**, nicht Grün — denn „Einstellung aktiv" ist kein
Laufzeitzustand. Grün bedeutet im ganzen Produkt genau eine Sache: *läuft gerade*.

### 13.0b Ein Tab je Anwendung, und eine Adresse für jede

Die Ansicht einer Session ersetzte anfangs das Dashboard. Beim ersten echten Benutzen fiel auf, dass
das dem Modell aus §9 widerspricht: Ein Arbeitsplatz hat mehrere Anwendungen offen, und „zurück zum
Dashboard" hiess, die laufende zu verlassen.

Seither hat jede Ansicht eine eigene Adresse, und Anwendungen öffnen in einem eigenen Tab:

| Adresse | Bedeutung |
|---|---|
| `/view/s/<session>[/<display>]` | Zeigt eine **bestimmte laufende** Session. Entsteht beim Öffnen aus dem Dashboard |
| `/launch/<vorlage>[/<app>]` | Sorgt dafür, dass etwas läuft, und zeigt es dann. Startet notfalls den Container |

Der Unterschied ist wichtig: Eine Verknüpfung auf dem Desktop wird angeklickt, wenn gerade *nichts*
läuft. Sie kann keine Session-Nummer enthalten — sie muss sagen, *was* jemand will, nicht *welche
Instanz*. Genau das ist `/launch/`, und genau das ist die Startadresse im PWA-Manifest.

Wer nicht angemeldet ist, landet auf der Anmeldung und danach in seiner Anwendung. Die Adresse
bleibt dabei stehen; es wird nichts umgeleitet und nichts zwischengespeichert.

### 13.0c Zweisprachig, mit dem deutschen Satz als Schlüssel

Die Oberfläche gibt es auf Deutsch und Englisch. Der Umschalter steht in der Leiste und — wichtig —
auch auf der Anmeldemaske: Wer kein Deutsch liest, soll nicht vor einer deutschen Anmeldung stehen.

Übersetzt wird über den **deutschen Satz als Schlüssel**, nicht über erfundene Bezeichner wie
`nav.help`. Drei Gründe:

- Im Quelltext steht weiterhin der Satz, den der Nutzer sieht. Wer den Code liest, muss nicht in
  einer zweiten Datei nachschlagen.
- Es gibt **ein** Wörterbuch statt zwei. Ein Bezeichner-Ansatz bräuchte auch für Deutsch eine
  vollständige Tabelle, die mit dem Quelltext auseinanderlaufen kann.
- Der Rückfall ist brauchbar: Fehlt eine Übersetzung, erscheint der deutsche Satz — nicht `nav.help`
  und keine leere Fläche.

Dieselbe Tabelle übersetzt auch die Meldungen des Servers (`call()` in `web/src/lib/api.ts`). Ein
Fehler soll nicht auf Deutsch dastehen, während der Rest der Seite Englisch spricht.

Das Handbuch selbst bleibt deutsch. Im englischen Modus sagt die Hilfe das offen, statt es zu
verschweigen.

### 13.0d Das Handbuch im Programm

`docs/wiki/` wird über die API ausgeliefert (`/api/help`), nicht als statische Dateien: Welche
Kapitel jemand sieht, ist eine Rechtefrage. Anwender bekommen Überblick, Arbeitsplatz und
Zwischenablage; Verwaltung und Betrieb bleiben Administratoren vorbehalten.

Der Markdown-Übersetzer (`web/src/lib/markdown.ts`) ist bewusst selbst geschrieben und keine
Bibliothek. Das Handbuch nutzt eine überschaubare Teilmenge, und jede Bibliothek müsste hier ohnehin
gebändigt werden — rohes HTML hat im Handbuch nichts zu suchen. Es wird zuerst alles maskiert und
danach ausschliesslich eingesetzt, was der Übersetzer selbst erzeugt.

### 13.0e Bearbeiten übernimmt das Hauptfenster

Der Workspace-Editor lag anfangs in einer Seitenleiste von 560 px. Das ging, solange darin ein
Formular stand. Es geht nicht mehr, seit dort App-Listen, Build-Protokolle, ein Rezept-Bauer und
Zuteilungen je Nutzer liegen — Inhalte, die Breite brauchen, um lesbar zu sein.

Deshalb ein Wechsel der Ansicht statt einer Überlagerung: Aus *Workspaces* wird
*Workspaces / Arbeitsplatz*, mit Reitern darunter. Der Weg zurück ist der erste Teil des Pfades,
kein Kreuz in der Ecke — man ist nicht in einem Dialog, sondern eine Ebene tiefer. Gemessen: 1116 px
statt 560 px Arbeitsfläche.

Die Seitenleiste bleibt, wo sie hingehört: für kurze Formulare, die man neben dem Bestand ausfüllt
(Nutzer, Gruppen). **Die Regel dahinter:** Ein Dialog unterbricht, eine Ebene führt weiter. Was man
in zehn Sekunden ausfüllt, unterbricht; woran man zehn Minuten arbeitet, führt weiter.

Formularfelder werden darin auf 720 px begrenzt. Eine Eingabezeile über die volle Breite ist nicht
komfortabler, sondern schlechter zu lesen; Listen und Tabellen dürfen die Breite dagegen nutzen.

### 13.1 Token

Abgeleitet aus Logo und Symbol (`icon.svg`, `Logo-Banner.svg`). Vorher war die Grundfläche ein
tiefes Teal-Ink mit warmem Bone als Primäraktion; die Marke arbeitet mit einer Slate-Leiter und
einem Cyan-Akzent. **Die Grundfläche ist das größte Stück Farbe im Bild** — sie anzugleichen bringt
mehr Wiedererkennung als jeder Akzent, deshalb beginnt der Wechsel dort.

```
Flächen    --ground   #090D16   App-Grund — der Grund des Logo-Banners
           --bay      #0F172A   Karten und Panels — die Fläche des Symbols
           --bay-2    #1B2436   angehoben: Drawer, Popover, Hover
           --well     #060A12   eingelassen: Eingaben, Fader-Schienen
           --edge     #1E293B   Haarlinie — die Panelfarbe im Logo
           --edge-lit #334155   Hover — die Strichfarbe im Logo

Text       --text     #F1F5F9   --label #94A3B8 (Logo-Unterzeile)   --mute #64748B

Aktion     --key      #E2E8F0   Primäraktion und Kennzahlen; das helle Element
           --key-dim  #CBD5E1   Fader-Füllung

Marke      --accent   #06B6D4   das Cyan aus „Apps" und aus dem Bildschirmrahmen
           --accent-dim #0891B2

Zustand    --live     #10B981   läuft        --paused  #3B82F6   pausiert
           --caution  #F59E0B   nahe Limit   --halt    #EF4444   gestoppt / Fehler
```

**Die Zustandsfarben stehen alle im Logo** — als LEDs in der Fensterleiste und am Rack. Das ist
kein Zufall, sondern der Grund, warum sich die Regel aus §13.0 hier halten lässt: Die Marke
verwendet gesättigte Farbe selbst nur als Statuspunkt.

**Wo der Akzent auftritt, und wo nicht.** Cyan ist die auffälligste Farbe der Marke, und genau
deshalb ist es keine Flächenfarbe. Es erscheint nur dort, wo es *Zugehörigkeit oder Fokus* anzeigt:
Signet in der Leiste, Fokusring, Verweise im Handbuch, das Zeichen des aktiven Menüpunkts, die
gewählte Sprache. Die Primäraktion bleibt bewusst unbunt — wäre der wichtigste Knopf gesättigt,
wäre Farbe wieder Dekoration statt Zustand.

**Ein Ort macht eine Ausnahme:** die Anmeldemaske. Dort steht das farbige Banner in voller Breite.
Es ist der einzige Bildschirm, auf dem sich die Anwendung vorstellt, statt benutzt zu werden.

**Breite der Leiste:** 112 px. Gemessen an der längsten Beschriftung — „Einstellungen" braucht
83 px Text plus Innenabstand. Bei den ursprünglichen 76 px wurde sie abgeschnitten.


**Schrift**: **Archivo** (variabel, Breitenachse) + **IBM Plex Mono**.
Bewusst *nicht* Inter/JetBrains Mono — das ist der Reflex jedes Dev-Dashboards.
Archivos Breitenachse trägt eine eigene Rolle: `wdth 118` + Versalien + `.13em` Sperrung ergibt die
`.silk`-Klasse — Beschriftungen, wie sie auf eine Gerätefront gedruckt werden. Mono ist strikt für
Daten reserviert: Werte, Skalen, Image-Referenzen, IDs. Freitext wie ein Anzeigename steht nie in Mono.

**Technik**: React + TypeScript + Vite, **handgeschriebenes CSS mit Custom Properties statt Tailwind**.
Begründung: Die tragenden Elemente (machinierte Fader-Schiene, Kapazitätszone, Zustandskante) sind
gerätespezifische Zeichnungen, keine Utility-Kompositionen. Flache BEM-artige Klassennamen vermeiden
zudem die Spezifitätskonflikte, die bei gemischten Selektoren entstehen.

### 13.2 Signature: der Kapazitäts-Fader
Das Element, an dem das Produkt erkennbar ist, und die eine bewusste Wette dieses Entwurfs.

Ein Regler mit eingelassener Schiene und **gedruckter Skala, deren Striche exakt auf ihrem Wert sitzen**
(nicht gleichmässig verteilt — eine Skala, die lügt, ist bei einem Instrument unbrauchbar). Auf der
Schiene ist der Bereich schraffiert, **ab dem dieser Host überbucht wäre**: bei CPU ab `host.cores`,
bei RAM ab dem real freien Speicher. Überschreitet der Wert die Grenze, färbt sich die Füllung auf
`--caution` und darunter erscheint der konkrete Satz, was passieren wird.

Der Fader macht die Regler-Anforderung inhaltlich wahr, statt sie nur zu bedienen: Du siehst beim
Schieben, wann die 15 GB dieses Hosts reissen — statt es später im OOM-Kill zu erfahren. Er wird für
CPU, RAM und Zeitlimits verwendet; bei Zeiten rastet er in sprechenden Stufen
(15 min · 30 min · 1 h · 4 h · 8 h · nie) statt eine freie Sekundenzahl zu verlangen.

### 13.3 Bedienelemente statt Eingabefelder

| Statt | Element | Umgesetzt in |
|---|---|---|
| `memory_bytes = 2902458368` | Kapazitäts-Fader mit Host-Grenze | `CapacityFader` |
| `cores = 2` | Fader, 0,5er-Raster, Grenze bei 4 | `CapacityFader` |
| Auflösung als zwei Zahlenfelder | Combobox mit Presets | `Combobox` |
| Idle-Timeout in Sekunden | Fader mit sprechender Rastung | `CapacityFader` |
| Timeout-Aktion | Segmented Control, „Löschen" in `--halt` | `Segmented` |
| Persistenz-Modus | Segmented Control | `Segmented` |
| Neun Rechte-Flags | Schalterliste mit Erklärzeile je Zeile | `Toggle` |
| Image-Referenz als Freitext | Combobox mit Suche über die real vorhandenen Images | `Combobox` |
| Kategorien kommagetrennt | Chips | `ChipSelect` |
| ENV/Volumes als JSON-Blob | Zeilen-Builder | `KeyValueRows` |
| Gruppen-Zuweisung | Zwei-Spalten-Liste mit Delta-Anzeige | in `Workspaces` |
| Ressourcen je Nutzer | aufklappbare Zeile pro Nutzer mit eigenen Fadern | Reiter *Zuteilung* |

Echte Textfelder bleiben genau dort, wo es nichts zu wählen gibt: Anzeigename, Beschreibung,
Setup-Skript, LDAP-DNs.

Zwei Regeln, die aus demselben Gedanken folgen:
- **Vererbung ist sichtbar.** Ein geerbter Wert trägt die Marke „geerbt von Global: 1 h" mit
  Zurücksetzen-Link (`Field`-Komponente). Ohne das weiss niemand, ob ein Wert gesetzt oder geerbt ist.
- **Jede Auswahl erklärt ihre Folge.** Der Hilfetext unter einem Segmented Control ändert sich mit der
  Auswahl und beschreibt, was konkret passiert — nicht, was die Option heisst.

### 13.4 Nutzer-Ansicht
**Die These: das Dashboard ist kein App-Store.** Der Alltag ist nicht „App aussuchen", sondern
„zurück in meine Maschine". Deshalb sind **laufende Sessions der Held der Seite**, nicht der
Kachelkatalog — Kasm dreht das um und kostet damit jeden Tag einen Klick.

- **Session-Bucht**: breite Karte mit Bildschirmfläche, Zustands-LED, Laufzeit, letzter Aktivität,
  CPU und RAM. Die 2px-Kante links trägt den Zustand als Farbe. Bei laufenden Sessions atmet die LED.
- **App-Kacheln** darunter. Eine bereits laufende App wird **nicht ausgegraut**, sondern als belegt
  markiert und verweist nach oben — ausgegraute Elemente wirken kaputt, nicht belegt.
- Gruss richtet sich nach der Uhrzeit; um 00:12 steht dort „Noch wach", nicht „Guten Morgen".
- Leerzustand ist eine Aufforderung mit Zeitangabe, kein leeres Raster.

### 13.5 Admin-Ansicht
- Schmale **Rail** links statt breiter Sidebar; unten die Host-Anzeige mit freiem Speicher.
  Admin-Einträge erscheinen dort nur für die Gruppe `admins`.
- **Kapazitätsmesser** über der Workspace-Liste: frei · zugesagt · Kerne. Übersteigt die Summe der
  zugesagten Speichermengen den freien Host-Speicher, färbt sich der Balken `--halt`. Der Admin sieht
  die Überbuchung, bevor sie zuschlägt.
- **Editor als Drawer** mit den Reitern *Allgemein · Ressourcen · Rechte · Umgebung · Zuweisung* —
  die Liste bleibt daneben sichtbar, der Kontext geht nicht verloren.
- Zuweisungsänderungen zeigen sofort ihr Delta („2 Gruppen kommen hinzu. Betroffene Nutzer sehen den
  Workspace nach dem Speichern.").
- **Reiter *Zuteilung*** führt beides zusammen: oben die Gruppenzuweisung, darunter eine Zeile je
  erreichbarem Nutzer mit den Werten, die für ihn **tatsächlich gelten**. Rechts steht die Herkunft —
  `VORLAGE`, `GRUPPE` oder `NUTZER`, letzteres in `--paused` als Abweichung markiert. Aufklappen zeigt
  die vollen Fader inklusive Host-Grenze; der Zurücksetzen-Link an der Vererbungsmarke entfernt die
  Abweichung wieder. Wer nichts Eigenes hat, erscheint trotzdem in der Liste — sonst müsste man raten,
  wen die Vorlage betrifft.
- Weitere Admin-Seiten folgen dem gleichen Muster (Roadmap M3): Golden Images, Nutzer, Gruppen,
  Sessions, Authentifizierung, Audit-Log.

### 13.6 Sprache
Deutsch als Default, Englisch vollständig gepflegt. Beschriftungen benennen, was der Mensch steuert,
nicht wie das System gebaut ist: „Sitzung endet nach Inaktivität", nicht „idle_timeout".
Eine Aktion behält ihren Namen über den ganzen Ablauf — der Knopf „Änderungen speichern" erzeugt die
Meldung „gespeichert". Fehlermeldungen nennen den Ausweg, nicht nur den Defekt.

### 13.7 Qualitätsboden
Tastaturbedienung mit sichtbarem Fokusring auf allen Elementen; Fader über `input[type=range]`, also
mit Pfeiltasten bedienbar und mit `aria-valuetext` in menschlicher Form („2,7 GB"). Drawer schliesst
mit Escape, Popover mit Escape und Klick daneben. `prefers-reduced-motion` schaltet alle Animationen
ab. Responsiv bis 430 px Breite: Rail schrumpft auf Icons, Buchten und Zuweisung brechen einspaltig.

## 14. Migration von `bmetallica`

Ziel: `bmetallica` meldet sich in OTA an und findet **exakt seinen VS-Code-Desktop** vor — gleiche Extensions, gleiche `settings.json`, gleiche SSH-Keys, gleiches XFCE-Layout.

### 14.1 Vorgehen
1. **Nutzer anlegen**: `bmetallica`, Mitglied in `admins` und `users` (entspricht seinen Kasm-Gruppen `Administrators` + `All Users`). Der Kasm-Passwort-Hash wird **nicht** übernommen — ein Import fremder Hash-Formate ist unnötiges Risiko. Stattdessen: Admin setzt ein Initialpasswort, `must_change_password = true`.
2. **Profil kopieren** (Kasm dabei gestoppt oder Session beendet, damit nichts halb geschrieben wird):
   ```bash
   rsync -aHAX --info=progress2 \
     --exclude='core.*' --exclude='.cache/' --exclude='*.sock' \
     --exclude='.config/google-chrome/*/Cache/' \
     --exclude='.config/Code/Cache*/' --exclude='.config/Code/CachedData/' \
     /srv/kasm_profiles/bmetallica/ /srv/ota/profiles/bmetallica/user/
   chown -R 1000:1000 /srv/ota/profiles/bmetallica/user/
   ```
   Erwartete Größe nach Ausschluss: deutlich unter 805 MB. **Bewusst mitgenommen**: `.ssh`, `.gnupg`, `.pki`, `.continue`, `.copilot`, `.vscode`, `.config/Code/User`, `.config/xfce4`, `.config/google-chrome` (ohne Caches).
   `.kasmpasswd` wird **nicht** übernommen — OTA erzeugt pro Session ein frisches VNC-Secret.
3. **Template anlegen** „Visual Studio Code": Image `kasmweb/vs-code:1.18.0-rolling-weekly`, 2 Cores, 2,7 GB, Kategorie *Development*, `persistent_profile_scope = user`, Pfad `/srv/ota/profiles/{username}/user` → `/home/kasm-user`. Damit ist es exakt die Kasm-Konfiguration.
4. **Zuweisen** an Gruppe `users` (damit später alle Entwickler es bekommen) und an `bmetallica`.
5. **Verifikation — Abnahmekriterien:**
   - [ ] `settings.json` enthält weiterhin `twinny.ollamaHostname`, `continue.*`, `myfeed.gatewayUrl`, `claudeCode.preferredLocation`
   - [ ] Remote-SSH-Extensions vorhanden und funktionsfähig
   - [ ] `ssh -T` gegen ein bekanntes Ziel funktioniert (Keys intakt, Permissions `600`)
   - [ ] XFCE-Desktop sieht aus wie vorher (Panels, Theme, Sprache Deutsch)
   - [ ] Copy/Paste zwischen Host-Browser und Container in beide Richtungen
   - [ ] Neustart der Session → alle Änderungen überleben
6. **Rückfallebene**: Kasm bleibt bis zur Abnahme unangetastet lauffähig; `/srv/kasm_profiles` wird **kopiert, nicht verschoben**, und zusätzlich als Tarball nach `/srv/ota/backups/` gesichert.

### 14.2 Weitere Kasm-Inhalte
Aus den bestehenden Images werden Templates: Obsidian, Thunderbird, GIMP, Inkscape, LibreOffice, IntelliJ IDEA. Die beiden VNC-Direktverbindungen (`HauptPC`, `VNC-HauptPC`) brauchen die Guacamole-Engine → Phase M7, in v1 bleiben sie in Kasm oder werden per externem Client genutzt.

---

## 15. Sicherheit

| Risiko | Maßnahme |
|---|---|
| Docker-Socket = Root | Nur `ota-agent` hat ihn; API und Web nicht. Später optional Socket-Proxy mit Endpoint-Whitelist oder rootless Docker |
| Container-Ausbruch | Kein `--privileged`, `no-new-privileges`, `cap_drop: ALL` — **auch kein `SYS_ADMIN`**, siehe §15.4 —, `seccomp`-Default, `pids_limit`, `/dev/shm` begrenzt. **Ausnahme: Administratoren** — siehe §15.1 |
| Anmeldung läuft mitten in der Arbeit ab | Rollende Sitzung: Jede Anfrage schiebt die Frist nach vorn. Die Frist misst Untätigkeit, nicht Zeit, und ist im Verwaltungsbereich zwischen 30 min und 48 h einstellbar |
| Zweite Session entwertet die erste | Das VNC-Passwort hängt am **Profil**, nicht an der Session. Sonst überschreibt der Start eines zweiten Containers `~/.kasmpasswd` im gemeinsamen Home — siehe §15.3 |
| Fremdzugriff auf Session | `forwardAuth` bei **jedem** Request; VNC-Secret nur serverseitig; Session-IDs sind UUIDv4 |
| Ressourcen-DoS durch einen Nutzer | Harte `cpus`/`mem_limit`/`pids_limit` pro Container, Session-Limit pro Nutzer, Preflight vor jedem Start: Arbeitsspeicher, freier Plattenplatz (Untergrenze) und Kontingent des eigenen Zuhauses |
| Zweiten Faktor raten | Fehlversuche beim Code zählen auf dieselbe Sperre wie beim Passwort (8 Versuche, 15 min). Ohne das war ein sechsstelliger Code bei bekanntem Passwort beliebig oft ratbar — siehe §15.4 |
| Konten ausspähen | Gleiche Meldung **und gleiche Dauer** für „gibt es nicht" und „falsches Passwort"; bei unbekanntem Namen läuft ein Argon2-Durchlauf gegen einen Blindhash |
| Fremder Bildschirm über ein Verwaltungsrecht | `sessions.view_all` erlaubt sehen und beenden, **nicht** das Zuschalten auf `/s/<id>/`. Dafür gilt Eigentum oder voller Admin — siehe §15.4 |
| Geheimnisse in Golden Images | Automatischer Secret-Filter beim „Session einfrieren", Warnung bei Fund, Build-Args nie im Image-Layer persistieren |
| Rechteausweitung im UI | Autorisierung serverseitig an jedem Endpunkt, Query-Scoping statt Frontend-Filter |
| Session-Hijacking | HttpOnly/Secure/SameSite-Cookies, kurze Token-Lifetime, Refresh-Rotation, Logout invalidiert serverseitig |
| Nachvollziehbarkeit | Audit-Log für alle Admin-Aktionen, unveränderlich (append-only), Export |

Vor dem Produktivgang: ein Sicherheitsreview der Auth- und Autorisierungspfade (Roadmap M6).

### 15.1 Administratoren dürfen in ihrem Container root werden

Wer OTA administriert, bekommt in **seinen eigenen** Session-Containern passwortloses `sudo`. Das
ist eine bewusste Lockerung, keine Nebenwirkung: Ohne sie liesse sich im Arbeitsplatz nichts
nachinstallieren und nichts prüfen — und genau dafür meldet sich ein Administrator dort an.

Konkret entfallen für diese Container zwei Sperren:

| Sperre | Warum sie fallen muss |
|---|---|
| `no-new-privileges:true` | Verhindert **jede** Rechteerhöhung, auch die über setuid. Mit ihr läuft `sudo` gar nicht erst an |
| `cap_drop: ALL` | Nimmt unter anderem `SETUID` und `SETGID`; ohne die kann `sudo` den Benutzer nicht wechseln |

**Der ehrliche Preis:** Root in einem Container ist nicht Root auf dem Host, aber der Abstand ist
kleiner als bei einem unprivilegierten Container. Diese Rechte gehören deshalb an denselben kleinen
Kreis wie der Zugang zum Docker-Host. Wer nur Nutzer anlegen oder Workspaces pflegen soll, bekommt
die einzelnen Rechte statt „Vollzugriff auf alles" — das Rechtemodell aus §5 kann das, und genau
dafür ist es da.

Entschieden wird das in der API (`user.is_admin`), nicht im Agent: Der Agent kennt keine Rollen und
soll auch keine kennen.

### 15.2 Ein Zuhause, ein laufender Container

Alle Workspaces mit Persistenz „Pro Nutzer" teilen sich dasselbe
`/home/kasm-user` (§11.1). Solange nur einer davon läuft, ist das genau richtig — es ist der Sinn
der Sache. Zwei gleichzeitig laufende Container auf einem Zuhause haben am 2026-08-27 zweimal
Schaden angerichtet, auf völlig unterschiedliche Weise:

| Was kaputtging | Warum |
|---|---|
| Zugangsdaten der laufenden Session | Der Startvorgang der Kasm-Images schreibt `~/.kasmpasswd` aus `VNC_PW` neu. Der zweite Container entwertete damit das Passwort des ersten (§15.3) |
| VS Code | Einzelinstanzig, mit Steuerkanal als Socket im Profil. Der zweite Container fand ihn und schickte seine Fenster in den *ersten* Container — dessen Aufsicht startete das Ganze alle drei Sekunden neu (§9.9) |

Beides liesse sich einzeln abfangen. Die gemeinsame Ursache nicht: **Ein Zuhause ist für einen
Rechner gedacht, nicht für zwei.** Jedes Programm, das eine Sperrdatei, einen Socket oder einen
Cache-Index im Home ablegt, geht davon aus, dass genau ein Prozess darauf schaut.

OTA lehnt deshalb den Start ab, wenn der Nutzer bereits eine laufende Session mit demselben
Profilpfad hat, und sagt auch, was stattdessen zu tun ist: den anderen beenden — oder dem zweiten
Workspace unter Persistenz ein eigenes Profil geben. Die Ablehnung ist die ehrlichere Antwort als
zwei Container, die sich gegenseitig die Arbeit zerlegen.

### 15.3 Das VNC-Passwort gehört zum Profil, nicht zur Session

Ein Fehler, der erst beim echten Benutzen auftrat und deshalb hier festgehalten sei.

Alle Sessions eines Nutzers teilen sich dasselbe `/home/kasm-user` — das ist der Sinn des
persistenten Profils (§11.1). Der Startvorgang der Kasm-Images schreibt aber bei *jedem*
Containerstart `~/.kasmpasswd` aus `VNC_PW` neu. Solange jedes Session-Passwort ein eigener
Zufallswert war, hiess das: **Wer eine zweite Session startete, entwertete die Zugangsdaten der
ersten.** Die lief weiter, das Bild lief weiter — aber jede neue Anfrage an ihren Stream bekam 401,
ohne dass sich an ihr irgendetwas geändert hätte.

Gemessen am 2026-08-27: Arbeitsplatz um 10:29 gestartet, VS Code um 11:12 dazu, danach antworteten
alle drei Displays des Arbeitsplatzes mit 401. Der verräterische Hinweis lag im Profil selbst — ein
`~/.vnc/<hostname>:1.pid` mit dem Hostnamen des *anderen* Containers.

Das Passwort wird deshalb aus Nutzer und Profilpfad abgeleitet (HMAC über das JWT-Geheimnis) statt
je Session gewürfelt. Wer sich dasselbe Zuhause teilt, teilt sich den Zugang; ein Überschreiben
schreibt denselben Wert. Das schwächt nichts ab — es ist dieselbe Person, und die Datei liegt
ohnehin in genau diesem Zuhause. Flüchtige Sessions ohne Profil behalten ihren Zufallswert, denn
dort hat jeder Container sein eigenes Home.

---

### 15.4 Was ein Durchsehen der Anmeldepfade zutage brachte

Am 2026-08-27 sind die Authentifizierungs- und Autorisierungspfade einmal von Hand durchgesehen
worden. Fünf Befunde, alle behoben, alle mit einer Prüfung in `scripts/test-authz.sh` festgenagelt —
denn ein Befund ohne Prüfung kommt wieder.

**1 · `SYS_ADMIN` für jeden Arbeitsplatz.** Die Fähigkeit stand vom ersten Tag an im Code, ohne
Begründung. Sie erlaubt Einhängungen und eigene Namespaces und ist damit praktisch gleichbedeutend
mit Root auf dem Host. Sie neben `no-new-privileges` zu setzen und im selben Kommentar zu
behaupten, ein Nicht-Administrator komme nicht an Root, war ein Widerspruch. Der Verdacht, Chrome
und Electron bräuchten sie, stimmt nicht — die laufen über `--no-sandbox`.

Zwei Folgen, beide gemessen und beide der bessere Tausch: Firefox meldet
`CanCreateUserNamespace() clone() failure: EPERM` und startet normal (der Standard-seccomp-Filter
lässt eigene User-Namespaces nur mit `SYS_ADMIN` zu; Firefox fällt auf eine schwächere interne
Sandbox zurück, die ohnehin nur gegen eine bösartige Webseite in genau dem Container schützt, in
dem der Nutzer schon ein Terminal hat). Und AppImages hängen sich nicht mehr per FUSE ein — das
Rezept setzt jetzt `APPIMAGE_EXTRACT_AND_RUN=1`.

**2 · `sessions.view_all` reichte bis auf den fremden Bildschirm.** In der Oberfläche heißt das
Recht „Alle Sessions sehen und beenden". Die Prüfung vor jedem Aufruf von `/s/<id>/` benutzte aber
dieselbe Funktion wie die Liste — und damit konnte eine Support-Rolle an einem fremden, laufenden
Bildschirm sitzen, mit offenem Terminal und entsperrtem Passwortspeicher. Getrennt in
`owns_session` (verwalten) und `may_attach_to_session` (daransitzen). Fernhilfe mit ausdrücklicher
Einwilligung wäre der richtige Weg dafür; die gibt es noch nicht.

**3 · Fehlversuche beim zweiten Faktor zählten nicht mit.** Nur das Passwort führte zur Sperre. Bei
bekanntem Passwort war ein sechsstelliger Code damit beliebig oft ratbar — und drei davon sind zu
jedem Zeitpunkt gültig (`valid_window=1`). Dasselbe galt für die Rückfallcodes.

**5 · Ein `PUT` ohne Gruppenzuweisung nahm sie allen weg.** Aufgefallen am 2026-08-28, als ein Test
eine Einstellung am Arbeitsplatz änderte und die Zuweisung nicht mitschickte: Der Workspace
verschwand daraufhin wortlos von jedem Dashboard — für die Nutzer sah es aus, als sei er gelöscht.
`group_ids` ist jetzt `None`-fähig: nicht mitgeschickt heißt „lass stehen", eine leere Liste heißt
„niemand mehr". Der Unterschied zwischen *nichts gesagt* und *nichts gewollt* muss in einer
Schnittstelle ausdrückbar sein.

**4 · Ein unbekanntes Konto antwortete schneller.** Die Meldung war schon gleich, die Dauer nicht:
ohne Argon2-Durchlauf war die Antwort messbar früher da. Damit ließe sich die Nutzerliste abfragen,
ohne je hereinzukommen.

---

## 16. Betrieb

- **Deployment**: ein `docker-compose.yml` plus `.env`; `make up`, `make migrate`, `make backup`. Alles reproduzierbar aus dem Repo.
- **Konfiguration**: Umgebungsvariablen für Secrets (DB-Passwort, JWT-Key), DB für alles Fachliche
- **Migrationen**: Alembic, beim Start automatisch geprüft, nie automatisch destruktiv
- **Backup**: Postgres-Dump + Profil-Tarballs, nächtlich, Restore-Prozedur dokumentiert und **mindestens einmal getestet** (ungetestete Backups zählen nicht)
- **Monitoring**: `/healthz` je Dienst, Prometheus-Metriken (aktive Sessions, Startdauer, Fehlerrate, Host-Ressourcen), optional Grafana
- **Logs**: strukturiert (JSON) mit `session_id`/`user_id`-Korrelation, Rotation
- **Update**: Rolling — `ota-api`/`ota-web` neu starten unterbricht **laufende Sessions nicht**, weil Traefik direkt zu den Containern routet. Das ist ein bewusster Architekturvorteil.

---

## 17. Entscheidungen

Stand 2026-08-27. Was hier steht, ist entschieden — die Begründung bleibt dokumentiert,
damit später nachvollziehbar ist, warum es so aussieht wie es aussieht.

### 17.1 Zielgröße — geklärt: Teststellung

Dieser Host ist eine **Teststellung**, keine Produktionsmaschine. Zwei bis drei parallele
Arbeitsplätze sind hier realistisch, und das genügt. Die Dimensionierung für ~20
Entwickler (≥ 16 Kerne, ≥ 64 GB, ≥ 1 TB) ist eine Frage der späteren Produktionsmaschine,
nicht dieser. Mehrere Hosts sind im Datenmodell vorgesehen (`sessions.host_id`), bleiben
aber M10.

### 17.2 Zertifikat — bleibt selbstsigniert

Es bleibt bei der lokalen CA. Ein echtes Zertifikat kommt später über einen vorgelagerten
Reverse Proxy, falls überhaupt. Der Weg dafür ist in Kapitel 10 des Handbuchs beschrieben
und braucht keine Änderung an OTA.

**Folge:** HSTS bleibt aus. Solange die CA nicht in jedem Browser importiert ist, würde es
den „trotzdem fortfahren"-Ausweg entfernen und Nutzer aussperren statt schützen.

### 17.3 Basisimages — erben, eigenes ab M5

Für den Piloten weiter von `kasmweb/*` erben. Ein eigenes `ota/base-xfce` ab M5 — es macht
nicht nur lizenzrechtlich unabhängig, sondern bringt auch `clipnotify` und `xsel` mit, ohne
die die Zwischenablage-Brücke bei Abfrage statt Ereignissen bleibt (§10.4).

### 17.4 Lizenzen — geprüft

Kasms Image-Repository ist MIT, KasmVNC GPL-2.0, die MS-VS-Code-EULA erlaubt internes
Deployment ausdrücklich. Am Originaltext verifiziert, siehe §3.

### 17.4b Reichweite — rein intern

OTA bedient ausschließlich eigene Mitarbeiter im Firmennetz. Damit greift die Einschränkung
der Microsoft-EULA nicht und der MS-Build von VS Code ist zulässig (§3.1). Sobald echte
Dritte Zugang bekämen, bräuchten diese ein Golden Image mit VSCodium.

### 17.5 Name — bleibt OpenTerminalApps

### 17.6 JetBrains — nur Community

Nur die Community-Editionen (Apache-2.0, kommerziell kostenfrei). Ultimate wird nicht
ausgerollt; damit entfällt die Frage nach Named-User-Lizenzen, und OTA speichert keine
Lizenzschlüssel.

### 17.7 Arbeitsplatz — der Kern des Produkts

Nicht ein Zusatz neben Ein-App-Containern, sondern das Modell, für das OTA gebaut wird
(§1.1). Grundfunktion steht und ist geprüft.

### 17.8 Streaming-Engine — KasmVNC, ein Display je App

Beide Betriebsarten nutzen damit dieselbe Strecke. Der eine Nachteil — jedes Display hat
seine eigene Zwischenablage — ist durch die Brücke aus §10.4 ausgeglichen.

### 17.9 AD-Anmeldedaten — Kerberos, keine Passwort-Durchreichung

Standardweg wird die **Kerberos-Ticket-Injektion** (§9.4, Weg 2). Der Weg „Nutzer verbindet
selbst" bleibt immer verfügbar.

**Die Passwort-Durchreichung wird vorerst gar nicht gebaut** — nicht nur abgeschaltet. Sie
würde OTA zum Passwortspeicher machen; wenn sie später gebraucht wird, ist das eine eigene
Entscheidung mit eigener Prüfung.

### 17.10 Cursor — bleibt draussen

Aus dem App-Katalog entfernt, nicht nur gesperrt. Proprietär, Lizenzlage für
Mehrbenutzerbetrieb ungeklärt, und als VS-Code-Fork dürfte es den MS-Marketplace ohnehin
nicht ansprechen. Die übrigen Editoren sind unbedenklich.

### 17.11 Registry-Signatur — nicht prüfen

Registries sind eine Vertrauensentscheidung des Admins, mit deutlichem Hinweis im
Import-Dialog. Eine Signaturprüfung würde eine Abhängigkeit von Kasms öffentlichem
Schlüssel schaffen, ohne mehr Sicherheit zu bringen als die Entscheidung, wem man vertraut.

Ausführlich, mit den Alternativen, die nicht getragen hätten:
[ADR-004](docs/adr/004-keine-signaturpruefung-fuer-registries.md).

### 17.12 Kasm und Golden Images — gelöst, ohne Kasm anzufassen

**Die Ursache war ein geerbtes Label.** Kasms Agent räumt im Modus „Aggressive" alle 30
Sekunden auf und löscht dabei genau die Images, die `com.kasmweb.image=true` tragen und
nicht in seiner Datenbank stehen. Ein von einem Kasm-Image abgeleitetes Golden Image
**erbt dieses Label** und wird deshalb als verwaiste Workspace-Version eingestuft.

Am 2026-08-27 durch einen Gegentest belegt: Zwei identische abgeleitete Images, eines mit
dem Label, eines ohne. Nach zwei Aufräumdurchläufen war das mit Label gelöscht, das ohne
unangetastet. Images ohne dieses Label betrachtet Kasm gar nicht erst — `alpine`- und
`busybox`-Ableitungen überstehen jeden Durchlauf.

**Der Builder löscht das Label deshalb in jedem erzeugten Dockerfile.** Damit laufen OTA
und Kasm auf demselben Host nebeneinander, ohne dass an Kasm etwas umgestellt werden muss.

Als Rückfallebene bleibt eine zweite Möglichkeit bestehen: Ein Build kann fremde
Aufräumdienste für seine Dauer anhalten (`pause_foreign_cleanup`, Vorgabe `kasm_agent`).
Der Agent startet sie in jedem Fall wieder — auch wenn der Build scheitert. Nach dem
Label-Fund ist das nicht mehr nötig, aber es kostet nichts und deckt den Fall ab, dass ein
anderes System auf demselben Host nach anderen Regeln aufräumt.

### 17.13 Port — bleibt frei einstellbar

OTA bleibt auf **8443**. Port 443 zu übernehmen war nie notwendig — der Port ist über
`OTA_HTTPS_PORT` frei wählbar, und mit einem vorgelagerten Reverse Proxy (§17.2) ist die
Frage endgültig gegenstandslos. Kasm behält 443.

**Damit entfällt auch der Zwang, Kasm abzuschalten.** Beide Systeme laufen dauerhaft
nebeneinander; §17.12 hat den letzten Konflikt beseitigt. Aus der Ablösung wird ein
Umzug im eigenen Tempo.

### 17.14 Migration — nur kopieren, Kasm bleibt

Übernommen wird das Profil, nicht der Container. `scripts/migrate-kasm-profile.sh` kopiert
`/srv/kasm_profiles/<nutzer>` nach `/srv/ota/profiles/<nutzer>/user`, lässt Caches,
Absturzabbilder und das alte VNC-Passwort weg und setzt die Eigentümerschaft auf 1000.

Am 2026-08-27 durchgeführt: **805 MB Rohdaten wurden zu 63 MB**, ohne dass eine
Nutzerdatei fehlt — der Löwenanteil waren Service-Worker-Caches (193 MB), von Chrome
nachgeladene Modelle (91 MB) und Editor-Caches. Abnahme bestanden: Einstellungen,
Extensions, SSH- und GPG-Schlüssel, XFCE-Layout und Continue-Konfiguration sind da.
**Kasm blieb unverändert** und läuft weiter.

