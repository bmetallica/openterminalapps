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

#### Dauerhaft installieren ⚠️

Der Weg über `about:debugging` hält nur bis zum nächsten Neustart von Firefox. Für den Dauerbetrieb
gibt es zwei Wege, und beide brauchen eine Entscheidung ausserhalb von OTA:

| Weg | Was zu tun ist | Wann sinnvoll |
|---|---|---|
| **Unternehmensrichtlinie** | `policies.json` mit `ExtensionSettings` verteilen, die Erweiterung von einer internen Adresse installieren lassen | Der übliche Weg im Unternehmen. Firefox nimmt so auch unsignierte Erweiterungen an, wenn sie über die Richtlinie kommen |
| **Signatur durch Mozilla** | Die Erweiterung bei addons.mozilla.org einreichen (auch als „unlisted", dann ohne Veröffentlichung) | Wenn keine Richtlinien ausgerollt werden können |

Firefox ESR erlaubt zusätzlich `xpinstall.signatures.required=false`. Das ist bequem, hebt die
Signaturpflicht aber für **alle** Erweiterungen auf — also nur dort, wo das bewusst getragen wird.

Der Quelltext liegt in `extension/firefox/` und ist keine hundert Zeilen. Wer ihn vor dem Ausrollen
prüfen will, findet dort drei Dateien: das Manifest, das Hintergrundskript und die Brücke zur Seite.

## Zwischen Apps im Arbeitsplatz ✅

Kopieren in VS Code, einfügen in IntelliJ — funktioniert.

Technisch ist das nicht selbstverständlich: Jede Anwendung läuft auf einem eigenen X-Display mit
eigener Zwischenablage. OTA betreibt deshalb im Container eine **Brücke**, die den Inhalt zwischen
allen laufenden Displays gleich hält. Sie startet automatisch, sobald die zweite Anwendung
geöffnet wird, und folgt den Rechten des Workspace — ist das Kopieren dort abgeschaltet, läuft
auch die Brücke nicht.

Geprüft wird das mit:

```bash
./scripts/test-clipboard-bridge.sh
```

Sechzehn Prüfungen: beide Richtungen, Umlaute, mehrzeiliger Code mit Tabulatoren, **ein Bild**,
**ein Megabyte Text**, das Verhalten **nach Pause und Fortsetzen** und der Fall, dass die
Zwischenablage im Workspace **abgeschaltet** ist.

**Auch Bilder gehen über die Brücke** — seit dem 2026-08-28. Vorher nicht, und das fiel niemandem
auf, weil es nichts dazu zu sehen gab: Ein Bild kommt nicht als Text aus der Zwischenablage. Wer sie
nur nach Text fragt, bekommt nichts und hält sie für leer. Ein Screenshot war damit in der
Nachbaranwendung unerreichbar, ohne jede Meldung.

**Die Markierung wandert nicht mit.** Was man mit der Maus markiert (die X-PRIMARY-Auswahl), bleibt
auf seinem Display. Das ist Absicht: Sonst überschriebe jede Markierung in einer Anwendung die
Markierung in allen anderen.

## Für Administratoren

### Einstellungen je Workspace ✅

Im Workspace-Editor unter **Rechte → Zwischenablage**:

| Schalter | Wirkung | Technisch |
|---|---|---|
| Einfügen erlauben | Browser → Session | `AcceptCutText` |
| Kopieren erlauben | Session → Browser | `SendCutText` |
| Bilder übertragen | `image/png` zusätzlich zu Text | `DLP_ClipTypes` |
| Markieren und Mittelklick | X-PRIMARY-Auswahl zusätzlich zu Strg+C | `SendPrimary` / `SetPrimary` |

Ab Werk sind Kopieren, Einfügen und Bilder **an**, ohne Größenbegrenzung. Die PRIMARY-Auswahl ist
**aus** — sie überrascht Nutzer, die Markieren nicht als Kopieren erwarten.

Gruppen können strenger sein als der Workspace, nie großzügiger.

### Was bei der Umsetzung wichtig ist

Diese Punkte scheitern in Eigenbauten regelmäßig, und zwar **lautlos**:

1. **HTTPS ist Pflicht.** `navigator.clipboard` existiert nur im Secure Context. Deshalb ist TLS in
   OTA keine Härtungsmaßnahme, sondern Voraussetzung.
2. **Das iframe braucht die Erlaubnis ausdrücklich.** Der Session-Viewer bettet den Stream ein. Ohne
   `allow="clipboard-read; clipboard-write"` blockiert die Permissions-Policy alles, ohne Fehler.
3. **Nicht auf `readText()` allein bauen.** Firefox stellt es nicht bereit. Der Standardweg ist das
   `paste`-Ereignis, `readText()` nur als Zusatz.
4. **Der Server darf nichts zurücknehmen.** Traefik sendet in OTA
   `Permissions-Policy: clipboard-read=(self), clipboard-write=(self), …` — eine restriktive Vorgabe
   an dieser Stelle macht alles andere wirkungslos.
5. **Der KasmVNC-Client schaltet die Zwischenablage im iframe selbst ab.** Er prüft
   `window.self !== window.top` und setzt dann `clipboard_up` und `clipboard_down` auf `false`;
   empfangene Inhalte werden danach verworfen — ohne Fehler, ohne Meldung. OTA hängt deshalb
   `clipboard_up=1&clipboard_down=1` an die Stream-Adresse, denn Parameter in der Adresse schlagen
   den Vorgabewert des Clients. Wer den Viewer umbaut oder die Adresse selbst zusammensetzt, muss
   diese Parameter mitnehmen, sonst ist der Weg aus der Session heraus wieder tot.

### Abnahme

„Copy-Paste geht" ist keine prüfbare Aussage. Die vollständige Matrix mit zwölf Fällen steht in
`plan.md` §10.5 und wird in **Chrome und Firefox** durchlaufen. Die beiden Fälle, die erfahrungsgemäß
durchrutschen: IntelliJ (Java behandelt X11-Zwischenablage eigenwillig) und der Weg zwischen zwei
Apps im selben Arbeitsplatz.

**Zehn von zwölf Fällen laufen bei jedem Testlauf automatisch mit** (`make test`):

| | |
|---|---|
| Browser → Session, Session → Browser, mehrzeiliger Text mit Umlauten | `tests/e2e.mjs`, im echten iframe |
| Zwischen zwei Apps, beide Richtungen | `scripts/test-clipboard-bridge.sh` |
| Ein Bild (`image/png`) | dito — seit dem 2026-08-28 |
| Ein Megabyte Text, vollständig und nicht abgeschnitten | dito |
| PRIMARY auf demselben Display, **und** dass es die Displaygrenze nicht überschreitet | dito |
| Nach Pause und Fortsetzen | dito |
| Abgeschaltet heisst abgeschaltet, und kommt beim Wiedereinschalten zurück | dito |

Offen bleiben drei: zwischen **zwei Sessions** (zwei Container gleichzeitig im Browser), **IntelliJ**
(der Start dauert Minuten) und **Firefox ohne `readText()`** — der Testbrowser ist Chromium.

## Dateien

**Upload** legt Dateien im Ordner `Uploads` der Session ab. **Download** reicht Dateien aus der
Session an den Browser weiter. Beides ist je Workspace abschaltbar.

Für große oder dauerhafte Datenmengen sind Netzlaufwerke der bessere Weg
([Kapitel 8](08-nutzer-und-gruppen.md)).

## Ton und Mikrofon

Audioausgabe wird in den Browser gestreamt und ist je Workspace schaltbar. Das Mikrofon ist
standardmäßig **aus** und braucht zusätzlich die Freigabe des Browsers.
