# 27 · OTA-Git (Forgejo) ✅

Eine Git-Plattform, die zu OTA gehört: [Forgejo](https://forgejo.org) unter einer eigenen
Subdomain. Unter **Einstellungen → Git** schaltest du sie ein und aus. Ist sie an,

- meldet man sich **mit denselben Zugangsdaten wie in OTA** an, über Keycloak, mit derselben
  zweiten Stufe;
- kommen nur die **berechtigten Gruppen** hinein, dazu immer die Administratoren;
- legt OTA die **Konten selbst an**, schon bevor sich jemand zum ersten Mal anmeldet. Wer seine
  Berechtigung verliert, wird **gesperrt, nie gelöscht**. **OTA-Admins sind auch in Forgejo
  Admins**;
- bekommt jeder berechtigte **Arbeitsplatz Git vorkonfiguriert**, auch ein Root-Arbeitsplatz.
  Andere Git-Server bleiben daneben nutzbar;
- erscheint eine Kachel **Git** im Anwendungskatalog. Sie startet gleich die Anmeldung über
  Keycloak; mit der Sitzung aus OTA ist man ohne Zwischenschritt drin.

Ausschalten hält nur an. Repositories, Konten und Datenbank bleiben, und ein erneutes Einschalten
macht weiter, wo es aufgehört hat.

## Einschalten

1. **Subdomain** eintragen, z. B. `git.firma.de`.
2. **Adresse von OTA** prüfen, so wie Browser sie sehen, z. B. `https://ota.firma.de`. Darüber
   findet Forgejo die Anmeldung (Keycloak). Vorgabe ist die Adresse, unter der du gerade
   arbeitest.
3. **Wer darf**: die Gruppen wählen. Ohne Gruppe kommen nur Administratoren hinein.
4. Den Schalter umlegen. Beim ersten Mal lädt OTA das Image von Forgejo
   (`codeberg.org/forgejo/forgejo:15.0.10`, festgelegt in `OTA_GIT_IMAGE`). Danach dauert es
   etwa 15 Sekunden.

Was dabei geschieht:

- Die Datenbank `forgejo` mit eigenem Benutzer wird im vorhandenen Postgres angelegt.
- Der Agent stellt ein Zertifikat für die Subdomain aus, von der OTA-CA.
- Ein Client in Keycloak wird angelegt, mit dem üblichen Gruppen-Zugang.
- Der Agent startet den Container `ota-git` mit dem Volume `ota_git_daten`.
- Der Agent richtet den Notzugang `ota-admin` und die Anmeldequelle ein.
- Zuletzt werden die Konten abgeglichen.

Die beiden Geheimnisse dafür, `OTA_GIT_DB_PW` und `OTA_GIT_ADMIN_PW`, erzeugt `make update` in
`deploy/.env`. Den Container legt der **Agent** an, nicht Compose, sonst ließe er sich nicht aus
der Oberfläche schalten.

## Wege hinein und Ports

```
Browser ──https──▶ Reverse Proxy ──https──▶ OTA-Host :8443 (Traefik, derselbe Eingang wie OTA)
  git.firma.de                                    │  Host: git.firma.de
                                                  ▼
                                            ota-git :3000 (http, nur intern)
```

| Port | Wo | Wofür |
|---|---|---|
| 8443 (`OTA_HTTPS_PORT`) | Host, wie bisher | HTTPS für OTA **und** die Subdomain. Traefik trennt am Namen |
| 3000 | nur intern, `ota-git` | Forgejo hinter Traefik |
| 443 | nur in den Sitzungsnetzen (Traefik `git-intern`) | HTTPS aus den Arbeitsplätzen |
| 2222 | nur in den Sitzungsnetzen (Traefik `git-ssh`) | Git über SSH aus den Arbeitsplätzen |

**Forgejo selbst hört auf 3000, und dieser Port wird nie veröffentlicht.** Der Reverse Proxy
zielt für die Subdomain auf **denselben Port wie für OTA**. Es kommt kein Port und keine
Firewall-Regel dazu. Unter der Subdomain gehört alles Forgejo, auch `/api`: Seine Regel hat
Vorrang (`priority 1000`) vor den Pfadregeln von OTA.

**Am Reverse Proxy** braucht es je Subdomain dasselbe wie für OTA, zusätzlich den Namen im
TLS-Handshake zu OTA (SNI). Das Beispiel steht in [Kapitel 24](24-hinter-nat.md#und-die-subdomain-von-ota-git).
Hinter dem Proxy vertraut Traefik den weitergereichten Kopfzeilen wie bisher nur von
`OTA_TRUSTED_PROXIES`, und Forgejo vertraut nur Traefik.

**DNS** brauchen nur die Browser: einen Eintrag der Subdomain auf den Reverse Proxy, ohne Proxy
auf den Host. Die Einstellungen zeigen, ob der OTA-Host den Namen auflöst. Arbeitsplätze
brauchen keinen Eintrag, siehe unten.

## Im Arbeitsplatz

Wenn Git an ist, der Mensch darf und die Vorlage **Git vorkonfigurieren** nicht abschaltet
(Vorgabe: an), richtet OTA bei jedem Start und jedem Fortsetzen als root ein:

- **`/etc/hosts`**: Die Subdomain zeigt auf Traefik im eigenen Sitzungsnetz. Das braucht weder
  Firmen-DNS noch einen Weg über den Proxy und geht auch im Netzprofil „kein Firmennetz“.
- **`/etc/ota-git/`**: ein Token, ein Credential-Helper, die CA von OTA, Name und E-Mail.
- **`/etc/gitconfig`** bindet das über `[include]` ein, also auf Systemebene, der mit dem
  niedrigsten Rang:
  - Der Helper und die CA gelten **nur für `https://<subdomain>`**. Ein anderer Server bekommt
    weder Token noch CA.
  - `user.name` und `user.email` kommen aus OTA. Was der Mensch in `~/.gitconfig` setzt,
    gewinnt.
  - Das Zuhause wird nicht angefasst. Eigene Zugangsdaten, SSH-Schlüssel und Helper für GitHub
    oder einen Firmenserver bleiben, wie sie sind.

Damit gehen `git clone https://git.firma.de/…`, `push` und VS Code ohne Passwortabfrage.

**Das Token:**

- Es gilt **je Arbeitsplatz** und darf nur Repositories lesen und schreiben und den eigenen
  Namen sehen.
- **Endet der Arbeitsplatz, widerruft OTA es.** Das gilt für Beenden, Anhalten und den
  Aufräumer, dazu alle 15 Minuten für alles, was daran vorbeiging.
- Ein Root-Arbeitsplatz bekommt beim Fortsetzen ein neues.
- Es liegt in `/etc/ota-git`, nicht im Zuhause, und gerät damit nicht in die Sicherung der
  Profile.

**SSH**: Den Schlüssel trägt der Mensch selbst in Forgejo ein (Einstellungen → SSH-Schlüssel).
Dann geht `git clone ssh://git@git.firma.de:2222/…`, **nur aus Arbeitsplätzen**. Forgejo zeigt
diese Adresse auch Browsern von außen an, dort funktioniert sie nicht. Von außen gilt HTTPS.

**git im Image**: Das Basisimage behält seit dem 2026-10-21 `git` (es wurde vorher nach dem Bau
wieder entfernt). Ältere Images: Basisimage neu bauen (`scripts/build-desktop-image.sh --pruefen`)
und die Arbeitsplatz-Images danach, oder `git` im Rezept bzw. im Root-Arbeitsplatz nachinstallieren.
Die Einrichtung wirkt, sobald git da ist.

## Konten

| Ereignis in OTA | In Forgejo |
|---|---|
| Mitglied einer berechtigten Gruppe, oder Admin | Konto anlegen bzw. entsperren |
| Admin | Forgejo-Admin; ohne die Rolle wieder nicht |
| aus der Gruppe genommen, deaktiviert, gesperrt | Anmeldung gesperrt (`prohibit_login`) |
| gelöscht | gesperrt; Repositories bleiben |
| im Verzeichnis umbenannt, Domänenkonto zugeordnet ([Kapitel 08](08-nutzer-und-gruppen.md)) | umbenannt; ein Konto, das den Namen schon trägt, wird beiseite benannt und gesperrt |

Abgeglichen wird bei jeder Anmeldung über Keycloak, nach jeder Änderung in der Verwaltung, nach
jedem Verzeichnisabgleich, alle 15 Minuten und mit **Konten jetzt abgleichen**. Ein Konto, das
OTA angelegt hat, wird bei der ersten Anmeldung im Browser **verknüpft, nicht verdoppelt**.

Repositories anlegen darf jeder. Neue Repositories sind privat.

**Notzugang**: `ota-admin` mit dem Passwort aus `OTA_GIT_ADMIN_PW`, über das Anmeldeformular von
Forgejo. Über ihn pflegt OTA die Konten. Das Passwort wird bei jedem Einschalten aus der `.env`
gesetzt.

## Einstellungen ändern

- **Andere Subdomain:**
  - Neues Zertifikat und neue Rücksprungadresse in Keycloak.
  - Der Container wird ersetzt, die Daten bleiben.
  - Arbeitsplätze bekommen die neue Adresse beim nächsten Start bzw. Fortsetzen.
  - Clones mit der alten Adresse stellt man um mit
    `git remote set-url origin https://<neu>/…`.
- **Andere Gruppen:** wirken sofort für Kachel und Keycloak. Konten werden gleich abgeglichen.
- **Ausschalten:** Container anhalten, Kachel und Keycloak-Client weg. Tokens laufen nicht mehr.

## Sicherung und Wiederherstellung

Ist Git eingerichtet, sichert der Sicherungslauf zusammen mit der Datenbank auch OTA-Git, unter
`/srv/ota/backups/git/<zeit>/`:

- `forgejo.sql.zst` enthält die Datenbank.
- `daten.tar.zst` enthält `/data` mit Repositories, Anhängen und Schlüsseln.

Das geht auch, wenn Git gerade aus ist.

Wiederherstellen geht von Hand:

```bash
# 1. In der Oberfläche: Einstellungen → Git → aus
D=/srv/ota/backups/git/<zeit>
zstd -dc $D/forgejo.sql.zst | docker exec -i ota-db psql -q -U ota -d forgejo
zstd -dc $D/daten.tar.zst | docker run --rm -i -v ota_git_daten:/data \
  --entrypoint tar codeberg.org/forgejo/forgejo:15.0.10 x -C /
# 2. Einstellungen → Git → an
```

## Entfernen

Ausschalten löscht nichts. Wer OTA-Git ganz loswerden will, entfernt nach dem Ausschalten von Hand:

```bash
docker rm ota-git && docker volume rm ota_git_daten
docker exec ota-db psql -U ota -c 'DROP DATABASE forgejo' -c 'DROP ROLE forgejo'
```

## Wenn etwas nicht geht

| Was | Woran es liegt |
|---|---|
| Nach der Anmeldung bei Keycloak wieder auf der Anmeldeseite von Forgejo | Die Anmeldequelle ist nicht auf dem Stand. Einmal aus- und einschalten; OTA startet Forgejo nach jeder Änderung der Quelle neu (der laufende Server liest sie nur beim Start) |
| „Kein Zugang zu dieser Anwendung“ | Nicht in einer berechtigten Gruppe, oder deaktiviert |
| Browser: Zertifikat passt nicht | Ohne Proxy: Der Browser muss der OTA-CA vertrauen. Mit Proxy: Zertifikat am Proxy prüfen |
| Unter der Subdomain erscheint OTA, oder Keycloak meldet `Invalid parameter: redirect_uri` | Der Proxy schickt den Namen nicht mit (`Host`, SNI). Caddy in der OPNsense: im Handler Protokoll `https://` und einen Header „nach oben“ `Host` = `{host}`. Nginx Proxy Manager: Scheme `https`, der `Host` stimmt dort von selbst |
| Nach der Anmeldung eine 404 auf `/sw.js` | Ein Browser, der unter der Subdomain einmal OTA gesehen hat, behält dessen Service Worker. Einmal die Website-Daten der Subdomain löschen (F12 → Application → Clear site data) |
| Keycloak fragt beim Weg von OTA nach Git noch einmal nach dem Passwort | Die „Adresse von OTA“ ist nicht die, unter der der Browser OTA aufruft |
| Im Arbeitsplatz fragt git nach Benutzer und Passwort | `git` fehlte beim Start, die Vorlage hat es abgeschaltet, oder der Mensch ist nicht berechtigt. Prüfen: `git config --show-origin --get-regexp credential` |
| Forgejo startet nicht | `docker logs ota-git`. Oft die Datenbank: `OTA_GIT_DB_PW` in `deploy/.env` gesetzt? |

Prüfreihe: `scripts/test-git.sh` (47 Prüfungen, auch hinter einem nginx als Reverse Proxy).
