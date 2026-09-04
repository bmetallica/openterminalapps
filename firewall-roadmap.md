# Umbau: Netzabsicherung der Arbeitsplätze

Arbeitsplan zum Entwurf in [`firewall.md`](firewall.md). Er hält fest, **was gemacht wird, in
welcher Reihenfolge und warum** — und was davon erledigt ist. Benannt wie
[`auth-roadmap.md`](auth-roadmap.md), die denselben Zweck für die Umstellung auf Keycloak hatte.

**Begonnen:** 2026-09-04 · **Neu geplant:** 2026-09-04, nach dem abgebrochenen ersten Anlauf

---

## Der Stand in einem Absatz

Fassung 1 (Regeln im Netfilter des Wirts) ist zu zwei Dritteln gebaut, läuft, und **schliesst die
Befunde H1, H2 und H3 heute schon** — gemessen. Sie wird trotzdem nicht fertiggebaut: Sie teilt
sich das Regelwerk mit Docker, und das hat unterwegs dreimal weh getan (unten). Fassung 2 hängt
alle Arbeitsplätze an einen Router-Container; die Absicherung ist dann keine Sammlung von Regeln
mehr, sondern eine Eigenschaft des Aufbaus.

**Der Zwischenstand bleibt bis dahin stehen.** Er kostet nichts, und die Lücke bliebe sonst offen.

---

## Etappe 0 · Die vier Annahmen messen — **bevor** gebaut wird

Fassung 1 ist an drei Annahmen gescheitert, die niemand vorher geprüft hatte. Diesmal stehen sie
vorn.

- [x] **Route-Injektion trägt.** `nsenter --net=<SandboxKey> ip route replace default via …`
      gesetzt: ok. Der Arbeitsplatz selbst darf es nicht (`RTNETLINK answers: Operation not
      permitted` bei `cap_drop: ALL`) — genau richtig herum. **Zugabe:** In einem `internal`-Netz
      legt Docker **gar keine** Standardroute an. Ein Arbeitsplatz ohne gesetzte Route kommt also
      nirgendwohin, nicht einmal an den Wirt.
- [x] **Der DNAT bleibt in Ruhe.** Ein Container mit veröffentlichtem Port behielt sein Ziel
      (`172.20.0.7:8080`), auch nachdem er einem `internal`-Netz beitrat; von aussen weiterhin
      HTTP 200. **Der Fehler, der Fassung 1 den Haupteingang zugemacht hat, tritt hier nicht auf.**
- [x] **Traefik erreicht den Arbeitsplatz** im `internal`-Netz (HTTP 200 aus einem Container, der
      in `ota_public` **und** im Sitzungsnetz hängt).
- [x] **40 Netze an einem Container, kein Fehler**, rund 50 ms je Verbindung, 43 Schnittstellen.
      Für die zu erwartenden Sitzungszahlen unkritisch.

**Zwei Lehren aus dem Messen, die in den Bau eingehen:**

* **Routen allein trennen nicht.** Sobald der Router weiterleitet, ist der Wirt durch ihn hindurch
  erreichbar (gemessen: SSH des Wirts vom Arbeitsplatz aus offen, bevor Regeln standen). Die
  Trennung macht das Regelwerk im Router, nicht der Aufbau allein. Der Aufbau sorgt dafür, dass es
  **keinen Weg daran vorbei** gibt — das ist der Unterschied zu Fassung 1, und er bleibt der
  entscheidende.
* **`ping` ist als Probe unbrauchbar.** Ohne `NET_RAW` scheitert es immer, auch wenn das Ziel
  erreichbar ist. Die Prüfreihe misst ausschliesslich mit TCP-Proben — sonst meldet sie
  „abgeschottet", wo nichts abgeschottet ist.

**Entscheidung: weiterbauen wie geplant.** Traefik geht direkt in die Sitzungsnetze.

---

## Etappe 1 · `ota-fw` als Router

- [x] Container mit Uplink, `NET_ADMIN`, `SYS_ADMIN`, Zugriff auf `/run/docker/netns` — **`rshared`**, sonst sieht er nur die Namensräume, die beim Start schon da waren (gemessen)
- [x] `nftables`-Grundgerüst: **je Sitzung eine eigene Kette** — die Zähler hängen daran
- [x] Masquerade auf dem Uplink
- [x] Zustand über den Unix-Socket, Vollabgleich statt Einzelbefehlen *(aus Fassung 1 übernommen)*
- [x] Zustand auf Platte, damit ein Neustart nichts vergisst — **und derselbe Fehler zweimal gefunden**: Auch der Agent hielt die Freigaben nur im Speicher und warf sie bei jedem Neustart weg, während sie in der Datenbank weiterstanden

---

## Etappe 2 · Die Arbeitsplätze hängen nur noch am Router

- [x] Sitzungsnetze auf `internal` umstellen
- [x] Route-Injektion beim Start; **laut scheitern**, wenn sie nicht greift
- [x] `ota-fw` in jedes Sitzungsnetz, Traefik ebenso — **und beides bei jedem Abgleich nachziehen**: Ein neu gebauter Container bekommt nur die Netze aus der Compose-Datei, alle Sitzungsnetze sind weg. Gemessen: Nach einem `up -d --build firewall` hing der Router nur noch am Uplink, und der Arbeitsplatz war stumm vom Netz getrennt.
- [x] Die Ketten auf dem Wirt aus Fassung 1 wieder abbauen
- [x] Waisen aufräumen: Netze ohne Container verschwinden *(übernommen)*

---

## Etappe 3 · Das Regelwerk

- [x] Grundregelsatz: DNS, TURN, OTA selbst, Proxy, NTP
- [x] **Globale Freigaben** — was für alle gilt, an einer Stelle gepflegt
- [x] Netzprofile mit drei Stufen: abgeschottet · internet · **aus**
- [x] „Aus" verlangt eine Begründung und steht im Protokoll (`netprofile.opened`)

---

## Etappe 4 · Namen

- [x] `dnsmasq` im Router-Container, erreichbar nur aus den Sitzungsnetzen
- [x] Freigaben nach Namen über eine nftables-Menge, gefüllt beim Beantworten. **Gemessen**: Profil auf Stufe abgeschottet mit `example.com` freigegeben — `example.com` antwortet mit 200, `debian.org` mit 000, `1.1.1.1:443` bleibt zu; in der Menge standen genau die beiden Adressen, die der Resolver herausgegeben hatte, mit ihrer Lebensdauer.
- [x] Kein zweiter Resolver erreichbar — **fast** von selbst: Über den Router hinaus war `8.8.8.8` sehr wohl erreichbar, solange die Stufe internet alles Öffentliche erlaubt. Zwei Zeilen im Regelwerk schliessen das.

---

## Etappe 5 · Oberfläche

- [x] Netzprofile verwalten *(Datenmodell und API aus Fassung 1 übernommen)*
- [x] Globale Freigaben
- [x] **Netzübersicht**: Nutzer · Arbeitsplatz · Adresse · Profil · Verkehr · abgewiesene Pakete · Freigaben — die „IP → Container"-Liste
- [x] Auswahl des Profils am Arbeitsplatz
- [x] Das geltende Profil im Dashboard des Nutzers — wer die Wirkung nicht kennt, meldet sie als Fehler

---

## Etappe 6 · „+ NAT" — Portfreigaben über den Wirt

- [x] Fester Portbereich am Router (Vorgabe 30000–30019 — jeder Port kostet eine Regel und einen Hilfsprozess)
- [x] Knopf in der Netzübersicht: welcher Port, wie lange, **wofür** (Pflichtfeld)
- [x] Ablauf wird **durchgesetzt**, nicht nur angezeigt
- [x] Anlegen und Entfernen stehen im Protokoll

---

## Etappe 7 · Der Beweis

- [x] `scripts/test-firewall.sh` misst **von innen**: Nachbar, Wirt, Brücke des eigenen Netzes, LAN, TURN, OTA selbst, DNS, fremder Resolver, Internet je Stufe, Freigabe nach Namen (erlaubt **und** verboten), Portfreigabe an und wieder aus. **19 Prüfungen, alle grün.**
- [x] Der Fall nach einem Neustart des Routers — **der Fall, der beim Bauen wirklich zugeschlagen hat.** Ein Neustart des Docker-Dienstes ist in Fassung 2 gegenstandslos: Die Regeln liegen im Namensraum des Routers, nicht in Dockers Ketten.
- [x] In `make test` aufgenommen

---

## Etappe 8 · Messen und Sehen

- [x] Zähler je Sitzungskette auslesen: Durchsatz und verworfene Pakete. **Und dabei die Falle gefunden**: Jedes `nft -f` setzt die Zähler zurück, und die Abgleichschleife läuft alle 30 Sekunden — es gäbe nie eine Zahl älter als eine halbe Minute. Jetzt wird nur gesetzt, was sich geändert hat, und was doch verlorenginge, vorher gerettet.
- ~~Abgewiesene Namensanfragen aus `dnsmasq`~~ — **gegenstandslos.** Der Resolver weist keine Anfrage ab: Er beantwortet jede und trägt nur die freigegebenen Adressen in die Menge ein; gefiltert wird danach am Paket. Es gibt also nichts zu zählen. Und ein Protokoll der gestellten Anfragen wäre die Liste der besuchten Adressen — genau das, was hier ausdrücklich nicht entsteht.
- [x] `/metrics` je Sitzung (nicht je Person) und zwei Spalten in der Netzübersicht
- [x] **Fristen** — und dabei stellte sich heraus, dass es nichts aufzubewahren gibt: Die Zähler werden live aus dem Router gelesen und **nirgends gespeichert**. Wer eine Zeitreihe daraus macht (Prometheus tut genau das), legt personenbezogene Daten an; die Frist dafür steht in [`dsgvo.md`](dsgvo.md).
- [x] Kein Mitschneiden von Inhalten, kein Aufbrechen von TLS, keine Liste besuchter Adressen

---

## Was der erste Anlauf gekostet und gebracht hat

Drei Dinge sind dabei **gemessen** worden, die man sonst nicht gewusst hätte. Sie sind der Grund
für Fassung 2, und sie stehen ausführlich in [`firewall.md`](firewall.md):

1. **Docker schreibt den DNAT veröffentlichter Ports um**, sobald ein Container einem weiteren Netz
   beitritt. Traefik trat einem Sitzungsnetz bei — und OTAs Haupteingang zeigte plötzlich in den
   Adressbereich der Sitzungen, wo die Grundsperre ihn traf. Von aussen kam niemand mehr herein,
   und nirgends stand ein Fehler.
2. **`dnsmasq` mit `bind-dynamic` bindet jede Schnittstelle** — auch die zum Firmennetz. Der eigene
   Resolver stand damit offen im LAN, bis drei Regelpaare ihn wieder schlossen.
3. **`br_netfilter` ist nicht geladen**, und Verkehr auf derselben Brücke läuft deshalb an
   iptables vorbei. Ein gemeinsames Sitzungsnetz hätte sich mit Regeln nie trennen lassen.

Übernommen werden ungefähr zwei Drittel: Netzvergabe, Datenmodell, API, Oberfläche, Vollabgleich,
Unix-Socket. Weggeworfen wird das, was mit dem Regelwerk des Wirts zu tun hat.


---

## Fertig — und was dabei gelernt wurde

**Alle Etappen sind gebaut und gemessen.** `scripts/test-firewall.sh` prüft 19 Dinge von innen und
läuft in `make test` mit.

Vier Fehler sind beim Bauen aufgetreten, die man nicht vorhersehen konnte und die alle dieselbe
Form haben — **etwas war eingerichtet, aber wirkungslos, und nichts sagte es**:

1. **Die Brücke des Wirts.** Das Regelwerk stand vollständig, und der Arbeitsplatz erreichte den
   Wirt trotzdem — über `10.99.k.1`, die Adresse der eigenen Brücke. Dieser Verkehr wird nicht
   weitergeleitet, also sieht ihn keine Forward-Regel. Behoben mit
   `com.docker.network.bridge.inhibit_ipv4`: Die Brücke bekommt gar keine Adresse.
2. **Der Router verlor seine Netze.** Ein `up -d --build firewall` erzeugt den Container neu, und
   ein neuer Container bekommt nur die Netze aus der Compose-Datei. Danach hing er nur am Uplink,
   und jeder Arbeitsplatz war stumm vom Netz getrennt — mit korrekter Standardroute auf einen
   Router, der nicht mehr da war.
3. **Der Agent vergass die Freigaben.** Er hielt sie nur im Speicher; nach seinem Neustart schickte
   der nächste Abgleich einen Satz ohne sie, und eine bestehende Portfreigabe verschwand aus dem
   Router, während sie in Datenbank und Oberfläche weiter stand.
4. **Die Zähler wurden dauernd zurückgesetzt.** Jedes `nft -f` setzt sie auf null, und die
   Abgleichschleife läuft alle dreissig Sekunden. Es hätte nie eine Zahl gegeben, die älter als
   eine halbe Minute war.

Alle vier fielen beim **Messen** auf, keiner beim Lesen des Regelwerks. Das ist der Grund, warum
die Prüfreihe von innen misst und nicht das Regelwerk prüft.
