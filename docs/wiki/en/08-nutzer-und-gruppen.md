# 8 · Users, groups and permissions

> **Since 2026-08-28 the accounts come from Keycloak.** OTA keeps them as a projection — groups,
> permissions and allocations stay here — but they are verified there. **Since 2026-10-08 they are
> also created there:** an account created here is created by OTA in Keycloak; password and second
> factor are changed under My account through Keycloak. Only the emergency account is local. How
> this fits together is in [chapter 18](18-zentrale-anmeldung.md).
>
> **Email is a required field.** For a long time it was not; since it is passed on to connected
> applications, an account without an address is one that cannot sign in there. Internal addresses
> (`boss@company.local`) are explicitly allowed — OTA is a tool for the internal network and does
> not enforce internet rules there. Two accounts with the same address are not possible: connected
> applications recognise people by it, and two would be one person there.

*For administrators.* AD connection ✅, Kerberos dropped

## Principle

OTA's user management is **self-contained**. LDAP/AD and OIDC are optional add-ons, not
prerequisites. There is no requirement for an external identity provider.

## Roles

Two system groups that cannot be deleted:

| Group | May |
|---|---|
| **`admins`** | Everything: workspaces, golden images, users, groups, assignments, registries, all sessions, audit log, global settings |
| **`users`** | Only their own: start assigned workspaces, manage their own sessions, their own settings |

Further groups can be created freely and serve for assignment and resource overrides
([chapter 6](06-ressourcen-und-zuteilung.md)).

The data model has fine-grained permissions (`images.manage`, `users.manage`, `sessions.view_all`,
`settings.manage`, `audit.view`), so that roles like "Support" (may see sessions, configure nothing)
are possible later without a schema change.

### Enforcement

In three places, not just in the menu:

1. Route guard in the frontend — convenience
2. Check at **every** API endpoint — the truth
3. Query restriction: non-admins get exclusively their own records; not "fetch everything and filter
   in the frontend"

## Administrators are root in their container ✅

Whoever administers OTA gets passwordless `sudo` in **their own** session containers. Without it
nothing could be installed or checked there — and that is exactly why an administrator signs in to a
workspace.

Technically that means two things: the container runs without `no-new-privileges`, and the Linux
capabilities are not dropped. Both are needed for `sudo` to start at all. For all other users both
stay in force.

**What this means, in all clarity:** root in a container is not root on the host, but the distance
between them is smaller than with an unprivileged container. These permissions therefore belong to
the same few people as access to the Docker host — not to "everyone who needs to administer
something now and then". Whoever should only create users and maintain workspaces gets the
individual permissions for that (*Create and change users*, *Create and change workspaces*) instead
of *Full access to everything*.

Changes to `/etc` and installed packages do not survive the container — they live outside `/home`.
What should stay permanently belongs in the golden image ([chapter 7](07-golden-images.md)) — or
the workspace is a **root workspace**: there root is unprivileged on the host (Sysbox), and what
gets installed stays ([chapter 25](25-root-arbeitsplatz.md)).

## Two permissions for root workspaces ✅

*Since 2026-10-06* ([chapter 25](25-root-arbeitsplatz.md)).

| Permission | Means |
|---|---|
| **Use root workspace** (`arbeitsplatz.root`) | Start templates of the class "Root with Docker": root and Docker in the container, stopped instead of deleted. Without the permission the start is refused with an explanation |
| **Web terminal as root into running workspaces** (`arbeitsplatz.terminal`) | Open a root shell in the browser under Operations → Workspaces — in every running workspace, including other people's. Every input is logged with the name |

Administrators have both. The second is more powerful than connecting to the screen: whoever has it
reads every file in a user's home. Grant it like access to the Docker host.

## What a permission means — and what it does not

*See and end all sessions* (`sessions.view_all`) means exactly that: administration lists all
running sessions, and they can be ended. It does **not** mean that you can connect to someone
else's screen.

Until 2026-08-27 it did. The check before every call to `/s/<id>/` used the same function as the
list, and so the permission reached all the way to another person's running screen — with their
open terminal and their unlocked password store. Between "seeing that something runs" and "sitting
at it" lies the whole difference.

Only a **full administrator** gets onto someone else's screen now, and they sit at the Docker host
anyway and reach the same there.

### And it is in the audit log ✅

Since 2026-09-04 this leaves a trace. If someone connects to another person's screen, an entry
`session.attached` is created with the owner's name — readable under **Operations → Audit log**,
there in plain text as "Connected to someone else's screen". It belongs to the long retention class
and stays for a year ([chapter 11](11-betrieb.md)).

Two subtleties, so the numbers do not mislead anyone:

* **One entry per quarter hour and pair**, not per call. The permission check runs before *every*
  request of a session, even before every frame — one entry per request would not be a log but
  noise, and the interesting line would drown in it.
* **Looking at your own screen creates no entry.** Otherwise the log would be full of the normal
  case.

What is still missing: **the person at the screen notices nothing.** A notice in the session while
someone else is watching, and beyond that remote assistance with explicit consent, would be the next
two steps. For a works agreement the audit entry is the basis: without it, a rule about connecting
cannot be verified.

## Passwords and sign-in

- **Argon2id**, minimum length 12, checked against known compromised passwords
- Session via `HttpOnly`/`Secure`/`SameSite` cookie, short validity, renewal with rotation
- **Lockout after eight failed attempts for 15 minutes — per account *and sender address*.**
  Whoever locks out locks themselves out
- **Ten sign-in attempts per minute and sender** at the local sign-in, enforced before that in
  Traefik
- Everything in the audit log

### Why the lockout is tied to the sender ✅

Until 2026-09-04 it applied to the **account**, regardless of where the failed attempts came from.
That made it a weapon: whoever knew a colleague's username locked them out with eight wrong
passwords — and with the emergency access precisely the way in you need when the central sign-in
fails.

Now OTA counts per **(account, sender address)**. Another sender starts at zero; the colleague gets
in unbothered from their desk. What this costs: whoever tries alternately from two addresses is not
locked out. That is acceptable — the brake sits in front, the password has at least twelve
characters, and every failed attempt is in the log.

### And the brake in front ✅

**Every sign-in attempt costs one Argon2 run** — deliberately expensive, so that passwords cannot be
brute-forced. That also applies to a name that does not exist at all: OTA makes it take just as
long, otherwise the user list could be queried via response time. **It was counted nowhere** — a
lockout only exists on an account, and a name without an account has none. That made it an
uncapped CPU eater on exactly the machine where the workspaces also compute.

Two brakes against it:

| Where | What | Configurable |
|---|---|---|
| Traefik, in front of `/api/auth/login` | 10 attempts per minute and sender, burst 30 | `OTA_ANMELDUNG_PRO_MINUTE`, `OTA_ANMELDUNG_STOSS` |
| In the API, before the hash | 20 **failed attempts** per sender within a minute | in the source (`auth.py`) |

**The second brake counts every failed attempt, not only those with an invented name** — and that
is no small thing. A brake that only applies to unknown names answers an invented name with 429 and
a real one with 401. That would make it exactly the user list the dummy hash above is meant to
prevent. It happened while building, and the existing timing check in `scripts/test-authz.sh` found
it: 113 milliseconds for a real account, 14 for an invented one. Once the counter is full, **every**
attempt from that address gets the same answer.

**Only `/api/auth/login` is throttled**, not `/api/auth/*`: below that also lie `/me` (on every page
load), the whole OIDC sign-in and the back channel through which Keycloak reports sign-outs. And
this one path is the **emergency door**, not the main door — Keycloak accounts are rejected there
and sent to the central sign-in. Ten attempts per minute therefore cost nobody anything.

> **If a reverse proxy sits in front**, its address must be in `OTA_TRUSTED_PROXIES`. Otherwise
> every request comes from the same address, and the brake lumps the whole company together.
> `scripts/traefik-config.sh` generates both from this one setting, so they do not drift apart.

## My account ✅

Everyone signed in manages their own account under **My account** (at the bottom of the bar). That
needs no administrative permissions — it is about your own person.

| Tab | What you can do there |
|---|---|
| **Password** | For central sign-in accounts: a button that leads to Keycloak and back. For directory accounts: a note that it is changed there. For the emergency account: change it yourself; the change signs out all *other* sessions |
| **Two-factor** | For central sign-in accounts: set up an authenticator app or passkey in Keycloak. For the emergency account: OTA's own (below) |
| **Language** | German or English, remembered on the account instead of only in the browser |

Next to it, the language at the top right, and at the bottom of the bar the **theme** — dark,
light or "match the system". Both are available **already on the sign-in page**. Theme and
language live in the browser: they are a question of the workplace, not of identity. The same
person at a light screen in the office and a dark one at home should not have to change their
account for it. The language is additionally remembered on the account; whoever never chooses gets
the installation's default language (Settings → Language).

"Match the system" is the default and follows the operating system, even when it switches by
itself in the evening. Whoever commits to one overrides that permanently.

> A resolution cannot be set, and that is no oversight: the remote screen follows the size of the
> browser window ([chapter 3](03-arbeitsplatz.md)).

## Two-factor ✅

> **What follows applies to local accounts — that is, the emergency account.** Central sign-in
> accounts have their second factor in Keycloak
> ([chapter 18](18-zentrale-anmeldung.md#my-account-with-the-central-sign-in-)).

**My account → Two-factor.** Set up with an authenticator app: scan the code, type six digits as a
test, done. Whoever cannot scan enters the secret by hand — it is shown next to it.

It is only saved when the test passes. Otherwise you would lock yourself out with a typo.

### Recovery codes

Setup creates **ten codes**. They appear exactly once; afterwards they only exist hashed on the
server, like passwords. **Each one works once** and is removed when used.

They are not an accessory but the answer to a lost phone. The alternative would be "an
administrator turns off the second factor" — and that would be exactly the back door it is meant to
prevent. **In OTA nobody can remove someone else's second factor.**

At sign-in a recovery code is simply typed instead of the six digits.

When they run low, *Renew codes* creates ten new ones; the old ones then no longer work.

### When phone and recovery codes are gone ✅

Then the person can no longer get in — and nobody could help. That is why an administrator can click
*"Remove second factor"* in the user editor under **Second factor**. Afterwards the password is
enough again, and the user sets up the factor anew.

**This is a deliberate weakening, and it is recorded as such.** Whoever manages accounts can use it
to override someone else's second factor. The alternative — nobody can help — is worse: in practice
it leads to nobody turning on the second factor.

Two things make it traceable:

- **All sessions of the account are ended.** Whoever lost their second factor may have lost more.
- The action is in the audit log with the **administrator's name**.

### Turning it off

Requires **password and a valid code**. Whoever only has the password — for example at an
unattended computer — should not be able to remove the second factor; otherwise it would not be
one.

### What is still missing

**Guessing is locked out.** Eight failed attempts lock the account for 15 minutes. Since 2026-08-27
failed attempts at the **second factor** count just the same — before, they did not, and so with a
known password the second factor could be guessed any number of times: six digits, three of them
valid at any time. The same applied to the recovery codes.

### Enforcement per group ✅

In the group editor there is **"Second factor is required"**. If it is on, for every member:

- **Sign-in stays possible.** Whoever cannot sign in cannot get to *My account* and cannot set up
  the second factor at all — a block at sign-in would be a block against its own resolution.
- **No workspace starts.** The attempt ends with a notice to set up the factor.
- The dashboard shows a strip with a button that leads directly to the setup.

The enforcement can also be set for the system groups — especially for them: *"admins must have
two-factor"* is the most common wish.

WebAuthn and passkeys are ✅ available — as a second factor next to the one-time password, not as a
replacement for the password.

## Active Directory and LDAP ✅

**One way, not two.** A directory is connected in **Keycloak** — sign-in lives there, the accounts
are kept there, and OTA takes them over and assigns their groups. It is set up from OTA's
interface: **Administration → Settings → Sign-in and directory**. You do not need the Keycloak
console for it.

How that works in detail is in
[chapter 18](18-zentrale-anmeldung.md#connecting-an-active-directory).

> **Until 2026-09-04 there was a second way:** OTA spoke LDAP itself — its own connection, its own
> nightly sync, its own sign-in. It was dropped. Two ways to the same thing were one too many, and
> the old one was the one nobody maintained any more (`auth-roadmap.md`, decision 4).

### Groups from the directory ✅

*Since 2026-10-19.* An OTA group can get its members from groups in the directory. Example: the OTA
group `ki1` gets everyone from the LDAP group `cn=ki-team`. Through the group `ki1` they then get
their workspaces and permissions, and in connected applications like Open WebUI also their MCP
server (see [chapter 18](18-zentrale-anmeldung.md#groups-in-the-application-open-webui-)).

**Setting up**, in this order:

1. **Directory → Groups from the directory:** enter the base of the groups (e.g.
   `ou=groups,dc=company,dc=com`), leave the form on *Automatic*, **Save and fetch groups**.
   - OTA tries the three usual forms (`groupOfNames`, `groupOfUniqueNames`, `posixGroup`) and takes
     the first under which groups appear.
   - The answer names the groups found. A filter like `(cn=ki-*)` narrows the list.
2. **Users and groups → group → Members from the directory:** choose one or more directory groups.
   - Before saving, OTA shows who is added and who drops out.
   - When saving, OTA syncs right away.
3. **Directory → Sync:** choose the interval (off, 15 min, 1 h, 6 h, 1 day; default 1 h). **Sync
   now** runs immediately.

**By hand and from the directory at the same time.** Every membership knows where it comes from:

| | set by | removed by |
|---|---|---|
| **by hand** | administration (Users → Groups) | administration |
| **from the directory** | the sync or the sign-in | the sync or the sign-in |

- Whoever was added by hand stays in, even if the directory does not list them.
- What the directory grants cannot be taken away in OTA. The user editor shows it locked with
  "LDAP", the user list with "·L".
- The emergency account can still be kept in `admins` by hand.

**When a change in the directory takes effect:**

- **At the next sign-in to OTA, immediately.** Keycloak reads the groups live from the directory for
  this (`cachePolicy: NO_CACHE`, which OTA sets itself during setup).
- **At the sync**, also for everyone who is not signing in right now. Their groups go to Keycloak
  right away, so that connected applications see them at the next sign-in there.
- **A running session in a third-party application** does not end because of it. Only the
  application itself can do that.

**Whoever is missing from the directory** is **disabled, never deleted** in OTA at the sync. Their
home and their workspaces stay. If a sync would disable more than half of all directory accounts,
it stops and reports that. That is what a wrong filter or a half-reachable directory looks like,
and without this brake half the staff would be locked out.

**A directory group grants nothing by itself.** Keycloak keeps them as roles of a separate client
`ota-verzeichnis`, not as groups. That is why they are not in the token under `groups`. An LDAP
group named `admins` makes nobody an OTA admin as long as it is not explicitly linked to the OTA
group `admins`. The test directory contains exactly such a group, and the test suite insists that it
achieves nothing.

**Accounts without a group** sign in and see an empty dashboard with a note. You set the text under
**Directory → Accounts without a group**. In the user list they appear with "no group", and the
switch **Only accounts without a group** shows only them.

> **Until 2026-10-19** OTA took over the groups from the token at every sign-in. Now OTA computes
> them itself: those assigned by hand from its own database, the rest from the directory.
> Afterwards OTA writes the result to Keycloak. Whoever moves accounts into `/ota/…` groups in
> Keycloak itself no longer changes anything in OTA that way.

### Linking a domain account to an existing account ✅

An example: someone has an OTA account with workspaces and now signs in with their domain account
from AD or LDAP. OTA does not know this domain account yet and creates a **new, empty account** for
it. This is how the linking works:

1. The person signs in with the domain account, sees an empty dashboard and tells administration.
2. Under **Users and groups** you open their **old** account. Under **Link domain account** you
   search by name, username or email. The search only shows accounts from the directory. If someone
   has already signed in, the account from that sign-in is shown.
3. With **Link**, only the old account exists afterwards. It is named as in the directory and only
   signs in through the domain from then on.

What comes along: sessions and root workspaces, home, own shelf, groups and quotas. All of that is
attached to the account's ID, not its name.

What changes:

- **The local password and OTA's second factor go away.** Otherwise a second way in would remain,
  bypassing Keycloak and a lock in the directory.
- **The account from the first domain sign-in is removed.** If a session is still running in it,
  nothing is touched; end it first. Its home stays on disk.
- **If OTA had created an account in Keycloak for the old account, it is disabled there, not
  deleted.** The domain account belongs to the directory and stays as it is.
- Signed-in sessions of the old account expire. The workspaces keep running.

The emergency account, your own account and an account that already signs in through the directory
cannot be linked. The audit log records `user.domaene_verknuepft` with the old and new name.

**Way back:** `POST /api/admin/identity/uebernahme/zuruecknehmen` with name and new password makes
the account local again. The domain account stays active; if it signs in again, it is rejected
because the name is already taken.

### The rule above everything

> **A local account is never signed in through the directory, and a directory entry can never take
> over a local account.**

Where a password is checked is decided by the account itself alone (`auth_provider`) — not by the
request and not by the directory. This value never changes by itself.

The attack this guards against is unspectacular and therefore easy to overlook: whoever may create
an entry in the directory creates one with the name of the first administrator and signs in as them
with their own password. Without this rule, that works.

The test directory (`scripts/ldap-test-server.sh`) therefore deliberately contains an entry with the
name of an existing local account and a different password. The check consists of it **not**
getting in — neither at OTA nor at Keycloak.

### Trying it yourself

```bash
scripts/ldap-test-server.sh start     # OpenLDAP with four entries
scripts/test-ldap.sh                  # the whole suite, from connecting to outage
scripts/test-verzeichnis.sh           # groups, sync, access to applications
scripts/ldap-test-server.sh stop
```

The test server is **not** part of the stack: a directory service that starts with `make up` would
be an invitation to run production against it.

### What is not coming

**Kerberos and network drives** (`sec=krb5`, `k5start`, UID/GID from the directory) were **dropped
on 2026-09-03**. An LDAP server is not enough for that — it would need a real AD with KDC and file
servers, and without one none of it could be honestly tested. Whoever needs a network drive in the
workspace connects it there themselves (way 3 below).

**Password pass-through stays out.** It would be the shortest way to mounted drives and the only one
where OTA would have to keep a person's sign-in password (`plan.md` §17.9).

## Network drives in the workspace — dropped

**Dropped on 2026-09-03.** OTA does not pass credentials on to file servers and will not do so.
Whoever needs a network drive in the workspace connects it there themselves — that is way 3 in the
following table, and it needs nothing from OTA.

The trade-off stays here because it explains **why** way 4 stays out — this decision applies
regardless of whether Kerberos is ever built. Four ways, ordered by cleanliness:

| Way | What happens | Assessment |
|---|---|---|
| **1 · Kerberos SSO with delegation** | The browser signs in via Negotiate, OTA fetches a ticket for the file server via constrained delegation | Cleanest solution. **A password never reaches OTA.** Requires SPNs and configured delegation |
| **2 · Kerberos ticket injection** | OTA checks against AD, fetches a ticket in the process and places it in the container. Mount via `sec=krb5` | **Standard way.** No password in the container, the ticket expires after ~10 h |
| **3 · User connects themselves** | A button in the container, password entry there | **Always available.** Zero risk for the platform |
| **4 · Password pass-through** | OTA keeps the password for the duration of the session | **Off by default.** Turns OTA into a password store |

**Way 4 is deliberately not the default.** It is convenient, but it enlarges the blast radius
considerably: whoever compromises OTA gets passwords instead of just sessions. Whoever wants to turn
it on sees an unmistakable notice in the admin UI.

**If anyone ever thinks about it again, regardless of the way:**
- Never credentials as an environment variable — readable via `docker inspect` and visible in logs
- Never into the golden image and never into the persistent profile
- Storage in a `tmpfs` file with `0600` that never goes to disk
- So that file permissions on the shares match, the UID/GID is taken from the directory

## Offboarding

When someone leaves: disable the account, end sessions, archive the profile, then delete. Profiles
contain personal data (SSH keys, browser history) and are subject to the GDPR.

## Audit log

Records sign-ins, session start and end, and all administrative changes — **no content**. Retention
configurable, default 90 days, CSV export.

Session recording and keystroke logging are **deliberately not implemented**. If wanted later:
clarify co-determination and purpose limitation first.
