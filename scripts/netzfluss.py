#!/usr/bin/env python3
"""Erzeugt die animierten Netzfluss-Diagramme — die Reise eines Pakets.

Fuenf Bilder, eines je Betriebsart der Firewall. Sie stehen in der README und
im Handbuch (Kapitel 23) und sollen eine Frage beantworten, die in Prosa
schwer zu beantworten ist: **Wo genau endet ein Paket, und warum?**

Warum erzeugt und nicht von Hand geschrieben: Die fuenf unterscheiden sich nur
in den Urteilen an den Leitungen. Von Hand waeren es fuenf Dateien, die
auseinanderlaufen, sobald jemand eine Farbe aendert.

**Animiert mit CSS, nicht mit SMIL.** Nur so laesst sich `prefers-reduced-motion`
beachten — wer Bewegung abgestellt hat, bekommt dasselbe Bild mit stehenden
Paketen, nicht ein leeres.

Aufruf:  python3 scripts/netzfluss.py
"""
from __future__ import annotations

import io
import os

ZIEL = os.environ.get("OTA_NETZFLUSS", "docs/wiki/bilder")

# Die Farben der Anwendung (web/src/styles/app.css).
GRUND, FLAECHE, HOCH = "#090D16", "#0F172A", "#1B2436"
RAND, RAND_HELL = "#1E293B", "#334155"
TEXT, LABEL, MUTE = "#F1F5F9", "#94A3B8", "#64748B"
AKZENT, HALT, WARN, LEBT = "#06B6D4", "#EF4444", "#F59E0B", "#10B981"

B, H = 860, 330
# Der Arbeitsplatz links, der Router in der Mitte, die Ziele rechts.
AP = (24, 128, 176, 74)          # x, y, w, h
RT = (352, 116, 168, 98)
ZIELE = {                         # name -> (x, y, w, h)
    "oben":  (664, 34, 172, 62),
    "mitte": (664, 134, 172, 62),
    "unten": (664, 234, 172, 62),
}
# Mitte der rechten Kante des Arbeitsplatzes und der linken/rechten des Routers.
AP_R = (AP[0] + AP[2], AP[1] + AP[3] / 2)
RT_L = (RT[0], RT[1] + RT[3] / 2)
RT_R = (RT[0] + RT[2], RT[1] + RT[3] / 2)


def _kasten(x, y, w, h, titel, unter, rahmen=RAND, fuellung=FLAECHE, dick=1.5):
    t = [f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="8" '
         f'fill="{fuellung}" stroke="{rahmen}" stroke-width="{dick}"/>',
         f'<text class="titel" x="{x + 18}" y="{y + 26}">{titel}</text>']
    for i, zeile in enumerate(unter):
        t.append(f'<text class="unter" x="{x + 18}" y="{y + 46 + i * 17}">{zeile}</text>')
    return "\n  ".join(t)


def _weg(nr: str, punkte, farbe: str, gestrichelt=False) -> str:
    """Eine Leitung. `punkte` sind (x, y)-Paare."""
    d = "M" + " L".join(f"{x} {y}" for x, y in punkte)
    strich = ' stroke-dasharray="5 4"' if gestrichelt else ""
    return (f'<path id="{nr}" d="{d}" fill="none" stroke="{farbe}" '
            f'stroke-width="2"{strich}/>')


def _paket(name: str, punkte, dauer: float, start: float, farbe: str):
    """Ein wanderndes Paket: das Rechteck und seine Keyframes.

    Die Zwischenschritte bekommen ihren Anteil an der Zeit nach Streckenlaenge
    — sonst rast es auf dem kurzen Stueck und schleicht auf dem langen.
    """
    laengen = [((punkte[i + 1][0] - punkte[i][0]) ** 2
                + (punkte[i + 1][1] - punkte[i][1]) ** 2) ** 0.5
               for i in range(len(punkte) - 1)]
    gesamt = sum(laengen) or 1
    anteil, weg = 0.0, []
    for i, (x, y) in enumerate(punkte):
        weg.append((anteil, x, y))
        if i < len(laengen):
            anteil += laengen[i] / gesamt

    schritte = "\n    ".join(
        f"{p * 100:.1f}% {{ transform: translate({x:.0f}px, {y:.0f}px); }}"
        for p, x, y in weg
    )
    rahmen = (f"@keyframes {name} {{\n    {schritte}\n  }}\n"
              f"  @keyframes {name}-blende {{\n"
              f"    0% {{ opacity: 0; }} 8% {{ opacity: 1; }}\n"
              f"    88% {{ opacity: 1; }} 100% {{ opacity: 0; }}\n  }}")

    # **Die Ruhelage steht im Attribut, nicht in einer Regel.** Wer Bewegung
    # abgestellt hat, bekommt sonst alle Pakete uebereinander in der linken
    # oberen Ecke — das Diagramm waere dann schlechter als gar keines.
    #
    # Bei einem Drittel der Strecke und nicht in der Mitte: Die Mitte liegt bei
    # einem verworfenen Paket mitten im Router, also auf dessen Beschriftung.
    ruhe = min(weg, key=lambda p: abs(p[0] - 0.33))
    rx, ry = ruhe[1], ruhe[2]
    knoten = (f'<rect class="paket" x="-7" y="-5" width="14" height="10" rx="2.5" '
              f'fill="{farbe}" transform="translate({rx:.0f} {ry:.0f})" '
              f'style="animation-name: {name}, {name}-blende; '
              f'animation-duration: {dauer}s, {dauer}s; '
              f'animation-delay: {start}s, {start}s;"/>')
    return knoten, rahmen


def _haken(x, y):
    return (f'<circle cx="{x}" cy="{y}" r="11" fill="{GRUND}" stroke="{AKZENT}" '
            f'stroke-width="1.5"/>'
            f'<path d="M{x - 5} {y} L{x - 1} {y + 4} L{x + 6} {y - 4}" fill="none" '
            f'stroke="{AKZENT}" stroke-width="2.4" stroke-linecap="round" '
            f'stroke-linejoin="round"/>')


def _kreuz(x, y):
    return (f'<circle cx="{x}" cy="{y}" r="11" fill="{GRUND}" stroke="{HALT}" '
            f'stroke-width="1.5"/>'
            f'<path d="M{x - 5} {y - 5} L{x + 5} {y + 5} M{x + 5} {y - 5} '
            f'L{x - 5} {y + 5}" stroke="{HALT}" stroke-width="2.4" '
            f'stroke-linecap="round"/>')


def bau(datei: str, titel: str, router_unter, ziele, hinweis: str) -> None:
    """`ziele`: Liste aus (platz, name, unterzeile, urteil, art).

    `art` ist eines von:
      durch     — das Paket kommt an
      gesperrt  — der Router verwirft es; wohin es gegangen waere, steht
                  gestrichelt daneben
      kein-weg  — es gibt gar keine Leitung; das Paket kommt nicht einmal
                  bis zum Router

    **Die Reihenfolge im Bild ist nicht beliebig**: erst die Leitungen, dann
    die Kaesten, dann die Urteile, zuletzt die Pakete. Andersherum laufen die
    Leitungen ueber die Beschriftung der Kaesten — das war der erste Entwurf.
    """
    leitungen, kaesten, urteile, pakete, keyframes = [], [], [], [], []

    kaesten.append(_kasten(*AP, "Arbeitsplatz", ["10.99.7.10"], rahmen=RAND_HELL,
                           fuellung=HOCH))
    kaesten.append(_kasten(*RT, "ota-firewall", router_unter, rahmen=AKZENT,
                           fuellung=HOCH, dick=2))

    GASSE = 596            # wo die Leitungen nach oben und unten abbiegen
    ENTSCHEID = 470        # wo im Router das Urteil faellt
    for i, (platz, name, unter, urteil, art) in enumerate(ziele):
        zx, zy, zw, zh = ZIELE[platz]
        kaesten.append(_kasten(zx, zy, zw, zh, name, [unter]))
        ziel_y = zy + zh / 2
        # Drei Spuren durch den Router, damit sich die Urteile nicht
        # uebereinanderlegen — und damit sichtbar wird, dass er entscheidet.
        spur = RT_L[1] + (ziel_y - RT_L[1]) * 0.34

        if art == "kein-weg":
            # Auch dieser Stummel zeigt in Richtung seines Ziels, sonst liegen
            # bei mehreren Zeilen alle Kreuze aufeinander.
            ziel_x = AP_R[0] + 66
            stumpf_y = AP_R[1] + (ziel_y - AP_R[1]) * 0.22
            strecke = [AP_R, (ziel_x, stumpf_y)]
            leitungen.append(_weg(f"w{i}", strecke, RAND, gestrichelt=True))
            urteile.append(_kreuz(ziel_x + 16, stumpf_y))
            urteile.append(f'<text class="urteil" x="{ziel_x + 32}" '
                           f'y="{stumpf_y + 4}" fill="{HALT}">{urteil}</text>')
        else:
            # Das Urteil faellt im Router — gezeigt wird es an seiner
            # **Austrittskante**. Mitten im Kasten laege es sonst auf dessen
            # eigener Beschriftung, und die mittlere Zeile trifft ihn genau.
            hin = [AP_R, RT_L, (ENTSCHEID, spur)]
            raus = [(RT_R[0], spur), (GASSE, spur), (GASSE, ziel_y), (zx - 22, ziel_y)]
            if art == "durch":
                strecke = hin + raus
                leitungen.append(_weg(f"w{i}", strecke, AKZENT))
                urteile.append(_haken(zx - 22, ziel_y))
                urteile.append(f'<text class="urteil" x="{zx - 40}" '
                               f'y="{ziel_y - 13}" text-anchor="end" '
                               f'fill="{AKZENT}">{urteil}</text>')
            else:
                strecke = hin + [(RT_R[0] + 16, spur)]
                leitungen.append(_weg(f"w{i}", strecke, AKZENT))
                leitungen.append(_weg(f"wg{i}", raus, RAND, gestrichelt=True))
                urteile.append(_kreuz(RT_R[0] + 16, spur))
                urteile.append(f'<text class="urteil" x="{RT_R[0] + 33}" '
                               f'y="{spur + 4}" fill="{HALT}">{urteil}</text>')

        farbe = AKZENT if art == "durch" else HALT
        knoten, rahmen = _paket(f"p{i}", strecke, 4.2, i * 0.8, farbe)
        pakete.append(knoten)
        keyframes.append(rahmen)

    svg = f"""<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {B} {H}" width="{B}" height="{H}" role="img" aria-label="{titel}. {hinweis}">
  <title>{titel}</title>
  <desc>{hinweis}</desc>
  <style>
    .titel {{ fill: {TEXT}; font: 600 14px system-ui, -apple-system, sans-serif; }}
    .unter {{ fill: {LABEL}; font: 400 11px ui-monospace, monospace; }}
    .urteil {{ font: 600 11.5px system-ui, sans-serif; }}
    .kopf {{ fill: {TEXT}; font: 600 15px system-ui, sans-serif; }}
    .fuss {{ fill: {MUTE}; font: 400 11.5px system-ui, sans-serif; }}
    /* `backwards`: Waehrend der Verzoegerung gilt schon der erste Keyframe —
       ohne das stuende ein Paket sichtbar an seiner Ruhelage und spraenge
       dann an den Anfang. */
    .paket {{ animation-timing-function: linear; animation-iteration-count: infinite;
             animation-fill-mode: backwards; }}
    @media (prefers-reduced-motion: reduce) {{
      .paket {{ animation: none !important; opacity: 1; }}
    }}
  {chr(10).join('  ' + k for k in keyframes)}
  </style>
  <rect width="{B}" height="{H}" fill="{GRUND}"/>
  <text class="kopf" x="24" y="30">{titel}</text>
  <text class="fuss" x="24" y="{H - 12}">{hinweis}</text>
  {chr(10).join('  ' + t for t in leitungen)}
  {chr(10).join('  ' + t for t in kaesten)}
  {chr(10).join('  ' + t for t in urteile)}
  {chr(10).join('  ' + p for p in pakete)}
</svg>
"""
    os.makedirs(ZIEL, exist_ok=True)
    pfad = os.path.join(ZIEL, datei)
    io.open(pfad, "w", encoding="utf-8").write(svg)
    print(f"  {pfad}")


print(f"Netzfluss-Diagramme nach {ZIEL}")

bau("netzfluss-internet.svg",
    "Stufe „Internet“ — die Vorgabe",
    ["Stufe: internet", "NAT auf die Wirtsadresse"],
    [("oben",  "Das Internet",   "z. B. 93.184.x.x",  "erlaubt", "durch"),
     ("mitte", "Das Firmennetz", "192.168.66.0/24", "verworfen", "gesperrt"),
     ("unten", "Nachbar-Arbeitsplatz", "10.99.3.10", "kein Weg", "kein-weg")],
    "Öffentliche Ziele gehen durch, alles Private ist zu — zum Nachbarn führt keine Leitung.")

bau("netzfluss-abgeschottet.svg",
    "Stufe „Abgeschottet“",
    ["Stufe: abgeschottet", "nur der Grundregelsatz"],
    [("oben",  "TURN, OTA, DNS", "der Grundregelsatz", "erlaubt", "durch"),
     ("mitte", "Das Internet",   "z. B. 93.184.x.x", "verworfen", "gesperrt"),
     ("unten", "Das Firmennetz", "192.168.66.0/24", "verworfen", "gesperrt")],
    "Nur was OTA für sich selbst braucht — sonst käme nicht einmal ein Bild an.")

bau("netzfluss-aus.svg",
    "Stufe „Aus“ — alles durch",
    ["Stufe: aus", "keine Filterung"],
    [("oben",  "Das Internet",   "z. B. 93.184.x.x", "erlaubt", "durch"),
     ("mitte", "Das Firmennetz", "192.168.66.0/24", "erlaubt", "durch"),
     ("unten", "Nachbar-Arbeitsplatz", "10.99.3.10", "kein Weg", "kein-weg")],
    "Der Router filtert nicht mehr — aber er bleibt der Weg. Auch hier kein Nachbar.")

bau("netzfluss-freigabe.svg",
    "Eine Freigabe nach Namen",
    ["Namensdienst + Regelwerk", "die Antwort füllt die Menge"],
    [("oben",  "git.firma.de",  "freigegeben",  "erlaubt", "durch"),
     ("mitte", "Der Namensdienst", "der Router selbst", "beantwortet", "durch"),
     ("unten", "wiki.firma.de", "nicht freigegeben", "verworfen", "gesperrt")],
    "Der Router beantwortet den Namen und trägt seine eigene Antwort ins Regelwerk ein.")

bau("netzfluss-nat.svg",
    "Eine Portfreigabe („+ NAT“)",
    ["Weiterleitung 30003", "→ 10.99.7.10:8080"],
    [("oben",  "Der Wirt, Port 30003", "von aussen erreichbar", "hinein", "durch"),
     ("mitte", "Ein anderer Port",     "nicht freigegeben", "verworfen", "gesperrt"),
     ("unten", "Nachbar-Arbeitsplatz", "10.99.3.10", "kein Weg", "kein-weg")],
    "Die Gegenrichtung: herein nur über einen freigegebenen Port, und nur solange die Frist läuft.")

print("fertig")
