# 7 · Golden images

*For administrators.* ✅ Build pipeline with live log, recipes, app discovery, versions, activation
and rollback · ✅ Freezing a session · ✅ Skeleton management, per workspace and per application ·
✅ own base image `ota/base-xfce`

> **Kasm on the same host no longer interferes.** At first its agent deleted every golden image
> that was built, because it inherited the label `com.kasmweb.image=true` from the base image. The
> builder now deletes this label — Kasm does not even look at images without it. Details in
> [chapter 12](12-fehlersuche.md).

## What a golden image is

A preconfigured workspace that all users get identically. It consists of four layers:

| Layer | Contents |
|---|---|
| **Base** | A starting image — `ota/base-xfce` or a finished Kasm image |
| **Build layer** | Packages, **extension lists per editor**, a free setup script |
| **Skeleton profile** | What is copied into the home on the *first* start: `settings.json`, Git template, certificates, desktop shortcuts |
| **Runtime policy** | Resources, resolution, permissions, timeouts |

## Freezing a session ✅

Golden images are rarely designed on the drawing board. The practical way:

1. **Start your own workspace** and set up in it what everyone should get — install packages,
   configure tools
2. Under *Software → Freeze session*, click **"See what would be included"**
3. Go through the list
4. **"Freeze as a new version"** — then activate it like any other version

What gets frozen is **your own** session. Capturing someone else's would be something different and
would need its own justification.

### What comes along — and what does not

**The home does not come along.** `docker commit` takes the container's file system, but no bind
mounts, and the home lives exactly there. That is the right boundary and no accident: a home
belongs to a person and contains their keys. Putting it into an image that everyone gets would be a
data leak waiting to happen.

Everything outside comes along: installed packages, changes in `/etc`, files in `/opt`.

Not in the list are the directories that change in every container and interest nobody — `/tmp`,
`/var/log`, `/var/cache`, `/proc`. Without this trimming the preview would be nine tenths noise,
and then nobody would read it. Nor would anyone read the warning in it.

### The secret filter

Credentials end up outside the home too: `/etc/ssh`, a `.netrc` under `/root`, a Kerberos ticket.
Whatever looks like one is listed **at the top and coloured**:

```
.ssh/id_*      .gnupg/       *token*        *.pem   *.key
.aws/          .docker/config.json          krb5cc_*
.netrc         .git-credentials             *.keytab
/etc/ssh/ssh_host_*           /etc/shadow
```

**Without explicit confirmation nothing is frozen.** A preview that can be skipped is decoration —
the button is then called "Freeze despite the findings", and the version's log names every single
file.

Still: **a golden image should never come from a session in which real credentials were used.** The
filter is a net, not a guarantee.

### One file is always removed

`/etc/sudoers.d/ota-admin` — the file that allows an administrator `sudo` in **their** container
([chapter 8](08-nutzer-und-gruppen.md)). If it stayed in the image, **every** user of the new
golden image would get passwordless root: an exception for one person would silently have become
the default for everyone.

It is removed before freezing and **put back into the running container afterwards**. Whoever
builds an image should not lose their own `sudo` doing so. For every further session of an
administrator it is written anew anyway.

### What happens afterwards

The new version is **not active**. Only a click on *Activate* puts it live — the same order as when
building, and for the same reason: what everyone gets, nobody should roll out by accident. Running
sessions stay untouched.

The Kasm label is deleted and the start script overwritten, exactly as when building: otherwise
Kasm's cleanup service would remove the image, and the frozen container would bring along the start
script that was running in it.

## Versions

Every build creates `ota/<name>:v<N>` with digest, size and full log.

- Exactly one version is **active** — new sessions use it
- **Running sessions stay untouched**
- **Rollback** is one click: set another version active
- Old versions are cleaned up: **the last three stay**, plus always the active one, even if it is
  older. A version you could fall back to is half the point of versioning

A single version can also be **removed by hand** — for a failed attempt, a trial run, an image
whose content should not be distributed. The **active** one cannot: deleting it would make the
template point to an image that no longer exists, and the next start would fail with a message
nobody would connect with this click.

> Until 2026-08-28 the cleanup did not run at all — the rule was in the code and never applied. It
> was only noticed when freezing arrived and versions grew faster than with building. Each one
> takes space, and on a host with 25 GB free that is the end of operations after a few weeks.

A **trial run** is recommended: assign the new version to a small group first, then globally.

## Adding and enabling software ✅

**Workspace editor → Software.** Two steps, one below the other, because they happen in this order.

### 1 · Adding

Click or type packages, then **Build image**. The log runs **live** — it comes as an event stream,
line by line, as soon as it is produced. Depending on the package the build takes a few minutes.
Afterwards the new version is listed under *Versions* and is put into operation with
**Activate**. Running sessions stay untouched — the new version applies from the next start.

**Packages are checked beforehand.** OTA asks the image whether it knows a name before the build
starts. That saves the most common failure: a Debian name on an Ubuntu image. Whoever enters
`firefox-esr` immediately gets "this image does not know it" and suggestions, instead of a line in
the log ten minutes later.

A second check is less conspicuous and more important: **Ubuntu 22.04 lists `firefox` only as a
pointer to a snap.** No snap runs in a container; what would be installed is a placeholder without
a program — the build would report success, and only the user would notice that nothing is there.
OTA recognises this and says so.

> **Why the log runs live.** The server still polls the agent every two seconds; there is no other
> way to get at the progress of `docker build`. What goes away is the browser's polling: it only
> receives the increment. With a log that grows to several hundred kilobytes, that is the
> difference between a calm window and one that stutters. If an intermediary does not let the
> stream through, the interface falls back to the old polling — better slow than blind.

**After building, OTA checks where the editors point.** At the end of the log it says which
marketplace VS Code, VSCodium or Code-OSS fetch their extensions from. If a non-Microsoft editor
points to Microsoft's marketplace, a warning appears — that would be a licence violation
([chapter 13](13-lizenzen.md)). The build does not fail because of it; the decision to distribute
such an image belongs to a human.

### Recipes ✅

For software that is not a plain package. Bundled are **Firefox** (from Mozilla's APT repository),
**Google Chrome** and **VSCodium**. A click appends the steps to your own script — visible and
changeable, not as hidden behaviour.

#### Building your own recipe

**New recipe** opens a guide. On the left the questions, on the right the result immediately: you
see what an answer does while you give it. Five kinds cover almost everything:

| Kind | What for | What is asked |
|---|---|---|
| **APT repository** | The most common case. This is how Firefox, Chrome and VSCodium get into the image | Key address, repository line, package, priority |
| **.deb file** | Software delivered as a file instead of through a repository | Address of the file |
| **Archive** | Everything with its own directory — JetBrains, Blender | Address, ID, program in the archive, display name |
| **AppImage** | A single AppImage file | Address, ID, display name |
| **Own script** | When no kind fits | just the text |

The guide takes care of two things that are otherwise overlooked:

- **The key is attached to the repository line.** Nobody writes the `signed-by` part themselves; it
  is inserted.
- **Archive and AppImage get a menu entry.** That is not decoration: OTA later recognises the
  application by its `.desktop` file when *looking inside the image*. Without it, it would be
  installed but not discoverable.

**The "priority" switch** is the least conspicuous and the most important. It is needed when the
distribution has a package of the same name — otherwise its version wins. Exactly the case for
Firefox on Ubuntu.

The generated script is no secret: it is shown next to it and can be changed. Whoever does so has
their version apply — the fields then no longer overwrite the text.

**Bundled recipes cannot be changed**, only copied. That way the original stays for comparison.
Recipes you built yourself can be changed and deleted.

Recipes fetch software from foreign repositories. Whoever does not want that builds from an
internal mirror; the steps are in the script and can be rewritten.

### 2 · Enabling

**Look inside the image** lists what is installed. Nobody needs to know a start command for this:
every Linux package brings a `.desktop` file containing name, icon and invocation — OTA reads them
from the built image.

What remains is a list with switches. In addition, per entry you can change:

| | |
|---|---|
| **Name** | directly in the row. "GNU Image Manipulation Program" may simply be "GIMP" for you |
| **Icon** | a click on the symbol cycles through. Only appears if the package does **not** bring its own icon — otherwise the real one is shown |

### The icon from the package ✅

Under `Icon` the `.desktop` file usually only contains a name ("firefox"), not a file. Where the
picture for it lives is defined by the freedesktop specification, and OTA looks for it there: under
`/usr/share/icons/<theme>/<size>/apps/`, in the old `/usr/share/pixmaps`, if need be across the
whole tree. The search goes from large to small and PNG before SVG — large, because the interface
scales and an upscaled 16-pixel icon looks mushy.

Measured on a real workspace image: **16 of 16 applications** brought an icon.

Two things happen automatically:

- **Scaled down.** A package ships the size it considers right: 554 bytes for Vim, 42 KB for GIMP,
  **428 KB for VSCodium**. OTA scales everything down to at most 128 pixels per edge. Without that,
  half a megabyte would sit in the database and in every answer of the catalog.
- **Checked.** An SVG with a reference to the outside is not taken over. Otherwise the dashboard
  would call a foreign server every time it opens — for every viewer.

> **Existing catalogs do not get the icons by themselves.** They come from the image, and OTA only
> reads it when looking through. **Look inside the image** and **Enable** once is enough;
> afterwards they appear everywhere — on the dashboard, in the switcher of the running session, in
> the skeleton tab.

They are served under their own address and not in the catalog itself. The reason is measurable: a
catalog with sixteen icons as data URLs weighs 140 KB, and the dashboard reloads the templates
**every 15 seconds**. As an address, the browser fetches each picture once and keeps it; a
fingerprint in the query string ensures that the new one still comes after an image update.

If an image brings no icon — for example a self-built start script without a `.desktop` entry —
the symbol stays, and the symbol switcher appears again.

Two notices appear by themselves:

- **"Needs a terminal"** — a console program like `htop` starts alone on an empty screen.
- **"No longer present in the active image"** — the catalog still knows it, the image no longer
  does. Happens after a change of base image.

**The order matters.** It determines which display an application gets. Whoever changes it must
restart running workspaces.

### Resolution per application ✅

Under each application there are two number fields. If they stay empty, the workspace's resolution
applies — it is shown in them as a placeholder, so the inherited value is visible without being
set.

This is meant for the case that one application needs more area than the others: an IDE next to a
terminal. The stream adapts to the browser window afterwards anyway — the resolution is the
**initial value**, and that decides how an application first lays out its interface. Some programs
remember this first layout.

**It applies from the next start of this application.** A running display is not changed — as with
all resources in OTA. Whoever wants to see the effect immediately closes the application in the
viewer and opens it again.

### Visibility per group ✅

Under each application it says who gets it. Normally **"Visible to everyone"** — meaning: everyone
who sees this workspace at all. A click opens the groups, and as soon as one is chosen, only its
members see the application.

The case this is meant for: a licence does not cover everyone. The application is in the image — it
has to be, it is an image for everyone — but on the dashboard it only appears for those who may use
it.

> **The list on the dashboard is filtered, but it is not the safeguard.**
> The check happens at start: a call to the start address with the short name of a blocked
> application is rejected, even if the workspace belongs to the caller. Both are checks in
> `scripts/test-authz.sh`.

**Administrators always see everything.** Otherwise they would be managing a catalog they cannot
see.

**A deleted group disappears from the catalogs.** The application is then available to everyone
again — the alternative would be an application that belongs to nobody and that nobody sees.

## The app catalog

For a desktop workspace, the golden image contains several applications. Per app the following is
stored:

```
Display name · icon · start command and arguments
preferred resolution ✅
skeleton subtree    its own tree per application ✅
extension list      installed during BUILD, not at start
visibility          can be restricted per group ✅
```

### The skeleton subtree per application

Under *Workspaces → Skeleton* there is a row at the top: **Whole workspace** and next to it every
application. The difference is the timing.

| | Whole workspace | Per application |
|---|---|---|
| **Arrives** | on the workspace's first start, as long as the home is empty | on the first start **of this application**, even months later |
| **How often** | once per home | once per home and application |
| **"Enforce"** | yes, for individual paths | no — that is what the workspace's tree is for |
| **Meant for** | `.bashrc`, company certificate, desktop shortcuts | `.config/Code/User/`, `.config/JetBrains/`, `.config/VSCodium/User/` |

**Why separate.** A workspace carries a dozen applications, and not every person starts each of
them. Putting the IDE's settings into the home of someone who only uses the terminal fills the home
and makes troubleshooting hard — when a complaint comes in, configuration lies around that no
application ever read.

The subtree arrives **before** the application starts. The other way round, it would first create
its defaults, and the subtree would afterwards overwrite what the person already sees on screen.

This is remembered in the home itself, under `~/.ota/app-skeleton/<application>` — not in the
database. Two reasons: the application catalog is replaced completely when saving, bookkeeping
attached to it would be gone after every catalog change. And the question is "does **this home**
already have the subtree?" anyway, which only the home can answer. A workspace without a persistent
profile consequently gets it anew on every start.

> **Roll out again** — the same gesture as "Again" for the one-time scripts, only by hand:
> ```
> docker exec <container> rm -f /home/kasm-user/.ota/app-skeleton/<application>
> ```
> On the next start of this application the subtree comes again.

**Extensions belong in the build, not in the start.** Otherwise every user waits for downloads on
every start, and an outage of the marketplace paralyses the workspace. The list is under
*Software → VS Code extensions*.

> **They end up exclusively in Microsoft's VS Code.** VSCodium has its own set from Open VSX and
> does not see them — the same ID there is not the same installation, and some extensions only
> exist on one of the two marketplaces. Whoever offers both editors maintains two sets
> ([chapter 13](13-lizenzen.md)).

### Single-instance applications

VS Code, Chrome and Thunderbird can only be started once per user. A second call reports to the
running instance and exits — without a window, without an error message. In the catalog such an
application therefore gets its **fixed display** entered: "this application belongs on exactly this
screen".

> Until 2026-08-27 this accidentally meant something else, namely "it is already running there" —
> OTA then did not start it at all. That only went well as long as the base image's inherited start
> script restarted it every three seconds. Both are fixed; the story is in
> [chapter 12](12-fehlersuche.md).

Recognisable by a black picture despite "running": check with
`docker exec <container> pgrep -a <application>` whether it is already running on another display.

## Profile and drift

Users change their environment — that is desired. For the cases where something must stay binding:

- **"Enforce" paths**: defined files are overwritten from the skeleton on *every* start. For
  company certificates, proxy settings, registry URLs. Use sparingly — every file here is one the
  user cannot adapt
- **Reset profile**: for individual users or whole groups, with automatic backup

## Builds

Builds run **serialised** — only one at a time, so the host does not collapse. The log runs live,
timeout 45 minutes, can be cancelled at any time.

A nightly rebuild to pick up security updates is optional. It reports what changed and does **not**
activate the new version by itself.

## Keeping an eye on size

A workspace with five tools ends up at 12–18 GB. It lives **once** on the host, independent of the
number of users. Still: before adding another application, check whether it really carries
everyday work.
