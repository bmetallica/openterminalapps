# 33 · Developing: Git and AI in the editor

*For users.* What OTA prepares for developers once the administrators have switched it on. Whether
it is on for you, you see from a **Git** tile under "Other applications" and from the AI assistant
in your editor.

## Git (OTA-Git) ✅

OTA brings its own Git server ([Forgejo](https://forgejo.org)).

**In the browser:** the **Git** tile opens it; you are signed in with your OTA account. There you
create repositories. New ones are private.

**In the workspace** Git is ready to use, at every start and every resume:

```bash
git clone https://git.firma.de/your-name/project.git    # no password prompt
git push
```

- Name and e-mail for commits come from OTA. What you set yourself in `~/.gitconfig` takes precedence.
- The access applies **only to this workspace** and ends with it. At the next start there is a new
  one. You do not need to keep any of it.
- Other Git servers (GitHub, a company server) work alongside as usual, with your own credentials
  or SSH keys.

**SSH instead of HTTPS:** you enter your public key in Forgejo in the browser (Settings → SSH
keys). After that `git clone ssh://git@git.firma.de:2222/…` works, but **only from workspaces**.
From your own computer, use HTTPS.

The exact name of the server is on the Git tile and in the address bar when you open it.

## The AI assistant in the editor (IDE-AI) ✅

**VS Code**, **VSCodium** and the **JetBrains IDEs** (IntelliJ IDEA, PyCharm …) contain
[Continue](https://continue.dev), connected to your company's AI server. Your data goes to that
server, not to a service on the internet.

What it can do:
- **Chat** about your code, with a choice of model
- **Edit:** select code and say what should change
- **Agent mode:** the model reads and changes files and suggests commands, each time with your
  confirmation

**In VS Code** Continue sits on the right in the sidebar and opens by itself the first time you open
a folder. If you have closed it, **Ctrl+Alt+B** brings it back. The built-in Copilot is switched off.

**In JetBrains IDEs** you find Continue as a tool window at the edge.

At a workspace's first start it can take a minute or two until the assistant is there: OTA installs
it in the background so the start does not wait. If the editor is already open, restart it once
afterwards.

**Your own settings:** OTA rewrites the configuration `~/.continue/config.yaml` at every start. If
you want to maintain it yourself, delete the first line (`# Verwaltet von OTA …`). After that OTA
no longer touches it. If you delete the whole file, OTA's version comes back at the next start.

### Continue is gone or behaves differently ✅

First check whether only the icon is missing: in JetBrains IDEs **View → Tool Windows → Continue**,
in VS Code **Ctrl+Alt+B**. New plugins like to push an icon into the **⋯** at the edge.

If Continue really is missing, something has usually displaced our version: an update from the
Marketplace, a disabled plugin or a configuration of your own. Then, on the dashboard, in the tile of
the running workspace: **⋯ → Set up AI tools again**. Close PyCharm and VSCodium first. It takes up
to a minute and

- removes a Continue copy from the Marketplace (JetBrains and VS Code/VSCodium),
- switches Continue back on if it was disabled,
- puts your own `~/.continue/config.yaml` aside as `config.yaml.vor-ota-<date>` and writes OTA's,
- installs OTA's packages once more.

Then start the editor. Other plugins and extensions stay as they are. The entry is only there if
IDE-AI is switched on for you.

**Please do not accept an update for Continue from the Marketplace** if the editor offers one. OTA's
version is set up for your AI server and adapted to the IDE.

## Docker

Docker is only available in **root workspaces** ([chapter 32](32-root-arbeitsplatz-nutzen.md#docker-)).
