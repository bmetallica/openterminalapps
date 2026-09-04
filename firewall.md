# Netzabsicherung der Arbeitsplätze

**Fassung 2, 2026-09-04.** Die erste Fassung wurde teilweise gebaut und dabei verworfen — nicht
weil sie nicht funktionierte, sondern weil sie **zu viele Stellen hatte, an denen man sie verstehen
musste**. Was dabei gemessen wurde, steht weiter unten; es ist das stärkste Argument für den
Aufbau, der jetzt hier steht.

---

## Das Bild

```
   Browser
      │ https
      ▼
  ┌─────────┐
  │ Traefik │
  └────┬────┘
       │                        ┌──────────────────────────────────┐
       │                        │            ota-fw                │
       │                        │  Router für alle Arbeitsplätze:  │
       └───────────────────────►│  Regeln · NAT · DNS · Freigaben  │──► Internet
                                └───┬──────────┬──────────┬────────┘    ──► Firmennetz
                        internal ───┘          │          └─── internal      (nur erlaubtes)
                        ota-n-1            ota-n-2            ota-n-3
                        10.99.1.0/24       10.99.2.0/24       10.99.3.0/24
                        │                  │                  │
                     ┌──┴───┐           ┌──┴───┐           ┌──┴───┐
                     │ Anna │           │ Bernd│           │ Cem  │
                     └──────┘           └──────┘           └──────┘
```

**Ein Satz, den man sich merken kann:** Jeder Arbeitsplatz hängt an einem eigenen Kabel, alle Kabel
enden in einer Firewall, und die Firewall ist der einzige Weg nach draussen. Genau dein Vorschlag —
und er ist besser als meiner.

Die Sitzungsnetze sind **`internal`**. Docker richtet für solche Netze **kein** NAT ein und lässt
nichts an ihnen vorbei: Ohne die Firewall kommt ein Arbeitsplatz nirgendwohin — auch nicht an den
Wirt, auch nicht ins LAN, auch nicht zu einem Nachbarn. Die Absicherung ist damit nicht mehr eine
Sammlung von Regeln, die richtig greifen müssen, sondern **eine Eigenschaft des Aufbaus**.

---

## Warum das die bessere Wahl ist — mit Belegen aus dem abgebrochenen Bau

Die erste Fassung setzte die Regeln im Netfilter des **Wirts** durch. Sie lief, aber unterwegs sind
drei Dinge aufgetreten, die alle dieselbe Ursache haben: **Man teilt sich das Regelwerk mit
Docker.** Alle drei verschwinden im neuen Aufbau ersatzlos.

| Was passierte | Warum es in Fassung 2 wegfällt |
|---|---|
| **Der Haupteingang ging zu.** Sobald Traefik mit einem Sitzungsnetz verbunden wurde, schrieb Docker den DNAT seines veröffentlichten Ports auf Traefiks Adresse **in diesem Netz** um (`--to-destination 10.99.0.3:8443`). Die Grundsperre traf damit OTA selbst — von aussen kam niemand mehr herein, und nirgends stand ein Fehler. | Auf `internal`-Netzen veröffentlicht Docker keine Ports. Der DNAT bleibt, wo er hingehört. |
| **Der eigene Resolver stand offen im Firmennetz.** `dnsmasq` bindet mit `bind-dynamic` jede Schnittstelle — prompt auch die LAN-Adresse des Wirts. Es brauchte drei zusätzliche Regelpaare, um ihn wieder zu schliessen. | Der Resolver läuft **im** Firewall-Container und ist nur über die Sitzungsnetze erreichbar. Nichts zu sperren. |
| **Fremde Resolver mussten eigens verboten werden**, sonst hebelt ein `8.8.8.8` jede Freigabe nach Namen aus. | Aus einem `internal`-Netz gibt es keinen Weg zu `8.8.8.8`. Der eigene Resolver ist der einzige. |

Dazu kommt, was gar nicht mehr nötig ist: keine Kette in `DOCKER-USER`, keine zweite in `INPUT`,
keine Abgleichschleife gegen Dockers Neustart, keine Sonderbehandlung für veröffentlichte Ports
fremder Stapel. **Das Regelwerk des Wirts bleibt unangetastet.**

---

## Die eine harte Stelle

Sie ist es wert, dass man sie kennt, bevor gebaut wird:

**Docker lässt einen Container nicht Gateway sein.** Ein Container bekommt seine Standardroute
immer auf die Brücke des Wirts — auch in einem `internal`-Netz, wo sie ins Leere führt. Damit der
Arbeitsplatz über `ota-fw` hinausfindet, muss seine Standardroute auf dessen Adresse zeigen. Dafür
gibt es genau drei Wege, und zwei davon fallen aus:

* ~~`NET_ADMIN` im Arbeitsplatz~~ — das ist die Fähigkeit, die wir dort gerade weggenommen haben.
  Wer Routen setzen darf, darf sie auch wieder wegnehmen.
* ~~Netz-Namensraum teilen~~ (`network_mode: container:…`) — hebt die Trennung auf.
* ✅ **Die Route von aussen setzen.** `ota-fw` betritt den Namensraum des Arbeitsplatzes
  (`nsenter --net=<SandboxKey>`) und setzt dort die Standardroute. Der Arbeitsplatz selbst braucht
  dafür keine einzige Fähigkeit; er merkt nichts davon.

Das ist derselbe Handgriff, mit dem Netz-Plugins in Kubernetes arbeiten. Er kostet: `ota-fw`
braucht `/var/run/docker/netns` und `SYS_ADMIN`. **Das ist der Preis dieses Aufbaus** — ein
privilegierter Container statt vieler Regeln auf dem Wirt. Ich halte ihn für den besseren Tausch,
weil die Privilegien an *einer* Stelle sitzen und dort sichtbar sind.

**Was geprüft werden muss, bevor darauf gebaut wird** (eine halbe Stunde, Etappe 0):

1. Zeigt Docker den Namensraum als `SandboxKey` an, und lässt sich darin die Route setzen?
2. Veröffentlicht Docker auf `internal`-Netzen wirklich keine Ports — bleibt der DNAT von 8443 in
   Ruhe, wenn Traefik einem Sitzungsnetz beitritt?
3. Erreicht Traefik den Arbeitsplatz in einem `internal`-Netz?
4. Wie viele Netze verträgt ein Container? Bei 50 gleichzeitigen Sitzungen hat `ota-fw` 50
   Schnittstellen.

Fällt Punkt 2 oder 3 durch, ändert sich der Aufbau an genau einer Stelle: Dann bekommt Traefik
seinen Weg zum Arbeitsplatz ebenfalls über `ota-fw` statt direkt.

---

## Was wir nicht bauen — und warum

**Keinen DHCP-Server.** Du hast ihn vorgeschlagen, und in einem echten Netz wäre er richtig. Hier
nicht: Docker vergibt die Adressen bereits selbst und **fest** — das Subnetz gehört der Sitzung,
die Adresse dem Container, beides steht in Dockers eigener Verwaltung. Ein DHCP-Server daneben
würde um dieselbe Aufgabe streiten, und ein Arbeitsplatz bräuchte einen DHCP-Client, der seine
Route ändern darf — also wieder `NET_ADMIN`. **Deine „IP → Container"-Liste bekommst du trotzdem**,
und sogar zuverlässiger: Sie kommt aus OTAs eigener Tabelle und ist damit immer aktuell (siehe
„Netzübersicht" unten).

**Keine fertige Firewall-Lösung.** Du hast danach gefragt, und die Antwort ist ehrlich
enttäuschend:

| Kandidat | Warum nicht |
|---|---|
| **OPNsense / pfSense** | FreeBSD. Läuft als VM, nicht als Container. |
| **VyOS** | Es gibt Container-Abbilder und eine HTTP-API. Aber es ist ein vollständiges Router-Betriebssystem, das man je Sitzung umkonfigurieren müsste — und die Route-Injektion oben bräuchte es trotzdem. Viel Maschine für wenig Nutzen. |
| **OpenWrt im Container** | Dasselbe in kleiner. Die `ubus`-API ist nicht dafür gedacht, im Sekundentakt von einer fremden Anwendung gefahren zu werden. |
| **firewalld** | Läuft auf dem Wirt — genau das wollen wir loswerden. |

**Empfehlung: `nftables` + `dnsmasq` in einem kleinen Container, gefahren über unsere eigene API.**
Weniger Teile als ein eingebettetes Router-Betriebssystem, und jede Regel ist eine, die wir selbst
geschrieben haben. Der Container bleibt klein genug, dass man ihn in einer Stunde versteht.

---

## Was `ota-fw` tut

Vier Aufgaben, mehr nicht:

1. **Routen** zwischen den Sitzungsnetzen und dem Uplink — und **nur** dorthin, wo es erlaubt ist.
2. **NAT** (Masquerade) auf dem Uplink, damit die Arbeitsplätze unter einer Adresse nach draussen
   gehen. Für vorgelagerte Firewalls im Unternehmen ist das genau eine Adresse statt 256.
3. **DNS** — `dnsmasq`, erreichbar nur aus den Sitzungsnetzen. Freigaben nach Namen tragen sich
   beim Beantworten in eine Menge ein, mit der Lebensdauer der Antwort. (Eine Auflösung auf Vorrat
   ist bei jedem Ziel hinter einem Lastverteiler falsch.)
4. **Portfreigaben nach innen** — die „+NAT"-Funktion, siehe unten.

Er bekommt seinen Zustand von OTA als **Gesamtbild**, nicht als Einzelbefehle: „So sieht die Welt
aus." Ein verlorener Aufruf heilt sich damit beim nächsten Mal von selbst; bei Einzelbefehlen
bleibt sonst etwas offen, ohne dass etwas kaputtgeht — und niemand merkt es.

---

## Was OTA steuert

### Der Grundregelsatz — sichtbar, nicht versteckt

Was **jede** Sitzung erreichen darf, damit OTA funktioniert, steht in der Oberfläche unter
**Netz → Was ohne Zutun gilt**: Ziel, Ports, Protokoll, **Grund** und **Herkunft** je Zeile.

Die Liste ist abgeleitet und nicht eingetragen — die Werte kommen aus `deploy/.env` und aus dem
Aufbau. Sie ist deshalb zu sehen, aber nicht zu ändern. **Zu sehen sein muss sie trotzdem:** Eine
Firewall, von der niemand weiss, was sie ohnehin durchlässt, macht aus jedem Problem erst einmal
die Frage, ob TURN überhaupt erlaubt ist.

### Netzprofile — drei Stufen und Listen

| Stufe | Bedeutung |
|---|---|
| **Abgeschottet** | Nur der Grundregelsatz. Kein Internet, kein LAN. |
| **Internet** *(Vorgabe)* | Grundregelsatz plus alles ausserhalb der privaten Bereiche. Das Firmennetz bleibt zu. |
| **Aus** | Die Firewall lässt alles durch. |

**„Aus" heisst nicht „ohne Firewall".** Der Arbeitsplatz hängt weiter am selben Kabel und geht
weiter durch `ota-fw` — der Router leitet nur alles weiter, statt zu filtern. Das ist besser als in
Fassung 1, wo „offen" bedeutet hätte, dass der Container wieder direkt am Netz des Wirts hängt.
Verlangt eine Begründung und steht im Protokoll.

Dazu je Profil eine **Freigabeliste**: Ziel (IP, CIDR **oder Name**), Ports oder Portbereich,
Protokoll — und eine **Notiz als Pflichtfeld**. Eine Freigabe ohne Begründung ist in einem Jahr
eine, die niemand zu entfernen wagt.

**Zwei Profile bringt jede Anlage mit** — „Standard" (internet) und „Abgeschottet". Eine leere
Liste wäre keine Vorgabe, sondern eine Aufgabe: Bis jemand sie erledigt, liefe alles auf einer
eingebauten Vorgabe, ohne dass irgendwo stünde, welche das ist. Eines mit der Stufe „aus" ist
**nicht** dabei — ein Profil, das man nur noch zuweisen muss, wird zugewiesen.

### Globale Freigaben

Was für **alle** Arbeitsplätze gilt: der Dateiserver, das interne Rechenzentrum, der Paketspiegel.
Dieselbe Form wie im Profil, aber an einer Stelle gepflegt. Reihenfolge: Grundregelsatz → globale
Freigaben → Profil-Freigaben → Stufe.

### Netzübersicht — die Hostliste

Eine Tabelle über alle laufenden Arbeitsplätze:

```
  Nutzer      Arbeitsplatz     Adresse       Profil        Freigaben nach aussen
  anna        Entwicklung      10.99.1.2     Entwickler    30017 → 8080  (bis 12.09.)
  bernd       Büro             10.99.2.2     Standard      —          [+ NAT]
  cem         Labor            10.99.3.2     Abgeschottet  —          [+ NAT]
```

Das ist die „IP → Container"-Liste, und sie ist immer richtig, weil sie aus den laufenden Sitzungen
kommt und nicht aus einer gepflegten Datei.

### „+ NAT" — eine Portfreigabe über den Wirt

Der Knopf in der Zeile. Er fragt drei Dinge: **welcher Port im Arbeitsplatz**, **wie lange**, und
**wofür** (Pflichtfeld — dieselbe Regel wie bei den Freigaben).

Wie es funktioniert: `ota-fw` veröffentlicht beim Start des Stapels einen **Portbereich** auf dem
Wirt (Vorgabe 30000–30099). Eine Freigabe belegt daraus einen Port und leitet ihn auf den
Arbeitsplatz weiter. Der Nutzer bekommt „erreichbar unter `<wirt>:30017` bis zum 12.09." Der
Ablauf wird durchgesetzt, nicht nur angezeigt: Ist die Frist um, verschwindet die Regel beim
nächsten Abgleich, und der Vorgang steht im Protokoll.

Warum ein fester Bereich und keine beliebigen Ports: Dockers Portveröffentlichung steht beim Start
des Containers fest; ein neuer Port bräuchte einen Neustart von `ota-fw` — und der ist der Weg
**aller** Arbeitsplätze nach draussen. Ein reservierter Bereich kostet nichts und erspart das.

**Beantragt wird das ausserhalb** (Mail an den Administrator), wie du es beschrieben hast. OTA
bildet die Entscheidung ab, nicht den Antrag.

### Der Grundregelsatz

Was jede Sitzung darf, damit OTA überhaupt funktioniert — unabhängig von der Stufe:

| Ziel | Warum |
|---|---|
| Antwortpakete (`ESTABLISHED,RELATED`) | Ohne das funktioniert nichts. |
| **DNS** → `ota-fw` selbst | Namensauflösung. Ein anderer Resolver ist nicht erreichbar. |
| **TURN** → Wirt, 3478 und der Relay-Bereich | Der Medienweg. |
| **OTA selbst** → Traefik, 8443 | Der Browser im Arbeitsplatz muss OTA erreichen — die Firefox-Erweiterung für die Zwischenablage wird von dort geladen. |
| **Firmenproxy**, falls gesetzt | Sonst kommt hinter dem Proxy nichts durch. |
| **NTP**, optional | Eine falsche Uhr bricht TLS. |

Traefik erreicht den Arbeitsplatz auf 6901 bzw. 8080 — die Gegenrichtung, und nur von Traefik.

---

## Was dabei abfällt: Messen und Sehen

Wenn aller Verkehr durch **eine** Stelle läuft, ist das Zählen fast geschenkt — und es ist der
zweite gute Grund für diesen Aufbau. Auf dem Wirt wäre dasselbe nur mit Mühe zu haben gewesen,
weil dort niemand weiss, welches Paket zu welcher Sitzung gehört.

**Was billig ist** (nftables zählt ohnehin mit, es muss nur ausgelesen werden):

| Wert | Woher | Wofür |
|---|---|---|
| **Durchsatz je Arbeitsplatz**, ein und aus | Zähler an der Kette der Sitzung | Wer zieht das Netz leer, und wann |
| **Verworfene Pakete je Arbeitsplatz** | Zähler an der Sperre | **Das interessanteste Signal.** Ein Arbeitsplatz, der plötzlich hundert verschiedene Ziele im Firmennetz anspricht, ist ein Portscan — und sieht in dieser Zahl genau so aus |
| **Offene Verbindungen** | `conntrack` | Last, und ein zweites Scan-Signal |
| **Abgewiesene Namensanfragen** | `dnsmasq` | Etwas im Container will woandershin, als es soll |
| **Summe über alle** | dieselben Zähler | Kapazitätsplanung: Was kostet ein Arbeitsplatz wirklich |

Ausgegeben wird das über OTAs vorhandenen Weg: `/metrics` (mit Merkmal, siehe
`security.md`) und eine Spalte in der Netzübersicht. Die Zähler stehen je
**Sitzung**, nicht je Person — wer dahintersteht, löst erst die Oberfläche auf, und dafür braucht
es Rechte.

**Was ausdrücklich nicht kommt:** kein Mitschneiden von Inhalten, kein Aufbrechen von TLS, keine
Liste besuchter Adressen. Das wäre technisch möglich und wäre der Punkt, an dem aus einer Firewall
eine Überwachungsanlage wird.

**Und ein Hinweis, der dazugehört.** Durchsatz und Verbindungen je Arbeitsplatz sind
personenbezogene Daten, sobald sich eine Sitzung einem Menschen zuordnen lässt — und sie lässt
sich. Damit gilt dasselbe wie für das Protokoll in [`dsgvo.md`](dsgvo.md#6--beschäftigtendatenschutz--was-mitbestimmungspflichtig-ist):
**eine Frist** (mein Vorschlag: Rohwerte 7 Tage, Tagessummen 90 Tage) und ein Punkt in der
Betriebsvereinbarung. Die Sicherheitssignale — verworfene Pakete, abgewiesene Namen — sind dabei
der leichtere Teil: Sie sagen etwas über eine *Maschine*, nicht über einen Menschen. Die
Durchsatzzahlen sind der schwerere.

Zum Bauen gehört das in eine eigene Etappe, nicht in die erste. Die Zähler kosten nichts, wenn der
Aufbau von Anfang an je Sitzung eine eigene Kette hat — genau das ist der Punkt, den man **jetzt**
mitdenken muss und später nicht mehr nachrüsten kann, ohne alles anzufassen.

---

## Was aus dem abgebrochenen Bau bleibt

Ungefähr zwei Drittel. Das ist der Grund, warum der Neuanfang billig ist:

| Bleibt | Fliegt weg |
|---|---|
| Ein Netz je Sitzung, eigener Bereich `10.99.0.0/16`, Vergabe im Agent (`netz.py`) | Die Ketten auf dem Wirt (`DOCKER-USER`, `INPUT`) |
| Datenmodell `net_profiles`, Stufen, Freigabeliste mit Pflichtnotiz | Die Ausnahme für Traefiks umgeschriebenen DNAT |
| API-Router, Prüfungen auf dem Server, Protokolleinträge | Die Sperre gegen fremde Resolver (im neuen Aufbau gegenstandslos) |
| Der Weg Vorlage → Profil → Agent → Firewall | Die Abgleichschleife gegen Dockers Neustart |
| Vollabgleich statt Einzelbefehlen, Zustand auf Platte | `dnsmasq` im Namensraum des Wirts |
| Der Unix-Socket statt eines Ports | |

---

## Risiken, ehrlich

* **`ota-fw` ist ein privilegierter Container** (`SYS_ADMIN`, `NET_ADMIN`, Zugriff auf die
  Namensräume). Er ist damit nach dem Agent der zweite Dienst, dessen Übernahme teuer wäre. Dafür
  bleibt der Wirt sauber.
* **Er ist der einzige Weg nach draussen.** Fällt er aus, hat kein Arbeitsplatz mehr Netz — der
  Bildschirm läuft weiter (der geht über Traefik), aber Internet und Firmennetz sind weg. Das ist
  bei einem echten Router genauso; es gehört in die Überwachung.
* **Er liegt im Datenweg.** Für den Bildstrom nicht (Traefik → Arbeitsplatz), wohl aber für alles,
  was der Nutzer selbst abruft. Kosten: eine Weiterleitung mehr. Sollte gemessen werden.
* **Die Route-Injektion hängt an einem Docker-Detail** (`SandboxKey`). Ändert Docker das, hat eine
  neue Sitzung kein Netz. Deshalb: beim Start prüfen und **laut** scheitern, nicht still.
* **Viele Schnittstellen an einem Container.** 50 Sitzungen sind 50 `veth`-Paare an `ota-fw`. Muss
  gemessen werden (Etappe 0, Punkt 4).

---

## Etappen

| # | Schritt | Aufwand |
|---|---|---|
| **0** | **Die vier Annahmen messen** (siehe oben). Erst danach wird gebaut. | ½ Tag |
| 1 | `ota-fw` als Router: Uplink, Masquerade, `nftables`-Grundgerüst, Zustand über Unix-Socket | 1–2 Tage |
| 2 | Sitzungsnetze auf `internal` umstellen, Route-Injektion, Traefik-Anbindung | 1–2 Tage |
| 3 | Regelwerk: Grundregelsatz, globale Freigaben, Profile, Stufen | 1 Tag |
| 4 | `dnsmasq` im Container, Freigaben nach Namen | 1 Tag |
| 5 | Oberfläche: Netzprofile, globale Freigaben, Netzübersicht mit „+ NAT" | 2–3 Tage |
| 6 | Portfreigaben mit Ablauf, Protokoll, Durchsetzung | 1 Tag |
| 7 | `scripts/test-firewall.sh` — misst **von innen**, nicht am Regelwerk | ½ Tag |
| 8 | Zähler auslesen, `/metrics`, Spalte in der Netzübersicht, Fristen | 1–2 Tage |

**Etappe 0 ist nicht verhandelbar.** Die erste Fassung ist an drei Annahmen gescheitert, die
niemand vorher geprüft hatte. Diesmal stehen sie vorn.

---

## Wo die Anlage jetzt steht

**Gebaut, gemessen, in Betrieb** (2026-09-04). Der Aufbau steht so, wie er oben beschrieben ist:
ein `internal`-Netz je Sitzung, alle enden im Router, der Router ist der einzige Weg nach draussen.
`scripts/test-firewall.sh` prüft 19 Dinge **von innen** und läuft in `make test` mit. Bedienung und
Alltag stehen im Handbuch, [Kapitel 23](docs/wiki/23-netz.md).

Vier Dinge sind unterwegs anders gekommen als geplant. Sie stehen hier, weil sie beim nächsten Mal
Zeit sparen:

* **Die Brücke des Wirts war das letzte Loch.** Das Regelwerk stand vollständig — und der
  Arbeitsplatz erreichte den Wirt trotzdem, über `10.99.k.1`. Dieser Verkehr wird nicht
  weitergeleitet, also sieht ihn keine Forward-Regel. Die Lösung ist eine Netzoption:
  `com.docker.network.bridge.inhibit_ipv4` — dann hat die Brücke gar keine Adresse, und es gibt
  dort nichts anzusprechen.
* **Fremde Resolver mussten doch gesperrt werden.** Der Entwurf sagte, aus einem `internal`-Netz
  gebe es keinen Weg zu `8.8.8.8`. Über den Router hinaus gibt es ihn sehr wohl, sobald die Stufe
  „internet" alles Öffentliche erlaubt. Zwei Zeilen im Regelwerk.
* **Der Router verliert seine Netze, wenn er neu gebaut wird.** Ein neuer Container bekommt nur die
  Netze aus der Compose-Datei. Deshalb zieht jeder Abgleich die Anbindung nach — für den Router
  **und** für Traefik.
* **`ping` ist als Probe unbrauchbar.** Ein Arbeitsplatz hat kein `NET_RAW`; `ping` scheitert dort
  immer. Eine Prüfung, die damit misst, meldet „abgeschottet", wo nichts abgeschottet ist.

Die drei schweren Befunde der Sicherheitsbetrachtung — Wirt und Firmennetz aus jedem Arbeitsplatz
erreichbar, Arbeitsplätze untereinander erreichbar, der Agent aus jedem Arbeitsplatz erreichbar —
sind damit geschlossen. Nicht durch Regeln, die richtig greifen müssen, sondern durch den Aufbau: Ein Arbeitsplatz hat keinen Weg, der am Router vorbeiführt.

### Feste Adressen

Jedes Paar (Mensch, Arbeitsplatz) bekommt ein Subnetz und behält es (`net_leases`). Annas
Entwicklungs-Arbeitsplatz ist damit immer `10.99.7.x` — auch nach dem Feierabend, auch nach einem
Neustart. Das war nicht im ersten Entwurf und hat sich als notwendig herausgestellt: Eine
vorgelagerte Firewall im Unternehmen lässt sich nicht auf eine Adresse einstellen, die morgen eine
andere ist, und in der Übersicht stünde jeden Tag etwas Neues.

**Die Portfreigaben hängen trotzdem nicht an der Adresse**, sondern an Mensch und Arbeitsplatz. Sie
überleben den Feierabend, stehen in der Liste weiter (mit dem Vermerk „wartet auf Start") und
greifen beim nächsten Start wieder — gemessen: zweimal gestartet, dieselbe Adresse, dieselbe
Freigabe.
