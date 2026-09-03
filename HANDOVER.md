# 🤖 KI-AGENTEN-ÜBERGABE (HANDOVER & CONTEXT INJECTION)

> **ANWEISUNG FÜR DEN EMPFANGENDEN AGENTEN:** Lies diese Datei vollständig, bevor du Code generierst oder vorschlägst. Sie enthält den exakten Projektstand, architektonische Leitplanken und den "mentalen Kontext" der vorherigen Sitzung. Nimm diese Identität und Arbeitsweise nahtlos an.

---

## 📅 METADATEN & SITZUNGSKONTEXT

* **Projektname:** OpenTerminalApps (OTA) — selbstgehostete Alternative zu Kasm Workspaces
* **Technologie-Stack:**
  * **API:** Python 3.12, FastAPI 0.115, SQLAlchemy 2.0, PostgreSQL 16 (psycopg 3), Alembic, Pydantic 2, argon2-cffi, PyJWT + cryptography (RS256 für Keycloak), pyotp, qrcode, Pillow, ldap3, httpx
  * **Agent:** Python 3.12, FastAPI, `docker` SDK — **der einzige Dienst mit Docker-Socket**
  * **Web:** React 18 + TypeScript + Vite, **handgeschriebenes CSS, keine UI-Bibliothek**
  * **Infrastruktur:** Docker Compose — Traefik v3.7 (Ingress, TLS), Keycloak 26.7 (IdP), eigene Registry, PostgreSQL
  * **Session-Container:** Selkies 1.6.2 auf Debian 13 (**Vorgabe**) bzw. KasmVNC 1.4.x (für Images von Kasm)
  * **Tests:** Bash-Prüfreihen (`scripts/test-*.sh`) + Puppeteer/Chromium (`tests/e2e.mjs`) — **keine Unit-Test-Frameworks**, alles gegen die laufende Anlage
* **Letzter Branch / Commit:**
  * `main` → der Selkies-Weg ist **zusammengeführt und Vorgabe**; `webrtc-viewer` ist damit erledigt
  * Das Vorgabe-Basisimage ist `ota/base-desktop:1` (Debian 13 + XFCE + Selkies, **kein KasmVNC**)
  * Repository: `github.com/bmetallica/openterminalapps` — **privat, muss privat bleiben**
* **Datum der Übergabe:** 2026-09-03
* **Ziel des Projekts:** Jeder Nutzer bekommt **seinen eigenen Linux-Arbeitsplatz im Browser** — ein Container je Person, die Anwendungen darin installiert, jede formatfüllend gestreamt, alle mit **einem gemeinsamen Zuhause** (dieselben Projekte, derselbe SSH-Schlüssel, dieselbe Zwischenablage). Daneben Einzelanwendungen als Wegwerf-Container, fremde Web-Anwendungen im Katalog und zentrale Anmeldung über Keycloak.

---

## 🧠 BESPROCHENER KONTEXT & PHILOSOPHIE

### Architektur-Stil

Drei Dienste mit **scharf getrennten Zuständigkeiten**, verbunden über HTTP:

```
Browser ──HTTPS──▶ Traefik ──┬──▶ web       Oberfläche (nginx)
                             ├──▶ api       REST, Anmeldung, Rechte, Sessions
                             └──▶ /s/<id>   Stream einer Session (forwardAuth)
                                     │
                    api ──HTTP──▶ agent ──▶ Docker-Socket
                                     │
                            Session-Container
```

* **Nur `agent` fasst Docker an** ([ADR-002](docs/adr/002-nur-der-agent-fasst-docker-an.md)). Die API verarbeitet Nutzereingaben und bekommt den Socket deshalb **nicht** — dieselbe Trennung gilt für das Dateisystem des Hosts. Wenn du überlegst, wo etwas hingehört: Fremde Daten verarbeiten → API. Container/Dateisystem anfassen → Agent.
* **Keycloak ist der Identitätsanbieter, OTA sein Verwalter.** Konten, Gruppen und die AD-Anbindung richtet man in OTAs Oberfläche ein; die Keycloak-Konsole bleibt für den Alltag zu. Ein lokales **Notfallkonto** (`notfall`, erreichbar unter `/notfall`) funktioniert ohne Keycloak.
* **Zwei Betriebsarten je Vorlage:** `workspace` (ein Container, mehrere Anwendungen auf eigenen X-Displays) und `single_app` (Wegwerf-Container je Anwendung).

### Wichtige Design-Entscheidungen

| Entscheidung | Begründung |
|---|---|
| **Pfade heissen nach `users.id`, nicht nach dem Anmeldenamen** | Seit die Konten aus Keycloak kommen, zieht OTA einen dort geänderten Namen nach — der Pfad zeigte danach woanders hin. Daneben steht ein Symlink unter dem Namen, damit Menschen im Dateisystem etwas finden. Gilt für `/srv/ota/profiles`, `/srv/ota/userfiles`, `/srv/ota/groupfiles`. |
| **Farbe ist Information, nie Dekoration** | Gesättigte Farbe tritt ausschliesslich als Zustand auf. Die Primäraktion ist bewusst unbunt. |
| **Deutsch als Schlüssel, Englisch als Wörterbuch** | `t('deutscher Text')` mit `web/src/lib/i18n.en.ts` als Übersetzungstabelle. Neue Texte **immer** in beiden. |
| **Das Zuhause gehört dem Menschen** | Skeleton-Dateien kommen beim **ersten** Start; „durchsetzen" (bei jedem Start überschreiben) ist die begründungspflichtige Ausnahme. |
| **Drei Ablagen mit verschiedenen Fragen** | gemeinsam (Verwaltung → alle, im Container nur lesbar) · eigen (je Nutzer, beschreibbar) · Gruppenlaufwerk (je Gruppe, beschreibbar). **Die Mitgliedschaft entscheidet, und sonst nichts** — auch ein Administrator kommt nur an die Gruppen, in denen er selbst ist. |
| **Zweiter Faktor: angeboten, nicht verlangt** | Passkey **oder** Einmalkennwort, über zwei Keycloak-Unterflüsse. Siehe „Verworfene Ansätze". |
| **Vorgabe des Gewands ist dunkel**, nicht „wie der Rechner" | Die meisten Rechner melden hell; OTA wäre sonst beim nächsten Aufruf für fast alle plötzlich hell. |
| **Symbole als Adresse, nicht als Datenadresse** | Ein Katalog mit sechzehn Symbolen wiegt als Datenadressen 140 KB, und das Dashboard lädt die Vorlagen **alle 15 Sekunden** neu. |
| **KasmVNC bleibt die Vorgabe** | Selkies ist ein Versuch auf einem Zweig, kein Ersatz. |

### Arbeitsweise (übernimm diese!)

* **Messen statt vermuten.** Fast jeder Fund dieser Sitzung kam aus einer Messung, nicht aus einer Überlegung. Wenn du eine Vermutung hast: baue sie, miss sie, und wenn sie falsch war, schreib auf, was statt dessen gilt.
* **Kommentare erklären das *Warum*, nicht das *Was*** — auf Deutsch, oft mit dem Datum und dem konkreten Fehlerbild („Gemessen am 2026-08-27: 119 leere VS-Code-Fenster, 2,5 GB belegt").
* **Ein Test, der die Ursache prüft, schlägt einen, der das Symptom prüft.**
* **Kein `|| true` am Ende von Installationsketten** — das hat schon einmal einen gescheiterten Build grün gemacht.
* **Commit-Nachrichten sind ausführlich und ehrlich**, inklusive eigener Fehler.
* Dokumentation wird **mitgeführt**: `roadmap.md` (Stand), `plan.md` (Architektur + Begründungen), `docs/wiki/` (21 Kapitel, wird im Programm als Hilfe ausgeliefert), `docs/adr/` (teure Entscheidungen).

### Verworfene Ansätze (Sackgassen vermeiden!)

1. **„Passkey ODER Einmalkennwort" als zwei ALTERNATIVE-Schritte nebeneinander.** Gemessen am 2026-09-02: Wer die Rolle `zweiter-faktor` trägt und **noch keins von beiden** eingerichtet hat, kommt gar nicht mehr herein — die Anmeldung endet mit „Invalid username or password". Eine vorgemerkte Ersteinrichtung (`CONFIGURE_TOTP`) hilft nicht, denn vorgemerkte Aktionen laufen **nach** der Anmeldung. Lösung: zwei Unterflüsse `ota-passkey` (mit Bedingung „beim Nutzer eingerichtet") und `ota-einmalkennwort`.
2. **`conditional-credential` als Keycloak-Bedingung für „hat einen Passkey".** Prüft, was während der Anmeldung *benutzt* wurde, nicht was jemand *hat*. Falsches Werkzeug.
3. **Ein eigenes Streaming-Protokoll bauen.** x11vnc ist einfädig und ungepflegt; TigerVNC ist der Stamm, von dem KasmVNC abzweigt — man würde gerade die Teile weglassen, die ihn ausmachen. Ein eigener Kodierer wären Personenjahre. Besser ist nur ein **Wechsel des Verfahrens** (H.264/WebRTC), und dafür gibt es fertige Maschinen.
4. **TURN im Session-Container.** Ein TURN-Server je Sitzung, hinter der Docker-Bridge, mit Ports, die der Agent durchreicht. Klingt sauber (ein Fehler trifft eine Sitzung statt aller) und **kann nicht funktionieren**: Er meldet als Relay die Adresse des Hosts, verschickt die Pakete aber mit der Container-Adresse als Absender, und jeder WebRTC-Stack verwirft die. Sichtbar war das als „Waiting for stream" im Browser und `Fatal SSL error` im Container — an keiner der beiden Stellen stand der Grund. Gemessen mit `scripts/pruef-turn.py`; seither läuft `turn` als Dienst auf dem Netz des Hosts.

5. **Selkies vom `main`-Zweig / aus PyPI `selkies==1.6.1`.** PyPI führt unter dem Namen `selkies` noch die **alte** GStreamer-Linie; der `main`-Zweig verlangt `pixelflux~=2.1.0`, das es nirgends gibt. Genommen wurde das getaggte Release **v1.6.2**.
6. **GPU-Durchreichung hier bauen.** Die Maschine hat eine QEMU-Standard-VGA, keine GPU — ließe sich weder bauen noch ehrlich prüfen.
7. **Passwort-Durchreichung an Netzlaufwerke.** Vom Nutzer ausdrücklich ausgeschlossen (`plan.md` §17.9).
8. **`docker builder prune` ist erlaubt und war nötig** (94 % volle Platte ließ Container-Starts scheitern) — Images und Volumes aber **nicht** anfassen.

### Harte Randbedingungen (vom Nutzer gesetzt)

* OTA bleibt **firmenintern** — das ist die Grundlage, auf der die MS-VS-Code-EULA erlaubt ist.
* **Cursor bleibt draussen.** **JetBrains nur Community.**
* **Kasm muss weiterlaufen** — OTA läuft daneben auf demselben Host, nur die VS-Code-Containerprofile wurden kopiert.
* Das Repository bleibt **privat**. **Keine Passwörter in Dateien im Repo** — sie stehen in `deploy/.env` (gitignored).
* Registry-Signaturen werden nicht geprüft — bewusste Entscheidung ([ADR-004](docs/adr/004-keine-signaturpruefung-fuer-registries.md)).

---

## 📍 AKTUELLER PROJEKTSTAND (STATUS QUO)

### ✅ Abgeschlossen & Funktionstüchtig

**Arbeitsplatz & Streaming**
- Ein Container je Nutzer, jede Anwendung auf eigenem X-Display, gestartet auf Zuruf
- Jede Anwendung in eigenem Tab mit eigener Adresse; als PWA auf dem Desktop ablegbar
- Stream wächst mit dem Fenster (`resize=remote`); Reconnect-Automat; Leerlaufuhr abgeschaltet
- Klassischer XFCE-Desktop als zusätzliche Ansicht
- **Zwischenablage ereignisgesteuert** (`clipnotify -l` je Display) mit Rückfall auf Abfrage, wenn das Image es nicht mitbringt. **Alle zwölf Abnahmefälle** aus `plan.md` §10.5 laufen automatisiert (Fall 7 auf Zuruf mit `OTA_PRUEFE_JAVA=1`)

**Identität**
- Keycloak im Stack **oder** ein vorhandenes anbinden; OTA ist dessen Verwalter (Konten, Gruppen, AD/LDAP-Föderation)
- Zweiter Faktor je Gruppe erzwingbar, wahlweise **Passkey oder Einmalkennwort**
- Notzugang `/notfall`; Übernahme von Bestandskonten; Abmelden überall
- Fremde Web-Anwendungen im Katalog (OIDC-Client wird in Keycloak angelegt) — produktiv gegen Open WebUI geprüft

**Dateien**
- Drei Ablagen (gemeinsam / eigen / **Gruppenlaufwerke**), alle auch in der Kontrollleiste einer laufenden Session, mit Ziehen und Ablegen
- Skeleton-Profil je Workspace **und je Anwendung** (Teilbaum kommt beim ersten Start *dieser* Anwendung)
- Startskript je Workspace, Einmal-Skripte je Nutzer

**Images & Betrieb**
- Build-Pipeline mit Live-Protokoll, Rezepte, Versionen, Rückrollen, Session einfrieren
- **Anwendungssymbole aus den Paketen** (`.desktop` → Icon-Datei → auf 128 px verkleinert → unter eigener, zwischenspeicherbarer Adresse)
- **Eigenes Basisimage `ota/base-xfce:test`** (Ubuntu 24.04 + XFCE + KasmVNC 1.4.0, 965 MB statt 20 GB) — 29 Prüfpunkte gegen den Vertrag mit dem Agent
- **Stückliste je Image** (`make sbom`, SPDX + CycloneDX)
- Sicherung/Wiederherstellung von Profil, Container, Datenbank und Inhalten; eigene Registry; HTTPS ab Werk; läuft hinter Reverse Proxy **und** direkt über IP
- **Helles Gewand** (dunkel / hell / wie der Rechner), auch auf der Anmeldemaske und in Keycloaks Maske

### 🛠️ In Arbeit / Unvollständig

**Eigenes Basisimage ohne Kasm** — Zweig `webrtc-viewer`:
- ✅ `ota/base-desktop:test` — **Debian 13 + XFCE + Selkies, kein KasmVNC**. Konto `ota` unter `/home/ota`, daneben ein Verweis unter dem OTA-Anmeldenamen. Geprüft durch OTA hindurch: 1404 Bilder, 1440×900, über TURN/TCP.
- ✅ **Der Heimatpfad kommt aus dem Image.** Der Agent liest `HOME` aus der Image-Konfiguration (`_heimat_aus_env`) und prüft den Wert, bevor er ihn als Mount-Ziel benutzt; ohne Angabe bleibt es bei `/home/kasm-user`, damit `kasmweb/*` unverändert läuft.
- ✅ **GStreamer aus der Distribution** (1.26.2) statt aus dem Selkies-Bündel. Das war erzwungen, nicht gewählt: Das Bündel bringt `gi/overrides` für **Python 3.12** mit, Debian 13 hat 3.13. Distribution und GStreamer hängen über Python zusammen.
- ✅ Das Dockerfile prüft sich selbst — `gst-inspect-1.0 webrtcbin`, `x264enc`, der Python-Import von `Gst/GstWebRTC/GstSdp` und die drei Selkies-Module. Alle drei Abstürze auf dem Weg waren grüne Builds mit Fehlern erst in der ersten Sitzung.
- ⚠️ **1,78 GB, kein Gewinn gegenüber dem Vorgänger.** Das Bündel spart 366 MB, Debians `plugins-bad` kostet dasselbe. Die dicksten Brocken sind `libllvm19` (124 MB) und `mesa-libgallium` (41 MB) — Software-OpenGL, ohne GPU nötig. Echter Ballast: `libonnxruntime`/`libdnnl` und `libflite`, ~70 MB, nur mit `--force-depends` zu entfernen.

**Einzelanwendungs-Modus** — überträgt jetzt wirklich nur die Anwendung:
- ✅ Der Agent schickt `OTA_MODE`; das Startskript startet bei `single_app` nur `xfwm4 --compositor=off` statt der ganzen Arbeitsumgebung und setzt das erste Fenster auf `fullscreen`.
- ✅ Feld **Startbefehl** im Bildbauer (`ImageBuild.start_command`, über base64 ins Dockerfile). Nötig, weil der Bildbauer für Einzelanwendungen das Startskript des Basisimages behält — bei Kasm-Images richtig, bei OTAs eigenem ein leerer Bildschirm.
- ✅ Gemessen: nur `Xvfb`, `xfwm4`, die Anwendung, Selkies, PulseAudio; Fenster `0 0 1440x900` mit `_NET_WM_STATE_FULLSCREEN`.

**Ein Fehler, der lange dalag:** Aus `Session.vnc_user` baut die API den Basic-Auth-Header für Traefik — in den Container kam der Name nie. Dort stand `kasm_user` fest im Startskript, und solange beide zufällig übereinstimmten, fiel es nicht auf. Ein Image mit anderem Namen antwortet mit 401 und zeigt eine leere Seite. Beide Seiten lesen jetzt denselben Wert; er hängt an der Maschine (`ota` für Selkies, `kasm_user` für KasmVNC — dort ist der Name Pflicht).

**Selkies als zweiter Streaming-Weg** — Zweig `webrtc-viewer`, Commit `d2ad3ae`:
- ✅ Der erste Anlauf (`base-selkies`, inzwischen entfernt) streamte H.264 über WebRTC **durch OTA hindurch**, mit OTAs Anmeldung davor, Auflösung folgt dem Browserfenster
- ✅ `Template.stream_engine` (`kasmvnc` Vorgabe | `selkies`), engine-abhängige Traefik-Labels (Port 8080/HTTP statt 6901/HTTPS)
- ✅ **TURN als eigener Dienst im Stack** (`turn`, `network_mode: host`, kurzlebige HMAC-Zugänge aus `OTA_TURN_SECRET`); der Session-Container veröffentlicht keinen Port mehr, beliebig viele Selkies-Sitzungen je Host
- ✅ Testarbeitsplatz **„Arbeitsplatz (Selkies-Versuch)"**, sichtbar nur für Gruppe `selkies-versuch` (Mitglied: `bmetallica`)
- ❌ **Nicht gemessen:** Latenz/Bildqualität im Vergleich, CPU-Kosten von x264 in Software, ob „ein Bildschirm je Sitzung" den Alltag trägt
- ✅ **Läuft beim Nutzer**, Bild und Zwischenablage, am 2026-09-02 bestätigt
- ✅ **MTU-Falle gefunden und behoben.** Chrome verschickt seinen DTLS-Handschlag mit fest 1200 Byte je Paket und passt sich einer kleineren Pfadgrösse *nicht* an. Hinter WireGuard mit MTU 1000 kam nur das kleine Paket der Flucht an (`263, 263, 263, …` statt `1200, 263, 1200, 263`), OpenSSL wartete auf den Rest und antwortete nie — im Browser „Waiting for stream", im Container **kein Fehler**. Abhilfe: `OTA_TURN_PROTOCOL=tcp` zusammen mit `OTA_TURN_ICE_POLICY=relay`; ein dritter Image-Patch macht `iceTransportPolicy` überhaupt erst einstellbar.
- ✅ Zwei Prüfwerkzeuge, die dem Weg vorher fehlten: `scripts/pruef-turn.py` (schickt ein Paket durch den TURN und vergleicht Absender mit Relay-Adresse) und `scripts/pruef-selkies.mjs` (fährt einen Browser in einem Container, der den Session-Container **nicht** direkt erreichen kann, durch Anmeldung und Sitzung und liest aus der WebRTC-Statistik, ob ein Bild ankommt)
- ✅ Abgelöst durch `images/base-desktop` (Debian 13, ohne KasmVNC, Konto `ota`); der Vorgänger ist entfernt
- ❌ Keine eigene Prüfreihe für den Selkies-Weg; die vorhandenen Reihen prüfen nur, dass der **bisherige** Weg unberührt ist
- ❌ Kein Umschalter in der Oberfläche — `stream_engine` lässt sich nur über die API setzen

### Userinteraktionen

Chronologisch, mit dem, was daraus wurde. (Die ersten Einträge stammen aus dem
zusammengefassten Teil der Sitzung.)

| # | Nutzeranweisung (sinngemäß/zitiert) | Antwort / Ergebnis |
|---|---|---|
| 1 | „mach weiter, mir ist aufgefallen das eine verbindung zu einer laufenden App session schon nach ein paar minuten beendet wird … zudem fehlt noch die bereitstellung der apps als PWA" | Ursache: KasmVNCs `idle_disconnect` ist ein `<select>` mit vier Werten — ein Wert ausserhalb fällt **auf den ersten** zurück (10 min). Behoben über `set_idle_timeout` per postMessage. PWA je App gebaut (Manifest wird nur einmal beim Laden gelesen → eigene Adressen). |
| 2 | „nein es ist im lokalen netzwerk (sollte aber auch via vpn gehen)" | Zur Kenntnis genommen, weitergearbeitet. |
| 3 | „ich versuche OTA über meinen intranet reverseproxy freizugeben, bekomme aber nur eine weiße Seite" | Diagnose geliefert (Traefik `forwardedHeaders.trustedIPs` muss die **verbindende** IP nennen, Upstream muss `X-Forwarded-Port 443` senden). |
| 4 | „ahh alles klar, war mein fehler … aber lass uns die Ablagen trennen: admin-ablage vs. user-ablage, je Workspace abschaltbar, auch in der Menüleiste bei laufender Session" | Zwei Ablagen getrennt, `user_shelf` je Vorlage, `ShelfPanel` in der Kontrollleiste mit Ziehen und Ablegen. |
| 5 | „was wir noch bräuchten ist die möglichkeit einmal skripte jeh workspace an zu legen" | Einmal-Skripte je Workspace, gebucht je Nutzer, mit „Nochmal"-Rücksetzung. |
| 6 | „ich überlege den kompletten authentifikationsmechanismuss umzustellen … stelle daraus eine auth-roadmap.md zusammen … baue aber noch nichts um" | `auth-roadmap.md` mit 12 Entscheidungspunkten geschrieben. |
| 7 | „erstmal die frage ob keycloak überhaupt die beste wahl ist" | Vergleich geliefert, Empfehlung Keycloak. |
| 8 | „keycloak bitte im stack aber auch einen weg ein bereits existierendes anzubinden" | Beide Wege umgesetzt (`OTA_IDP_MODE`). |
| 9 | „Gruppenentzug während laufender Session = bis zur nächsten Anmeldung gelten lassen. Wer darf Anwendungen anlegen verstehe ich nicht ganz" | Frage erklärt, Entscheidung übernommen (gilt bis heute, auch für Gruppenlaufwerke). |
| 10 | „was soll der quatsch mit dem Speicherversprechen? … das hier ist nur eine entwicklungsumgebung" | **Berechtigte Korrektur.** Ich hatte eine Speicherobergrenze zu einem Entscheidungs-Gate gemacht. Entfernt; nur noch eine Notiz zur Entwicklungsmaschine. |
| 11 | „ja mache das und fange mit der umstellung auf keycloak an. mache solange eigenständig weiter bis du meine interaktion wirklich benötigst" | Etappen A–E umgesetzt. |
| 12 | „mach weiter" | fortgesetzt |
| 13 | „mache alles, ein echtes openwebui läuft auf … username … passwort …" | Open WebUI end-to-end gegen Keycloak angebunden. **Zugangsdaten wurden nicht committet.** |
| 14 | „wie ist das passwort für den keycloak user bmetallica?" | Beantwortet. |
| 15 | „lass uns die email mit ins OTA als pflichtfeld übernehmen" | E-Mail Pflichtfeld, Propagation nach Keycloak, `SPECIAL_USE_DOMAIN_NAMES` angepasst. |
| 16 | „halt, hast du jetzt alles auf ota.boden.home umgeschrieben? eigentlich sollten beide wege gehen" | **Berechtigte Rückfrage.** Beide Wege (IP und Domain) funktionieren und sind geprüft. |
| 17 | „kann ich das nicht in openwebui auf allow selfsigned stellen … testumgebung flexibel halten" | Risiko einmal benannt, dann umgesetzt (`sitecustomize.py` gemountet). Entscheidung steht. |
| 18 | „was muss in der sitecustomize.py stehen?" | Inhalt geliefert. |
| 19 | „der auth funktioniert, allerdings werden keine gruppen angezeigt" | Gruppen-Claim ergänzt. |
| 20 | „mach mit dem rest weiter. abmelden führt nicht zu keycloak; die farbe der linken Navigation geht nicht bis nach unten" | Beides behoben (Logout über `/api/auth/oidc/logout`, `.rail` scrollbar). |
| 21 | „du musst auch das wiki und die readme vervollständigen. funktioniert die installation überhaupt noch? bekommen wir das keycloak loginfenster in unser design?" | Wiki + READMEs nachgezogen, Keycloak-Theme in OTA-Farben. |
| 22 | „nein nicht neuinstallation — die frage war ob dein beschriebener installationsweg noch funktioniert" | **Berechtigte Korrektur.** Zwei echte Brüche im dokumentierten Weg gefunden und behoben. |
| 23 | „ja" (Proxy-IP aus der Vorlage nehmen) | `traefik.yml` wird aus Vorlage + `.env` erzeugt. |
| 24 | „mach weiter und committe anschließend" / „hast du die readme auch geupdatet?" | erledigt |
| 25 | „sieh dir die roadmap an, ob wirklich alles abgearbeitet ist" | 22 offene Punkte gegen den Code geprüft, Roadmap korrigiert. |
| 26 | „was ist jetzt noch offen, mach mir eine liste" | Liste geliefert. |
| 27 | **„setze 1, 2 (außer der firefox erweiterung), 3 (das basis image bitte erstmal als testimage)"** | Pfade auf Kennungen umgestellt + Migration; SBOM; eigenes Basisimage; ereignisgesteuerte Zwischenablage; Abnahmefälle 3/7/12. Commit `e195589`. |
| 28 | „muss dann überhaupt kasm-vnc in unser basisimage? wäre etwas vollständig eigenes nicht besser?" | Ehrliche Analyse: selbst gebaut wäre **schlechter**; besser wäre nur ein Wechsel des Verfahrens (WebRTC). Empfehlung: KasmVNC vorerst behalten, WebRTC als eigener Meilenstein. |
| 29 | „notiere das mal für später. mein gedanke war ob es rechtlich ok ist kasm-vnc in ein eigenes image einzubauen" | Lizenz geprüft (**GPL-2+**, belegt im Paket selbst), in `THIRD-PARTY-NOTICES.md` und Wiki-Kapitel 13 dokumentiert, im Gedächtnis abgelegt. Ergebnis: erlaubt und **sauberer** als von `kasmweb/*` abzuleiten. |
| 30 | „so ich habe jetzt aufgeräumt … mach weiter mit den noch fehlenden punkten" | Gruppenlaufwerke, Passkeys, helles Gewand. Commit `10fa7ac`. |
| 31 | „was mir noch fehlt sind die app symbole der bereitgestellten apps" | Symbole aus den `.desktop`-Dateien, verkleinert, über eigene Adresse ausgeliefert. Commit `06018cb`. |
| 32 | **„lass uns an die alternative zu kasm-vnc gehen … bisheriger weg soll vollständig bestehen bleiben … eigener arbeitsplatz auf dem konto bmetallica … nicht auf main committen"** | Zweig `webrtc-viewer`, `ota/base-selkies:test`, Testarbeitsplatz für `bmetallica`. Commit `d2ad3ae`. |
| 33 | „bist du noch dran?" | Ja — Zwischenstand gemeldet, dann committet. |
| 34 | „Erstelle eine ausführliche HANDOVER.md" | Diese Datei. |

### ⚠️ Eine Fehlersuche, die lange gedauert hat — und warum

Nach der Umstellung auf Selkies als Vorgabe fielen **18 Prüfungen** aus. Die Meldung lautete
„Der Container-Dienst ist nicht erreichbar. Läuft ota-agent?" — und zeigte damit auf den
falschen Dienst. Der Agent war gesund.

Die Ursache stand auf dem Etikett eines sterbenden Containers: `ota.engine=selkies` auf einem
Image, das kein Selkies enthält. Die Prüfreihe legt Arbeitsplätze auf Kasm-Images an, ohne die
Maschine zu nennen; seit der Umstellung bekamen sie alle Selkies, und der Agent wartete
neunzig Sekunden auf einen Port, den dort niemand öffnet.

**Zwei Lehren, beide eingebaut:**

* Wer beim Anlegen nichts angibt, bekommt die Maschine, **die das Image mitbringt**
  (`SELKIES_HOME` in der Image-Konfiguration). Kein Raten, kein stiller Fehlgriff.
* Die Prüfreihen schrieben `/home/kasm-user` an 29 Stellen fest — genau den Pfad, den wir zur
  Eigenschaft des Images gemacht haben. Sie erfragen ihn jetzt aus dem Container (`$HOME`) und
  prüfen damit **beide** Wege statt einen davon vorauszusetzen.

Auf dem Weg dorthin habe ich zweimal die falsche Fährte verfolgt (volle Platte, Speichermangel)
und mir dreimal selbst Fehlschläge erzeugt: Dienste mitten im Lauf neu gestartet, Session-Container
aufgeräumt, deren Datenbankzeile noch `running` war, und mit `pkill -f` die eigene Shell erwischt.
**Während eines Laufs nichts anfassen.**

### ⚠️ Bekannte Bugs & Test-Status

* **Testergebnis:** `scripts/test-authz.sh` **216/216**,
  `scripts/build-desktop-image.sh --pruefen` **19/19**, `scripts/pruef-selkies.mjs` liefert ein
  Bild (1252 Einzelbilder, 1440×900), `scripts/pruef-turn.py` grün. Ein vollständiger `make test` steht weiterhin aus — `scripts/test-backup.sh` beendet
  Sitzungen, und auf dieser Maschine lief durchgehend ein Arbeitsplatz des Nutzers.
* **Zwei Fallen beim Prüfen, beide selbst gestellt:** Wer während eines Laufs Dienste neu startet,
  bekommt „Der Container-Dienst ist nicht erreichbar" und 16 Fehlschläge, die keine sind. Und wer
  Session-Container aufräumt, deren Datenbankzeile noch `running` ist, lässt den e2e auf einen
  toten Stream warten. **Während eines Laufs nichts anfassen.**
* **Älteres Ergebnis (vor der Umstellung):**
  `216 authz · 18 Zwischenablage · 107 e2e · 42 ldap · 36 Sicherung (2 Fehler)` = **419 von 421**
* **Fehlermeldung:** `✗ Pfad im Archiv stimmt nicht` und `✗ Markierung fehlt nach dem Zurückspielen` in `scripts/test-backup.sh`
* **Vermutete Ursache — und was daraus wurde:** Kein Produktfehler, sondern ein **Testartefakt**. `/api/backups/run` sichert **jede** laufende Sitzung; die Prüfung griff sich „die erste Container-Sicherung". Während des Laufs lief unter demselben Konto zusätzlich meine Selkies-Sitzung, also war es die falsche. Mit zwei Streaming-Maschinen sind zwei Sitzungen je Konto der Normalfall, deshalb wählt die Prüfung die Sicherung jetzt über die Vorlage aus.
  **Nach der Korrektur: `test-backup.sh` allein → 38/38 grün.** Ein vollständiger `make test` **nach** dieser Korrektur steht noch aus — das ist der erste Schritt unten.
* **Weitere offene Kleinigkeiten:**
  * `kasmweb/gimp:1.18.0-rolling-daily` (Vorlage `gimp`) liegt nicht mehr lokal — beim Start würde OTA versuchen, es zu holen.
  * Die Vorlage `neuer-arbeitsplatz` zeigt auf eine fremde Registry (`192.168.66.12:5000`), die nicht erreichbar sein muss.
  * Selkies: der Medienweg ist gemessen, aber noch nicht im Browser bestätigt.

---

## 🚀 NÄCHSTE ARBEITSSCHRITTE (BACKLOG FÜR DEN AGENTEN)

1. **Vollständigen `make test` fahren** und bestätigen, dass alle fünf Reihen grün sind (die Sicherungsprüfung wurde gehärtet, aber nur allein gegengeprüft). Erwartung: 421/421.
2. **Selkies messen, bevor irgendetwas daran entschieden wird.** Konkret:
   * Latenz und Bildqualität gegen KasmVNC, auf denselben Inhalten, im selben Netz
   * CPU-Last je Sitzung (x264 in Software, die Maschine hat keine GPU)
   * Trägt „ein Bildschirm je Sitzung" den Alltag, oder fehlt der Anwendungsumschalter?
   Ohne diese Zahlen keine Entscheidung für oder gegen den Weg.
3. **Wenn Selkies bleibt:** eine eigene Prüfreihe für den Selkies-Weg und ein Umschalter in der Oberfläche für `stream_engine`. (Die Portvergabe je Sitzung stand hier und hat sich erledigt: Der TURN ist ein gemeinsamer Dienst geworden.)
4. **Branding** (eigenes Logo/Farben je Anlage) — klein, gut machbar, rein Frontend.
5. **code-server** als leichte Engine für reine Editor-Sessions (Extensions über Open VSX) — überschneidet sich stark mit dem, was der Arbeitsplatz kann; erst bauen, wenn jemand es braucht.
6. **Guacamole-Engine** für RDP/VNC-Ziele — eigener Meilenstein mit eigener Abnahme.
7. **Netzlaufwerke / Kerberos (M6)** — braucht ein KDC und einen Dateiserver, hier nicht ehrlich prüfbar. **Passwort-Durchreichung bleibt draussen.**
8. **Mehrere Hosts (M10)** — braucht eine zweite Maschine.

**Ausdrücklich nicht anfassen:** Firefox-Erweiterung signieren (vom Nutzer ausgenommen), GPU-Durchreichung (keine GPU vorhanden).

---

## 📋 CODE-STYLE & AGENTEN-REGELN (CONSTRAINTS)

**Sprache**
* **Alle** Kommentare, Docstrings, Commit-Nachrichten, Fehlermeldungen und Dokumente auf **Deutsch**. Ausnahme: `README.en.md`.
* Bezeichner im Code auf Deutsch, wo sie fachlich sind (`verweis_setzen`, `laufende_session`, `Symbol`), englisch wo technisch üblich.
* **Kommentare erklären das Warum.** Bei behobenen Fehlern gehören Datum und das konkrete Fehlerbild hinein.
* In Python-Dateien im Agent/API stehen Umlaute in Kommentaren teils als `ae/oe/ue` — beides kommt vor, halte dich an die jeweilige Datei.

**Oberfläche**
* Neue sichtbare Texte **immer** über `t('deutscher Text')` **und** einen Eintrag in `web/src/lib/i18n.en.ts`.
* Handgeschriebenes CSS in `web/src/styles/app.css`, über **Merkmale** (`var(--…)`). **Keine Festfarbe in einer Regel** — sonst bleibt sie beim Gewandwechsel stehen.
* `useLang()` in jeder Ansicht, die übersetzten Text zeigt.

**Datenbank**
* Neue Spalten werden von `api/ota/schema_sync.py` beim Start **automatisch ergänzt** (nur Hinzufügen, nie Entfernen/Ändern). Für alles darüber hinaus: Alembic in `api/migrations/`.
* Neue Spalten brauchen `server_default`, damit Bestandszeilen nicht NULL sind — oder einen `BeforeValidator` im Schema (siehe `Symbol` in `schemas.py`).

**Tests**
* Neue Funktion → neue Prüfung in der passenden Reihe. Reihen sind Bash mit `ok`/`bad`/`expect`.
* **Nie `echo "$X" | grep -q`** in den Prüfreihen — `set -o pipefail` liefert dann 141 (SIGPIPE) auch bei Treffern. Stattdessen Here-Strings (`grep -q muster <<<"$X"`).
* Nie „den ersten Container aus `docker ps`" nehmen — immer den der geprüften Sitzung/des Kontos.
* Warten auf Zustände, nicht auf feste Zeiten (`for i in $(seq …); do … done`).
* Ein Testlauf hinterlässt **nichts** im Katalog (siehe `finally`-Block in `tests/e2e.mjs`).

**Sicherheit**
* Keine Geheimnisse in Dateien im Repo. `deploy/.env` ist gitignored.
* Fremde Daten (Bilder aus Paketen, Eingaben aus dem Browser) werden in der **API** verarbeitet, nie im Agent.
* Wessen Ablage/Profil es ist, kommt **nie aus der Anfrage**, sondern aus dem Cookie — und zwar als Kennung, nicht als Name.

**Shell/Dockerfiles**
* Kein `|| true` am Ende einer Installationskette.
* Ein Skript, das im Hintergrund laufen soll, bekommt `&` — verlass dich nicht auf ein `-fork`-Versprechen.

---

## ⚡ QUICKSTART FÜR DEN AGENTEN

```bash
cd /opt/openterminalapps

# --- Stand ---------------------------------------------------------------
git status -sb                 # aktuell: webrtc-viewer (Selkies-Versuch)
git checkout main              # der produktive Stand ohne den Versuch

# --- Anlage starten / neu bauen -----------------------------------------
make setup                     # nur beim ersten Mal: .env, Zertifikate, Verzeichnisse
make up                        # alles hoch
make identity                  # Keycloak-Realm einrichten (idempotent)
docker compose -f deploy/docker-compose.yml --env-file deploy/.env \
  up -d --build api agent web  # nach Codeänderungen

# --- Prüfen (Zugangsdaten kommen aus deploy/.env) ------------------------
set -a && . deploy/.env && set +a && export OTA_TEST_ADMIN_PW
make test                      # alle fünf Reihen, ~12 Minuten
./scripts/test-authz.sh        # nur die Autorisierungsreihe (216 Prüfungen)
cd tests && node e2e.mjs       # nur der Browsertest (107 Prüfungen)

# --- Images --------------------------------------------------------------
./scripts/build-base-image.sh --pruefen        # ota/base-xfce:test, 29 Punkte
OTA_PRUEFE_JAVA=1 ./scripts/build-base-image.sh --nur-pruefen   # + Abnahmefall 7
scripts/build-desktop-image.sh --pruefen                        # Basisimage bauen und messen
make sbom                                       # Stückliste je Image

# --- Nützlich ------------------------------------------------------------
make ps ; make logs
docker exec ota-db psql -U ota -d ota -c "SELECT slug, stream_engine FROM templates"
```

**Adressen:** Oberfläche `https://192.168.66.224:8443` (auch `https://ota.boden.home` hinter dem Reverse Proxy) · Notzugang `/notfall` · Keycloak `/auth`.
**Konten:** `notfall` (lokal, Notzugang) und `bmetallica` (über Keycloak). **Passwörter stehen in `deploy/.env`, nicht hier.**

---
**ENDE DER ÜBERGABE. Du bist nun bereit. Antworte mit einer kurzen Zusammenfassung, was du als Erstes tun wirst, um zu bestätigen, dass du den Kontext verstanden hast.**
---
