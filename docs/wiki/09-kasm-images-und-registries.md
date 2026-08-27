# 9 · Kasm-Images und Registries einbinden

*Für Administratoren.* 🔨 M8

Ein **Feature**, nicht das Fundament. Der Kern von OTA ist der Arbeitsplatz
([Kapitel 3](03-arbeitsplatz.md)). Dieses Kapitel beschreibt, wie das vorhandene Ökosystem an
fertigen Anwendungscontainern mitbenutzt wird.

## Wann sich das lohnt

- Werkzeuge, die man **selten und isoliert** braucht — GIMP, Inkscape, ein Wegwerf-Browser, ein
  OSINT-Werkzeug — und die im persönlichen Arbeitsplatz nur Platz kosten würden
- Der **Umstieg**: Was heute in Kasm läuft, läuft am ersten Tag auch in OTA
- Anwendungen, für die es schon ein gepflegtes Image gibt und für die sich ein eigener Build nicht
  lohnt

## Einzelnes Image einbinden

Neuen Workspace anlegen, `mode: single_app`, Image-Referenz eintragen. Das war es. Ressourcen, Rechte
und Zuweisung funktionieren genau wie beim Arbeitsplatz.

## Ganze Registry einbinden

Eine Registry ist ein Katalog fertiger Anwendungen als JSON-Datei unter fester Adresse:

```
{registry_url}/{schema_version}/list.json
```

**Vorkonfiguriert, jeweils abschaltbar:**

| Registry | Adresse | Anwendungen |
|---|---|---|
| Kasm Technologies | `https://registry.kasmweb.com/1.1/list.json` | 86 |
| Kasm AI Images | `https://ai.registry.kasmweb.com/1.1/list.json` | 11 |
| LinuxServer.io | `https://kasmregistry.linuxserver.io/1.1/list.json` | 2 |

Eigene Registries lassen sich über die URL hinzufügen.

Verfügbare Kategorien im offiziellen Katalog: Browser, Chat, Communication, Desktop, Development,
Games, Mobile, Multimedia, OSINT, Office, Privacy, Productivity, Remote Access, Security.

## Der Import

1. **Katalog laden** — OTA holt die Liste und legt sie ab. Über den Änderungszeitstempel wird
   erkannt, ob eine Aktualisierung nötig ist
2. **Durchsuchen** — nach Name, Kategorie, Beschreibung
3. **Importieren** — es entsteht ein Workspace mit `mode: single_app`; Name, Beschreibung,
   Kategorien und Icon werden übernommen, die Image-Referenz passend zur gewählten Version
4. **Zuweisen** wie bei jedem anderen Workspace

### Was OTA dabei prüft

**Architektur.** Nur Einträge werden angeboten, die zur Architektur des Hosts passen. Ein reines
`arm64`-Image auf einem `amd64`-Host wird gar nicht erst zur Auswahl gestellt.

**Größe.** Der Katalog nennt die entpackte Größe. Sie steht **vor** dem Import da, und wenn sie den
freien Plattenplatz nennenswert angreift, warnt die Oberfläche. Ein 6,5-GB-Image ist bei begrenztem
Platz eine Entscheidung, keine Nebensache.

## Zwei Hinweise, die ernst zu nehmen sind

> **Eine Registry ist eine Vertrauensentscheidung.**
> Ein importiertes Image kommt aus fremder Quelle und läuft anschließend im eigenen Netz. Der Katalog
> trägt zwar eine Signatur, aber ob OTA sie prüft, ist noch nicht entschieden (`plan.md` §17.11).
> Bis dahin gilt: Nur Registries einbinden, deren Betreiber man vertraut.

> **Der Katalog sagt nichts über Lizenzen.**
> Dass eine Registry ein Image listet, ist keine Aussage darüber, ob dessen Nutzung im Unternehmen
> zulässig ist. Enthaltene Anwendungen können proprietär sein oder Nutzerlizenzen verlangen. Der
> Import-Dialog weist darauf hin — die Prüfung bleibt beim Administrator
> ([Kapitel 13](13-lizenzen.md)).

## Grenzen

Die Images sind auf **eine Anwendung** ausgelegt. Es sind Wegwerf-Container: kein gemeinsames Home
mit dem Arbeitsplatz, keine gemeinsamen SSH-Schlüssel, und die Zwischenablage funktioniert nur
zum Browser hin und zurück — nicht direkt zu einer App im Arbeitsplatz. Der Weg über die
Browser-Zwischenablage funktioniert selbstverständlich.

Wer ein Werkzeug täglich braucht, ist im Arbeitsplatz besser aufgehoben.
