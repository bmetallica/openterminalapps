# 9 · Kasm-Images und Registries einbinden

*Für Administratoren.*

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

**Verwaltung → Registries.** Dort steht, was eingetragen ist, wie viele Einträge der jeweilige
Katalog hat, wie viele davon übernommen wurden, und wann zuletzt gelesen wurde.

### Vorgeschlagen, nicht eingetragen

OTA kennt drei verbreitete Registries und bietet sie mit einem Klick an — **eingetragen ist keine
von selbst.** Eine Registry ist eine Vertrauensentscheidung (siehe unten), und die trifft ein
Mensch, nicht die Voreinstellung.

| Registry | Adresse | Anwendungen |
|---|---|---|
| Kasm Technologies | `https://registry.kasmweb.com` | 86 |
| Kasm AI Images | `https://ai.registry.kasmweb.com` | 11 |
| LinuxServer.io | `https://kasmregistry.linuxserver.io` | 2 |

Jede andere Adresse lässt sich genauso eintragen. Verlangt wird **https** — ein Katalog über eine
ungesicherte Verbindung ist ein Katalog, den unterwegs jemand ändern kann, und daraus entstehen
Image-Referenzen, die anschließend im eigenen Netz laufen.

**Der Katalog wird beim Eintragen sofort gelesen.** Lässt er sich nicht laden, entsteht kein
Eintrag: Eine Registry, die nur als Zeile in einer Liste steht, hilft niemandem. Schlägt später ein
**Aktualisieren** fehl, bleibt die Registry — der Fehler wird aber festgehalten und in der Liste
gezeigt, damit auch morgen noch sichtbar ist, dass hier seit gestern etwas klemmt.

Kategorien im offiziellen Katalog: Browser, Chat, Communication, Desktop, Development, Games,
Mobile, Multimedia, OSINT, Office, Privacy, Productivity, Remote Access, Security.

## Der Katalog

Ein Klick auf eine Registry öffnet ihren Katalog im Hauptfenster: Suche über Name, Beschreibung und
Kategorie, dazu Kategorie-Chips zum Eingrenzen. Jeder Eintrag nennt Symbol, Name, Beschreibung,
Image-Referenz und **Größe**.

### Welche Fassung vorgeschlagen wird

Der Katalog listet je Anwendung mehrere Kasm-Versionen. Naiv die letzte zu nehmen ist falsch: Bei
AlmaLinux 8 zeigen die beiden neuesten auf `kasmweb/almalinux-8-desktop:develop` — einen rollenden
Entwicklungsstand, und der letzte davon mit Größe 0, also noch gar nicht gebaut.

OTA schlägt deshalb die **neueste Fassung vor, die kein `develop` ist und eine echte Größe hat**.
Nur wenn es die nicht gibt, fällt die Wahl auf das Übriggebliebene — dann steht im Katalog eben
nichts Besseres.

### Was OTA vor dem Übernehmen prüft

**Architektur.** Ein reines `arm64`-Image auf einem `amd64`-Host wird gezeigt, aber nicht zum
Übernehmen angeboten; darunter steht, warum. Es zu verschweigen erzeugt nur die Frage, warum es
fehlt.

**Größe.** Der Katalog nennt die entpackte Größe. Sie steht **vor** dem Übernehmen da, und wenn sie
den freien Plattenplatz nennenswert angreift, warnt die Oberfläche. Ein 6,5-GB-Image ist bei
begrenztem Platz eine Entscheidung, keine Nebensache.

## Der Import

**Ein Import lädt nichts herunter.** Er legt eine Vorlage an, mehr nicht. Das Image kommt erst beim
ersten Start oder wenn es jemand unter *Images* holt ([Kapitel 16](16-images-verwalten.md)).

Was dabei entsteht:

| | |
|---|---|
| Betriebsart | `single_app` — ein Kasm-Image bringt genau eine Anwendung mit und startet sie selbst. Als Arbeitsplatz betrieben würde sein Startskript überdeckt, und dann startete gar nichts |
| Sichtbarkeit | **abgeschaltet.** Ein Import soll nicht ungefragt auf den Dashboards aller Nutzer auftauchen. Erst Gruppe zuweisen, dann einschalten |
| Zuhause | ein **eigenes** Profil je Vorlage, nicht das gemeinsame des Arbeitsplatzes. Ein fremdes Image bekommt nicht den Schlüssel zur Wohnung |
| Herkunft | bleibt vermerkt. Ein zweiter Import desselben Eintrags wird abgelehnt, mit Verweis auf die vorhandene Vorlage |

Übernommene Vorlagen **stehen auf eigenen Füßen**: Wird die Registry später entfernt, bleiben sie
bestehen. Der Katalog war nur der Weg, wie sie entstanden sind.

Verschwindet ein Eintrag aus dem Katalog, fliegt er beim nächsten Aktualisieren raus — außer er
wurde übernommen. Dann bleibt er als Herkunftsnachweis stehen.

### Warum die Symbole über OTA laufen

Die Symbole liegen bei der fremden Registry, aber der Browser holt sie über
`/api/admin/registries/{id}/icon`. Nicht aus Ordnungsliebe: Die Inhaltsregel der Anwendung lässt
keine fremden Bildquellen zu (`img-src 'self'`), und sie für jede eingetragene Registry
aufzuweichen wäre für ein Symbol ein schlechter Tausch.

Der Umweg ist gefesselt — geholt wird nur, was **unterhalb der Adresse dieser Registry** liegt, und
nur, wenn es ein Bild ist. Ohne diese Fessel wäre er ein Werkzeug, mit dem sich über OTA beliebige
Adressen abrufen ließen, auch solche im internen Netz.

## Zwei Hinweise, die ernst zu nehmen sind

> **Eine Registry ist eine Vertrauensentscheidung.**
> Ein importiertes Image kommt aus fremder Quelle und läuft anschließend im eigenen Netz. Der
> Katalog trägt ein ES256-JWT über einen Hash seines Inhalts, aber der öffentliche Schlüssel dafür
> liegt bei Kasm; **OTA prüft die Signatur nicht** — das wäre ohne den Schlüssel Theater. Die
> Oberfläche sagt das, statt es zu verschweigen. Es gilt: Nur Registries einbinden, deren Betreiber
> man vertraut.

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
