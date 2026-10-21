# 16 · Managing images

*For administrators.* ✅ List, pull, remove, own registry

**Administration → Images.**

## Where the list comes from

From the Docker host, unfiltered: **every tagged image that lies there.** On a machine that OTA
shares with other services, that is quickly fifty entries — from Elasticsearch to busybox. That is
exactly why this screen exists and not just a selection list in the workspace editor.

They are sorted by **origin**, because that decides what you may do with them:

| Origin | What it means |
|---|---|
| **Built by OTA** | `ota/…` — created in the workspace editor under *Software*. Your versions, your cleanup |
| **From Kasm** | Belongs to the other system on this host. OTA shows them but does not touch them — they are deleted where they came from |
| **Other** | Everything else on the host. Usable if it is a KasmVNC image; removable if no workspace uses it |

The column **Used by** names the workspaces that point to an image. Without it, "remove" would be a
guessing game — and a workspace whose image is missing only reports it on a user's next click.

## Pulling an image

Enter the reference as with `docker pull`, then **Pull**:

```
kasmweb/gimp:1.18.0-rolling-weekly
registry.company.local:5000/team/workspace:2026-08
```

The progress is shown — a Kasm image brings one to three gigabytes, that takes time. Afterwards it
can be chosen in the workspace editor.

In the editor itself the reference can also be **entered freely**. If it points to something that is
not on the host yet, the field says so — it is saved anyway, because the image only has to be present
at start.

## Removing an image

Only if both apply: **no workspace uses it**, and it is **not from Kasm**. Otherwise OTA refuses with
the reason.

Old versions of your own images are limited anyway: per workspace the last three stay
([chapter 7](07-golden-images.md)).

## The own registry ✅

In the stack, `registry:2` runs as the service `ota-registry`. Every built golden image lands there
in addition to the Docker store, and the version's reference becomes the reference in the registry:

```
127.0.0.1:5000/ota/arbeitsplatz:v5
```

### What it is good for — and what not

**Not** for rolling back a version. OTA can do that without it, via *Software → Versions →
Activate*, and for individual users via allocation ([chapter 6](06-ressourcen-und-zuteilung.md)).

What it is good for:

- **A host that never built an image can still start it.** If it is missing locally, the agent pulls
  it from the registry at session start. That is the prerequisite for a second host.
- **Foreign cleanup does not hit the copy.** Kasm's agent once deleted every image it did not know on
  this host ([chapter 9](09-kasm-images-und-registries.md)). The label problem is worked around —
  the copy outside the store is the more robust protection.

### Why on 127.0.0.1 and without TLS

The Docker daemon runs on the host, not in a container — it must reach the registry, and under the
same address that is in the image name. On `127.0.0.1` Docker requires **no** TLS. That saves a
certificate, `daemon.json` and a restart of the daemon.

The registry is therefore not reachable from outside. Whoever wants to offer it to a second host puts
it behind Traefik and then needs a certificate and access protection.

It can be turned off with `OTA_REGISTRY=` (empty) in `deploy/.env`. Then images only stay in the
Docker store, as before.

### Reclaiming space ⚠️

Deleting from the registry does **not** free the space by itself; a separate collection runs for
that:

```bash
docker compose -f deploy/docker-compose.yml exec registry \
  registry garbage-collect /etc/docker/registry/config.yml
```

That is exactly the price of the registry: every version lies twice, once in the Docker store and
once here. With 1.8 GB per workspace version and three versions kept, that is around 5 GB extra per
workspace.

### Looking at what is inside

```bash
curl -s http://127.0.0.1:5000/v2/_catalog
curl -s http://127.0.0.1:5000/v2/ota/arbeitsplatz/tags/list
```
