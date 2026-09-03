# 19 · Das eigene Basisimage

> **Hinweis.** Dieses Kapitel beschreibt `ota/base-xfce` — Ubuntu + XFCE +
> KasmVNC. Es ist **nicht mehr die Vorgabe**: Die ist seit dem Wechsel auf
> Selkies `ota/base-desktop` (Debian 13, ohne KasmVNC), beschrieben in
> [Kapitel 20](20-selkies-versuch.md). `base-xfce` bleibt bestehen und wird
> gepflegt, solange Arbeitsplätze darauf laufen — für Images von Kasm ist es
> weiterhin der richtige Weg.

*Für Administratoren.* ✅ `ota/base-xfce` — Ubuntu 24.04 + XFCE + KasmVNC, ohne Anwendung.
**Steht als Testimage bereit** und löst noch nichts ab.

## Warum überhaupt eines

Bis jetzt leitet jeder Arbeitsplatz von einem Kasm-Anwendungsimage ab — `kasmweb/vs-code` und
Verwandte. Das brachte drei Dinge mit, die dort stören:

1. **Eine Anwendung, die von selbst startet.** Kasm-Images für einzelne Anwendungen bringen ein
   `custom_startup.sh` mit, das „ihre" Anwendung startet, und `vnc_startup.sh` startet dieses
   Skript **alle drei Sekunden neu**, sobald es sich beendet. In einem Arbeitsplatz ist das
   verheerend: gemessen am 2026-08-27 waren es nach sechs Minuten 119 leere VS-Code-Fenster,
   2,5 GB belegt, schwarzer Bildschirm. OTA legt deshalb ein eigenes Skript darüber.
2. **20 GB für einen Editor, den der Arbeitsplatz gar nicht startet.**
3. **Das Label `com.kasmweb.image`.** Kasms Aufräumer löscht im Modus „Aggressive" alle
   30 Sekunden genau die Images, die es tragen und nicht in seiner Datenbank stehen — ein
   frisch gebautes Golden Image war Sekunden später weg.

Und drei Kleinigkeiten fehlten, an denen die Zwischenablage hängt: `clipnotify`, `xsel`,
`autocutsel` ([Kapitel 4](04-zwischenablage.md)).

**965 MB statt 20 GB.** Das eigene Basisimage enthält keine Anwendung — die kommt beim Bau des
Golden Image dazu ([Kapitel 7](07-golden-images.md)).

## Bauen und prüfen

```bash
scripts/build-base-image.sh              # baut ota/base-xfce:test
scripts/build-base-image.sh --pruefen    # baut und prüft es danach
scripts/build-base-image.sh --nur-pruefen
```

Die Prüfung ist keine Formsache. Sie startet den Container so, wie OTA ihn startet, und misst
27 Punkte gegen den **Vertrag mit dem Agent**:

| Was | Warum es geprüft wird |
|---|---|
| KasmVNC nimmt auf **6901** an | Daran erkennt der Agent, dass die Session bereit ist |
| Kennung **1000**, Zuhause `/home/kasm-user` | Dorthin hängt der Agent das Profil; die Ablagen auf der Platte gehören 1000:1000 |
| `.kasmpasswd` mit dem Namen **`kasm_user`** | Vor dem Stream setzt OTA einen Basic-Auth-Header mit genau diesem Namen. Mit `kasm-user` (Bindestrich) fragt der Bildschirm nach einem Passwort, das niemand kennt |
| `.vnc/self.pem` | KasmVNC hört nur mit TLS (`-sslOnly`) |
| `Xvnc`, `xauth`, `mcookie`, `xfwm4`, `wmctrl`, `xdotool` | Damit öffnet der Agent weitere Displays und startet Anwendungen darauf |
| Ein **zweites Display**, eine Anwendung darauf | Der Kern des Arbeitsplatzmodells |
| `clipnotify`, `xsel`, `autocutsel` und die Brücke | Zwischenablage ereignisgesteuert statt im Halbsekundentakt |
| **Kein** `com.kasmweb.image` | Sonst räumt Kasms Aufräumer es weg |
| `ota/arbeitsplatz` liegt unverändert daneben | Der Beweis, dass nichts Bestehendes angefasst wurde |

Mit `OTA_PRUEFE_JAVA=1` kommt Abnahmefall 7 dazu (Java/AWT, stellvertretend für IntelliJ). Er
läuft nicht von selbst mit, weil er ein JDK in den **Prüfcontainer** nachinstalliert — rund
300 MB. Ins Image gehört das nicht: Ein Basisimage, von dem jeder Arbeitsplatz abstammt, trägt
kein JDK mit sich herum, nur damit ein Test es vorfindet.

## Es heisst `:test`, und das ist Absicht

Keine Vorlage zeigt darauf, `ota/arbeitsplatz` bleibt unberührt. Erst wenn ein Arbeitsplatz
darauf nachweislich so läuft wie bisher, wird daraus eine Fassung ohne `test` im Namen.

Wer es ausprobieren will, legt eine **eigene Vorlage** damit an (Workspaces → Neu, `image_ref`
auf `ota/base-xfce:test`) und lässt die bestehende in Ruhe. Zwei Vorlagen mit
`persistence_scope: user` teilen sich allerdings dasselbe Zuhause — gib der Probevorlage unter
*Persistenz* ein eigenes Profil, sonst weist OTA die zweite Session ab.

## KasmVNC bleibt drin — die Lizenzfrage ist geprüft

KasmVNC steht unter **GPL-2.0-or-later**; nachgesehen nicht in einem Blogeintrag, sondern in
`/usr/share/doc/kasmvncserver/copyright` im gebauten Image. Es unverändert aus dem offiziellen
Release zu übernehmen und als eigenes Programm zu starten, ist genau der Fall, für den die GPL
gemacht ist.

Es ist sogar **sauberer als vorher**: `kasmweb/*`-Images sind MIT nur für die Baurezepte — das
fertige Abbild ist ein Bündel fremder Software unter „Other". Ubuntu + XFCE + offizielles
KasmVNC-Paket besteht dagegen aus einzeln nachlesbaren Teilen. Ausführlich in
[Kapitel 13](13-lizenzen.md) und in `THIRD-PARTY-NOTICES.md`.

Pflichten greifen erst, wenn ein Image das Haus verlässt. Dann gehört die Stückliste dazu:

```bash
make sbom          # je Image eine Stückliste in SPDX und CycloneDX, nach sbom/
```

## Und etwas ganz Eigenes statt KasmVNC?

Die Frage kam beim Bauen auf, und die Antwort ist: **selbst gebaut hiesse hier schlechter.**
x11vnc ist einfädig und seit Jahren ungepflegt; TigerVNC ist der Stamm, von dem KasmVNC abzweigt
— wir würden gerade die Teile weglassen, die ihn ausmachen (mehrfädige WebP-Kodierung,
`DLP_ClipDelay`, `KasmPasswordFile`). Ein eigenes Protokoll wären Personenjahre.

Wirklich besser wäre nur ein **Wechsel des Verfahrens: WebRTC statt RFB**, mit GStreamer und
H.264/VP8 — niedrigere Latenz, brauchbares Video, GPU-Kodierung. Der Preis ist ebenso real: UDP
und ein TURN-Weg durch den Ingress, eine Audiokette, und Reconnect, Leerlauf-Abschaltung und
Zwischenablage der Oberfläche sind gegen die Schnittstelle des KasmVNC-Clients geschrieben. Das
ist ein eigener Meilenstein mit eigener Abnahme — ein zweites Testimage daneben, und dann wird
gemessen statt geglaubt (`roadmap.md`).
