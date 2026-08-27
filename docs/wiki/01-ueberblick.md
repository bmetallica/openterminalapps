# 1 · Überblick — was OTA ist

## Der Arbeitsplatz ist der Kern

OTA gibt jedem Nutzer **einen eigenen, dauerhaften Linux-Arbeitsplatz** im Browser. Darin sind seine
Werkzeuge installiert — VS Code, JetBrains, VSCodium, opencode, ein Terminal —, und jedes lässt sich
einzeln formatfüllend in den Browser holen.

Entscheidend ist, was sie sich teilen: **ein Zuhause.** Dieselben Projektverzeichnisse, derselbe
SSH-Schlüssel, dieselbe Git-Konfiguration, dieselbe Zwischenablage.

```
Arbeitsplatz von bmetallica
  ├─ Visual Studio Code   ← läuft
  ├─ IntelliJ IDEA CE     ← läuft
  ├─ VSCodium             ← nicht gestartet, kostet nichts
  ├─ opencode
  └─ Terminal
       alle auf  /home/bmetallica
```

## Der Unterschied zum App-Katalog-Modell

Andere Plattformen geben pro *Anwendung* einen Container. VS Code hier, IntelliJ dort — und derselbe
Repository-Klon liegt dreimal herum, mit drei Schlüsselbunden und drei Konfigurationen.

OTA dreht das um: **eine Maschine pro Mensch, viele Werkzeuge darin.**

Daraus folgt:

| | |
|---|---|
| **Vorkonfiguration** | Admins bauen den Arbeitsplatz als Golden Image — gesetzte Extensions, fertige Einstellungen, Firmen-Zertifikate. Versioniert, mit Rollback |
| **Identität** | Ein Nutzer, ein Container, eine Identität. Erst damit lohnen sich AD-Anmeldung und Netzlaufwerke |
| **Ressourcen** | Das Kontingent gehört zum Menschen, nicht zum Werkzeug. Nutzer A bekommt 4 Kerne, Nutzer B einen |

## Einzelne Anwendungen als Feature

Daneben kann OTA **eine Anwendung als eigenen Wegwerf-Container** starten. Das ist bewusst ein
Zusatz, kein zweites Fundament. Es lohnt sich für:

- Werkzeuge, die man **selten und isoliert** braucht — GIMP, LibreOffice, ein Wegwerf-Browser
- Den **Umstieg**: Was heute in Kasm läuft, läuft am ersten Tag auch in OTA
- Das **vorhandene Ökosystem**: Allein die offizielle Kasm-Registry führt 86 fertige Workspaces
  → [Kapitel 9](09-kasm-images-und-registries.md)

## Wer was sieht

| Rolle | Sicht |
|---|---|
| **Nutzer** (`users`) | Eigener Arbeitsplatz, zugewiesene Apps, eigene Einstellungen. Sonst nichts |
| **Administrator** (`admins`) | Zusätzlich: Workspaces, Golden Images, Nutzer, Gruppen, alle Sessions, Registries, Audit-Log |

Die Trennung wird serverseitig an jedem Endpunkt durchgesetzt, nicht nur im Menü.

## Technische Grundlage

- **Docker** auf Debian, kein Kubernetes nötig
- **Traefik** als Ingress mit TLS — Pflicht, nicht Kür: Ohne HTTPS funktioniert die Zwischenablage
  im Browser nicht ([Kapitel 4](04-zwischenablage.md))
- **KasmVNC** als Streaming-Engine, ein Display je Anwendung
- **PostgreSQL** für Nutzer, Templates, Sessions und Audit
