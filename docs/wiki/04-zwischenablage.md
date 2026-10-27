# 4 · Zwischenablage, Dateien und Ton

Kopieren und Einfügen ist die Funktion, an der eine Remote-Desktop-Plattform im Alltag steht oder
fällt. Deshalb bekommt sie ein eigenes Kapitel.

## Für Anwender

**Der Normalfall**: Strg+C und Strg+V funktionieren in beide Richtungen — vom Browser in die Session
und zurück, **und zwischen zwei Anwendungen im selben Arbeitsplatz**. Auch Bilder, nicht nur Text.

**Wenn es nicht geht**, in dieser Reihenfolge prüfen:

1. **Läuft die Seite über `https://`?** Browser geben die Zwischenablage nur über HTTPS frei. Über
   `http://` ist sie technisch nicht verfügbar — das lässt sich in der Anwendung nicht umgehen.
2. **Hat die Session den Fokus?** Einmal in den Bildschirmbereich klicken. Ohne Fokus erreichen
   Tastenanschläge die Session nicht.
3. **Hat der Browser gefragt?** Chrome verlangt beim ersten Lesen eine Freigabe. Wurde sie abgelehnt,
   steht sie im Schloss-Symbol der Adressleiste.
4. **Ist es im Workspace erlaubt?** Der Administrator kann Kopieren und Einfügen getrennt abschalten.
   Das Zwischenablage-Panel sagt dann, dass es gesperrt ist.

**Das Panel als Rückfall**: In der Kontrollleiste gibt es ein Textfeld in beide Richtungen. Es
funktioniert immer, auch wenn der Browser die automatische Zwischenablage verweigert.

### Firefox ✅

Firefox stellt Webseiten das *automatische Lesen* der Zwischenablage nicht zur Verfügung. Das ist
keine Einstellung, die sich umlegen liesse, sondern eine Festlegung des Browsers.

**Ohne Erweiterung** nutzt OTA dort den Weg über das Einfüge-Ereignis: Du drückst Strg+V, und der
Inhalt wird übernommen. Das funktioniert zuverlässig, verlangt aber jedes Mal den Tastendruck im
richtigen Fenster.

**Mit der OTA-Erweiterung** verhält sich Firefox wie Chrome: Kopieren und Einfügen gleichen sich von
selbst ab. Die Erweiterung tut nichts anderes — sie reicht den Lesezugriff an genau eine Adresse
weiter.

Wenn OTA in Firefox läuft und die Erweiterung fehlt, steht in der Kontrollleiste ein Hinweis mit
einem Knopf zum Herunterladen. Der Weg dorthin von Hand:

1. In der Session die Kontrollleiste öffnen (Griff am rechten Rand).
2. Unter **Zwischenablage** auf **Erweiterung herunterladen**.
3. In Firefox `about:debugging` → **Dieser Firefox** → **Temporäres Add-on laden** → die
   heruntergeladene ZIP-Datei auswählen.
4. Auf das Symbol der Erweiterung in der Symbolleiste klicken, während OTA offen ist. Erst dieser
   Klick gibt sie für diese Adresse frei — vorher darf sie nichts.

Der Weg über `about:debugging` hält nur bis zum nächsten Neustart von Firefox. Dauerhaft
installiert die Verwaltung die Erweiterung, wende dich dafür an sie.

## Zwischen Apps im Arbeitsplatz ✅

Kopieren in VS Code, einfügen in IntelliJ — funktioniert.

Technisch ist das nicht selbstverständlich: Jede Anwendung läuft auf einem eigenen X-Display mit
eigener Zwischenablage. OTA betreibt deshalb im Container eine **Brücke**, die den Inhalt zwischen
allen laufenden Displays gleich hält. Sie startet automatisch, sobald die zweite Anwendung
geöffnet wird, und folgt den Rechten des Workspace — ist das Kopieren dort abgeschaltet, läuft
auch die Brücke nicht.

**Auch Bilder gehen über die Brücke** — seit dem 2026-08-28. Vorher nicht, und das fiel niemandem
auf, weil es nichts dazu zu sehen gab: Ein Bild kommt nicht als Text aus der Zwischenablage. Wer sie
nur nach Text fragt, bekommt nichts und hält sie für leer. Ein Screenshot war damit in der
Nachbaranwendung unerreichbar, ohne jede Meldung.

**Die Markierung wandert nicht mit.** Was man mit der Maus markiert (die X-PRIMARY-Auswahl), bleibt
auf seinem Display. Das ist Absicht: Sonst überschriebe jede Markierung in einer Anwendung die
Markierung in allen anderen.

## Dateien

Dateien kommen über **Meine Ablage** in den Arbeitsplatz und wieder heraus, im Browser und in der
Kontrollleiste einer laufenden Session. Was wo liegt und was erhalten bleibt, steht in
[Kapitel 31](31-dateien.md).

## Ton und Mikrofon

Was im Arbeitsplatz Ton ausgibt, hörst du im Browser. Ein Mikrofon gibt es nicht.
