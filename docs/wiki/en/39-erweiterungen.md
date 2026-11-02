# 39 · Extensions ✅

*For administrators. Since 2026-11-02.*

An **extension** is a standalone Docker application with its own Compose project that OTA
integrates into the workspaces. The first is the **memory for opencode**
([github.com/bmetallica/plugin_ota-opencode](https://github.com/bmetallica/plugin_ota-opencode)):
every opencode session gets a long-term memory that survives summaries of the history and later
continuations.

What OTA takes care of:

- **Pairing**, once per extension.
- **Turning it on** for groups.
- An **own token** per entitled workspace. It is issued at the start and ends with the workspace.
- The **MCP server** for opencode and the **snippet for the system prompt**
  ([chapter 38](38-opencode.md)).
- The extension's **views** in OTA: under **My account** and in the **⋯** menu of a workspace tile.
- The **events** in an account's life: locking, unlocking, deleting.

Network, data and updates stay with the extension.

## How it fits together

```
Workspace ──http──▶ ota-erweiterungen:8091/<slug>/mcp ─▶ Traefik (in the session network)
                                                            │  only paths from the manifest
Browser ──https──▶ OTA /x/<slug>/ansicht/… ─▶ Traefik ─forwardAuth─▶ ota-api
                                                            │  signed headers
ota-api ──contract /ota/v1 (service secret)───────────────▶ │
                                                            ▼
                                           Extension (network ota_erweiterungen)
```

- `make update` creates the network **`ota_erweiterungen`** with a fixed range
  (`OTA_ERWEITERUNGEN_NETZ`, default `10.98.0.0/24`). Only Traefik, the API and the extensions are in
  it, never a workspace.
- **From the workspaces** only Traefik's entrypoint `erweiterungen` (port 8091) leads there. It is
  reachable only in the session networks, not on the host, and opens only the paths the extension
  names in its manifest (for the memory `/mcp`). In the workspace the name `ota-erweiterungen`
  points to Traefik in its own session network. **No host port and no firewall rule** are needed;
  this also holds with the network profile "no company network".
- This path is **unencrypted**. The session network contains only this one workspace, its router
  and Traefik, and the token is valid only for this workspace.
- **From the browser** only `/x/<slug>/ansicht/…` under OTA's own address leads there. Traefik asks
  the API first (forwardAuth). The API checks the sign-in and passes the person's identifier and
  their workspaces on in headers, signed with the service secret. Headers the browser sends itself
  are replaced by Traefik.
- **The contract** (`/ota/v1/…`) is called only by the API, from the network `ota_erweiterungen`.
  It is reachable neither from the workspace nor from the browser.

## Installing an extension: the memory

On the OTA host, next to OTA:

```bash
cd /opt
git clone https://github.com/bmetallica/plugin_ota-opencode.git
cd plugin_ota-opencode
./setup.sh                    # creates .env and shows the pairing key
docker compose up -d --build
```

Then in OTA under **Settings → Extensions → Pair an extension**:

1. Enter the **address**, `http://ota-gedaechtnis:8080`, and the **pairing key** from `setup.sh`.
   It is also in the `.env`.
2. **Pair**. OTA fetches the manifest and deposits its own service secret with the extension. OTA
   no longer needs the pairing key afterwards; pairing again works with the same key.
3. **Configure**: the extension brings the form itself. For the memory these are:
   - the embedding server: address with `/v1`, model, a key and prefixes if needed;
   - expiry, quotas and "ask before saving".

   **Test** asks the embedding server.
4. Choose the groups under **Who may** and flip **On**.

This requires **opencode to be on** ([chapter 38](38-opencode.md)). It applies from the next start
or resume of a workspace, the views immediately.

**Embeddings**, for searching by meaning instead of only by words: any server with an OpenAI
interface (`/v1/embeddings`) works.

| Server | Address | Model | Prefixes |
|---|---|---|---|
| vLLM | `http://<host>:8000/v1` | e.g. `BAAI/bge-m3` | empty |
| llama.cpp (also behind llama-swap) | `http://<host>:8080/v1` | e.g. `nomic-embed-text` | entry `search_document: `, search `search_query: ` |

Without an embedding server the memory searches by words only. If the server fails, it still saves
and embeds later.

## What people see

- **In opencode** the tools `memory_recall`, `memory_search`, `memory_save`, `memory_update` and
  `memory_forget`. Every session sees only its own memory; subagents and forks share that of their
  root session.
- **My account → Memory**: all sessions, grouped by workspace. There entries can be read, edited,
  pinned, deleted, created and copied or moved to other sessions. A session can also be given
  **access to the memory of another one**: it then reads it along, read-only and not further
  through that session's own accesses. There is also the export as JSON
  and Markdown and "delete everything".
- **⋯ → Memory (opencode sessions)** on the tile: the same for the sessions of this workspace.

More for the people is in [chapter 33](33-entwickeln.md#opencode-and-its-memory-).

## Privacy

- **Admins do not read contents.** The view too shows everyone only their own. Under Settings there
  are only numbers (**Numbers**: people, sessions, entries, storage).
- **Separation between people** is enforced by the extension's database itself (Row Level
  Security), not only by the code.
- The memory refuses **credentials** when saving: keys, tokens, passwords in addresses.
- **Expiry:** sessions without activity are deleted after the configured number of days, default
  180.
- **Account deletion:** if an account is deleted in OTA, the extension deletes all its data. If it
  cannot be reached at that moment, OTA repeats the job every 15 minutes until it confirms. Older
  backups hold the data until they expire.
- **Locking:** disabling, locking and removal from the group lock the person in the extension;
  tokens and view then no longer work, the data stays.

## Life cycle

| Event | In the extension |
|---|---|
| Workspace starts or is resumed | new token. An older one of the same workspace is revoked |
| Workspace ends, is stopped, reaper | token revoked; the entries stay |
| every 15 minutes | Reconciliation: tokens of workspaces that no longer run are revoked. Locks are reconciled, open jobs repeated, routes rewritten |
| every minute | Health. If the extension has a new version, OTA fetches its manifest again |
| Account deleted | all data deleted (see above) |
| Unpaired | tokens revoked, routes gone; the data stays in the extension |

**A workspace never fails because of an extension.** If it does not answer within 3 seconds at the
start, the workspace starts without it, and the error shows under Settings.

## Running the memory

- **Update:** in the extension's directory `make update`, that is `git pull` and rebuild. The data
  stays in the volume `ota_gedaechtnis_daten`.
- **Backup:** OTA's backup run (with "back up the database", [chapter 14](14-sicherung.md)) fetches
  it through the contract and stores it under
  `/srv/ota/backups/erweiterungen/gedaechtnis/<time>/gedaechtnis.dump`, `pg_dump` in custom format;
  retention as with the other backups. Restore by hand:

  ```bash
  docker exec -i ota-gedaechtnis-db pg_restore -U gedaechtnis -d gedaechtnis --clean --if-exists \
    < /srv/ota/backups/erweiterungen/gedaechtnis/<time>/gedaechtnis.dump
  docker restart ota-gedaechtnis
  ```
- **Removing:** unpair in OTA, then `docker compose down`. Only `docker volume rm
  ota_gedaechtnis_daten` deletes the data.
- **Log:** `docker logs ota-gedaechtnis`. It contains no contents and no tokens.

## Building an extension yourself

The contract OTA speaks (interface 1), with the service secret as bearer except for `manifest` and
`koppeln`:

| Call | Purpose |
|---|---|
| `GET /ota/v1/manifest` | identifier (`slug`, a–z/0–9), name, version, `pfade_fuer_arbeitsplaetze`, `liefert` (`opencode.mcp`, `opencode.plugin`, `prompt`), `ansichten` (`ort`: `konto` or `arbeitsplatz`, path under `/ansicht/`), `konfiguration` (JSON schema; `x-geheim` for secrets) |
| `POST /ota/v1/koppeln` | `{kopplungsschluessel, dienstgeheimnis}` |
| `GET /ota/v1/gesund` | `{ok, version, …}` |
| `GET`, `PUT /ota/v1/konfiguration` | the form's values; never return secrets, only `<name>_gesetzt` |
| `POST /ota/v1/testen` | free, for the "Test" button |
| `POST /ota/v1/arbeitsplatz` | `{arbeitsplatz_id, arbeitsplatz_name, nutzer:{id,name,anzeigename}, gruppen, vorlage, root}` → `{token, mcp_pfad, opencode_plugin, opencode_fragen, prompt}` |
| `DELETE /ota/v1/arbeitsplatz/{id}` | revoke the token |
| `GET /ota/v1/arbeitsplaetze` | `{arbeitsplaetze: [ids]}` with a valid token |
| `POST /ota/v1/nutzer/{id}/sperren`, `/entsperren`, `/loeschen` | events of an account |
| `GET /ota/v1/statistik` | numbers for admins |
| `GET /ota/v1/sicherung` | a stream that OTA's backup run stores (if the manifest says `sicherung: true`) |

The views check the headers `X-OTA-Nutzer`, `X-OTA-Name`, `X-OTA-Arbeitsplaetze`
(comma-separated), `X-OTA-Zeit` and `X-OTA-Signatur`. The signature is an HMAC-SHA256 with the
service secret over `nutzer|name|arbeitsplaetze|zeit`, valid for five minutes. OTA does not accept
foreign plugin code: `opencode_plugin` names only plugins from the package `ota-opencode`.

## When something does not work

| What | Cause |
|---|---|
| Pairing: "does not answer" | The extension is not in the network `ota_erweiterungen` (it only exists after `make update`) or not running: `docker ps`, `docker logs ota-gedaechtnis` |
| Pairing: 403 | Wrong pairing key: `grep KOPPLUNG .env` in the extension's directory |
| opencode: "Memory not set up: the OTA plugin did not provide the session" | opencode did not run in OTA's version or without OTA's configuration (own installation before the takeover, workspace not restarted yet) |
| opencode: "invalid or revoked token" | The workspace was resumed but opencode kept running: restart opencode |
| My account shows no "Memory" tab | Extension off, or the person is not in an entitled group |
| Search does not find related meaning | Check the embedding server (**Test**); with nomic-embed-text set the prefixes |
