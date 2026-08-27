"""Baut Golden Images (plan.md §8).

Gebaut wird ueber ``docker buildx build --load``, nicht ueber den klassischen
Build-Endpunkt des Python-SDK. Grund: Auf einem Host mit containerd-Image-Store
legt der klassische Builder bei Multi-Plattform-Basisimages — und das sind die
Kasm-Images — kein benutzbares Image im Store ab. Der Build meldet Erfolg, das
Image ist unmittelbar danach abfragbar und kurz darauf verschwunden. Ein
Fehlerbild, das viel Zeit kostet, wenn man es nicht kennt.

Builds laufen serialisiert — nur einer gleichzeitig. Auf einer Maschine, die
nebenher Sessions bedient, wuerde ein paralleler Build die Nutzer ausbremsen.
"""

from __future__ import annotations

import os
import shlex
import subprocess
import tempfile
import threading
import uuid
from datetime import datetime, timezone
from typing import Any

import docker

_lock = threading.Lock()
_builds: dict[str, dict[str, Any]] = {}
_MAX_LOG = 200_000
_TIMEOUT = 45 * 60


def render_dockerfile(base_image: str, apt_packages: list[str],
                      vscode_extensions: list[str], setup_script: str) -> str:
    """Erzeugt das Dockerfile aus den Angaben der Oberflaeche.

    Alle Eingaben werden mit shlex.quote entschaerft, bevor sie in eine
    Shell-Zeile wandern. Das Setup-Skript ist bewusst frei — es wird als Datei
    hineingelegt und ausgefuehrt, nicht in eine Kommandozeile eingebettet.
    """
    lines = [
        f"FROM {base_image}",
        "",
        "# Der Bau laeuft als root; die Session laeuft spaeter wieder als 1000.",
        "USER root",
        "",
    ]

    if apt_packages:
        pkgs = " ".join(shlex.quote(p) for p in apt_packages)
        lines += [
            "RUN apt-get update \\",
            f" && DEBIAN_FRONTEND=noninteractive apt-get install -y "
            f"--no-install-recommends {pkgs} \\",
            " && apt-get clean && rm -rf /var/lib/apt/lists/*",
            "",
        ]

    if vscode_extensions:
        # Extensions gehoeren in den Build, nicht in den Start: Sonst wartet
        # jeder Nutzer bei jedem Start auf Downloads, und ein Ausfall des
        # Marketplace legt den Arbeitsplatz lahm.
        lines.append("# Extensions werden beim Build installiert, nicht beim Start.")
        for ext in vscode_extensions:
            safe = shlex.quote(ext)
            lines.append(
                f"RUN su kasm-user -c 'code --no-sandbox --force "
                f"--install-extension {safe}' || echo 'Extension {safe} uebersprungen'"
            )
        lines.append("")

    if setup_script.strip():
        lines += [
            "COPY ota-setup.sh /tmp/ota-setup.sh",
            "RUN chmod +x /tmp/ota-setup.sh && /tmp/ota-setup.sh && rm -f /tmp/ota-setup.sh",
            "",
        ]

    lines += ["USER 1000", ""]
    return "\n".join(lines)


def _append(state: dict[str, Any], text: str) -> None:
    state["log"] = (state["log"] + text)[-_MAX_LOG:]


def _run_build(build_id: str, tag: str, dockerfile: str, setup_script: str) -> None:
    state = _builds[build_id]

    with _lock:
        state["status"] = "building"
        try:
            with tempfile.TemporaryDirectory(prefix="ota-build-") as ctx:
                with open(os.path.join(ctx, "Dockerfile"), "w") as fh:
                    fh.write(dockerfile)
                with open(os.path.join(ctx, "ota-setup.sh"), "w") as fh:
                    fh.write(setup_script or "#!/bin/sh\ntrue\n")

                proc = subprocess.Popen(
                    ["docker", "buildx", "build",
                     "--load",                 # ins Image-Store uebernehmen
                     "--progress", "plain",    # zeilenweise statt Fortschrittsbalken
                     "--pull=false",
                     "-t", tag, "."],
                    cwd=ctx,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.STDOUT,
                    text=True,
                    bufsize=1,
                )
                assert proc.stdout is not None
                for line in proc.stdout:
                    _append(state, line)

                code = proc.wait(timeout=_TIMEOUT)

            if code != 0:
                state["status"] = "failed"
                _append(state, f"\nBuild abgebrochen mit Rückgabewert {code}.\n")
                return

            # Erst wenn das Image wirklich im Store liegt, gilt der Build als
            # erfolgreich. Genau daran scheiterte der klassische Weg lautlos.
            client = docker.from_env()
            image = client.images.get(tag)
            state["status"] = "ok"
            state["image_ref"] = tag
            state["size_bytes"] = image.attrs.get("Size", 0)
            state["digest"] = (image.id or "")[:71]
            _append(state, f"\nImage im Store: {tag} ({state['size_bytes'] / 1024**3:.2f} GB)\n")

        except subprocess.TimeoutExpired:
            state["status"] = "failed"
            _append(state, f"\nAbbruch: Der Build lief länger als {_TIMEOUT // 60} Minuten.\n")
        except docker.errors.ImageNotFound:
            state["status"] = "failed"
            _append(state, "\nFEHLER: Der Build meldete Erfolg, aber das Image liegt "
                           "nicht im Image-Store.\n")
        except Exception as exc:  # noqa: BLE001
            state["status"] = "failed"
            _append(state, f"\nUnerwarteter Fehler: {exc}\n")
        finally:
            state["finished_at"] = datetime.now(timezone.utc).isoformat()


def start(tag: str, base_image: str, apt_packages: list[str],
          vscode_extensions: list[str], setup_script: str) -> dict[str, Any]:
    dockerfile = render_dockerfile(base_image, apt_packages, vscode_extensions, setup_script)
    build_id = uuid.uuid4().hex

    _builds[build_id] = {
        "id": build_id,
        "status": "queued",
        "log": f"Dockerfile:\n{'-' * 62}\n{dockerfile}{'-' * 62}\n\n",
        "image_ref": None,
        "size_bytes": 0,
        "digest": None,
        "finished_at": None,
        "dockerfile": dockerfile,
    }

    threading.Thread(
        target=_run_build, args=(build_id, tag, dockerfile, setup_script), daemon=True,
    ).start()
    return {"build_id": build_id, "dockerfile": dockerfile}


def status(build_id: str) -> dict[str, Any] | None:
    state = _builds.get(build_id)
    if state is None:
        return None
    return {k: v for k, v in state.items() if k != "dockerfile"}


def busy() -> bool:
    return _lock.locked()
