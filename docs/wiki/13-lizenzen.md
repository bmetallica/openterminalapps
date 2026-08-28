# 13 · Lizenzen

Zusammenfassung. Ausführlich mit Originalzitaten: `plan.md` §3.
**Keine Rechtsberatung** — aber am Lizenztext geprüft, nicht aus dem Gedächtnis.

## Kurzfassung

**Der unternehmensinterne Betrieb ist gedeckt.** Die Grenze verläuft nicht bei der Nutzerzahl,
sondern bei der Weitergabe nach außen.

## Die Bestandteile

| Bestandteil | Lizenz | Bewertung |
|---|---|---|
| **Microsoft VS Code** | proprietär, MS-EULA | Internes Deployment **ausdrücklich erlaubt**, unbegrenzte Kopien |
| **VSCodium** | MIT | frei. Nur Open VSX |
| **IntelliJ IDEA Community** | Apache-2.0 | kommerziell kostenfrei |
| **IntelliJ Ultimate** | proprietär | **Named-User-Lizenz je Entwickler**, Aktivierung durch den Nutzer |
| **opencode** | MIT | frei |
| **Cursor** | proprietär | **vor Aufnahme prüfen** — siehe unten |
| **KasmVNC** | GPL-2.0 | Eigenbetrieb uneingeschränkt frei; bei **Weitergabe** greifen die GPL-Pflichten |
| **Kasm-Workspace-Images** | MIT **nur für die Baurezepte** | Das fertige Image ist nicht MIT — siehe unten |
| **Kasm Workspaces Server** | kommerzieller EULA | **wird durch OTA ersetzt** |
| Docker, Traefik, PostgreSQL, XFCE | Apache-2.0 / MIT / PostgreSQL / GPL | frei |

> **Ein Image ist ein zusammengesetztes Werk.** Die Zeilen dieser Tabelle beschreiben einzelne
> Bestandteile, nicht das Ergebnis. Ein Arbeitsplatz-Image enthält OTA-Konfiguration, KasmVNC,
> XFCE, hunderte Distributionspakete und die installierten Anwendungen — jedes mit seiner eigenen
> Lizenz. **Nichts davon wird durch OTA neu lizenziert.** Die Aufstellung in drei Ebenen steht in
> [THIRD-PARTY-NOTICES.md](../../THIRD-PARTY-NOTICES.md).

## Betrieb oder Weitergabe — die Linie, auf die es ankommt

Fast jede Frage in diesem Kapitel hat zwei Antworten, je nachdem auf welcher Seite dieser Linie man
steht:

| | Eigenes Haus | Weitergabe nach aussen |
|---|---|---|
| Was gemeint ist | Eigene Mitarbeitende greifen über den Browser auf eine intern betriebene Anlage zu | Ein Image veröffentlichen, ein Angebot für Dritte betreiben, eine Anlage ausliefern |
| KasmVNC (GPL-2.0) | frei, keine Pflichten | Lizenztext und Hinweise mitgeben, Quellcode verfügbar halten |
| Kasm-Baurezepte (MIT) | frei | Copyright-Vermerk erhalten |
| Microsoft VS Code | **ausdrücklich erlaubt** | **nicht gedeckt** |
| Distributionspakete | frei | jeweilige Pflichten, in Summe nur mit einer Stückliste zu überblicken |

**OTA ist für die linke Spalte gebaut** (`plan.md` §17.4b). Wer in die rechte will, hat damit kein
Lizenzproblem des Projekts, sondern eine Reihe eigener Prüfungen vor sich — angefangen bei VS Code.

## Microsoft VS Code

Die EULA sagt in §1a wörtlich:

> „You may use **any number of copies** of the software to develop and test your applications,
> **including deployment within your internal corporate network**."

Kein Nutzerlimit, keine Gebühr, interner Netzbetrieb ausdrücklich benannt.

§5 verbietet:

> „share, publish, rent or lease the software, or **provide the software as a stand-alone offering
> for others to use**."

| Vorhaben | Zulässig |
|---|---|
| Eigene Mitarbeiter im Firmennetz | **Ja** |
| Golden Image in eine **interne** Registry | **Ja** |
| Beliebig viele Nutzer und Sessions | **Ja** |
| Image in eine **öffentliche** Registry | **Nein** |
| OTA an Kunden verkaufen oder hosten | **Nein** |

**Sobald echte Dritte Zugang bekommen sollen** — Kunden, Partnerfirmen —, brauchen diese ein
Golden Image mit **VSCodium** statt dem Microsoft-Build.

### Marketplace

Der offizielle Marketplace darf nach Microsofts Nutzungsbedingungen **nur von MS-gebrandeten
Produkten** angesprochen werden. VS Code darf, VSCodium und Cursor dürfen nicht — sie nutzen Open VSX
bzw. eigene Registries.

**Daraus folgt zweierlei:**
1. Die Desktop-Variante von VS Code im Container ist der rechtlich saubere Weg zum Marketplace.
   `code-server` und `openvscode-server` müssten auf Open VSX ausweichen.
2. VSCodium und Cursor dürfen **nicht** per Konfiguration auf den MS-Marketplace umgebogen werden.
   Das ist technisch möglich und lizenzrechtlich unzulässig.

**OTA prüft das nach jedem Build.** Sobald ein Image im Store liegt, liest der Build die
`product.json` jedes gefundenen Editors und schreibt ins Protokoll, wohin er seine Erweiterungen
holt. Zeigt ein Nicht-Microsoft-Editor auf `marketplace.visualstudio.com`, steht dort eine Warnung.
Der Build scheitert deswegen nicht — das Image ist gebaut und benutzbar; die Entscheidung, es so zu
verteilen, gehört einem Menschen.

Im aktuellen Arbeitsplatz-Image sieht das so aus:

```
Erweiterungs-Marktplatz der gefundenen Editoren:
  VS Code (Microsoft): https://marketplace.visualstudio.com/_apis/public/gallery
  VSCodium: https://open-vsx.org/vscode/gallery
```

Also korrekt. Ein Hinweis zur Fehlersuche: Ein einfaches `grep` nach
`marketplace.visualstudio.com` in der `product.json` von VSCodium **findet einen Treffer** und ist
trotzdem kein Befund — der Name steht dort unter `extensionAllowedBadgeProviders`, also in der
Liste der Hosts, von denen Abzeichen in einer README geladen werden dürfen. Entscheidend ist allein
`extensionsGallery.serviceUrl`.

### Telemetrie

VS Code sendet Telemetrie an Microsoft (EULA §2). Bei betrieblicher Nutzung ist das ein
DSGVO-Thema. Empfehlung: im Skeleton-Profil `"telemetry.telemetryLevel": "off"` vorbelegen.

## KasmVNC — GPL-2.0

- **Betrieb uneingeschränkt frei.** Die GPL kennt keine Nutzerlimits und keine Gebühren
- Pflichten entstehen nur bei **Weitergabe**. Mitarbeiter über den Browser auf eine intern betriebene
  Instanz zugreifen zu lassen ist keine Weitergabe. GPLv2 hat auch keine Netzwerkklausel
- **OTA selbst muss nicht GPL sein** — es spricht nur über HTTPS und WebSocket mit KasmVNC, linkt
  keinen GPL-Code und bettet keinen ein
- Wer KasmVNC **weitergibt** — und das tut, wer ein Image damit veröffentlicht —, muss Lizenztext
  und Hinweise erhalten und den zugehörigen Quellcode verfügbar halten. Das macht **nicht das ganze
  Image zu GPL**; es heisst, dass der GPL-Teil ein GPL-Teil bleibt
- KasmVNC führt neben der GPL eine **eigene Liste von Drittanbieter-Hinweisen**, und Kasm merkt
  selbst an, dass sie nicht zwingend vollständig ist. Wer ein KasmVNC-haltiges Image verteilt, gibt
  deshalb die Lizenz- und Hinweisdateien der jeweiligen Fassung mit, statt sich auf
  „KasmVNC = GPL-2.0" zu verlassen

## Kasm-Images — MIT

Die Build-Rezepte stehen unter MIT. Der Disclaimer der Lizenzdatei ist wichtig:

> „This license applies **only to the source code that is directly maintained in this git
> repository** … to include other projects owned and/or maintained by Kasm Technologies."

MIT gilt also für die **Dockerfiles**, nicht für den Inhalt der fertigen Images. Jedes enthaltene
Paket behält seine eigene Lizenz.

GitHub führt die Kasm-Image-Repositorien folgerichtig nicht als „MIT", sondern als *Other* —
nachgeprüft am 2026-08-28 über die GitHub-Lizenz-Schnittstelle.

**Marken**: „Kasm" und „Kasm Workspaces" sind geschützt; MIT erteilt keine Markenrechte. OTA darf sie
nicht im Produktnamen, Logo oder in Domains führen. Der MIT-Copyright-Vermerk muss in abgeleiteten
Dockerfiles erhalten bleiben.

## Cursor — vor Aufnahme klären

Cursor steht im App-Katalog **deaktiviert**. Zwei Punkte sind offen:

1. Erlaubt Cursors EULA den Betrieb in einer zentral bereitgestellten Mehrbenutzer-Umgebung, und
   brauchen die Nutzer je eine eigene Lizenz? Bei Pro-Abos ist von Named-User auszugehen.
2. Cursor ist ein VS-Code-Fork und damit **kein MS-gebrandetes Produkt** — der MS-Marketplace darf
   daraus nicht angesprochen werden.

Diese Prüfung kann OTA nicht abnehmen.

## Importierte Registry-Images

Dass eine Registry ein Image listet, ist **keine Aussage über dessen Lizenz**. Enthaltene
Anwendungen können proprietär sein oder Nutzerlizenzen verlangen. Vor dem Ausrollen prüfen.
→ [Kapitel 9](09-kasm-images-und-registries.md)

## Regel für jedes neue Golden Image

Vor der Aufnahme einer Anwendung deren Lizenz prüfen und dokumentieren. Faustregel: Pakete aus den
Debian- und Ubuntu-Quellen sind unkritisch; Hersteller-Binärpakete (Chrome, JetBrains Ultimate,
Microsoft-Produkte, Cursor) brauchen einen Einzelblick.
