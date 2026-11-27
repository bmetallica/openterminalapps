# 42 · Data protection: the page for data protection officers ✅

*Since 2026-11-27.* This chapter is written for data protection officers and assumes no IT
knowledge. For administrators, the end of the chapter explains how to set up the group.

## What it is about

Data protection officers must be able to check what data about people is collected, who may
access it and who actually did. They need no administrative rights for that. They should not
have them either: they check the administration and are not part of it.

OTA therefore has its own group **datenschutz** and the menu item **Data protection** on the left
(symbol ⚖). Members of the group see everything needed for the review there and cannot change
anything in the system. There are only two exceptions:

- creating an **access report under Art. 15 GDPR**;
- editing the **privacy notice** everyone can read under "GDPR".

## The five areas of the page

### Overview

Every processing OTA knows about, as a card: what it means, whether it is switched on and how
long the data is kept. These include:

| Card | What is behind it |
|---|---|
| Audit log | who did what in administration and when, sign-ins, workspace starts; two retention periods |
| Copy of the audit log on a central server | whether a second copy independent of OTA exists (syslog) |
| Statistics on AI usage | requests to the AI per person, without content, with retention periods |
| Connected AI programs | e.g. Open WebUI, which passes names or e-mail addresses to OTA |
| Protecting the AI against attacks | counts suspicious texts, without reference to people |
| AI security case reports | short excerpts of flagged texts, without a person, with a retention period |
| Check for passwords in program code | counts findings in OTA Git, without reference to people |
| Files of deleted accounts | whether and when they are removed |
| Backups | how long copies are kept; deleted data is still in them until then |
| Privacy notice | own text or default text, when and by whom last changed |
| Extensions | add-on services like a memory for the AI assistant, and for which groups |

At the top, **Please note** lists open points, for example:

- "The privacy notice is still the supplied default text";
- "The audit log exists only inside OTA itself";
- "Files of deleted accounts are not removed automatically".

This list is a good starting point for the record of processing activities.

### Who may do what

Which groups have far-reaching permissions, what these permissions mean in words, and who the
members are. At the top: how many active accounts hold each permission. Meant are permissions
like "Full access to everything", "Run commands in other people's workspaces and read all files
there" or "Create, change and lock accounts". Permissions unrelated to data protection, such as
building images, are left out.

Groups without such a permission, for example the group of all users, do not appear.

### Access

The audit log entries that matter for data protection, in four kinds:

| Kind | Examples |
|---|---|
| Viewing other people's data | attached to a screen; terminal opened in someone else's workspace; a person's AI usage viewed; case report opened; access report created; audit log exported |
| Accounts locked or deleted | account locked, deleted; an account's files removed |
| Permissions granted | groups created or changed; groups assigned from the directory |
| Data protection settings | statistics switched on or off; retention periods changed; privacy notice changed |

If a **reason** was given, it is shown in the "Details" column, together with the account
concerned. This applies, for example, to viewing a person's AI usage or opening a case report.
Clicking a row shows everything stored.

This page deliberately does not show the **content** of case reports or the AI usage of
individual people. For the review it is enough to see who opened them and with what reason.

### Audit log

The complete audit log, with these filters:

- period;
- who acted;
- **person concerned:** finds everything the person did and everything that concerned their
  account.

100 entries per page. **Download as a table (CSV)** delivers the filtered entries, at most
50,000, as a file for Excel.

### Access request

The access report under Art. 15 GDPR:

1. Search for the person by name, account or e-mail address.
2. Enter a **reason** of at least ten characters, for example the file reference and date of
   the request.
3. **Create and download the access report.**

The result is a ZIP file with everything OTA has stored about the person:

- master data and groups;
- audit log entries;
- working times at workspaces;
- AI usage;
- backups;
- OTA Git;
- a list of their own files, without their content.

Passwords and keys are not included. The file `liesmich.txt` inside explains every part.

**Before handing it out**, weigh whether administrators' names must be redacted. The audit log in
the report names them too (Art. 15(4) GDPR).

The reason is mandatory. Since 2026-11-27 this also applies to administrators (*Users → account
→ Create access report*).

## What is recorded in the audit log itself

The work of data protection officers is traceable too, for administrators as for other data
protection officers:

| Entry | When |
|---|---|
| `user.auskunft` | access report created, with reason |
| `datenschutz.protokoll_exportiert` | audit log downloaded as CSV, with the filters |
| `datenschutz.protokoll_person` | audit log filtered by a person (once per ten minutes and person) |
| `dsgvo.hinweis_geaendert` | privacy notice changed |

Merely viewing the overview, permissions and access is not recorded. It concerns no specific
person.

## Manual

Under **Help**, group members see, besides the chapters for everyone, the chapters describing
what OTA records about people:

- 08 · Users and groups;
- 11 · Operations (audit log and retention);
- 27 · OTA Git;
- 28 · IDE AI and AI usage;
- 39 · Extensions;
- 41 · AI security.

## For administrators: setting it up

1. OTA creates the group **datenschutz** itself at start-up, with exactly one permission:
   `datenschutz.pruefen`. It is built in. OTA restores its permissions at every start if
   someone changed them.
2. Assign the data protection officer's account to the group **datenschutz** under *Users*.
   With sign-in through a directory (LDAP, Active Directory), a group of the same name there
   is enough, see [chapter 08](08-nutzer-und-gruppen.md).
3. The account needs **no** other group apart from the one for all users. In particular not
   `admins`: otherwise whoever is in administration checks themselves.

The permission `datenschutz.pruefen` can also be given to a group of your own. Administrators
see the page anyway, because `admin` includes all permissions.

**What the group may not do:** change settings, manage accounts or groups, attach to
workspaces, open terminals, see the AI usage of individual people, open case reports. The test
series `scripts/test-datenschutz.sh` checks this.

## Technical

- API: `/api/datenschutz/lage`, `/rechte`, `/protokoll`, `/protokoll.csv`, `/personen`,
  `/auskunft/{id}` (`api/ota/datenschutz.py`, `api/ota/routers/datenschutz.py`).
- UI: `web/src/screens/Datenschutz.tsx`.
- The entries fall under the long retention period of the audit log ([chapter 11](11-betrieb.md)).
