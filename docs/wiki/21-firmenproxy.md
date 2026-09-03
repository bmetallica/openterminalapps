# 21 · Betrieb hinter einem Firmenproxy

*Für Administratoren.* Ohne Proxy ist nichts zu tun — das ist die Vorgabe und
bleibt es. Dieses Kapitel gilt nur für Netze, in denen der Weg ins Internet
über einen Proxy führt.

## Die drei Zeilen in `deploy/.env`

```
OTA_HTTP_PROXY=http://proxy.firma.example:3128
OTA_HTTPS_PROXY=http://proxy.firma.example:3128
OTA_NO_PROXY=localhost,127.0.0.1,::1,ota-api,ota-agent,ota-db,ota-keycloak,ota-web,ota-traefik,ota-turn,ota-registry,.local,10.0.0.0/8,172.16.0.0/12,192.168.0.0/16
```

Danach `sudo make update`. Leer lassen heisst: kein Proxy, und alles verhält
sich wie zuvor.

**`OTA_NO_PROXY` stellt `make setup` selbst zusammen**, wenn dort nichts steht:
die eigenen Dienste, der Rückkanal, **dieser Host unter jedem Namen, unter dem
er sich kennt**, und die privaten Netzbereiche. Der Hostname ist der Grund,
warum die Vorlage das nicht fest enthalten kann — sie weiss ihn nicht. Die
privaten Bereiche decken jede Docker-Brücke ab, ohne sie einzeln aufzuzählen;
die legt Docker erst beim Start an, lange nach `make setup`. Wer die Zeile von
Hand pflegt, behält sie.

> **`OTA_NO_PROXY` ist der wichtigste der drei.** Ohne ihn schickt die API ihre
> Aufrufe an den Agent, an Keycloak und an die eigene Registry durch den
> Firmenproxy. Der kennt diese Namen nicht und lässt sie in einen Zeitablauf
> laufen — der Fehler sieht dann nach OTA aus und ist keiner. Was drinsteht,
> muss alles abdecken, was **innerhalb** der Anlage liegt.

Eine Eigenheit, die überrascht: Nicht jedes Programm versteht CIDR-Bereiche in
`no_proxy`. Go-Programme (Docker, Traefik) tun es, Pythons `urllib` nicht —
dort zählen nur Namen und einzelne Adressen. Deshalb stehen in der Vorgabe
beide Formen nebeneinander.

## Wohin OTA den Proxy reicht

| Stelle | Wofür | Wie |
|---|---|---|
| **Bauen der Dienste** | `pip`, `npm` in api, agent, web | Build-Argumente in `deploy/docker-compose.yml` |
| **Bauen der Images** | `apt`, `curl`, `git clone` | `scripts/build-desktop-image.sh` und der Bildbauer |
| **Session-Container** | Anwender installieren nach | der Agent setzt sie beim Start |
| **API und Agent** | Kataloge fremder Registries | Umgebung in der Compose-Datei |

Gesetzt wird jeweils **klein und gross geschrieben**. Das ist keine
Doppelmoppelei: `curl` liest `http_proxy`, viele Java-Programme `HTTP_PROXY`.
Wer nur eine Schreibweise setzt, hat die halbe Anlage versorgt.

Beim **Bauen** genügen die Build-Argumente, und zwar ohne eine `ARG`-Zeile im
Dockerfile: Docker kennt diese sechs Namen vorab, reicht sie in jedes `RUN`
durch und schreibt sie **nicht** ins fertige Image. Nachgeprüft am 2026-09-03.
Genau deshalb muss der Proxy für Session-Container getrennt gesetzt werden —
was beim Bauen galt, gilt zur Laufzeit nicht mehr.

## Was in der Sitzung ankommt

Die Umgebungsvariablen stehen in **jedem** Session-Container, gleich aus
welchem Image er stammt — auch in fremden von Kasm. Das deckt alles ab, was
sie liest: `curl`, `wget`, `pip`, `git`, und über GLibs Auflöser auch Firefox
und Chrome.

Zwei verbreitete Fälle lesen sie aber **nicht**, und beide treffen genau das,
was Anwender ständig tun:

| | Warum | Was OTA hinterlegt |
|---|---|---|
| **`apt`** | kennt keine Umgebungsvariablen, nur seine eigene Konfiguration | `/etc/apt/apt.conf.d/99ota-proxy` |
| **Login-Shells** | wer sich über ein Terminal eine neue Shell holt, erbt die Umgebung nicht zwingend | `/etc/environment` und `/etc/profile.d/ota-proxy.sh` |

Das geschieht **absichtlich blind**: OTA schreibt die Dateien in jede Sitzung,
ohne zu prüfen, ob das Image sie überhaupt liest. Eine Datei, die dort niemand
anschaut, schadet nicht; eine fehlende Einstellung kostet den Anwender eine
Stunde Suche. Scheitert das Hinterlegen, läuft der Arbeitsplatz trotzdem — es
fehlt dann nur die Bequemlichkeit.

In der apt-Konfiguration landen auch die Ausnahmen: Jeder Name aus
`OTA_NO_PROXY` bekommt ein `DIRECT`. Ohne das ginge selbst der Zugriff auf die
eigene Registry durch den Firmenproxy. Bereiche wie `10.0.0.0/8` fallen dabei
weg — apt kennt keine Netzbereiche, nur einzelne Rechnernamen.

**Wo es trotzdem klemmen kann:** Programme mit einer eigenen Proxy-Einstellung
in ihrer Oberfläche. Firefox steht ab Werk auf „Systemeinstellungen verwenden"
und ist damit versorgt; wer es einmal von Hand umgestellt hat, muss es selbst
zurückstellen. Dagegen hilft kein Automatismus — nur ein Skeleton-Profil, das
die Einstellung mitbringt ([Kapitel 17](17-ablage-und-startskript.md)).

## Was OTA nicht lösen kann: `docker pull`

Images holt der **Docker-Daemon**, nicht ein Container. Er liest `deploy/.env`
nicht und braucht seine eigene Konfiguration auf dem Host:

```bash
sudo install -d /etc/systemd/system/docker.service.d
sudo tee /etc/systemd/system/docker.service.d/proxy.conf > /dev/null <<'EOF'
[Service]
Environment="HTTP_PROXY=http://proxy.firma.example:3128"
Environment="HTTPS_PROXY=http://proxy.firma.example:3128"
Environment="NO_PROXY=localhost,127.0.0.1,::1,.local,10.0.0.0/8,172.16.0.0/12,192.168.0.0/16"
EOF
sudo systemctl daemon-reload && sudo systemctl restart docker
```

**Die eigene Registry gehört in `NO_PROXY`.** OTA betreibt sie unter
`127.0.0.1:5000`; ginge der Zugriff durch den Proxy, käme kein Golden Image
mehr herein.

## Proxies, die TLS aufbrechen

Manche Firmenproxies ersetzen Zertifikate durch eigene, statt Verbindungen
durchzureichen. Dann kennt kein Image den Aussteller, und schon das erste
`apt-get update` scheitert — mit einer Meldung über ein ungültiges Zertifikat,
die aussieht, als sei das Paketdepot kaputt.

Abhilfe: Die CA der Firma nach `images/base-desktop/ca/` legen, Endung `.crt`,
Format PEM.

```bash
cp /pfad/zur/firmen-ca.pem images/base-desktop/ca/firma.crt
scripts/build-desktop-image.sh --pruefen
```

Das Bauen sagt dann, was es übernommen hat; ist das Verzeichnis leer, steht da
„Keine eigene Zertifizierungsstelle — Normalfall."

Zwei Dinge, die dieselbe CA zusätzlich brauchen:

* **Der Docker-Daemon** für die eigene Registry —
  `/etc/docker/certs.d/<registry>/ca.crt` auf dem Host.
* **`pip`**, wenn es im Bildbauer benutzt wird: Es vertraut seinem eigenen
  Speicher und nicht dem des Systems. `pip install --cert
  /etc/ssl/certs/ca-certificates.crt` oder `PIP_CERT` in der Umgebung.

## Nachsehen, ob es wirkt

```bash
# Kommt der Agent nach draussen?
docker exec ota-agent sh -c 'echo $HTTP_PROXY; curl -sS -o /dev/null -w "%{http_code}\n" https://deb.debian.org/'

# Und geht der Weg nach innen am Proxy vorbei?
docker exec ota-api sh -c 'echo $NO_PROXY | tr "," "\n" | grep -c ota-agent'
```

Die zweite Zeile muss `1` liefern. Steht dort `0`, laufen die Aufrufe der API
an den Agent durch den Proxy — und das ist der Fehler, der am schwersten zu
finden ist, weil er nach einem Ausfall des Agents aussieht.
