# OpenTerminalApps — Handbuch

Dieses Handbuch wird im Programm selbst unter **Hilfe** ausgeliefert. Es beschreibt Bedienung,
Verwaltung und Betrieb von OTA.

Welche Kapitel jemand dort sieht, hängt an den Rechten: Anwender bekommen Überblick, Arbeitsplatz,
Zwischenablage und Lizenzen; Verwaltung und Betrieb bleiben Administratoren vorbehalten. Diese
Aufteilung steht in `api/ota/routers/help.py` — wer ein Kapitel hinzufügt, trägt es dort ein.

## Kennzeichnung

Jeder Abschnitt trägt einen Status. Das Handbuch beschreibt bewusst auch Geplantes, damit
Konfigurationsentscheidungen vorausschauend getroffen werden können — aber es sagt immer, was davon
heute schon funktioniert.

| Zeichen | Bedeutung |
|---|---|
| ✅ | verfügbar und geprüft |
| 🔨 | geplant, mit Meilenstein aus der [Roadmap](../../roadmap.md) |
| ⚠️ | Entscheidung offen, siehe `plan.md` §17 |

## Inhalt

**Grundlagen**
1. [Überblick — was OTA ist](01-ueberblick.md)
2. [Erste Schritte — Installation und Start](02-erste-schritte.md)

**Für Anwender**
3. [Der Arbeitsplatz](03-arbeitsplatz.md)
4. [Zwischenablage, Dateien und Ton](04-zwischenablage.md)

**Für Administratoren**
5. [Workspaces verwalten](05-workspaces-verwalten.md)
6. [Ressourcen und Zuteilung je Nutzer](06-ressourcen-und-zuteilung.md)
7. [Golden Images](07-golden-images.md)
8. [Nutzer, Gruppen und Rechte](08-nutzer-und-gruppen.md)
9. [Kasm-Images und Registries einbinden](09-kasm-images-und-registries.md)
16. [Images verwalten](16-images-verwalten.md)
17. [Ablagen und Startskript](17-ablage-und-startskript.md)
18. [Zentrale Anmeldung (Keycloak)](18-zentrale-anmeldung.md)
19. [Das eigene Basisimage](19-eigenes-basisimage.md)
20. [Selkies — der Streaming-Weg](20-selkies-versuch.md)
21. [Betrieb hinter einem Firmenproxy](21-firmenproxy.md)
22. [Die eigene Marke — Name, Farbe, Zeichen](22-marke.md)
23. [Das Netz der Arbeitsplätze](23-netz.md)

**Betrieb**
10. [Zertifikate und HTTPS](10-zertifikate-und-https.md)
11. [Betrieb und Updates](11-betrieb.md)
12. [Fehlersuche](12-fehlersuche.md)
13. [Lizenzen](13-lizenzen.md)
14. [Sicherung und Wiederherstellung](14-sicherung.md)
15. [Ein Profil aus Kasm übernehmen](15-migration-aus-kasm.md)

Die Nummern sind die Reihenfolge, in der die Kapitel entstanden sind, nicht die, in der man sie
liest — deshalb stehen 16 bis 23 zwischen 9 und 10. Umnummerieren würde jeden Verweis brechen, der
irgendwo schon steht.

## Wo was steht

Dieses Handbuch erklärt **Bedienung und Betrieb**. Die Begründungen hinter den Entscheidungen — warum
eine Engine gewählt wurde, wie das Datenmodell aussieht, welche Alternativen verworfen wurden — stehen
in [`plan.md`](../../plan.md). Die zeitliche Planung in [`roadmap.md`](../../roadmap.md).

Für die wenigen Entscheidungen, die teuer rückgängig zu machen sind und in einem Jahr die Frage
„warum eigentlich?" auslösen, gibt es eigene Einträge in
[`docs/adr/`](../adr/README.md) — jeweils mit den Alternativen, die nicht getragen hätten.
