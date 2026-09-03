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
| Anwendungen | **je Anwendung ein Bildschirm**, umschaltbar in der Leiste | dasselbe — je Anwendung ein `Xvfb` mit eigener Selkies-Instanz |
| Weg des Bildes | durch Traefik, ein Port | **an Traefik vorbei**, WebRTC über UDP |
| Zusätzliche Ports | keine | 3478 und 49160–49260 auf dem Host (UDP), einmal für alle |
| Sitzungen gleichzeitig | beliebig viele | beliebig viele (ein TURN für den ganzen Host) |
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
Host erreichen — nicht die eines Docker-Netzes und nicht `0.0.0.0` — und ein
Geheimnis für die TURN-Anmeldung:

```
OTA_TURN_HOST=192.168.66.224
OTA_TURN_SECRET=…            # openssl rand -base64 32
OTA_TURN_PROTOCOL=udp        # tcp bei kleiner MTU, siehe unten
OTA_TURN_ICE_POLICY=all      # relay bei kleiner MTU, siehe unten
```

Dann den TURN-Dienst starten und **nachmessen**, bevor irgendetwas anderes
probiert wird:

```bash
docker compose -f deploy/docker-compose.yml --env-file deploy/.env up -d turn
python3 scripts/pruef-turn.py
```

Die letzte Zeile muss `TURN vermittelt.` lauten. Tut sie es nicht, hat es
keinen Zweck, eine Sitzung zu starten — sie zeigt dann „Waiting for stream"
und sagt nicht warum.

Dann eine Vorlage anlegen mit `image_ref: ota/base-selkies:test` und
`stream_engine: selkies`. Alles andere bleibt wie bei jedem Arbeitsplatz:
Zuhause, Ablagen, Skeleton, Startskript, Rechte.

## Warum der TURN-Server im Stack läuft und nicht in der Sitzung

WebRTC braucht einen Medienweg per UDP. Session-Container liegen in einem
internen Docker-Netz ohne veröffentlichte Ports — der Browser käme nicht
heran, und Traefik hilft nicht: Es spricht HTTP, nicht UDP. Vermittelt wird
deshalb über einen TURN-Server.

Der lief zuerst **im Session-Container**, einer je Sitzung, mit Ports, die der
Agent nach aussen durchreichte. Das klang sauber — ein Fehler trifft eine
Sitzung statt aller — und kann trotzdem nicht funktionieren. Ein TURN hinter
einer Docker-Bridge meldet als Relay-Adresse die des Hosts, verschickt die
vermittelten Pakete aber mit der Container-Adresse als Absender:

```
2. Allocate mit Anmeldung  -> Relay 192.168.66.224:65502
5. Client -> Relay -> Peer: b'HINAUS' von 192.168.0.4:65502
   Absender != Relay 192.168.66.224:65502  [ausgehend KAPUTT]
```

Jeder WebRTC-Stack verwirft ein Paket, dessen Absender nicht zu dem Kandidaten
passt, auf den er wartet. Deshalb läuft der Dienst `turn` auf dem **Netz des
Hosts** (`network_mode: host`) — nur ohne NAT dazwischen stimmen gemeldete und
tatsächliche Adresse überein.

Ein gemeinsamer TURN bringt nebenbei das, was der Weg vorher nicht konnte:
**mehr als eine Selkies-Sitzung je Host.** Der Portbereich wird einmal geteilt
statt je Container veröffentlicht, und der Session-Container macht überhaupt
keinen Port mehr auf.

Angemeldet wird mit kurzlebigen Zugangsdaten aus einem HMAC über
`OTA_TURN_SECRET` — Selkies rechnet sie sich aus demselben Geheimnis aus und
gibt sie dem Browser mit Ablaufzeit mit. Das Sitzungspasswort steht nicht drin.

Die Weboberfläche und die Signalisierung laufen weiterhin über Traefik, mit
derselben Anmeldung und demselben Basic-Auth-Header wie bei KasmVNC. **Nur der
Medienstrom geht daran vorbei.**

## Das Nachfolge-Image: Debian 13, ohne KasmVNC

`ota/base-selkies:test` leitet von `base-xfce` ab und schleppt damit KasmVNC
mit — `Xvnc`, `kasmvncserver`, `kasmvncpasswd` und 3,4 MB Weboberfläche, von
denen dort **nichts läuft**. Das war richtig, solange Selkies ein Versuch auf
einer funktionierenden Grundlage war, und ist verkehrt herum, seit es streamt.

`images/base-desktop/` beginnt deshalb bei `debian:13`:

```bash
docker build -t ota/base-desktop:test images/base-desktop
```

| | base-selkies | base-desktop |
|---|---|---|
| Grundlage | Ubuntu 24.04 über `base-xfce` | Debian 13 direkt |
| KasmVNC | mit drin, läuft nie | nicht vorhanden |
| Konto / Zuhause | `kasm-user` / `/home/kasm-user` | `ota` / `/home/ota` |
| GStreamer | Bündel, 1.24.6, 366 MB unter `/opt` | aus der Distribution, 1.26.2 |
| Grösse | 1,73 GB | 1,78 GB |

Die Grösse ist der ehrliche Wermutstropfen: Das Bündel fällt weg, aber Debians
`gstreamer1.0-plugins-bad` bringt fast dasselbe mit — CUDA-, Vulkan- und
Wayland-Anteile, die ein Streaming-Server nie anfasst. Abspecken wäre ein
eigener Schritt.

### Wo das Zuhause liegt, sagt das Image

Der Agent liest `HOME` aus der Image-Konfiguration und hängt das Profil
dorthin (`_heimat_aus_env` in `agent/otaagent/main.py`); ohne Angabe bleibt es
bei `/home/kasm-user`. Fremdimages wie `kasmweb/gimp` laufen dadurch
unverändert weiter, und ein eigenes Image bestimmt seinen Pfad selbst. Der
Wert wird geprüft, bevor er als Mount-Ziel dient — ein Image darf nicht
bestimmen, wohin der Agent auf dem Host greift.

Daneben legt das Startskript einen Verweis unter dem OTA-Anmeldenamen an:
`/home/bmetallica` → `/home/ota`. Dasselbe Muster wie auf dem Host, wo unter
der Kennung gespeichert und ein lesbarer Verweis danebengelegt wird. Eine
Umbenennung in Keycloak verschiebt nur diesen Verweis; alles, was im Profil
einen absoluten Pfad gespeichert hat — Editor-Einstellungen, virtuelle
Umgebungen, `git config` — bleibt gültig. Genau das wäre kaputt, wenn das
Zuhause selbst den Anmeldenamen trüge.

### Eine Anwendung, kein Schreibtisch

Betriebsart **„Einzelne App"** überträgt genau eine Anwendung, formatfüllend,
ohne Leiste und ohne Schreibtischsymbole. Der Container startet dafür nur
einen Fenstermanager statt der ganzen Arbeitsumgebung.

Zwei Dinge greifen ineinander:

* Der Agent schickt `OTA_MODE` mit. Das Startskript verzweigt darauf — vorher
  wusste der Container seine Betriebsart nicht und startete immer XFCE.
* Im Bildbauer gibt es das Feld **Startbefehl**. Daraus entsteht ein
  `custom_startup.sh` im gebauten Image.

Das Feld ist nötig, weil der Bildbauer für Einzelanwendungen bewusst das
Startskript des Basisimages behält. Bei den Kasm-Anwendungsimages stimmt das —
die starten „ihre" Anwendung selbst. OTAs eigenes Basisimage bringt dagegen
absichtlich einen Platzhalter mit, der **nichts** startet; ein darauf gebautes
Einzelanwendungs-Image zeigte deshalb einen leeren Bildschirm, und der Grund
stand nirgends.

Der Befehl wird über base64 ins Dockerfile gelegt und nicht in eine
`RUN`-Zeile geschrieben: Er kommt aus einem Textfeld und darf
Anführungszeichen, Dollarzeichen und Zeilenumbrüche enthalten.

Beendet sich die Anwendung, startet das Startskript sie nach drei Sekunden
neu. Bei einer Einzelanwendung ist das gewollt — im Arbeitsplatz hat dieselbe
Aufsicht einmal 119 leere Fenster erzeugt, weshalb ein Arbeitsplatz-Image den
Platzhalter bekommt.

Geprüft im laufenden Container: Es laufen `Xvfb`, `xfwm4`, die Anwendung,
Selkies, PulseAudio — **kein** `xfce4-panel`, `xfdesktop` oder
`xfce4-session`. Das Fenster steht auf `0 0 1440x900` bei einem Bildschirm von
1440×900, mit `_NET_WM_STATE_FULLSCREEN`.

Zwei Stolperstellen, beide gemessen:

* **`xfwm4 --daemon` gibt es in Debian nicht.** Der Fenstermanager beendete
  sich sofort, und sichtbar war das erst daran, dass `wmctrl` keine
  Fensterliste bekam (`Cannot get client list properties`). Ohne
  Fenstermanager hat die Anwendung keinen Rahmen, folgt der Bildschirmgrösse
  nicht und lässt sich nicht formatfüllend setzen. Er läuft jetzt mit
  `--compositor=off` — ohne GPU passiert jeder Bildaufbau in Software, und
  diese Rechenzeit gehört dem Kodierer.
* **`fullscreen`, nicht `maximized`.** Maximiert bliebe die Titelleiste
  stehen, und bei einer einzelnen Anwendung gibt es nichts, wozu man sie
  brauchte.

### Mehrere Anwendungen gleichzeitig — auch mit Selkies

Hier stand einmal, Selkies übertrage genau einen Bildschirm, mehrere
Anwendungen lägen deshalb nebeneinander auf demselben. Das war ein
Missverständnis: Es gilt für **eine** Selkies-Instanz, nicht für das
Arbeitsplatzmodell von OTA. Dort bekommt jede Anwendung ihren eigenen
Bildschirm, formatfüllend, umschaltbar in der Leiste — und mehrere laufen
gleichzeitig aus einem Container.

Genau so läuft es jetzt auch mit Selkies, nur mit anderer Technik dahinter:

| | KasmVNC | Selkies |
|---|---|---|
| X-Server je Anwendung | `Xvnc :N` | `Xvfb :N` |
| Strom je Anwendung | derselbe `Xvnc`, Port `6900+N` | eigene Selkies-Instanz, Port `8080+N` |
| Fenstermanager | `xfwm4`, kein Schreibtisch | dito, dazu `--compositor=off` |
| Traefik-Route | `/s/<kennung>/a/N`, HTTPS | dito, HTTP |

Gemessen an einer Sitzung mit zwei Anwendungen: drei Displays (`X1 X2 X3`),
drei `Xvfb`, drei Selkies-Instanzen auf 8080, 8082 und 8083, auf `:2` das
Terminal und auf `:3` Thunar — und beide Ströme liefern 1440×900 im Browser.

Die Prozesskennungen von `Xvfb` und Selkies werden je Bildschirm abgelegt.
Ein Abgleich über den Namen scheitert hier: `pkill -f` durchsucht ganze
Kommandozeilen und fände das Abbau-Skript selbst, dessen Text die gesuchten
Namen enthält.

### Die Anwendung bleibt, wo sie hingehört

In einer Einzelanwendungs-Sitzung gibt es keine Leiste, über die man ein
Fenster zurückholt. Deshalb sieht eine Aufsicht alle zwei Sekunden nach:

* **Minimiert** — kommt wieder hoch (`_NET_WM_STATE_HIDDEN` → `wmctrl -a`).
  Gemessen: `IsUnMapped` direkt nach dem Einklappen, nach fünf Sekunden
  wieder `IsViewable`.
* **Nicht formatfüllend** — wird wieder formatfüllend gesetzt.
* **Geschlossen** — das erledigt die Aufsicht des Startskripts, die
  `custom_startup.sh` neu ausführt, sobald es sich beendet. Gemessen: Prozess
  beendet, nach drei Sekunden läuft ein neuer, das Fenster wieder
  formatfüllend.

### Nur eine Leiste

Der Selkies-Client bringt eine eigene Seitenleiste mit, deren runder Knopf am
rechten Rand **genau unter OTAs Griff** lag. Der von Selkies weicht: Was darin
steht, ist hier fast durchweg überflüssig (Zwischenablage und Skalierung macht
OTA), serverseitig festgelegt (Relay-Zwang) oder falsch — *Return to launcher*
führt aus OTA heraus. Siehe `patches/keine-fremde-leiste.py`; der Build bricht
ab, wenn der Knopf nicht mehr genau einmal vorkommt.

### Drei Fallen beim Wechsel auf Debian

Alle drei hatten dieselbe Form: Das Image baute grün durch, und der Fehler
stand erst im Protokoll der ersten Sitzung.

1. **`cannot import name '_gi_gst' from 'gi.overrides'`** — Das vorgebaute
   Selkies-Bündel ist für **Python 3.12** übersetzt, Debian 13 hat 3.13.
   Distribution und GStreamer hängen also über Python zusammen und lassen
   sich nicht einzeln wechseln. Genommen wird deshalb Debians eigenes
   GStreamer.
2. **`Namespace GstWebRTC not available`** — Die Plugins waren da, die
   Introspektionsdaten nicht. Sie liegen in `gir1.2-gst-plugins-bad-1.0`.
3. **`ModuleNotFoundError: No module named 'distutils'`** — Mit Python 3.12
   aus der Standardbibliothek geflogen (PEP 632); Selkies zieht `GPUtil`
   herein, und das braucht es. `setuptools` bringt den Ersatz mit.

Deshalb prüft das Dockerfile sich jetzt selbst, und der **Build** bricht ab
statt der ersten Verbindung:

```dockerfile
&& gst-inspect-1.0 webrtcbin > /dev/null \
&& gst-inspect-1.0 x264enc > /dev/null \
&& python3 -c "… from gi.repository import Gst, GstWebRTC, GstSdp; …"
…
&& PYTHONPATH="$ORT" python -c "import gpu_monitor, gstwebrtc_app, signalling_web"
```

`selkies-gstreamer --help` taugt als Prüfung übrigens nicht — es verlangt
einen laufenden X-Server.

### Der Name für die Basic-Auth

Aus `Session.vnc_user` baut die API den Header, den Traefik der Sitzung
voranstellt. **In den Container kam der Name bisher nie** — dort stand
`kasm_user` fest im Startskript, und solange beide zufällig übereinstimmten,
fiel es nicht auf. Ein Image, das einen anderen Namen erwartet, antwortet mit
401, und in der Oberfläche steht eine leere Seite.

Jetzt lesen beide Seiten denselben Wert, und er hängt an der Streaming-
Maschine: `ota` für Selkies, `kasm_user` für KasmVNC. Dort ist der Name keine
Geschmacksfrage — die Passwortdatei der Kasm-Images kennt nur diesen.

## Netze mit kleiner Paketgrösse (VPN)

Wer über ein VPN zugreift, dessen MTU deutlich unter 1500 liegt — WireGuard mit
1000 zum Beispiel —, bekommt **kein Bild und keine Fehlermeldung**. Die Sitzung
baut sich auf, ICE verbindet, und dann steht „Waiting for stream".

Der Grund: **Chrome verschickt seinen DTLS-Handschlag mit fest 1200 Byte je
Paket und passt sich einer kleineren Pfadgrösse nicht an.** Die kleinen
ICE-Prüfungen kommen durch, das grosse Paket nicht. Die Gegenseite wartet auf
den fehlenden Teil des Handschlags und antwortet deshalb gar nicht — darum
steht nirgends ein Fehler. Im Protokoll der Sitzung sieht man es am
Grössenmuster der empfangenen Pakete:

```
tragfähiger Weg:  1200, 263, 1200, 263, …
über den Tunnel:  263, 263, 263, …   (und sonst nichts)
```

Abhilfe, beide Zeilen zusammen:

```
OTA_TURN_PROTOCOL=tcp
OTA_TURN_ICE_POLICY=relay
```

`relay` nimmt dem Browser den direkten Weg, `tcp` legt die Strecke
Browser–TURN in einen TCP-Strom — und TCP handelt seine Segmentgrösse mit dem
Pfad selbst aus. Die Frage nach der Paketgrösse stellt sich damit nicht mehr.

Das kostet etwas: Jedes Byte läuft über den TURN-Server, auch für Anwender im
selben Netz, die direkt könnten. Solange nur ein Teil der Anwender über ein
solches VPN kommt, ist das ein Kompromiss zu Lasten aller. Die saubere Lösung
wäre, dem Browser beide Wege anzubieten und ihn wählen zu lassen — dafür müsste
Selkies zwei TURN-Einträge ausliefern, heute liefert es einen.

Nachweisen lässt sich beides mit `scripts/pruef-selkies.mjs`: Der Prüfstand
fährt einen Browser, der den Session-Container **nicht** direkt erreichen kann,
und sagt, ob ein Bild ankommt. Mit einer Sperre für grosse UDP-Pakete
(`iptables … -m length --length 1029:65535 -j DROP`) lässt sich der Fehler
gezielt nachstellen — er verschwindet mit den beiden Zeilen oben.

## Fünf Fallen, alle beim Bauen aufgetreten

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

3. **coturn darf nicht nach `/var/run` schreiben.** Solange er im Container
   lief, gehörte er dem Nutzer 1000, und ohne `pidfile=/tmp/...` startete er
   gar nicht — die Meldung stand in seinem eigenen Protokoll, nicht dort, wo
   man sucht. Der Dienst im Stack hat das Problem nicht mehr; die Falle bleibt
   hier stehen, weil sie zwei Tage gekostet hat.

4. **TURN hinter NAT vermittelt nicht.** Siehe oben. Der Fehler zeigt sich an
   drei Stellen und an keiner davon als das, was er ist: im Browser
   „Waiting for stream", im Container `Fatal SSL error` beim DTLS-Handschlag,
   im TURN-Protokoll `create_relay_ioa_sockets: no available ports` — Letzteres
   nur eine Folge davon, dass elf Ports für die vielen Anläufe zu wenig waren.
   Zu sehen ist die Ursache erst, wenn man ein Paket durchschickt und den
   Absender vergleicht: `scripts/pruef-turn.py`.

5. **Ein zu kleines MTU sieht aus wie gar nichts.** Siehe den Abschnitt oben.
   Dieser Fehler kostet besonders viel Zeit, weil jede einzelne Schicht gesund
   aussieht: TURN vermittelt, ICE verbindet, der Handschlag kommt an. Nur eben
   nicht ganz. Aufgefallen ist er erst beim Vergleich der Paketgrössen
   zwischen einer funktionierenden und einer scheiternden Sitzung.

## Wie es weitergeht

Der Versuch beantwortet die Frage „geht es überhaupt". Was er **nicht**
beantwortet, und was vor einer Entscheidung gemessen gehört:

- **Wie viel besser ist es wirklich?** Latenz und Bildqualität nebeneinander,
  auf denselben Inhalten, im selben Netz.
- **Was kostet es an CPU?** H.264 in Software (x264) ist nicht umsonst. Auf
  einer Maschine ohne GPU zahlt das jede Sitzung.
- **Trägt das Modell „ein Bildschirm" den Alltag** — oder fehlt der
  Anwendungsumschalter dann doch?
- **Wie viele Sitzungen trägt ein TURN?** Eine Verbindung belegt vier
  Relay-Ports, und coturn gibt sie erst nach Ablauf der Lebenszeit frei. Der
  Vorgabebereich von hundert Ports reicht für rund zwanzig gleichzeitige
  Sitzungen; wer mehr braucht, macht ihn grösser.

Solange das nicht gemessen ist, bleibt KasmVNC die Vorgabe.
