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
zählen, wer die KI wie oft anspricht. Zu sehen ist das an drei Stellen.

**Betrieb → KI-Nutzung, ohne Namen.** Was die Verwaltung zuerst sieht, für einen wählbaren
Zeitraum (24 h, 3, 7, 30 Tage oder frei), wahlweise nach Anfragen oder Tokens:

- Kacheln: Anfragen, Tokens hinein und heraus, Menschen, Arbeitsplätze, mittlere Dauer, Fehler.
- Der Verlauf aller Anfragen. Ein im Graphen aufgezogener Bereich vergrößert ihn.
- Ringdiagramme **je Mensch** und **je Arbeitsplatz**. Sie zeigen nur Grössen: „Person 1“ ist im
  gewählten Zeitraum und Maß die grösste, nicht immer dieselbe, und die API liefert dafür weder
  Namen noch Kennungen. Unter **drei** Menschen oder Arbeitsplätzen im Zeitraum entfällt die
  Aufteilung, denn bei zweien wüsste jeder, wer wer ist. Dazu Ringe je Vorlage, je Modell und,
  bei mehreren Servern, je Server. Mehr als sieben Stücke fasst „Übrige“ zusammen.
- Eine Verteilung **nach Tageszeit**, über den ganzen Zeitraum zusammengezählt.

**Personenbezogene Auskunft.** Namen, die Übersicht je Mensch und seine Arbeitsplätze mit Verlauf
gibt es erst nach einer **Begründung** (mindestens zehn Zeichen, z. B. eine Ticketnummer). Sie
steht als `ki.auskunft` mit dem Namen der fragenden Person im Prüfprotokoll und dort unter
Betrieb → Protokoll sichtbar. Die Auskunft gilt **30 Minuten**, nur für dieses Konto und nur in
diesem Fenster: Neu laden heißt neu begründen. Jeder Blick auf einen einzelnen Menschen steht
zusätzlich als `ki.nutzung_angesehen` mit dem Vorgang der Auskunft im Protokoll.
Technisch ist die Auskunft ein signiertes Merkmal (Kopfzeile `X-OTA-Auskunft`). Ohne sie
antworten `/api/admin/ki-nutzung/personen` und `/nutzer/{id}` mit 403.

Ein Klick auf einen Namen zeigt seine Arbeitsplätze mit einem Graphen, je Arbeitsplatz eine
Linie. **« 1 Tag mehr** erweitert ihn nach hinten, **‹ früher / später ›** verschiebt ihn. Darunter
stehen Modelle und Werkzeuge (opencode, Continue, Skript).

**Meine KI-Nutzung.** Solange die Statistik läuft, sieht **jeder** seine eigenen Zahlen in der
Seitenleiste: Summen, Verlauf je Arbeitsplatz, Modelle, Werkzeuge. Das ist Selbstauskunft
(Art. 15 DSGVO), deshalb ohne Begründung und ohne Protokolleintrag.

**DSGVO.** Ebenfalls solange die Statistik läuft, steht für alle ein Punkt **DSGVO** in der
Seitenleiste. Er erklärt, was OTA über Arbeitsplätze und KI-Nutzung erfasst, wozu, wie lange und
wer es sehen darf. Die Verwaltung sieht den Punkt immer und passt den Text dort mit
**Bearbeiten** an, Markdown wie bei den News. Die Platzhalter `{frist_roh}`, `{frist_stunden}`
und `{statistik}` setzt OTA ein, so stimmen genannte Fristen auch nach einer Änderung.
**Mitgelieferten Text verwenden** stellt die Vorlage wieder her (deutsch und englisch nach der
Sprache der Oberfläche). Die verantwortliche Stelle und die Datenschutzbeauftragte bzw. den
Datenschutzbeauftragten müsst ihr selbst eintragen. Jede Änderung steht als
`dsgvo.hinweis_geaendert` im Protokoll.

Was gezählt wird:

- **Zeit, Mensch, Arbeitsplatz, Server, Modell, Dauer und Tokens, nie Inhalte**. Den Menschen
  findet OTA über die Absenderadresse des Arbeitsplatzes.
- Die Tokens liefert der Server in seiner Antwort. Bei gestreamten Antworten bestellt der
  Durchgang sie mit (`stream_options.include_usage`) und nimmt den zusätzlichen Block wieder heraus,
  bevor er beim Werkzeug ankommt.

**Aufbewahrung:** Einzelne Anfragen 30 Tage, Stundensummen 365 Tage. Beides ist einstellbar, bei den
Stundensummen heißt 0 unbegrenzt. Älteres löscht OTA einmal am Tag. **Alle Nutzungsdaten löschen**
unter Betrieb → KI-Nutzung leert beides.

**Auf der Platte** kostet das wenig: Der Durchgang schreibt in eine Spool-Datei unter
`/srv/ota/runtime/ki/spool/`, die API holt sie einmal in der Minute in einem Zug ab. Das tut sie
auch, wenn Statistik und Durchgang inzwischen aus sind. Was dort liegt, wurde gezählt, als die
Statistik lief, und gehört in die Datenbank, wo die Fristen es löschen.

> **Vor dem Einschalten:** Auch ohne Namen auf der ersten Seite ist die Statistik eine technische
> Einrichtung, die sich zur Leistungs- und Verhaltenskontrolle *eignet* (§ 87 Abs. 1 Nr. 6
> BetrVG). Gibt es einen Betriebsrat, gehört er gefragt. Eine Betriebsvereinbarung sollte
> festhalten, wofür die Zahlen da sind (Kapazität, Kosten, Fehler, keine Leistungsbewertung) und
> welche Gründe eine personenbezogene Auskunft rechtfertigen. Mit eurer bzw. eurem
> Datenschutzbeauftragten klären, ob eine Datenschutz-Folgenabschätzung nötig ist, und den Eintrag
> im Verarbeitungsverzeichnis anlegen. Informiert werden die Menschen über den Punkt **DSGVO**. Den
> Text vorher anpassen. Ein- und Ausschalten, jede Auskunft mit Grund und jedes Öffnen der Zahlen
> eines Menschen stehen im Protokoll.

### Externe Dienste (Open WebUI)

Ein Dienst außerhalb der Arbeitsplätze, etwa Open WebUI, kann die KI ebenfalls über den Durchgang
ansprechen. Er sieht dann dasselbe Modellverzeichnis, es gilt dieselbe Gruppenregel, und seine
Anfragen stehen in derselben Statistik, beim richtigen Menschen. Den Schlüssel des KI-Servers kennt
er nicht mehr.

**Einrichten**

1. Auf dem Host in `deploy/.env` den Port setzen, z. B. `OTA_KI_EXTERN_PORT=8791`, dann
   `sudo make update`. Das veröffentlicht den Eingang am Host und **startet den Router neu**: Die
   Arbeitsplätze sind kurz ohne Netz. Der Port muss frei sein. `OTA_KI_EXTERN_BIND` begrenzt die
   Adresse, an der er lauscht (Vorgabe: alle). Ohne den Port bleibt alles wie bisher.
2. Unter **Einstellungen → IDE-AI → Externe Dienste** einen Dienst anlegen, z. B. „Open WebUI“.
   OTA zeigt den Schlüssel **genau einmal** und speichert danach nur seinen SHA-256. Geht er
   verloren: Dienst entfernen und neu anlegen.
3. In Open WebUI unter **Administration → Einstellungen → Verbindungen → OpenAI-API** die
   Adresse `http://<host>:8791/v1` und diesen Schlüssel eintragen.
4. Damit OTA weiß, wer fragt, braucht der Container von Open WebUI die Umgebungsvariable
   `ENABLE_FORWARD_USER_INFO_HEADERS=true`. Dafür wird er mit geänderter Konfiguration neu
   erstellt; das macht ihr an Open WebUI, OTA fasst den Container nicht an. Ältere Versionen von
   Open WebUI kennen die Variable nicht.

**Wie es wirkt**

- Am zweiten Eingang (Port 8791 im Namensraum der Firewall) gilt nur der Weg über den Namen und nur
  mit gültigem Schlüssel. Sonst kommt 401. Die Arbeitsplätze selbst sperrt die Firewall dort aus;
  sie haben ihren eigenen Eingang.
- Wer fragt, steht in den Kopfzeilen `X-OpenWebUI-User-Email` und `X-OpenWebUI-User-Name`. Der
  Durchgang glaubt ihnen nur bei gültigem Schlüssel. **Zum KI-Server gehen weder sie noch der
  Schlüssel des Dienstes weiter**, nur der Schlüssel des Servers.
- **Gruppen:** Ein weiterer Server mit Gruppen ist über den Dienst nur für deren Mitglieder (und
  Administratoren) erreichbar. Zugeordnet wird über E-Mail oder Benutzernamen. Ohne Angabe, wer
  fragt, gibt es nur die Server für alle. Die Liste der Berechtigten schickt die API mit jeder
  Konfiguration und spätestens alle zehn Minuten.
- **Statistik:** Die API ordnet die Anfrage über E-Mail, Benutzernamen oder einen eindeutigen
  Anzeigenamen dem OTA-Konto zu. Der Dienst steht an der Stelle des Arbeitsplatzes (unter „Meine
  KI-Nutzung“ also als eigene Zeile) und als Werkzeug „Externer Dienst (kürzel)“. Ist niemand
  zuzuordnen, zählt die Anfrage als „nicht zuzuordnen“.
- Open WebUI schickt auch eigene Anfragen, etwa für Chat-Titel, Schlagwörter oder Vorschläge.
  Die zählen beim jeweiligen Menschen mit.
- Anlegen und Entfernen stehen im Protokoll (`ki.extern_angelegt`, `ki.extern_geloescht`). Ein
  entfernter Dienst ist sofort ausgesperrt.
- Der mitgelieferte DSGVO-Text erwähnt angebundene Dienste. Passt ihn an, wenn ihr einen anbindet.

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
  [Nutzungsstatistik](#nutzungsstatistik). Läuft sie, zeigt OTA allen den Punkt **DSGVO** und
  jedem seine eigenen Zahlen. Die Verwaltung sieht Namen nur nach einer protokollierten
  Begründung.

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
| „Personenbezogene Zahlen nur mit einer Auskunft“ / „Die Auskunft ist abgelaufen“ | Die halbe Stunde ist um, oder die Seite wurde neu geladen: Begründung erneut eingeben |
| Kein Ringdiagramm je Mensch, nur „Erst ab 3 Menschen …“ | Gewollt: Bei weniger als drei Menschen bzw. Arbeitsplätzen im Zeitraum wäre erkennbar, wer wer ist. Zeitraum vergrößern |
| Kein Punkt „DSGVO“ / „Meine KI-Nutzung“ in der Seitenleiste | Beide erscheinen nur, solange die Nutzungsstatistik läuft. Die Verwaltung sieht „DSGVO“ immer. Die Seitenleiste fragt alle fünf Minuten nach, sonst Seite neu laden |
| Open WebUI: „Unbekannter Schlüssel“ (401) | Schlüssel falsch übernommen oder Dienst entfernt. Dienst neu anlegen, Schlüssel neu eintragen |
| Open WebUI erreicht `http://<host>:8791` nicht | `OTA_KI_EXTERN_PORT` in `deploy/.env` gesetzt und danach `make update`? `docker port ota-firewall` zeigt den Port. Eine Firewall am Host muss ihn für das Netz von Open WebUI durchlassen |
| Anfragen über Open WebUI „nicht zuzuordnen“ | `ENABLE_FORWARD_USER_INFO_HEADERS=true` fehlt am Container, oder die E-Mail in Open WebUI passt zu keinem OTA-Konto |
| In der KI-Nutzung keine Zahlen | Statistik an? Durchgang bereit (Einstellungen → IDE-AI)? Die API holt jede Minute ab: `docker logs ota-api 2>&1 \| grep KI-Nutzung` |

Prüfreihe: `scripts/test-ide-ai.sh`. Sie startet jede Vorlage mit einem passenden Editor und fragt
den KI-Server aus dem Arbeitsplatz. Vorgabe ist der llama.cpp-Server der Testanlage; ein anderer
über `OTA_TEST_KI_URL` und `OTA_TEST_KI_MODELL`. Durchgang, mehrere Server, Statistik und Ausfall
prüft `scripts/test-ki.sh` mit denselben Angaben.
