# 15 · Taking over a profile from Kasm

*For administrators.* ✅

What is taken over is the **profile**, not the container. The container is created anew in OTA from
the golden image; what is valuable is the user's home.

**Kasm stays untouched** and keeps running. The script copies, it does not move.

## Procedure

```bash
cd /opt/openterminalapps

./scripts/migrate-kasm-profile.sh --dry-run bmetallica   # shows what would come
./scripts/migrate-kasm-profile.sh bmetallica             # copies
./scripts/migrate-kasm-profile.sh --verify bmetallica    # checks afterwards
```

The script is **idempotent** — a second run only syncs the differences. An already existing OTA
profile is put aside beforehand, not overwritten.

If a session of the user is running, it aborts. Swapping a profile under an open editor leads to
data loss on both sides.

## What comes along — and what does not

**Taken along** is everything that is work: settings, extensions, SSH and GPG keys, Git
configuration, XFCE layout, browser profile, editor history.

**Left out** is what is recreated at any time or would get in the way after the move:

| Excluded | Why |
|---|---|
| The extensions' `CacheStorage` | Service worker cache. **193 MB** in the measured profile and fully reloadable |
| Chrome's models and lists | `component_crx_cache`, `WasmTtsEngine`, `Safe Browsing`, dictionaries — together over **91 MB**, all reloadable |
| Editor caches | `Cache`, `CachedData`, `CachedExtensionVSIXs`, `GPUCache` |
| `core.*` | Crash dumps from old sessions |
| `.Xauthority`, `.ICEauthority`, sockets | Runtime leftovers of the old session that get in the way in the new container |
| `.kasmpasswd`, `.vnc/` | The old VNC password. OTA assigns its own secret per session — taking the old one along would simply be wrong |

**Result in the test run:** 805 MB of raw data became **63 MB**, without a single user file
missing.

## Acceptance

`--verify` checks that the essentials have arrived and shows the taken-over `settings.json` for a
visual check:

```
✓ Profil vorhanden                    ✓ Continue-Konfiguration übernommen
✓ VS-Code-Einstellungen übernommen    ✓ Kein Absturzabbild mitgekommen
✓ Extensions übernommen               ✓ Kein altes VNC-Passwort mitgekommen
✓ SSH-Schlüssel übernommen            ✓ Eigentümer ist 1000:1000
✓ GPG-Verzeichnis übernommen          ✓ XFCE-Einstellungen übernommen
```

(Profile present, VS Code settings, extensions, SSH keys and GPG directory taken over; Continue
configuration taken over, no crash dump and no old VNC password came along, owner is 1000:1000,
XFCE settings taken over.)

Then start the workspace and look inside — that is the only acceptance that counts.

## When something is not right

The previous OTA profile lies next to it as `user.vor-migration-<timestamp>`:

```bash
cd /srv/ota/profiles/<user>
mv user user.verworfen
mv user.vor-migration-<timestamp> user
chown -R 1000:1000 user
```

And the Kasm profile under `/srv/kasm_profiles/<user>` is unchanged anyway — the move can be
repeated any number of times.

## The opposite way

There is none. OTA never writes to `/srv/kasm_profiles`. Whoever wants to go back simply works in
Kasm again — everything there is still as it was.
