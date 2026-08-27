# 6 · Ressourcen und Zuteilung je Nutzer

*Für Administratoren.* Workspace-Editor → Reiter **Zuteilung**.

## Das Problem

Derselbe Arbeitsplatz soll für verschiedene Menschen verschieden groß sein. Der Entwickler bekommt
4 Kerne und 6 GB, der Werkstudent 1 Kern und 2 GB, externe Dienstleister pauschal wenig.

Der naheliegende Weg wäre, den Workspace zu kopieren. **Das ist der falsche Weg** — er vervielfacht
die Pflege von Image, Rechten, App-Katalog und Golden-Image-Version. Drei Kopien bedeuten drei
Stellen, an denen man ein Update vergessen kann.

## Die Lösung: Abweichungen

OTA legt **nur die abweichenden Werte** ab. Alles andere wird weitervererbt.

```
1.  Vorgabe der Vorlage            4 Kerne / 6,0 GB
2.  Abweichung je Gruppe           Gruppe "externe": 2 Kerne / 3,0 GB
3.  Abweichung je Nutzer           tim.r: 1 Kern / 1,0 GB
                                   ↓
    Das Spezifischste gewinnt.
```

Gehört jemand mehreren Gruppen an, entscheidet die Gruppe mit der höheren Priorität.

## In der Oberfläche

Der Reiter **Zuteilung** listet jeden Nutzer, der den Workspace über eine zugewiesene Gruppe
erreicht — auch die ohne eigene Abweichung. Sonst müsste man raten, wen die Vorlage betrifft.

Je Zeile: Name, geltende Kerne, geltender Speicher und die **Herkunft**:

| Kennzeichnung | Bedeutung |
|---|---|
| `VORLAGE` | erbt alles |
| `GRUPPE` | eine Gruppenabweichung greift |
| `NUTZER` | eigene Zuteilung, blau markiert |
| `GEMISCHT` | Kerne und Speicher kommen aus verschiedenen Ebenen |

Aufklappen zeigt die Regler für genau diesen Nutzer, mit derselben Überbuchungs-Schraffur wie sonst.
An der Vererbungsmarke steht, woher der aktuelle Wert stammt; **Zurücksetzen** entfernt die
Abweichung wieder.

## Wann welche Ebene

| Ebene | Wofür |
|---|---|
| **Vorlage** | Der Normalfall. Was die meisten bekommen sollen |
| **Gruppe** | Ganze Personenkreise: Externe, Auszubildende, ein Projektteam mit hohem Bedarf |
| **Nutzer** | Die Ausnahme. Einzelne Menschen mit belegtem Sonderbedarf |

Als Faustregel: Wenn eine Nutzerabweichung mehr als zwei- oder dreimal identisch auftaucht, gehört
sie in eine Gruppe.

## Wirksamwerden

Änderungen gelten für die **nächste** Session. Laufende bleiben unberührt — es wäre schwer erklärbar,
wenn jemandem mitten in der Arbeit der Speicher entzogen würde.

Beim Start wird der aufgelöste Wert festgeschrieben und als `--cpus` und `--memory` an den Container
übergeben. In der Session-Übersicht ist er nachvollziehbar.

## Überbuchung

OTA hindert niemanden daran, mehr zuzusagen, als der Host hat — das ist bei wechselnder Nutzung oft
sinnvoll. Aber es wird sichtbar gemacht:

- Der Regler schraffiert den überbuchten Bereich
- Die Kapazitätsanzeige über der Liste färbt sich rot
- Beim Start prüft OTA den **tatsächlich freien** Speicher und lehnt mit einer verständlichen
  Meldung ab, statt den Host in den OOM-Kill laufen zu lassen

## Was noch nicht je Nutzer einstellbar ist

Auflösung, Rechte und Timeouts folgen der Vorlage und den Gruppen-Einstellungen. Das Datenmodell sieht
Abweichungen dafür vor (`plan.md` §9.7), die Oberfläche zeigt sie noch nicht. 🔨
