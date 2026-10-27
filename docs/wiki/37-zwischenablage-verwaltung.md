# 37 · Zwischenablage für Administratoren

*Für Administratoren.* Einstellungen, Technik und Abnahme der Zwischenablage. Was Anwender
wissen müssen, steht in [Kapitel 4](04-zwischenablage.md).

## Einstellungen je Workspace ✅

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

## Was bei der Umsetzung wichtig ist

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

## Abnahme

„Copy-Paste geht" ist keine prüfbare Aussage. Die vollständige Matrix mit zwölf Fällen steht in
`plan.md` §10.5. Die beiden Fälle, die erfahrungsgemäß durchrutschen: IntelliJ (Java behandelt die
X11-Zwischenablage eigenwillig) und der Weg zwischen zwei Apps im selben Arbeitsplatz.

**Elf von zwölf Fällen laufen bei jedem Testlauf automatisch mit** (`make test`):

| | |
|---|---|
| Browser → Session, Session → Browser, mehrzeiliger Text mit Umlauten | `tests/e2e.mjs`, im echten iframe |
| Zwischen zwei Apps, beide Richtungen | `scripts/test-clipboard-bridge.sh` |
| Ein Bild (`image/png`) | dito — seit dem 2026-08-28 |
| Ein Megabyte Text, vollständig und nicht abgeschnitten | dito |
| PRIMARY auf demselben Display, **und** dass es die Displaygrenze nicht überschreitet | dito |
| Nach Pause und Fortsetzen | dito |
| Abgeschaltet heisst abgeschaltet, und kommt beim Wiedereinschalten zurück | dito |
| Zwischen **zwei Sessions** desselben Nutzers | `tests/e2e.mjs` — zwei echte Container, der Weg führt über die System-Zwischenablage des Browsers |
| Ein Browser **ohne `readText()`** | `tests/e2e.mjs` — in Chromium mit abgeschaltetem `readText`. Kein Ersatz für einen Lauf in Firefox, aber es prüft genau den Pfad, der dort greift, bei jedem Lauf |

Der zwölfte ist **IntelliJ** beziehungsweise Java/AWT. Er läuft auf Zuruf:

```bash
OTA_PRUEFE_JAVA=1 scripts/build-base-image.sh --nur-pruefen
```

Nicht bei jedem Lauf, weil er ein JDK in den Prüfcontainer nachinstalliert (~300 MB). Ins Image
gehört das nicht — ein Basisimage, von dem jeder Arbeitsplatz abstammt, trägt kein JDK mit sich
herum, nur damit ein Test es vorfindet.

> **Warum Java eine eigene Zeile hat.** X11 kennt keinen Speicher, in dem etwas liegt: Es gibt
> einen *Besitzer* der Auswahl, und wer den Inhalt will, fragt den Besitzer. AWT bedient diese
> Frage aus einem eigenen Thread und gibt den Besitz auf, sobald die virtuelle Maschine endet.
> Ein Programm, das kopiert und sich sofort beendet, hinterlässt deshalb eine leere
> Zwischenablage — bei Gtk- und Electron-Anwendungen passiert das nicht.

## Ereignisse statt Abfragen

Seit dem 2026-09-01 wartet die Brücke auf Ereignisse, statt im halben Sekundentakt nachzufragen:
`clipnotify -l` je Display meldet jede Änderung. Entschieden wird das **im Container** — fehlt
`clipnotify` (so in allen Kasm-Images), bleibt es beim Takt. Beide Wege teilen sich denselben
Abgleich darunter.

Der Gewinn ist nicht die Last, sondern die Verzögerung: Im Takt liegt zwischen Kopieren und
Einfügen bis zu eine halbe Sekunde, in der die Nachbaranwendung noch den alten Inhalt hat. Wer
schnell genug ist, fügt das Vorherige ein — und das sieht aus wie ein Fehler, den niemand
reproduzieren kann. Über Ereignisse sind es Millisekunden.

`clipnotify` liegt in OTAs eigenem Basisimage ([Kapitel 19](19-eigenes-basisimage.md)).

## Firefox-Erweiterung dauerhaft installieren ⚠️

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

## Die Brücke zwischen Apps prüfen ✅

Geprüft wird das mit:

```bash
./scripts/test-clipboard-bridge.sh
```

Sechzehn Prüfungen: beide Richtungen, Umlaute, mehrzeiliger Code mit Tabulatoren, **ein Bild**,
**ein Megabyte Text**, das Verhalten **nach Pause und Fortsetzen** und der Fall, dass die
Zwischenablage im Workspace **abgeschaltet** ist.
