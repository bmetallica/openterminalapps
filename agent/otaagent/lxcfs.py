"""LXCFS: `top`, `htop` und `free` zeigen den Arbeitsplatz, nicht den Wirt.

Werkzeuge wie `free`, `htop` oder `uptime` lesen ihre Summen aus `/proc`
(`meminfo`, `loadavg`, `cpuinfo` …) — und das gehört dem Kernel des Wirts.
Im Container sahen sie deshalb 16 GB und vier Kerne, auch wenn der
Arbeitsplatz 4 GB und zwei Kerne hat. LXCFS (ein Dienst auf dem Wirt,
`scripts/lxcfs-einrichten.sh`) stellt dieselben Dateien je Container passend
zu seiner cgroup bereit; sie werden hier über die echten gelegt.

Zwei Wege, je nach Container:

* **Neue Container** bekommen die Dateien als gewöhnliche Einhängepunkte
  (`docker_mounts`). Die überdauern jeden Neustart des Containers.
* **Bestehende Root-Arbeitsplätze** (angelegt, bevor es LXCFS gab) werden
  fortgesetzt, nicht neu angelegt — und einem bestehenden Container kann
  Docker keinen Einhängepunkt mehr geben. Ihnen hängt `einhaengen` die
  Dateien nach jedem Start in den laufenden Container: ein kurzlebiger
  Helfer (dieses Abbild, privilegiert, im PID-Namensraum des Wirts) klont
  sie im Namensraum des Wirts (`open_tree`) und setzt sie in dem des
  Containers ab (`move_mount`). Mit Sysbox geprüft am 2026-11-18.

Grenze (gemessen am 2026-11-18, LXCFS 6.0.4, cgroup v2): Speicher, Swap,
Load, Uptime und die Zahl der Kerne in `cpuinfo` stimmen. Die CPU-
**Auslastung** in `/proc/stat` bleibt die des Wirts — LXCFS kann sie unter
cgroup v2 nicht berechnen. Dafür gibt es `ota-top` im Arbeitsplatz.

Fehlt LXCFS, passiert nichts: Die Container laufen wie bisher.
"""
from __future__ import annotations

import ctypes
import logging
import os
import sys
from typing import Any

log = logging.getLogger("ota.agent.lxcfs")

WURZEL = "/var/lib/lxcfs"
DATEIEN = ("/proc/cpuinfo", "/proc/diskstats", "/proc/loadavg", "/proc/meminfo",
           "/proc/stat", "/proc/swaps", "/proc/uptime", "/sys/devices/system/cpu/online")


def abgeschaltet() -> bool:
    """`OTA_LXCFS=aus` in deploy/.env, oder — ohne Neustart — die Datei
    `lxcfs-aus` im Laufzeitordner. Gilt für neu angelegte und fortgesetzte
    Arbeitsplätze; was schon eingehängt ist, bleibt bis zum nächsten Start."""
    if os.environ.get("OTA_LXCFS", "").strip().lower() in ("aus", "0", "nein", "off"):
        return True
    return os.path.exists(os.path.join(os.environ.get("OTA_RUNTIME_ROOT", "/srv/ota/runtime"),
                                       "lxcfs-aus"))


def verfuegbar() -> bool:
    """Läuft LXCFS? Der Agent sieht `/var/lib/lxcfs` des Wirts (compose).
    Ein abgestürztes LXCFS hinterlässt einen toten Einhängepunkt: `stat`
    scheitert dann, und das zählt als „nicht da“."""
    if abgeschaltet():
        return False
    try:
        os.stat(WURZEL + "/proc/meminfo")
        return True
    except OSError:
        return False


def docker_mounts() -> list[Any]:
    if not verfuegbar():
        return []
    import docker
    return [docker.types.Mount(target=d, source=WURZEL + d, type="bind", read_only=True)
            for d in DATEIEN if os.path.exists(WURZEL + d)]


def hat_eigene(container) -> bool:
    """Hat der Container die Dateien schon als Einhängepunkte von Docker?"""
    return any((m.get("Destination") == "/proc/meminfo")
               for m in (container.attrs.get("Mounts") or []))


def einhaengen(client, container) -> str:
    """Die Dateien in einen **laufenden** Container hängen, der sie nicht von
    Docker hat. Nach jedem Start nötig: Ein neuer Start ist ein neuer
    Namensraum. Scheitert es, läuft der Arbeitsplatz trotzdem."""
    if not verfuegbar():
        return "ohne-lxcfs"
    try:
        container.reload()
        if hat_eigene(container):
            return "eigene"
        pid = int((container.attrs.get("State") or {}).get("Pid") or 0)
        if container.status != "running" or pid <= 0:
            return "laeuft-nicht"
        bild = client.containers.get(os.environ.get("HOSTNAME", "ota-agent")).image.id
        aus = client.containers.run(
            bild, entrypoint=["python3", "-m", "otaagent.lxcfs"], command=[str(pid), *DATEIEN],
            privileged=True, pid_mode="host", network_mode="none", user="0",
            remove=True, stdout=True, stderr=True, labels={"ota.helfer": "lxcfs"},
        )
        text = (aus or b"").decode("utf-8", "replace").strip()
        log.info("LXCFS in %s: %s", container.name, " ".join(text.split()))
        return text
    except Exception as exc:  # noqa: BLE001 — Anzeige, kein Grund zum Abbruch
        log.warning("LXCFS nicht in %s eingehängt: %s", container.name, exc)
        return f"fehler: {exc}"


# ------------------------------------------------- der Helfer (eigener Prozess)

_SYS_OPEN_TREE, _SYS_MOVE_MOUNT = 428, 429   # x86_64 und aarch64 gleich
_OPEN_TREE_CLONE, _OPEN_TREE_CLOEXEC = 1, 0o2000000
_MOVE_MOUNT_F_EMPTY_PATH = 0x4
_AT_FDCWD = -100
_CLONE_NEWNS = 0x00020000


def _schon_lxcfs(pid: int) -> set[str]:
    raus: set[str] = set()
    with open(f"/proc/{pid}/mountinfo", encoding="utf-8", errors="replace") as f:
        for zeile in f:
            teile = zeile.split(" - ", 1)
            felder = teile[0].split()
            if len(teile) == 2 and len(felder) > 4 and teile[1].startswith("fuse.lxcfs"):
                raus.add(felder[4])
    return raus


def _helfer(pid: int, dateien: list[str]) -> int:
    libc = ctypes.CDLL(None, use_errno=True)

    def pruefe(r: int, was: str) -> int:
        if r < 0:
            e = ctypes.get_errno()
            raise OSError(e, f"{was}: {os.strerror(e)}")
        return r

    offen = sorted(set(dateien) - _schon_lxcfs(pid))
    if not offen:
        print("schon-da")
        return 0
    wirt = os.open("/proc/1/ns/mnt", os.O_RDONLY)
    ziel = os.open(f"/proc/{pid}/ns/mnt", os.O_RDONLY)
    pruefe(libc.setns(wirt, _CLONE_NEWNS), "setns Wirt")
    baeume: dict[str, int] = {}
    for d in offen:
        quelle = WURZEL + d
        if os.path.exists(quelle):
            baeume[d] = pruefe(libc.syscall(_SYS_OPEN_TREE, _AT_FDCWD, quelle.encode(),
                                            _OPEN_TREE_CLONE | _OPEN_TREE_CLOEXEC), "open_tree " + d)
    pruefe(libc.setns(ziel, _CLONE_NEWNS), "setns Container")
    fehler = 0
    for d, fd in baeume.items():
        try:
            pruefe(libc.syscall(_SYS_MOVE_MOUNT, fd, b"", _AT_FDCWD, d.encode(),
                                _MOVE_MOUNT_F_EMPTY_PATH), "move_mount " + d)
            print("ok", d)
        except OSError as exc:
            fehler += 1
            print("fehler", exc)
    return 1 if fehler else 0


if __name__ == "__main__":
    sys.exit(_helfer(int(sys.argv[1]), sys.argv[2:]))
