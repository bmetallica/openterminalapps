# Netzabsicherung der Arbeitsplätze

**Entwurf, 2026-09-04.** Antwort auf die Befunde [H1, H2 und H3](security.md) — und auf den
Vorschlag, jeder Sitzung ein eigenes Docker-Netz zu geben und den Verkehr über einen
Firewall-Container zu führen, konfigurierbar in der Oberfläche.

*(Kleingeschrieben wie `security.md` und `dsgvo.md` daneben.)*

---

## Kurze Antwort

**Ja — der Kern trägt, und er löst mehr als den ersten Punkt.** Je Sitzung ein eigenes Netz plus
eine Freigabeliste beseitigt H1 (Wirt und Firmennetz erreichbar) und H2 (Arbeitsplätze erreichen
einander), und nebenbei H3 (der Agent ist erreichbar), sobald der Agent nicht mehr in den
Sitzungsnetzen hängt.

**Zwei Stellen im Entwurf würde ich anders bauen.** Beide sind Fallen, die man erst im Betrieb
merkt — und die zweite ist genau der Fall, um den es in H1 in erster Linie geht.

---

## Korrektur 1 · Der Firewall-Container kann nicht der Router sein

Der Gedanke ist naheliegend: ein Container mit `iptables`, alle Sitzungsnetze hängen daran, aller
Verkehr geht durch ihn. Das funktioniert so nicht, und der Grund ist Docker selbst.

**Docker richtet für jedes Bridge-Netz eigenständig NAT und Weiterleitung ein.** Ein Container
bekommt seine Standardroute auf die Bridge des Wirts, nicht auf einen Nachbarcontainer. Der Weg
nach draussen geht also **am Firewall-Container vorbei**, egal wie viele Netze an ihm hängen.

Ihn tatsächlich zum Gateway zu machen ginge nur auf zwei Wegen, und beide sind schlechter als das
Problem:

* **Standardroute im Sitzungscontainer umbiegen.** Dafür braucht dieser Container `NET_ADMIN` —
  also genau die Fähigkeit, die wir ihm mit `cap_drop: ALL` gerade genommen haben. Wer seine
  Routen setzen darf, darf sie auch wieder wegnehmen.
* **Netz-Namensraum teilen** (`network_mode: container:<firewall>`). Dann liegen alle Sitzungen im
  selben Namensraum — das Gegenteil von Trennung.

**Stattdessen:** Die Regeln gehören in den Netfilter des **Wirts**. Der Container darf bleiben, nur
seine Rolle ändert sich — vom **Router** zum **Regelschreiber**. Ein `ota-firewall` mit
`network_mode: host` und `cap_add: NET_ADMIN`, der nichts weiter tut, als Regeln zu setzen und
nachzuhalten. Er transportiert kein einziges Paket; er entscheidet nur, welche der Kernel
weiterleitet. Das ist schneller (kein zusätzlicher Sprung), einfacher (keine Routen im Container)
und robuster.

> Der Vollständigkeit halber: Auch der Agent könnte die Regeln schreiben — er hat mit dem
> Docker-Socket ohnehin Wirtsrechte. Ein eigener Dienst ist mir trotzdem lieber. `NET_ADMIN` und
> `network_mode: host` sind eine Rechteklasse für sich, und der Agent ist schon heute der Dienst
> mit der grössten Angriffsfläche ([H3](security.md#h3)).

---

## Korrektur 2 · `DOCKER-USER` sieht den Wirt nicht

Die übliche Stelle für eigene Regeln ist die Kette `DOCKER-USER`. Sie hängt in **`FORWARD`** — also
in dem Weg, den *weitergeleiteter* Verkehr nimmt: Container nach draussen, Container zu Container
über verschiedene Brücken.

**Verkehr vom Container an den Wirt selbst geht nicht durch `FORWARD`, sondern durch `INPUT`.**
`DOCKER-USER` sieht ihn nie. Und genau das ist der erste Teil von H1:

```
192.168.0.1:22   OFFEN     ← SSH des Wirts
192.168.0.1:9200 OFFEN     ← Elasticsearch eines anderen Stapels
192.168.0.1:6379 OFFEN     ← Redis eines anderen Stapels
```

Alle drei Ziele sind **der Wirt**. Eine Firewall, die nur `DOCKER-USER` bespielt, lässt sie offen —
und man sieht es dem Regelwerk nicht an.

**Also zwei Regelwerke, nicht eins:**

| Kette | Was sie abdeckt |
|---|---|
| `DOCKER-USER` (in `FORWARD`) | Container → Internet, Container → LAN, Container → anderer Container |
| `INPUT` (`-i br-…` oder `-s <sitzungsnetz>`) | Container → Dienste **auf dem Wirt** |

---

## Warum je Sitzung ein eigenes Netz nicht optional ist

Der Gedanke „ein gemeinsames Sitzungsnetz reicht, die Firewall trennt sie darin" scheitert an einer
Kernel-Eigenschaft. **Gemessen auf dieser Maschine:**

```
$ sysctl net.bridge.bridge-nf-call-iptables
(kein solcher Schlüssel)
$ lsmod | grep -c br_netfilter
0
```

Das Modul `br_netfilter` ist nicht geladen. **Verkehr zwischen zwei Containern auf derselben Brücke
wird gebrückt, nicht geroutet — und läuft damit an iptables vollständig vorbei.** Keine Regel der
Welt sieht ihn.

Erst wenn beide in **verschiedenen** Netzen liegen, muss der Kernel routen, und erst dann greift
`FORWARD` und damit `DOCKER-USER`. Das eigene Netz je Sitzung ist also nicht die bequeme, sondern
die **einzige** Variante, die H2 wirklich schliesst.

*(Man könnte `br_netfilter` laden. Dann läuft aller Brückenverkehr des ganzen Wirts durch
Netfilter — mit Nebenwirkungen für jeden anderen Stapel auf dieser Maschine. Kein guter Tausch.)*

---

## Der Aufbau

```
   Browser
      │  https
      ▼
  ┌─────────┐   je Sitzung verbunden    ┌──────────────────┐
  │ Traefik │◄─────────────────────────►│ ota-s-<id>       │
  └─────────┘                           │ Netz 10.99.k.0/24│
                                        └────────┬─────────┘
                                                 │  alles Übrige
                                    ┌────────────▼─────────────┐
                                    │  Netfilter des Wirts     │
                                    │  FORWARD / DOCKER-USER   │  ← ota-firewall
                                    │  INPUT                   │     schreibt hier
                                    └────────────┬─────────────┘
                                       erlaubt?  │
                                  ┌──────────────┼───────────────┐
                                  ▼              ▼               ▼
                              TURN (Wirt)   Internet         LAN ✗
```

**Ablauf beim Start einer Sitzung**, Reihenfolge nicht beliebig:

1. **Netz anlegen** mit ausdrücklichem Subnetz aus OTAs eigenem Bereich (dazu unten mehr).
2. **Regeln setzen** — Freigaben für dieses Subnetz. Die Grundsperre steht schon (Punkt 0, siehe
   unten), das Netz ist also von seiner ersten Sekunde an dicht.
3. **Container starten**, nur in diesem einen Netz.
4. **Traefik verbinden** (`docker network connect`) und am Container
   `traefik.docker.network=<netz>` setzen, damit Traefik die richtige Adresse nimmt.
5. Beim Beenden alles rückwärts: Traefik trennen, Regeln entfernen, Netz löschen.

**Punkt 0 — die Grundsperre.** Einmalig, unabhängig von einzelnen Sitzungen: eine Regel, die den
**ganzen** OTA-Adressbereich verwirft. Erst danach die Freigaben je Sitzung. Sonst gibt es beim
Anlegen ein Zeitfenster, in dem ein Netz schon existiert und noch keine Regel hat. Ein solches
Fenster ist genau die Art Fehler, die im Betrieb einmal im Jahr zuschlägt und nie reproduzierbar
ist.

**Der Agent verbindet sich nicht mehr mit den Sitzungsnetzen.** Er braucht sie nur, um Ports
abzufragen — das geht über den Docker-Socket, den er ohnehin hat. Damit fällt [H3](security.md#h3)
als Nebenwirkung weg.

---

## Der Grundregelsatz, den OTA selbst braucht

Ausgehend vom Sitzungsnetz. Alles, was hier nicht steht, ist verworfen.

| Ziel | Warum |
|---|---|
| `ESTABLISHED,RELATED` | Antwortpakete. Ohne das funktioniert nichts. |
| **DNS** → der festgelegte Resolver, 53/udp+tcp | Ohne Namensauflösung startet keine Anwendung sauber. **Nur der eine Resolver** — siehe „DNS-Namen" unten. |
| **TURN** → Wirt, 3478/tcp+udp und der Relay-Bereich (Vorgabe 49160–49260/udp) | Der Medienweg. Läuft gegen den Wirt, also **`INPUT`**, nicht `DOCKER-USER`. |
| **Traefik** → Sitzung, 6901 bzw. 8080 | Eingehend, damit das Bild ankommt. Nur von Traefiks Adresse. |
| **Firmenproxy** → falls gesetzt, Host:Port aus `OTA_HTTP_PROXY` | Sonst kommt hinter dem Proxy nichts durch. Ohne Proxy entfällt die Zeile. |
| **NTP**, 123/udp — optional | Eine falsche Uhr im Container bricht TLS und Kerberos-Tickets. |

Ausdrücklich **nicht** freigegeben, auch nicht in der Stufe „Internet":

* das Netz des Wirts (alle seine Adressen, nicht nur die Bridge-Adresse),
* die anderen Sitzungsnetze,
* `ota_internal` (Datenbank, API, Keycloak) — heute schon dicht, bleibt dicht,
* der Agent.

---

## Die Stufen in der Oberfläche

Drei Stufen sind genug. Mehr Knöpfe erzeugen mehr falsch eingestellte Anlagen.

| Stufe | Bedeutung |
|---|---|
| **Abgeschottet** | Nur der Grundregelsatz. Kein Internet, kein LAN. Für Arbeitsplätze, die nur mit lokalen Daten arbeiten. |
| **Internet** *(Vorgabe)* | Grundregelsatz plus alles ausserhalb der privaten Bereiche (RFC 1918, `169.254/16`, `100.64/10`). Das LAN bleibt zu. |
| **Offen** | Keine Einschränkung. |

Dazu je Profil eine **Freigabeliste** für das, was zusätzlich erreichbar sein soll:

```
  Ziel                 Ports        Protokoll
  192.168.66.10        445, 139     tcp        ← Dateiserver
  10.20.0.0/16         443          tcp        ← internes Rechenzentrum
  git.firma.de         22, 443      tcp        ← per Name, siehe unten
  buildserver.firma.de 8080-8090    tcp        ← Bereich
```

**„Offen" ist eine Entscheidung, keine Einstellung.** Sie gehört mit Warnung, Protokolleintrag
(`firewall.disabled`) und Namensnennung versehen — dieselbe Behandlung wie die
Passwort-Durchreichung in `plan.md` §17.9. Wer sie wählt, soll das später begründen können.

**Wo das Profil hängt.** Am besten wie die Ressourcen: eine Vorgabe an der Vorlage, überschreibbar
je Gruppe und je Nutzer (`security.py: effective_resources` ist das Muster). Dann bekommt die
Entwicklungsabteilung ihren Buildserver, ohne dass ihn alle bekommen.

---

## DNS-Namen — ehrlich betrachtet

Netfilter kennt keine Namen, nur Adressen. Für `git.firma.de` gibt es zwei Wege, und der
naheliegende ist der schlechtere:

**Der naheliegende:** den Namen alle paar Minuten auflösen und die Adressen in eine Menge (`ipset`
bzw. nft-Set) schreiben. Das funktioniert für einen Server mit fester Adresse und **bricht** bei
allem mit kurzer TTL oder mehreren Adressen: Der Browser bekommt vom DNS die Adresse A, die
Freigabe enthält noch B — und der Zugriff scheitert scheinbar grundlos. Bei CDN-gestützten Zielen
ist das der Normalfall, nicht die Ausnahme.

**Der bessere:** ein eigener Resolver für die Sitzungsnetze (`dnsmasq` oder `unbound` im
`ota-firewall`), der **beim Beantworten** genau die Adresse in die Menge legt, die er gerade
herausgibt — mit der TTL der Antwort. Dann stimmen Freigabe und Verbindung immer überein, weil
beide aus derselben Auskunft stammen. `dnsmasq --ipset=/git.firma.de/ota-frei-<sitzung>` macht
genau das.

**Damit das trägt, muss der Weg zu fremden Resolvern zu sein.** Sonst fragt eine Anwendung
`8.8.8.8`, bekommt eine Adresse, die in keiner Menge steht — oder umgekehrt: sie umgeht die
Freigabeliste über einen Namen, den unser Resolver nie gesehen hat. Deshalb steht im
Grundregelsatz oben **ein** Resolver und keine allgemeine Freigabe für Port 53.

*(Und ja: DNS über HTTPS umgeht auch das. Wer „Internet" freigibt, gibt DoH mit frei. Das ist keine
Lücke dieses Entwurfs, sondern die Grenze jeder namensbasierten Freigabe — sie gehört
aufgeschrieben, nicht wegdiskutiert.)*

---

## Was das löst — und was nicht

| Befund | danach |
|---|---|
| [H1](security.md#h1) Wirt und LAN erreichbar | ✅ gelöst, **wenn** `INPUT` mitbedacht ist (Korrektur 2) |
| [H2](security.md#h2) Arbeitsplätze untereinander | ✅ gelöst durch getrennte Netze |
| [H3](security.md#h3) Agent erreichbar | ✅ gelöst, sobald der Agent draussen bleibt |
| [H4](security.md#h4) Stilles Aufschalten | ❌ **unberührt.** Anderes Thema, andere Lösung. |
| Ausbruch aus dem Container | ❌ unberührt — gemeinsamer Kernel bleibt gemeinsamer Kernel |
| Abfluss von Daten ins Internet | ⚠️ In der Stufe „Internet" möglich. Das ist eine Richtlinienfrage, keine technische. |

Und eine Einschränkung, die man sich merken sollte: **Das Regelwerk ist nur so gut wie seine
Verankerung.** Auf dieser Maschine stehen heute vier Regeln für ein fremdes Netz **vor**
`DOCKER-USER`:

```
1  -P FORWARD DROP
2  -A FORWARD -o br_kasm_sidecar … -j ACCEPT
4  -A FORWARD -i br_kasm_sidecar ! -o br_kasm_sidecar -j ACCEPT   ← lässt alles durch
6  -A FORWARD -j DOCKER-USER                                       ← erst hier sind wir
```

Für dieses eine Netz wäre `DOCKER-USER` wirkungslos. OTAs eigene Netze sind nicht betroffen (Docker
29 hängt sie hinter `DOCKER-USER` ein), aber die Lehre gilt: **Die Wirkung des Regelwerks wird
geprüft, nicht gelesen.**

---

## Fallstricke

**Der Adressbereich ist auf dieser Maschine fast leer.** Gemessen:

```
172.17 … 172.31   belegt (15 Netze, Dockers erster Pool ist voll)
192.168.0.0/20    ota_sessions        ← zweiter Pool, /20-Häppchen
192.168.16.0/20   sonnensystem_default
```

Dockers Standardvorrat gibt noch **14** weitere Netze her — für alle Stapel auf diesem Rechner
zusammen. Ein Netz je Sitzung würde ihn in einer Woche aufbrauchen, und der Fehler beim Start
lautet dann `could not find an available, non-overlapping IPv4 address pool`.

Zwei Auswege, und der zweite ist der bessere:

* `default-address-pools` in `/etc/docker/daemon.json` erweitern — braucht einen **Neustart des
  Docker-Dienstes**, und der reisst jeden Container auf dieser Maschine mit. Wartungsfenster.
* **OTA vergibt die Subnetze selbst**: ein eigener Bereich, etwa `10.99.0.0/16`, aufgeteilt in
  `/24`. Das sind 256 gleichzeitige Sitzungen, `docker network create --subnet 10.99.k.0/24`, kein
  Neustart, keine Kollision mit fremden Stapeln — und die Regeln lassen sich über den ganzen
  Bereich in **einer** Grundsperre formulieren.

**Nicht `192.168.x` nehmen.** Das heutige `ota_sessions` liegt auf `192.168.0.0/20` — in vielen
Firmen- und Heimnetzen ist genau das die LAN-Adresse. Beim Einsatz an anderer Stelle kollidiert es,
und dann ist nicht die Firewall schuld, sondern die Route. `10.99` ist unverbrauchter.

**Regeln überleben keinen Docker-Neustart.** Docker baut seine Ketten beim Start neu auf; was in
`DOCKER-USER` stand, ist weg. Der `ota-firewall` braucht deshalb eine **Abgleichschleife**: beim
Start und danach regelmässig prüfen, ob für jede laufende Sitzung ihre Regeln stehen, und fehlende
nachziehen. OTA hat dieses Muster schon — der Waisen-Aufräumer arbeitet genauso.

**IPv6.** Auf den Netzen ist es aus (`EnableIPv6=false`), aber `ip6tables` hat eine
`DOCKER-USER`-Kette. Wer IPv6 einschaltet, ohne die Regeln zu spiegeln, hat eine Firewall, die für
die Hälfte des Verkehrs nicht existiert. Entweder beide Familien bedienen oder IPv6 ausdrücklich
aus lassen — und das aufschreiben.

**51 Brücken stehen schon auf diesem Wirt.** Ein paar Dutzend mehr sind unkritisch; bei Hunderten
werden `iptables`-Durchläufe und `ip link` spürbar. Ein Grund mehr, das Netz beim Beenden der
Sitzung wirklich zu löschen und nicht liegen zu lassen.

**MTU.** Neue Brücken erben die Vorgabe. Wer über einen Tunnel mit kleiner MTU arbeitet (hier:
WireGuard mit 1000), sollte `com.docker.network.driver.mtu` bewusst setzen, statt es später zu
suchen — dieses Projekt hat mit MTU schon einmal zwei Tage verloren
([Kapitel 20](docs/wiki/20-selkies-versuch.md)).

**nftables und iptables nebeneinander.** Debian 13 setzt `iptables-nft` ein, Docker schreibt
darüber. Der `ota-firewall` sollte dasselbe Werkzeug benutzen und **kein** eigenes nft-Tabellenwerk
danebenstellen — zwei Regelwerke, die sich gegenseitig nicht sehen, sind schlimmer als keins.

---

## Datenmodell und Oberfläche

Ein neues Objekt, angelehnt an das, was es schon gibt:

```
netzprofile
  id, name, beschreibung
  stufe            abgeschottet | internet | offen
  regeln  [ { ziel: "10.20.0.0/16" | "git.firma.de",
              ports: "443" | "8080-8090" | "*",
              protokoll: tcp | udp | beide,
              notiz: "Warum das offen ist" } ]
```

* `templates.netzprofil_id` — die Vorgabe je Arbeitsplatz.
* `template_overrides` — je Gruppe und je Nutzer, wie bei Kernen und Speicher.
* **`notiz` ist Pflicht.** Eine Freigabe ohne Begründung ist in einem Jahr eine Freigabe, die
  niemand zu entfernen wagt.

In der Oberfläche unter **Verwaltung → Netzprofile**, und am Arbeitsplatz eine Auswahl wie bei
**Streaming**. Auf dem Dashboard des Nutzers ein kleiner Hinweis, welches Profil gilt — wer nicht
weiss, dass eine Firewall läuft, meldet ihre Wirkung als Fehler.

---

## Die Prüfreihe ist der eigentliche Beweis

Das Regelwerk zu lesen genügt nicht (siehe oben, `br_kasm_sidecar`). `scripts/test-firewall.sh`
startet eine Sitzung und prüft **von innen**:

| Prüfung | Erwartung |
|---|---|
| Nachbarsitzung auf 6901/8080 | ✗ nicht erreichbar |
| SSH des Wirts (22) | ✗ nicht erreichbar |
| Ein Dienst eines anderen Stapels auf dem Wirt (9200) | ✗ nicht erreichbar |
| Eine LAN-Adresse | ✗ nicht erreichbar |
| TURN auf dem Wirt (3478) | ✓ erreichbar |
| Namensauflösung | ✓ funktioniert |
| Fremder Resolver (`8.8.8.8:53`) | ✗ nicht erreichbar |
| Internet in Stufe „Internet" | ✓ erreichbar |
| Internet in Stufe „abgeschottet" | ✗ nicht erreichbar |
| Eine Freigabe aus der Liste | ✓ erreichbar |
| Nach `systemctl restart docker` erneut | alles wie oben |

Die letzte Zeile ist die wichtigste — sie prüft die Abgleichschleife, und genau die vergisst man.

---

## Etappen

| # | Schritt | Aufwand | Wirkung |
|---|---|---|---|
| 1 | Wirt vor seinen Containern schützen: `INPUT`-Regeln für `ota_sessions`, von Hand | **1 Stunde** | Schliesst den schlimmsten Teil von H1 **heute**, ohne eine Zeile Code |
| 2 | Eigener Adressbereich `10.99.0.0/16`, ein Netz je Sitzung, Traefik dynamisch verbinden | 1–2 Tage | H2 und H3 |
| 3 | `ota-firewall` als Regelschreiber, Grundsperre, Freigaben je Sitzung, Abgleichschleife | 2–3 Tage | H1 vollständig |
| 4 | Netzprofile in Datenmodell und Oberfläche, drei Stufen, Freigabeliste | 2–3 Tage | Bedienbar statt gebaut |
| 5 | Eigener Resolver, Freigaben nach Namen | 1–2 Tage | Der Teil, der ohne ihn nur halb funktioniert |
| 6 | `scripts/test-firewall.sh` | ½ Tag | Ohne sie ist alles darüber eine Behauptung |

**Schritt 1 lohnt sofort**, unabhängig vom Rest: Er ist in einer Stunde erledigt, braucht keinen
Code und nimmt dem gravierendsten Befund die Spitze. Alles Weitere kann danach in Ruhe entstehen.
