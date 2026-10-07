# Selkies — OTAs Fork

Dieses Verzeichnis ist **unsere Kopie von Selkies**, dem Streaming-Server der Arbeitsplätze.
OTAs Basisimage wird **nur** aus diesen Quellen gebaut, nicht aus einem Release im Internet.

**Warum:** Am 2026-10-07 waren die Release-Dateien von Selkies 1.6.2, auf denen OTA bis dahin lief,
bei GitHub verschwunden — das Projekt war umbenannt, die alten Releases entfernt. Das Basisimage ließ
sich danach nirgends mehr neu bauen. Ein zweites Mal soll ein Wechsel oben uns nicht treffen: Was
hier liegt, bleibt, und eine neue Fassung von upstream übernehmen wir, wenn **wir** es wollen.

## Herkunft

| | |
|---|---|
| Projekt | <https://github.com/selkies-project/selkies> |
| Lizenz | MPL-2.0 (siehe `LICENSE`); `src/selkies/Xlib` LGPL-3.0 (eigene `LICENSE` dort) |
| Fassung | **2.0.0** (Tag `2.0.0`, Release vom 2026-09-23) |
| Commit | `3ec56fb1538cf077c27156f5ab75b6595a83c461` |
| Release-Quellarchiv | `selkies-2.0.0.tar.gz`, sha256 `906039c44bff11f7e7e9e6515242d49b33aa7427a7ac15555658bc327dcb1f32` |
| Release-Rad | `selkies-2.0.0-py3-none-any.whl`, sha256 `f2777e74d191e2b5063190d40bfc6df00d7a77930620e0048a79267f211cbead` |
| Übernommen | 2026-10-07 |

## Was gegenüber upstream anders ist

Jede Änderung steht hier **und** als eigener Commit in OTAs Repository.

1. **Der gebaute Web-Client ist dabei** (`src/selkies/selkies_web/`). Upstream baut ihn in der
   Release-Pipeline aus `addons/selkies-dashboard` und `addons/selkies-web-core` und hält ihn aus
   Git heraus. Wir haben ihn unverändert aus dem Release-Quellarchiv übernommen (`diff -r` gegen
   `selkies-2.0.0.tar.gz`: gleich), damit der Bau des Basisimages kein Node braucht. Die Quellen
   liegen daneben; wer am Client etwas ändert, baut ihn dort neu und legt das Ergebnis hierher.
   Dazu ist dieselbe Zeile in `.gitignore` und `.dockerignore` auskommentiert — ohne die zweite
   fehlte der Client im Baukontext, und Selkies lieferte auf `/` eine 404.
2. **Weggelassen:** `.git`, `website/` (die Projektseite), `CLAUDE.md` und `AGENTS.md`
   (Anweisungen für KI-Werkzeuge in *deren* Repository — in unserem würden sie mitgelesen).
3. **Fassungsnummer** in `pyproject.toml`: `2.0.0` statt `0.0.0.dev0`. Upstream setzt sie erst
   in der Release-Pipeline ein; im Release-Quellarchiv steht `2.0.0`, und so steht es jetzt hier.
4. **Hinzugefügt:** diese Datei und `ota-abhaengigkeiten.txt`.

Am Programm selbst ist **nichts** geändert. OTA stellt Selkies über seine Einstellungen ein
(`SELKIES_*`, siehe `images/base-desktop/dockerstartup/desktop_startup.sh`); die fünf Eingriffe,
die 1.6.2 brauchte, entfallen.

## Die Abhängigkeiten

`ota-abhaengigkeiten.txt` nennt **alle** Pakete, die Selkies braucht, transitiv, mit Fassung und
Prüfsumme — für Debian 13, Python 3.13, amd64. Darunter die beiden Rust-Erweiterungen, die Bild und
Ton aufnehmen und kodieren:

| Paket | Fassung | Lizenz | Quelle |
|---|---|---|---|
| `pixelflux` | 2.1.0 | MPL-2.0 | <https://github.com/selkies-project/pixelflux> |
| `pcmflux` | 2.1.0 | MPL-2.0 | <https://github.com/selkies-project/pcmflux> |

Beide gibt es auf PyPI **nur als fertige Räder**, nicht als Quellarchiv. Sie liegen deshalb mit
allen anderen im **Datei-Vorrat** der eigenen Paketquelle (`dateien/selkies/2.0.0/raeder/`,
Handbuch Kapitel 26), und der Bau nimmt sie von dort — ohne Internet. Ohne Vorrat kommen sie von
PyPI, geprüft gegen dieselben Prüfsummen.

Selbst übersetzen ließen sie sich auch (Rust, dazu die Kodierer-Bibliotheken x264, libvpx,
SVT-AV1 …). Das ist der Weg, falls PyPI sie einmal nicht mehr führt: Quellen der Fassung 2.1.0
holen, mit `maturin` bauen, Räder in den Vorrat legen, Prüfsummen hier eintragen.

## Abhängigkeiten erneuern

```bash
# in einem Debian-13-Container mit Python 3.13 (z. B. dem Image ota/repo)
python3 -m venv /v && /v/bin/pip download --dest /raeder --only-binary=:all: setuptools wheel
/v/bin/pip download --dest /raeder third_party/selkies
# dann die Liste neu schreiben: Name==Fassung --hash=sha256:… je Datei
```

## Auf eine neue Fassung von upstream wechseln

1. Tag auschecken, Inhalt hierher kopieren (ohne die oben weggelassenen Teile).
2. Den gebauten Client aus dem Release-Quellarchiv nach `src/selkies/selkies_web/`.
3. Die Tabelle oben und `ota-abhaengigkeiten.txt` erneuern.
4. `scripts/build-desktop-image.sh --pruefen` und `scripts/test-streaming.sh`.
5. Als **eigener Commit**, damit ein Rückweg ein `git revert` ist.
