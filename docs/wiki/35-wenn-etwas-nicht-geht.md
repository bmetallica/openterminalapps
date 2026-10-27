# 35 · Wenn etwas nicht geht

*Für Anwender.* Die häufigsten Stolpersteine, was du selbst tun kannst, und was die Verwaltung von
dir wissen muss, wenn es nicht hilft.

## Erst probieren

| Was du siehst | Was du tust |
|---|---|
| **„Diese Sitzung läuft nicht mehr"** | Die Session wurde beendet, etwa wegen Leerlauf. Zurück zur Startseite und neu starten. Dein Zuhause ist noch da |
| **Schwarzes oder eingefrorenes Bild** | Kontrollleiste → **Neu verbinden**. Hilft das nicht, den Tab schliessen und die Session auf der Startseite neu öffnen |
| **Tastatur reagiert nicht** | Einmal ins Bild klicken, sonst Kontrollleiste → **Fokus setzen** |
| **Kopieren und Einfügen geht nicht** | die Prüfliste in [Kapitel 4](04-zwischenablage.md). Als Rückfall das Textfeld in der Kontrollleiste |
| **Umlaute fehlen, `/` wird zu `?`** | Session beenden und neu starten. Bleibt es, der Verwaltung melden |
| **Bild ruckelt** | rechenintensive Programme im Arbeitsplatz prüfen (Tests, Builds, Indexierung). Dauerhaft: melden |
| **Anwendung im Arbeitsplatz startet nicht** | Session beenden und neu starten. Beim Root-Arbeitsplatz: anhalten und fortsetzen |
| **Desktop leer, ohne Menü und Leiste** | Session beenden und neu starten |
| **Seite zeigt „Die Daten konnten nicht geladen werden"** | Seite neu laden (F5). Direkt nach einem Update der Anlage ist das normal |

## Meldungen beim Start

| Meldung | Bedeutung | Was du tust |
|---|---|---|
| **Zweiter Faktor ist für deine Gruppe Pflicht** | ohne zweiten Faktor kein Start | **Jetzt einrichten** ([Kapitel 30](30-mein-konto.md#zweiter-faktor-)) |
| **„… läuft schon und benutzt dasselbe Zuhause"** | ein anderer Arbeitsplatz hat dein Zuhause offen | den anderen beenden ([Kapitel 31](31-dateien.md#mehrere-arbeitsplätze-ein-zuhause)) |
| **„Dein Zuhause belegt … GB"** | dein Zuhause ist voll | aufräumen: Downloads, Caches, alte Dateien. Oder um mehr Platz bitten |
| **„Dieser Root-Arbeitsplatz belegt … GB"** | der Arbeitsplatz selbst ist voll | [Kapitel 32](32-root-arbeitsplatz-nutzen.md#platz) |
| **„Es sind höchstens … Anwendungen gleichzeitig offen"** | zu viele Anwendungen offen | eine schliessen |

Platz im Zuhause findest du so:

```bash
du -sh ~/* ~/.[!.]* 2>/dev/null | sort -h | tail -15
```

Oft sind es `~/.cache`, `~/Downloads` oder alte Abbilder in `~/.local/share`.

## Was die Verwaltung von dir braucht

Hilft nichts davon, schreib der Verwaltung:

1. **Welcher Arbeitsplatz:** der Name der Kachel
2. **Wann:** Datum und ungefähre Uhrzeit. Damit findet sie den Eintrag im Protokoll
3. **Was genau:** die Meldung im Wortlaut oder ein Bildschirmfoto
4. **Was du vorher getan hast:** gestartet, fortgesetzt, eine Datei hochgeladen …
5. **Seit wann:** nur einmal, oder immer wieder

Die Verwaltung sieht unter **Betrieb**, wie ausgelastet dein Arbeitsplatz ist, und kann sich mit
einem Terminal hineinschalten. Beides steht im Protokoll.
