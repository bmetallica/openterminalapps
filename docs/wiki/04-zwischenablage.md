# 4 · Zwischenablage, Dateien und Ton

Kopieren und Einfügen ist die Funktion, an der eine Remote-Desktop-Plattform im Alltag steht oder
fällt. Deshalb bekommt sie ein eigenes Kapitel.

## Für Anwender

**Der Normalfall**: Strg+C und Strg+V funktionieren in beide Richtungen — vom Browser in die Session
und zurück. Auch Bilder, nicht nur Text.

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

### Firefox

Firefox stellt Webseiten das *automatische Lesen* der Zwischenablage nicht zur Verfügung. OTA nutzt
dort den Weg über das Einfüge-Ereignis: Du drückst Strg+V, und der Inhalt wird übernommen. Für dich
macht das keinen Unterschied — es funktioniert, nur die Technik dahinter ist eine andere.

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

Der Test kopiert in beide Richtungen zwischen zwei Displays, mit Umlauten und mehrzeiligem Code
mit Tabulatoren.

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

### Abnahme

„Copy-Paste geht" ist keine prüfbare Aussage. Die vollständige Matrix mit zwölf Fällen steht in
`plan.md` §10.5 und wird in **Chrome und Firefox** durchlaufen. Die beiden Fälle, die erfahrungsgemäß
durchrutschen: IntelliJ (Java behandelt X11-Zwischenablage eigenwillig) und der Weg zwischen zwei
Apps im selben Arbeitsplatz.

## Dateien

**Upload** legt Dateien im Ordner `Uploads` der Session ab. **Download** reicht Dateien aus der
Session an den Browser weiter. Beides ist je Workspace abschaltbar.

Für große oder dauerhafte Datenmengen sind Netzlaufwerke der bessere Weg
([Kapitel 8](08-nutzer-und-gruppen.md)).

## Ton und Mikrofon

Audioausgabe wird in den Browser gestreamt und ist je Workspace schaltbar. Das Mikrofon ist
standardmäßig **aus** und braucht zusätzlich die Freigabe des Browsers.
