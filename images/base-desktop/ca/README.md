# Eigene Zertifizierungsstellen

Hier hinein gehören `*.crt`-Dateien, wenn der Firmenproxy TLS aufbricht — also
Verbindungen mit einem eigenen Zertifikat ersetzt, statt sie durchzureichen.
Ohne sie scheitert im Image jedes `apt-get update`, jedes `curl` und jedes
`pip install` an einem Aussteller, den es nicht kennt.

Das Format muss **PEM** sein und die Endung `.crt` lauten — `update-ca-certificates`
ignoriert alles andere stillschweigend. Eine `.pem`-Datei wird einfach
umbenannt; der Inhalt ist derselbe.

```bash
cp /pfad/zur/firmen-ca.pem images/base-desktop/ca/firma.crt
scripts/build-desktop-image.sh --pruefen
```

Ist das Verzeichnis leer, passiert nichts — das ist der Normalfall und die
Vorgabe.

**Was das nicht löst:** Der Docker-Daemon holt Images selbst und liest diese
Dateien nicht. Für ihn gehört dieselbe CA nach
`/etc/docker/certs.d/<registry>/ca.crt` auf dem Host. Siehe
[Handbuch, Kapitel 21](../../../docs/wiki/21-firmenproxy.md).
