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

Without the gateway, Continue addresses the server **from the workspace**, not through OTA. That is why the OTA host
must be able to reach the server (the workspaces go through its router).

## Several AI servers, AI gateway and usage statistics

*Since 2026-11-17. Everything here is optional and off by default.*

### The AI gateway

The gateway is a small service of its own, `ota-ki`. It runs in the firewall's network namespace
and listens there on port 8790. It is turned on under **Settings → IDE-AI → AI gateway**.
Then:

- **Continue and opencode** talk to `http://ki.ota:8790/v1` instead of the server directly. The name
  resolves in every workspace to the address of its router. The home holds **no API key** any
  more; the gateway adds it.
- **The firewall intercepts** what a workspace sends to the address and port of a registered AI
  server and redirects it to the gateway (nft `redirect`). This way scripts, own configurations and
  old instances with the real address go through it too, and so do containers in root workspaces.
  The request then goes exactly to the server it wanted to reach.
- **If the gateway is down**, the firewall removes the redirect within ten seconds, and traffic
  goes directly to the server again. What goes through `ki.ota` does need it, though. If the
  firewall restarts, the agent restarts `ota-ki` too; otherwise it would hang in the old namespace.

### Several AI servers

Under **Further AI servers** any number of servers can be added to the one above, each with name,
short code, address, key and models. They take effect **only with the gateway**:

- Continue and opencode see one model list across all servers. The gateway forwards each request
  to the server the model belongs to.
- If a further server has a model whose name is already taken, it is called `code/model` there,
  e.g. `gpu2/qwen3-coder`. The gateway puts the real name back. The models of the server above keep
  their names, the default model stays valid.
- A model that is not registered in OTA is answered by the gateway with 404 and an explanation.

**Who gets which server:** the server above applies to everyone who has IDE-AI or opencode. Each
further server gets its own **groups**. Their members get it in addition, administrators always.
Without a group it applies to everyone.

- Continue and opencode offer each person only the models of their servers. The default model
  falls back to that of the first server if it lies on a server the person does not have.
- The gateway checks every request: whoever addresses a model or the address of a server not
  granted to them gets 403 ("… is not enabled for you"). A direct HTTPS connection ends without an
  answer.
- A server with groups is **not** allowed for everyone in the firewall. It is reachable only
  through the gateway. If the gateway is down, it stays closed instead of being open to everyone.
- Changed groups take effect in the gateway immediately. In Continue and opencode new models
  appear with the next start or resume of the workspace.

### Usage statistics

With the gateway on, **Settings → IDE-AI → Usage statistics** counts who talks to the AI how
often. It is shown in three places.

**Operations → AI usage, without names.** What administrators see first, for a selectable period
(24 h, 3, 7, 30 days or custom), either by requests or by tokens:

- Tiles: requests, tokens in and out, people, workspaces, average duration, errors.
- The trend of all requests. Dragging across the graph zooms into that range.
- Donut charts **per person** and **per workspace**. They show only sizes: "Person 1" is the
  largest in the selected period and measure, not always the same one, and the API returns no
  names or IDs for them. With fewer than **three** people or workspaces in the period the split
  is left out, because with two everyone would know who is who. There are also donuts per
  template, per model and, with several servers, per server. More than seven slices are grouped
  as "Others".
- A distribution **by time of day**, summed over the whole period.
- A donut **per application**: which share comes from opencode, VS Code, PyCharm, Open WebUI and
  so on (see below for how OTA recognises the application).

**Filters.** Above the tiles the whole page can be narrowed down:

- **Overall / OTA only / Open WebUI only**: all requests, only those from workspaces, or only
  those of a connected service (one button per service, see [External services](#external-services-open-webui)).
  The buttons only appear once there is at least one service.
- **Model**: a single model.
- **Application**: a single application, e.g. PyCharm only.

All three can be combined; **Reset filters** clears them. The choices are what occurs in the
period. The minimum also applies to the selection itself: if **fewer than three people** use what
is filtered, the page shows no figures, only a notice. Otherwise the trend of "PyCharm only" alone
would reveal when the one PyCharm user was working. For that case there is the justified access.

**How OTA recognises the application.** From the request alone, without looking into the workspace:

| Shown as | based on |
|---|---|
| opencode, Continue, Cline, Roo Code, Kilo Code, Aider | user agent, for Cline/Roo/Kilo also `X-Title` or `HTTP-Referer` |
| VS Code, PyCharm, IntelliJ IDEA … | the name in the user agent, or: a generic library and the template has exactly that IDE (see below) |
| Open WebUI (or the service's name) | the key of the external service |
| Java, Node, Python program | only the library is recognisable (`okhttp`, OpenAI SDK for JS or Python …) |
| Script / command line | `curl`, `wget`, Go |
| not recorded | counted before this update: the hourly totals only know the application since then |

VS Code and PyCharm do not send AI requests themselves, their extensions do, and these often only
identify their library. OTA therefore adds information from the workspace's **template**: a Java
request from a template with exactly one JetBrains IDE counts for that IDE (e.g. PyCharm), with
several as "JetBrains IDE". A Node request from a template with VS Code or VSCodium counts for
VS Code. Without a matching IDE in the template it stays the program rather than a guess. A script
using the OpenAI SDK for Node inside such a workspace therefore also counts as VS Code. How
precise the donut is depends on which extensions you use.

**Personal access.** Names, the per-person overview and a person's workspaces with their trend
appear only after a **reason** is given (at least ten characters, e.g. a ticket number). It is
recorded as `ki.auskunft` with the name of the person asking and is visible under Operations →
Log. Access is valid for **30 minutes**, only for that account and only in that window: reloading
means giving a reason again. Every look at an individual person is also recorded as
`ki.nutzung_angesehen` together with the access case. Technically the access is a signed token
(header `X-OTA-Auskunft`). Without it, `/api/admin/ki-nutzung/personen` and `/nutzer/{id}`
return 403.

A click on a name shows that person's workspaces with a graph, one line per workspace.
**« 1 more day** extends it backwards and **‹ earlier / later ›** shifts it. Below are the models
and applications.

**My AI usage.** While the statistics run, **everyone** sees their own figures in the sidebar:
totals, the trend per workspace, models and tools. This is self-disclosure (Art. 15 GDPR), so no
reason is asked and nothing is logged.

**GDPR.** Also while the statistics run, everyone sees a **GDPR** item in the sidebar. It explains
what OTA records about workspaces and AI usage, why, for how long and who may see it.
Administrators always see the item and adapt the text there with **Edit**, in Markdown as for the
news. OTA fills in the placeholders `{frist_roh}`, `{frist_stunden}` and `{statistik}`, so the
stated retention periods stay correct after a change. **Use built-in text** restores the template
(German or English, following the UI language). You must fill in the controller and the data
protection officer yourselves. Every change is recorded as `dsgvo.hinweis_geaendert` in the log.

What is counted:

- **Time, person, workspace, server, model, duration and tokens, never contents**. OTA finds the
  person through the workspace's sender address.
- The server returns the tokens in its response. For streamed responses the gateway requests them
  as well (`stream_options.include_usage`) and removes the extra block again before it reaches the
  tool.

**Retention:** individual requests 30 days, hourly totals 365 days. Both are adjustable; for hourly
totals 0 means unlimited. OTA deletes older data once a day. **Delete all usage data** under
Operations → AI usage empties both.

**On disk** this costs little: the gateway writes to a spool file under
`/srv/ota/runtime/ki/spool/`, the API collects it once a minute in one go. It also does so when
the statistics and the gateway have since been switched off. What is there was counted while the
statistics ran, and it belongs in the database, where the retention periods delete it.

> **Before switching it on:** even without names on the first page, the statistics are a technical
> facility *suitable* for monitoring performance and behaviour (in Germany § 87 (1) no. 6 BetrVG).
> If there is a works council, ask it. A works agreement should state what the figures are for
> (capacity, cost, errors, not performance appraisal) and which reasons justify personal access.
> Ask your data protection officer whether a data protection impact assessment is needed, and add
> the entry to the record of processing activities. People are informed through the **GDPR** item:
> adapt its text first. Switching on and off, every access with its reason and every opening of a
> person's figures are recorded in the log.

### External services (Open WebUI)

A service outside the workspaces, such as Open WebUI, can also talk to the AI through the gateway.
It then sees the same model directory, the same group rule applies, and its requests appear in the
same statistics, with the right person. It no longer knows the AI server's key.

**Setting up**

1. On the host, set the port in `deploy/.env`, e.g. `OTA_KI_EXTERN_PORT=8791`, then run
   `sudo make update`. This publishes the entrance on the host and **restarts the router**:
   workspaces are briefly offline. The port must be free. `OTA_KI_EXTERN_BIND` limits the address
   it listens on (default: all). Without the port, everything stays as before.
2. Under **Settings → IDE-AI → External services**, add a service, e.g. "Open WebUI". OTA shows
   the key **exactly once** and afterwards stores only its SHA-256. If it is lost: remove the
   service and add it again.
3. In Open WebUI, under **Admin panel → Settings → Connections → OpenAI API**, enter the address
   `http://<host>:8791/v1` and this key.
4. For OTA to know who is asking, the Open WebUI container needs the environment variable
   `ENABLE_FORWARD_USER_INFO_HEADERS=true`. This means recreating it with changed configuration;
   you do that on Open WebUI, OTA does not touch the container. Older Open WebUI versions do not
   know the variable.

**How it works**

- At the second entrance (port 8791 in the firewall's namespace) only the route by name applies,
  and only with a valid key. Otherwise the answer is 401. The firewall keeps the workspaces
  themselves out; they have their own entrance.
- Who is asking is in the headers `X-OpenWebUI-User-Email` and `X-OpenWebUI-User-Name`. The
  gateway trusts them only with a valid key. **Neither they nor the service's key are passed on to
  the AI server**, only the server's own key.
- **Groups:** a further server with groups is reachable through the service only for their members
  (and administrators). Matching is by e-mail or username. Without information on who is asking,
  only the servers for everyone are available. The API sends the list of entitled people with every
  configuration and at least every ten minutes.
- **Statistics:** the API assigns the request to the OTA account by e-mail, username or a unique
  display name. The service takes the place of the workspace (so under "My AI usage" it is a row of
  its own) and appears as the tool "External service (short name)". If nobody matches, the request
  counts as "not attributable".
- Open WebUI also sends requests of its own, e.g. for chat titles, tags or suggestions. They count
  for the respective person.
- Adding and removing are logged (`ki.extern_angelegt`, `ki.extern_geloescht`). A removed service
  is locked out immediately.
- The built-in GDPR text mentions connected services. Adapt it when you connect one.

### Encrypted connections

If the AI server speaks HTTPS, nothing changes for Continue and opencode: they talk to the gateway
through `ki.ota`, and the gateway speaks HTTPS to the server, verifying the certificate. The path
from the workspace to the router is a private connection on the same host.

What a script sends **directly via HTTPS** to the server's address the gateway cannot read without
pushing an own CA onto the workspaces. OTA does not do that. Such connections it passes through
unchanged and counts only as a connection, with the server name from the TLS hello. In the overview
they appear as "encrypted (connections only)".

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
> the community; version 1.0.67 is from March 2026. For PyCharm 2026.2, OTA adapts it during the
> package build: from 2026.2 on, JCEF, the browser in which Continue shows its chat, is a plugin of its
> own. Without the dependency declared, the window would stay empty ("Nothing to show"). In addition,
> the agent gives `continue-binary` to the person of the workspace, because Continue sets its
> permissions itself at every start.
> For VS Code and VSCodium, Continue keeps developing.

## Privacy

- What someone asks goes **only to your AI server**, not to Continue or third parties.
- Continue's telemetry (PostHog) is turned off. In VSCodium it is anyway.
- Continue stores histories in the home (`~/.continue/sessions/`). They therefore end up in the
  profile backup.
- An API key is stored in `~/.continue/config.yaml` in the home, so also in the backup.
  Not with the AI gateway: then only the gateway knows it.
- Usage statistics are off as long as nobody switches them on. What they count is described above
  under [Usage statistics](#usage-statistics). While they run, OTA shows everyone the **GDPR**
  item and their own figures. Administrators see names only after a logged reason.

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
| PyCharm shows only "Nothing to show" for Continue | Package `ota-ide-ai-jetbrains` older than `1.0.67-ota5`: `make update`, then restart the workspace. The log (`~/.cache/JetBrains/*/log/idea.log`) then says `NoClassDefFoundError: com/intellij/ui/jcef/JBCefApp` or `continue-binary: Operation not permitted` |
| PyCharm does not show Continue | Is there `~/.local/share/JetBrains/<IDE><version>/ota-continue`? The name comes from the IDE's `product-info.json` |
| Continue displaced: Marketplace update, disabled, own `config.yaml` | The person themselves: dashboard → tile → **⋯ → Set up AI tools again** ([chapter 33](33-entwickeln.md#continue-is-gone-or-behaves-differently-)). Removes the copies, switches Continue on, puts the own `config.yaml` aside and installs the packages once more. In the log: `ide_ai.neu_eingerichtet`, in the agent `IDE-AI in … neu eingerichtet: …` |

| Under IDE-AI "The gateway does not respond" | `docker logs ota-ki`. If it runs but the firewall was restarted: the agent restarts it with the next reconciliation, otherwise `docker restart ota-ki`. Until then traffic goes direct |
| "The model … is not registered in OTA" | A tool asks through `ki.ota` for a model that is not offered under IDE-AI. Offer it, or choose another in the tool |
| "not attributable" in AI usage | Requests from an address without a running session, e.g. shortly after it ended |
| "Personal figures only with access" / "The access has expired" | The half hour is over, or the page was reloaded: enter a reason again |
| No donut per person, only "Only from 3 people …" | Intended: with fewer than three people or workspaces in the period it would be obvious who is who. Widen the period |
| No "GDPR" / "My AI usage" item in the sidebar | Both appear only while usage statistics run. Administrators always see "GDPR". The sidebar checks every five minutes; otherwise reload the page |
| Open WebUI: "Unknown key" (401) | Key copied wrongly or service removed. Add the service again and enter the new key |
| Open WebUI cannot reach `http://<host>:8791` | `OTA_KI_EXTERN_PORT` set in `deploy/.env` and `make update` run afterwards? `docker port ota-firewall` shows the port. A host firewall must let it through for Open WebUI's network |
| Requests via Open WebUI "not attributable" | `ENABLE_FORWARD_USER_INFO_HEADERS=true` is missing on the container, or the e-mail in Open WebUI matches no OTA account |
| No figures in AI usage | Statistics on? Gateway ready (Settings → IDE-AI)? The API collects every minute: `docker logs ota-api 2>&1 \| grep KI-Nutzung` |

Test suite: `scripts/test-ide-ai.sh`. It starts every template with a matching editor and asks the
AI server from the workspace. The default is the llama.cpp server of the test installation; another
one via `OTA_TEST_KI_URL` and `OTA_TEST_KI_MODELL`. Gateway, several servers, statistics and
outage are checked by `scripts/test-ki.sh` with the same settings.
