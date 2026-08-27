# ADR-002 · Nur der Agent fasst Docker und das Dateisystem des Hosts an

**Stand:** angenommen
**Datum:** 2026-08-27

## Ausgangslage

OTA startet Container, legt Profile an, baut Images und verwaltet eine gemeinsame Ablage. All das
braucht den Docker-Socket und Schreibrechte im Dateisystem des Hosts. Der Docker-Socket ist
effektiv Root auf dem Host: Wer ihn hat, kann einen privilegierten Container mit `/` als Mount
starten.

Gleichzeitig ist die API der Dienst, der Nutzereingaben verarbeitet: Anmeldedaten, Formulare,
Pfade, Image-Namen, hochgeladene Dateien. Sie ist die Angriffsfläche.

## Entscheidung

Die API bekommt den Docker-Socket **nicht**. Sie entscheidet, wer was darf, und schickt die
ausgeführte Arbeit an einen zweiten Dienst — den Agent. Dasselbe gilt für das Dateisystem des Hosts.

## Alternativen

**Alles in einem Dienst.** Ein Dienst weniger, ein Netz weniger, eine Schnittstelle weniger. Und
jede Lücke in der Eingabeverarbeitung — eine Pfadinjektion beim Hochladen, ein Deserialisierungsfehler,
eine übersehene Autorisierung — wäre unmittelbar Root auf dem Host. Der Abstand ist die ganze
Begründung.

**Docker-Socket-Proxy** (etwa `tecnativa/docker-socket-proxy`). Erlaubt nur bestimmte
HTTP-Methoden auf bestimmten Pfaden. Hilft gegen manches, aber `POST /containers/create` muss
erlaubt sein, damit OTA funktioniert — und damit ist der Weg zum privilegierten Container wieder
offen. Ein Filter auf Endpunkten ist kein Filter auf Absichten.

**Rootless Docker.** Sinnvoll und nicht ausgeschlossen. Es ersetzt diese Entscheidung aber nicht,
sondern ergänzt sie: Auch ohne Root will man nicht, dass der Dienst mit der grössten
Angriffsfläche direkt Container startet.

## Folgen

**Eine Schnittstelle mehr.** Zwischen API und Agent liegt HTTP im internen Netz. Sie ist nicht
öffentlich, aber sie ist da, und sie muss selbst richtig sein.

**Die Grenze muss gepflegt werden.** Es ist jederzeit bequem, „nur diesen einen Aufruf" in der API
zu machen. Deshalb steht die Regel im Kopf jeder betroffenen Datei, und deshalb liegen
`registry.py`, `shared.py`, `discover.py`, `backup.py` und `builder.py` im Agent — auch dort, wo
der Griff nach draussen nichts mit Docker zu tun hat.

**Der Agent muss der API misstrauen.** Er bekommt Pfade und Namen von einem Dienst, der sie von
Menschen bekommen hat. Deshalb prüft `shared.py` die Eindämmung nach dem Auflösen von Symlinks und
`registry.py` die erlaubte Wurzel, bevor es ein Symbol holt.
