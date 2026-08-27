# 10 · Zertifikate und HTTPS

✅ verfügbar

## Warum HTTPS keine Option ist

Ohne TLS funktioniert die **Zwischenablage im Browser nicht**. `navigator.clipboard` steht nur in
einem Secure Context zur Verfügung. Das lässt sich in der Anwendung nicht umgehen und ist nicht
verhandelbar — HTTPS ist bei OTA Voraussetzung, keine Härtungsmaßnahme.

## Warum eine lokale CA statt eines selbstsignierten Zertifikats

Beide erzeugen beim ersten Aufruf eine Browserwarnung. Der Unterschied zeigt sich beim **zweiten**
Zertifikat:

| | Selbstsigniert | Lokale CA |
|---|---|---|
| Erster Aufruf | Warnung | Warnung, bis die CA importiert ist |
| Nach dem Import | — | keine Warnung mehr |
| Zertifikat erneuern | **jeder Nutzer muss erneut zustimmen** | nichts zu tun |
| Zweiter Host dazu | erneut überall zustimmen | nichts zu tun |

Bei einem Zertifikat, das ohnehin ausgetauscht werden soll, ist die CA die deutlich bessere Wahl.

## Zertifikat erzeugen

```bash
./scripts/make-cert.sh
```

Erzeugt in `deploy/certs/`:

| Datei | Zweck |
|---|---|
| `ota-ca.crt` | Root-Zertifikat — **das wird verteilt** |
| `ota-ca.key` | Schlüssel der CA — bleibt geheim, `0600` |
| `ota.crt` / `ota.key` | Serverzertifikat, gültig 825 Tage |

Die CA wird nur einmal angelegt und danach wiederverwendet. Erneutes Ausführen stellt **nur** ein
neues Serverzertifikat aus — die CA bleibt, und niemand muss etwas neu importieren.

### Zusätzliche Namen

Das Skript nimmt automatisch den Hostnamen und alle LAN-Adressen auf; Docker-Bridge-Adressen werden
ausgelassen. Weitere Namen:

```bash
OTA_DNS=ota.firma.local OTA_IP=10.0.0.50 ./scripts/make-cert.sh
```

> **SAN ist Pflicht.** Moderne Browser ignorieren den Common Name vollständig. Ein Zertifikat ohne
> passenden Subject Alternative Name wird abgelehnt, egal was im CN steht. Das Skript setzt SAN
> immer — bei handgemachten Zertifikaten ist es die häufigste Fehlerquelle.

## CA verteilen

```bash
# Linux, systemweit
sudo cp deploy/certs/ota-ca.crt /usr/local/share/ca-certificates/ota-ca.crt
sudo update-ca-certificates
```

**Firefox** hat einen eigenen Speicher: *Einstellungen → Datenschutz → Zertifikate anzeigen →
Importieren*, Haken bei „Dieser CA vertrauen, um Websites zu identifizieren".

**Windows**: `certlm.msc` → Vertrauenswürdige Stammzertifizierungsstellen → Importieren.
Per Gruppenrichtlinie lässt sich das domänenweit ausrollen — der empfohlene Weg im Unternehmen.

**macOS**: Schlüsselbundverwaltung → System → importieren → auf „Immer vertrauen" setzen.

## Zertifikat austauschen

Der ganze Sinn des Aufbaus. Beide Dateien überschreiben:

```bash
cp neu.crt deploy/certs/ota.crt
cp neu.key deploy/certs/ota.key
chmod 600 deploy/certs/ota.key
```

Traefik überwacht das Verzeichnis und lädt von selbst neu. **Kein Neustart nötig.**

Beim Wechsel auf ein Zertifikat einer echten CA — Let's Encrypt oder die Firmen-PKI — wird
`ota-ca.crt` nicht mehr gebraucht und kann aus den Clients entfernt werden.

## Betrieb hinter einem Reverse Proxy

Steht bereits ein Proxy mit gültigem Zertifikat davor, gibt es zwei Wege:

**TLS bis zu OTA durchreichen** (empfohlen): Der vorgelagerte Proxy leitet auf 8443 weiter, ohne die
Verschlüsselung aufzubrechen. OTA behält sein eigenes Zertifikat, Ende-zu-Ende bleibt verschlüsselt.

**Am Proxy terminieren**: Der Proxy hält das gültige Zertifikat und spricht intern mit OTA. Dann muss
der Proxy `X-Forwarded-Proto: https` setzen, sonst hält OTA die Verbindung für unverschlüsselt.
WebSockets müssen durchgelassen werden — ohne sie erscheint kein Bild.

In beiden Fällen: Der Browser muss die Seite als `https://` sehen, sonst fällt die Zwischenablage aus.

## HSTS

**Standardmäßig aus.** Der Grund ist praktischer Natur: Solange die CA nicht überall importiert ist,
würde HSTS den „trotzdem fortfahren"-Ausweg im Browser entfernen und Nutzer vollständig aussperren.

Einschalten, sobald die CA verteilt oder ein echtes Zertifikat aktiv ist — in
`deploy/traefik/dynamic/middlewares.yml` ist die Middleware `ota-hsts` bereits vorbereitet und muss
nur am Router ergänzt werden.

## Prüfen

```bash
# Kette gültig? ssl_verify_result muss 0 sein
curl -o /dev/null -w "%{http_code} %{ssl_verify_result}\n" \
  --cacert deploy/certs/ota-ca.crt https://<host>:8443/

# Enthält das Zertifikat die richtigen Namen?
openssl x509 -in deploy/certs/ota.crt -noout -subject -dates -ext subjectAltName
```
