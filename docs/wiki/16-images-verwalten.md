# 16 · Images verwalten

*Für Administratoren.* ✅ Liste, Holen, Entfernen, eigene Registry

**Verwaltung → Images.**

## Woher die Liste kommt

Aus dem Docker-Host, ungefiltert: **jedes getaggte Image, das dort liegt.** Auf einer Maschine, die
sich OTA mit anderen Diensten teilt, sind das schnell fünfzig Einträge — von Elasticsearch bis
busybox. Genau deshalb gibt es diesen Bildschirm und nicht nur eine Auswahlliste im
Workspace-Editor.

Sortiert wird nach **Herkunft**, denn die entscheidet, was du damit tun darfst:

| Herkunft | Was das heisst |
|---|---|
| **Von OTA gebaut** | `ota/…` — im Workspace-Editor unter *Software* entstanden. Deine Fassungen, dein Aufräumen |
| **Von Kasm** | Gehört dem anderen System auf diesem Host. OTA zeigt sie an, fasst sie aber nicht an — gelöscht werden sie dort, wo sie hergekommen sind |
| **Übrige** | Alles Weitere auf dem Host. Nutzbar, wenn es ein KasmVNC-Image ist; entfernbar, wenn kein Workspace es benutzt |

Die Spalte **Benutzt von** nennt die Workspaces, die auf ein Image zeigen. Ohne sie wäre „entfernen"
ein Ratespiel — und ein Workspace, dem das Image fehlt, meldet sich erst beim nächsten Klick eines
Nutzers.

## Ein Image holen

Adresse eintragen wie bei `docker pull`, dann **Holen**:

```
kasmweb/gimp:1.18.0-rolling-weekly
registry.firma.local:5000/team/arbeitsplatz:2026-08
```

Der Fortschritt läuft mit — ein Kasm-Image bringt ein bis drei Gigabyte mit, das dauert. Danach
steht es im Workspace-Editor zur Auswahl.

Im Editor selbst lässt sich die Adresse auch **frei eintragen**. Zeigt sie auf etwas, das noch nicht
auf dem Host liegt, sagt das Feld das — gespeichert wird trotzdem, denn vorhanden sein muss das
Image erst beim Start.

## Ein Image entfernen

Nur, wenn beides zutrifft: **kein Workspace benutzt es**, und es ist **nicht von Kasm**. Sonst
verweigert OTA es mit dem Grund.

Alte Fassungen eigener Images werden ohnehin begrenzt: Je Workspace bleiben die letzten drei
([Kapitel 7](07-golden-images.md)).

## Die eigene Registry ✅

Im Stack läuft `registry:2` als Dienst `ota-registry`. Jedes gebaute Golden Image landet dort
zusätzlich zum Docker-Store, und die Adresse der Fassung wird die Adresse in der Registry:

```
127.0.0.1:5000/ota/arbeitsplatz:v5
```

### Wozu sie gut ist — und wozu nicht

**Nicht** für das Zurückdrehen einer Fassung. Das kann OTA ohne sie, über *Software → Fassungen →
Aktivieren*, und für einzelne Nutzer über die Zuteilung ([Kapitel 6](06-ressourcen-und-zuteilung.md)).

Wofür sie taugt:

- **Ein Host, der ein Image nie gebaut hat, kann es trotzdem starten.** Fehlt es lokal, holt der
  Agent es beim Sessionstart aus der Registry. Das ist die Voraussetzung für einen zweiten Host.
- **Fremdes Aufräumen trifft die Kopie nicht.** Kasms Agent hat auf diesem Host schon einmal jedes
  ihm unbekannte Image gelöscht ([Kapitel 9](09-kasm-images-und-registries.md)). Das Label-Problem
  ist umgangen — die Kopie ausserhalb des Stores ist der stabilere Schutz.

### Warum auf 127.0.0.1 und ohne TLS

Der Docker-Daemon läuft auf dem Host, nicht in einem Container — er muss die Registry erreichen, und
zwar unter derselben Adresse, die im Image-Namen steht. Auf `127.0.0.1` verlangt Docker **kein**
TLS. Das erspart Zertifikat, `daemon.json` und einen Neustart des Daemons.

Von aussen ist die Registry damit nicht erreichbar. Wer sie einem zweiten Host anbieten will, stellt
sie hinter Traefik und braucht dann Zertifikat und Zugangsschutz.

Abschalten lässt sie sich mit `OTA_REGISTRY=` (leer) in `deploy/.env`. Dann bleiben Images nur im
Docker-Store, wie vorher.

### Platz zurückholen ⚠️

Ein Löschen aus der Registry gibt den Platz **nicht** von selbst frei; dafür läuft eine eigene
Sammlung:

```bash
docker compose -f deploy/docker-compose.yml exec registry \
  registry garbage-collect /etc/docker/registry/config.yml
```

Der Preis der Registry ist genau das: Jede Fassung liegt zweimal, einmal im Docker-Store und einmal
hier. Bei 1,8 GB je Arbeitsplatz-Fassung und drei behaltenen Fassungen sind das rund 5 GB je
Workspace zusätzlich.

### Nachsehen, was drin liegt

```bash
curl -s http://127.0.0.1:5000/v2/_catalog
curl -s http://127.0.0.1:5000/v2/ota/arbeitsplatz/tags/list
```
