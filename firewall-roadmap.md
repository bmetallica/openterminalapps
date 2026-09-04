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

- [ ] Lässt sich die Standardroute im Namensraum eines fremden Containers setzen
      (`nsenter --net=<SandboxKey>`), ohne dass dieser Container eine Fähigkeit bekommt?
- [ ] Veröffentlicht Docker auf `internal`-Netzen wirklich keine Ports — bleibt der DNAT von 8443
      in Ruhe, wenn Traefik einem Sitzungsnetz beitritt? *(In Fassung 1 hat genau das den
      Haupteingang zugemacht.)*
- [ ] Erreicht Traefik einen Arbeitsplatz in einem `internal`-Netz?
- [ ] Wie viele Netze verträgt ein Container? Bei 50 Sitzungen hat `ota-fw` 50 Schnittstellen.

**Ergebnis dieser Etappe ist eine Entscheidung**, kein Code: weiterbauen wie geplant, oder Traefik
den Weg zum Arbeitsplatz ebenfalls über `ota-fw` geben.

---

## Etappe 1 · `ota-fw` als Router

- [ ] Container mit Uplink, `NET_ADMIN`, `SYS_ADMIN`, Zugriff auf `/var/run/docker/netns`
- [ ] `nftables`-Grundgerüst: **je Sitzung eine eigene Kette** — das ist die Stelle, die man jetzt
      richtig machen muss, weil die Zähler daran hängen (Etappe 8)
- [ ] Masquerade auf dem Uplink
- [ ] Zustand über den Unix-Socket, Vollabgleich statt Einzelbefehlen *(aus Fassung 1 übernommen)*
- [ ] Zustand auf Platte, damit ein Neustart nichts vergisst *(übernommen)*

---

## Etappe 2 · Die Arbeitsplätze hängen nur noch am Router

- [ ] Sitzungsnetze auf `internal` umstellen
- [ ] Route-Injektion beim Start; **laut scheitern**, wenn sie nicht greift — ein Arbeitsplatz ohne
      Route ist besser als einer, der still am Wirt vorbeiredet
- [ ] `ota-fw` in jedes Sitzungsnetz, Traefik dorthin, wo Etappe 0 es entschieden hat
- [ ] Die Ketten auf dem Wirt aus Fassung 1 wieder abbauen
- [ ] Waisen aufräumen: Netze ohne Container verschwinden *(übernommen)*

---

## Etappe 3 · Das Regelwerk

- [ ] Grundregelsatz: DNS, TURN, OTA selbst, Proxy, NTP
- [ ] **Globale Freigaben** — was für alle gilt, an einer Stelle gepflegt
- [ ] Netzprofile mit drei Stufen: abgeschottet · internet · **aus**
- [ ] „Aus" verlangt eine Begründung und steht im Protokoll

---

## Etappe 4 · Namen

- [ ] `dnsmasq` im Router-Container, erreichbar nur aus den Sitzungsnetzen
- [ ] Freigaben nach Namen über eine Menge, gefüllt beim Beantworten — nicht aus einer Auflösung
      von vorgestern
- [ ] Kein zweiter Resolver erreichbar (im neuen Aufbau von selbst so)

---

## Etappe 5 · Oberfläche

- [ ] Netzprofile verwalten *(Datenmodell und API aus Fassung 1 übernommen)*
- [ ] Globale Freigaben
- [ ] **Netzübersicht**: Nutzer · Arbeitsplatz · Adresse · Profil · Freigaben — die „IP → Container"-Liste
- [ ] Auswahl des Profils am Arbeitsplatz
- [ ] Das geltende Profil im Dashboard des Nutzers — wer die Wirkung nicht kennt, meldet sie als Fehler

---

## Etappe 6 · „+ NAT" — Portfreigaben über den Wirt

- [ ] Fester Portbereich am Router (Vorgabe 30000–30099), beim Start veröffentlicht
- [ ] Knopf in der Netzübersicht: welcher Port, wie lange, **wofür** (Pflichtfeld)
- [ ] Ablauf wird **durchgesetzt**, nicht nur angezeigt
- [ ] Anlegen, Verlängern und Ablauf stehen im Protokoll

---

## Etappe 7 · Der Beweis

- [ ] `scripts/test-firewall.sh` misst **von innen**: Nachbar, Wirt, LAN, TURN, DNS, fremder
      Resolver, Internet je Stufe, eine Freigabe, eine Portfreigabe
- [ ] Der Fall nach einem Neustart von Docker **und** nach einem Neustart des Routers
- [ ] In `make test` aufgenommen

---

## Etappe 8 · Messen und Sehen

- [ ] Zähler je Sitzungskette auslesen: Durchsatz ein/aus, verworfene Pakete, offene Verbindungen
- [ ] Abgewiesene Namensanfragen aus `dnsmasq`
- [ ] `/metrics` je Sitzung (nicht je Person) und eine Spalte in der Netzübersicht
- [ ] **Fristen**: Rohwerte 7 Tage, Tagessummen 90 Tage — und ein Absatz in
      [`dsgvo.md`](dsgvo.md), weil Durchsatz je Arbeitsplatz personenbezogen ist
- [ ] Kein Mitschneiden von Inhalten, kein Aufbrechen von TLS, keine Liste besuchter Adressen

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
