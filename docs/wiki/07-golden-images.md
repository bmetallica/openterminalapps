# 7 · Golden Images

*Für Administratoren.* ✅ Build-Pipeline, Versionen und Aktivierung ·
🔨 Skeleton-Verwaltung und „Session einfrieren" (M5)

> **Solange Kasm auf demselben Host läuft, funktioniert das Bauen nicht.**
> Kasms Agent löscht im Modus „Aggressive" alle 30 Sekunden jedes Image, das er
> nicht kennt — auch unsere. OTA erkennt das und sagt es im Build-Log. Abhilfe:
> die Einstellung in Kasm unter *Infrastructure → Servers* ändern, oder erst nach
> der Ablösung bauen. Siehe [Kapitel 12](12-fehlersuche.md).

## Was ein Golden Image ist

Ein vorkonfigurierter Arbeitsplatz, den alle Nutzer identisch bekommen. Er besteht aus vier Schichten:

| Schicht | Inhalt |
|---|---|
| **Basis** | Ein Ausgangsimage — `ota/base-xfce` oder ein fertiges Kasm-Image |
| **Build-Layer** | Pakete, **Extension-Listen je Editor**, freies Setup-Skript |
| **Skeleton-Profil** | Was beim *ersten* Start ins Home kopiert wird: `settings.json`, Git-Vorlage, Zertifikate, Desktop-Verknüpfungen |
| **Laufzeit-Richtlinie** | Ressourcen, Auflösung, Rechte, Timeouts |

## Der übliche Weg: Session einfrieren

Golden Images entstehen selten am Reißbrett. Der praktische Weg:

1. Arbeitsplatz starten
2. Alles interaktiv einrichten — Extensions installieren, Einstellungen setzen, Werkzeuge
   konfigurieren
3. **„Als Golden Image speichern"**

OTA nimmt dann ein Abbild des Containers, vergleicht das Home mit dem bisherigen Skeleton und schlägt
die Änderungen vor.

### Der Geheimnis-Filter

Vor dem Speichern werden Zugangsdaten **automatisch aussortiert**:

```
.ssh/id_*      .gnupg/       *token*        *.pem
.aws/          .docker/config.json          krb5cc_*
.smbcredentials              keytab         Browser-Cookies
```

Was gefunden wurde, wird angezeigt. Trotzdem gilt: **Ein Golden Image sollte nie aus einer Session
entstehen, in der mit echten Zugangsdaten gearbeitet wurde.** Der Filter ist ein Netz, keine Garantie.

## Versionen

Jeder Build erzeugt `ota/<name>:v<N>` mit Digest, Größe und vollständigem Log.

- Genau eine Version ist **aktiv** — neue Sessions nutzen sie
- **Laufende Sessions bleiben unberührt**
- **Rollback** ist ein Klick: eine andere Version aktiv setzen
- Alte Versionen werden nach Regel aufgeräumt (Vorgabe: die letzten drei)

Empfehlenswert ist ein **Testlauf**: neue Version zuerst einer kleinen Gruppe zuweisen, dann global.

## Der App-Katalog

Beim Arbeitsplatz enthält das Golden Image mehrere Anwendungen. Je App wird hinterlegt:

```
Anzeigename · Icon · Startbefehl und Argumente
bevorzugte Auflösung
Skeleton-Teilbaum   .config/Code/User/       für VS Code
                    .config/JetBrains/        für IntelliJ
                    .config/VSCodium/User/    für VSCodium
Extension-Liste     wird beim BUILD installiert, nicht beim Start
Sichtbarkeit        je Gruppe zuschaltbar
```

**Extensions gehören in den Build, nicht in den Start.** Sonst wartet jeder Nutzer bei jedem Start
auf Downloads, und ein Ausfall des Marketplace legt den Arbeitsplatz lahm.

### Einzelinstanz-Anwendungen

VS Code, Chrome und Thunderbird lassen sich nur einmal je Nutzer starten. Ein zweiter Aufruf meldet
sich bei der laufenden Instanz und beendet sich — ohne Fenster, ohne Fehlermeldung. Im Katalog
bekommt eine solche Anwendung deshalb ihr **festes Display** eingetragen, wenn das Image sie
ohnehin selbst startet. OTA blendet sie dann nur ein, statt sie erneut zu starten.

Erkennbar am schwarzen Bild trotz „läuft": Prüfe mit
`docker exec <container> pgrep -a <anwendung>`, ob sie bereits auf einem anderen Display läuft.

## Profil und Drift

Nutzer verändern ihre Umgebung — das ist erwünscht. Für die Fälle, in denen etwas verbindlich bleiben
muss:

- **„Enforce"-Pfade**: definierte Dateien werden bei *jedem* Start aus dem Skeleton überschrieben.
  Für Firmen-Zertifikate, Proxy-Einstellungen, Registry-URLs. Sparsam einsetzen — jede Datei hier ist
  eine, die der Nutzer nicht anpassen kann
- **Profil zurücksetzen**: für einzelne Nutzer oder ganze Gruppen, mit automatischer Sicherung

## Builds

Builds laufen **serialisiert** — nur einer gleichzeitig, damit der Host nicht einbricht. Das Log
läuft live mit, Timeout 45 Minuten, jederzeit abbrechbar.

Ein nächtlicher Rebuild zur Aufnahme von Sicherheitsupdates ist optional. Er meldet, was sich
geändert hat, und aktiviert die neue Version **nicht** von selbst.

## Größe im Blick behalten

Ein Arbeitsplatz mit fünf Werkzeugen landet bei 12–18 GB. Er liegt **einmal** auf dem Host,
unabhängig von der Zahl der Nutzer. Trotzdem: vor dem Aufnehmen einer weiteren Anwendung prüfen, ob
sie den Alltag wirklich trägt.
