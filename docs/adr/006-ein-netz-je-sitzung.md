# ADR-006 · Jeder Arbeitsplatz bekommt ein eigenes Netz, der einzige Ausgang ist ein Router

**Stand:** angenommen
**Datum:** 2026-09-04

## Ausgangslage

Alle Arbeitsplätze hingen in einem gemeinsamen Netz (`ota_sessions`). Aus einem Arbeitsplatz heraus
waren damit erreichbar: der Wirt, das gesamte Firmennetz, die Sitzung jedes Kollegen — und der
Agent, der einzige Dienst mit schreibendem Zugriff auf den Docker-Socket. Das war die kürzeste
Strecke von einem beliebigen Nutzer zu root auf dem Wirt.

Der naheliegende Gedanke — Regeln dagegen schreiben — trägt nicht: **Verkehr zwischen zwei
Containern auf derselben Brücke wird von `iptables` gar nicht gesehen**, solange `br_netfilter`
nicht geladen ist. Eine Regel hätte dort nichts gesperrt, sondern nur so ausgesehen.

## Entscheidung

**Ein `internal`-Netz je Sitzung**, angelegt vom Agent, ohne NAT und ohne Standardroute. Alle diese
Netze enden in einem **Router-Container** (`ota-firewall`) mit nftables, NAT und eigenem
Namensdienst; er ist der einzige Weg nach draussen. Gesteuert wird er über OTAs Oberfläche.

## Alternativen

**Regeln auf dem gemeinsamen Netz.** Siehe oben: greift nicht. `br_netfilter` zu laden wäre eine
Änderung am Wirt, die OTA nicht gehört und die jede andere Anwendung darauf mitbetrifft.

**Eine fertige, über eine API steuerbare Firewall-Lösung.** Gesucht, nichts Passendes gefunden:
Was es gibt, verwaltet Netze *für sich* und nicht *aus einer fremden Anwendung heraus*. Der Router
ist deshalb klein und tut nur, was OTA ihm sagt — 700 Zeilen, kein eigener Zustand ausser dem, was
der Agent ihm schickt.

**Dockers `--internal` allein, ohne Router.** Dann hätte kein Arbeitsplatz Internet. Das ist für
manche Vorlagen richtig (die Stufe „abgeschottet") und für die meisten falsch.

**Ein Netz je Nutzer statt je Sitzung.** Weniger Netze, aber zwei Sitzungen desselben Menschen
sähen einander wieder — und die Frage „darf dieser Arbeitsplatz ins Firmennetz?" gehört an die
Vorlage, nicht an die Person.

## Folgen

**Der Router ist eine einzelne Stelle, an der alles hängt.** Startet er neu, sind alle
Arbeitsplätze kurz ohne Netz. Das ist der Preis dafür, dass es keinen Weg an ihm vorbei gibt.
Abgefedert durch `restart: unless-stopped`, einen Healthcheck und einen Abgleich alle 30 Sekunden,
der die Anbindung selbst wiederherstellt — ein neu gebauter Container bekommt sonst nur die Netze
aus der Compose-Datei zurück.

**Die Standardroute muss von aussen gesetzt werden.** Docker lässt einen Container nicht Gateway
sein. Der Router setzt sie deshalb per `nsenter` im Namensraum des Arbeitsplatzes; dafür braucht er
`SYS_ADMIN` und `/run/docker/netns` als `rshared`. Das ist die eine harte Stelle des ganzen
Aufbaus, und sie ist in `firewall.md` beschrieben.

**Der Router hängt in jedem Sitzungsnetz.** Ein Netzwerkport an ihm wäre aus jedem Arbeitsplatz
erreichbar, und wer ihn erreicht, schreibt das Regelwerk. Er hat deshalb **keinen**: Der Agent
spricht mit ihm über einen Unix-Socket, und die Dateirechte entscheiden.

**Freigaben nach Namen funktionieren nur über den eigenen Namensdienst.** Der Router beantwortet
die Anfrage und trägt seine eigene Antwort in die Regel ein — Freigabe und Verbindung stammen aus
derselben Auskunft. Wer verschlüsseltes DNS im Browser benutzt, umgeht das; das ist die Grenze
jeder namensbasierten Freigabe und steht so im Handbuch.

**Gemessen wird von innen.** Beim Bauen stand das Regelwerk dreimal vollständig da, und trotzdem
war der Wirt erreichbar — über die Adresse seiner eigenen Brücke, für die es keine Forward-Regel
gibt. `scripts/test-firewall.sh` misst deshalb aus einem laufenden Arbeitsplatz heraus und nicht
am Regelwerk.
