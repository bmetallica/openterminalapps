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

import base64
import json
import os
import shlex
import subprocess
import tempfile
import threading
import uuid
from datetime import datetime, timezone
from typing import Any

import docker

# Adresse der eigenen Registry. Leer schaltet sie ab — dann bleiben Images
# nur im Docker-Store dieses Hosts.
REGISTRY = os.environ.get("OTA_REGISTRY", "").strip()

_lock = threading.Lock()
_builds: dict[str, dict[str, Any]] = {}
_MAX_LOG = 200_000
_TIMEOUT = 45 * 60


def render_dockerfile(base_image: str, apt_packages: list[str],
                      vscode_extensions: list[str], setup_script: str,
                      mode: str = "workspace", start_command: str = "") -> str:
    """Erzeugt das Dockerfile aus den Angaben der Oberflaeche.

    Alle Eingaben werden mit shlex.quote entschaerft, bevor sie in eine
    Shell-Zeile wandern. Das Setup-Skript ist bewusst frei — es wird als Datei
    hineingelegt und ausgefuehrt, nicht in eine Kommandozeile eingebettet.

    `mode` entscheidet ueber das Startverhalten: Ein Arbeitsplatz startet keine
    Anwendung von selbst (siehe unten). Ein Einzelanwendungs-Image bekommt mit
    `start_command` ein eigenes Startskript; ohne behaelt es das des
    Basisimages — was bei den Kasm-Anwendungsimages richtig ist und bei OTAs
    eigenem Basisimage einen leeren Schreibtisch ergaebe.
    """
    lines = [
        f"FROM {base_image}",
        "",
        "# Das Kasm-Label loeschen, das von einem Kasm-Basisimage geerbt wird.",
        "#",
        "# Gemessen am 2026-08-27: Kasms Agent raeumt im Modus \"Aggressive\" alle",
        "# 30 Sekunden auf und loescht dabei GENAU die Images, die",
        "# com.kasmweb.image=true tragen und nicht in seiner Datenbank stehen.",
        "# Ein abgeleitetes Image erbt das Label und wird deshalb als verwaiste",
        "# Kasm-Workspace-Version eingestuft — der Build meldet Erfolg, und",
        "# Sekunden spaeter ist das Image weg. Images ohne dieses Label",
        "# betrachtet Kasm gar nicht erst.",
        "#",
        "# Damit laufen OTA und Kasm auf demselben Host nebeneinander, ohne",
        "# dass an Kasm etwas umgestellt werden muss.",
        "LABEL com.kasmweb.image=\"\" \\",
        "      org.opencontainers.image.title=\"OpenTerminalApps Golden Image\"",
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
            # Der Kontoname steht nicht fest: In Kasm-Images heisst die
            # Kennung 1000 `kasm-user`, in OTAs eigenen Images `ota`. Ein
            # festgeschriebener Name liesse den Build hier scheitern, sobald
            # jemand von einem eigenen Basisimage ableitet.
            lines.append(
                f'RUN su "$(id -un 1000)" -c \'code --no-sandbox --force '
                f'--install-extension {safe}\' || echo \'Extension {safe} uebersprungen\''
            )
        lines.append("")

    if setup_script.strip():
        lines += [
            "COPY ota-setup.sh /tmp/ota-setup.sh",
            "RUN chmod +x /tmp/ota-setup.sh && /tmp/ota-setup.sh && rm -f /tmp/ota-setup.sh",
            "",
        ]

    if mode == "workspace":
        # Das Startskript des Basisimages ueberschreiben.
        #
        # Kasm-Images fuer einzelne Anwendungen bringen ein
        # `custom_startup.sh` mit, das "ihre" Anwendung startet, und
        # `vnc_startup.sh` startet dieses Skript **alle drei Sekunden neu**,
        # sobald es sich beendet.
        #
        # In einem abgeleiteten Arbeitsplatz-Image ist das verheerend.
        # Gemessen am 2026-08-27 mit einem von kasmweb/vs-code abgeleiteten
        # Image: Das geerbte Skript startete `code`, VS Code ist
        # einzelinstanzig, die zweite Instanz reichte den Aufruf weiter und
        # beendete sich — worauf die Aufsicht sie erneut startete. Nach sechs
        # Minuten: 119 leere Fenster, 2,5 GB belegt, schwarzer Bildschirm.
        #
        # Ein Arbeitsplatz startet seine Anwendungen selbst, auf Zuruf.
        lines += [
            "# Kein Selbststart einer Anwendung — der Arbeitsplatz startet sie",
            "# auf Zuruf, jede auf ihrem eigenen Display.",
            "RUN printf '%s\\n' "
            "'#!/usr/bin/env bash' "
            "'# Von OpenTerminalApps ersetzt: Im Arbeitsplatz startet keine' "
            "'# Anwendung von selbst. Das Skript darf sich nicht beenden,' "
            "'# sonst startet vnc_startup.sh es alle drei Sekunden neu.' "
            "'while true; do sleep 3600; done' "
            "> /dockerstartup/custom_startup.sh \\",
            " && chmod +x /dockerstartup/custom_startup.sh",
            "",
        ]

    elif start_command.strip():
        # Einzelanwendung mit ausdruecklichem Startbefehl.
        #
        # **Warum das noetig wurde.** Frueher stand hier nichts: Ein
        # Einzelanwendungs-Image behielt das Startskript seines Basisimages,
        # und bei den Kasm-Anwendungsimages stimmt das auch — die starten
        # "ihre" Anwendung selbst. OTAs eigenes Basisimage bringt dagegen
        # absichtlich einen Platzhalter mit, der **nichts** startet. Ein darauf
        # gebautes Einzelanwendungs-Image zeigte deshalb einen leeren
        # Schreibtisch, und der Grund stand nirgends.
        #
        # Beendet sich die Anwendung, startet das Startskript des Basisimages
        # sie nach drei Sekunden neu. Bei einer Einzelanwendung ist genau das
        # gewollt — anders als im Arbeitsplatz, wo dieselbe Aufsicht einmal
        # 119 leere Fenster erzeugt hat (siehe oben).
        skript = (
            "#!/usr/bin/env bash\n"
            "# Von OpenTerminalApps erzeugt: der Startbefehl dieses\n"
            "# Einzelanwendungs-Images. Beendet sich die Anwendung, startet\n"
            "# das Startskript des Basisimages sie neu.\n"
            f"{start_command.strip()}\n"
        )
        # Ueber base64 statt direkt: Der Befehl kommt aus einem Textfeld und
        # enthaelt Anfuehrungszeichen, Dollarzeichen und Zeilenumbrueche.
        # Alles davon wuerde beim Einbetten in eine RUN-Zeile etwas anderes
        # tun, als dort steht.
        kodiert = base64.b64encode(skript.encode("utf-8")).decode("ascii")
        lines += [
            "# Der Startbefehl dieses Einzelanwendungs-Images.",
            f"RUN printf '%s' {shlex.quote(kodiert)} | base64 -d "
            "> /dockerstartup/custom_startup.sh \\",
            " && chmod +x /dockerstartup/custom_startup.sh",
            "",
        ]

    lines += ["USER 1000", ""]
    return "\n".join(lines)


def _append(state: dict[str, Any], text: str) -> None:
    state["log"] = (state["log"] + text)[-_MAX_LOG:]


def _pause(names: list[str]) -> list[str]:
    """Haelt fremde Container fuer die Dauer des Builds an.

    Gebraucht, weil ein zweites System auf demselben Docker-Host Images
    aufraeumen kann, waehrend hier eines entsteht — Kasm tut das im Modus
    "Aggressive" alle 30 Sekunden mit allem, was es nicht kennt. Bewusst als
    Liste von Containernamen und nicht fest auf Kasm verdrahtet: Die Regel
    ist "diese Container stoeren beim Bauen", nicht "Kasm ist besonders".
    """
    client = docker.from_env()
    stopped: list[str] = []
    for name in names:
        try:
            container = client.containers.get(name)
        except docker.errors.NotFound:
            continue
        if container.status != "running":
            continue
        container.stop(timeout=20)
        stopped.append(name)
    return stopped


def _resume(names: list[str]) -> None:
    """Startet die angehaltenen Container wieder.

    Laeuft im finally-Zweig: Auch ein abgestuerzter oder abgebrochener Build
    darf fremde Dienste nicht dauerhaft ausschalten.
    """
    client = docker.from_env()
    for name in names:
        try:
            client.containers.get(name).start()
        except Exception:  # noqa: BLE001 — jeder Container fuer sich
            pass


def _run_build(build_id: str, tag: str, dockerfile: str, setup_script: str,
               pause_containers: list[str]) -> None:
    state = _builds[build_id]
    paused: list[str] = []

    with _lock:
        state["status"] = "building"
        try:
            if pause_containers:
                paused = _pause(pause_containers)
                if paused:
                    _append(state, f"Angehalten für die Dauer des Builds: "
                                   f"{', '.join(paused)}\n\n")
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
            state["image_ref"] = tag
            state["size_bytes"] = image.attrs.get("Size", 0)
            state["digest"] = (image.id or "")[:71]
            _append(state, f"\nImage im Store: {tag} ({state['size_bytes'] / 1024**3:.2f} GB)\n")

            _gallery_note(state, tag)

            # In die eigene Registry, falls es eine gibt — **vor** dem Setzen
            # von "ok". Die API hoert auf zuzusehen, sobald der Zustand nicht
            # mehr "building" ist; stuende das Hochladen danach, fehlte es im
            # Protokoll und die Adresse bliebe die lokale.
            #
            # Der Build gilt auch dann als gelungen, wenn das Ablegen
            # misslingt: Das Image liegt im Store und ist benutzbar. Ein Build,
            # der an einer nicht erreichbaren Registry scheitert, waere die
            # schlechtere Antwort.
            if REGISTRY:
                pushed = _push(state, client, tag)
                if pushed:
                    state["image_ref"] = pushed

            state["status"] = "ok"

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
            if paused:
                _resume(paused)
                _append(state, f"\nWieder gestartet: {', '.join(paused)}\n")
            state["finished_at"] = datetime.now(timezone.utc).isoformat()


# Wo die Editoren der VS-Code-Familie ihre Erweiterungen holen. Nicht kosmetisch:
# Der Marktplatz von Microsoft darf laut seinen Bedingungen nur von Microsofts
# eigenem VS Code benutzt werden. Ein VSCodium, das dorthin zeigt, waere ein
# Lizenzproblem — und es faellt niemandem auf, weil es einfach funktioniert.
_PRODUCT_JSON = (
    ("VS Code (Microsoft)", "/usr/share/code/resources/app/product.json"),
    ("VSCodium", "/usr/share/codium/resources/app/product.json"),
    ("Code - OSS", "/usr/lib/code/product.json"),
)
_MS_GALLERY = "marketplace.visualstudio.com"


def _gallery_note(state: dict[str, Any], tag: str) -> None:
    """Haelt im Protokoll fest, wohin die gebauten Editoren zeigen.

    Bricht nichts ab. Das Image ist gebaut und benutzbar; hier steht nur, was
    ein Mensch wissen muss, bevor er es verteilt.
    """
    script = "; ".join(
        f'if [ -f {path} ]; then echo "@@{name}"; cat {path}; echo; fi'
        for name, path in _PRODUCT_JSON
    )
    try:
        raw = subprocess.run(
            ["docker", "run", "--rm", "--entrypoint", "sh", tag, "-c", script],
            capture_output=True, text=True, timeout=120,
        ).stdout
    except (subprocess.SubprocessError, OSError):
        return
    if "@@" not in raw:
        return

    lines = ["\nErweiterungs-Marktplatz der gefundenen Editoren:"]
    for block in raw.split("@@")[1:]:
        name, _, body = block.partition("\n")
        name = name.strip()
        try:
            gallery = json.loads(body).get("extensionsGallery") or {}
        except json.JSONDecodeError:
            continue
        url = str(gallery.get("serviceUrl") or "—")
        lines.append(f"  {name}: {url}")
        # Nur der Microsoft-Marktplatz in einem Nicht-Microsoft-Editor ist ein
        # Befund. Der umgekehrte Fall ist der Normalzustand.
        if _MS_GALLERY in url and not name.startswith("VS Code"):
            lines.append(
                f"  ACHTUNG: {name} zeigt auf den Marktplatz von Microsoft. "
                "Dessen Bedingungen erlauben das nur Microsofts eigenem "
                "VS Code. Siehe Handbuch, Kapitel 13."
            )
    _append(state, "\n".join(lines) + "\n")


def _push(state: dict[str, Any], client: docker.DockerClient, tag: str) -> str | None:
    """Legt eine Kopie in der eigenen Registry ab.

    Zwei Gruende, und das Zurueckdrehen einer Fassung ist keiner davon — das
    kann OTA laengst ueber `image_builds`:

      1. Ein zweiter Host koennte die eigenen Golden Images sonst nicht
         bekommen. Sie existieren nirgends ausser lokal.
      2. Fremdes Aufraeumen. Kasms Agent hat auf diesem Host schon einmal
         jedes ihm unbekannte Image geloescht.

    Zurueck kommt die Adresse in der Registry — sie wird die Adresse des
    Images, damit ein spaeterer Start sie von dort holen kann.
    """
    remote = f"{REGISTRY}/{tag}"
    try:
        client.images.get(tag).tag(remote)
        _append(state, f"\nIn die Registry: {remote}\n")
        for chunk in client.images.push(remote, stream=True, decode=True):
            if "error" in chunk:
                _append(state, f"Registry meldet: {chunk['error']}\n")
                return None
        _append(state, "Abgelegt.\n")
        return remote
    except docker.errors.APIError as exc:
        _append(state, f"\nRegistry nicht erreichbar ({exc}). Das Image liegt "
                       "im Store dieses Hosts und ist benutzbar.\n")
        return None


def start(tag: str, base_image: str, apt_packages: list[str],
          vscode_extensions: list[str], setup_script: str,
          pause_containers: list[str] | None = None,
          mode: str = "workspace", start_command: str = "") -> dict[str, Any]:
    dockerfile = render_dockerfile(base_image, apt_packages, vscode_extensions,
                                   setup_script, mode, start_command)
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
        target=_run_build,
        args=(build_id, tag, dockerfile, setup_script, pause_containers or []),
        daemon=True,
    ).start()
    return {"build_id": build_id, "dockerfile": dockerfile}


def status(build_id: str) -> dict[str, Any] | None:
    state = _builds.get(build_id)
    if state is None:
        return None
    return {k: v for k, v in state.items() if k != "dockerfile"}


def busy() -> bool:
    return _lock.locked()
