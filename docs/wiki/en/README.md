# OpenTerminalApps — Manual

[Deutsch](../README.md) · **English**

This manual is delivered inside the program itself under **Help**. It describes how to use,
administer and operate OTA.

Every chapter also exists in German, in [`docs/wiki/`](../README.md) under the same file name. The
program shows the version in the interface language; whoever changes a chapter changes both —
`scripts/i18n-pruefen.py` compares the structure. File names and some anchors stay German, because
renaming them would break every link that already exists.

Which chapters someone sees there depends on their permissions: users get the overview, workspace,
clipboard and licences; administration and operations are reserved for administrators. This split
is defined in `api/ota/routers/help.py` — whoever adds a chapter registers it there.

## Markers

Every section carries a status. The manual deliberately also describes what is planned, so that
configuration decisions can be made with foresight — but it always says what already works today.

| Mark | Meaning |
|---|---|
| ✅ | available and tested |
| 🔨 | planned, with a milestone from the [roadmap](../../../roadmap.md) |
| ⚠️ | decision open, see `plan.md` §17 |

## Contents

**Basics**
1. [Overview — what OTA is](01-ueberblick.md)
2. [First steps — installation and start](02-erste-schritte.md)

**For users**
3. [The workspace](03-arbeitsplatz.md)
4. [Clipboard, files and sound](04-zwischenablage.md)

**For administrators**
5. [Managing workspaces](05-workspaces-verwalten.md)
6. [Resources and allocation per user](06-ressourcen-und-zuteilung.md)
7. [Golden images](07-golden-images.md)
8. [Users, groups and permissions](08-nutzer-und-gruppen.md)
9. [Connecting Kasm images and registries](09-kasm-images-und-registries.md)
16. [Managing images](16-images-verwalten.md)
17. [Shelves and start script](17-ablage-und-startskript.md)
18. [Central sign-in (Keycloak)](18-zentrale-anmeldung.md)
19. [The own base image](19-eigenes-basisimage.md)
20. [Selkies — the streaming path](20-selkies-versuch.md)
21. [Operating behind a corporate proxy](21-firmenproxy.md)
22. [Your own brand — name, colour, logo](22-marke.md)
23. [The workspaces' network](23-netz.md)
25. [Root workspace — root and Docker in the container](25-root-arbeitsplatz.md)

**Operations**
10. [Certificates and HTTPS](10-zertifikate-und-https.md)
11. [Operations and updates](11-betrieb.md)
12. [Troubleshooting](12-fehlersuche.md)
13. [Licences](13-lizenzen.md)
14. [Backup and restore](14-sicherung.md)
15. [Taking over a profile from Kasm](15-migration-aus-kasm.md)
24. [Operating behind a firewall with NAT](24-hinter-nat.md)
26. [The own package repository](26-paketquellen.md)
27. [OTA Git (Forgejo)](27-git.md)

The numbers are the order in which the chapters were written, not the order in which you read them
— that is why 16 to 23 sit between 9 and 10, and 24 and 26 are under operations. Renumbering would
break every reference that already exists somewhere.

## Where to find what

This manual explains **usage and operations**. The reasoning behind the decisions — why an engine
was chosen, what the data model looks like, which alternatives were rejected — is in
[`plan.md`](../../../plan.md) (German). The schedule is in [`roadmap.md`](../../../roadmap.md).

For the few decisions that are expensive to undo and will raise the question "why, actually?" in a
year, there are separate entries in [`docs/adr/`](../../adr/README.md) — each with the alternatives
that would not have held.
