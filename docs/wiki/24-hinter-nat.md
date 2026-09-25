# 24 · Betrieb hinter einer Firewall mit NAT ✅

*Für Administratoren. Seit dem 2026-09-25.*

Dieses Kapitel beschreibt den Aufbau, bei dem **Browser und OTA nicht im selben Netz stehen**: OTA
läuft in einem eigenen Netz hinter einer Firewall, die Nutzer kommen von aussen und kennen nur die
Adresse der Firewall. Die Firewall reicht einzelne Ports weiter (Portweiterleitung, DNAT), davor
oder dahinter steht ein Reverse Proxy mit dem Zertifikat, dem alle vertrauen, und das Verzeichnis
(OpenLDAP oder AD) liegt auf der anderen Seite der Firewall.

Das Beispiel durchs ganze Kapitel:

| | Adresse |
|---|---|
| Firewall, von aussen | `10.50.0.33` |
| OTA-Host, innen | `192.168.1.22` |
| Reverse Proxy, innen | `192.168.1.23` |
| OpenLDAP, aussen | `10.50.0.1` |
| Name für die Nutzer | `https://ota.ai.vermkv.local` (DNS `*.ai.vermkv.local` → `10.50.0.33`) |

```
  Nutzer im 10er-Netz                          OTA-Netz 192.168.1.0/24
  ───────────────────                          ─────────────────────────────────────────
                          ┌──────────────┐
  Browser ──443/tcp──────▶│   Firewall   │──443──▶ Reverse Proxy .23 ──8443──▶ OTA .22
          ──3478/tcp─────▶│  10.50.0.33  │──3478─────────────────────────────▶ OTA .22 (coturn)
                          │              │
  OpenLDAP 10.50.0.1 ◀────│──636/tcp─────│◀──────── Keycloak auf OTA .22
                          └──────────────┘
```

**Der Bildstrom geht nicht durch den Reverse Proxy.** Selkies überträgt über WebRTC, und der Weg
dafür ist der TURN-Server `coturn` auf dem OTA-Host. Er braucht seine eigene Weiterleitung, direkt
auf den OTA-Host. Das ist der Punkt, an dem die meisten Einrichtungen scheitern: Die Seite lädt, die
Anmeldung klappt, und dann steht „Waiting for stream".

## 1 · Portweiterleitungen an der Firewall (von aussen nach innen)

| Extern | Ziel innen | Proto | Wofür | Pflicht |
|---|---|---|---|---|
| `10.50.0.33:443` | `192.168.1.23:443` (Reverse Proxy) | TCP | Oberfläche, API, Anmeldung (`/auth`), KasmVNC-Streams, WebSockets | ja |
| `10.50.0.33:3478` | `192.168.1.22:3478` (OTA-Host, **nicht** der Proxy) | TCP | TURN — der Bildstrom von Selkies | ja |
| `10.50.0.33:80` | `192.168.1.23:80` | TCP | nur die Umleitung auf HTTPS | nein |
| `10.50.0.33:30000–30019` | `192.168.1.22:30000–30019` | TCP | befristete Portfreigaben aus einem Arbeitsplatz („+ NAT", [Kapitel 23](23-netz.md)) | nur wenn genutzt |

- **Keycloak braucht keinen eigenen Port.** Es liegt unter `/auth` auf derselben Adresse wie OTA.
  Die API spricht Keycloak intern an, nicht über die Firewall.
- **3478 nur als TCP genügt**, wenn `OTA_TURN_PROTOCOL=tcp` und `OTA_TURN_ICE_POLICY=relay` gesetzt
  sind (siehe unten). Dann spricht der Browser ausschliesslich mit diesem einen Port. Wer auf UDP
  umstellt, braucht zusätzlich `3478/udp`.
- **Der Relay-Bereich `49160–49260` bleibt zu.** Mit `relay` benutzt ihn nur coturn selbst, auf dem
  OTA-Host, zwischen sich und dem Arbeitsplatz. Von aussen wird er nie angesprochen.
- **Eine Hairpin-NAT braucht es nicht.** Der Arbeitsplatz bekommt dieselbe TURN-Adresse wie der
  Browser (`10.50.0.33`); der Router der Arbeitsplätze biegt sie auf den Host um, bevor ein Paket
  die Firewall überhaupt erreicht.

Die Strecke Reverse Proxy → OTA (`192.168.1.23` → `192.168.1.22:8443`) liegt im selben Netz und
geht nicht über die Firewall.

**Nicht weiterleiten:** 8449 (Traefik-Dashboard), 5000 (Registry), 5432 (Datenbank), 8080 und
9000 (Keycloak direkt), 8100 (Agent), 49160–49260 (TURN-Relay).

## 2 · Freigaben vom OTA-Host ins äussere Netz

| Quelle | Ziel | Port | Wofür |
|---|---|---|---|
| `192.168.1.22` | `10.50.0.1` | **636/TCP** | Keycloak liest das Verzeichnis (ldaps) |
| `192.168.1.22` | DNS-Server | 53/UDP+TCP | Namensauflösung — der Name des Verzeichnisses, `*.ai.vermkv.local` |
| `192.168.1.22` | NTP-Server | 123/UDP | Uhrzeit — eine falsche Uhr bricht TLS und die Einmalkennwörter |
| `192.168.1.22` | Internet oder Firmenproxy | 443 bzw. Proxy-Port | Images holen und bauen ([Kapitel 21](21-firmenproxy.md)) |

- **636 und nicht 389.** OTA legt die Anbindung mit `startTls: false` an; StartTLS auf 389 lässt
  sich in der Oberfläche nicht einstellen. `ldap://…:389` hiesse: das Kennwort des Dienstkontos
  und jede Anmeldung im Klartext durch die Firewall.
- **Nur lesend.** Die Anbindung ist `READ_ONLY`: Keycloak liest Konten und Gruppen und prüft
  Passwörter per Bind, schreibt aber nie zurück. Das Dienstkonto braucht deshalb nur Leserecht.
- **Absender ist `192.168.1.22`.** Keycloak läuft in einem Docker-Netz, Docker setzt ausgehende
  Verbindungen auf die Adresse des Hosts um. Setzt die Firewall für diese Richtung zusätzlich
  Source-NAT, sieht das Verzeichnis `10.50.0.33`. Danach richten sich die ACLs am LDAP-Server.
- **Arbeitsplätze** erscheinen im äusseren Netz ebenfalls als `192.168.1.22`. Wer aus einem
  Arbeitsplatz etwas im 10er-Netz erreichen soll, braucht die Freigabe **zweimal**: an der Firewall
  und im Router der Arbeitsplätze (Oberfläche → Netz, [Kapitel 23](23-netz.md)).

## 3 · Was in OTA einzustellen ist

### `deploy/.env` auf dem OTA-Host

```bash
# Der Reverse Proxy — die Adresse, von der er verbindet.
OTA_TRUSTED_PROXIES=192.168.1.23/32

# TURN: unter welcher Adresse die Browser ihn erreichen, und an welche er
# sich bindet. Ohne NAT ist beides dasselbe und OTA_TURN_BIND bleibt leer.
OTA_TURN_HOST=10.50.0.33
OTA_TURN_BIND=192.168.1.22
OTA_TURN_PORT=3478
OTA_TURN_PROTOCOL=tcp
OTA_TURN_ICE_POLICY=relay

# Wenn der Host die Namen im 10er-Netz nicht von selbst auflöst:
OTA_FW_DNS_UPSTREAM=<DNS-Server im 10er-Netz>
OTA_NTP_HOST=<NTP-Server>
```

Danach `make up`. Das erzeugt `traefik.yml` und `turnserver.conf` neu und startet, was sich
geändert hat.

- **`OTA_TURN_HOST` darf auch ein Name sein** (`ota.ai.vermkv.local`), wenn er aussen auf die
  Firewall auflöst. `OTA_TURN_BIND` muss eine Adresse des Hosts sein — `scripts/turn-config.sh`
  warnt, wenn nicht. Eine IP ist der robustere Weg: Den Namen löst der Router bei jedem Abgleich
  auf, und ohne Namensdienst fällt die Umleitung aus.
- **`OTA_SELF_ADDRESS`** bleibt leer. Sie folgt `OTA_TURN_BIND` — unter dieser Adresse erreicht ein
  Arbeitsplatz OTA selbst auf `OTA_HTTPS_PORT`, um die Erweiterung für die Zwischenablage zu laden.
- **`relay` und `tcp` gehören zusammen** und sind hinter einer Firewall die richtige Wahl: ein
  einziger TCP-Port, keine Fragen nach Paketgrösse ([Kapitel 20](20-selkies-versuch.md), „Netze mit
  kleiner Paketgrösse").
- **`OTA_SESSION_POOL`** (Vorgabe `10.99.0.0/16`) darf sich nicht mit dem äusseren Netz
  überschneiden. Liegt dort ein ganzes `10.0.0.0/8`, gehört der Pool woandershin — sonst gewinnt
  das Sitzungsnetz, und das echte Ziel ist nicht mehr erreichbar.

### Der Reverse Proxy (`192.168.1.23`)

Er terminiert TLS mit dem Zertifikat für `*.ai.vermkv.local` und reicht an OTA weiter. Vier Dinge
müssen stimmen:

1. **Ziel `https://192.168.1.22:8443`.** Der Proxy muss dem Zertifikat von OTA vertrauen —
   `deploy/certs/ota-ca.crt` hinterlegen. `make cert` trägt die Adressen des Hosts von selbst ein.
2. **`X-Forwarded-Proto: https`, `X-Forwarded-Host` und `X-Forwarded-Port: 443`** setzen. Ohne
   den Port trägt Traefik `8443` ein, und für einen OIDC-Client ist das ein anderer Aussteller.
3. **WebSocket-Upgrades** durchreichen. Ohne sie gibt es kein Bild und keine Zwischenablage.
4. **Lange Zeitgrenzen.** Ein Stream ist eine Verbindung über Stunden.

Mit nginx:

```nginx
server {
    listen 443 ssl;
    http2 on;
    server_name ota.ai.vermkv.local;
    ssl_certificate     /etc/nginx/certs/ai.vermkv.local.crt;
    ssl_certificate_key /etc/nginx/certs/ai.vermkv.local.key;

    location / {
        proxy_pass https://192.168.1.22:8443;
        proxy_ssl_trusted_certificate /etc/nginx/certs/ota-ca.crt;
        proxy_ssl_verify on;

        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
        proxy_set_header Host $host;
        proxy_set_header X-Forwarded-Host $host;
        proxy_set_header X-Forwarded-Proto https;
        proxy_set_header X-Forwarded-Port 443;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;

        proxy_buffering off;
        proxy_read_timeout 12h;
        proxy_send_timeout 12h;
        client_max_body_size 0;
    }
}
```

Mit Caddy steht das Beispiel in [Kapitel 10](10-zertifikate-und-https.md).

**Welche Adresse in `OTA_TRUSTED_PROXIES` gehört**, zeigt Traefik selbst — nachsehen statt raten:

```bash
curl -sk https://ota.ai.vermkv.local/api/gibtsnicht -o /dev/null
docker logs ota-traefik --tail 5 | grep gibtsnicht     # erste Spalte = Absender
```

### Das Verzeichnis (Oberfläche → Einstellungen → Verzeichnis in Keycloak)

```
Adresse       ldaps://<Name des LDAP-Servers>:636
Basis         ou=people,dc=…
Dienstkonto   cn=<nur lesend>,dc=…
Art           OpenLDAP        (Anmeldename: uid)
```

**Verbindung testen**, speichern, **Jetzt abgleichen**. Danach kommen die Konten bei der Anmeldung
und bei jedem Abgleich aus dem Verzeichnis; geändert wird dort, nicht in OTA.

**Die CA des Verzeichnisses gehört in Keycloaks Truststore.** Keycloak prüft das Zertifikat des
LDAP-Servers (`useTruststoreSpi: always`) und kennt ab Werk nur die öffentlichen CAs der
Java-Laufzeit. Ein Zertifikat aus der Firmen-PKI wird sonst abgelehnt:

```bash
cp firmen-ca.pem deploy/keycloak-truststore/       # PEM, eine oder mehrere Dateien
docker restart ota-keycloak
docker logs ota-keycloak 2>&1 | grep -i truststore  # „Found the following truststore files …"
```

Das Verzeichnis wird nach `/opt/keycloak/conf/truststores` eingehängt; Keycloak liest jede Datei
darin von selbst. Es gehört zur Anlage und steht nicht im Repository (`.gitignore`).

**Das Zertifikat muss zur Adresse passen.** Wer `ldaps://10.50.0.1:636` einträgt, braucht ein
Zertifikat mit der IP im `subjectAltName`. Meist steht dort nur der Name — dann den Namen eintragen
und dafür sorgen, dass der Host ihn auflöst.

Der Test in der Oberfläche sagt, woran es liegt: „verschlüsselte Verbindung scheitert" heisst
Truststore oder Zertifikat, „Namen nicht auflösbar" heisst DNS, „nicht erreichbar" heisst Firewall.

## 4 · Was sich an OTA dafür geändert hat

Bis zum 2026-09-25 liess sich OTA hinter einer NAT nicht mit Selkies betreiben. Vier Stellen:

1. **Zwei TURN-Adressen statt einer.** `OTA_TURN_HOST` steuerte zugleich, woran coturn sich bindet
   und welche Adresse die Browser bekommen. Hinter NAT sind das zwei verschiedene: Mit der Adresse
   der Firewall startete coturn nicht, mit der eigenen bekamen die Browser eine, die sie nicht
   erreichen. Neu: `OTA_TURN_BIND` (`scripts/turn-config.sh`, Grundregeln im Agent).
2. **Umleitung im Router der Arbeitsplätze.** Selkies im Arbeitsplatz bekommt dieselbe Adresse wie
   der Browser. Der Router biegt `OTA_TURN_HOST:3478` auf `OTA_TURN_BIND` um; sichtbar unter
   **Netz → Was ohne Zutun gilt** als Zeile mit der Herkunft `OTA_TURN_HOST → OTA_TURN_BIND`.
3. **`OTA_SELF_ADDRESS` ist eine eigene Einstellung.** Sie hing fest an `OTA_TURN_HOST` und hätte
   hinter NAT auf `10.50.0.33:8443` gezeigt — ein Port, der dort gar nicht offen ist.
4. **Truststore für Keycloak** (`deploy/keycloak-truststore/`). Vorher liess sich ein Verzeichnis
   mit einem Zertifikat aus einer Firmen-CA überhaupt nicht verschlüsselt anbinden. Dazu sagt der
   Verbindungstest jetzt, **warum** er scheitert — vorher stand für jeden Fall „nicht erreichbar",
   auch wenn der Server längst antwortete und nur die CA fehlte.

Beim Bauen fielen drei weitere Fehler auf, die mit NAT nichts zu tun haben und jede Anlage treffen
konnten ([Kapitel 12](12-fehlersuche.md), „Nach einem Neustart des Hosts hat kein Arbeitsplatz
Netz"): Traefik nahm dem Router nach einem Neustart des Hosts seine Adresse, ein gescheitertes
Anbinden hinterliess einen Eintrag, der Traefik später am Starten hinderte, und die Liste der
Container je Sitzungsnetz kam leer an.

## Prüfen

```bash
make up
./scripts/test-streaming.sh    # Bild durch die NAT — siehe unten
./scripts/test-firewall.sh     # u. a. „Die veröffentlichte TURN-Adresse führt zum Wirt"
```

`test-streaming.sh` stellt die NAT selbst nach: Ist `OTA_TURN_BIND` gesetzt und verschieden, legt
es für die Dauer der Reihe eine DNAT-Regel auf dem Host an, die für das Netz des Prüfbrowsers die
Rolle der Firewall spielt (`OTA_TURN_HOST:3478 → OTA_TURN_BIND`). Der Browser kennt dann nur die
veröffentlichte Adresse, Selkies im Arbeitsplatz geht über die Umleitung im Router. Gemessen am
2026-09-25 mit `OTA_TURN_HOST=10.50.0.33`: 1311 Bilder, die Zähler der Umleitung im Router
stiegen.

Von aussen — auf einem Rechner im 10er-Netz:

```bash
curl -s -o /dev/null -w "%{http_code}\n" https://ota.ai.vermkv.local/healthz   # 200
nc -zv 10.50.0.33 3478                                                          # offen
```

Auf dem OTA-Host:

```bash
python3 scripts/pruef-turn.py      # prüft coturn unter OTA_TURN_BIND
docker exec ota-firewall nft list chain inet ota prerouting   # die Umleitung samt Zählern
```

Gegen das Verzeichnis: **Verbindung testen** in der Oberfläche. Nachgestellt am 2026-09-25 mit
einem OpenLDAP, dessen Zertifikat von einer eigenen CA stammte: ohne die CA im Truststore
„verschlüsselte Verbindung scheitert" (im Protokoll von Keycloak `PKIX path building failed`),
mit ihr gelangen Verbindung und Anmeldung des Dienstkontos.

## Wenn etwas nicht geht

| Bild | Ursache |
|---|---|
| Seite lädt, „Waiting for stream" | 3478/TCP nicht weitergeleitet, oder auf den Reverse Proxy statt auf den OTA-Host |
| Anmeldung springt auf `https://192.168.1.22:8443` | `OTA_TRUSTED_PROXIES` fehlt oder nennt die falsche Adresse |
| Anmeldung scheitert mit „invalid issuer" in einer fremden Anwendung | Der Proxy schickt `X-Forwarded-Port` nicht |
| `turn-config.sh` warnt „keine Adresse dieses Hosts" | `OTA_TURN_BIND` fehlt oder ist falsch |
| Verzeichnistest: „verschlüsselte Verbindung scheitert" | CA fehlt in `deploy/keycloak-truststore/`, oder das Zertifikat passt nicht zur Adresse |
| Verzeichnistest: „nicht erreichbar" | 636 an der Firewall zu, oder das Verzeichnis nimmt nur 389 |
