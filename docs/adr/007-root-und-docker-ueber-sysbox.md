# ADR-007 · Root und Docker im Arbeitsplatz über Sysbox

**Stand:** angenommen
**Datum:** 2026-10-06

## Ausgangslage

Entwickler sollen in ihrem Arbeitsplatz root sein, Docker samt Compose benutzen und behalten, was
sie installiert haben. OTA härtet Arbeitsplätze bisher mit `cap_drop: ALL` und
`no-new-privileges`, löscht sie beim Beenden, und nur der Agent fasst Docker an
([ADR-002](002-nur-der-agent-fasst-docker-an.md)). Unter Dockers normaler Laufzeit (`runc`) ist
root im Container root auf dem Wirt.

## Entscheidung

Eine eigene **Arbeitsplatzklasse „Root"**, die ausschliesslich unter **Sysbox** (`sysbox-runc`)
läuft. Sysbox gibt jedem Container einen eigenen Benutzer-Namensraum: root im Container ist auf dem
Wirt ein unprivilegierter Nutzer (gemessen: UID 0 → 296608). Darin laufen `dockerd`, Compose und
`sudo` ohne `--privileged`. Fehlt Sysbox, wird der Start **abgelehnt**, nie auf `runc` mit
`--privileged` zurückgefallen.

Dazu: **angehalten statt gelöscht**, dieselbe Kennung und Adresse über alle Starts, Docker-Daten in
einem eigenen Volume je Platz, Platzgrenze je Vorlage, eigenes Recht `arbeitsplatz.root`.

## Alternativen

**Den Docker-Socket des Wirts einhängen.** Jeder Nutzer wäre root auf dem Wirt, sähe alle Container
— Keycloak, die Datenbank, fremde Arbeitsplätze — und seine Container umgingen den Router.
Ausgeschlossen.

**Docker-in-Docker mit `--privileged`.** Alle Rechte des Kernels im Arbeitsplatz; root darin ist mit
wenig Aufwand root auf dem Wirt. Hebt die gesamte Härtung auf.

**Rootless Podman im Arbeitsplatz.** Ohne Änderung am Wirt, aber nur mit gelockertem Seccomp und
AppArmor und `/dev/fuse` — für den ganzen Container. root im Arbeitsplatz löst es nicht (dafür
bräuchte es wieder `elevated`, also root auf dem Wirt), und „fast Docker" kostet im Alltag Zeit.

**Ein externer Docker-Server** (`DOCKER_HOST=ssh://…`). Hält Docker aus dem Wirt heraus, löst aber
root im Arbeitsplatz nicht. Bind-Mounts aus dem Zuhause (`./src:/app`) meinen dann Pfade auf dem
Server, die Netzprofile des Routers gelten dort nicht, und Trennung zwischen Nutzern muss eigens
gebaut werden. **Zurückgestellt**, nicht verworfen — für schwere Lasten denkbar (Uoktober.md, Teil D).

**Kata Containers / eine VM je Arbeitsplatz.** Stärkste Trennung (eigener Kernel), braucht aber KVM
und damit verschachtelte Virtualisierung — der Wirt ist selbst eine VM.

## Folgen

- Eine weitere Komponente im Kern: Sysbox muss zu Docker und Kernel passen. Geprüft mit Docker
  29.7, containerd 2.2, Kernel 6.12. Ein Update von Sysbox startet alle laufenden Root-Arbeitsplätze
  neu — ins Wartungsfenster.
- Die Installation verlangt ohne Vorbereitung, **alle** Container des Wirts zu löschen. Das wird mit
  `scripts/sysbox-einrichten.sh` umgangen (bip und Adressbereiche vorab auf die geltenden Werte
  gesetzt; dann genügt ein SIGHUP).
- Die inneren Container gehen durch den Router — die Netzprofile gelten für sie wie für den
  Arbeitsplatz. Ihr DNS ist der Router (`dockerd --dns`), weil `127.0.0.11` nicht weitergebbar ist.
- Root-Arbeitsplätze wachsen. Die Platzgrenze je Vorlage und die Liste unter Betrieb sind die
  Antwort darauf; gesichert wird die Schicht des Containers, nicht die Docker-Daten.
- Restrisiko: kein eigener Kernel. Ein schwerer Kernel-Fehler bleibt ein Weg nach draussen, wie bei
  jedem Container.
