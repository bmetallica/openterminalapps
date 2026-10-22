# 28 · IDE-AI: AI assistant in VS Code, VSCodium and PyCharm ✅

*For administrators. Since 2026-10-22.*

IDE-AI brings an AI assistant into the editors of the workspaces, connected to **your own AI
server**. Behind it is [Continue](https://continue.dev) (Apache-2.0):

- **Chat** on the right in the side bar, where VS Code otherwise has its chat, with a choice of model,
- **Editing** selected code,
- **Agent mode**: the model reads and changes files and suggests commands, each with
  confirmation,
- optionally **completion while typing**.

The AI server must speak the OpenAI interface (`/v1/chat/completions`). **vLLM**, **llama.cpp**
(also behind llama-swap), Ollama and LiteLLM can do that.

Why Continue and not an own plugin: an own plugin would mean two code bases (VS Code in
TypeScript, JetBrains in Kotlin), and everything beyond a plain chat would be months of work.
Continue can do it, can be configured entirely through one file and runs in all three
editors.

## Turning it on

Under **Settings → IDE-AI**:

1. Enter the **AI server address**, with `/v1`, e.g. `http://192.168.1.2:3000/v1` (vLLM) or
   `http://192.168.1.3:8080/v1` (llama.cpp). Without a path, OTA adds `/v1`.
2. **Fetch models**. OTA asks the server for `/v1/models`.
3. In the table, **offer** the models that should be available and choose the **default model**.
   Enter **context window** and **response length** in tokens for each model.
4. **Test** sends a short question to the model and shows answer and duration.
5. **Save**, then turn on the **IDE-AI** switch.

It applies from the **next start or resume** of a workspace. Running ones stay as they
are.

**Turning it off** removes Continue from the editors again at the next start and deletes OTA's
configuration in the home. The packages stay in the workspace; without the link they do nothing.

## The settings

| Setting | What it does |
|---|---|
| AI server address | The OpenAI interface, with `/v1` |
| API key | Only if the server requires one (`--api-key` with vLLM and llama.cpp). It never leaves OTA towards the browser, but it is stored in the configuration in the home |
| Models | What people can choose from in Continue, the default model first |
| Context window | How many tokens Continue puts into one request. At most what the server allows: vLLM `--max-model-len`, llama.cpp `--ctx-size` divided by `--parallel` |
| Response length | At most this many tokens per answer (`max_tokens`). Must be smaller than the context window. Reasoning models need more, because the reasoning counts too |
| Completion while typing | A model that suggests the rest of the line while writing, or off. Only worth it with a fast model |
| Tools (agent mode) | The model may read and change files and suggest commands. Needs tool calls in the server (see below) |
| Temperature | Empty: what the server sets |
| Timeout | How long Continue waits for an answer. llama-swap loads a model only on the first call |
| Company proxy | Default: directly to the AI server, even if the workspaces otherwise go through the company proxy ([chapter 21](21-firmenproxy.md)) |
| Rules for the model | Hints with every request, one line per rule, e.g. "Answer in English." |
| Who may | Without a group, everyone. Otherwise only members of these groups; administrators always |

**Tool calls in the server:**

- vLLM: `--enable-auto-tool-choice --tool-call-parser <parser>`, the parser matching the model
  (e.g. `hermes` for Qwen).
- llama.cpp: `--jinja`.

Without them the chat stays usable; then turn **Tools** off.

## What happens in the workspace

At every start and resume, as root:

1. **Configuration** to `~/.continue/config.yaml`, immediately, before the editor is first opened.
   Plus Continue's telemetry off (`~/.continue/index/globalContext.json`).
2. **Packages**, in the background, so the start does not wait. Only for editors present in the
   image, and only if the version from the package source is not installed already:

| Package | For | How it is linked |
|---|---|---|
| `ota-ide-ai-vscode` | VS Code, VSCodium | as built-in extensions under `resources/app/extensions/ota-continue` and `ota-ide-ai`, for all users |
| `ota-ide-ai-jetbrains` | PyCharm, IntelliJ IDEA and every other JetBrains IDE under `/opt` | in the plugin directory of the home, `~/.local/share/JetBrains/<IDE><version>/ota-continue` |

The agent fetches the package file itself from the [own package source](26-paketquellen.md) and
installs it with `dpkg`. That is why IDE-AI gets **into every image with dpkg**: Debian 13 as well as
Ubuntu and Kasm images, also into those where OTA enters no package source. The workspace needs
no way into the network for it.

**Root workspaces** move to the newest version when resuming, as with `ota-selkies`.

Whoever builds new images can include the packages right away (Administration → Software, package
`ota-ide-ai-vscode` or `ota-ide-ai-jetbrains`). Then the installation at start is skipped; it is not
necessary.

Why JetBrains in the home: newer JetBrains IDEs load from their own `plugins/` only what is in the
precomputed `plugins/plugin-classpath.txt`. A plugin next to it does not even show up in the
log (measured with PyCharm 2026.2). Only the link lives in the home; the plugin itself, about
180 MB, stays in the package.

### Continue on the right, Copilot off (VS Code, VSCodium)

- **Continue sits on the right** in the secondary side bar, not on the left between Explorer and
  Search. For that, the package build changes the place in Continue's `package.json`
  (`viewsContainers.secondarySidebar`).
- **The side bar opens by itself**, once per folder. OTA's small extension `ota-ide-ai` next to it
  does that: on its own the side bar would stay closed, because it is still empty at start (Continue
  loads only afterwards) and VS Code closes an empty side bar. Whoever closes it keeps it closed;
  `Ctrl+Alt+B` opens it again.
- **The built-in Copilot is off** as long as IDE-AI is on. `ota-ide-ai` sets
  `chat.disableAIFeatures` as a default for that. Whoever wants Copilot after all sets the setting to
  `false` in their own settings. When IDE-AI is off, OTA removes the link, and Copilot is back.
- Whoever drags Continue elsewhere keeps that place.

## The configuration belongs to OTA until someone takes it over

OTA rewrites `~/.continue/config.yaml` at every start. The first line is the mark:

```yaml
# Verwaltet von OTA (IDE-AI). Änderungen hier überschreibt OTA beim nächsten Start.
# Wer die Datei selbst pflegen will, löscht diese erste Zeile.
name: OTA IDE-AI
models:
- name: Hauptmodell
  provider: openai
  model: Hauptmodell
  apiBase: http://192.168.66.225:8080/v1
  defaultCompletionOptions:
    contextLength: 65536
    maxTokens: 2048
```

(The two comment lines say: "Managed by OTA (IDE-AI). OTA overwrites changes here at the next
start. Whoever wants to maintain the file themselves deletes this first line.")

**Whoever deletes the first line maintains the file themselves.** OTA no longer touches it after
that, not even when turned off. Whoever wants OTA's version back deletes the file; at the next start
it is there again.

Exception: the empty file Continue creates itself when it starts without a configuration
(`name: Main Config`, `models: []`) belongs to no one. OTA replaces it at the next start.

Which model someone has currently chosen, Continue remembers itself. The choice survives
restarts.

## Network and firewall

As long as IDE-AI is on, the firewall allows the AI server **for all workspaces**: address and
port from the setting, TCP. Without this allowance the level "internet" would block a server in the
private address range. The allowance is not in the list under **Network → Exceptions for all workspaces**,
because it follows from this setting; it disappears when turned off.

The groups under **Who may** decide who gets Continue set up, not who reaches the server.
Whoever wants to open the server only to certain people gives it an API key.

Continue addresses the server **from the workspace**, not through OTA. That is why the OTA host
must be able to reach the server (the workspaces go through its router).

## Packages and versions

The packages are built by `scripts/build-ide-ai-deb.sh` from the files listed with version and
checksum in `packaging/ota-ide-ai/quellen`:

| File | Source |
|---|---|
| Continue for VS Code, Linux x64 | Open VSX (`Continue.continue`) |
| Continue for JetBrains | JetBrains Marketplace (plugin 22707); only Linux x64 goes into the package |

`make update` builds them and puts them into the package source if the version is missing there. The
first time, that fetches about 450 MB from the internet (through the company proxy, if set). After
that the files are kept in `dist/ide-ai-quellen/`. Without internet: put the two files there by hand.

A new version of Continue: in `packaging/ota-ide-ai/quellen` change version, address and
checksum, set `revision` to 1, then:

```bash
scripts/build-ide-ai-deb.sh --hochladen
```

The settings page shows which versions are in the package source.

> **About the JetBrains plugin:** since 2026 Continue no longer maintains it itself but leaves it to
> the community; version 1.0.67 is from March 2026. In PyCharm 2026.2 it loads without errors.
> For VS Code and VSCodium, Continue keeps developing.

## Privacy

- What someone asks goes **only to your AI server**, not to Continue or third parties.
- Continue's telemetry (PostHog) is turned off. In VSCodium it is anyway.
- Continue stores histories in the home (`~/.continue/sessions/`). They therefore end up in the
  profile backup.
- An API key is stored in `~/.continue/config.yaml` in the home, so also in the backup.

## When something does not work

| What | Cause |
|---|---|
| No Continue in the editor | The workspace was already running when IDE-AI was turned on: restart. At the very first start the installation may finish half a minute after the start: reopen the editor once. Log: `docker logs ota-agent 2>&1 \| grep IDE-AI` |
| "The packages are missing from the package source" | `scripts/build-ide-ai-deb.sh --hochladen` on the host |
| Continue shows a different configuration | The first line of `~/.continue/config.yaml` is missing: the file belongs to the person. Delete it, restart |
| Continue shows `Main Config` without models | Continue ran before OTA wrote the configuration. Restart the workspace; pause and resume a root workspace. The log then says "Konfiguration gesetzt" |
| No answer, timeout | Does the workspace reach the server? `curl http://<server>/v1/models` in the terminal. A model that is loaded first takes longer: raise the timeout |
| Answer breaks off, or only "Thought for …" without text | The response length is not enough; reasoning models use it up with the reasoning. Raise it |
| "context length exceeded" or similar from the server | The context window in OTA is larger than in the server. Lower it |
| Agent mode calls no tools | The server cannot do tool calls: vLLM `--enable-auto-tool-choice --tool-call-parser …`, llama.cpp `--jinja`. Or turn **Tools** off |
| Continue not visible on the right | `Ctrl+Alt+B` opens the right side bar. OTA opens it by itself only once per folder |
| PyCharm does not show Continue | Is there `~/.local/share/JetBrains/<IDE><version>/ota-continue`? The name comes from the IDE's `product-info.json` |

Test suite: `scripts/test-ide-ai.sh`. It starts every template with a matching editor and asks the
AI server from the workspace. The default is the llama.cpp server of the test installation; another
one via `OTA_TEST_KI_URL` and `OTA_TEST_KI_MODELL`.
