# 38 · opencode: the AI assistant in the terminal ✅

*For administrators. Since 2026-11-02.*

[opencode](https://opencode.ai) (MIT) is an AI assistant for the terminal: it reads and changes
code, runs commands and works in sessions that can be continued later. OTA brings it into every
entitled workspace and connects it to **your own AI server**, the same one IDE-AI uses
([chapter 28](28-ide-ai.md)).

What OTA takes care of:

- **Installation**: OTA delivers the package `ota-opencode` from its own package source. At every
  start and resume it lifts the workspace to the pinned version, even without a way to the
  internet. opencode's own self-update is off.
- **Configuration**: OTA writes opencode's **managed configuration**. It holds the AI server, the
  models, the default model, the prompt addition and the MCP servers of the extensions.
- **Prompt addition**: a text that goes along with every request to the model, globally and per
  group.
- **Extensions**: whatever an extension delivers for opencode comes along. One example is the
  memory ([chapter 39](39-erweiterungen.md)).

## Turning it on

Under **Settings → opencode**:

1. Under **IDE-AI** the AI server and at least one model must be entered. opencode uses the same,
   with context window and response length. IDE-AI itself does not have to be on for this.
2. If needed, choose the **default model** and the **small model**. The small model produces titles
   and summaries; a fast model without thinking saves waiting time there.
3. If needed, enter an **addition to the system prompt** and choose the groups under **Who may**.
4. Flip the **opencode** switch.

It applies from the **next start or resume** of a workspace. While opencode or IDE-AI is on, the
firewall allows the AI server for all workspaces.

`make update` builds the package by itself as soon as the version is missing from the package
source. By hand it is `scripts/build-opencode-deb.sh --hochladen`. The version is set in
`packaging/ota-opencode/quellen`.

## The settings

| Setting | What it does |
|---|---|
| Default model | The model opencode starts with. Empty means: the default model from IDE-AI. Whoever set one in `~/.config/opencode` keeps theirs |
| Small model | For titles and summaries (`small_model`). Empty means: like the default model |
| Addition to the system prompt | Goes along with every request, for everyone. Placeholders: `{anzeigename}`, `{nutzer}`, `{vorlage}`, `{datum}` |
| Per group | Additional texts for members of certain groups, such as a style guide. Whoever is in several groups gets all of them |
| Additional configuration | JSON that OTA merges into the managed configuration, taking precedence. Meant for everything the interface does not know (see below). OTA sets `mcp`, `plugin` and `instructions` itself |
| Who may | Without a group everyone may. Otherwise only members of these groups; administrators always |
| Preview | Shows what a particular person would get: the prompt addition with an estimated length and the managed configuration. Includes changes not yet saved |

**Length of the prompt addition:** the addition costs context with every request. From about 2,000
tokens the preview warns, because with local models of 32 k context or less it matters.

**A default, not a security boundary:** a project can bring its own instructions (`AGENTS.md` in
the repository), and the model can disregard instructions. What really must not happen is governed
by the firewall and the permissions, not by the prompt.

Every change to the prompt addition and the additional configuration goes into the audit log with
old and new text.

### Additional configuration: example

For a llama.cpp server with a thinking main model and a variant without thinking for titles and
summaries, it looks like this, for example:

```json
{
  "provider": { "ota": { "models": {
    "Hauptmodell": { "reasoning": true, "modalities": { "input": ["text", "image"], "output": ["text"] } },
    "Hauptmodell-nothink": { "options": { "chat_template_kwargs": { "enable_thinking": false } } }
  } } },
  "agent": {
    "compaction": { "model": "ota/Hauptmodell-nothink" },
    "title": { "model": "ota/Hauptmodell-nothink" }
  }
}
```

The provider is always called `ota` in opencode, so a model is `ota/<model>`. They must be models
selected under IDE-AI.

## In the workspace

At every start and resume OTA writes as root:

| File | Content |
|---|---|
| `/etc/opencode/opencode.jsonc` | the managed configuration. The first line is OTA's mark |
| `/etc/opencode/ota-anweisungen.md` | the prompt addition: global, the person's groups, the snippets of the extensions |
| `/etc/opencode/ota-ki-schluessel` | the API key of the AI server, only if one is entered |
| `/etc/ota/erweiterungen/<slug>/token` | the token per extension, see [chapter 39](39-erweiterungen.md) |
| `/etc/hosts` | `ota-erweiterungen` points to Traefik in the workspace's own session network |

**Precedence:** opencode reads `/etc/opencode` with the highest precedence. Whatever a person sets
in `~/.config/opencode/opencode.json` is added: own providers, own MCP servers, own plugins, own
permissions. The keys OTA sets cannot be overridden there. One exception is the default model: if
someone set one themselves, OTA does not prescribe one.

**A managed configuration of the image**, that is `/etc/opencode/opencode.json` without OTA's mark,
is left alone. OTA then writes none of its own and reports it in the agent's log.

**Turning it off** or losing the entitlement removes OTA's files at the next start. The package
stays; opencode then runs only with the person's own configuration.

## Whoever already installed opencode themselves

Root workspaces in particular may already have opencode installed by their users, with the install
script (`~/.opencode/bin`), with npm (`/usr/local/bin`) or with Bun. At the next start or resume OTA
**takes over** this installation:

- The file is renamed to `opencode.vor-ota`; nothing is deleted.
- In its place goes a small script that starts OTA's version (`/usr/bin/opencode`). So the tested
  version always runs, whatever comes first in the `PATH`.
- Left unchanged: the person's own configuration in `~/.config/opencode`, the previous sessions in
  `~/.local/share/opencode` and their own default model.
- If someone reinstalls later, that only replaces the script. At the next start OTA takes over
  again.

**Why this is necessary:** the plugin `ota-sitzung` (see below) depends on opencode's plugin
interface, and that changes between versions. A version other than the pinned one could silently
break the extensions.

## The plugin ota-sitzung

The package ships a small plugin (`/usr/share/ota-opencode/plugins/ota-sitzung`). OTA turns it on
only when an extension needs it. Before every call of one of this extension's tools it fills in the
**opencode session**:

- Child sessions (subagents) and forks are mapped to their root session, by the same rule opencode
  uses internally.
- Title and directory of the session come along, only for display.
- It hides these fields from the model; whatever the model enters there is overwritten.
- It sends nothing anywhere by itself.

That way the memory, for example, reliably knows which session an entry belongs to, without the
model having to remember an identifier.

## A new version of opencode

1. In `packaging/ota-opencode/quellen` change version, address and checksum, and set `revision` to
   1.
2. `scripts/build-opencode-deb.sh --hochladen`
3. `scripts/test-opencode.sh` checks, among other things, the plugin with the new version, using a
   fake model in the workspace.

## When something does not work

| What | Cause |
|---|---|
| opencode missing in the workspace | The package installs in the background, a minute or two at the first start. Without `dpkg` in the image it does not work; then install by hand, the configuration still applies |
| OTA's models are missing | Check `/etc/opencode/opencode.jsonc`. If it is missing, the agent's log reports a managed configuration of the image (`gehört dem Image`) |
| `opencode` starts an old version | The takeover runs at start and resume. Until then `/usr/bin/opencode` helps |
| Errors with tool calls | The AI server must support tool calls: vLLM `--enable-auto-tool-choice --tool-call-parser …`, llama.cpp `--jinja` |
| An own model from `~/.config/opencode` is ignored | Only the default model is left to the person; OTA sets the model list of the provider `ota`. An own provider with another name works |

Test: `scripts/test-opencode.sh`, together with the memory from [chapter 39](39-erweiterungen.md).
