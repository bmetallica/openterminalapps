# 2 · Erste Schritte

> **Zwei Konten nach `make admin`.** Der Alltagszugang liegt in Keycloak, der Notzugang `notfall`
> lokal in OTA. Beide Passwörter werden **einmal** gedruckt. Die Startseite führt zur zentralen
> Anmeldung; der Notzugang liegt unter `/notfall`. Warum das so ist:
> [Kapitel 18](18-zentrale-anmeldung.md).

## Voraussetzungen

| | |
|---|---|
| Betriebssystem | Debian 12/13 oder vergleichbar |
| Docker | ≥ 25, mit Compose v2. **Docker 29** verlangt API ≥ 1.40 — siehe [Fehlersuche](12-fehlersuche.md) |
| RAM | 8 GB für einen Piloten, **64 GB** für ~20 Arbeitsplätze |
| CPU | 4 Kerne für einen Piloten, **16+** für die Zielgröße |
| Platte | 100 GB für einen Piloten, **1 TB** für die Zielgröße |

**Diese Ports müssen auf dem Host frei sein** — und, wo eine Firewall davor steht, für die
Arbeitsplätze erreichbar:

| Port | Wofür | Einstellbar über |
|---|---|---|
| **8443** (TCP) | Die Oberfläche und der Bildstrom | `OTA_HTTPS_PORT` |
| **8081** (TCP) | Leitet nur auf HTTPS um | `OTA_HTTP_PORT` |
| **3478** (UDP/TCP) | Der TURN-Server, sobald eine Vorlage auf Selkies steht | `OTA_TURN_PORT` |
| **49160–49260** (UDP) | Worüber TURN den Medienstrom vermittelt. Eine Verbindung belegt vier Ports | `OTA_TURN_MIN/MAX` |
| **30000–30019** (TCP) | Der Vorrat für Portfreigaben („+ NAT", [Kapitel 23](23-netz.md)). Belegt wird davon nur, was jemand freigibt | `OTA_NAT_MIN/MAX` |

Dazu ein **freier Adressbereich für die Arbeitsplatznetze**: ab Werk `10.99.0.0/16`. Er darf sich
nicht mit dem Firmennetz überschneiden — sonst gewinnt das Sitzungsnetz, und das echte Ziel ist aus
dem Arbeitsplatz nicht mehr erreichbar. Umzustellen über `OTA_SESSION_POOL`, **bevor** die erste
Sitzung läuft.

Ein Arbeitsplatz ist mit 4 Kernen und 6 GB veranschlagt. Der Container muss auf die **Spitze**
ausgelegt sein — auf alles, was ein Nutzer gleichzeitig offen hat.

## Installation ✅

Auf dem Host wird **nur Docker** gebraucht — kein Node, kein Python. Alles wird
in Containern gebaut und ausgeführt.

```bash
git clone <repo> /opt/openterminalapps
cd /opt/openterminalapps

sudo make setup            # Zertifikat, deploy/.env, Geheimnisse, Verzeichnisse
sudo make up               # Stack bauen und starten
sudo make admin NAME=deinname   # ersten Administrator anlegen
```

**Die Geheimnisse erzeugt `make setup` selbst** und trägt sie ein — von Hand ist nichts
nachzutragen. Ein zweiter Aufruf lässt vorhandene Werte unangetastet und ergänzt nur, was in einer
neuen Fassung dazugekommen ist; deshalb läuft er auch bei jedem `make update` mit.

`sudo` braucht es für die Verzeichnisse unter `/srv/ota` und den Docker-Socket. Wer in der Gruppe
`docker` ist und `/srv/ota` selbst angelegt hat, kann es weglassen.

`make help` zeigt alle Befehle.

Danach erreichbar unter `https://<host>:8443/`.

### Warum 8443 und nicht 443

Solange Kasm parallel läuft, belegt es Port 443. Nach der Ablösung wird in `deploy/.env` umgestellt:

```ini
OTA_HTTPS_PORT=443
OTA_HTTP_PORT=80
```

Der HTTP-Port leitet nur auf HTTPS um. Auf diesem Host ist 8080 von einem anderen Dienst belegt,
daher die Vorgabe 8081.

## Zertifikat vertrauen

Beim ersten Aufruf warnt der Browser, weil die CA unbekannt ist. **Einmalig** das Root-Zertifikat
importieren, danach ist Ruhe — auch nach jedem Zertifikatswechsel:

```bash
# Linux, systemweit
sudo cp deploy/certs/ota-ca.crt /usr/local/share/ca-certificates/ota-ca.crt
sudo update-ca-certificates
```

Firefox bringt einen eigenen Speicher mit: *Einstellungen → Datenschutz → Zertifikate anzeigen →
Importieren*, Haken bei „Dieser CA vertrauen, um Websites zu identifizieren".

Details und der Wechsel auf ein echtes Zertifikat: [Kapitel 10](10-zertifikate-und-https.md).

## Erster Administrator ✅

```bash
make admin NAME=<benutzername>
```

Gibt ein Einmal-Passwort aus, das beim ersten Login gewechselt werden muss.
Der Nutzer landet in den Gruppen `admins` und `users`.

## Was heute schon läuft

| Bestandteil | Status |
|---|---|
| Traefik mit TLS, HTTP-Umleitung, Sicherheits-Header | ✅ |
| Lokale CA und Zertifikatserzeugung | ✅ |
| Anmeldung, Nutzer, Gruppen, Rechte | ✅ |
| Workspaces anlegen und zuweisen | ✅ |
| Ressourcen je Nutzer (Abweichungen) | ✅ |
| Container starten, streamen, pausieren, beenden | ✅ |
| **Arbeitsplatz mit mehreren Apps** | ✅ Grundfunktion |
| **Zwischenablage-Brücke zwischen den Apps** | ✅ |
| Leerlauf-Aufräumer, Waisen-Aufräumer | ✅ |
| **Ein eigenes Netz je Arbeitsplatz, hinter einem Router** | ✅ [Kapitel 23](23-netz.md) |
| **Firewall in der Oberfläche**: Profile, Freigaben, Portfreigaben, Übersicht | ✅ |
| Golden Images mit Build-Pipeline, Rezepte, App-Erkennung | ✅ |
| LDAP/AD | ✅ (über Keycloak) |
| Netzlaufwerke, Kerberos | gestrichen — siehe [Kapitel 8](08-nutzer-und-gruppen.md#netzlaufwerke-im-arbeitsplatz--gestrichen) |
| Kasm-Registries einbinden | ✅ |
| Eigene Marke (Name, Farbe, Zeichen) | ✅ |

Prüfen, ob alles läuft:

```bash
make test
```
