# 9 · Connecting Kasm images and registries

*For administrators.*

A **feature**, not the foundation. OTA's core is the workspace ([chapter 3](03-arbeitsplatz.md)).
This chapter describes how the existing ecosystem of ready-made application containers is used
alongside.

## When it is worth it

- Tools you need **rarely and in isolation** — GIMP, Inkscape, a throwaway browser, an OSINT tool —
  and that would only take up space in the personal workspace
- **Migration**: what runs in Kasm today also runs in OTA on day one
- Applications for which a maintained image already exists and for which a build of your own is not
  worth it

## Connecting a single image

Create a new workspace, `mode: single_app`, enter the image reference. That is it. Resources,
permissions and assignment work exactly as for the workspace.

## Connecting a whole registry

A registry is a catalog of ready-made applications as a JSON file at a fixed address:

```
{registry_url}/{schema_version}/list.json
```

**Administration → Registries.** It shows what is registered, how many entries each catalog has, how
many of them were added, and when it was last read.

### Suggested, not registered

OTA knows three widespread registries and offers them with one click — **none is registered by
itself.** A registry is a trust decision (see below), and that is made by a human, not by the
default.

| Registry | Address | Applications |
|---|---|---|
| Kasm Technologies | `https://registry.kasmweb.com` | 86 |
| Kasm AI Images | `https://ai.registry.kasmweb.com` | 11 |
| LinuxServer.io | `https://kasmregistry.linuxserver.io` | 2 |

Any other address can be registered the same way. **https** is required — a catalog over an
unsecured connection is a catalog someone can change on the way, and from it come image references
that afterwards run in your own network.

**The catalog is read immediately when registering.** If it cannot be loaded, no entry is created:
a registry that only exists as a line in a list helps nobody. If a later **Refresh** fails, the
registry stays — but the error is recorded and shown in the list, so that tomorrow it is still
visible that something has been stuck here since yesterday.

Categories in the official catalog: Browser, Chat, Communication, Desktop, Development, Games,
Mobile, Multimedia, OSINT, Office, Privacy, Productivity, Remote Access, Security.

## The catalog

A click on a registry opens its catalog in the main window: search over name, description and
category, plus category chips to narrow it down. Every entry names icon, name, description, image
reference and **size**.

### Which version is suggested

The catalog lists several Kasm versions per application. Naively taking the last one is wrong: for
AlmaLinux 8 the two newest point to `kasmweb/almalinux-8-desktop:develop` — a rolling development
state, and the last of them with size 0, so not even built yet.

OTA therefore suggests the **newest version that is not `develop` and has a real size**. Only if
there is none does the choice fall on what is left — then the catalog simply has nothing better.

### What OTA checks before adding

**Architecture.** A pure `arm64` image on an `amd64` host is shown, but not offered for adding;
below it, it says why. Hiding it only raises the question of why it is missing.

**Size.** The catalog names the unpacked size. It is shown **before** adding, and if it takes a
noticeable bite out of free disk space, the interface warns. A 6.5 GB image is a decision when space
is limited, not a side issue.

## The import

**An import downloads nothing.** It creates a template, nothing more. The image only comes on the
first start or when someone pulls it under *Images* ([chapter 16](16-images-verwalten.md)).

What is created:

| | |
|---|---|
| Mode | `single_app` — a Kasm image brings exactly one application and starts it itself. Operated as a desktop, its start script would be covered, and then nothing would start at all |
| Visibility | **turned off.** An import should not appear unasked on all users' dashboards. Assign a group first, then turn it on |
| Home | its **own** profile per template, not the shared one of the workspace. A foreign image does not get the key to the flat |
| Origin | stays recorded. A second import of the same entry is refused, with a reference to the existing template |

Added templates **stand on their own feet**: if the registry is removed later, they remain. The
catalog was only the way they came about.

If an entry disappears from the catalog, it is dropped at the next refresh — unless it was added.
Then it stays as proof of origin.

### Why the icons go through OTA

The icons live at the foreign registry, but the browser fetches them via
`/api/admin/registries/{id}/icon`. Not out of tidiness: the application's content policy does not
allow foreign image sources (`img-src 'self'`), and loosening it for every registered registry would
be a bad trade for an icon.

The detour is tethered — only what lies **below the address of this registry** is fetched, and only
if it is an image. Without this tether it would be a tool to fetch arbitrary addresses through OTA,
including ones in the internal network.

## Two notes to take seriously

> **A registry is a trust decision.**
> An imported image comes from a foreign source and afterwards runs in your own network. The catalog
> carries an ES256 JWT over a hash of its content, but the public key for it is held by Kasm; **OTA
> does not verify the signature** — without the key that would be theatre. The interface says so
> instead of hiding it. The rule: only connect registries whose operator you trust.

> **The catalog says nothing about licences.**
> That a registry lists an image is no statement about whether its use in the company is permitted.
> Contained applications can be proprietary or require user licences. The import dialog points this
> out — the check stays with the administrator ([chapter 13](13-lizenzen.md)).

## Limits

The images are designed for **one application**. They are throwaway containers: no shared home with
the workspace, no shared SSH keys, and the clipboard only works towards the browser and back — not
directly to an app in the workspace. The path via the browser clipboard works, of course.

Whoever needs a tool daily is better off in the workspace.
