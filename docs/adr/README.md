# Architekturentscheidungen

Hier steht, **warum** OTA an einigen Stellen so gebaut ist, wie es gebaut ist — und nicht, wie es
gebaut ist. Das Wie steht in [`plan.md`](../../plan.md) und im [Handbuch](../wiki/README.md).

Eine Entscheidung bekommt einen eigenen Eintrag, wenn drei Dinge zusammenkommen:

1. Sie war **umstritten** — es gab mindestens eine ernstzunehmende Alternative
2. Sie ist **teuer rückgängig zu machen**
3. Jemand wird in einem Jahr fragen: *„Warum eigentlich?"*

Alles andere gehört in einen Kommentar an die Stelle, an der es passiert. Ein ADR für eine
Entscheidung, die niemand hinterfragt, verwässert die, die es wert sind.

## Format

```markdown
# ADR-00N · Titel als Aussagesatz

**Stand:** angenommen | abgelöst durch ADR-00M | zurückgezogen
**Datum:** JJJJ-MM-TT

## Ausgangslage
Was war das Problem? Was war der Zwang, der eine Entscheidung nötig machte?

## Entscheidung
Ein Satz. Im Aktiv.

## Alternativen
Was sonst noch zur Wahl stand — und was daran nicht getragen hätte.

## Folgen
Was das kostet. Auch das Unangenehme; besonders das.
```

**Ein ADR wird nicht geändert, wenn die Entscheidung fällt.** Es bekommt den Stand
*abgelöst durch ADR-00M*, und der neue Eintrag beschreibt, was sich geändert hat. Die alte
Begründung bleibt lesbar — sonst sieht die Geschichte im Nachhinein wie eine Reihe
selbstverständlicher Schritte aus, und das war sie nie.

## Verzeichnis

| | | |
|---|---|---|
| [ADR-001](001-arbeitsplatz-als-fundament.md) | Der Arbeitsplatz ist das Fundament, Einzel-Apps sind ein Feature | angenommen |
| [ADR-002](002-nur-der-agent-fasst-docker-an.md) | Nur der Agent fasst Docker und das Dateisystem an | angenommen |
| [ADR-003](003-kasmvnc-als-engine.md) | KasmVNC ist die Streaming-Engine, ein Display je Anwendung | **abgelöst durch ADR-005** |
| [ADR-004](004-keine-signaturpruefung-fuer-registries.md) | Registry-Signaturen werden nicht geprüft | angenommen |
| [ADR-005](005-selkies-statt-kasmvnc.md) | Selkies überträgt das Bild, KasmVNC bleibt für fremde Images | angenommen |
| [ADR-006](006-ein-netz-je-sitzung.md) | Jeder Arbeitsplatz bekommt ein eigenes Netz, der einzige Ausgang ist ein Router | angenommen |
