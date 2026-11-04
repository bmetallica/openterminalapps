# 39 · Erweiterungen ✅

*Für Administratoren. Seit dem 2026-11-02.*

Eine **Erweiterung** ist eine eigenständige Docker-Anwendung mit eigenem Compose-Projekt, die OTA
in die Arbeitsplätze einbindet. Die erste ist das **Gedächtnis für opencode**
([github.com/bmetallica/plugin_ota-opencode](https://github.com/bmetallica/plugin_ota-opencode)):
Jede opencode-Sitzung bekommt ein Langzeitgedächtnis, das Zusammenfassungen des Verlaufs und
spätere Fortsetzungen übersteht.

OTA übernimmt dabei:

- **Koppeln**, ein Mal je Erweiterung.
- **Einschalten** für Gruppen.
- Je berechtigtem Arbeitsplatz ein **eigenes Token**. Es wird beim Start ausgestellt und endet mit
  dem Arbeitsplatz.
- Den **MCP-Server** für opencode und den **Schnipsel für den Systemprompt**
  ([Kapitel 38](38-opencode.md)).
- Die **Ansichten** der Erweiterung in OTA: unter **Mein Konto** und im Menü **⋯** der Kachel eines
  Arbeitsplatzes. Das Gedächtnis hat statt der Lasche unter Mein Konto einen eigenen Punkt in der
  Seitenleiste, **opencode · Erinnerungen**.
- Die **Ereignisse** im Leben eines Kontos: Sperren, Entsperren, Löschen.

Netz, Daten und Updates bleiben bei der Erweiterung.

## Wie es zusammenhängt

```
Arbeitsplatz ──http──▶ ota-erweiterungen:8091/<slug>/mcp ─▶ Traefik (im Sitzungsnetz)
                                                               │  nur Pfade aus dem Manifest
Browser ──https──▶ OTA /x/<slug>/ansicht/… ─▶ Traefik ─forwardAuth─▶ ota-api
                                                               │  signierte Kopfzeilen
ota-api ──Vertrag /ota/v1 (Dienstgeheimnis)──────────────────▶ │
                                                               ▼
                                              Erweiterung (Netz ota_erweiterungen)
```

- Das Netz **`ota_erweiterungen`** legt `make update` an, mit festem Bereich
  (`OTA_ERWEITERUNGEN_NETZ`, Vorgabe `10.98.0.0/24`). Darin hängen nur Traefik, die API und die
  Erweiterungen, nie ein Arbeitsplatz.
- **Aus den Arbeitsplätzen** führt nur der Eingang `erweiterungen` von Traefik (Port 8091) hin. Er
  ist nur in den Sitzungsnetzen erreichbar, nicht auf dem Host, und öffnet nur die Pfade, die die
  Erweiterung im Manifest nennt (beim Gedächtnis `/mcp`). Der Name `ota-erweiterungen` zeigt im
  Arbeitsplatz auf Traefik im eigenen Sitzungsnetz. Es braucht **keinen Hostport und keine
  Firewallregel**; das gilt auch beim Netzprofil „kein Firmennetz“.
- Dieser Weg ist **unverschlüsselt**. Das Sitzungsnetz enthält nur diesen einen Arbeitsplatz,
  seinen Router und Traefik, und das Token gilt nur für diesen Arbeitsplatz.
- **Aus dem Browser** führt nur `/x/<slug>/ansicht/…` unter OTAs eigener Adresse hin. Traefik fragt
  vorher die API (forwardAuth). Die API prüft die Anmeldung und reicht die Kennung des Menschen und
  seine Arbeitsplätze in Kopfzeilen weiter, signiert mit dem Dienstgeheimnis. Kopfzeilen, die der
  Browser selbst schickt, ersetzt Traefik.
- **Den Vertrag** (`/ota/v1/…`) ruft nur die API, aus dem Netz `ota_erweiterungen`. Weder aus dem
  Arbeitsplatz noch aus dem Browser ist er erreichbar.

## Eine Erweiterung installieren: das Gedächtnis

Auf dem OTA-Host, neben OTA:

```bash
cd /opt
git clone https://github.com/bmetallica/plugin_ota-opencode.git
cd plugin_ota-opencode
./setup.sh                    # legt .env an und zeigt den Kopplungsschlüssel
docker compose up -d --build
```

Dann in OTA unter **Einstellungen → Erweiterungen → Erweiterung koppeln**:

1. Die **Adresse** eintragen, `http://ota-gedaechtnis:8080`, und den **Kopplungsschlüssel** aus
   `setup.sh`. Er steht auch in der `.env`.
2. **Koppeln**. OTA holt das Manifest und hinterlegt bei der Erweiterung ein eigenes
   Dienstgeheimnis. Den Kopplungsschlüssel braucht OTA danach nicht mehr; erneutes Koppeln geht mit
   demselben Schlüssel.
3. **Einstellen**: Das Formular bringt die Erweiterung selbst mit. Beim Gedächtnis sind das:
   - der Embedding-Server: Adresse mit `/v1`, Modell, gegebenenfalls Schlüssel und Präfixe;
   - Ablauf, Kontingente und „Vor dem Speichern fragen“.

   **Testen** fragt den Embedding-Server.
4. Unter **Wer darf** die Gruppen wählen und **Eingeschaltet** umlegen.

Voraussetzung ist, dass **opencode eingeschaltet** ist ([Kapitel 38](38-opencode.md)). Es gilt ab
dem nächsten Start oder Fortsetzen eines Arbeitsplatzes, die Ansichten sofort.

**Embeddings**, für die Suche nach Bedeutung statt nur nach Wörtern: Jeder Server mit
OpenAI-Schnittstelle (`/v1/embeddings`) geht.

| Server | Adresse | Modell | Präfixe |
|---|---|---|---|
| vLLM | `http://<host>:8000/v1` | z. B. `BAAI/bge-m3` | leer |
| llama.cpp (auch hinter llama-swap) | `http://<host>:8080/v1` | z. B. `nomic-embed-text` | Eintrag `search_document: `, Suche `search_query: ` |

Ohne Embedding-Server sucht das Gedächtnis nur nach Wörtern. Fällt der Server aus, speichert es
trotzdem und bettet später nach.

## Was die Menschen sehen

- **In opencode** die Werkzeuge `memory_recall`, `memory_search`, `memory_save`, `memory_update`
  und `memory_forget`, dazu `document_search` und `document_list` für die Dokumente (unten). Jede Sitzung sieht nur ihr eigenes Gedächtnis; Unteragenten und Forks teilen
  das ihrer Wurzelsitzung.
- **opencode · Erinnerungen** in der Seitenleiste (bis 2026-11-04 unter Mein Konto): alle Sitzungen, nach Arbeitsplatz gegliedert. Dort lassen sich
  Einträge lesen, bearbeiten, anheften, löschen, neu anlegen und in andere Sitzungen kopieren oder
  verschieben. Eine Sitzung kann außerdem **Zugriff auf das Gedächtnis einer anderen** bekommen:
  Sie liest es dann mit, nur lesend und nicht weiter über deren eigene Zugriffe. Außerdem gibt es den Export als JSON und Markdown und „alles löschen“.
- **Hauptgedächtnis**, ganz oben in der Liste: Einträge, die **alle** Sitzungen dieses Menschen
  mitlesen, auch künftige. Nur er pflegt es, hier in OTA; opencode liest es nur und weist Ändern,
  Löschen und Speichern dorthin ab. Angeheftetes bekommt jede Sitzung bei jedem Abruf
  (`memory_recall`), alles andere findet sie über `memory_search`. So füllt ein großes
  Hauptgedächtnis nicht jeden Sitzungsstart. Es läuft nicht ab. Einträge aus einer Sitzung lassen
  sich hineinkopieren.
- **⋯ → Gedächtnis (opencode-Sitzungen)** auf der Kachel: dasselbe für die Sitzungen dieses
  Arbeitsplatzes, ohne das Hauptgedächtnis.
- **Dokumente**, unter dem Hauptgedächtnis: eine Bibliothek je Mensch. Hochladen per Ziehen oder
  Klicken: PDF mit Textschicht, DOCX, XLSX, PPTX, ODT, ODS, ODP, HTML, TXT, MD, CSV und andere
  Textdateien.
  - Ausgelesen wird im Hintergrund und in einem eigenen Prozess mit Zeit- und Speichergrenze.
    Office-Dateien, die entpackt zu groß würden (ZIP-Bomben), werden abgelehnt.
  - Gescannte PDFs ohne Textschicht werden mit Hinweis abgelehnt, eine Texterkennung gibt es nicht.
    Die alten Formate `.doc`, `.xls` und `.ppt` gehen nicht, bitte als `…x` oder PDF speichern.
  - **Zugangsdaten** im Text werden beim Auslesen durch `[entfernt]` ersetzt, die Ansicht nennt
    die Zahl der Stellen. Das Original bleibt unverändert und lässt sich herunterladen.
  - **Freigeben:** auf der Seite einer Sitzung unter „Dokumente für diese Sitzung“ anhaken, oder
    am Dokument „für alle Sitzungen“ (auch künftige).
  - **In opencode** durchsucht `document_search` die freigegebenen Dokumente und nennt die Quelle
    (Dokument, Seite, Überschrift oder Tabellenblatt), `document_list` zeigt, was freigegeben ist.
    Der Systemprompt sagt opencode, dass es bei Fragen, die nicht diese Sitzung betreffen, zuerst
    dort suchen soll.
  - **Grenzen** in den Einstellungen der Erweiterung: MB je Datei (Vorgabe 25) und MB je Mensch
    (Vorgabe 1024, Originale und Text zusammen).
  - Die Originale liegen in der Datenbank der Erweiterung. Damit sind sie in OTAs Sicherung, und
    mit dem Konto oder „alles löschen“ sind sie weg.

Mehr für die Menschen steht in [Kapitel 33](33-entwickeln.md#opencode-und-sein-gedächtnis-).

## Datenschutz

- **Admins lesen keine Inhalte.** Auch die Ansicht zeigt jedem nur sein Eigenes. Unter
  Einstellungen gibt es nur Zahlen (**Zahlen**: Menschen, Sitzungen, Einträge, Speicherbedarf).
- **Trennung zwischen Menschen** setzt die Datenbank der Erweiterung selbst durch (Row Level
  Security), nicht nur der Code.
- **Zugangsdaten** weist das Gedächtnis beim Speichern zurück: Schlüssel, Tokens, Passwörter in
  Adressen.
- **Ablauf:** Sitzungen ohne Aktivität werden nach der eingestellten Zahl von Tagen gelöscht,
  Vorgabe 180.
- **Kontolöschung:** Wird ein Konto in OTA gelöscht, löscht die Erweiterung alle seine Daten. Ist
  sie gerade nicht erreichbar, wiederholt OTA den Auftrag alle 15 Minuten, bis sie ihn bestätigt.
  In älteren Sicherungen liegen die Daten bis zu deren Ablauf.
- **Sperren:** Deaktivieren, Sperren und der Entzug der Gruppe sperren den Menschen in der
  Erweiterung; Tokens und Ansicht gehen dann nicht mehr, die Daten bleiben.

## Lebenszyklus

| Ereignis | In der Erweiterung |
|---|---|
| Arbeitsplatz startet oder wird fortgesetzt | neues Token. Ein älteres desselben Arbeitsplatzes wird widerrufen |
| Arbeitsplatz endet, hält an, Aufräumer | Token widerrufen; die Einträge bleiben |
| alle 15 Minuten | Abgleich: Tokens von Arbeitsplätzen, die nicht mehr laufen, werden widerrufen. Dazu Sperren abgleichen, offene Aufträge wiederholen, Routen neu schreiben |
| jede Minute | Gesundheit. Hat die Erweiterung eine neue Version, holt OTA ihr Manifest neu |
| Konto gelöscht | alle Daten gelöscht (siehe oben) |
| entkoppelt | Tokens widerrufen, Routen weg; die Daten bleiben in der Erweiterung |

**Ein Arbeitsplatz scheitert nie an einer Erweiterung.** Antwortet sie beim Start nicht innerhalb
von 3 Sekunden, startet er ohne sie, und unter Einstellungen steht der Fehler.

## Betrieb des Gedächtnisses

- **Update:** im Verzeichnis der Erweiterung `make update`, also `git pull` und Neubau. Die Daten
  bleiben im Volume `ota_gedaechtnis_daten`.
- **Sicherung:** OTAs Sicherungslauf (mit „Datenbank sichern“, [Kapitel 14](14-sicherung.md))
  holt sie über den Vertrag ab und legt sie unter
  `/srv/ota/backups/erweiterungen/gedaechtnis/<Zeit>/gedaechtnis.dump` ab, `pg_dump` im
  Custom-Format; Aufbewahrung wie bei den übrigen Sicherungen. Wiederherstellen von Hand:

  ```bash
  docker exec -i ota-gedaechtnis-db pg_restore -U gedaechtnis -d gedaechtnis --clean --if-exists \
    < /srv/ota/backups/erweiterungen/gedaechtnis/<Zeit>/gedaechtnis.dump
  docker restart ota-gedaechtnis
  ```
- **Entfernen:** in OTA entkoppeln, dann `docker compose down`. Erst `docker volume rm
  ota_gedaechtnis_daten` löscht die Daten.
- **Protokoll:** `docker logs ota-gedaechtnis`. Es enthält keine Inhalte und keine Tokens.

## Selbst eine Erweiterung bauen

Der Vertrag, den OTA spricht (Schnittstelle 1), mit dem Dienstgeheimnis als Bearer außer bei
`manifest` und `koppeln`:

| Aufruf | Zweck |
|---|---|
| `GET /ota/v1/manifest` | Kennung (`slug`, a–z/0–9), Name, Version, `pfade_fuer_arbeitsplaetze`, `liefert` (`opencode.mcp`, `opencode.plugin`, `prompt`), `ansichten` (`ort`: `konto` oder `arbeitsplatz`, Pfad unter `/ansicht/`), `konfiguration` (JSON-Schema; `x-geheim` für Geheimnisse) |
| `POST /ota/v1/koppeln` | `{kopplungsschluessel, dienstgeheimnis}` |
| `GET /ota/v1/gesund` | `{ok, version, …}` |
| `GET`, `PUT /ota/v1/konfiguration` | die Werte des Formulars; Geheimnisse nie zurückgeben, nur `<name>_gesetzt` |
| `POST /ota/v1/testen` | frei, für den Knopf „Testen“ |
| `POST /ota/v1/arbeitsplatz` | `{arbeitsplatz_id, arbeitsplatz_name, nutzer:{id,name,anzeigename}, gruppen, vorlage, root}` → `{token, mcp_pfad, opencode_plugin, opencode_fragen, prompt}` |
| `DELETE /ota/v1/arbeitsplatz/{id}` | Token widerrufen |
| `GET /ota/v1/arbeitsplaetze` | `{arbeitsplaetze: [ids]}` mit gültigem Token |
| `POST /ota/v1/nutzer/{id}/sperren`, `/entsperren`, `/loeschen` | Ereignisse eines Kontos |
| `GET /ota/v1/statistik` | Zahlen für Admins |
| `GET /ota/v1/sicherung` | ein Datenstrom, den OTAs Sicherungslauf ablegt (wenn das Manifest `sicherung: true` sagt) |

Die Ansichten prüfen die Kopfzeilen `X-OTA-Nutzer`, `X-OTA-Name`, `X-OTA-Arbeitsplaetze`
(Komma-getrennt), `X-OTA-Zeit` und `X-OTA-Signatur`. Die Signatur ist ein HMAC-SHA256 mit dem
Dienstgeheimnis über `nutzer|name|arbeitsplaetze|zeit`, gültig fünf Minuten. Fremden Plugin-Code
nimmt OTA nicht an: `opencode_plugin` nennt nur Plugins aus dem Paket `ota-opencode`.

## Wenn etwas nicht geht

| Was | Ursache |
|---|---|
| Koppeln: „antwortet nicht“ | Die Erweiterung ist nicht im Netz `ota_erweiterungen` (gibt es erst nach `make update`) oder läuft nicht: `docker ps`, `docker logs ota-gedaechtnis` |
| Koppeln: 403 | Falscher Kopplungsschlüssel: `grep KOPPLUNG .env` im Verzeichnis der Erweiterung |
| opencode: „Memory not set up: the OTA plugin did not provide the session“ | opencode lief nicht in OTAs Fassung oder ohne OTAs Konfiguration (eigene Installation vor der Übernahme, Arbeitsplatz noch nicht neu gestartet) |
| opencode: „invalid or revoked token“ | Der Arbeitsplatz wurde fortgesetzt, opencode lief aber weiter: opencode neu starten |
| Kein Punkt „opencode · Erinnerungen“ in der Seitenleiste | Erweiterung aus, oder der Mensch ist nicht in einer berechtigten Gruppe |
| Suche findet Sinnverwandtes nicht | Embedding-Server prüfen (**Testen**); bei nomic-embed-text die Präfixe setzen |
