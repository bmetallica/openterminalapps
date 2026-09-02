# 12 · Fehlersuche

Die hier dokumentierten Fälle sind beim Aufbau tatsächlich aufgetreten. Sie haben gemeinsam, dass sie
**lautlos** scheitern — nichts stürzt ab, es funktioniert nur nicht.

## „Diese Sitzung läuft nicht mehr", obwohl sie gerade gestartet wurde

Diese Seite kommt vom Schutzwall aus `deploy/traefik/dynamic/session-guard.yml`. Er antwortet, wenn
für einen `/s/…`-Pfad **kein** Session-Router passt.

Das passierte früher direkt nach dem Start: Traefiks Docker-Anbindung bemerkt einen neuen Container
erst beim nächsten Durchlauf, die Oberfläche öffnete den Stream aber sofort. In der Lücke dazwischen
gab es keine Route.

**Behoben:** Die API meldet eine Session erst als `running`, wenn Traefik ihre Route kennt
(`_wait_for_route()` in `api/ota/routers/sessions.py`), und der Agent wartet zusätzlich, bis
KasmVNC im Container Verbindungen annimmt. Bleibt die Route aus, steht die Session auf `starting`
statt auf `running` — das Dashboard versucht es dann weiter, statt eine Sackgasse zu zeigen.

Kommt die Seite trotzdem, ist die Session wirklich weg: beendet, aufgeräumt oder der Container
gestorben. Ein Blick in **Betrieb → Sessions** zeigt, was gilt.

## Sessions scheitern sprunghaft — und jedes Mal woanders

Das hier war der unangenehmste Fall bisher, weil er nie zweimal gleich aussah. Die Symptome, alle
vom selben Grund:

- `Startskript in ota-s-… endete mit 137` — das ist SIGKILL
- ein Einmal-Skript, das nichts zurückgibt, und OTA bucht es folgerichtig als „nicht gelaufen"
- `KasmVNC in ota-s-… war nach 40s noch nicht bereit`
- drei 409er direkt danach: `container … is not running`
- in der Oberfläche: „Der Arbeitsplatz läuft gerade nicht", obwohl er gerade gestartet wurde

Gemeinsam war nur, dass es **unter Last** häufiger passierte und bei einem ruhigen Rechner kaum.
Genau das führt in die Irre: Es sieht nach Speichermangel aus. War es nicht — der Container
benutzte 231 MB von 3 GB, und nichts wurde vom Kernel wegen Speichers getötet.

**Die Ursache** lag zwei Ebenen weiter oben. Die API legte die Session-Zeile mit `flush` an, nicht
mit `commit`. Ein `flush` schreibt nur *innerhalb* der eigenen Transaktion; für jede andere
Verbindung gab es die Session bis zum abschließenden `commit` nicht — und der kam erst, wenn der
Container vollständig stand: Skeleton kopiert, Einmal-Skripte gelaufen, Startskript durch, KasmVNC
bereit. Unter Last dauert das über eine Minute.

In genau diesem Fenster läuft der **Aufräumer** (`_reap_once` in `api/ota/main.py`, minütlich). Er
sieht einen Container mit OTA-Kennzeichnung, findet in der Datenbank keine Session dazu — und
entfernt ihn. Mitten im Start. Je länger der Start dauerte, desto wahrscheinlicher der Treffer.

**Behoben** an beiden Enden:

1. Die Session-Zeile wird **committet, bevor der Container entsteht**. Ab da ist sie für jede
   Verbindung da.
2. Der Aufräumer vergleicht zusätzlich die **Session-Kennung** aus dem Container-Label, nicht nur
   die `container_id` — die steht während des Starts noch nicht in der Zeile.

Geprüft wird die Ursache und nicht das Symptom: `scripts/test-authz.sh` startet eine Session im
Hintergrund und sieht währenddessen mit einer **zweiten** Verbindung in der Datenbank nach, ob die
Zeile da ist.

> **Die Lehre daraus**, falls etwas Ähnliches auftaucht: Wenn Fehler sprunghaft sind und unter Last
> häufiger, ist die Versuchung groß, an Zeitgrenzen zu drehen. Das hätte hier das Fenster nur
> verschoben. Die Frage, die weiterhalf, war nicht „warum ist es zu langsam", sondern „wer bringt
> den Prozess um".

## Der Stream bricht nach Minuten ab, obwohl die Grenze bei Stunden steht

Zwei Ursachen, die zusammen genau das Bild ergaben: Man sieht einem Build zu oder liest ein langes
Dokument, fasst dabei weder Maus noch Tastatur an — und irgendwann ist das Bild weg und kommt nicht
wieder. In **Betrieb → Sessions** steht die Session weiter auf `running`.

**Erstens: Der Client hatte seine eigene Uhr.** KasmVNC trennt von sich aus nach 20 Minuten *ohne
Eingabe*; gezählt werden nur Maus und Tastatur, nicht der Bildinhalt. Zusehen zählt dort als
Nichtstun. Weil `reconnect` im Client aus ist, blieb es danach schwarz.

```js
// aus dem Client, /usr/share/kasmvnc/www/assets/ui-*.js
const s = (Date.now() - rfb.lastActiveAt) / 1000
let l = 1200                                     // 20 Minuten, wenn nichts gesetzt ist
if (Number.isFinite(parseFloat(rfb.idleDisconnect))) l = parseFloat(rfb.idleDisconnect) * 60
if (s > l) window.location.replace("disconnect…")
```

**Behoben:** Über die Laufzeit einer Session entscheidet OTA, nicht der Client. Der Viewer stellt
die Uhr beim Verbinden auf ein Jahr (`set_idle_timeout` in
`web/src/screens/SessionViewer.tsx`), und die Stream-Adresse hebt sie zusätzlich auf 60 Minuten
(`STREAM_ARGS` in `api/ota/routers/sessions.py`). Solange ein Fenster offen ist, kommt alle 30
Sekunden ein Herzschlag; erst wenn der ausbleibt, greift `idle_minutes` der Vorlage.

Eine Falle dabei: `idle_disconnect` ist im Client ein Auswahlfeld mit genau vier Werten
(10, 20, 30, 60). Ein anderer Wert in der Adresse wird nicht übernommen, sondern fällt auf den
**ersten** Eintrag zurück — aus einem gut gemeinten `525600` wurden gemessene 10 Minuten. Eine `0`
ist noch schlimmer: Die Grenze ist dann null Sekunden, und die Verbindung fällt sofort. Deshalb der
Umweg über die Nachricht an den laufenden Client, die am Auswahlfeld vorbeigeht.

**Zweitens: Ein Abbruch heilte nicht.** Riss die Verbindung aus einem Grund ab, den OTA nicht kennt
— ein Zwischenstück im Netz, das eine schweigende Verbindung abräumt, ein Rechner, der schlafen geht
—, blieb KasmVNCs eigener Abbruchbildschirm im iframe stehen. Der ist ausgeblendet; im Fenster sah
man nur ein eingefrorenes Bild.

**Behoben:** Der Viewer beobachtet die Verbindung von aussen. Solange sie steht, trägt das
Wurzelelement im iframe die Klasse `noVNC_connected`; ihr Verschwinden ist das Signal. Danach lädt
er den Stream neu, mit wachsendem Abstand und höchstens acht Mal, und zeigt währenddessen ein
Banner mit einem Knopf für „sofort versuchen". Ist die Session inzwischen wirklich beendet, sagt er
das, statt weiter zu versuchen.

Gemessen: Abbruch erkannt nach 5 Sekunden, wieder verbunden im zweiten Versuch, Banner von selbst
weg. Geprüft wird der ganze Weg in `tests/e2e.mjs` (Abschnitt Session-Viewer).

## Eine Anwendung lässt sich nicht mehr starten und der Tab bleibt tot

Stirbt das X-Display einer Anwendung im Arbeitsplatz — Absturz, `Xvnc` weg —, führte OTA sie
weiterhin als `running`. Der Startknopf tat dann scheinbar nichts: Der Aufruf sah den Eintrag, hielt
alles für in Ordnung und kehrte sofort zurück. Damit war die Anwendung für immer tot.

**Behoben:** Der Start sieht beim Agent nach, ob es das Display wirklich noch gibt
(`_display_lebt()` in `api/ota/routers/sessions.py`). Fehlt es, wird der Eintrag auf `stopped`
gesetzt und die Anwendung neu aufgemacht. Antwortet der Agent gar nicht, gilt das Display als
lebendig — eine Störung beim Nachsehen darf keine laufende Anwendung abräumen.

## Zwischenablage funktioniert nicht

In dieser Reihenfolge prüfen:

**1 · Läuft die Seite über HTTPS?**
`navigator.clipboard` existiert nur im Secure Context. Über `http://` ist die Zwischenablage
technisch nicht verfügbar. → [Kapitel 10](10-zertifikate-und-https.md)

**2 · Erlaubt das iframe es?**
Der Session-Viewer bettet den Stream ein. Ohne `allow="clipboard-read; clipboard-write"` blockiert die
Permissions-Policy den Zugriff — **ohne Fehlermeldung**. Das ist die häufigste Ursache in
Eigenbauten.

**2b · Hat der Client die Zwischenablage im iframe abgeschaltet?**
KasmVNC tut das von sich aus, sobald er nicht die oberste Seite ist. Im Viewer die Kontrollleiste
des Streams öffnen und nachsehen, oder in der Browser-Konsole:

```js
const d = document.querySelector('.viewer__frame').contentDocument
d.getElementById('noVNC_setting_clipboard_down').checked   // muss true sein
```

Ist der Wert `false`, fehlen die Parameter in der Stream-Adresse. Sie muss
`…&clipboard_up=1&clipboard_down=1` enthalten. Der Weg **aus der Session heraus** ist sonst tot,
und zwar völlig lautlos: kein Fehler, keine Konsolenmeldung, das Feld bleibt leer. Der Weg **in die
Session hinein** funktioniert davon unabhängig weiter — wenn also nur eine Richtung fehlt, ist das
hier die erste Vermutung.

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

## VS Code öffnet sich, aber der Bildschirm bleibt leer

**Symptom:** Im Arbeitsplatz startet VS Code, der Stream verbindet sich — und es kommt kein Bild.
Oder: Der Container füllt sich ohne erkennbaren Grund mit Arbeitsspeicher.

**Ursache (behoben am 2026-08-27), zwei Schichten:**

**1 · Das geerbte Startskript.** Kasm-Images für einzelne Anwendungen bringen ein
`/dockerstartup/custom_startup.sh` mit, das „ihre" Anwendung startet. `vnc_startup.sh` beaufsichtigt
dieses Skript und **startet es alle drei Sekunden neu**, sobald es sich beendet. In einem davon
abgeleiteten Arbeitsplatz-Image ist das verheerend: Das Skript rief `code` auf, VS Code ist
einzelinstanzig, die zweite Instanz reichte den Aufruf an die erste weiter und beendete sich —
worauf die Aufsicht sie erneut startete. Nach sechs Minuten: 119 leere VS-Code-Fenster, 2,5 GB
belegt, schwarzer Bildschirm.

OTA hängt in Arbeitsplatz-Containern jetzt ein Ersatzskript darüber, das nichts startet, und neu
gebaute Arbeitsplatz-Images bringen es gleich mit. Anwendungen startet der Agent auf Zuruf.

**2 · Der gespeicherte Fensterzustand.** VS Code merkt sich seine offenen Fenster und stellt sie
beim nächsten Start wieder her. Nach einem solchen Fenstersturm steht die Zahl im Profil — und der
Sturm wiederholt sich bei jedem Start, auch nachdem die Ursache behoben ist.

**Reparatur eines betroffenen Profils.** Die Reihenfolge ist wichtig: erst VS Code beenden, dann die
Datei ändern. Sonst schreibt VS Code beim Beenden seinen alten Zustand zurück.

```bash
CN=<container>   # docker ps --filter "label=ota.session_id"

docker exec -u 1000 "$CN" pkill -f /usr/share/code/code
sleep 3

docker exec -i -u 1000 "$CN" python3 - <<'EOF'
import json, pathlib
p = pathlib.Path("/home/kasm-user/.config/Code/User/globalStorage/storage.json")
d = json.loads(p.read_text())
d.setdefault("windowsState", {})["openedWindows"] = []
p.write_text(json.dumps(d))
EOF
```

Danach die Anwendung im Dashboard neu starten. Wie viele Fenster wirklich offen sind, zeigt

```bash
docker exec "$CN" bash -lc 'export HOME=/home/kasm-user XAUTHORITY=$HOME/.Xauthority
  DISPLAY=:1 wmctrl -l'
```

Genau zwei Zeilen sind richtig: `Desktop` (das Hintergrundbild) und die Anwendung.

## Zwei Arbeitsplätze lassen sich nicht gleichzeitig starten

**Meldung:** „… läuft schon und benutzt dasselbe Zuhause."

Das ist keine Störung, sondern Absicht. Alle Workspaces mit Persistenz **Pro Nutzer** teilen sich
dasselbe `/home/kasm-user`. Zwei laufende Container auf einem Zuhause haben in der Praxis zweimal
Schaden angerichtet:

- Der Startvorgang der Kasm-Images schreibt `~/.kasmpasswd` neu — der zweite Container entwertete
  damit die Zugangsdaten des ersten (siehe Abschnitt zu 401).
- VS Code legt seinen Steuerkanal als Socket im Profil ab. Der zweite Container fand ihn und
  schickte seine Fenster in den *ersten* Container.

**Was tun:** Entweder den anderen Arbeitsplatz beenden — oder dem zweiten Workspace unter
*Ressourcen → Persistentes Profil* die Einstellung **Pro Workspace** geben. Dann bekommt er sein
eigenes Zuhause und beide laufen nebeneinander. Der Preis: getrennte Einstellungen und Projekte.

## „Die Daten konnten nicht geladen werden" nach einem Update

**Ursache (behoben am 2026-08-27):** `Base.metadata.create_all()` legt fehlende **Tabellen** an,
fehlende **Spalten** nicht. Eine neue Spalte im Modell bedeutete deshalb: Der Start meldete „Schema
bereit", und danach scheiterte jede Abfrage auf diese Tabelle mit

```
column templates.start_script does not exist
```

Für den Anwender sah das aus wie „Unerwarteter Fehler. Der Vorgang wurde abgebrochen."

**Behoben:** Beim Start werden fehlende Spalten ergänzt (`api/ota/schema_sync.py`). Was dabei
passiert, steht im Protokoll:

```bash
docker compose -f deploy/docker-compose.yml logs api | grep "Spalte ergänzt"
```

Ergänzt wird nur, **hinzugefügt** — nie gelöscht, nie umbenannt, nie ein Typ geändert. Eine Spalte,
die im Modell fehlt, kann ein vergessener Rest sein oder das Zeichen dafür, dass die Datenbank
neuer ist als der Code; im zweiten Fall wäre Löschen Datenverlust. Was sich nicht gefahrlos
ergänzen lässt — eine Spalte ohne Vorgabewert, die nicht leer sein darf — wird gemeldet und
verlangt eine Migration von Hand.

## „Es sind höchstens 6 Anwendungen gleichzeitig möglich", obwohl keine läuft

**Ursache (behoben am 2026-08-27):** Die Displaynummer wurde aus der **Position im App-Katalog**
abgeleitet. Damit galt die Grenze nicht für gleichzeitig offene Anwendungen, sondern für die Grösse
des Katalogs: Ab dem siebten Eintrag liess sich eine Anwendung nie starten. Alphabetisch traf es
meist VS Code und VSCodium.

**Behoben:** Vergeben wird das erste freie Display, gemessen an den laufenden Streams. Der Katalog
darf beliebig gross sein; gleichzeitig offen sind weiterhin höchstens sechs.

## Eine Anwendung öffnet, der Bildschirm bleibt schwarz

Zuerst das Protokoll der Anwendung im Container ansehen:

```bash
docker exec <container> cat /tmp/ota-app-<slug>.log
```

**Der häufigste Fund bei Electron- und Chromium-Anwendungen** (VS Code, VSCodium, Chrome, viele
Chat-Programme):

```
Failed to move to new namespace: ... errno = Operation not permitted
FATAL: Check failed: . : Invalid argument (22)
```

Diese Programme legen ihre Sandbox über PID-Namespaces an; im Container scheitert das. Sie brauchen
`--no-sandbox`. Die `.desktop`-Datei sagt darüber nichts — sie ist für einen normalen Desktop
geschrieben.

OTA erkennt das inzwischen beim *Im Image nachsehen*: Ein Programm, neben dem eine Datei
`chrome-sandbox` liegt, bekommt den Schalter von selbst. Steht er in einem älteren Katalogeintrag
noch nicht, genügt ein erneutes Durchsehen und Übernehmen.

## Der Desktop ist leer — kein Menü, keine Leiste

Dann fehlt `xfce4-panel` im Golden Image. Frühe Arbeitsplatz-Images hatten es bewusst entfernt, weil
Anwendungen über OTA gestartet werden; für den Desktop als Ansicht braucht es die Leiste aber.

Nachrüsten über *Software → Pakete*: `xfce4-panel` und `xfce4-whiskermenu-plugin`, bauen,
aktivieren. Laufende Sessions bekommen es beim nächsten Start.

## Eine laufende Session antwortet plötzlich mit 401

**Symptom:** Ein Arbeitsplatz läuft, das Bild stand eben noch — und auf einmal kommt für jeden
seiner Streams `401`. Neu anmelden hilft nicht. Der Container läuft weiter, `docker ps` zeigt ihn,
die Anwendungen darin arbeiten.

**Ursache (behoben am 2026-08-27):** Alle Sessions eines Nutzers teilen sich dasselbe
`/home/kasm-user` — das ist der Sinn des persistenten Profils. Der Startvorgang der Kasm-Images
schreibt aber bei *jedem* Containerstart `~/.kasmpasswd` aus `VNC_PW` neu. Startete jemand eine
zweite Session, überschrieb sie damit das Passwort der bereits laufenden ersten. Deren Traefik-Regel
schickte weiterhin die alten Zugangsdaten — KasmVNC lehnte sie ab.

Der Fehler war unauffällig, weil an der laufenden Session nichts passiert war: kein Neustart, kein
Fehler im Log, nur 401 aus dem Nichts.

**Behebung:** Das VNC-Passwort hängt jetzt am Profil und nicht mehr an der Session
(`vnc_secret()` in `api/ota/security.py`). Wer sich dasselbe Zuhause teilt, teilt sich den Zugang —
und ein Überschreiben schreibt denselben Wert.

**Prüfen, ob es wieder auftritt:**

```bash
# Zeigt der Container ein PID-File mit fremdem Hostnamen, hat ein anderer
# Container in dasselbe Profil geschrieben.
docker exec <container> bash -c 'hostname; ls /home/kasm-user/.vnc/*.pid'
```

Stimmen Hostname und PID-Datei nicht überein, sind zwei Container auf demselben Profil — das ist
normal. Kommt dann trotzdem 401, sind die Passwörter auseinandergelaufen; die betroffenen Sessions
einmal beenden und neu starten.

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

**Ursache**: Läuft Kasm Workspaces auf demselben Docker-Host, räumt dessen Agent
im Modus „Aggressive" alle 30 Sekunden auf. Er löscht dabei **genau die Images,
die das Label `com.kasmweb.image=true` tragen** und nicht in seiner Datenbank
stehen. Ein von einem Kasm-Image abgeleitetes Golden Image **erbt dieses Label**
und wird deshalb als verwaiste Workspace-Version eingestuft.

```bash
docker logs kasm_agent --since 5m | grep -i prune
# "Docker image id (...): with tags (['ota/...']): is not needed."
# "Successfully pruned unneeded Docker image id (...)"
```

**Behoben.** OTAs Builder löscht das Label in jedem erzeugten Dockerfile:

```dockerfile
LABEL com.kasmweb.image="" \
      org.opencontainers.image.title="OpenTerminalApps Golden Image"
```

Images ohne dieses Label betrachtet Kasm gar nicht erst. Damit laufen OTA und
Kasm dauerhaft nebeneinander, **ohne dass an Kasm etwas umgestellt werden muss**.

Prüfen lässt sich das am gebauten Image:

```bash
docker image inspect ota/<name>:v1 \
  --format '{{index .Config.Labels "com.kasmweb.image"}}'
# leer = richtig.  "true" = das Image wird gelöscht werden.
```

OTA merkt es ausserdem selbst: 45 Sekunden nach einem erfolgreichen Build wird
nachgesehen, ob das Image noch da ist. Fehlt es, gilt der Build als
fehlgeschlagen und das Log nennt den Grund.

**Rückfallebene**, falls ein anderes System nach anderen Regeln aufräumt: Ein
Build kann fremde Aufräumdienste für seine Dauer anhalten
(`pause_foreign_cleanup`, Vorgabe `kasm_agent`). Sie werden in jedem Fall wieder
gestartet — auch wenn der Build scheitert.

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

## Ein Workspace ist plötzlich bei niemandem mehr im Dashboard

**Symptom.** Der Workspace steht in der Verwaltung, ist eingeschaltet, das Image liegt da — und
trotzdem sieht ihn kein Nutzer mehr. Auch kein Fehler, nirgends.

**Ursache.** Seine Gruppenzuweisung ist leer. Bis zum 2026-08-28 reichte dafür ein
`PUT /api/templates/{id}`, das `group_ids` gar nicht erwähnte: Ein fehlendes Feld galt als leere
Liste, und wer nur eine Einstellung ändern wollte, nahm dabei allen die Zuweisung weg.

**Nachsehen.**

```bash
curl -sk -b cookies.txt https://<host>:8443/api/templates \
  | python3 -c 'import sys,json;[print(t["slug"], t["group_ids"]) for t in json.load(sys.stdin)]'
```

Steht dort `[]`, ist es das.

**Reparatur.** Im Workspace-Editor unter *Zuteilung* die Gruppe wieder setzen.

**Behoben.** `group_ids` ist jetzt `None`-fähig: nicht mitgeschickt heißt „lass stehen", eine leere
Liste heißt „niemand mehr". Eine Prüfung in `scripts/test-authz.sh` hält das fest.

## Firefox meldet „CanCreateUserNamespace() clone() failure: EPERM"

**Symptom.** Im Protokoll unter `/tmp/ota-app-firefox.log` steht diese Zeile. Firefox startet
trotzdem und funktioniert.

**Das ist kein Fehler**, sondern die Folge einer bewussten Entscheidung: Der Arbeitsplatz-Container
bekommt seit dem 2026-08-27 kein `CAP_SYS_ADMIN` mehr. Der Standard-seccomp-Filter von Docker lässt
eigene User-Namespaces nur mit dieser Fähigkeit zu, und ohne sie fällt Firefox auf eine schwächere
interne Sandbox zurück.

Der Tausch ist bewusst: Firefox' Sandbox schützt vor einer bösartigen Webseite, und die landet im
schlimmsten Fall in genau dem Container, in dem der Nutzer ohnehin ein Terminal hat. `SYS_ADMIN`
dagegen ist ein Weg **aus** dem Container heraus ([Kapitel 11](11-betrieb.md)).

## Ein AppImage startet nicht mehr

**Symptom.** Ein per Rezept eingebautes AppImage bricht ab, oft mit einer Meldung über FUSE oder
`/dev/fuse`.

**Ursache.** Dieselbe wie oben: kein `CAP_SYS_ADMIN`. Ein AppImage hängt sich beim Start
normalerweise selbst per FUSE ein, und das braucht diese Fähigkeit.

**Reparatur.** Das AppImage-Rezept legt seit dem 2026-08-27 einen Starter an, der
`APPIMAGE_EXTRACT_AND_RUN=1` setzt — das AppImage entpackt sich und startet daraus. Wer ein älteres
Rezept hat, ergänzt in seinem Skript:

```bash
cat > /usr/local/bin/<name> <<'RUN'
#!/bin/sh
export APPIMAGE_EXTRACT_AND_RUN=1
exec /opt/<name>.AppImage "$@"
RUN
chmod +x /usr/local/bin/<name>
```

Kostet einen Moment beim Start und sonst nichts.

## Das Einfrieren hängt und kommt nie zurück

**Symptom.** *Session einfrieren* läuft und läuft. Kein Fehler, keine Meldung, kein Fortschritt.
`docker ps` zeigt den Container als **Paused**.

**Ursache.** `docker commit` hält den Container für die Dauer der Aufnahme selbst an — und ein
bereits angehaltener Container lässt sich nicht ein zweites Mal anhalten. Der Aufruf wartet dann auf
etwas, das nie passiert.

Zwei Wege führten dorthin, beide am 2026-08-28 gemessen:

1. Der Container war **vorher schon** pausiert — meist durch den Leerlauf-Aufräumer.
2. Der Aufräumer pausierte ihn **mitten in der Aufnahme**.

**Behoben, an zwei Stellen:** Der Agent prüft vor dem Einfrieren den Zustand des Containers und
weckt ihn — er verlässt sich dabei nicht auf das, was die API über den Container zu wissen glaubt.
Und der Aufräumer lässt Sessions in Ruhe, an deren Workspace gerade gebaut oder eingefroren wird.

**Wenn es doch einmal hängt:**

```bash
docker ps --filter "name=ota-s-" --format '{{.Names}} {{.Status}}'
docker unpause <container>     # die Aufnahme läuft dann weiter
```

## Ein Arbeitsplatz lässt sich nicht mehr starten, es steht nur „starting"

**Symptom.** Der Startknopf tut nichts Sichtbares. Die Session steht auf `starting` und bleibt
dort — auch nach Minuten, auch nach einem Neuladen. Ein Container ist keiner zu sehen.

**Ursache.** Eine frühere Session derselben Vorlage steht in der Datenbank noch als lebendig, ihr
Container ist aber weg. OTA gibt beim Start eine bereits laufende Session zurück, statt eine
zweite anzulegen — und bekam damit jedes Mal dieselbe Leiche.

Dorthin führte ein Zeitablauf: Meldet Traefik die Route eines neuen Containers nicht innerhalb von
25 Sekunden, bleibt die Session auf `starting`. Danach prüfte nichts mehr nach.

**Nachsehen.**

```bash
docker compose -f deploy/docker-compose.yml exec -T db psql -U ota -d ota \
  -c "SELECT id, status, container_id FROM sessions WHERE status IN ('starting','running');"
docker ps --filter "label=ota.session_id" --format '{{.Names}}'
```

Steht dort eine Session, zu der kein Container gehört, ist es das.

**Behoben am 2026-08-28**, an zwei Stellen: Der Start sieht selbst nach, ob der Container noch
existiert, und schliesst die Session, wenn nicht. Und der Aufräumer räumt solche Leichen bei jedem
Durchlauf weg — auch ohne dass jemand einen Start versucht.

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
