# 31 · Files — what lives where and what is kept

*For users.* How files get into your workspace and out again, and what of it is still there after
ending.

## What lives where ✅

| Place in the workspace | What it is | Kept | Who sees it |
|---|---|---|---|
| `~` (your home) | your projects, settings, keys | ✅ always | only you |
| `~/Austausch` | **My files**, also reachable in the browser | ✅ | only you |
| `~/Gruppen/<group>` | your group's drive | ✅ | everyone in the group |
| `~/Gemeinsam` | files from the administrators for everyone, **read-only** | ✅ | everyone |
| everything else (`/opt`, `/usr`, `/etc` …) | the workspace's system | ❌ for a standard workspace, ✅ for a root workspace | – |

The three folders in your home are links. The same content is under `/mnt/austausch`,
`/mnt/gruppen` and `/mnt/ota`, in case you use them in a script. If one is missing, the
administrators have switched it off for this workspace.

## My files ✅

The quick way into the workspace and out again.

- **In the browser:** sidebar → **My files**. Drag files in or **Choose files**, create folders,
  download, delete. What you put here is in `~/Austausch` a second later.
- **While working:** open the session's control bar (handle on the right edge). The same shelf is
  there. Drop files onto the bar, not onto the application's picture: the remote desktop does not
  accept files from your own computer directly.
- **Out:** put the file into `~/Austausch` in the workspace, download it in the browser.

Nobody else sees your shelf, not even the administrators.

## Group drives ✅

For files a team works on together. Under **My files** you choose the drive at the top; in the
workspace it is under `~/Gruppen/<group>`. You only see the drives of groups you are in.

If you join a new group, its drive appears in the browser immediately and in the workspace at the
**next start**.

## The shared shelf ✅

`~/Gemeinsam` contains what the administrators provide for everyone: certificates, installation
packages, templates. You can read and copy from it, but not put anything in.

## What is still there after ending

**Your home always stays**, even when the container is deleted or a new image arrives.

**In a standard workspace**, everything outside your home goes with the container: packages you
installed with `apt`, changes to `/etc`. If you need a program permanently, tell the
administrators. It then belongs in the image.

**In a root workspace** the system stays too, until you rebuild it
([chapter 32](32-root-arbeitsplatz-nutzen.md)).

## Several workspaces, one home

Normally your workspaces share one home. That is why only one of them can run at a time; the second
one says "… is already running and uses the same home".

If the administrators have set a workspace's persistence to **Shared data**, it has a home of its
own for settings but shares `Desktop`, `Documents`, `Downloads` and other folders with your normal
home. Such workspaces run side by side.

## Confidential material

- Private keys and passwords belong in your home, not in a group drive.
- What is in `~/Gemeinsam`, everyone sees.
- Whether and how often your home is backed up is decided by the administrators.
