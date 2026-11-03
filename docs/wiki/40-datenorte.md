# 40 · Wo die Daten liegen: Datenbanken auf SSD, Nutzerdaten auf HDD ✅

*Für Administratoren. Seit dem 2026-11-02.*

OTA hat zwei Arten von Daten, und sie wollen verschiedene Platten:

| Art | Was | Braucht |
|---|---|---|
| **Viele kleine, synchrone Schreibvorgänge** | Postgres von OTA und Keycloak, Registry, OTA-Git, Datenbank der Gedächtnis-Erweiterung, Docker-Daten der Root-Arbeitsplätze | SSD |
| **Viel Platz** | Zuhause, Benutzer- und Gruppenlaufwerke, gemeinsame Ablage, Sicherungen (`OTA_PROFILES_ROOT`, `OTA_USERFILES_ROOT` …) | große Platte |

Ohne Einstellung liegt die erste Art in Docker-Volumes, also im Docker-Verzeichnis des Wirts. Liegt
das auf einer langsamen Platte, wartet jeder Start, jedes Image und jede Anmeldung darauf.
`scripts/docker-diagnose.sh` zeigt das als zu wenige synchrone Schreibvorgänge je Sekunde
([Kapitel 12](12-fehlersuche.md)).

## Die Einstellungen

In `deploy/.env`, je Teil ein Verzeichnis. Leer bedeutet: Docker-Volume, wie bisher.

| Variable | Teil |
|---|---|
| `OTA_DB_DIR` | Postgres von OTA und Keycloak |
| `OTA_REGISTRY_DIR` | Registry der Arbeitsplatz-Images |
| `OTA_GIT_DIR` | OTA-Git (Forgejo) |
| `OTA_PLATZ_DOCKER_ROOT` | Docker-Daten der Root-Arbeitsplätze, ein Unterverzeichnis je Platz |
| `GEDAECHTNIS_DB_DIR` | in der `.env` der Erweiterung: ihre Datenbank |

**Nicht von Hand umstellen.** Ein neuer Pfad allein ist ein leeres Verzeichnis, und der Dienst
startete ohne seine Daten. Das Umziehen und Eintragen übernimmt das Skript.

Jeder Teil kann an einen eigenen Ort, etwa die Datenbank auf die eine SSD und die Docker-Daten der
Root-Arbeitsplätze auf eine andere.

## Die SSD vorbereiten

In einer VM: eine neue virtuelle Platte auf dem SSD-Speicher anlegen. Unter Proxmox mit Cache
„Write back“ (nicht „unsafe“), Discard, SSD-Emulation und IO-Thread; **Backup** an, sonst fehlt die
Datenbank in den Sicherungen von Proxmox. In der VM:

```
lsblk                                   # die neue Platte finden, z. B. sdc
mkfs.ext4 -L ota-ssd /dev/sdc
mkdir -p /ssd
echo 'LABEL=ota-ssd /ssd ext4 defaults,noatime 0 2' >> /etc/fstab
mount /ssd
```

ext4 oder xfs, **nicht btrfs**: btrfs ist bei vielen `fsync` deutlich langsamer. Das Skript weist
darauf hin.

## Umziehen

```
sudo scripts/daten-umziehen.sh --status                         # wo liegt was?
sudo scripts/daten-umziehen.sh --alle /ssd/ota                  # alles nach /ssd/ota/<teil>
sudo scripts/daten-umziehen.sh --db /ssd/ota/db --platz-docker /ssd2/platz-docker
```

Je Teil:

1. **Kopieren im laufenden Betrieb** mit `rsync`. Das dauert je nach Platte, stört aber niemanden.
   Meldungen `file has vanished` sind dabei normal: Dienste und Plätze löschen weiter Temporäres,
   Logs und WAL-Dateien. Was dadurch fehlt, holt der letzte Abgleich nach.
2. **Umschalten.** Der Dienst hält an, ein letzter Abgleich überträgt nur noch die Änderungen
   (Sekunden). Dann trägt das Skript den Ort in `.env` ein, legt den Dienst neu an und wartet, bis
   er gesund ist. Wird er es nicht, schaltet es auf den alten Ort zurück.
3. **Die alte Kopie bleibt liegen**, bis `--aufraeumen` sie löscht.

Während die Datenbank umschaltet, zeigt OTA das Update-Banner. Die Oberfläche wartet kurz und wirft
niemanden hinaus. Laufende Arbeitsplätze bleiben verbunden.

`--nur-kopieren` macht nur Schritt 1. Das geht beliebig oft; danach ist das Umschalten schneller.
Der letzte Abgleich rechnet dabei immer ab dem Beginn der ersten Vorkopie.
`--ja` fragt nicht nach.

### Laufende Root-Arbeitsplätze

**Das Skript hält keinen laufenden Arbeitsplatz an.** Es kopiert dessen Docker-Daten nur vor und
trägt `OTA_PLATZ_DOCKER_ROOT` ein. Umgeschaltet wird beim **nächsten Fortsetzen**: Bevor der Agent
den Container startet, gleicht er ab, was sich seit der Vorkopie geändert hat, und schaltet um.
Das dauert meist Sekunden. Gelingt es nicht, startet der Platz vom alten Ort, und das Protokoll des
Agents sagt warum. Angehaltene Plätze schaltet das Skript gleich um.

Neue Root-Arbeitsplätze legt der Agent danach gleich unter `OTA_PLATZ_DOCKER_ROOT` an.

### Zurück

```
sudo scripts/daten-umziehen.sh --db volume                      # zurück ins Docker-Volume
```

Derselbe Ablauf in die andere Richtung; Änderungen seit dem Umzug kommen mit. Docker-Daten von
Root-Arbeitsplätzen gehen nur angehalten zurück. Plätze, die schon unter `OTA_PLATZ_DOCKER_ROOT`
angelegt wurden, können nur an einen anderen Pfad, nicht zurück in ein Volume.

### Aufräumen

```
sudo scripts/daten-umziehen.sh --aufraeumen
```

Fragt bei jeder alten Kopie, ob sie weg soll: alte Volumes, alte Verzeichnisse und die alten Daten
umgezogener Root-Arbeitsplätze (`….vor-umzug`). Erst danach ist der Platz auf der alten Platte frei.

## Wie es gebaut ist

- **Dienste aus Compose** (Datenbank, Registry, Gedächtnis): Die Einhängung lautet
  `${OTA_DB_DIR:-db-data}:/var/lib/postgresql/data`. Mit Pfad ist es ein Bind-Mount, ohne Pfad das
  Volume.
- **OTA-Git** legt der Agent an. Er merkt am Container, dass `/data` nicht mehr vom gewünschten Ort
  kommt, und ersetzt ihn ([Kapitel 27](27-git.md)).
- **Docker-Daten der Root-Arbeitsplätze**: Das Volume `ota-platz-docker-<Sitzung>` behält seinen
  Namen. Neue Volumes binden `<OTA_PLATZ_DOCKER_ROOT>/<Name>` ein (`type=none,o=bind`). Bei
  umgezogenen zeigt das alte Datenverzeichnis per Verweis dorthin: Docker lässt die Optionen eines
  Volumes nicht ändern, solange ein Container es nutzt, und ein Root-Arbeitsplatz behält seinen
  Container. `docker system df` kennt die Größe solcher Volumes nicht; der Agent misst sie mit `du`
  und löscht sie samt Daten, wenn der Arbeitsplatz gelöscht wird.
- **Der letzte Abgleich** kopiert zusätzlich jede Datei neu, deren ctime jünger ist als der Beginn
  der Vorkopie. `rsync` vergleicht sonst nur Größe und Zeit auf die Sekunde. Postgres überschreibt
  WAL-Dateien gleicher Größe aber mehrmals je Sekunde; eine so kopierte Datenbank startet nicht
  („invalid checkpoint record“).
- `rsync -aHAXS --numeric-ids` behält Besitzer, Hardlinks, ACLs und erweiterte Attribute. Docker
  braucht das für seine Overlay-Schichten (Whiteouts, `trusted.overlay.*`).
