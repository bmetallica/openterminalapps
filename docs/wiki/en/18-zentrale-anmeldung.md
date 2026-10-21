# 18 · Central sign-in (Keycloak)

*For administrators.* ✅ Sign-in, directory, third-party applications, emergency access

Since 2026-08-28 OTA is no longer its own identity provider. It is the **portal** in front of a
central Keycloak — and its administrator. The background, the trade-offs and all decisions are in
[`auth-roadmap.md`](../../../auth-roadmap.md); this chapter explains how to work with it.

## Three responsibilities, cleanly separated

| | Question | Responsible |
|---|---|---|
| **Keycloak** | Who are you? | Sign-in, identity, SSO, AD/LDAP, second step (passkey or one-time password), sessions |
| **OTA** | Which applications may you **see and enter**? | Catalog, access per group, workspaces |
| **The application** | What may you do **inside** it? | Open WebUI permissions, Grafana roles, … |

The third row is the one most easily overlooked: **OTA does not rebuild the permission model of
third-party applications.** It decides whether someone sees the tile and whether the door opens.

## How someone signs in

```
Browser ──► OTA ──► Keycloak ──► OTA sets its own cookie ──► workspace
```

Keycloak lives under **`/auth` of the same address** as OTA. That is not a cosmetic flaw but a
prerequisite: a desktop shortcut opens a window without an address bar, and a jump to a foreign
origin would leave its scope. This way the sign-in stays in the same window.

**Behind the front door, OTA's cookie applies.** Traefik's `forwardAuth` stands in front of every
session path, including the WebSocket handshake — and an upgrade cannot be redirected to Keycloak.

## The emergency access

**`https://<host>:8443/notfall`** — a local administrator account that works without Keycloak.

`make admin` creates it during setup (`notfall`) and prints its password **once**. It is the way in
when Keycloak does not answer or a directory configuration blocks the sign-in. Without it an
installation could no longer be entered after such a failure.

There is deliberately exactly **one**, under its own address, and every sign-in through it is in the
audit log. The migration (below) leaves it untouched.

## The entrances ✅

*Since 2026-10-08.* There are two entrances, and only two:

| Address | For whom | What happens |
|---|---|---|
| **`/`** (any address) | everyone | on to the central sign-in (Keycloak) |
| **`/notfall`** | the emergency account | local form, bypassing Keycloak — for when it fails |

**`/login`** is no longer a third entrance but a transition:

- If there are **no local accounts** other than the emergency account any more, `/login` redirects
  to the central sign-in immediately.
- If there still are some (legacy accounts from before Keycloak), it shows the form. If such an
  account signs in there, it **moves over** (below) and is redirected to the central sign-in.
- Whoever enters the name of a central sign-in account there lands at Keycloak — with the name
  already filled in.
- With `?fehler=…` (when something went wrong at Keycloak) the page stays and says what happened.
  Otherwise the browser would run into a loop.

Until 2026-10-08 `/login` showed everyone a local form. An account created in OTA got in **only**
there — bypassing the central sign-in and its second step. Found on the production installation.

## Creating and maintaining accounts ✅

*Since 2026-10-08.* **Administration → Users → create** creates the account **in Keycloak**:

- **Administration assigns the initial password.** Whether it must be changed at the first sign-in
  as well (switch "Change at first sign-in", default: yes). It must satisfy Keycloak's password
  policy; a refusal comes back with Keycloak's reason.
- **Name, email, groups, active/locked** and the role for the second step are kept in sync in
  Keycloak by OTA on every change. The groups are there under `/ota/<group>`, so that connected
  applications see them in the token. **OTA is authoritative**: since 2026-10-19 the groups are no
  longer taken from the token at sign-in but computed from OTA and the directory
  ([chapter 08](08-nutzer-und-gruppen.md#groups-from-the-directory-)).
- **A new password** from administration applies in Keycloak, again optionally to be changed at the
  next sign-in.
- **Reset second factor** removes one-time password and passkeys in Keycloak.
- **Delete** removes the account from OTA and **locks** it in Keycloak; it is never deleted there (a
  Keycloak may also belong to other applications). Without the lock, the next sign-in would simply
  create the account in OTA again. If the same name is created again later, OTA links the locked
  account and unlocks it.
- **An account from the directory** (AD/LDAP via federation) belongs to the directory: name, address
  and password come from there. Administration does not set a password for it (409); groups and
  active/locked still work.

**Local accounts** are no longer created through administration. Only the emergency account is local
(`make admin`, Settings → Emergency account).

## My account with the central sign-in ✅

*Since 2026-10-08.* The password and second factor of a central sign-in account live in Keycloak,
and that is where they are changed. **My account** leads there and brings you back (Keycloak's
"Application-Initiated Actions"): OTA sees no password, Keycloak's password policy and second step
apply as at sign-in.

| | Central sign-in account | from the directory | Emergency account |
|---|---|---|---|
| Change password | button → Keycloak | **in the directory**, as usual in the company | form in OTA |
| One-time password | button → Keycloak (`CONFIGURE_TOTP`) | button → Keycloak | OTA's own |
| Passkey | button → Keycloak (`webauthn-register`) | button → Keycloak | — |
| View, remove | Keycloak's account page (linked) | same | in OTA |

The local paths (`/api/auth/password`, `/api/auth/totp/…`) refuse such an account (409) — set there,
it would not take effect at sign-in and would open a way around it.

## Connecting an Active Directory

**Settings → Directory in Keycloak.**

Enter address, base, service account, **Test connection**, save, **Sync now**. OTA writes the
connection to Keycloak through the admin API; nobody has to open the Keycloak console.

```
Address          ldaps://dc01.company.local:636
Base             OU=Users,DC=company,DC=local
Service account  CN=svc-keycloak,OU=Services,DC=company,DC=local
```

It is created **read-only** (`editMode: READ_ONLY`): OTA never writes back to the directory. The
service account's password only goes in — leaving it empty means "do not touch", not "delete".

### ldaps and the directory's CA ✅

`ldaps://…:636` is the way; the interface does not offer StartTLS on 389. Keycloak checks the
directory's certificate and by default only knows the public CAs of the Java runtime. If the
certificate comes from the company PKI, its CA belongs as a PEM file in
**`deploy/keycloak-truststore/`**, followed by `docker restart ota-keycloak`. The directory has been
mounted to `/opt/keycloak/conf/truststores` since 2026-09-25; before that such a directory could not
be connected encrypted at all.

**Test connection** also says *why* it fails since then — Keycloak reports the reason, OTA just never
read it:

| Message | Means |
|---|---|
| "the encrypted connection fails" | CA missing from the truststore, or the certificate does not match the address (`ldaps://<IP>` needs the IP in the certificate) |
| "cannot resolve name …" | the host's DNS |
| "No directory answers on the port" | wrong port — `ldaps://` belongs to 636 |
| "unreachable" | firewall, routing, or the directory is not running |

If the directory sits beyond a firewall: [chapter 24](24-hinter-nat.md).

> **Terminology trap.** In Keycloak this is a *user federation* and **not** an "identity provider" —
> that is what foreign OIDC and SAML providers are called there. Whoever searches in the wrong menu
> finds nothing.

A directory entry **cannot take over an existing account.** If there is a `bmetallica` in AD and one
already exists here, the import is refused. That is the attack the rule guards against: whoever may
create something in the directory would otherwise create an entry with the administrator's name.

## The password policy ✅

Since 2026-09-04 the realm requires at least **twelve characters**, and that the password is neither
the username nor the email address:

```
length(12) and notUsername(undefined) and notEmail(undefined)
```

The same lower limit has always applied in OTA's own sign-in. Without this line the **main path** was
weaker than the emergency access — without a policy Keycloak accepts any length, even one character.

It is set by `scripts/keycloak-init.sh`, on creation **and** for a realm that already exists. It can
be tightened via `OTA_KC_PASSWORTREGEL` in `deploy/.env`, followed by `make identity`. Existing
passwords stay valid until they are next changed — Keycloak checks the policy when setting, not
retroactively.

## The second step

It lives in Keycloak, no longer in OTA. What was a field on the group in OTA (`require_totp`) is a
sign-in flow with a condition there — and groups are no good as a condition, roles are. Therefore:

```
Realm role  zweiter-faktor  →  whoever carries it sets up a second factor at sign-in
```

OTA attaches the role to everyone whose group requires it. The sign-in flow is a **copy** of the
built-in one (`ota-browser`) — Keycloak does not allow changing built-in flows, and a copy can be
detached again with one move: set `browserFlow` back to `browser`.

### Passkey or one-time password ✅

Both work as a second factor. Whoever has registered a **passkey** — fingerprint, face recognition,
a security key — identifies with it; whoever has none gets the **one-time password** prompt as
before.

A passkey is registered in Keycloak's account management under *Signing in → Passkey*. The action
needed for it (`webauthn-register`) is enabled in the realm by default; in the browser OTA presents
itself as "OpenTerminalApps".

```
Condition: role zweiter-faktor              REQUIRED
├─ ota-passkey                             ALTERNATIVE
│    ├─ Condition: set up for the user      REQUIRED
│    └─ WebAuthn                             REQUIRED
└─ ota-einmalkennwort                      ALTERNATIVE
     └─ One-time password                    REQUIRED
```

> **Why two branches and not simply two alternatives side by side.**
>
> The obvious structure would be to set one-time password and passkey both to ALTERNATIVE: "pick
> one". Measured against this Keycloak on 2026-09-02: whoever carries the role and has set up **neither
> of the two yet** can then no longer get in at all — the sign-in ends with *"Invalid username or
> password"*. So not just a lockout, but one with a misleading message that nobody would trace back
> to the cause.
>
> A queued initial setup does not help either: queued actions run **after** the sign-in, and it
> never gets that far.
>
> With the two branches, someone without a passkey falls through the first condition and lands in
> the second branch, where the one-time password triggers its own setup if needed. There is thus no
> state in which nobody gets in any more — and that is exactly what `scripts/test-authz.sh` checks on
> every run.

Whoever has a passkey is no longer offered the one-time password. That is deliberate: two ways side
by side are two ways an attacker can try, and the weaker one wins.

## Connecting third-party applications

**Applications → Add application.** OTA creates the OIDC client in Keycloak and shows the
configuration to transfer.

Two locks secure this, and they secure against different things:

* The permission **`anwendungen.verwalten`**, separate from `templates.manage`. Whoever puts together
  workspaces does not incidentally create accesses through which identities flow outside.
* A **list of allowed destinations** under **Settings → Applications**. It is **empty** in the
  delivered state and then allows nothing — not everything. As long as it is empty, the web
  applications page shows a button leading there.

What is entered is an **origin**, i.e. scheme, host and port if needed, without a path: such as
`https://ai.company.com` or `http://192.168.66.225:3000`. An application's redirect address must
start with one of them. `http://` is allowed and is marked *unencrypted* in the list — the sign-in
code then goes over the wire in plain text. OTA does not accept wildcards (`*`). If a destination is
removed, applications pointing there stay, but can no longer be changed.

Why this is needed: in an OIDC client there is one line that decides everything.

```
Redirect URI    https://ai.company.com/oauth/oidc/callback
```

That is where Keycloak sends the code after sign-in. **Whoever sets it decides where the users'
identity flows.** In the audit log that looks like "added an application".

The client secret comes back **once** and afterwards only exists in Keycloak.

On the certificate — the point where the first connection reliably fails — see
[chapter 10](10-zertifikate-und-https.md).

### Who gets in ✅

*Since 2026-10-19.* An application's groups no longer only decide who **sees** its tile, but also
who may **sign in** there. Keycloak checks this itself, even if someone calls the application's
address directly or is already signed in to OTA.

| Access | who gets in |
|---|---|
| Groups chosen | only their members |
| **All signed-in users** | every central sign-in account |
| nothing chosen | **nobody**; the interface warns about it |

Whoever has no access sees "No access to this application" at Keycloak. They stay signed in to OTA.

> **When updating to this version**, every existing application without a group gets "All signed-in
> users" once. Until then "no group" meant "everyone", and this way nothing breaks. Afterwards the
> strict rule applies.

**How it is built.**

- Every application has the role `zugang` (access) in Keycloak. OTA attaches it to the Keycloak
  groups `/ota/<group>` of the chosen groups.
- A **separate sign-in flow** per application (`ota-app <client> <fingerprint>`) rejects whoever
  lacks it. It is a copy of the realm's sign-in flow, with the check in **both** branches: after the
  form and after the existing SSO session. Only in the form branch, everyone already signed in to OTA
  would pass unchecked.
- The second step is copied along and applies there just as for OTA.
- If the realm's sign-in flow changes, for example through a new second factor, the fingerprint in
  the name no longer matches. At the next start of the API, OTA rebuilds the flows.
- "All signed-in users" needs no flow of its own. Then the ordinary one applies.

### Groups in the application (Open WebUI) ✅

A group in OTA arrives as a group in the application. That way something can be attached to it
there, such as an MCP server for the group `ki1`. The path:

```
LDAP group ki-team → OTA group ki1 → Keycloak /ota/ki1 → token "groups": ["ki1"] → Open WebUI group ki1
```

Open WebUI needs:

```
OAUTH_GROUP_CLAIM=groups
ENABLE_OAUTH_GROUP_MANAGEMENT=true
ENABLE_OAUTH_GROUP_CREATION=true
```

- The group is created in Open WebUI at the first sign-in of a member.
- There you assign it the MCP server, the models or the tool once.
- You never set the members by hand in Open WebUI. Open WebUI takes them from the token at every
  sign-in, and whatever was set there by hand would be gone next time.

**A peculiarity of Open WebUI** (measured with 0.12.3 on 2026-10-19): it only removes someone from a
group if the token names **at least one** group. An account that has no OTA group at all any more
keeps its old groups in Open WebUI and thus, for example, its MCP server.

With the access lock this does not happen: whoever signs in is in at least one group of the
application, and that is in the token. So for Open WebUI assign **one access group** (e.g.
`ki-alle`) and next to it the groups for the tools (`ki1`, `ki2`), **not** "All signed-in users".
Checked with a real instance:

- A member of the LDAP group ends up in `ki1` in Open WebUI.
- Whoever has no group of the application is already rejected by Keycloak.
- After revocation in LDAP and a sync, Open WebUI removes them from `ki1` at the next sign-in. Via
  `ki-alle` they still get in.

Whoever gets in without a group anyway ("for everyone") keeps their old groups in Open WebUI until an
admin removes them there.

### One clock for OTA and the applications ✅

*Since 2026-10-08.* Whoever is signed in to OTA gets into a connected application **without a sign-in
form** — as long as they are signed in to OTA, not just for half an hour.

Before, two clocks ran side by side: OTA's own session (Settings → *Sign out after inactivity*, about
eight hours) and Keycloak's SSO session (default 30 minutes without contact). After sign-in you only
work with OTA's cookie, Keycloak hears nothing any more. After half an hour you were still signed in
to OTA, but Open WebUI showed the form.

Now:

* **Same timeout.** OTA sets Keycloak's idle timeout to its own — at start and on every change in the
  settings. The upper limit of an SSO session is a week, because OTA itself knows none; Keycloak's
  default of ten hours would have thrown out everyone who works longer at a stretch.
* **Keeping alive.** As long as work is happening in OTA, OTA refreshes the Keycloak sign-in every
  five minutes. The refresh token for this lies as an httponly cookie in the browser (`ota_kcwach`,
  only for `/api`), not in the database — it belongs to this one sign-in on this device.
* **Ending together.** If Keycloak no longer knows the session — signed out elsewhere, ended in the
  console — the session in OTA ends at the next refresh as well. If Keycloak is just not answering
  right now, everything stays as it is.

Whoever is signed in via `/notfall` has no Keycloak session; there is no SSO for them either.

> **When refreshing, OTA talks to Keycloak internally** (`http://keycloak:8080`), but the browser
> signed in under the public address. Keycloak compares the issuer in the token with the address it
> is asked under when refreshing. OTA therefore passes the public address from the token along as
> `X-Forwarded-*` — the same headers Traefik sets for the browser.

## Taking over legacy accounts

**The easiest is for an account to move over by itself — at its next sign-in** (*since
2026-10-08*): if it signs in under `/login` with its local password, OTA creates it in Keycloak,
**with exactly this password**, deletes the local hash and redirects to the central sign-in. No
one-time password, no import of hashes — OTA knows the password at this moment anyway. If an account
of this name already exists in Keycloak, it is linked and its password is not touched. If that
account is **locked** there (usually because it was once deleted in OTA), nothing moves over: the
account keeps signing in locally until administration sorts it out — for instance by deleting the
local account and creating it again; that links the locked one and unlocks it with the assigned
password. If Keycloak does not answer, the account gets in locally and moves over next time.

For accounts that do not sign in for a long time, there is the run by hand:

**Settings → Migration.** It brings local accounts to Keycloak: name, email, groups and the role for
the second step come along, the password is **newly assigned once** and must be changed at the first
sign-in.

Why not take the existing hashes along: an import depends on matching parameters and, when in doubt,
fails **silently** — it is only noticed when someone cannot sign in.

Three properties that are not negotiable:

* **Without an emergency account the run does not start.** Whoever switches all accounts to a service
  that can fail needs a way back first.
* **The local hash goes away.** Leaving it would mean keeping a second way open — bypassing Keycloak
  and the second step.
* **There is a way back per account.** *Revert* makes a single account local again and disables it
  in Keycloak. A way back that has to be invented in an emergency is none.

Whoever has been migrated and tries to sign in under `/login` does not get a "wrong password" error
but a note where the right entrance is.

## The look of the sign-in form

It carries OTA's colours — the same surface, the same font, the same light primary button. The theme
lives under `deploy/keycloak-theme/ota` and is mounted as a directory; no build step is needed.

> **Whoever works on it must turn off the theme cache.** Keycloak reads a theme file once and keeps
> it — a restart does not clear that, and the browser may keep it for 30 days. You then change a
> file and see nothing.
>
> ```
> KEYCLOAK_THEME_CACHE=false
> KEYCLOAK_THEME_MAX_AGE=-1
> ```
>
> For operation set back to `true` and `2592000`.

### The form follows the theme

Whoever has set **light** in OTA also gets a light sign-in form. That works because Keycloak sits
behind the same ingress as OTA — so on the same origin, and thus the form reads the same
`localStorage` in which OTA stores the choice (`resources/js/gewand.js` in the theme).

Without that, someone with a light theme would get a dark sign-in form and then a light application.
That does not look like one installation but like two — and a sign-in page must never raise exactly
that doubt.

> **If Keycloak runs under its own name**, it is a foreign origin and the form stays with the dark
> theme. That is not a bug but the limit of `localStorage`; it is only noticed when someone has set
> light.

## The Keycloak console is reachable — deliberately

The bundled Keycloak sits behind Traefik under `/auth`, and that includes its **administration
interface** under `/auth/admin/`. Whoever reaches OTA therefore reaches it too.

**That is a decision, not carelessness.** OTA manages Keycloak from the inside — for everyday use
nobody has to go in there. But if something ever gets stuck that OTA's interface does not cover (a
sign-in flow, a federation certificate, a look at an account's sessions), the console is the only
way. Walling it off would mean locking yourself out when something breaks.

What depends on it, and what operations owe it:

* **The Keycloak administrator's password is thus as important as the host's.** It is in
  `deploy/.env` (`KEYCLOAK_ADMIN_PW`), is generated by `make setup` and should never appear anywhere
  a second time.
* **The second factor belongs on this account**, not only on the users'.
* **The brake against brute force is in place** — Keycloak locks for 15 minutes after five failed
  attempts, that applies at the console too.
* **This reasoning holds for an intranet.** As soon as OTA becomes reachable from the internet, it
  flips: then a restriction to known addresses belongs in front of `/auth/admin` (`ipAllowList` in
  Traefik, `deploy/traefik/dynamic/middlewares.yml`). The users' sign-in path is not affected — it
  runs via `/auth/realms/…`, and OTA's own access goes through the internal network anyway, not via
  Traefik.

## Using an existing Keycloak

Whoever already runs one sets in `deploy/.env`:

```
OTA_IDP_MODE=vorhanden
OTA_KEYCLOAK_URL=https://auth.company.com
OTA_KEYCLOAK_REALM=company
OTA_KEYCLOAK_SECRET=<secret of the client ota-manager>
```

There OTA is a **guest**: the realm belongs to someone else. It deletes no accounts (only disables),
only touches groups below `/ota`, and the directory connection probably already belongs to someone.
When connecting, OTA determines which permissions it has and only shows what really works — instead
of offering a button that ends in a 403.

The client `ota-manager` and the realm must be created there **beforehand**; `make identity` does not
touch a foreign Keycloak.
