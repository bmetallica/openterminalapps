# ADR-005 · Selkies überträgt das Bild, KasmVNC bleibt für fremde Images

**Stand:** angenommen — löst [ADR-003](003-kasmvnc-als-engine.md) ab
**Datum:** 2026-09-03

## Ausgangslage

[ADR-003](003-kasmvnc-als-engine.md) hat KasmVNC gewählt, und die Entscheidung war richtig: Sie
hat den Arbeitsplatz zum Laufen gebracht. Zwei Dinge sind seither dazugekommen.

**Das Verfahren ist die Grenze.** RFB überträgt rechteckige Ausschnitte. Für ein Terminal und einen
Editor genügt das; ein scrollendes PDF, ein Video, eine Zeichenfläche sehen aus wie eine
Diaschau — und daran ändert keine Einstellung etwas, weil es am Protokoll liegt und nicht an der
Umsetzung.

**Kein Bestandteil des Vorgabe-Images soll „Kasm" heissen.** Das eigene Basisimage war ohnehin
fällig (20 GB gegen 965 MB), und ein Image, das die Software eines Wettbewerbers mitbringt und
dessen Namen in Pfaden, Konten und Umgebungsvariablen trägt, ist eine unnötige Abhängigkeit —
lizenzlich wie praktisch.

## Entscheidung

**Selkies** (MPL-2.0) überträgt das Bild im Vorgabe-Basisimage `ota/base-desktop`: H.264 über
WebRTC, vermittelt über einen TURN-Dienst im Stack. **KasmVNC bleibt** und ist je Vorlage
wählbar — Images von Kasm bringen kein Selkies mit, und die sollen weiter laufen.

## Alternativen

**Bei KasmVNC bleiben.** Der billigste Weg, und für Terminal und Editor ohne Nachteil. Er hätte
aber die Verfahrensgrenze festgeschrieben und den Namen im Vorgabe-Image gelassen.

**Etwas Eigenes bauen.** x11vnc ist einfädig und ungepflegt, TigerVNC ist der Stamm, von dem
KasmVNC abzweigt — man würde gerade die Teile weglassen, die es ausmachen. Eine eigene
WebRTC-Kette wären Personenjahre für ein gelöstes Problem.

**Selkies als alleinige Engine, KasmVNC entfernen.** Hätte die fremden Kasm-Images unbrauchbar
gemacht, und die sind der Grund, aus dem OTA neben einer bestehenden Anlage überhaupt betreibbar
ist.

## Folgen

**Der Medienweg wird zum eigenen Betriebsgegenstand.** WebRTC braucht UDP, einen TURN-Server und
eine Adresse, unter der die **Browser** den Host erreichen. Fünf Fallen lagen darauf, alle
gemessen: Der Client baut zwei Adressen aus der Wurzel statt aus dem Pfad; `cvt` fehlt in Ubuntu
24.04 wie in Debian 13; coturn darf als Nutzer 1000 nicht nach `/var/run` schreiben; **ein
TURN-Server hinter einer Docker-Bridge kann nicht vermitteln**; und **Chrome verschickt DTLS mit
fest 1200 Byte je Paket**, was hinter einem Tunnel mit MTU 1000 nie ankommt. Deshalb gibt es
`scripts/test-streaming.sh` als eigene Prüfreihe — keine andere hätte diese Fehler gefunden, und
im Browser sahen alle gleich aus: „Waiting for stream".

**Zwei Wege, die beide gepflegt werden müssen.** Reconnect, Leerlaufuhr und Zwischenablage gibt es
je Engine. Das ist der Preis dafür, dass fremde Images weiterlaufen; er ist bewusst bezahlt.

**MPL-2.0, und OTA verändert Selkies.** Die Lizenz wirkt **dateiweise**: Wer das Image weitergibt,
legt die **fünf** geänderten Dateien bei — sie stehen in `THIRD-PARTY-NOTICES.md`, und wer einen
Eingriff hinzufügt, trägt ihn dort ein. Dazu libx264 unter GPL-2.0+. Für den Betrieb im eigenen Haus
stellt sich die Frage nicht — beim Weitergeben schon
([Handbuch, Kapitel 13](../wiki/13-lizenzen.md)).

**Gemessen statt geglaubt.** `make messung` vergleicht beide Wege unter derselben Last; die Zahlen
stehen in `docs/messungen/` und in [Kapitel 20](../wiki/20-selkies-versuch.md).
