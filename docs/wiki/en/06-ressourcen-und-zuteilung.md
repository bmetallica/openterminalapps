# 6 · Resources and allocation per user

*For administrators.* Workspace editor → tab **Allocation**.

## The problem

The same workspace should be sized differently for different people. The developer gets 4 cores and
6 GB, the working student 1 core and 2 GB, external contractors a flat small amount.

The obvious way would be to copy the workspace. **That is the wrong way** — it multiplies the
maintenance of image, permissions, app catalog and golden image version. Three copies mean three
places where an update can be forgotten.

## The solution: overrides

OTA stores **only the values that differ**. Everything else is inherited.

```
1.  Template default               4 cores / 6.0 GB
2.  Override per group             group "externe": 2 cores / 3.0 GB
3.  Override per user              tim.r: 1 core / 1.0 GB
                                   ↓
    The most specific wins.
```

If someone belongs to several groups, the group with the higher priority decides.

## In the interface

The **Allocation** tab lists every user who reaches the workspace through an assigned group — also
those without an override of their own. Otherwise you would have to guess whom the template
affects.

Per row: name, effective cores, effective memory and the **origin**:

| Marker | Meaning |
|---|---|
| `VORLAGE` (template) | inherits everything |
| `GRUPPE` (group) | a group override applies |
| `NUTZER` (user) | own allocation, marked blue |
| `GEMISCHT` (mixed) | cores and memory come from different levels |

Expanding shows the sliders for exactly this user, with the same overbooking hatching as elsewhere.
The inheritance marker shows where the current value comes from; **Reset** removes the override
again.

## Which level when

| Level | What for |
|---|---|
| **Template** | The normal case. What most people should get |
| **Group** | Whole circles of people: externals, apprentices, a project team with high demand |
| **User** | The exception. Individual people with documented special needs |

As a rule of thumb: if a user override shows up identically more than two or three times, it
belongs in a group.

## Taking effect

Since 2026-10-08 changed resources apply **to existing containers as well** — running, paused and
stopped root workspaces. Before, they only applied to the next container, and a root workspace that
stays the same for weeks never got them. This applies to changes to the workspace and to overrides
per group and user; the message after saving says how many containers were adjusted.

One limit remains, and it is intentional: **nobody has memory they are currently using taken away
in the middle of their work.** If memory is to drop below what a running container currently
needs, the CPU applies immediately and the memory from the next start or resume. Otherwise the
change would mean: the kernel kills programs in the session.

Technically this is `docker update` through the agent; swap is set to twice the memory, as when
creating.

At start the resolved value is fixed and passed to the container as `--cpus` and `--memory`. It is
traceable in the session overview.

## Overbooking

OTA does not stop anyone from committing more than the host has — with varying usage that often
makes sense. But it is made visible:

- The slider hatches the overbooked range
- The capacity gauge above the list turns red
- At start OTA checks the **actually free** memory and refuses with an understandable message,
  instead of letting the host run into the OOM killer

## What cannot be set per user yet

Resolution, permissions and timeouts follow the template and the group settings. The data model
provides overrides for them (`plan.md` §9.7), the interface does not show them yet. 🔨
