# 38 · opencode: der KI-Assistent im Terminal ✅

*Für Administratoren. Seit dem 2026-11-02.*

[opencode](https://opencode.ai) (MIT) ist ein KI-Assistent für das Terminal: Er liest und ändert
Code, führt Befehle aus und arbeitet in Sitzungen, die sich später fortsetzen lassen. OTA bringt ihn
in jeden berechtigten Arbeitsplatz und verbindet ihn mit **eurem eigenen KI-Server**, denselben,
den IDE-AI nutzt ([Kapitel 28](28-ide-ai.md)).

Was OTA dabei übernimmt:

- **Installation**: OTA liefert das Paket `ota-opencode` aus der eigenen Paketquelle. Bei jedem
  Start und Fortsetzen hebt es den Arbeitsplatz auf die festgelegte Fassung, auch ohne Weg ins
  Internet. opencodes eigene Selbstaktualisierung ist aus.
- **Konfiguration**: OTA schreibt opencodes **verwaltete Konfiguration**. Darin stehen der
  KI-Server, die Modelle, das Standardmodell, der Prompt-Zusatz und die MCP-Server der
  Erweiterungen.
- **Prompt-Zusatz**: ein Text, der bei jeder Anfrage an das Modell mitgeht, global und je Gruppe.
- **Erweiterungen**: Was eine Erweiterung für opencode liefert, kommt mit. Ein Beispiel ist das
  Gedächtnis ([Kapitel 39](39-erweiterungen.md)).

## Einschalten

Unter **Einstellungen → opencode**:

1. Unter **IDE-AI** müssen der KI-Server und mindestens ein Modell eingetragen sein. opencode
   nutzt dieselben, mit Kontextfenster und Antwortlänge. IDE-AI selbst muss dafür nicht
   eingeschaltet sein.
2. Bei Bedarf **Standardmodell** und **kleines Modell** wählen. Das kleine Modell erzeugt Titel und
   Zusammenfassungen; ein schnelles Modell ohne Denken spart dabei Wartezeit.
3. Bei Bedarf einen **Zusatz zum Systemprompt** eintragen und unter **Wer darf** die Gruppen wählen.
4. Den Schalter **opencode** umlegen.

Es gilt ab dem **nächsten Start oder Fortsetzen** eines Arbeitsplatzes. Solange opencode oder
IDE-AI an ist, gibt die Firewall den KI-Server für alle Arbeitsplätze frei.

Das Paket baut `make update` von selbst, sobald die Fassung in der Paketquelle fehlt. Von Hand
geht es mit `scripts/build-opencode-deb.sh --hochladen`. Die Fassung steht in
`packaging/ota-opencode/quellen`.

## Die Einstellungen

| Einstellung | Was sie bewirkt |
|---|---|
| Standardmodell | Das Modell, mit dem opencode startet. Leer bedeutet: das Standardmodell aus IDE-AI. Wer in `~/.config/opencode` selbst eines gesetzt hat, behält es |
| Kleines Modell | Für Titel und Zusammenfassungen (`small_model`). Leer bedeutet: wie das Standardmodell |
| Zusatz zum Systemprompt | Geht bei jeder Anfrage mit, für alle. Platzhalter: `{anzeigename}`, `{nutzer}`, `{vorlage}`, `{datum}` |
| Je Gruppe | Zusätzliche Texte für Mitglieder bestimmter Gruppen, etwa ein Styleguide. Wer in mehreren Gruppen ist, bekommt alle |
| Zusätzliche Konfiguration | JSON, das OTA in die verwaltete Konfiguration einmischt und das Vorrang hat. Gedacht für alles, was die Oberfläche nicht kennt (siehe unten). `mcp`, `plugin` und `instructions` setzt OTA selbst |
| Wer darf | Ohne Gruppe dürfen alle. Sonst nur Mitglieder dieser Gruppen; Administratoren immer |
| Vorschau | Zeigt, was ein bestimmter Mensch bekäme: den Prompt-Zusatz mit geschätzter Länge und die verwaltete Konfiguration. Berücksichtigt auch noch nicht gespeicherte Änderungen |

**Länge des Prompt-Zusatzes:** Der Zusatz kostet bei jeder Anfrage Kontext. Ab etwa 2 000 Tokens
warnt die Vorschau, denn bei lokalen Modellen mit 32 k oder weniger Kontext fällt das ins Gewicht.

**Eine Vorgabe, keine Sicherheitsgrenze:** Ein Projekt kann eigene Anweisungen mitbringen
(`AGENTS.md` im Repository), und das Modell kann sich über Anweisungen hinwegsetzen. Was wirklich
nicht sein darf, regeln die Firewall und die Rechte, nicht der Prompt.

Jede Änderung am Prompt-Zusatz und an der zusätzlichen Konfiguration kommt mit altem und neuem
Text ins Audit-Log.

### Zusätzliche Konfiguration: Beispiel

Für einen llama.cpp-Server mit einem denkenden Hauptmodell und einer Fassung ohne Denken für
Titel und Zusammenfassungen sieht das zum Beispiel so aus:

```json
{
  "provider": { "ota": { "models": {
    "Hauptmodell": { "reasoning": true, "modalities": { "input": ["text", "image"], "output": ["text"] } },
    "Hauptmodell-nothink": { "options": { "chat_template_kwargs": { "enable_thinking": false } } }
  } } },
  "agent": {
    "compaction": { "model": "ota/Hauptmodell-nothink" },
    "title": { "model": "ota/Hauptmodell-nothink" }
  }
}
```

Der Anbieter heißt in opencode immer `ota`, ein Modell also `ota/<Modell>`. Es müssen Modelle
sein, die unter IDE-AI ausgewählt sind.

## Im Arbeitsplatz

Bei jedem Start und Fortsetzen schreibt OTA als root:

| Datei | Inhalt |
|---|---|
| `/etc/opencode/opencode.jsonc` | die verwaltete Konfiguration. Die erste Zeile ist OTAs Marke |
| `/etc/opencode/ota-anweisungen.md` | der Prompt-Zusatz: global, die Gruppen des Menschen, die Schnipsel der Erweiterungen |
| `/etc/opencode/ota-ki-schluessel` | der API-Schlüssel des KI-Servers, nur wenn einer eingetragen ist |
| `/etc/ota/erweiterungen/<slug>/token` | das Token je Erweiterung, siehe [Kapitel 39](39-erweiterungen.md) |
| `/etc/hosts` | `ota-erweiterungen` zeigt auf Traefik im eigenen Sitzungsnetz |

**Vorrang:** opencode liest `/etc/opencode` mit dem höchsten Vorrang. Was ein Mensch in
`~/.config/opencode/opencode.json` einstellt, kommt dazu: eigene Anbieter, eigene MCP-Server,
eigene Plugins, eigene Rechte. Die Schlüssel, die OTA setzt, kann er dort nicht überschreiben.
Eine Ausnahme ist das Standardmodell: Hat jemand selbst eines gesetzt, schreibt OTA keines vor.

**Eine verwaltete Konfiguration des Images**, also `/etc/opencode/opencode.json` ohne OTAs Marke,
bleibt unangetastet. OTA schreibt dann keine eigene und meldet das im Protokoll des Agenten.

**Ausschalten** oder Entzug der Berechtigung entfernt beim nächsten Start OTAs Dateien. Das Paket
bleibt; opencode läuft danach nur mit der eigenen Konfiguration des Menschen.

## Wer opencode schon selbst installiert hat

Gerade in Root-Arbeitsplätzen haben manche opencode schon selbst installiert, mit dem
Installationsskript (`~/.opencode/bin`), mit npm (`/usr/local/bin`) oder mit Bun. Beim nächsten
Start oder Fortsetzen **übernimmt** OTA diese Installation:

- Die Datei wird zu `opencode.vor-ota` umbenannt, gelöscht wird nichts.
- An ihre Stelle tritt ein kleines Skript, das OTAs Fassung startet (`/usr/bin/opencode`). So läuft
  immer die geprüfte Fassung, egal was im `PATH` vorne steht.
- Bleiben unverändert: die eigene Konfiguration in `~/.config/opencode`, die bisherigen Sitzungen
  in `~/.local/share/opencode` und ein eigenes Standardmodell.
- Installiert jemand später neu, ersetzt das nur das Skript. Beim nächsten Start übernimmt OTA
  wieder.

**Warum das nötig ist:** Das Plugin `ota-sitzung` (siehe unten) hängt an opencodes
Plugin-Schnittstelle, und die ändert sich zwischen Fassungen. Eine andere Fassung als die
festgelegte könnte die Erweiterungen still brechen.

## Das Plugin ota-sitzung

Das Paket bringt ein kleines Plugin mit (`/usr/share/ota-opencode/plugins/ota-sitzung`). OTA
schaltet es nur ein, wenn eine Erweiterung es braucht. Vor jedem Aufruf eines Werkzeugs dieser
Erweiterung setzt es die **opencode-Sitzung** ein:

- Kind-Sitzungen (Unteragenten) und Forks werden auf ihre Wurzelsitzung abgebildet, nach derselben
  Regel, die opencode intern nutzt.
- Dazu kommen Titel und Verzeichnis der Sitzung, nur für die Anzeige.
- Für das Modell blendet es diese Felder aus; was das Modell dort einträgt, wird überschrieben.
- Es schickt selbst nichts irgendwohin.

So weiß etwa das Gedächtnis zuverlässig, zu welcher Sitzung ein Eintrag gehört, ohne dass sich das
Modell eine Kennung merken muss.

## Eine neue Fassung von opencode

1. In `packaging/ota-opencode/quellen` Fassung, Adresse und Prüfsumme ändern und `revision` auf 1
   setzen.
2. `scripts/build-opencode-deb.sh --hochladen`
3. `scripts/test-opencode.sh` prüft unter anderem das Plugin mit der neuen Fassung, mit einem
   Fake-Modell im Arbeitsplatz.

## Wenn etwas nicht geht

| Was | Ursache |
|---|---|
| opencode fehlt im Arbeitsplatz | Das Paket installiert sich im Hintergrund, beim ersten Start ein, zwei Minuten. Ohne `dpkg` im Image geht es nicht; dann von Hand installieren, die Konfiguration gilt trotzdem |
| Die Modelle von OTA fehlen | `/etc/opencode/opencode.jsonc` prüfen. Fehlt es, steht im Protokoll des Agenten eine eigene verwaltete Konfiguration des Images (`gehört dem Image`) |
| `opencode` startet eine alte Fassung | Die Übernahme läuft beim Start und Fortsetzen. Bis dahin hilft `/usr/bin/opencode` |
| Fehler bei Werkzeugaufrufen | Der KI-Server muss Werkzeugaufrufe beherrschen: vLLM `--enable-auto-tool-choice --tool-call-parser …`, llama.cpp `--jinja` |
| Ein eigenes Modell aus `~/.config/opencode` wird ignoriert | Nur das Standardmodell bleibt dem Menschen; die Modellliste des Anbieters `ota` setzt OTA. Ein eigener Anbieter mit anderem Namen geht |

Test: `scripts/test-opencode.sh`, zusammen mit dem Gedächtnis aus [Kapitel 39](39-erweiterungen.md).
