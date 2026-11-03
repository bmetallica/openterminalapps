# 40 · Where the data lives: databases on SSD, user data on HDD ✅

*For administrators. Since 2026-11-02.*

OTA has two kinds of data, and they want different disks:

| Kind | What | Needs |
|---|---|---|
| **Many small, synchronous writes** | Postgres of OTA and Keycloak, registry, OTA-Git, database of the memory extension, Docker data of root workspaces | SSD |
| **Lots of space** | Homes, user and group drives, shared storage, backups (`OTA_PROFILES_ROOT`, `OTA_USERFILES_ROOT` …) | big disk |

Without configuration the first kind lives in Docker volumes, i.e. in the host's Docker directory.
If that is on a slow disk, every start, every image and every login waits for it.
`scripts/docker-diagnose.sh` shows this as too few synchronous writes per second
([chapter 12](12-fehlersuche.md)).

## The settings

In `deploy/.env`, one directory per part. Empty means: Docker volume, as before.

| Variable | Part |
|---|---|
| `OTA_DB_DIR` | Postgres of OTA and Keycloak |
| `OTA_REGISTRY_DIR` | Registry of the workspace images |
| `OTA_GIT_DIR` | OTA-Git (Forgejo) |
| `OTA_PLATZ_DOCKER_ROOT` | Docker data of root workspaces, one subdirectory per workspace |
| `GEDAECHTNIS_DB_DIR` | in the extension's `.env`: its database |

**Do not change these by hand.** A new path on its own is an empty directory, and the service
would start without its data. The script moves the data and fills them in.

Each part can go to its own place, e.g. the database to one SSD and the Docker data of root
workspaces to another.

## Preparing the SSD

In a VM: create a new virtual disk on the SSD storage. Under Proxmox with cache "Write back" (not
"unsafe"), Discard, SSD emulation and IO thread; **Backup** on, otherwise the database is missing
from Proxmox backups. In the VM:

```
lsblk                                   # find the new disk, e.g. sdc
mkfs.ext4 -L ota-ssd /dev/sdc
mkdir -p /ssd
echo 'LABEL=ota-ssd /ssd ext4 defaults,noatime 0 2' >> /etc/fstab
mount /ssd
```

ext4 or xfs, **not btrfs**: btrfs is much slower with many `fsync` calls. The script points it out.

## Moving

```
sudo scripts/daten-umziehen.sh --status                         # where is what?
sudo scripts/daten-umziehen.sh --alle /ssd/ota                  # everything to /ssd/ota/<part>
sudo scripts/daten-umziehen.sh --db /ssd/ota/db --platz-docker /ssd2/platz-docker
```

Per part:

1. **Copy while running** with `rsync`. This takes as long as the disk needs, but disturbs nobody.
   Messages `file has vanished` are normal here: services and workspaces keep deleting temporary
   files, logs and WAL files. The last sync fetches whatever is missing because of that.
2. **Switch.** The service stops, a last sync transfers only the changes (seconds). Then the script
   writes the location into `.env`, recreates the service and waits until it is healthy. If it does
   not become healthy, it switches back to the old location.
3. **The old copy stays** until `--aufraeumen` deletes it.

While the database switches, OTA shows the update banner. The UI waits briefly and logs nobody out.
Running workspaces stay connected.

`--nur-kopieren` does only step 1. It can run any number of times; afterwards switching is faster.
The last sync always counts from the start of the first pre-copy.
`--ja` does not ask.

### Running root workspaces

**The script never stops a running workspace.** It only pre-copies its Docker data and sets
`OTA_PLATZ_DOCKER_ROOT`. The switch happens at the **next resume**: before the agent starts the
container it syncs what changed since the pre-copy and switches over. That usually takes seconds.
If it fails, the workspace starts from the old location and the agent's log says why. Stopped
workspaces are switched by the script right away.

From then on the agent creates new root workspaces directly under `OTA_PLATZ_DOCKER_ROOT`.

### Back

```
sudo scripts/daten-umziehen.sh --db volume                      # back into the Docker volume
```

The same procedure in the other direction; changes since the move come along. Docker data of root
workspaces only goes back while stopped. Workspaces that were created under
`OTA_PLATZ_DOCKER_ROOT` can only move to another path, not back into a volume.

### Cleaning up

```
sudo scripts/daten-umziehen.sh --aufraeumen
```

Asks for every old copy whether it should go: old volumes, old directories and the old data of
moved root workspaces (`….vor-umzug`). Only then is the space on the old disk free.

## How it is built

- **Services from Compose** (database, registry, memory): the mount reads
  `${OTA_DB_DIR:-db-data}:/var/lib/postgresql/data`. With a path it is a bind mount, without one the
  volume.
- **OTA-Git** is created by the agent. It notices from the container that `/data` no longer comes
  from the desired place and replaces it ([chapter 27](27-git.md)).
- **Docker data of root workspaces**: the volume `ota-platz-docker-<session>` keeps its name. New
  volumes bind `<OTA_PLATZ_DOCKER_ROOT>/<name>` (`type=none,o=bind`). For moved ones the old data
  directory points there via a symlink: Docker does not allow changing a volume's options while a
  container uses it, and a root workspace keeps its container. `docker system df` does not know the
  size of such volumes; the agent measures it with `du` and deletes them with their data when the
  workspace is deleted.
- **The last sync** additionally re-copies every file whose ctime is newer than the start of the
  pre-copy. Otherwise `rsync` only compares size and time to the second. Postgres, however,
  overwrites WAL files of the same size several times per second; a database copied that way does
  not start ("invalid checkpoint record").
- `rsync -aHAXS --numeric-ids` keeps owners, hard links, ACLs and extended attributes. Docker needs
  that for its overlay layers (whiteouts, `trusted.overlay.*`).
