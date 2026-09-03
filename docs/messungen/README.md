# Messungen

Rohdaten aus `make messung` — je Lauf eine Datei `streaming-<datum>.json`.

Was drinsteht und wie es zustande kommt, erklärt der Kopf von
[`scripts/mess-streaming.mjs`](../../scripts/mess-streaming.mjs). Die Kurzfassung:

- **`ohne` / `mit`** — dieselbe Last einmal ohne und einmal mit Betrachter. Die Differenz ist der
  Preis des Stroms; die Kosten der Anwendung kürzen sich heraus.
- **`kerne`** — CPU-Zeit des Session-Containers, geteilt durch die verstrichene Zeit. 1,0 ist ein
  voller Kern.
- **`mbitS`** — aus dem Zähler der Netzkarten. Der einzige Wert, den beide Maschinen gleich melden.
- **`reaktion`** — von Glas zu Glas in Millisekunden: vom Umschalten der Fläche im Container bis zu
  dem Einzelbild, in dem der Browser es sieht.
- **`kerneGrenze`** — was die Vorlage erlaubt. Liegt ein Messwert nahe daran, ist er gedeckelt und
  zu klein.

**Die Zahlen gelten für diese Maschine** — vier Kerne, keine GPU, x264 in Software — und für
1280×720. Auf anderer Hardware sind sie andere; das Verhältnis der beiden Wege zueinander bleibt.

Ausgewertet stehen sie im Handbuch, [Kapitel 20](../wiki/20-selkies-versuch.md#was-es-kostet--gemessen).
