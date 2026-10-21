#!/usr/bin/env python3
"""Ist OTA vollständig zweisprachig? Prüft Oberfläche, Servermeldungen und Doku.

    scripts/i18n-pruefen.py            Bericht, Exit 1 bei Lücken
    scripts/i18n-pruefen.py --liste    zusätzlich jede Lücke einzeln

Der deutsche Satz ist der Schlüssel (`web/src/lib/i18n.ts`). Geprüft wird:

1. Jeder Text in `t('…')` / `tr('…')` steht in `web/src/lib/i18n.en.ts`.
2. Kein deutscher Text steht ohne Übersetzung im Quelltext der Oberfläche
   (Literale und JSX-Text; eine Schätzung über Umlaute und häufige Wörter).
3. Jede Meldung des Servers (`HTTPException`, `…Fehler(…)`) steht im
   Wörterbuch — wörtlich oder, wenn sie Werte einsetzt, als Muster mit
   Platzhaltern (`„{name}“ ist kein gültiger Name …`).
4. Jedes Kapitel aus `docs/wiki/` gibt es in `docs/wiki/en/`, und es gibt
   `README.en.md` — jeweils mit demselben Aufbau (Überschriften, Codeblöcke,
   Tabellenzeilen, Bilder) wie die deutsche Fassung, und jeder Verweis
   `kapitel.md#abschnitt` zeigt auf eine vorhandene Überschrift.
"""
from __future__ import annotations

import ast
import re
import sys
from pathlib import Path

WURZEL = Path(__file__).resolve().parent.parent
WEB = WURZEL / "web" / "src"
EN_DATEI = WEB / "lib" / "i18n.en.ts"
LISTE = "--liste" in sys.argv

DEUTSCH = re.compile(
    r"[äöüÄÖÜß]|\b(der|die|das|und|nicht|ist|mit|für|von|kein|keine|wird|werden|noch|nur|"
    r"auf|bei|Nutzer|Gruppe|Gruppen|Speichern|Löschen|Abbrechen|Neu|Alle|Fehler|Wird|"
    r"Keine|Kein|Ohne|Datei|Sitzung|Vorlage|Ablage|Hinzufügen|Entfernen|Anlegen|Starten|"
    r"Beenden|Erst|Bitte|Gibt|gibt|nach|oder)\b")


def _entschaerfen(s: str) -> str:
    return s.replace("\\'", "'").replace('\\"', '"').replace("\\n", "\n")


def woerterbuch() -> set[str]:
    text = EN_DATEI.read_text(encoding="utf-8")
    return {_entschaerfen(m.group(2)) for m in re.finditer(
        r"^\s*(['\"])((?:\\.|(?!\1).)*)\1\s*:", text, re.M)}


def _ohne_kommentare(text: str) -> str:
    text = re.sub(r"/\*.*?\*/", lambda m: "\n" * m.group(0).count("\n"), text, flags=re.S)
    return re.sub(r"(^|\s)//.*$", r"\1", text, flags=re.M)


def oberflaeche(en: set[str]) -> tuple[list[str], list[str]]:
    schluessel_fehlt: list[str] = []
    roh: list[str] = []
    for datei in sorted(WEB.rglob("*.ts*")):
        if datei == EN_DATEI:
            continue
        rel = datei.relative_to(WURZEL)
        text = _ohne_kommentare(datei.read_text(encoding="utf-8"))
        for m in re.finditer(r"\b(?:t|tr)\(\s*(['\"`])((?:\\.|(?!\1).)*)\1", text, re.S):
            k = _entschaerfen(m.group(2))
            if k not in en:
                zeile = text[:m.start()].count("\n") + 1
                schluessel_fehlt.append(f"{rel}:{zeile}: {k[:100]}")
        for nr, zeile in enumerate(text.split("\n"), 1):
            for m in re.finditer(r"(['\"])((?:\\.|(?!\1).)+)\1", zeile):
                v = _entschaerfen(m.group(2))
                if v in en or not DEUTSCH.search(v):
                    continue
                vor = zeile[:m.start()]
                if re.search(r"\b(?:t|tr)\(\s*$", vor) or re.search(r"(className|import|from)\b[^'\"]*$", vor):
                    continue
                if v.startswith(("/", ".", "#", "http", "--")) or "${" in v:
                    continue
                if re.fullmatch(r"[a-zäöüß_-]+", v):  # ein Wert wie 'nur', kein Text
                    continue
                roh.append(f"{rel}:{nr}: {v[:100]}")
            # Text zwischen JSX-Tags: >Text< oder eine Zeile, die nur Text ist.
            for m in re.finditer(r">([^<>{}]*[A-Za-zÄÖÜäöüß][^<>{}]*)<", zeile):
                v = m.group(1).strip()
                if v and v not in en and DEUTSCH.search(v) and "=>" not in v:
                    roh.append(f"{rel}:{nr}: JSX {v[:100]}")
            s = zeile.strip()
            if (re.fullmatch(r"[A-ZÄÖÜa-zäöü][^=;(){}<>'\"`]*[a-zäöüß.:!?…)]", s)
                    and DEUTSCH.search(s) and " " in s and s not in en and datei.suffix == ".tsx"):
                roh.append(f"{rel}:{nr}: JSX {s[:100]}")
    return schluessel_fehlt, roh


def _muster(s: str) -> str:
    return re.sub(r"\{\w*\}", "{}", s)


def _vorlage(knoten: ast.JoinedStr) -> str:
    teile = []
    for w in knoten.values:
        if isinstance(w, ast.Constant):
            teile.append(str(w.value).replace("{", "{{").replace("}", "}}"))
        else:
            teile.append("{}")
    return "".join(teile).replace("{{", "{").replace("}}", "}")


def _text(knoten: ast.AST) -> str | None:
    """Der Satz, so wie er beim Server ankommt — Platzhalter als {}."""
    if isinstance(knoten, ast.Constant) and isinstance(knoten.value, str):
        return knoten.value
    if isinstance(knoten, ast.JoinedStr):
        return _vorlage(knoten)
    if isinstance(knoten, ast.BinOp) and isinstance(knoten.op, ast.Add):
        a, b = _text(knoten.left), _text(knoten.right)
        if a is not None and b is not None:
            return a + b
    return None


def server(en: set[str]) -> list[str]:
    exakt = en
    muster = {_muster(k) for k in en if "{" in k}
    fehlt: list[str] = []
    gesehen: set[str] = set()
    for datei in sorted((WURZEL / "api" / "ota").rglob("*.py")):
        rel = datei.relative_to(WURZEL)
        baum = ast.parse(datei.read_text(encoding="utf-8"))
        for k in ast.walk(baum):
            if not isinstance(k, ast.Call):
                continue
            name = getattr(k.func, "id", None) or getattr(k.func, "attr", None) or ""
            if name == "HTTPException":
                kandidaten = list(k.args[1:2]) + [w.value for w in k.keywords if w.arg == "detail"]
            elif name.endswith("Fehler") and name[0].isupper():
                kandidaten = list(k.args[:1])
            else:
                continue
            for a in kandidaten:
                satz = _text(a)
                if not satz or not DEUTSCH.search(satz) or satz in gesehen:
                    continue
                gesehen.add(satz)
                if "{}" in satz:
                    if satz not in muster:
                        fehlt.append(f"{rel}:{k.lineno}: MUSTER {satz}")
                elif satz not in exakt:
                    fehlt.append(f"{rel}:{k.lineno}: {satz}")
    return fehlt


def _aufbau(pfad: Path) -> dict[str, int]:
    """Was beim Übersetzen gleich bleiben muss: Überschriften je Ebene,
    Codeblöcke, Tabellenzeilen, Bilder. Läuft eine Fassung der anderen
    hinterher, fällt es hier auf."""
    text = pfad.read_text(encoding="utf-8")
    ohne_code = re.sub(r"^```.*?^```", "", text, flags=re.S | re.M)
    zaehler = {f"h{n}": len(re.findall(rf"^{'#' * n} ", ohne_code, re.M)) for n in (1, 2, 3, 4)}
    zaehler["Codeblöcke"] = len(re.findall(r"^```", text, re.M)) // 2
    zaehler["Tabellenzeilen"] = len(re.findall(r"^\|", ohne_code, re.M))
    zaehler["Bilder"] = len(re.findall(r"!\[", text))
    return zaehler


def _vergleichen(de: Path, en: Path) -> str | None:
    a, b = _aufbau(de), _aufbau(en)
    abweichend = [f"{k} {a[k]}≠{b[k]}" for k in a if a[k] != b[k]]
    if abweichend:
        return f"{en.relative_to(WURZEL)}: anderer Aufbau als die deutsche Fassung ({', '.join(abweichend)})"
    return None


def _anker(text: str) -> set[str]:
    """Die Anker der Überschriften, so wie GitHub sie bildet."""
    ohne_code = re.sub(r"^```.*?^```", "", text, flags=re.S | re.M)
    anker = set()
    for m in re.finditer(r"^#{1,6} (.+)$", ohne_code, re.M):
        titel = m.group(1).strip().lower()
        titel = re.sub(r"[^\w\- ]", "", titel)
        anker.add(titel.replace(" ", "-"))
    return anker


def verweise() -> list[str]:
    """Jeder Verweis `kapitel.md#anker` muss auf eine Überschrift zeigen —
    in beiden Sprachen. Eine übersetzte Überschrift hat einen anderen Anker."""
    kaputt = []
    wiki = WURZEL / "docs" / "wiki"
    dateien = [WURZEL / "README.md", WURZEL / "README.en.md"]
    dateien += sorted(wiki.glob("*.md")) + sorted((wiki / "en").glob("*.md"))
    for datei in dateien:
        text = datei.read_text(encoding="utf-8")
        for m in re.finditer(r"\]\(([^)#\s]*\.md)?#([^)\s]+)\)", text):
            ziel = (datei.parent / m.group(1)).resolve() if m.group(1) else datei
            if not ziel.is_file():
                kaputt.append(f"{datei.relative_to(WURZEL)}: {m.group(1)} fehlt")
            elif m.group(2) not in _anker(ziel.read_text(encoding="utf-8")):
                kaputt.append(f"{datei.relative_to(WURZEL)}: #{m.group(2)} nicht in {ziel.relative_to(WURZEL)}")
    return kaputt


def doku() -> list[str]:
    fehlt = []
    wiki = WURZEL / "docs" / "wiki"
    paare = [(WURZEL / "README.md", WURZEL / "README.en.md")]
    paare += [(k, wiki / "en" / k.name) for k in sorted(wiki.glob("*.md"))]
    for de, en in paare:
        if not en.is_file():
            fehlt.append(str(en.relative_to(WURZEL)))
        elif (abw := _vergleichen(de, en)):
            fehlt.append(abw)
    return fehlt


def main() -> int:
    en = woerterbuch()
    schluessel, roh = oberflaeche(en)
    srv = server(en)
    dok = doku()
    anker = verweise()
    luecken = 0
    for titel, liste in (("Oberfläche: Schlüssel ohne Übersetzung", schluessel),
                         ("Oberfläche: deutscher Text ohne Übersetzung", roh),
                         ("Server: Meldungen ohne Übersetzung", srv),
                         ("Doku: englische Fassung fehlt", dok),
                         ("Doku: Verweise auf fehlende Abschnitte", anker)):
        print(f"{'OK ' if not liste else 'FEHLT'} {titel}: {len(liste)}")
        if liste and LISTE:
            for z in liste:
                print("   ", z)
        luecken += len(liste)
    print(f"\n{len(en)} Einträge im Wörterbuch, {luecken} Lücken.")
    return 1 if luecken else 0


if __name__ == "__main__":
    sys.exit(main())
