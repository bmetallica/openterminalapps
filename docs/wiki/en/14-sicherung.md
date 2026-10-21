# 14 · Backup and restore

*For administrators.* ✅ Menu item **Operations → Backup**

## What is backed up

| Kind | Contents | Default |
|---|---|---|
| **Profiles** | Every user's home without caches: projects, settings, SSH keys, Git configuration | **on** |
| **Container** | Only what was changed outside the home, determined via `docker diff` | off |
| **Database** | Users, groups, workspaces, assignments, audit log | **on** |
| **Content** | Skeleton profiles, shared shelf, the users' own shelves, the group drives | **on** (only `make backup`) |
| **Git** | The database of [OTA Git](27-git.md) and all repositories, under `/srv/ota/backups/git/` | **on** once OTA Git has been set up; runs with the database |

**The network is included, without a line of its own.** Network profiles, global rules and port
forwards are in the database and travel with its dump. The router itself holds nothing it does not
get back: after a restore the API pushes the whole set over again, and the next sync restores it.
The workspaces' fixed addresses are kept that way too — they are tied to person and template, not to
the container.

**A restore brings old audit log entries back** — and the next nightly run clears them away again
by the same retention periods (90 days behaviour, 365 days administration). That is intended:
otherwise the retention period would depend on when the last restore happened.

**The archives are `0600`, their directory `0700`**, and that is not decoration: a database dump
contains password hashes and the seeds of the second factor. Until 2026-09-04 they lay there
readable for every user of the host. They are **not** encrypted — whoever takes them out of the
building encrypts them themselves.

The last row was missing until 2026-08-28, and that was a real gap: only the users' homes and the
database were backed up. Skeleton profiles, shared shelf, the own shelves and the group drives are,
however, **content created by hand** — they can be restored neither from the code nor from an
image. A restored state came back without them, and it was only noticed when they were needed.

**Why not the whole container?** Measured on the running system: a user's profile is 326 MB, their
container's writable layer 340 MB — a full export would be **4.8 GB**, and almost all of that is the
base image, which can be reproduced from the golden image anyway. Storing it again on every run and
for every user would be wasted space.

**What is excluded**: browser and editor caches, `node_modules`, `__pycache__`, sockets and lock
files. In a real profile this shrank the archive from 6,754 to 355 entries — without a single user
file missing. The 306 MB difference was a downloaded SDK cache.

**Not included: the own package repository** ([chapter 26](26-paketquellen.md#backup)). Its signing
key, the own packages and the file pool are under `OTA_REPO_ROOT` and belong in the host's backup.
The mirror itself comes back with a sync.

### Root workspaces ✅

For root workspaces ([chapter 25](25-root-arbeitsplatz.md)) the container is the state a user has
worked out. Their container layer is therefore backed up on **every** scheduled run — stopped ones
too, and even if the schedule does not back up containers otherwise. The Docker data in them
(images, volumes) is not: it lives in a volume of its own and can be rebuilt and pulled again.

## Backing up by hand

### On the command line: the complete state

```bash
make backup
```

Stores three archives under `backups/`:

```
db-2026-08-28-1549.sql.zst          database
profiles-2026-08-28-1549.tar.zst    /srv/ota/profiles
inhalte-2026-08-28-1550.tar.zst     /srv/ota/{skeletons,shared,userfiles}
```

That is the way to go before an update. The three together are a complete state; everything else —
images, containers, the application itself — can be rebuilt.

### In the interface: the profiles

*Operations → Backup → **Back up all now***. That backs up the profiles of all active users. The
progress appears in the list below.

A single user can also be backed up via the API:

```bash
curl --cacert deploy/certs/ota-ca.crt -b cookie.txt \
  -X POST https://<host>:8443/api/backups/run \
  -H 'Content-Type: application/json' \
  -d '{"username":"anna.k","include_container":true}'
```

> Backing up also works with an open session. That is intentional — whoever only backs up with
> closed sessions in practice never backs up. An editor that is writing at that moment can leave a
> file half-written in the archive; for source code and settings that is acceptable. With a closed
> session it is cleaner.

## Backing up automatically

In the **Backup** tab, flip the switch *Back up automatically*. Then:

- **Time** — the server's local time. Best when nobody is working.
- **Weekdays** — nothing selected means: every day.
- **What is backed up** — profiles and optionally the container changes.
- **Retention** — how many daily states stay, and how many additional weekly ones.

The scheduler checks every minute and **catches up on a run** if the service was just restarting at
the scheduled minute. A missed run therefore does not simply drop out.

### How retention is calculated

Per user and kind the last *n* states are kept. Of the older ones, the newest per calendar week
stays, up to the set number. With the default — 7 daily, 4 weekly — the backup reaches back about
five weeks, without the amount growing without limit.

Failed runs disappear after 30 days. They take no space, but clutter the view.

## Restoring the database

There is deliberately **no button** for this. The database holds the sign-in you are using in the
interface right now — swapping it under the running application breaks every open connection in the
middle.

When you click *Restore*, the interface shows the ready-made command. On the server:

```bash
cd /opt/openterminalapps
./scripts/restore-db.sh --list          # existing backups
./scripts/restore-db.sh                 # the newest
./scripts/restore-db.sh <path>          # a specific one
```

The script proceeds in five steps and says at each what it is doing:

1. Create a **safety copy** of the current state
2. **Stop API and agent** — database and Traefik keep running, so that an understandable page is
   still delivered
3. **End open connections**
4. **Import**. If it fails, it aborts, shows the last log lines and names the command for the way
   back
5. **Start services** and check health

To confirm, the database name has to be typed — an accidental Enter is not enough.

**Afterwards everyone has to sign in again.** Profiles on disk are not affected. If a session runs
that the restored database does not know, the reaper removes its container on its next pass.

## Restoring container backups

Here it is **the other way round** than with the profile: the files are placed into the **running**
container. The user's workspace must therefore be open — if none is running, OTA refuses and says
so.

In the list, click **Restore into session** for the container backup.

> The restored files lie outside the home. Applications that are already open do not read them any
> more — close and reopen them.

## Restoring profiles

In the list, click **Restore** for the desired backup. The dialog names user and time and says what
will be lost.

**Two things happen, both deliberately:**

1. **If a session of the user is still running, it is refused.** Swapping a profile under an open
   editor leads to data loss on both sides. End the session first — in the *Sessions* tab.
2. **The previous state is not deleted.** It stays next to the profile as
   `user.vor-wiederherstellung-<timestamp>`. If the restore was not the right thing after all, it
   can be brought back:

```bash
cd /srv/ota/profiles/<user>
mv user user.verworfen
mv user.vor-wiederherstellung-<timestamp> user
chown -R 1000:1000 user
```

If unpacking fails, OTA moves the old state back by itself — nobody is left without a profile.

After unpacking, ownership is set to **UID/GID 1000**. Without that the container cannot write to
its own home.

## Putting the backups on a network drive

All backups live under **one** path — default `/srv/ota/backups`, configurable via
`OTA_BACKUP_ROOT` in `deploy/.env`.

That is exactly why moving to NFS costs OTA nothing:

```bash
# 1 · Put running backups aside
systemctl stop ... # or: cd deploy && docker compose stop api agent
mv /srv/ota/backups /srv/ota/backups.lokal

# 2 · Mount NFS
mkdir -p /srv/ota/backups
echo 'nas:/export/ota-backups /srv/ota/backups nfs4 defaults,_netdev 0 0' >> /etc/fstab
mount /srv/ota/backups

# 3 · Take over the existing backups
rsync -a /srv/ota/backups.lokal/ /srv/ota/backups/

# 4 · Carry on as before
cd deploy && docker compose up -d
```

Afterwards the interface shows **"network drive"** instead of "local disk" under *Storage* — that
is how you can check whether the mount really applies.

> **Do not forget `_netdev` in the fstab.** Without it the system tries to mount the NFS before the
> network; the mount fails, OTA then happily writes into the empty local directory underneath — and
> nobody notices until the backup is needed.

## Checking that it works

```bash
./scripts/test-backup.sh
```

The test places a marker in a real profile, backs up, restores and checks that the marker has
disappeared and the old state is kept. It also checks that a normal user neither sees the backups
nor can trigger one, and that the restore is refused with a running session.

> **A backup whose restore was never checked is not a backup.**
> That applies to the database too — its restore is not automated yet and should be played through
> by hand once.

## Two things that keep the list clean

**Accounts without a profile produce no error entry.** Whoever never had a session has no home —
that is the normal case for freshly created accounts and not an error. The run counts them
separately ("2 without profile") instead of cluttering the list with red rows.

**Stuck runs are cleaned up.** If the service restarts in the middle of a backup, the entry would
otherwise stay on *running* forever. OTA closes such runs as soon as someone opens the list — with
the note that the service restarted in between. The same applies after a database restore that
turns the state back to a time when a run was still open.

## All checked

```bash
./scripts/test-backup.sh      # 34 checks
make test                     # all suites, 102 checks
```
