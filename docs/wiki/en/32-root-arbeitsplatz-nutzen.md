# 32 · Working with a root workspace

*For users.* A root workspace is a small Linux computer of your own: you may use `sudo`, install
packages and use Docker in it, and what you install stays. The administrators enable it per
workspace. The tile carries the label **root**.

## What differs from a standard workspace

| | Standard | Root |
|---|---|---|
| `sudo`, `apt install` | no | yes |
| Docker, `docker compose` | no | yes, without `sudo` |
| Things installed outside the home | gone when the container ends | stay until you rebuild |
| Ending | container gone, home stays | **stop**, everything stays |
| Space limit | for the home | additionally for the workspace itself |

Root in the workspace does not mean root on the server: the workspace runs isolated in a user space
of its own.

## Stopping and resuming ✅

- The **square** on the tile stops the workspace. Afterwards it shows as "stopped" on the start
  page.
- **Resume** starts exactly this workspace again, with all packages, settings and Docker images.
  Both take just a few seconds; a progress bar shows how far it has got.
- When **idle**, a root workspace is only ever stopped, never deleted.
- If the desktop in it crashes, it shows as stopped afterwards and can be resumed.

## Rebuilding ✅

For a broken state, or when you want the newest image. **Your home always stays.**

| Variant | What stays |
|---|---|
| **Rebuild, keep Docker images** | home, and the Docker images, containers and volumes in it |
| **Rebuild and delete Docker data** | only the home |

Everything you installed with `apt` or changed under `/etc`, `/opt` etc. is gone afterwards. A new
base image gets into your workspace **only** this way.

## Docker ✅

`docker`, `docker compose` and `docker buildx` work without `sudo`. A published port, such as
`ports: ["8080:80"]`, is reachable in the browser **inside the workspace** at
`http://localhost:8080`. From your own computer that only works through a time-limited port
forwarding set up by the administrators.

After resuming, the desktop is there before Docker is ready: Docker is still starting your
containers with `restart: always`. A `docker ps` in the first few seconds therefore waits briefly.

## Space

Images grow fast. If your workspace exceeds its limit, it no longer starts, and you get the message
"This root workspace uses … GB, … GB are allowed". Then this helps:

```bash
docker system prune        # unused images, containers, networks
docker system df           # what uses how much
```

If it does not start at all any more, rebuild it and delete the Docker data too. Or ask the
administrators to raise the limit. They can also start it despite the limit so you can tidy up
inside.

## Several root workspaces at once

If two workspaces share the same home, only one runs at a time. If the administrators have set the
workspace's persistence to **Shared data**, they run side by side and share your data folders
([chapter 31](31-dateien.md#several-workspaces-one-home)).

## What the administrators do

- **Run-once scripts:** the administrators can deposit scripts that run once at the next start or
  resume, for example to install a certificate. What a script printed is in
  `/tmp/ota-einmal-<number>.log`.
- **Web terminal:** administrators can open a root shell in your running workspace. Every input in
  it is logged.
- **Stop, start, delete** under Operations. Deleting removes the workspace including Docker data;
  your home stays.

## Git and Selkies in the workspace

OTA sets up Git at every start and resume ([chapter 33](33-entwickeln.md)). If `git` is missing in
an older workspace, install it once with `sudo apt install git`. OTA raises the picture
transmission (Selkies) to the newest version by itself when resuming.
