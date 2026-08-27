# 12 · Fehlersuche

Die hier dokumentierten Fälle sind beim Aufbau tatsächlich aufgetreten. Sie haben gemeinsam, dass sie
**lautlos** scheitern — nichts stürzt ab, es funktioniert nur nicht.

## Zwischenablage funktioniert nicht

In dieser Reihenfolge prüfen:

**1 · Läuft die Seite über HTTPS?**
`navigator.clipboard` existiert nur im Secure Context. Über `http://` ist die Zwischenablage
technisch nicht verfügbar. → [Kapitel 10](10-zertifikate-und-https.md)

**2 · Erlaubt das iframe es?**
Der Session-Viewer bettet den Stream ein. Ohne `allow="clipboard-read; clipboard-write"` blockiert die
Permissions-Policy den Zugriff — **ohne Fehlermeldung**. Das ist die häufigste Ursache in
Eigenbauten.

**3 · Nimmt der Server es zurück?**
```bash
curl -sI --cacert deploy/certs/ota-ca.crt https://<host>:8443/ | grep -i permissions-policy
```
Erwartet: `clipboard-read=(self), clipboard-write=(self), …`
Fehlt der Header oder ist er restriktiv, macht er alles andere wirkungslos.

**4 · Firefox?**
Firefox stellt Webseiten `navigator.clipboard.readText()` nicht zur Verfügung. Wer nur gegen Chrome
entwickelt, merkt das erst beim ersten Firefox-Nutzer. OTA nutzt dort das `paste`-Ereignis.

**5 · Hat die Session den Fokus?**
Ohne Fokus im iframe erreichen Tastenanschläge den Stream nicht.

**6 · Ist es im Workspace erlaubt?**
Rechte → Zwischenablage. Kopieren und Einfügen sind getrennt schaltbar.

**7 · Zwischen zwei Apps im selben Arbeitsplatz?**
Jede App läuft auf einem eigenen X-Display mit eigener Zwischenablage. Dafür läuft die Brücke im
Container. Prüfen, ob sie läuft — und ob das Kopieren in den Rechten überhaupt erlaubt ist, denn
sonst startet sie bewusst nicht. → [Kapitel 4](04-zwischenablage.md)

## Traefik erzeugt keine Route — alles gibt 404

**Ursache A: Docker-API-Version.**
Docker 29 hat alle API-Versionen unter 1.40 abgeschafft. Ältere Traefik-Versionen melden sich fest
mit 1.24. Der Docker-Provider bleibt dann **völlig stumm** — keine Route entsteht, ohne dass an der
Konfiguration etwas falsch aussieht.

```bash
docker logs ota-traefik 2>&1 | grep "too old"
# "client version 1.24 is too old. Minimum supported API version is 1.40"
```

Abhilfe: Traefik ≥ v3.7 (handelt die Version aus) und `DOCKER_API_VERSION` in `deploy/.env`.

**Ursache B: Der Container gilt als nicht gesund.**
Traefik ignoriert Container, deren Healthcheck nicht grün ist — kommentarlos.

```bash
docker logs ota-traefik 2>&1 | grep -i "filtering"
# "Filtering unhealthy or starting container: web-ota-…"
docker inspect ota-web --format '{{.State.Health.Status}}'
```

**Ursache C: CLI-Argumente werden ignoriert.**
Traefik liest die statische Konfiguration aus **genau einer Quelle**. Sobald eine `traefik.yml`
existiert, werden `command:`-Argumente im Compose **vollständig ignoriert** — sie werden nicht
zusammengeführt. Alles Statische gehört in die Datei.

## Container bleibt „unhealthy", obwohl der Dienst läuft

Klassiker: Der Healthcheck fragt `http://localhost/...`, aber `localhost` löst im Container zuerst
auf `::1` auf, während der Dienst nur auf IPv4 lauscht.

```bash
docker inspect <container> --format '{{range .State.Health.Log}}{{.Output}}{{end}}'
# "wget: can't connect to remote host: Connection refused"
docker exec <container> sh -c 'netstat -tln'
# tcp 0.0.0.0:80 LISTEN   ← nur IPv4
```

Abhilfe: im Healthcheck **`127.0.0.1`** statt `localhost`.

Bei Traefik selbst braucht `traefik healthcheck --ping` zusätzlich einen aktivierten `ping:`-Abschnitt
in der statischen Konfiguration — fehlt er, bleibt der Container dauerhaft unhealthy.

## Browser warnt vor dem Zertifikat

Normal, solange die lokale CA nicht importiert ist. → [Kapitel 10](10-zertifikate-und-https.md)

Bleibt die Warnung **nach** dem Import, fehlt meist der passende Name im Zertifikat:

```bash
openssl x509 -in deploy/certs/ota.crt -noout -ext subjectAltName
```

Moderne Browser ignorieren den Common Name vollständig — der aufgerufene Name muss im SAN stehen.
Wer über eine IP zugreift, braucht dort einen `IP Address:`-Eintrag, kein `DNS:`.

## Session startet nicht

**Zu wenig Speicher.** OTA prüft vor dem Start den tatsächlich freien Speicher und lehnt mit einer
Meldung ab, statt den Host in den OOM-Kill laufen zu lassen. Prüfen: `free -h` und die
Kapazitätsanzeige über der Workspace-Liste.

**Image fehlt.** Beim ersten Start eines neuen Workspace wird es gezogen. Ein 6-GB-Image braucht
seine Zeit; im Startdialog steht die Phase.

**Zu viele Sessions.** Das Limit je Nutzer steht in den Gruppen-Einstellungen.

## Kein Bild, obwohl die Session läuft

Fast immer die WebSocket-Verbindung. Steht ein zusätzlicher Reverse Proxy davor, muss er
WebSocket-Upgrades durchlassen und `X-Forwarded-Proto: https` setzen. Ohne das erscheint kein Bild.


## Session lädt, aber es kommt kein Bild

Die Seite erscheint, bleibt aber schwarz oder zeigt „Connecting…". Fast immer
der WebSocket.

**Ursache A: Der Client sucht den WebSocket an der falschen Stelle.**
Der KasmVNC-Client hängt seinen Pfad an die **Wurzel** der Seite, nicht an den
aktuellen Pfad. Ohne Gegenmaßnahme versucht er `wss://host/websockify` — das
landet bei der Weboberfläche, die für jeden Pfad die Anwendung mit HTTP 200
ausliefert. Kein Upgrade, kein Bild, und **keine Fehlermeldung im Server-Log**.

OTA gibt dem Client deshalb den vollen Pfad als URL-Parameter mit:

```
/s/<session-id>/?path=s/<session-id>/websockify
```

Erkennbar in der Browser-Konsole:
```
WebSocket connection to 'wss://…/websockify' failed:
Error during WebSocket handshake: Unexpected response code: 200
```

**Ursache B: Ein vorgelagerter Proxy reicht WebSockets nicht durch.**
Er muss Upgrade-Anfragen weiterleiten und `X-Forwarded-Proto: https` setzen.

## Alle Session-Routen verschwinden auf einmal

Symptom: `/s/<id>/` antwortet plötzlich mit der Weboberfläche statt mit dem
Stream, und im Traefik-Dashboard fehlen sämtliche Session-Router.

```bash
docker logs ota-traefik 2>&1 | grep "cannot be linked"
# "Router s-… cannot be linked automatically with multiple Services: [...]"
```

**Ursache**: Sobald ein Container mehr als einen Traefik-Dienst definiert — beim
Arbeitsplatz sind es einer je App-Display —, muss **jeder Router seinen Dienst
ausdrücklich benennen** (`traefik.http.routers.<name>.service=<name>`). Fehlt
das, verwirft Traefik **alle** Router dieses Containers, nicht nur die
mehrdeutigen.

Weil eine solche Anfrage sonst auf der Weboberfläche landet und dort mit 200
beantwortet wird, sähe das von aussen aus wie eine Session ohne Anmeldung. OTA
legt deshalb einen Schutzwall über `/s/` (`deploy/traefik/dynamic/session-guard.yml`):
Er greift nur, wenn kein Session-Router passt, verlangt trotzdem eine Anmeldung
und antwortet dann mit einer verständlichen Meldung statt mit der Anwendung.

## Eine App im Arbeitsplatz startet nicht

```bash
docker exec <session-container> ls /tmp/.X11-unix/     # welche Displays laufen
docker exec <session-container> cat /tmp/ota-display-3.log
docker exec <session-container> cat /tmp/ota-app-<slug>.log
```

Fehlt die Datei `ota-app-<slug>.log` vollständig, wurde die Anwendung nie
gestartet. Fehlt `X<n>` unter `/tmp/.X11-unix/`, kam das Display nicht hoch.

**Zwei häufige Ursachen:**

*Die Anwendung ist eine Einzelinstanz.* VS Code, Chrome und Thunderbird laufen nur
einmal je Nutzer. Ein zweiter Aufruf meldet sich bei der laufenden Instanz und
beendet sich — das Logfile bleibt leer, das Display schwarz. Prüfen mit
`docker exec <container> pgrep -a <anwendung>`. Lösung: im App-Katalog das feste
Display eintragen (Handbuch, Kapitel 7).

*Der Selbsttreffer beim Prozessabgleich.* `pgrep -f <name>` findet das eigene
Startskript, weil dessen Kommandozeile den Namen enthält — das Skript hält sich
dann selbst für die laufende Anwendung und beendet sich. OTA prüft deshalb über
die Fensterliste des Displays, nicht über Prozessnamen. Dieselbe Falle gilt für
`pkill -f`: Es bringt die eigene Shell um. Deshalb wird die
Zwischenablage-Brücke ausschliesslich über ihre PID-Datei gesteuert.

## Das Tastenkürzel Strg+Alt+Shift wirkt im Stream nicht

Das ist so und lässt sich nicht beheben. Der ferne Desktop beansprucht die
Tastatur für sich — sonst könnte man dort keine Tastenkombination benutzen.
Gemessen wurde: Control und Alt erreichen das eingebettete Fenster noch, Shift
und Buchstabentasten nicht mehr.

**Der Griff am rechten Rand** liegt im Elternfenster und funktioniert immer. Er
ist der eigentliche Weg zur Kontrollleiste; das Kürzel ist die Abkürzung für
alles ausserhalb des Streams.

## Golden Image ist nach dem Bau wieder verschwunden

Der Build läuft durch, meldet Erfolg — und beim ersten Sessionstart heisst es
„Image liegt nicht auf diesem Host".

```bash
docker logs kasm_agent --since 5m | grep -i prune
# "Searching for images to prune with mode: (Aggressive)"
# "Docker image id (...): with tags (['ota/...']): is not needed."
# "Successfully pruned unneeded Docker image id (...)"
```

**Ursache**: Läuft Kasm Workspaces auf demselben Docker-Host, räumt dessen Agent
im Modus **„Aggressive"** etwa alle 30 Sekunden auf und löscht **jedes Image, das
er nicht kennt** — auch unsere Golden Images.

OTA erkennt das inzwischen selbst: 45 Sekunden nach einem erfolgreichen Build wird
nachgesehen, ob das Image noch da ist. Fehlt es, wird der Build auf *fehlgeschlagen*
gesetzt und das Log erklärt den Grund.

**Abhilfe, eine von beiden:**
- In Kasm unter *Infrastructure → Servers* die Aufräum-Einstellung von „Aggressive"
  auf eine mildere Stufe setzen.
- Golden Images erst bauen, nachdem Kasm abgelöst ist.

Alles andere am Parallelbetrieb ist davon **nicht** betroffen: Sessions, Streams,
Nutzer und Zuweisungen laufen unbeeinträchtigt nebeneinander.

## Build meldet Erfolg, das Image taucht nie in `docker images` auf

Anderes Symptom, andere Ursache: Auf einem Host mit **containerd-Image-Store** legt
der klassische Docker-Builder bei Multi-Plattform-Basisimages kein benutzbares Image
im Store ab.

```bash
docker info | grep -i snapshotter
#   driver-type: io.containerd.snapshotter.v1
```

OTA baut deshalb über `docker buildx build --load`. Wer eigene Build-Skripte schreibt,
sollte dasselbe tun — `DOCKER_BUILDKIT=0` oder das Python-SDK reichen hier nicht.

## Nützliche Befehle

```bash
cd /opt/openterminalapps/deploy

docker compose ps                                   # Zustand aller Dienste
docker compose logs -f --tail=100 ota-traefik       # Traefik mitlesen
curl -s http://127.0.0.1:8449/api/http/routers | python3 -m json.tool   # aktive Routen
docker inspect <container> --format '{{.State.Health.Status}}'

# Traefik ausführlich, wenn Routen fehlen: level: DEBUG in traefik.yml,
# danach wieder auf INFO zurücksetzen — DEBUG ist sehr gesprächig.
```
