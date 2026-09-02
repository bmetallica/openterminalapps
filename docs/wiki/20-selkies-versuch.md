# 20 · Selkies — der zweite Streaming-Weg

*Für Administratoren.* 🔨 **Versuch.** Der bisherige Weg über KasmVNC läuft
vollständig weiter und ist unverändert die Vorgabe.

## Worum es geht

KasmVNC spricht **RFB**: Es überträgt rechteckige Bildausschnitte, sobald sich
etwas ändert. Für Text und ruhige Oberflächen ist das genau richtig — wenig
Bandbreite, gestochen scharf. Für alles, was sich bewegt, ist es die falsche
Form: Ein Video, ein Scroll durch eine lange Datei, eine Zeichenfläche
zerfallen in nachziehende Kacheln.

**Selkies** kodiert statt dessen einen H.264-Strom und schickt ihn über
WebRTC. Das ist die Technik, mit der Spiele-Streaming arbeitet.

## Was der Versuch kostet

Ehrlich vorweg, denn es sind keine Kleinigkeiten:

| | KasmVNC | Selkies |
|---|---|---|
| Anwendungen | **je Anwendung ein Bildschirm**, umschaltbar in der Leiste | **ein Bildschirm je Sitzung** — alle Anwendungen darauf, wie an einem echten Rechner |
| Weg des Bildes | durch Traefik, ein Port | **an Traefik vorbei**, WebRTC über UDP |
| Zusätzliche Ports | keine | 3478 und 65500–65510 auf dem Host |
| Sitzungen gleichzeitig | beliebig viele | **eine** je Host (feste Ports, siehe unten) |
| Zwischenablage | OTAs Brücke zwischen den Displays | Selkies' eigene, im Bild eingebaut |
| Ton | über KasmVNC | über WebRTC |

Der erste Punkt ist der schwerwiegendste: **Das Arbeitsplatzmodell ist ein
anderes.** Bei KasmVNC läuft jede Anwendung auf einem eigenen X-Display, und
die Leiste schaltet um. Selkies überträgt genau einen Bildschirm; die
Anwendungen liegen darauf nebeneinander, wie auf einem Schreibtisch. Für
manche ist das besser, für andere schlechter — es ist jedenfalls nicht
dasselbe.

## Einrichten

```bash
scripts/build-base-image.sh              # ota/base-xfce:test, die Grundlage
docker build -t ota/base-selkies:test images/base-selkies
```

In `deploy/.env` muss stehen, unter welcher Adresse die **Browser** diesen
Host erreichen — nicht die eines Docker-Netzes:

```
OTA_SELKIES_TURN_HOST=192.168.66.224
```

Dann eine Vorlage anlegen mit `image_ref: ota/base-selkies:test` und
`stream_engine: selkies`. Alles andere bleibt wie bei jedem Arbeitsplatz:
Zuhause, Ablagen, Skeleton, Startskript, Rechte.

> **Eine Sitzung je Host.** Die TURN-Ports stehen fest; eine zweite
> Selkies-Sitzung fände sie belegt. Für den Versuch reicht das. Wird daraus
> ein Weg für alle, ist eine Portvergabe je Sitzung das Erste, was fehlt.

## Warum ein TURN-Server im Container läuft

WebRTC braucht einen Medienweg per UDP. Session-Container liegen in einem
internen Docker-Netz ohne veröffentlichte Ports — der Browser käme nicht
heran, und Traefik hilft nicht: Es spricht HTTP, nicht UDP.

Vermittelt wird deshalb über einen TURN-Server. Er läuft **im
Session-Container**, nicht im Stack: So gehört er zur Sitzung, und ein Fehler
trifft eine statt aller. Der Agent reicht seine Ports nach aussen durch.

Die Weboberfläche und die Signalisierung laufen weiterhin über Traefik, mit
derselben Anmeldung und demselben Basic-Auth-Header wie bei KasmVNC. **Nur der
Medienstrom geht daran vorbei.**

## Drei Fallen, alle beim Bauen aufgetreten

1. **Der Client baut seine Adressen aus der Wurzel.** `fetch("/turn")` und
   `wss://host/<erstes Pfadsegment>/signalling/` — beides zeigt nicht dorthin,
   wo eine OTA-Session liegt (`/s/<kennung>/`, zwei Segmente). Ohne Korrektur
   baut sich die Seite vollständig auf, das Bild bleibt schwarz, und in der
   Konsole steht ein einzelnes `401` von OTAs eigener Schnittstelle. Beide
   Stellen werden beim Bauen des Images ersetzt
   (`images/base-selkies/patches/gst-web-pfad.py`) — und wenn die Zeilen sich
   in einer neuen Fassung ändern, **bricht der Build ab**, statt still das
   Falsche zu tun.

   Es ist derselbe Fehler wie seinerzeit bei KasmVNC, das seinen
   Websocket-Pfad ebenfalls an die Wurzel hängte ([Kapitel 12](12-fehlersuche.md)).

2. **`cvt` gibt es in Ubuntu 24.04 nicht mehr.** Selkies passt die Auflösung
   an das Browserfenster an und holt sich die Modeline damit; kein Paket
   liefert es noch (`apt-file` sagt: keins). Ohne Ersatz bleibt der ferne
   Bildschirm auf der vollen Grösse des Framebuffers stehen — 3840×2160, in
   ein 1440er Fenster gequetscht. Das Image bringt eine eigene Rechnung mit,
   geprüft am Referenzwert für 1920×1080.

3. **coturn darf nicht nach `/var/run` schreiben.** Der Container läuft als
   Nutzer 1000. Ohne `pidfile=/tmp/...` startet der TURN-Server gar nicht, und
   das Bild bleibt schwarz — die Meldung steht in seinem eigenen Protokoll,
   nicht dort, wo man sucht.

## Wie es weitergeht

Der Versuch beantwortet die Frage „geht es überhaupt". Was er **nicht**
beantwortet, und was vor einer Entscheidung gemessen gehört:

- **Wie viel besser ist es wirklich?** Latenz und Bildqualität nebeneinander,
  auf denselben Inhalten, im selben Netz.
- **Was kostet es an CPU?** H.264 in Software (x264) ist nicht umsonst. Auf
  einer Maschine ohne GPU zahlt das jede Sitzung.
- **Trägt das Modell „ein Bildschirm" den Alltag** — oder fehlt der
  Anwendungsumschalter dann doch?

Solange das nicht gemessen ist, bleibt KasmVNC die Vorgabe.
