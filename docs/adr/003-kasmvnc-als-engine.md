# ADR-003 · KasmVNC ist die Streaming-Engine, mit einem Display je Anwendung

**Stand:** angenommen
**Datum:** 2026-08-27

## Ausgangslage

Aus [ADR-001](001-arbeitsplatz-als-fundament.md) folgt: Ein Container, mehrere Anwendungen, jede
einzeln formatfüllend im Browser. Gebraucht wird also etwas, das einen X-Bildschirm in einen
Browser-Tab bringt — ohne Plugin, mit funktionierender Zwischenablage, und mehrfach nebeneinander
im selben Container.

## Entscheidung

**KasmVNC** (GPL-2.0), eine `Xvnc`-Instanz je Anwendung, jede auf ihrem eigenen Display und
eigenem WebSocket-Port. Die Displayvergabe macht OTA selbst.

## Alternativen

**Apache Guacamole.** Ausgereift, mit RDP und SSH obendrein, und lizenzlich unproblematisch.
Es braucht aber einen eigenen Dienst (`guacd`) neben den Sessions und spricht klassisches VNC — die
Zwischenablage läuft über den Guacamole-Client, nicht über den Browser, und die
Auflösungsanpassung ist gröber. Für RDP-Ziele bleibt Guacamole vorgemerkt; als Fundament für den
Arbeitsplatz ist es der Umweg.

**code-server / openvscode-server.** Der bequemste Weg zu einem Editor im Browser — und nur zu
einem Editor. Ein Terminal daneben, ein Dateimanager, GIMP: alles wieder offen. Ausserdem dürfte
ein solcher Dienst den Marktplatz von Microsoft nicht benutzen
([Handbuch, Kapitel 13](../wiki/13-lizenzen.md)).

**Ein Desktop je Nutzer, ein einziges Display.** Siehe ADR-001: Das ergibt einen Desktop im
Desktop. OTA bietet ihn als zusätzliche Ansicht an.

## Folgen

**Displays sind eine begrenzte Ressource.** Jede Anwendung bekommt eine Nummer, jede Nummer eine
Traefik-Route. Aus dieser Kopplung stammt der Fehler vom 2026-08-27, bei dem die Displaynummer aus
der Katalogposition kam und die Grenze von sechs für die *Kataloggrösse* galt statt für gleichzeitig
offene Anwendungen ([Handbuch, Kapitel 12](../wiki/12-fehlersuche.md)).

**Die Zwischenablage hängt am Client.** KasmVNC schaltet sie im iframe ab, weil es dort keine
Berechtigung erwartet. OTA schaltet sie über Adressparameter wieder ein. Das ist eine Abhängigkeit
vom Verhalten fremden Codes, und sie muss bei jedem Versionswechsel nachgeprüft werden.

**GPL-2.0.** KasmVNC läuft im Container, OTA ruft es über das Netz auf. Es wird nicht mit OTA
verlinkt und nicht mit ihm ausgeliefert — die Lizenz von OTA (Apache-2.0) bleibt davon unberührt.
