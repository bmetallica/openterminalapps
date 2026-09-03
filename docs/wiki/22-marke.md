# 22 · Die eigene Marke — Name, Farbe, Zeichen ✅

*Für Administratoren.*

OTA steht in einem Unternehmen und heisst dort selten „OpenTerminalApps". Drei Dinge entscheiden,
ob sich eine Anlage nach *unserem Werkzeug* anfühlt oder nach fremder Software: wie sie heisst,
welche Farbe sie hat und welches Zeichen oben links steht. Genau diese drei lassen sich einstellen,
und mehr nicht — ein Baukasten für Gestaltung soll das hier nicht werden.

Zu finden unter **Einstellungen → Marke**. Es braucht das Recht `settings.manage`.

## Was sich ändert

| Einstellung | Wo sie auftaucht |
|---|---|
| **Name der Anlage** | Reiter des Browsers, Anmeldemaske, Startbildschirm, Name der Verknüpfung auf dem Desktop (PWA) |
| **Akzentfarbe** | aktive Schaltflächen, Regler, Markierungen, Verweise — auch auf der Anmeldemaske von Keycloak |
| **Zeichen** | Anmeldemaske, Startbildschirm, Leiste am linken Rand, Symbol im Reiter des Browsers |

Alles gilt sofort und für alle — es ist eine Einstellung der Anlage, keine des einzelnen Browsers.
Genau andersherum als **Gewand** (dunkel/hell) und **Sprache**: Die liegen im Browser, weil sie zum
Arbeitsplatz gehören und nicht zur Anlage.

## Das Zeichen

SVG, PNG, WebP oder JPEG, höchstens 512 KB.

**Ein SVG darf zeichnen und sonst nichts.** Enthält es ein `<script>`, einen Ereignisbehandler
(`onload=…`) oder ein `<foreignObject>`, wird es abgelehnt — mit Begründung, nicht stillschweigend
beschnitten. Der Grund: Ein SVG ist ein Dokument, und wer es direkt aufruft, bekäme es auf der
Herkunft der Anlage ausgeführt. Hochladen darf ohnehin nur, wer die Anlage verwaltet; das hier ist
die zweite Reihe. Wer ein Logo aus einem Zeichenprogramm exportiert, hat davon nichts drin — und
wenn doch, hilft ein PNG.

**Am besten quadratisch.** Dasselbe Bild steht gross auf der Anmeldemaske und klein in der Leiste
und im Reiter des Browsers. Ein breiter Schriftzug wird dort sehr klein — verzerrt wird er nicht,
aber lesbar ist er dann auch nicht mehr. Wer beides will, nimmt das quadratische Zeichen; der
Schriftzug steht ohnehin als Name daneben.

Das Zeichen liegt in der Datenbank, nicht als Datei auf der Platte. Damit ist es in jeder Sicherung
enthalten und kommt bei einer Wiederherstellung von selbst zurück — ohne einen weiteren
Einhängepunkt, den man beim Aufsetzen vergessen kann.

## Die Farbe

Eine Farbe, angegeben als `#RRGGBB`. Für das helle Gewand wird sie automatisch abgedunkelt, sonst
verschwände sie auf weisser Fläche. Wer sie zurücksetzt, bekommt wieder OTAs Kühlblau `#06B6D4` —
und damit auch dessen eigens abgestimmte helle Fassung.

**Auf der Anmeldemaske von Keycloak** erscheint die Farbe ebenfalls, aber erst ab dem zweiten
Besuch: Die Maske liest sie ohne Rückfrage aus dem Browser, damit sie nicht kurz in der falschen
Farbe aufblitzt — und dort steht sie erst, wenn OTA einmal geöffnet war. Der **Name** und das
**Zeichen** bleiben auf dieser Maske aussen vor; sie gehört Keycloak, und was dort steht, entscheidet
dessen eigenes Thema (`deploy/keycloak-theme/ota/`).

## Was bewusst nicht geht

- **Kein zweites Zeichen** für die Leiste. Ein Bild, drei Grössen — das ist die Beschränkung, die
  den Abschnitt klein hält.
- **Keine freien Farben** für Flächen, Text oder Rahmen. Die Leiter aus Grundfläche, Karten und
  Rahmen ist aufeinander abgestimmt und in beiden Gewändern durchgerechnet; ein Farbwähler dafür
  würde vor allem unlesbare Anlagen erzeugen.
- **Keine Marke je Gruppe.** Eine Anlage, ein Gesicht.
