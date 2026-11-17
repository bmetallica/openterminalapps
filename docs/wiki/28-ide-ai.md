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

Ohne Durchgang spricht Continue den Server **aus dem Arbeitsplatz** an, nicht über OTA. Deshalb
muss der OTA-Host den Server erreichen können (die Arbeitsplätze gehen über seinen Router).

## Mehrere KI-Server, KI-Durchgang und Nutzungsstatistik

*Seit dem 2026-11-17. Alles hier ist optional und ab Werk aus.*

### Der KI-Durchgang

Der Durchgang ist ein eigener kleiner Dienst, `ota-ki`. Er läuft im Netzwerk-Namensraum der Firewall
und lauscht dort auf Port 8790. Eingeschaltet wird er unter **Einstellungen → IDE-AI → KI-Durchgang**.
Dann gilt:

- **Continue und opencode** sprechen `http://ki.ota:8790/v1` an statt den Server direkt. Der Name
  löst sich in jedem Arbeitsplatz zur Adresse seines Routers auf. Im Zuhause steht **kein
  API-Schlüssel** mehr; den setzt der Durchgang ein.
- **Die Firewall fängt ab**, was aus einem Arbeitsplatz an die Adresse und den Port eines
  eingetragenen KI-Servers geht, und leitet es zum Durchgang um (nft `redirect`). So laufen auch
  Skripte, eigene Konfigurationen und alte Instanzen mit der echten Adresse über ihn, und auch
  Container in Root-Arbeitsplätzen. Die Anfrage geht dann genau an den Server, den sie ansprechen
  wollte.
- **Liegt der Durchgang**, nimmt die Firewall die Umleitung nach spätestens zehn Sekunden heraus,
  und der Verkehr geht wieder direkt zum Server. Was über `ki.ota` geht, braucht ihn allerdings.
  Startet die Firewall neu, startet der Agent `ota-ki` mit, sonst hinge er im alten Namensraum.

### Mehrere KI-Server

Unter **Weitere KI-Server** lassen sich zum Server oben beliebig viele dazu eintragen, jeder mit
Name, Kürzel, Adresse, Schlüssel und Modellen. Sie wirken **nur mit dem Durchgang**:

- Continue und opencode sehen ein Modellverzeichnis über alle Server. Der Durchgang leitet jede
  Anfrage an den Server, zu dem das Modell gehört.
- Hat ein weiterer Server ein Modell, dessen Name schon vergeben ist, heißt es dort
  `kürzel/modell`, etwa `gpu2/qwen3-coder`. Der Durchgang setzt den echten Namen wieder ein. Die
  Modelle des Servers oben behalten ihren Namen, das Standardmodell bleibt gültig.
- Ein Modell, das in OTA nicht eingetragen ist, beantwortet der Durchgang mit 404 und einer
  Erklärung.

**Wer welchen Server bekommt:** Der Server oben gilt für alle, die IDE-AI oder opencode haben.
Jeder weitere Server bekommt eigene **Gruppen**. Deren Mitglieder bekommen ihn zusätzlich,
Administratoren immer. Ohne Gruppe gilt er für alle.

- Continue und opencode bieten jedem Menschen nur die Modelle seiner Server an. Das Standardmodell
  fällt auf das des ersten Servers zurück, wenn es auf einem Server liegt, den der Mensch nicht hat.
- Der Durchgang prüft jede Anfrage: Wer ein Modell oder die Adresse eines Servers anspricht, der
  ihm nicht zusteht, bekommt 403 („… ist für dich nicht freigegeben“). Eine direkte
  HTTPS-Verbindung endet ohne Antwort.
- Ein Server mit Gruppen ist in der Firewall **nicht** für alle freigegeben. Erreichbar ist er nur
  über den Durchgang. Liegt der Durchgang, bleibt er zu, statt für alle offen zu sein.
- Geänderte Gruppen gelten im Durchgang sofort. In Continue und opencode erscheinen neue Modelle
  beim nächsten Start oder Fortsetzen des Arbeitsplatzes.

### Nutzungsstatistik

Mit eingeschaltetem Durchgang lässt sich unter **Einstellungen → IDE-AI → Nutzungsstatistik**
zählen, wer die KI wie oft anspricht. Zu sehen ist das unter **Betrieb → KI-Nutzung**:

- **Übersicht** für einen wählbaren Zeitraum (24 h, 3, 7, 30 Tage oder frei): je Mensch Anfragen,
  Tokens hinein und heraus, Arbeitsplätze, meistgenutztes Modell, Verlauf, zuletzt.
- **Ein Klick auf den Namen** zeigt seine Arbeitsplätze mit einem Graphen, je Arbeitsplatz eine
  Linie. Standard sind die letzten 24 Stunden. **« 1 Tag mehr** erweitert den Graphen nach hinten,
  **‹ früher / später ›** verschiebt ihn, und ein im Graphen aufgezogener Bereich vergrößert ihn.
  Darunter Modelle und Werkzeuge (opencode, Continue, Skript).
- Gezählt werden **Zeit, Mensch, Arbeitsplatz, Server, Modell, Dauer und Tokens, nie Inhalte**.
  Den Menschen findet OTA über die Absenderadresse des Arbeitsplatzes.
- Die Tokens liefert der Server in seiner Antwort. Bei gestreamten Antworten bestellt der
  Durchgang sie mit (`stream_options.include_usage`) und nimmt den zusätzlichen Block wieder heraus,
  bevor er beim Werkzeug ankommt.

**Aufbewahrung:** Einzelne Anfragen 30 Tage, Stundensummen 365 Tage. Beides ist einstellbar, bei den
Stundensummen heißt 0 unbegrenzt. Älteres löscht OTA einmal am Tag. **Alle Nutzungsdaten löschen**
unter Betrieb → KI-Nutzung leert beides.

**Auf der Platte** kostet das wenig: Der Durchgang schreibt in eine Spool-Datei unter
`/srv/ota/runtime/ki/spool/`, die API holt sie einmal in der Minute in einem Zug ab.

> **Vor dem Einschalten:** Eine Auswertung je Person kann unter die Leistungs- und
> Verhaltenskontrolle fallen (§ 87 Abs. 1 Nr. 6 BetrVG). Gibt es einen Betriebsrat, gehört er
> gefragt, und die Menschen gehören informiert. Ein- und Ausschalten und jedes Öffnen der Zahlen
> eines Menschen stehen im Protokoll.

### Verschlüsselte Verbindungen

Spricht der KI-Server HTTPS, ändert sich für Continue und opencode nichts: Sie sprechen den
Durchgang über `ki.ota` an, und der Durchgang spricht HTTPS zum Server, mit Prüfung des Zertifikats.
Die Strecke vom Arbeitsplatz zum Router ist eine private Verbindung auf demselben Host.

Was ein Skript **direkt per HTTPS** an die Adresse des Servers schickt, kann der Durchgang nicht
lesen, ohne den Arbeitsplätzen eine eigene CA unterzuschieben. Das tut OTA nicht. Solche
Verbindungen reicht er unverändert durch und zählt sie nur als Verbindung, mit dem Servernamen aus
dem TLS-Hello. In der Übersicht stehen sie als „verschlüsselt (nur Verbindungen)“.

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
  Mit dem KI-Durchgang nicht: Dann kennt ihn nur der Durchgang.
- Die Nutzungsstatistik ist aus, solange niemand sie einschaltet. Was sie zählt, steht oben unter
  [Nutzungsstatistik](#nutzungsstatistik).

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
| Continue verdrängt: Marketplace-Update, abgeschaltet, eigene `config.yaml` | Der Mensch selbst: Dashboard → Kachel → **⋯ → KI-Werkzeuge neu einrichten** ([Kapitel 33](33-entwickeln.md#continue-ist-weg-oder-verhält-sich-anders-)). Räumt die Kopien weg, schaltet Continue ein, legt die eigene `config.yaml` beiseite und installiert die Pakete noch einmal. Im Protokoll: `ide_ai.neu_eingerichtet`, im Agent `IDE-AI in … neu eingerichtet: …` |

| Unter IDE-AI „Der Durchgang antwortet nicht“ | `docker logs ota-ki`. Läuft er, aber die Firewall war neu gestartet: Der Agent startet ihn beim nächsten Abgleich mit, sonst `docker restart ota-ki`. Bis dahin geht der Verkehr direkt |
| „Das Modell … ist in OTA nicht eingetragen“ | Ein Werkzeug fragt über `ki.ota` nach einem Modell, das unter IDE-AI nicht angeboten wird. Anbieten oder im Werkzeug ein anderes wählen |
| In der KI-Nutzung „nicht zuzuordnen“ | Anfragen von einer Adresse ohne laufende Sitzung, etwa kurz nach dem Beenden |
| In der KI-Nutzung keine Zahlen | Statistik an? Durchgang bereit (Einstellungen → IDE-AI)? Die API holt jede Minute ab: `docker logs ota-api 2>&1 \| grep KI-Nutzung` |

Prüfreihe: `scripts/test-ide-ai.sh`. Sie startet jede Vorlage mit einem passenden Editor und fragt
den KI-Server aus dem Arbeitsplatz. Vorgabe ist der llama.cpp-Server der Testanlage; ein anderer
über `OTA_TEST_KI_URL` und `OTA_TEST_KI_MODELL`. Durchgang, mehrere Server, Statistik und Ausfall
prüft `scripts/test-ki.sh` mit denselben Angaben.
