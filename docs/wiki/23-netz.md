# 23 · Das Netz der Arbeitsplätze ✅

*Für Administratoren.*

Jeder Arbeitsplatz hängt in einem **eigenen Netz**. Alle diese Netze enden in einem
Router (`ota-firewall`), und der Router ist der einzige Weg nach draussen. Einen Weg daran vorbei
gibt es nicht — die Netze sind so angelegt, dass Docker selbst keinen NAT einrichtet und keine
Standardroute vergibt.

**Das ist der Unterschied zu einer Sammlung von Regeln**: Die Absicherung ist eine Eigenschaft des
Aufbaus. Wenn der Router nichts durchlässt, kommt nichts durch — nicht, weil eine Regel greift,
sondern weil es keinen anderen Weg gibt.

Zu finden unter **Netz**. Es braucht das Recht `settings.manage`.

## Was ohne Zutun gilt

| Ziel | |
|---|---|
| Das Internet | ✅ erlaubt |
| Das Firmennetz (alle privaten Bereiche) | ❌ zu |
| Der Arbeitsplatz eines Kollegen | ❌ zu |
| Der Wirt, auf dem OTA läuft | ❌ zu |
| Der TURN-Server, OTA selbst, die Namensauflösung | ✅ erlaubt — sonst käme kein Bild an |

Das ist die Stufe **Internet**, und sie gilt für jeden Arbeitsplatz ohne eigenes Profil.

## Die drei Stufen

| Stufe | Bedeutung |
|---|---|
| **Abgeschottet** | Nur was OTA selbst braucht. Kein Internet, kein Firmennetz. Für Arbeitsplätze, die nur mit lokalen Daten umgehen. |
| **Internet** *(Vorgabe)* | Wie oben. |
| **Aus** | Der Router lässt alles durch. |

**„Aus" heisst nicht „ohne Firewall".** Der Arbeitsplatz hängt weiter am selben Kabel und geht
weiter durch den Router — der filtert nur nicht mehr. Die Stufe verlangt eine Begründung und steht
im Protokoll (`netprofile.opened`).

## Freigaben

Zwei Listen, beide mit derselben Form: **Ziel · Ports · Protokoll · Notiz**.

* **Global** — was für *alle* Arbeitsplätze gilt: der Dateiserver, das interne Rechenzentrum, der
  Paketspiegel. An einer Stelle gepflegt statt in jedem Profil wiederholt.
* **Je Profil** — was nur diese Gruppe von Arbeitsplätzen braucht.

Als Ziel geht eine Adresse (`192.168.66.10`), ein Bereich (`10.20.0.0/16`) **oder ein Name**
(`git.firma.de`). Ports einzeln (`443`), als Liste (`80,443`) oder als Bereich (`8080-8090`).

**Die Notiz ist Pflicht.** Eine Freigabe ohne Begründung ist in einem Jahr eine, die niemand zu
entfernen wagt.

### Warum Namen funktionieren, obwohl eine Firewall keine Namen kennt

Der Router ist zugleich der Namensdienst der Arbeitsplätze. Gibt er eine Antwort heraus, trägt er
dieselbe Adresse in eine Liste ein — mit der Lebensdauer der Antwort. Freigabe und Verbindung
stammen damit **aus derselben Auskunft** und können nicht auseinanderlaufen.

Der naheliegende Weg — den Namen alle paar Minuten auflösen und die Adresse eintragen — funktioniert
bei allem mit kurzer Lebensdauer oder mehreren Adressen nicht: Der Browser bekommt dann eine andere
Adresse als die eingetragene, und der Zugriff scheitert scheinbar grundlos.

**Ein anderer Namensdienst ist nicht erreichbar**, und das ist Absicht: Wer `8.8.8.8` fragen dürfte,
bekäme Adressen, die in keiner Liste stehen — und die Namensfreigaben wären wirkungslos. (Namen über
verschlüsseltes DNS im Browser umgehen auch das. Das ist die Grenze jeder namensbasierten Freigabe.)

## Die Netzübersicht

Wer arbeitet gerade unter welcher Adresse, mit welchem Profil, wie viel geht durch die Leitung —
und wie viele Pakete wurden verworfen.

**Die verworfenen Pakete sind das interessanteste Feld.** Ein Arbeitsplatz, der plötzlich hundert
verschiedene Ziele im Firmennetz anspricht, ist ein Portscan — und sieht in dieser Zahl genau so
aus. Die Zahlen stehen live und werden nirgends gespeichert; wer eine Zeitreihe daraus macht, legt
personenbezogene Daten an ([Datenschutz](../../dsgvo.md)).

### Feste Adressen

Jedes Paar aus **Mensch und Arbeitsplatz** bekommt ein Netz und behält es. Wer heute unter
`10.99.7.10` arbeitet, tut es morgen wieder — auch nach Feierabend, auch nach einem Neustart. Ohne
das liesse sich eine vorgelagerte Firewall im Unternehmen nicht auf einen Arbeitsplatz einstellen.

## Einen Port nach aussen freigeben („+ NAT")

Wenn jemand seine eigene Anwendung im Arbeitsplatz testen will und sie von aussen erreichbar sein
soll: **Netz → Portfreigaben → Neue Freigabe**, oder der Knopf **+ NAT** in der Zeile eines
laufenden Arbeitsplatzes.

Gefragt wird nach drei Dingen: welcher Port im Arbeitsplatz, wie lange, und **wofür**. Der Port auf
dem Wirt wird vergeben — aus dem Bereich, den der Router beim Start veröffentlicht hat (ab Werk
30000–30019). Der Mensch bekommt „erreichbar unter `<wirt>:30003` bis zum 12.09."

* Die Freigabe hängt an **Mensch und Arbeitsplatz**, nicht an der Sitzung. Sie überlebt den
  Feierabend, steht in der Liste weiter (mit dem Vermerk „wartet auf Start") und greift beim
  nächsten Start wieder.
* **Der Ablauf wird durchgesetzt**, nicht nur angezeigt. Ist die Frist um, verschwindet die Regel
  beim nächsten Abgleich.
* `0 Tage` heisst unbefristet. Erlaubt — aber eine Entscheidung, und sie steht im Protokoll.

**Beantragt wird so etwas ausserhalb von OTA** (eine Mail an die Verwaltung genügt). OTA bildet die
Entscheidung ab, nicht den Antrag.

Reicht der Portbereich nicht, lässt er sich in der `.env` vergrössern (`OTA_NAT_MIN`,
`OTA_NAT_MAX`) — **das erfordert einen Neustart des Routers, und der trennt kurz alle
Arbeitsplätze vom Netz.** Jeder Port kostet ausserdem eine Regel und einen Hilfsprozess; deshalb
sind es ab Werk zwanzig und nicht tausend.

## Wenn etwas nicht geht

| Bild | Ursache |
|---|---|
| „Das Intranet geht nicht" | Vorgabe. Das Firmennetz ist zu — eine Freigabe eintragen, global oder im Profil. |
| Eine Anwendung im Arbeitsplatz kommt nicht ins Internet | Profil steht auf **abgeschottet**. Im Dashboard des Nutzers steht, was gilt. |
| Ein freigegebener **Name** geht nicht | Läuft die Anwendung über verschlüsseltes DNS (DoH), fragt sie den eigenen Namensdienst nicht — dann greift die Freigabe nicht. Adresse statt Name eintragen. |
| Nach einem Neustart des Routers hat niemand Netz | Der Abgleich zieht die Anbindung nach; er läuft alle 30 Sekunden. Bleibt es dabei, sagt `docker logs ota-firewall`, woran es liegt. |
| Kein Bild mehr, aber die Sitzung läuft | Nicht das Netz: Der Bildstrom geht über Traefik, nicht über den Router. Siehe [Kapitel 12](12-fehlersuche.md). |

## Prüfen

```bash
scripts/test-firewall.sh
```

Startet zwei Arbeitsplätze mit verschiedenen Profilen und misst **von innen**: Nachbar, Wirt,
Brücke, Firmennetz, TURN, OTA, Namensauflösung, fremder Namensdienst, Internet je Stufe, eine
Freigabe nach Namen (erlaubt und verboten), eine Portfreigabe an und wieder aus — und alles noch
einmal nach einem Neustart des Routers. Läuft in `make test` mit.

**Von innen und nicht am Regelwerk**, und das ist kein Detail: Beim Bauen stand das Regelwerk
dreimal vollständig da, und trotzdem war etwas offen — die Brücke des Wirts hat keine Regel
gebraucht, um erreichbar zu sein.
