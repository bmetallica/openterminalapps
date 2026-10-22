# 28 · IDE-AI: KI-Assistent in VS Code, VSCodium und PyCharm ✅

*Für Administratoren. Seit dem 2026-10-22.*

IDE-AI bringt einen KI-Assistenten in die Editoren der Arbeitsplätze, verbunden mit **eurem eigenen
KI-Server**. Dahinter steckt [Continue](https://continue.dev) (Apache-2.0):

- **Chat** rechts in der Seitenleiste, wo VS Code sonst seinen Chat hat, mit Auswahl des Modells,
- **Bearbeiten** markierten Codes,
- **Agent-Modus**: Das Modell liest und ändert Dateien und schlägt Befehle vor, jeweils mit
  Bestätigung,
- auf Wunsch **Vervollständigung beim Tippen**.

Der KI-Server muss die OpenAI-Schnittstelle sprechen (`/v1/chat/completions`). Das können **vLLM**,
**llama.cpp** (auch hinter llama-swap), Ollama und LiteLLM.

Warum Continue und kein eigenes Plugin: Ein eigenes Plugin hieße zwei Codebasen (VS Code in
TypeScript, JetBrains in Kotlin), und alles, was über einen reinen Chat hinausgeht, wäre Arbeit für
Monate. Continue kann das, lässt sich vollständig über eine Datei einstellen und läuft in allen drei
Editoren.

## Einschalten

Unter **Einstellungen → IDE-AI**:

1. **Adresse des KI-Servers** eintragen, mit `/v1`, z. B. `http://192.168.1.2:3000/v1` (vLLM) oder
   `http://192.168.1.3:8080/v1` (llama.cpp). Ohne Pfad ergänzt OTA `/v1`.
2. **Modelle abrufen**. OTA fragt den Server nach `/v1/models`.
3. In der Tabelle die Modelle **anbieten**, die zur Auswahl stehen sollen, und das **Standardmodell**
   wählen. Für jedes Modell **Kontextfenster** und **Antwortlänge** in Tokens eintragen.
4. **Testen** schickt eine kurze Frage an das Modell und zeigt Antwort und Dauer.
5. **Speichern**, dann den Schalter **IDE-AI** einschalten.

Es gilt ab dem **nächsten Start oder Fortsetzen** eines Arbeitsplatzes. Laufende bleiben, wie sie
sind.

**Ausschalten** entfernt beim nächsten Start Continue wieder aus den Editoren und löscht OTAs
Konfiguration im Zuhause. Die Pakete bleiben im Arbeitsplatz liegen; ohne Verknüpfung tun sie nichts.

## Die Einstellungen

| Einstellung | Was sie bewirkt |
|---|---|
| Adresse des KI-Servers | Die OpenAI-Schnittstelle, mit `/v1` |
| API-Schlüssel | Nur, wenn der Server einen verlangt (`--api-key` bei vLLM und llama.cpp). Er verlässt OTA nie in Richtung Browser, steht aber in der Konfiguration im Zuhause |
| Modelle | Was die Menschen in Continue zur Auswahl haben, das Standardmodell zuerst |
| Kontextfenster | Wie viele Tokens Continue in eine Anfrage packt. Höchstens so viel, wie der Server zulässt: vLLM `--max-model-len`, llama.cpp `--ctx-size` geteilt durch `--parallel` |
| Antwortlänge | Höchstens so viele Tokens je Antwort (`max_tokens`). Muss kleiner sein als das Kontextfenster. Denkende Modelle brauchen mehr, weil die Überlegung mitzählt |
| Vervollständigung beim Tippen | Ein Modell, das beim Schreiben den Rest der Zeile vorschlägt, oder aus. Lohnt nur mit einem schnellen Modell |
| Werkzeuge (Agent-Modus) | Das Modell darf Dateien lesen und ändern und Befehle vorschlagen. Braucht Werkzeugaufrufe im Server (siehe unten) |
| Temperatur | Leer: was der Server vorgibt |
| Zeitlimit | Wie lange Continue auf eine Antwort wartet. llama-swap lädt ein Modell beim ersten Aufruf erst |
| Firmenproxy | Vorgabe: direkt zum KI-Server, auch wenn die Arbeitsplätze sonst über den Firmenproxy gehen ([Kapitel 21](21-firmenproxy.md)) |
| Regeln für das Modell | Hinweise bei jeder Anfrage, eine Zeile je Regel, z. B. „Antworte auf Deutsch.“ |
| Wer darf | Ohne Gruppe alle. Sonst nur Mitglieder dieser Gruppen; Administratoren immer |

**Werkzeugaufrufe im Server:**

- vLLM: `--enable-auto-tool-choice --tool-call-parser <parser>`, der Parser passend zum Modell
  (etwa `hermes` für Qwen).
- llama.cpp: `--jinja`.

Ohne sie bleibt der Chat nutzbar; dann **Werkzeuge** ausschalten.

## Was im Arbeitsplatz passiert

Bei jedem Start und Fortsetzen, als root:

1. **Konfiguration** nach `~/.continue/config.yaml`, sofort, vor dem ersten Öffnen des Editors.
   Dazu die Telemetrie von Continue aus (`~/.continue/index/globalContext.json`).
2. **Pakete**, im Hintergrund, damit der Start nicht wartet. Nur für Editoren, die es im Image gibt,
   und nur, wenn die Fassung aus der Paketquelle nicht schon installiert ist:

| Paket | Für | Wie verknüpft |
|---|---|---|
| `ota-ide-ai-vscode` | VS Code, VSCodium | als mitgelieferte Erweiterungen unter `resources/app/extensions/ota-continue` und `ota-ide-ai`, für alle Nutzer |
| `ota-ide-ai-jetbrains` | PyCharm, IntelliJ IDEA und jede andere JetBrains-IDE unter `/opt` | im Plugin-Verzeichnis des Zuhauses, `~/.local/share/JetBrains/<IDE><Fassung>/ota-continue` |

Der Agent holt die Paketdatei selbst aus der [eigenen Paketquelle](26-paketquellen.md) und spielt sie
mit `dpkg` ein. Deshalb kommt IDE-AI **in jedes Image mit dpkg**: Debian 13 wie Ubuntu und
Kasm-Images, auch in solche, in die OTA keine Paketquelle einträgt. Der Arbeitsplatz braucht dafür
keinen Weg ins Netz.

**Root-Arbeitsplätze** heben sich beim Fortsetzen auf die neueste Fassung, wie bei `ota-selkies`.

Wer neue Images baut, kann die Pakete gleich mitgeben (Verwaltung → Software, Paket
`ota-ide-ai-vscode` bzw. `ota-ide-ai-jetbrains`). Dann entfällt die Installation beim Start; nötig
ist das nicht.

Warum JetBrains im Zuhause: Neuere JetBrains-IDEs laden aus ihrem eigenen `plugins/` nur, was in der
vorberechneten `plugins/plugin-classpath.txt` steht. Ein Plugin daneben erscheint nicht einmal im
Protokoll (gemessen mit PyCharm 2026.2). Im Zuhause liegt nur die Verknüpfung, das Plugin selbst
bleibt mit rund 180 MB im Paket.

### Continue rechts, Copilot aus (VS Code, VSCodium)

- **Continue sitzt rechts** in der zweiten Seitenleiste, nicht links zwischen Explorer und Suche.
  Dafür ändert der Paketbau in Continues `package.json` den Platz (`viewsContainers.secondarySidebar`).
- **Die Leiste geht von selbst auf**, einmal je Ordner. Das erledigt OTAs kleine Erweiterung
  `ota-ide-ai` daneben: Von allein bliebe die Leiste zu, weil sie beim Start noch leer ist (Continue
  lädt erst danach) und VS Code eine leere Leiste schliesst. Wer sie zumacht, dem bleibt sie zu;
  `Strg+Alt+B` öffnet sie wieder.
- **Der eingebaute Copilot ist aus**, solange IDE-AI an ist. `ota-ide-ai` setzt dafür
  `chat.disableAIFeatures` als Vorgabe. Wer Copilot doch will, setzt die Einstellung in den eigenen
  Einstellungen auf `false`. Ist IDE-AI aus, entfernt OTA die Verknüpfung, und Copilot ist wieder da.
- Wer Continue woandershin zieht, behält diesen Platz.

## Die Konfiguration gehört OTA, bis jemand sie übernimmt

OTA schreibt `~/.continue/config.yaml` bei jedem Start neu. Die erste Zeile ist die Marke:

```yaml
# Verwaltet von OTA (IDE-AI). Änderungen hier überschreibt OTA beim nächsten Start.
# Wer die Datei selbst pflegen will, löscht diese erste Zeile.
name: OTA IDE-AI
models:
- name: Hauptmodell
  provider: openai
  model: Hauptmodell
  apiBase: http://192.168.66.225:8080/v1
  defaultCompletionOptions:
    contextLength: 65536
    maxTokens: 2048
```

**Wer die erste Zeile löscht, pflegt die Datei selbst.** OTA fasst sie danach nicht mehr an, auch
nicht beim Ausschalten. Wer zu OTAs Fassung zurück will, löscht die Datei; beim nächsten Start ist
sie wieder da.

Ausnahme: Die leere Datei, die Continue selbst anlegt, wenn es ohne Konfiguration startet
(`name: Main Config`, `models: []`), gehört niemandem. Die ersetzt OTA beim nächsten Start.

Welches Modell jemand gerade gewählt hat, merkt sich Continue selbst. Die Auswahl bleibt über
Neustarts erhalten.

## Netz und Firewall

Solange IDE-AI an ist, gibt die Firewall den KI-Server **für alle Arbeitsplätze** frei: Adresse
und Port aus der Einstellung, TCP. Ohne diese Freigabe sperrte die Stufe „internet“ einen Server im
privaten Adressbereich. Die Freigabe steht nicht in der Liste unter **Netz → Freigaben für alle Arbeitsplätze**,
weil sie sich aus dieser Einstellung ergibt; sie verschwindet mit dem Ausschalten.

Die Gruppen unter **Wer darf** bestimmen, wer Continue eingerichtet bekommt, nicht, wer den Server
erreicht. Wer den Server nur bestimmten Menschen öffnen will, gibt ihm einen API-Schlüssel.

Continue spricht den Server **aus dem Arbeitsplatz** an, nicht über OTA. Deshalb muss der
OTA-Host den Server erreichen können (die Arbeitsplätze gehen über seinen Router).

## Pakete und Fassungen

Die Pakete baut `scripts/build-ide-ai-deb.sh` aus den Dateien, die in `packaging/ota-ide-ai/quellen`
mit Fassung und Prüfsumme stehen:

| Datei | Herkunft |
|---|---|
| Continue für VS Code, Linux x64 | Open VSX (`Continue.continue`) |
| Continue für JetBrains | JetBrains Marketplace (Plugin 22707); ins Paket kommt nur Linux x64 |

`make update` baut sie und legt sie in die Paketquelle, wenn die Fassung dort fehlt. Beim ersten Mal
holt das rund 450 MB aus dem Internet (über den Firmenproxy, falls gesetzt). Danach liegen die Dateien
in `dist/ide-ai-quellen/`. Ohne Internet: die beiden Dateien von Hand dorthin legen.

Eine neue Fassung von Continue: in `packaging/ota-ide-ai/quellen` Fassung, Adresse und Prüfsumme
ändern, `revision` auf 1, dann:

```bash
scripts/build-ide-ai-deb.sh --hochladen
```

Die Einstellungsseite zeigt, welche Fassungen in der Paketquelle liegen.

> **Zum JetBrains-Plugin:** Continue pflegt es seit 2026 nicht mehr selbst, sondern überlässt es der
> Gemeinschaft; die Fassung 1.0.67 ist vom März 2026. Für PyCharm 2026.2 passt OTA sie beim Paketbau
> an: Ab 2026.2 steckt JCEF, der Browser, in dem Continue seinen Chat zeigt, in einem eigenen Plugin.
> Ohne angemeldete Abhängigkeit bliebe das Fenster leer („Nothing to show“). Ausserdem gibt der Agent
> `continue-binary` dem Menschen des Arbeitsplatzes, denn Continue setzt dessen Rechte bei jedem
> Start selbst.
> Für VS Code und VSCodium entwickelt Continue weiter.

## Datenschutz

- Was jemand fragt, geht **nur an euren KI-Server**, nicht an Continue oder Dritte.
- Die Telemetrie von Continue (PostHog) ist ausgeschaltet. In VSCodium ist sie es ohnehin.
- Verläufe speichert Continue im Zuhause (`~/.continue/sessions/`). Sie kommen damit in die
  Profilsicherung.
- Ein API-Schlüssel steht in `~/.continue/config.yaml` im Zuhause, also auch in der Sicherung.

## Wenn etwas nicht geht

| Was | Ursache |
|---|---|
| Im Editor kein Continue | Der Arbeitsplatz lief schon, als IDE-AI eingeschaltet wurde: neu starten. Beim allerersten Start kann die Installation eine halbe Minute nach dem Start fertig werden: Editor einmal neu öffnen. Protokoll: `docker logs ota-agent 2>&1 \| grep IDE-AI` |
| „Die Pakete fehlen in der Paketquelle“ | `scripts/build-ide-ai-deb.sh --hochladen` auf dem Host |
| Continue zeigt eine andere Konfiguration | Die erste Zeile von `~/.continue/config.yaml` fehlt: Die Datei gehört dem Menschen. Löschen, neu starten |
| Continue zeigt `Main Config` ohne Modelle | Continue lief, bevor OTA die Konfiguration schrieb. Arbeitsplatz neu starten, Root-Workspace anhalten und fortsetzen. Im Protokoll steht dann „Konfiguration gesetzt“ |
| Keine Antwort, Zeitüberschreitung | Erreicht der Arbeitsplatz den Server? `curl http://<server>/v1/models` im Terminal. Ein Modell, das erst geladen wird, braucht länger: Zeitlimit erhöhen |
| Antwort bricht ab, oder nur „Thought for …“ ohne Text | Die Antwortlänge reicht nicht; denkende Modelle verbrauchen sie mit der Überlegung. Größer stellen |
| „context length exceeded“ oder ähnlich vom Server | Das Kontextfenster in OTA ist größer als im Server. Kleiner stellen |
| Agent-Modus ruft keine Werkzeuge auf | Der Server kann keine Werkzeugaufrufe: vLLM `--enable-auto-tool-choice --tool-call-parser …`, llama.cpp `--jinja`. Oder **Werkzeuge** aus |
| Continue rechts nicht zu sehen | `Strg+Alt+B` öffnet die rechte Leiste. Von selbst öffnet OTA sie nur einmal je Ordner |
| PyCharm zeigt bei Continue nur „Nothing to show“ | Paket `ota-ide-ai-jetbrains` älter als `1.0.67-ota5`: `make update`, dann Arbeitsplatz neu starten. Im Protokoll (`~/.cache/JetBrains/*/log/idea.log`) steht dann `NoClassDefFoundError: com/intellij/ui/jcef/JBCefApp` oder `continue-binary: Die Operation ist nicht erlaubt` |
| PyCharm zeigt Continue nicht | Gibt es `~/.local/share/JetBrains/<IDE><Fassung>/ota-continue`? Der Name kommt aus `product-info.json` der IDE |

Prüfreihe: `scripts/test-ide-ai.sh`. Sie startet jede Vorlage mit einem passenden Editor und fragt
den KI-Server aus dem Arbeitsplatz. Vorgabe ist der llama.cpp-Server der Testanlage; ein anderer
über `OTA_TEST_KI_URL` und `OTA_TEST_KI_MODELL`.
