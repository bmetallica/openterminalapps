# ADR-004 · Registry-Signaturen werden nicht geprüft

**Stand:** angenommen
**Datum:** 2026-08-27

## Ausgangslage

Ein Kasm-Registry-Katalog trägt ein ES256-JWT über einen Hash seines Inhalts. Aus diesem Katalog
entstehen Image-Referenzen, die anschliessend als Container im eigenen Netz laufen. Wer den Katalog
unterwegs ändert, ändert damit, was gestartet wird.

Der öffentliche Schlüssel zu dieser Signatur wird von Kasm nicht veröffentlicht.

## Entscheidung

OTA prüft die Signatur **nicht** und sagt in der Oberfläche deutlich, dass eine Registry eine
Vertrauensentscheidung des Administrators ist.

## Alternativen

**Den Schlüssel aus dem Kasm-Quelltext oder einer Installation ziehen und fest einbauen.**
Technisch möglich. Aber ein Schlüssel, den der Herausgeber nicht als solchen veröffentlicht, kann
jederzeit wechseln, ohne dass das eine Ankündigung wäre. Die Prüfung fiele dann irgendwann aus, und
zwar als Fehlermeldung bei einer Registry, an der nichts falsch ist.

**Die Signatur prüfen, wenn sie da ist, und sonst durchwinken.** Das ist die schlechteste Variante:
Es sieht nach Prüfung aus, und wer sie umgehen will, lässt die Signatur einfach weg.

**Nur eine feste Liste von Registries zulassen.** Nimmt dem Administrator eine Entscheidung ab, die
ihm gehört — und die Adresse einer eigenen, internen Registry ist ein naheliegender Wunsch.

## Folgen

**Der Katalog ist nur so vertrauenswürdig wie die Verbindung und der Betreiber.** Deshalb ist
**https Pflicht** (`agent/otaagent/registry.py`): Ohne sie könnte jeder auf dem Weg den Katalog
ändern, und die Vertrauensentscheidung wäre gegenstandslos.

**Die Oberfläche muss reden.** Der Import-Dialog sagt, dass ein importiertes Image aus fremder
Quelle kommt und im eigenen Netz läuft. Ein Hinweis ist schwächer als eine Prüfung — aber ein
ehrlicher Hinweis ist stärker als eine Prüfung, die nichts prüft.

**Die drei bekannten Registries sind Vorschläge, keine Voreinstellung.** Wenn eine Registry eine
Entscheidung ist, darf sie nicht schon getroffen sein, bevor jemand hinsieht.

**Rückholbar.** Sollte Kasm den Schlüssel veröffentlichen, wird daraus ein ADR-005, das dieses hier
ablöst. Der Leseweg dafür liegt schon an der richtigen Stelle (`registry.py` liest `signature`
bereits, meldet es aber nur).
