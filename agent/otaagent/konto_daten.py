"""Zuhause und Ablage eines gelöschten Kontos entfernen.

Ob das überhaupt geschieht und nach welcher Frist, entscheidet die Verwaltung
(Einstellungen → Löschen von Konten). Hier steht nur das Wie:

1. Beim Löschen des Kontos wandern `profiles/<kennung>` und
   `userfiles/<kennung>` in den Papierkorb ihrer Wurzel (`.geloescht/`).
   Daneben liegt eine kleine Datei mit Zeitpunkt und Anmeldenamen. Die
   Verweise unter dem Namen verschwinden sofort; sonst zeigte
   `profiles/anna` ins Leere oder, schlimmer, auf ein neues Konto.
2. Der tägliche Lauf der API (`leeren`) löscht, was älter ist als die Frist.
   Bis dahin lässt sich ein Irrtum von Hand zurückholen (Wiki, Kapitel 08).

Der Papierkorb liegt **in** der jeweiligen Wurzel und nicht daneben: Zuhause
und Ablage können auf verschiedenen Platten liegen, und `rename` funktioniert
nur innerhalb eines Dateisystems. Kopieren wäre bei einem Zuhause von 80 GB
keine Option.

Ein **echtes** Verzeichnis unter dem Anmeldenamen bleibt unberührt. Es stammt
von vor der Umstellung auf Kennungen, und welchem Konto es gehört, weiß hier
niemand sicher.
"""
from __future__ import annotations

import json
import logging
import os
import shutil
import threading
import time
import uuid
from pathlib import Path

log = logging.getLogger("ota.agent.konto_daten")

PAPIERKORB = ".geloescht"
TAG = 86400


def _wurzeln() -> list[Path]:
    return [Path(os.environ.get("OTA_PROFILES_ROOT", "/srv/ota/profiles")),
            Path(os.environ.get("OTA_USERFILES_ROOT", "/srv/ota/userfiles"))]


def _kennung(text: str) -> str:
    """Nur eine UUID taugt als Name im Papierkorb. Alles andere wäre ein Weg
    aus der Wurzel hinaus."""
    return str(uuid.UUID(str(text)))


def _marker(korb: Path, kennung: str) -> Path:
    return korb / f"{kennung}.json"


def _weg(korb: Path, kennung: str) -> bool:
    """Löscht einen Eintrag samt Marker. False, wenn etwas stehen blieb; der
    Marker bleibt dann, und der nächste Lauf versucht es wieder."""
    ziel = korb / kennung
    fehler: list[str] = []
    if ziel.is_symlink():
        ziel.unlink()
    elif ziel.exists():
        shutil.rmtree(ziel, onexc=lambda _f, p, e: fehler.append(f"{p}: {e}"))
    if fehler or ziel.exists():
        log.warning("%s nicht vollständig gelöscht: %s", ziel, "; ".join(fehler[:3]))
        return False
    _marker(korb, kennung).unlink(missing_ok=True)
    return True


def entfernen(kennung: str, name: str = "", sofort: bool = False,
              jetzt: float | None = None) -> dict:
    """Legt Zuhause und Ablage eines Kontos in den Papierkorb.

    `sofort` löscht sie gleich danach, im Hintergrund: Ein großes Zuhause
    braucht Minuten, und die Antwort an die Verwaltung soll nicht warten.
    """
    kennung = _kennung(kennung)
    jetzt = time.time() if jetzt is None else jetzt
    bereiche: list[str] = []
    koerbe: list[Path] = []
    for wurzel in _wurzeln():
        if not wurzel.is_dir():
            continue
        # Verweise, die auf diese Kennung zeigen, unter welchem Namen auch
        # immer; der Name kann sich über die Jahre geändert haben.
        with os.scandir(wurzel) as eintraege:
            for e in eintraege:
                if e.is_symlink() and os.readlink(e.path) == kennung:
                    os.unlink(e.path)
        quelle = wurzel / kennung
        if quelle.is_symlink() or not quelle.is_dir():
            continue
        korb = wurzel / PAPIERKORB
        korb.mkdir(mode=0o700, exist_ok=True)
        ziel = korb / kennung
        if ziel.exists():
            # Kann nur nach einem abgebrochenen Lauf vorkommen: Die Kennung
            # ist einmalig. Das Ältere geht vor.
            _weg(korb, kennung)
        os.rename(quelle, ziel)
        _marker(korb, kennung).write_text(json.dumps({"am": int(jetzt), "name": name}))
        bereiche.append(wurzel.name)
        koerbe.append(korb)

    if sofort and koerbe:
        def loeschen() -> None:
            for korb in koerbe:
                _weg(korb, kennung)
        threading.Thread(target=loeschen, name=f"konto-loeschen-{kennung[:8]}",
                         daemon=True).start()
    return {"bereiche": bereiche, "sofort": sofort}


def leeren(tage: int, jetzt: float | None = None) -> dict:
    """Löscht alles im Papierkorb, was älter ist als `tage`.

    Gibt die endgültig entfernten Konten mit Namen zurück. Die API braucht den
    Namen, um die Sicherungen dieses Kontos mitzunehmen; die hängen am Namen,
    nicht an der Kennung.
    """
    jetzt = time.time() if jetzt is None else jetzt
    tage = max(0, int(tage))
    entfernt: dict[str, str] = {}
    offen = 0
    for wurzel in _wurzeln():
        korb = wurzel / PAPIERKORB
        if not korb.is_dir():
            continue
        # Ein Verzeichnis ohne Marker (von Hand hineingelegt, abgebrochener
        # Lauf) bekommt einen; seine Frist beginnt jetzt.
        for e in korb.iterdir():
            if e.is_dir() and not e.is_symlink() and not _marker(korb, e.name).exists():
                try:
                    _kennung(e.name)
                except ValueError:
                    continue
                _marker(korb, e.name).write_text(json.dumps({"am": int(jetzt), "name": ""}))
        for marker in sorted(korb.glob("*.json")):
            try:
                kennung = _kennung(marker.stem)
                angaben = json.loads(marker.read_text() or "{}")
                am = float(angaben.get("am") or 0)
            except (ValueError, OSError):
                continue
            if jetzt - am < tage * TAG:
                offen += 1
                continue
            if _weg(korb, kennung):
                entfernt.setdefault(kennung, str(angaben.get("name") or ""))
            else:
                offen += 1
    return {"entfernt": [{"kennung": k, "name": n} for k, n in entfernt.items()],
            "offen": offen}


def inhalt() -> list[dict]:
    """Was im Papierkorb liegt, je Konto: Name und seit wann."""
    konten: dict[str, dict] = {}
    for wurzel in _wurzeln():
        korb = wurzel / PAPIERKORB
        if not korb.is_dir():
            continue
        for marker in korb.glob("*.json"):
            try:
                kennung = _kennung(marker.stem)
                angaben = json.loads(marker.read_text() or "{}")
            except (ValueError, OSError):
                continue
            k = konten.setdefault(kennung, {"kennung": kennung, "name": "", "am": 0})
            k["name"] = k["name"] or str(angaben.get("name") or "")
            k["am"] = max(k["am"], int(angaben.get("am") or 0))
    return sorted(konten.values(), key=lambda k: k["am"])


# --------------------------------------------------------------------------
# Für die Auskunft nach Art. 15 (api/ota/auskunft.py)
# --------------------------------------------------------------------------

GRENZE_EINTRAEGE = 200_000


def verzeichnis(kennung: str) -> dict:
    """Was im Zuhause und in der eigenen Ablage eines Kontos liegt: Pfad,
    Größe, Änderungszeit. **Kein Inhalt.** Symbolische Verweise werden als
    solche gelistet und nicht verfolgt — sonst führte einer aus dem Zuhause
    hinaus. Bei mehr als GRENZE_EINTRAEGE Einträgen gekürzt."""
    kennung = _kennung(kennung)
    eintraege: list[dict] = []
    gekuerzt = False
    for bereich, wurzel in zip(("zuhause", "ablage"), _wurzeln()):
        basis = wurzel / kennung
        if not basis.is_dir() or basis.is_symlink():
            continue
        for ordner, unter, dateien in os.walk(basis, followlinks=False):
            unter.sort()
            for name in sorted(dateien) + [u for u in unter if os.path.islink(os.path.join(ordner, u))]:
                pfad = os.path.join(ordner, name)
                try:
                    st = os.lstat(pfad)
                except OSError:
                    continue
                eintraege.append({
                    "bereich": bereich,
                    "pfad": os.path.relpath(pfad, basis),
                    "groesse": st.st_size,
                    "geaendert": int(st.st_mtime),
                    "verweis": os.path.islink(pfad),
                })
                if len(eintraege) >= GRENZE_EINTRAEGE:
                    gekuerzt = True
                    break
            if gekuerzt:
                break
        if gekuerzt:
            break
    return {"eintraege": eintraege, "gekuerzt": gekuerzt}
