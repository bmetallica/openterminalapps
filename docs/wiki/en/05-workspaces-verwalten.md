# 5 · Managing workspaces

*For administrators.* Menu item **Workspaces**.

## What a workspace is

A template that sessions are created from. It defines: which image, how many resources, which
permissions, who may see it.

Two modes:

| `mode` | Meaning | When |
|---|---|---|
| **`workspace`** | One Linux per user, several apps inside. **Default** | The everyday workspace |
| `single_app` | One application as a throwaway container | Rarely used tools, connected Kasm images |

## Capacity gauges

Above the list there are three measurements:

- **Free memory** — what the host has left right now
- **Committed per session** — the sum of all active workspaces if all ran at the same time. If it
  exceeds free memory, the bar turns red. That is **not an error**, but deliberate overbooking —
  only it should be visible, not surprising
- **Cores** — what all sessions share

## The editor

A click on a row opens the editor as a side panel; the list stays visible.

### General
Display name, description, image, categories, active/inactive.

The **image** is picked from those present on the host, not typed freely. Its size is shown next
to it.

A deactivated workspace disappears from the dashboards, but the assignments remain.

**Streaming** is here as well: `Selkies` is the default and the path of the own base image;
`KasmVNC (RFB)` belongs to Kasm images that do not bring Selkies.

### Network ✅

A selection field, and without any action it says **Default (internet, no company network)**: the
workspace gets to the internet, but not to the company network, not to the neighbouring session
and not to the host. For most templates that is the right answer and there is nothing to do.

Whoever needs more or less creates a profile under **Network** and picks it here — for example
*Isolated* for a template that only handles local data, or one of your own with a rule for the
internal package mirror. A profile applies to **every session of this template**.

The field only takes effect on the **next start** of a session. What the base rule set lets through
anyway is in [chapter 23](23-netz.md) — also the level "off", which lifts every restriction and
therefore requires a justification.

### Apps (only for `mode: workspace`) ✅
The catalog of applications installed in the golden image. Per app: active/inactive and the source
of its extensions.

> **Extensions do not travel between the editors.** VS Code pulls from the Microsoft marketplace,
> VSCodium from Open VSX, Cursor from its own registry. Whoever works in several maintains several
> sets. That is not a limitation of OTA but a licence condition ([chapter 13](13-lizenzen.md)).

Blocked apps show the reason and cannot be turned on.

### Resources
Processor cores, memory, resolution, idle time and what happens afterwards.

The sliders show **hatched** on the track from where this host would be overbooked. Whoever goes
beyond sees the consequence immediately — instead of learning it later in an OOM kill.

For a desktop the values apply to the **container as a whole**, not per app.

**Cores are a weight, not a hard limit** (since 2026-10-27). While the host has headroom, a
container may use up to four times its cores, at most all cores of the host. When it gets tight, the
kernel shares CPU time in proportion to the configured cores: a workspace with 4 cores then gets
twice as much as one with 2. The factor is `OTA_CPU_BURST` in `deploy/.env` (default `4`; `1` means
a hard limit as before), applied to newly created containers and on every resource change. The
reason is in [Troubleshooting](12-fehlersuche.md#everything-stutters-although-the-host-is-not-busy).
Memory stays a hard limit.

*What happens after inactivity:*

| | |
|---|---|
| **Pause** | Memory stays allocated, resuming takes under a second |
| **Stop** | The container is ended and started again next time |
| **Delete** | The container is removed. **The persistent profile is kept** |

*Persistence:*

| | |
|---|---|
| **Per user** | One shared home for all workspaces. The normal case |
| **Shared data** | Own settings per type, data folders from the shared home. Runs **alongside** the user's other workspaces |
| **Per workspace** | A separate home per type. When configurations interfere |
| **Ephemeral** | Nothing is stored. Every start begins at the golden image |

**Two workspaces on one home do not start at the same time.** The second is refused with a
message. That is deliberate: programs such as VS Code or Chrome put locks and sockets in the home
and would otherwise reach into the other container. Anyone who needs several at once, such as two
root workspaces, sets them to **Shared data**:

- Each workspace has its own home under `/srv/ota/profiles/<id>/<slug>`, with its own settings and
  its own browser and IDE profile.
- The folders under **Shared folders** come from the shared home (`…/<id>/user`). Whatever one
  workspace puts there, the other sees at once. Default: `Desktop`, `Documents`, `Downloads`,
  `Music`, `Pictures`, `Videos`, `Templates`, `Public`. Your own folders work too, such as
  `Projekte` or `Projekte/customer-a`. They must be relative, without `..` and not hidden.
- Shelf, group drives and `~/Gemeinsam` are there as always.
- After switching, the workspace starts with fresh settings from the skeleton. The old dotfiles
  stay in the shared home. A **paused root workspace** needs one *Rebuild*
  ([chapter 25](25-root-arbeitsplatz.md)), because the folders are mounted when the container is
  created. Freeze whatever is installed in it first ([chapter 7](07-golden-images.md)).

**OTA Git** (under Resources): if [OTA Git](27-git.md) is on, workspaces from this template get Git
preconfigured for the Git subdomain: address, token, name and email. On by default. Turning it off
is worth it for workspaces that have nothing to do with Git. It takes effect on the next start of a
workspace.

### Permissions
Clipboard, files, devices, other — grouped, with an explanation per switch.
See [chapter 4](04-zwischenablage.md).

### Environment
Environment variables for the container.

> **No secrets here.** Environment variables are readable via `docker inspect` for anyone with
> Docker access and end up in logs. Credentials belong in the secret store.

### Allocation
Two parts: which **groups** see the workspace, and which **resources per user** apply.
→ [chapter 6](06-ressourcen-und-zuteilung.md)

Changes to the group assignment show their consequence immediately ("2 groups are added. Affected
users see the workspace after saving.").

> **For everyone using the API directly:** in a `PUT /api/templates/{id}` a **missing** `group_ids`
> means the assignment stays as it is. An **empty list** means nobody has it any more. The
> difference between *said nothing* and *wanted nothing* matters here: until 2026-08-28 both
> counted as "nobody any more", and a call that only wanted to change one setting made the
> workspace silently vanish from all dashboards.

## Duplicating ✅

The editor has a **Duplicate** button at the top. It is the way to use a fully set-up workspace —
say a root workspace with apps, network profile and start script — as the starting point for a
second one. The only question is the name (default: "… (copy)").

| Copied | Not copied |
|---|---|
| all settings: image, class, streaming, resources, network profile, permissions, environment, start script, shelves, Git | the **version list** under Images — the copy points at the same image until it gets its own built or frozen version |
| the app catalogue with icons, resolutions and visibility per group | what people have **inside** their workspaces: homes, software installed in the root container |
| run-once scripts — they run once more for everyone in the copy | users' own names |
| allocations per group and user, the groups | unsaved changes in the open editor |
| the skeleton, including the applications' subtrees | |

The copy is **disabled**. Otherwise every assigned person would immediately see a second tile that
looks the same. Adjust it, then enable it under General.

Because original and copy can share an image, OTA **never removes an image that another template
still points at** when deleting or pruning old versions — only the list entry goes.

> To take **what is installed inside** along as well, first freeze your own session
> ([chapter 7](07-golden-images.md#freezing-a-session-)), then duplicate the template and point
> the copy at the frozen version. For a root workspace the Docker data (images and containers
> inside it) does **not** come along — it lives in a separate volume.

## Changes to running sessions

Resource changes take effect **immediately, also on running, paused and stopped containers**. Only
when memory is to drop below what a running container currently uses does that part wait until the
next start — nobody has memory they need taken away during operation. Details in
[chapter 6](06-ressourcen-und-zuteilung.md#taking-effect).

Permission changes take effect immediately.
