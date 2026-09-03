"""Eine laufende Session zu einem Golden Image einfrieren (plan.md §8).

Der Weg dahin ist der Alltag: Ein Administrator meldet sich an seinem
Arbeitsplatz an, installiert mit ``sudo apt install`` etwas nach, probiert es
aus — und will danach, dass es alle bekommen. Das von Hand in ein Rezept zu
uebersetzen ist Arbeit, die niemand gern macht und bei der Schritte verloren
gehen.

**Was eingefangen wird und was nicht.** ``docker commit`` nimmt das
Dateisystem des Containers, aber **keine Bind-Mounts**. Das Zuhause des
Nutzers liegt genau dort — es ist ein Bind-Mount aus ``/srv/ota/profiles``.
Eingefangen wird also, was ausserhalb des Home passiert ist: nachinstallierte
Pakete, Aenderungen in ``/etc``, Dateien in ``/opt``.

Das ist die richtige Grenze, und zwar nicht zufaellig: Das Zuhause gehoert
einem Menschen und enthaelt seine Schluessel. Es in ein Image zu legen, das
alle bekommen, waere ein Datenleck mit Ansage.

**Trotzdem wird gewarnt.** Auch ausserhalb des Home landen Geheimnisse:
``/etc/ssh``, eine ``.netrc`` unter ``/root``, ein Kerberos-Ticket in
``/tmp``. Vor dem Einfrieren zeigt OTA deshalb, was sich geaendert hat, und
markiert die Pfade, die nach einem Geheimnis aussehen. Entschieden wird von
einem Menschen — aber er entscheidet mit offenen Augen.
"""

from __future__ import annotations

import re
import subprocess
from typing import Any

# Pfade, die nach einem Geheimnis aussehen. Bewusst grosszuegig: Ein Fehlalarm
# kostet einen Blick, ein uebersehener Schluessel kostet mehr.
SECRET_HINTS = (
    re.compile(r"/\.ssh/(?!known_hosts$|config$)"),
    re.compile(r"/\.ssh/id_"),
    re.compile(r"/\.gnupg/"),
    re.compile(r"/\.aws/"),
    re.compile(r"/\.docker/config\.json$"),
    re.compile(r"/\.netrc$"),
    re.compile(r"/\.git-credentials$"),
    re.compile(r"/etc/ssh/ssh_host_"),
    re.compile(r"/etc/shadow$"),
    re.compile(r"krb5cc_"),
    re.compile(r"\.keytab$"),
    re.compile(r"\.smbcredentials$"),
    re.compile(r"\.pem$|\.key$|\.p12$|\.pfx$"),
    re.compile(r"(?i)token|secret|passwo?rd"),
)

# Was sich in jedem Container aendert und niemanden interessiert. Ohne diese
# Liste besteht die Vorschau zu neun Zehnteln aus Rauschen, und dann liest sie
# niemand — womit die Warnung davor auch niemand liest.
NOISE = (
    "/tmp", "/var/tmp", "/run", "/var/run", "/proc", "/sys", "/dev",
    "/var/log", "/var/cache", "/var/lib/apt/lists",
    "/home",            # Bind-Mount; wird ohnehin nicht eingefangen
    "/mnt/ota",         # Einhaengepunkt der gemeinsamen Ablage, ebenso
    "/mnt/austausch",   # und der der eigenen
    "/dockerstartup",
)

# Was vor dem Einfrieren aus dem Container **entfernt** wird.
#
# `/etc/sudoers.d/ota-admin` ist der wichtigste Eintrag und der Grund, warum
# es diese Liste ueberhaupt gibt: OTA legt diese Datei in den Container eines
# Administrators, damit er darin `sudo` benutzen kann. Friert man einen
# solchen Container ein, ohne sie zu entfernen, bekaeme **jeder** Nutzer des
# neuen Images passwortloses root — aus einer Ausnahme fuer eine Person waere
# stillschweigend die Voreinstellung fuer alle geworden.
#
# Sie fehlt danach nicht: Fuer jede Session eines Administrators wird sie neu
# geschrieben.
STRIP = (
    "/etc/sudoers.d/ota-admin",
)


def _noise(path: str) -> bool:
    return any(path == n or path.startswith(n + "/") for n in NOISE)


def is_secret(path: str) -> bool:
    return any(p.search(path) for p in SECRET_HINTS)


def _zustand(container_id: str) -> str:
    """Laeuft, pausiert, gestoppt? `docker commit` braucht die Antwort."""
    try:
        out = subprocess.run(
            ["docker", "inspect", "-f", "{{.State.Status}}", container_id],
            capture_output=True, text=True, timeout=30,
        )
    except (subprocess.SubprocessError, OSError):
        return ""
    return (out.stdout or "").strip()


def _aufwecken(container_id: str) -> bool:
    """Hebt eine Pause auf. Gibt zurueck, ob etwas zu tun war.

    **Ohne das haengt `docker commit` unbegrenzt.** Der Grund: Es haelt den
    Container fuer die Dauer der Aufnahme selbst an, und ein bereits
    angehaltener Container laesst sich nicht ein zweites Mal anhalten — der
    Aufruf wartet dann auf etwas, das nie passiert. Kein Fehler, keine
    Meldung, nur Stillstand.

    Passiert im Alltag ohne Zutun: Der Leerlauf-Aufraeumer pausiert eine
    Session, die eine Weile unbenutzt war. Wer danach einfriert, trifft genau
    diesen Fall.
    """
    if _zustand(container_id) != "paused":
        return False
    subprocess.run(
        ["docker", "unpause", container_id], capture_output=True, timeout=60,
    )
    return True


def preview(container_id: str, limit: int = 400) -> dict[str, Any]:
    """Was ein Einfrieren dieses Containers mitnehmen wuerde.

    ``docker diff`` nennt jede Aenderung gegenueber dem Basisimage mit einem
    Kennbuchstaben: ``A`` neu, ``C`` geaendert, ``D`` geloescht.
    """
    try:
        out = subprocess.run(
            ["docker", "diff", container_id],
            capture_output=True, text=True, timeout=120,
        )
    except (subprocess.SubprocessError, OSError) as exc:
        raise RuntimeError(f"Der Container liess sich nicht vergleichen: {exc}") from exc
    if out.returncode != 0:
        raise RuntimeError(out.stderr.strip() or "docker diff schlug fehl")

    aenderungen: list[dict[str, Any]] = []
    entfernt: list[str] = []
    rauschen = 0
    for zeile in (out.stdout or "").splitlines():
        if len(zeile) < 3:
            continue
        art, pfad = zeile[0], zeile[2:]
        if _noise(pfad):
            rauschen += 1
            continue
        if pfad in STRIP:
            entfernt.append(pfad)
            continue
        aenderungen.append({"art": art, "pfad": pfad, "geheimnis": is_secret(pfad)})

    geheim = [a for a in aenderungen if a["geheimnis"]]
    # Die verdaechtigen zuerst — sie sind der Grund, warum es diese Liste gibt.
    aenderungen.sort(key=lambda a: (not a["geheimnis"], a["pfad"]))

    return {
        "aenderungen": aenderungen[:limit],
        "gesamt": len(aenderungen),
        "gekuerzt": len(aenderungen) > limit,
        "uebersprungen": rauschen,
        "geheimnisse": [a["pfad"] for a in geheim][:50],
        # Wird vor dem Einfrieren entfernt. Steht hier, damit es nicht
        # aussieht, als waere es uebersehen worden.
        "entfernt": entfernt,
    }


def commit(container_id: str, tag: str, comment: str = "") -> dict[str, Any]:
    """Friert den Container als Image ein.

    Das Kasm-Label wird dabei geloescht — aus demselben Grund wie beim Bauen:
    Kasms Aufraeumdienst loescht im Modus „Aggressive" jedes Image mit
    ``com.kasmweb.image=true``, das er nicht kennt, und ein eingefrorener
    Container erbt es vom Basisimage.

    Das Startskript wird ebenfalls ueberschrieben. Ein Arbeitsplatz startet
    keine Anwendung von selbst, und ein eingefrorener Container brachte sonst
    das Skript mit, das gerade in ihm lief.
    """
    # Eine pausierte Session zuerst aufwecken — sonst haengt `docker commit`
    # ohne Meldung. Sie bleibt danach wach: Wer gerade einfriert, arbeitet an
    # diesem Container.
    geweckt = _aufwecken(container_id)

    zustand = _zustand(container_id)
    if zustand != "running":
        raise RuntimeError(
            f"Der Container ist {zustand or 'in unbekanntem Zustand'} und nicht "
            "gestartet. Starte den Arbeitsplatz, dann lässt er sich einfrieren."
        )

    # Erst raeumen, dann einfrieren, dann zuruecklegen. Die mittlere Zeile
    # ist der Punkt; die dritte ist Hoeflichkeit: Der Administrator sitzt
    # gerade in diesem Container, und ihm mitten in der Arbeit sein `sudo` zu
    # nehmen, weil er ein Image gebaut hat, waere eine Ueberraschung ohne Not.
    beiseite: dict[str, str] = {}
    for pfad in STRIP:
        gelesen = subprocess.run(
            ["docker", "exec", "-u", "0", container_id, "cat", "--", pfad],
            capture_output=True, text=True, timeout=30,
        )
        if gelesen.returncode != 0:
            continue          # gibt es nicht — nichts zu tun
        beiseite[pfad] = gelesen.stdout
        weg = subprocess.run(
            ["docker", "exec", "-u", "0", container_id, "rm", "-f", "--", pfad],
            capture_output=True, timeout=30,
        )
        if weg.returncode != 0:
            raise RuntimeError(
                f"{pfad} liess sich nicht entfernen. Ohne das bekaeme jeder "
                "Nutzer des neuen Images root — abgebrochen."
            )

    def zurueck() -> None:
        for p, inhalt in beiseite.items():
            subprocess.run(
                ["docker", "exec", "-u", "0", "-i", container_id,
                 "sh", "-c", f"cat > {p} && chmod 0440 {p}"],
                input=inhalt, text=True, capture_output=True, timeout=30,
            )

    befehl = [
        "docker", "commit",
        "--message", (comment or "Eingefroren durch OpenTerminalApps")[:200],
        "--change", 'LABEL com.kasmweb.image=""',
        "--change", 'LABEL org.opencontainers.image.title="OpenTerminalApps Golden Image"',
        "--change", "USER 1000",
        container_id, tag,
    ]
    try:
        out = subprocess.run(befehl, capture_output=True, text=True, timeout=900)
    except (subprocess.SubprocessError, OSError) as exc:
        zurueck()
        raise RuntimeError(f"Das Einfrieren schlug fehl: {exc}") from exc
    finally:
        # Auch wenn das Einfrieren scheitert: Der Container laeuft weiter, und
        # was fuer ihn galt, soll weiter gelten.
        zurueck()
    if out.returncode != 0:
        raise RuntimeError(out.stderr.strip() or "docker commit schlug fehl")

    return {
        "image_ref": tag,
        "digest": (out.stdout or "").strip(),
        "zurueckgelegt": sorted(beiseite),
        "aufgeweckt": geweckt,
    }
