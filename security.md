# Sicherheitsbetrachtung

**Stand: 2026-09-04.** Betrachtet wurde OTA im Zustand des Commits `99e9400`, so wie er auf dieser
Maschine läuft.

Diese Betrachtung ist **kein Penetrationstest und kein Audit**. Sie ist das, was sie ist: eine
gründliche Durchsicht des eigenen Codes und der laufenden Anlage durch den, der beides gebaut hat.
Was hier steht, ist entweder im Quelltext nachgelesen oder an der laufenden Anlage **gemessen** —
und wo es gemessen ist, steht der Befehl daneben. Was nicht geprüft wurde, steht am Ende.

---

## Wie OTA aufgebaut ist — und wo die Grenzen liegen

Drei Vertrauensgrenzen tragen die ganze Konstruktion:

1. **Browser → Traefik → API.** Alles, was ein Mensch tut, geht durch Traefik. Vor jedem Zugriff
   auf einen Bildschirm (`/s/<id>/…`) fragt Traefik die API (`forwardAuth`), wem die Sitzung
   gehört — auch vor dem WebSocket-Handschlag.
2. **API → Agent.** Nur der Agent fasst Docker an (ADR-002). Die API bekommt den Socket nicht,
   weil sie Nutzereingaben verarbeitet.
3. **Agent → Session-Container.** Der Container ist das, worin der Mensch arbeitet. Er ist gegen
   OTAs Innereien abgeschottet — aber nicht gegen das Netz dahinter.

Die dritte Grenze ist die schwächste, und die drei schwerwiegendsten Befunde liegen alle dort.

---

## Befunde

Bewertet nach dem, was ein Angreifer damit erreicht — nicht nach dem Aufwand, es zu beheben.

> **Stand 2026-09-04: H1, H2 und H3 sind geschlossen.** Jeder Arbeitsplatz hängt in einem eigenen
> `internal`-Netz und erreicht die Aussenwelt nur über einen Router-Container; einen Weg daran
> vorbei gibt es nicht. Nachgewiesen von innen durch `scripts/test-firewall.sh` (19 Prüfungen).
> Aufbau und Begründung: [`firewall.md`](firewall.md).

| Nr. | Befund | Schwere |
|---|---|---|
| [H1](#h1) | ~~Aus jedem Arbeitsplatz sind Wirt und Firmennetz vollständig erreichbar~~ ✅ behoben | **hoch** |
| [H2](#h2) | ~~Arbeitsplätze erreichen einander direkt~~ ✅ behoben | **hoch** |
| [H3](#h3) | ~~Der Agent ist aus jedem Arbeitsplatz erreichbar~~ ✅ behoben | **hoch** |
| [H4](#h4) | Ein Administrator kann sich unbemerkt auf einen laufenden Bildschirm schalten | **hoch** |
| [M1](#m1) | Ungenutzter Endpunkt am Agent führt beliebige Befehle in beliebigen Containern aus | mittel |
| [M2](#m2) | Geheimnisse liegen im Klartext in der Datenbank, Sicherungen sind für alle lesbar | mittel |
| [M3](#m3) | Keycloak hat keine Passwortregel — der Hauptweg ist schwächer als der Nebenweg | mittel |
| [M4](#m4) | Keycloaks Verwaltungsoberfläche ist von aussen erreichbar | mittel |
| [M5](#m5) | `script-src 'unsafe-inline'` entwertet einen Teil der CSP | mittel |
| [M6](#m6) | Der Zeichensatz kommt bei jedem Aufruf von Google | mittel |
| [N1](#n1) | Kennzahlen-Merkmal wird nicht zeitkonstant verglichen | niedrig |
| [N2](#n2) | Keine Bremse am Reverse Proxy; die Kontosperre lässt sich gegen Kollegen richten | niedrig |
| [N3](#n3) | Container-Protokolle wachsen unbegrenzt und enthalten IP-Adressen | niedrig |
| [N4](#n4) | Administratorcontainer laufen ohne `no-new-privileges` und mit allen Fähigkeiten | Hinweis |
| [N5](#n5) | Beim Einfrieren werden Geheimnisse angezeigt, nicht entfernt | Hinweis |
| [N6](#n6) | HSTS ist aus | Hinweis |

---

### H1 · Aus jedem Arbeitsplatz sind Wirt und Firmennetz vollständig erreichbar {#h1}

> ✅ **Behoben am 2026-09-04.** Die Sitzungsnetze sind `internal`, der Router ist der einzige Weg
> hinaus, und die Brücke des Wirts trägt keine Adresse mehr. Gemessen von innen: Wirt, Firmennetz
> und Nachbarsitzung sind zu; TURN, OTA selbst, DNS und Internet gehen.

**Gemessen**, aus einem Container im Netz `ota_sessions`:

```
Gateway: 192.168.0.1
  192.168.0.1:22   OFFEN     ← SSH des Wirts
  192.168.0.1:8443 OFFEN     ← OTA selbst
  192.168.0.1:9200 OFFEN     ← Elasticsearch eines anderen Stapels
  192.168.0.1:6379 OFFEN     ← Redis eines anderen Stapels
  192.168.66.224:22 OFFEN    ← derselbe Wirt über seine LAN-Adresse
  192.168.66.1:80   OFFEN    ← anderes Gerät im Firmennetz
  http://example.com → 200   ← Internet
```

**Was das heisst.** Ein Arbeitsplatz ist ein vollwertiger Netzknoten im Firmennetz. Wer einen
Arbeitsplatz bekommt, bekommt einen Brückenkopf: Er kann den Wirt und jedes erreichbare Gerät
scannen und ansprechen. Besonders unangenehm sind Dienste ohne eigene Anmeldung — Elasticsearch
auf 9200 und Redis auf 6379 laufen auf **diesem** Wirt und antworten dem Container.

**Zum Teil ist das gewollt**: Ein Arbeitsplatz ohne Netz ist kein Arbeitsplatz. Die Nutzer sollen
ins Internet und an interne Dienste. Der Befund ist deshalb keine Fehlfunktion, sondern eine
**unausgesprochene Annahme**: Wer einen Arbeitsplatz vergibt, vergibt Netzzugang aus dem
Rechenzentrum heraus. Das gehört entschieden und aufgeschrieben, nicht stillschweigend
mitgeliefert.

**Empfehlung**, in dieser Reihenfolge — ausgearbeitet in [`firewall.md`](firewall.md):
1. Den Wirt vor seinen eigenen Containern schützen: Die Verwaltungsports des Wirts (22, und was
   sonst nur der Administrator braucht) für den Adressbereich der Sitzungen sperren. **Und zwar in
   `INPUT`, nicht in `DOCKER-USER`** — Verkehr an den Wirt selbst wird nicht weitergeleitet und
   läuft an `DOCKER-USER` vorbei.
2. Nachbarstapel abschirmen (Elasticsearch, Redis): entweder auf `127.0.0.1` binden oder
   Anmeldung einschalten.
3. Erst danach über eine allgemeine Ausgangsregel nachdenken. Sie ist die grösste Änderung und die
   mit den meisten Nebenwirkungen.

---

### H2 · Arbeitsplätze erreichen einander direkt {#h2}

> ✅ **Behoben am 2026-09-04.** Ein Netz je Sitzung — der einzige Weg, der wirklich trennt: Ohne
> geladenes `br_netfilter` läuft Verkehr auf derselben Brücke an jeder Regel vorbei.

**Gemessen**, zwei Container im Netz `ota_sessions`:

```
  Nachbarcontainer auf 6901 ERREICHBAR
  HTTP dorthin: 200
```

**Was das heisst.** Traefiks `forwardAuth` — die Stelle, die prüft, wem eine Sitzung gehört — sitzt
auf dem Weg **durch Traefik**. Von Container zu Container gibt es diesen Weg nicht. Zwischen dem
Arbeitsplatz von A und dem Bildschirm von B steht damit nur noch das Streaming-Passwort: bei
KasmVNC das aus dem Profil abgeleitete VNC-Geheimnis, bei Selkies die Basic-Auth der Sitzung. Beide
sind nicht zu erraten, aber sie sind die **einzige** verbleibende Schranke, und sie stehen im
Klartext in der Umgebung des jeweiligen Containers.

**Empfehlung.** Je Sitzung ein eigenes Netz statt eines gemeinsamen `ota_sessions` — und zwar
zwingend so: Ohne geladenes `br_netfilter` läuft Verkehr auf **derselben** Brücke gebrückt statt
geroutet und damit an jeder iptables-Regel vorbei. Eine Firewall über einem gemeinsamen Netz sähe
diesen Verkehr nie. Ausgearbeitet in [`firewall.md`](firewall.md).

---

### H3 · Der Agent ist aus jedem Arbeitsplatz erreichbar {#h3}

> ✅ **Behoben am 2026-09-04.** Der Agent hängt in keinem Sitzungsnetz mehr; er braucht es nicht,
> weil er über den Docker-Socket arbeitet.

**Gemessen**, aus einem Container im Netz `ota_sessions`:

```
  agent:8100/healthz -> 200
  agent:8100/host    -> 403  {"detail":"Agent-Token ungültig"}
  api:8000     -> nicht erreichbar
  db:5432      -> nicht erreichbar
  keycloak:8080 -> nicht erreichbar
```

Die Abschottung gegen Datenbank, API und Keycloak **funktioniert** — das ist die gute Hälfte des
Befundes. Aber der Agent hängt in `ota_sessions`, weil er die Container erreichen muss, und Docker
kennt keine Einbahnstrasse: Damit erreichen die Container auch ihn.

**Was das heisst.** Der Agent ist der einzige Dienst mit **schreibendem** Zugriff auf den
Docker-Socket. Wer ihn übernimmt, ist root auf dem Wirt. Zwischen einem beliebigen Nutzer und
diesem Zugriff steht genau ein gemeinsames Merkmal (`OTA_AGENT_TOKEN`, Header `X-Agent-Token`,
verglichen mit `secrets.compare_digest` — das ist richtig gemacht). Das Merkmal wird nicht in
Session-Container gereicht; es steht in der Umgebung von API und Agent.

**Empfehlung.** Den Agent aus `ota_sessions` herausnehmen. Er braucht das Netz nur, um Ports in
Containern abzufragen — das geht auch über den Docker-Socket. Solange er dort hängt: Merkmal lang
und je Anlage einzigartig halten (`make setup` erzeugt es), und bei jedem Verdacht wechseln.

---

### H4 · Ein Administrator kann sich unbemerkt aufschalten {#h4}

**Im Quelltext**, `api/ota/security.py`:

```python
def may_attach_to_session(sess, user):
    return sess.user_id == user.id or user.is_admin
```

Die Unterscheidung zwischen „alle Sitzungen sehen" (`sessions.view_all`) und „an einem fremden
Bildschirm sitzen" ist sauber gezogen und war ein bewusster Fix — ein Supporter mit `view_all`
kommt **nicht** heran. Ein voller Administrator kommt heran.

**Was fehlt**: Es gibt **keinen Protokolleintrag** dafür. Nachgesehen in
`api/ota/routers/internal.py` (kein `audit.record`) und in der Datenbank:

```sql
select action, count(*) from audit_log where action like '%attach%'; → leer
```

Und der Mensch am Bildschirm merkt nichts davon.

**Was das heisst.** Ein Administrator kann jederzeit still auf dem offenen Terminal, dem
Passwortspeicher und der Mailanwendung eines Kollegen mitlesen und mitarbeiten. Technisch ist das
schwer zu vermeiden — wer am Docker-Host sitzt, erreicht dasselbe ohnehin. **Unsichtbar** muss es
deshalb aber nicht sein, und aus Sicht des Beschäftigtendatenschutzes darf es das nicht sein
(siehe [`dsgvo.md`](dsgvo.md), Abschnitt „Aufschalten").

**Empfehlung**, aufsteigend:
1. **Protokollieren.** Ein Eintrag `session.attached` in `/api/internal/authz`, wenn Betrachter und
   Eigentümer verschieden sind. Zwei Zeilen Code, und der Vorgang ist nachvollziehbar.
2. **Sichtbar machen.** Ein Streifen im Bild der betroffenen Sitzung, solange jemand Fremdes
   zusieht.
3. **Zustimmung einholen.** Fernhilfe auf Anfrage statt auf Zuruf. Der Quelltext nennt das seit
   dem 2026-08-27 als den richtigen Weg; gebaut ist er nicht.

---

### M1 · Ungenutzter Endpunkt führt beliebige Befehle aus {#m1}

`agent/otaagent/main.py`:

```python
@app.post("/containers/{cid}/exec", dependencies=[Depends(require_token)])
def exec_in_container(cid: str, req: ExecRequest):
    c.exec_run(req.cmd, ...)
```

Ein Endpunkt am empfindlichsten Dienst, der einen beliebigen Befehl in einem beliebigen Container
ausführt — ohne Einschränkung auf Session-Container, ohne Nutzerbezug. **Aufgerufen wird er von
niemandem**: Die Suche im ganzen Baum (API, Frontend, Skripte) findet keinen Aufrufer.

**Empfehlung.** Löschen. Was nicht da ist, kann nicht missbraucht werden; die App-Starts im
Arbeitsplatz laufen über eigene, engere Wege.

---

### M2 · Geheimnisse im Klartext, Sicherungen für alle lesbar {#m2}

Im Klartext in der Datenbank:

* `identity_configs.bind_password` — das Dienstkonto zum Verzeichnis (nur Leserecht, aber ein
  gültiges AD-Konto)
* `users.totp_secret` — der Startwert des zweiten Faktors. Wer ihn hat, erzeugt gültige Codes.
  (Die **Rückfallcodes** sind gehasht — das ist richtig gemacht.)

Beides wird über die API nie herausgegeben (`has_bind_password: true/false`, `totp_enabled:
true/false`) — der Weg dorthin führt über die Datenbank oder eine Sicherung. Und die liegt offen:

```
-rw-r--r-- root root  /srv/ota/backups/database/2026-09-03T21-19-38Z
drwxr-xr-x root root  /srv/ota/profiles
drwxrwxrwx bmetallica  /srv/ota/profiles/7c1185e1-…/user     ← 777
```

**Was das heisst.** Ein Datenbankabzug enthält Passwort-Hashes, TOTP-Startwerte und das
AD-Kennwort — und ist für **jeden** Benutzer des Wirts lesbar. Zwei Profilverzeichnisse stehen auf
777, also für jeden auch beschreibbar. Zusätzlich laufen **alle** Sitzungen als dieselbe UID 1000
auf dem Wirt: Die Trennung der Zuhause ist eine Frage der Einhängung, nicht der Dateirechte.

**Empfehlung.**
1. `chmod 0700` auf `/srv/ota/{profiles,backups,userfiles,groupfiles}` und `0600` auf die Archive;
   der Agent setzt die Rechte beim Anlegen mit.
2. Die beiden 777-Verzeichnisse geraderücken.
3. Mittelfristig: TOTP-Startwerte und `bind_password` mit einem Schlüssel aus der `.env`
   verschlüsseln. Das schützt nicht gegen einen kompromittierten Wirt, aber gegen ein abhanden
   gekommenes Sicherungsarchiv — und genau das ist der wahrscheinlichere Fall.

---

### M3 · Keycloak hat keine Passwortregel {#m3}

Abgefragt am Realm `ota`:

```
  bruteForceProtected: True      failureFactor: 5      maxFailureWaitSeconds: 900
  passwordPolicy: None
  registrationAllowed: False     resetPasswordAllowed: False
```

Die Bremse gegen Durchprobieren steht. Eine **Passwortregel gibt es nicht** — Keycloak nimmt jede
Länge. OTAs eigene, lokale Anmeldung verlangt dagegen mindestens zwölf Zeichen
(`api/ota/security.py`). Damit ist der **Hauptweg** schwächer als der Nebenweg, der nur noch für
den Notzugang gedacht ist.

**Empfehlung.** Im Realm eine Regel setzen, mindestens `length(12)`, und die Einrichtung in
`scripts/keycloak-init.sh` mitnehmen, damit sie nicht bei der nächsten Anlage wieder fehlt.

---

### M4 · Keycloaks Verwaltungsoberfläche ist von aussen erreichbar {#m4}

```
GET https://192.168.66.224:8443/auth/admin/  → 302 (Anmeldemaske)
```

OTA steuert Keycloak von innen (Dienstkonto, `ota-agent` spricht `http://keycloak:8080`). Die
Verwaltungsoberfläche muss von aussen nicht erreichbar sein — sie ist es aber, samt der Anmeldung
zum `master`-Realm, dessen Konto in der `.env` steht.

**Empfehlung.** In Traefik eine Regel für `/auth/admin` mit `ipAllowList` auf das
Verwaltungsnetz — oder ganz zu, solange niemand sie braucht.

---

### M5 · `script-src 'unsafe-inline'` {#m5}

Aus `deploy/traefik/dynamic/middlewares.yml`:

```
Content-Security-Policy: default-src 'self'; script-src 'self' 'unsafe-inline'; …
```

Der Rest der Regel ist gut geschnitten (`frame-ancestors 'self'`, `base-uri`, `form-action`,
`object-src` implizit über `default-src`). `'unsafe-inline'` nimmt der Regel aber ihre wichtigste
Wirkung: Eine gefundene XSS-Lücke wäre damit sofort ausführbar.

Gebraucht wird es für **ein** Skript: die Manifest-Zuordnung im Kopf von `web/index.html`, die
synchron laufen muss, bevor der Parser weiterläuft.

**Empfehlung.** Dieses eine Skript in eine eigene Datei ziehen oder ihm einen `nonce` geben, dann
`'unsafe-inline'` streichen. Solange es drin steht, ist die Maskierung im Markdown-Übersetzer
(`web/src/lib/markdown.ts` — die maskiert zuerst und setzt nur selbst Erzeugtes ein) die
eigentliche Verteidigung.

---

### M6 · Der Zeichensatz kommt von Google {#m6}

`web/index.html`:

```html
<link rel="preconnect" href="https://fonts.googleapis.com" />
<link href="https://fonts.googleapis.com/css2?family=Archivo…" rel="stylesheet" />
```

Bei **jedem** Aufruf holt der Browser jedes Nutzers zwei Zeichensätze von Google. Sicherheitlich
ist das eine fremde Herkunft im Ladepfad der Oberfläche und eine Abhängigkeit vom Internet — hinter
einem Firmenproxy oder offline lädt die Seite langsamer und sieht anders aus. Datenschutzrechtlich
ist es der schwerwiegendere Punkt; er steht in [`dsgvo.md`](dsgvo.md).

**Empfehlung.** Die beiden Schriften mitliefern (`web/public/fonts/`, `@font-face`), die beiden
Google-Herkünfte aus der CSP streichen. Das ist eine halbe Stunde Arbeit und löst beide Probleme
auf einmal.

---

### N1 · Kennzahlen-Merkmal, nicht zeitkonstant verglichen {#n1}

`api/ota/routers/monitoring.py`: `head[7:] == token`. Der Vergleich bricht beim ersten
unterschiedlichen Zeichen ab. Über ein Netz ist das kaum auswertbar, aber der Agent macht es
nebenan richtig (`secrets.compare_digest`) — also hier auch.

### N2 · Keine Bremse am Reverse Proxy {#n2}

Es gibt keine `rateLimit`-Middleware. Gegen Durchprobieren steht die Kontosperre (8 Fehlversuche →
15 Minuten, `LOCK_AFTER`/`LOCK_MINUTES`) und Keycloaks eigene Bremse. Zwei Kehrseiten: Ein
Unbeteiligter kann einen Kollegen gezielt aussperren, wenn er den Anmeldenamen kennt; und alle
anderen Endpunkte haben gar keine Bremse.

**Empfehlung.** Eine milde `rateLimit`-Middleware vor `/api/auth/*`.

### N3 · Protokolle ohne Grenze {#n3}

`docker inspect` meldet `json-file` ohne `max-size` und ohne `max-file`. Die Protokolle wachsen
unbegrenzt, und Traefiks Zugriffsprotokoll (gefiltert auf 4xx/5xx) enthält IP-Adressen.

**Empfehlung.** `logging: driver: json-file, options: {max-size: 10m, max-file: 3}` an jeden
Dienst. Das ist zugleich der Löschmechanismus, den die DSGVO verlangt.

### N4 · Administratorcontainer ohne Sperren {#n4}

`security_opt=[] if req.elevated else ["no-new-privileges:true"]`, dasselbe für `cap_drop`. Für
Administratoren fallen beide Sperren, damit `sudo` läuft. Das ist **begründet und dokumentiert**
und betrifft nur, wer ohnehin am Docker-Host sitzt. `SYS_ADMIN` ist entfernt, `pids_limit` steht,
der Docker-Socket wird nie in einen Session-Container gereicht. Bleibt ein Hinweis: Ein
Administratorcontainer ist kein Sicherheitsbehälter.

### N5 · Einfrieren zeigt Geheimnisse, entfernt sie nicht {#n5}

`agent/otaagent/freeze.py` erkennt Schlüssel, Token und Passwortdateien großzügig (vierzehn Muster)
und stellt sie in der Vorschau **nach oben**. Entfernt werden nur sechs feste Pfade (Proxy,
sudo-Ausnahme, Browser-Richtlinien); das Zuhause ist ohnehin ausgenommen. Wer die Vorschau nicht
liest und bestätigt, friert ein Geheimnis mit ein. Bewusst so gebaut — ein Filter, der still
löscht, zerstört irgendwann etwas Gebrauchtes. Bleibt ein Hinweis für den Betrieb: **Die Vorschau
ist zum Lesen da.**

### N6 · HSTS ist aus {#n6}

Dokumentiert und begründet: Mit der eigenen CA würde HSTS den „trotzdem fortfahren"-Ausweg
entfernen und Nutzer aussperren. Die Middleware `ota-hsts` liegt fertig daneben. **Einschalten,
sobald ein Zertifikat einer anerkannten CA im Einsatz ist** — hinter dem Firmen-Reverse-Proxy ist
das bereits der Fall.

---

## Was gut gelöst ist

Damit das Bild stimmt — das hier ist geprüft und trägt:

* **Die Trennung von API und Docker** (ADR-002). Gemessen: Aus einem Session-Container sind
  Datenbank, API und Keycloak **nicht** erreichbar.
* **`forwardAuth` vor jedem Bildschirm**, auch vor dem WebSocket-Handschlag, und die
  Unterscheidung zwischen „sehen dürfen" und „daran sitzen dürfen".
* **Passwörter mit Argon2**, Rückfallcodes gehasht, `token_epoch` zum serverseitigen Ungültigmachen
  aller Sitzungen eines Menschen.
* **Pfadauflösung**: `_resolve` löst zuerst auf und prüft dann, ob das Ergebnis noch in der Ablage
  liegt — ein `..` fällt damit genauso auf wie ein Symlink nach draussen.
* **Kein CORS, kein `Access-Control-Allow-Origin`.** Die Oberfläche ist gleicher Herkunft;
  `SameSite=Lax` plus JSON-Pflicht trägt den CSRF-Schutz.
* **Markdown ohne rohes HTML**: erst maskieren, dann nur selbst Erzeugtes einsetzen; Verweise
  werden nur für `http(s)://` zu Links, `javascript:` also nie.
* **TLS 1.2 als Untergrenze**, gemessen: TLS 1.1 wird abgelehnt.
* **Geheimnisse waren nie im Repository** (`git log -- deploy/.env` ist leer), `.env` und Schlüssel
  stehen auf `0600`.
* **Container-Härtung für Nicht-Administratoren**: `cap_drop: ALL`, `no-new-privileges`, kein
  `SYS_ADMIN`, `pids_limit`, Speicher- und Kerngrenze.
* **434 automatische Prüfungen**, davon 226 zur Autorisierung — sie prüfen unter anderem
  nachweisbar, dass ein normaler Nutzer nichts Administratives tun und an keinem fremden Bildschirm
  sitzen kann.

---

## Abhängigkeiten

| Bestandteil | Fassung |
|---|---|
| FastAPI / Uvicorn / SQLAlchemy / Pydantic | 0.115.6 / 0.34.0 / 2.0.36 / 2.10.4 |
| PyJWT / cryptography / argon2-cffi / pyotp | 2.10.1 / 44.0.0 / 23.1.0 / 2.9.0 |
| docker (Python) | 7.1.0 |
| Traefik / Keycloak / PostgreSQL / coturn | v3.7 / 26.7 / 16-alpine / 4.6-alpine |
| Basis-Images | `python:3.12-slim`, `node:22-alpine`, `nginx:alpine` |

**Ein Abgleich gegen Schwachstellenlisten (CVE) hat nicht stattgefunden.** `make sbom` erzeugt die
Stückliste je Image in SPDX und CycloneDX; sie durch einen Scanner zu schicken ist der nächste
Schritt und gehört in den Betrieb, nicht in eine einmalige Durchsicht.

---

## Was diese Betrachtung nicht war

* **Kein Penetrationstest.** Niemand hat versucht, die Anlage zu übernehmen.
* **Keine Prüfung der fremden Bestandteile.** Keycloak, Traefik, KasmVNC, Selkies, PostgreSQL und
  die Kasm-Images wurden als das genommen, was sie sind.
* **Kein CVE-Abgleich**, siehe oben.
* **Kein Fuzzing, keine statische Analyse** über das hinaus, was Typprüfung und die 434 Prüfungen
  ohnehin abdecken.
* **Der Browser des Nutzers** blieb aussen vor — Erweiterungen, kompromittierte Endgeräte,
  Schulter­blicke.
* **Der Wirt selbst** blieb aussen vor: Betriebssystem, Kernel, Docker-Fassung, SSH-Konfiguration.
  Das ist keine Kleinigkeit — Befund H1 hängt unmittelbar daran.

---

## Reihenfolge, wenn nur begrenzt Zeit ist

1. **H4 protokollieren** — zwei Zeilen, und das Aufschalten ist nachvollziehbar. Auch die
   dringendste Zeile in [`dsgvo.md`](dsgvo.md).
2. **M1 löschen** — ein Endpunkt weniger, den niemand braucht.
3. **M2, Teil 1** — Dateirechte auf Sicherungen und Profile. Ein `chmod`, sofort wirksam.
4. **M3** — Passwortregel in Keycloak.
5. **M6** — Zeichensatz mitliefern. Löst zugleich den grössten DSGVO-Punkt.

~~H1, H2 und H3~~ sind am 2026-09-04 erledigt — siehe [`firewall.md`](firewall.md).
