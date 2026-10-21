# 17 · Shelves and start script

*For administrators.* ✅ Shared shelf, own shelf, group drives, skeleton profile, script at session
start

Ways to get things into the users' workspaces without building an image every time. They belong
together: the shared shelf is the source, the skeleton lays down the baseline, the script fetches
what it needs. The **own shelf** stands next to them and belongs not to administration but to the
user — it is their way to get files into their container and back out.

## What goes where

| | Where to | Why |
|---|---|---|
| Software | **Golden image** ([chapter 7](07-golden-images.md)) | Build once instead of installing on every start |
| Files for everyone | **Shared shelf** | Replaceable without an image build |
| A user's files, in and out | **Own shelf** | Their way into the container and out |
| A team's files | **Group drive** | The same files for all members, both directions |
| What a home starts with | **Skeleton** | Files that should simply be there — visible in the browser |
| Setup in the home | **Start script** | For everything that has to be *executed* |
| One-off change in the home | **One-time script** | For a change needed exactly once per user |
| Own settings | **None of these** | The persistent home keeps them anyway |

The last point is often overlooked: **what a user changes in their home stays.** Extensions, editor
configuration, SSH keys, project folders — that lives on the host under
`/srv/ota/profiles/<user>/` and is mounted on every start. A new golden image changes nothing about
it; the home lies *over* the image.

## The skeleton profile ✅

In the workspace editor under **Skeleton** there is a directory tree. It comes into a user's home on
the **first** start — as long as it is still empty. Afterwards the home belongs to them.

That way nobody starts with a bare desktop: editor settings, a root certificate, a template file, a
`.bashrc`. **Dot files are explicitly allowed** and the normal case — unlike in the shared shelf,
where they have no business.

### `.bashrc`, `.profile` and `.bash_logout` ✅

Even without a skeleton, every home gets the basic files from the image's `/etc/skel`, in both
classes. Until 2026-10-19 they were missing. The image does create them during the build, but the
home is the profile mounted *over* it at start, and that is empty at the beginning. Without
`.bashrc`, prompt, colours and aliases are missing, and programs that add themselves there during
setup (nvm, conda, rustup …) do not find the file.

The agent therefore adds on **every** start, and when a root workspace resumes, whatever is
**missing** from `/etc/skel`:

- An existing file stays untouched, even if the user changed it.
- The skeleton comes afterwards and has the last word.
- A **deleted** `.bashrc` is back on the next start. Whoever does not want one empties it instead of
  deleting it.

### "Enforce"

Next to every entry there is a switch *enforce*. If it is on, this path comes on **every** start and
**overwrites** what the user changed.

> **This is deliberately the exception.** A home belongs to the person working in it; overwriting
> their settings on every start must be justifiable. For a proxy configuration or a root
> certificate it is right. For a colour scheme it is not.

What is enforced is shown as a warning below the list — with the paths, so nobody has to guess.

If a file is deleted, it also disappears from the enforcement list. A path that no longer exists
would be a setting that does nothing any more, and a question at the next look.

### Skeleton or start script?

| | |
|---|---|
| **Skeleton** | Files that should simply be there |
| **Start script** | Everything that has to be *executed* — fetching, generating, querying something |

Whoever has the choice takes the skeleton: a file you see in the browser is easier to check than a
line of shell.

The order at start is skeleton → link to the shelf → start script. The script may therefore
overwrite the baseline; it is the more specific tool.

Everything lands in the home as `1000:1000` — copying happens as root, and without this step the
user would no longer own their own home.


## The three shelves ✅

They answer different questions. Whoever mixes them up puts confidential material in the wrong place
— that is why they are separate in the interface too.

| | Shared shelf | Own shelf | Group drive |
|---|---|---|---|
| Belongs to | administration | one user each | one group each |
| Who sees it in the browser | whoever manages images or workspaces | only the owner | every member |
| In the container | `/mnt/ota`, **read-only** | `/mnt/austausch`, **writable** | `/mnt/gruppen/<name>`, **writable** |
| In the home | `~/Gemeinsam` | `~/Austausch` | `~/Gruppen` |
| What for | certificates, packages, templates for everyone | files in and back out | the same files for a team |
| Can be turned off | no | yes, per workspace | yes, per workspace |

## The shared shelf ✅

**Administration → Shared files.**

A place for files that are needed in every workspace: a company certificate, an installation
package, a template file.

In every container it is in two places:

```
/mnt/ota                        the mount point
~/Gemeinsam                     a link to it, in the home
```

**For users it is read-only.** That is not a setting but the mount point itself (`read_only`) — a
write attempt fails in the file system, not at a check that could be bypassed.

The link lies in the home and not the mount point itself: a directory you cannot write to in the
middle of your own files confuses more than it helps. Whoever already has a folder of their own
called "Gemeinsam" keeps it — the link is then not created.

### Placing files

Drag and drop, or **Choose files**. Folders can be created, files downloaded and deleted. At most
2 GB per file — the shelf is meant for packages and certificates, not as a data dump.

> **No place for confidential material.** What lies here is seen by every user in every workspace.
> A private key does not belong here, a public certificate does.

Writing and **seeing** happens exclusively through this interface, and only by those who may manage
images or workspaces. Until 2026-08-28 every signed-in user could read the content, with the
argument that they saw it in their container anyway. The argument still holds — it is just not a
blueprint for the interface: two shelves side by side, one of which is only for watching, do not
explain themselves.

## The own shelf ✅

**My files** — at the very top of the menu, for everyone, including administrators.

The quick way into your own container and back out. What is placed there is in the container a
second later; what the user puts in inside the container, they find in the browser.

```
/mnt/austausch                  the mount point, writable
~/Austausch                     a link to it, in the home
```

**Everyone only sees their own.** There is no way for anyone to name someone else's — not even as
an administrator. The name never comes from the request, but from the sign-in cookie. That is
intentional and no gap: whoever has to get at someone else's files has backup and restore, a way
that is in the audit log ([chapter 14](14-sicherung.md)). A silent look into a colleague's home
should not be one.

It lies next to the home and not inside it — for two reasons: the browser and the container should
see the same place, and it should not appear a second time when the profile is backed up.

### During work too

In the control bar of a running session (handle on the right edge) there is the same shelf: drag
and drop, download, delete. Whoever needs a file in the middle of work does not have to go back to
the dashboard.

Dragging works in the **window**, not in the session's picture. That is not a lack of convenience
but the limit of the embedded stream: a drag from the operating system ends where the remote desktop
begins. The bar lies in front of it and catches it.

### Turning it off per workspace

In the workspace editor under **Resources → Own shelf**. The default is **on**. Off makes sense for
workspaces from which nothing should deliberately be carried out; then the mount point is missing
entirely, and a link from an earlier start is cleaned up on the next start.

The switch takes effect on the **next** start of the session — a running container is not
re-mounted.

## Group drives ✅

**My files** — at the top, the drives of your own groups are offered for selection. The switcher
only appears if there is one at all; a selector with a single entry is no selector.

```
/mnt/gruppen/<group name>       the mount point, writable
~/Gruppen                       a link to the parent directory
```

One folder per group the person is in, and only those. Whoever is in three groups sees three
folders; whoever is in none does not see `~/Gruppen` at all — a link pointing into nothing is
cleaned up on the next start.

**Membership decides, and nothing else.** Even an administrator only gets to the drives of the
groups they are in themselves. That is intentional: whoever manages groups manages memberships —
that does not mean they should look into the files. Whoever really needs to get in adds themselves
to the group, and that is in the audit log.

### When a revocation takes effect

| | Takes effect |
|---|---|
| In the browser | **immediately** — the next request is rejected |
| In the running container | at the **next session start** |

The difference is not carelessness. Taking a bind mount away from a running container would only be
possible by ending it — throwing someone out in the middle of their work would be worse than the
hour until the next start. The same rule applies to the other permissions (`auth-roadmap.md`).

### On disk

```
/srv/ota/groupfiles/<id>/             the directory
/srv/ota/groupfiles/<group name>      a link to it, for humans
```

Named after the group's **ID**, not its name — for the same reason as with the profiles: a group
name can be changed in administration, and from that moment the path would point elsewhere. In the
container the folder still carries the name; if the group is renamed, it is called differently from
the next start, and the data stays where it is.

The directory carries the **setgid bit**. Without it a container could create files that another
can no longer change — and on a shared drive that is the normal case, not the exception.

It is backed up with `make backup` together with the other content ([chapter 14](14-sicherung.md)).

### Turning it off per workspace

In the workspace editor under **Resources → Group drives**. The default is **on**. Off makes sense
for workspaces that should deliberately be isolated.

## The start script ✅

**Workspace editor → Environment → Script at start.**

Runs on every session start **as the user** in the container, before the workspace counts as ready.
Meant for everything that belongs in the home but not in the image.

As the user and not as root, and deliberately so: a script that writes into a user directory with
root permissions leaves files behind that the user can no longer change — a bug that is only noticed
weeks later.

Two variables are available:

| Variable | Contents |
|---|---|
| `$HOME` | `/home/kasm-user` |
| `$OTA_SHARED` | `/mnt/ota` — the shared shelf |

### Example: distributing a company certificate

```bash
#!/usr/bin/env bash
set -e
mkdir -p "$HOME/.pki"
cp "$OTA_SHARED"/zertifikate/*.crt "$HOME/.pki/" 2>/dev/null || true
```

The certificate is uploaded to the shelf once; every start fetches the current state.

### What it should not do

**No installations.** Those belong in the golden image. An `apt-get install` in the start script
would run on every start, make every user wait and block the workspace if the package source fails.

**Nothing that takes long.** The workspace only counts as ready afterwards.

### When it fails

The workspace starts anyway. Refusing it entirely because of a failed setup would be the worse
answer — the applications run, after all.

The output is in the container:

```bash
docker exec <container> cat /tmp/ota-start.log
```

and the return code in the agent's log:

```bash
docker compose -f deploy/docker-compose.yml logs agent | grep Startskript
```


## One-time scripts ✅

**Workspace editor → One-time.**

The case they exist for: a new golden image brings an application in a new version, and it needs a
change in the home — a moved settings file, a new path.

* The **skeleton** does not help: it only applies as long as the home is empty, and it has not been
  for a long time.
* The **start script** helps, but then runs again on every start — although the matter is settled
  after the first time.

A one-time script runs **exactly once per user**, on the next start of this workspace.

```bash
#!/usr/bin/env bash
set -euo pipefail
# $OTA_SHARED = shared shelf,  $OTA_FILES = the user's own shelf
mkdir -p "$HOME/.config/Code/User"
cp "$OTA_SHARED/vscode/settings.json" "$HOME/.config/Code/User/settings.json"
```

### The bookkeeping

It is recorded per **user and script**, not per session: whoever starts three workspaces of the same
template one after another gets it once. A **new** script is a new entry and runs again for everyone
— that is exactly how it is meant.

**A change to the text does not make it run again.** That is the uncomfortable but honest answer: a
script that ran again for everyone after every typo fix would no longer be a one-time thing, and
nobody would dare to touch it. Whoever really wants to repeat the run says so explicitly — that is
what **Again** is for.

**Again** executes nothing. A one-time script runs in the container, and that may not be running at
the moment; the button only takes back the note "has already run". It is caught up on the next
start of every affected user.

### When it fails

The workspace starts anyway — refusing it because of a failed setup would be the worse answer.

The run is **still recorded as done.** Otherwise a broken script would run again on every start of
every user, and an error would become a permanent burden. It stays visible: the editor shows return
code, affected users and the last lines of output.

One exception: if the run did not even happen — the container did not answer — nothing is recorded.
Then the script was not the problem but the way there, and the next start tries again.

### What it should not do

The same as for the start script: **no installations.** Those belong in the golden image. And
nothing that needs root — it runs as the user in the container, so the files belong to them and
they can still change them later.
