# 1 · Overview — what OTA is

## The workspace is the core

OTA gives every user **their own, persistent Linux workspace** in the browser. Their tools are
installed in it — VS Code, JetBrains, VSCodium, opencode, a terminal — and each one can be brought
into the browser on its own, filling the window.

What matters is what they share: **one home.** The same project directories, the same SSH key, the
same Git configuration, the same clipboard.

```
Workspace of bmetallica
  ├─ Visual Studio Code   ← running
  ├─ IntelliJ IDEA CE     ← running
  ├─ VSCodium             ← not started, costs nothing
  ├─ opencode
  └─ Terminal
       all on  /home/bmetallica
```

## The difference from the app catalog model

Other platforms give each *application* its own container. VS Code here, IntelliJ there — and the
same repository clone lies around three times, with three keyrings and three configurations.

OTA turns that around: **one machine per person, many tools inside it.**

From that follows:

| | |
|---|---|
| **Preconfiguration** | Admins build the workspace as a golden image — preset extensions, finished settings, company certificates. Versioned, with rollback |
| **Identity** | One user, one container, one identity — one sign-in for everything they start |
| **Resources** | The quota belongs to the person, not the tool. User A gets 4 cores, user B one |
| **Network** | Every workspace sits in its own network. To the internet yes — to the company network, a colleague's session or the host only if someone explicitly allows it → [chapter 23](23-netz.md) |

## Single applications as a feature

Alongside, OTA can start **an application as its own throwaway container**. That is deliberately an
add-on, not a second foundation. It is worth it for:

- Tools you need **rarely and in isolation** — GIMP, LibreOffice, a throwaway browser
- **Migration**: what runs in Kasm today also runs in OTA on day one
- The **existing ecosystem**: the official Kasm registry alone lists 86 ready-made workspaces
  → [chapter 9](09-kasm-images-und-registries.md)

## Who sees what

| Role | View |
|---|---|
| **User** (`users`) | Own workspace, assigned apps, own settings. Nothing else |
| **Administrator** (`admins`) | In addition: workspaces, golden images, users, groups, all sessions, registries, audit log |

The separation is enforced on the server at every endpoint, not just in the menu.

## Technical foundation

- **Docker** on Debian, no Kubernetes needed
- **Traefik** as ingress with TLS — mandatory, not optional: without HTTPS the clipboard does not
  work in the browser ([chapter 4](04-zwischenablage.md))
- **Selkies 2.0** as the streaming engine (H.264 over WebSockets, from OTA's own fork), one display per application. **KasmVNC**
  remains for Kasm images and can be chosen per workspace
  ([chapter 20](20-selkies-versuch.md))
- **Its own network per workspace** behind a router that filters everything
  ([chapter 23](23-netz.md))
- **PostgreSQL** for users, templates, sessions and audit
