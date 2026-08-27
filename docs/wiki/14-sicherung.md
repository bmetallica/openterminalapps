# 14 · Sicherung und Wiederherstellung

*Für Administratoren.* ✅ Menüpunkt **Betrieb → Sicherung**

## Was gesichert wird

| Art | Inhalt | Voreinstellung |
|---|---|---|
| **Profile** | Das Home jedes Nutzers ohne Caches: Projekte, Einstellungen, SSH-Schlüssel, Git-Konfiguration | **an** |
| **Container** | Nur was ausserhalb des Home verändert wurde, ermittelt über `docker diff` | aus |
| **Datenbank** | Nutzer, Gruppen, Workspaces, Zuweisungen, Audit-Log | über `make backup` |

**Warum nicht der ganze Container?** Am laufenden System gemessen: Das Profil eines
Nutzers sind 326 MB, die Schreibschicht seines Containers 340 MB — ein vollständiger
Export wäre **4,8 GB**, und davon ist fast alles Basisimage, das aus dem Golden Image
ohnehin reproduzierbar ist. Es bei jedem Lauf und für jeden Nutzer erneut abzulegen
wäre verschwendeter Platz.

**Was ausgeschlossen wird**: Browser- und Editor-Caches, `node_modules`, `__pycache__`,
Sockets und Sperrdateien. In einem echten Profil schrumpfte das Archiv dadurch von 6.754
auf 355 Einträge — ohne dass eine Nutzerdatei fehlte. Die 306 MB Unterschied waren ein
heruntergeladener SDK-Cache.

## Von Hand sichern

*Betrieb → Sicherung → **Jetzt alle sichern***. Das sichert die Profile aller aktiven
Nutzer. Der Fortschritt erscheint in der Liste darunter.

Über die API lässt sich auch ein einzelner Nutzer sichern:

```bash
curl --cacert deploy/certs/ota-ca.crt -b cookie.txt \
  -X POST https://<host>:8443/api/backups/run \
  -H 'Content-Type: application/json' \
  -d '{"username":"anna.k","include_container":true}'
```

> Sichern funktioniert auch bei offener Session. Das ist Absicht — wer nur bei
> geschlossener Session sichert, sichert in der Praxis nie. Ein Editor, der gerade
> schreibt, kann eine Datei halbfertig im Archiv hinterlassen; für Quelltext und
> Einstellungen ist das vertretbar. Bei geschlossener Session ist es sauberer.

## Automatisch sichern

Im Reiter **Sicherung** den Schalter *Automatisch sichern* umlegen. Dann:

- **Uhrzeit** — Ortszeit des Servers. Am besten dann, wenn niemand arbeitet.
- **Wochentage** — nichts ausgewählt bedeutet: jeden Tag.
- **Was gesichert wird** — Profile und wahlweise die Container-Änderungen.
- **Aufbewahrung** — wie viele tägliche Stände bleiben, und wie viele zusätzliche
  wöchentliche.

Der Zeitplaner prüft minütlich und **holt einen Lauf nach**, wenn der Dienst zur
geplanten Minute gerade neu gestartet wurde. Ein verpasster Lauf fällt also nicht
einfach aus.

### Wie die Aufbewahrung rechnet

Behalten werden je Nutzer und Art die letzten *n* Stände. Aus den älteren bleibt je
Kalenderwoche der neueste, bis zur eingestellten Zahl. Bei der Voreinstellung — 7 täglich,
4 wöchentlich — reicht die Sicherung also etwa fünf Wochen zurück, ohne dass die Menge
unbegrenzt wächst.

Fehlgeschlagene Läufe verschwinden nach 30 Tagen. Sie belegen keinen Platz, verstellen
aber die Sicht.

## Wiederherstellen

In der Liste bei der gewünschten Sicherung auf **Wiederherstellen**. Der Dialog nennt
Nutzer und Zeitpunkt und sagt, was verloren geht.

**Zwei Dinge passieren dabei, beide bewusst:**

1. **Läuft noch eine Session des Nutzers, wird abgelehnt.** Ein Profil unter einem
   geöffneten Editor auszutauschen führt auf beiden Seiten zu Datenverlust. Beende die
   Session zuerst — im Reiter *Sessions*.
2. **Der bisherige Stand wird nicht gelöscht.** Er bleibt als
   `user.vor-wiederherstellung-<zeitstempel>` neben dem Profil liegen. Falls die
   Wiederherstellung doch nicht das Richtige war, lässt er sich zurückholen:

```bash
cd /srv/ota/profiles/<nutzer>
mv user user.verworfen
mv user.vor-wiederherstellung-<zeitstempel> user
chown -R 1000:1000 user
```

Schlägt das Entpacken fehl, schiebt OTA den alten Stand von selbst zurück — niemand
steht ohne Profil da.

Nach dem Entpacken wird die Eigentümerschaft auf **UID/GID 1000** gesetzt. Ohne das kann
der Container nicht in sein eigenes Home schreiben.

## Ablage auf ein Netzlaufwerk legen

Alle Sicherungen liegen unter **einem** Pfad — Vorgabe `/srv/ota/backups`, einstellbar
über `OTA_BACKUP_ROOT` in `deploy/.env`.

Genau deshalb kostet der Umzug auf NFS nichts an OTA:

```bash
# 1 · Laufende Sicherungen beiseite
systemctl stop ... # oder: cd deploy && docker compose stop api agent
mv /srv/ota/backups /srv/ota/backups.lokal

# 2 · NFS einhängen
mkdir -p /srv/ota/backups
echo 'nas:/export/ota-backups /srv/ota/backups nfs4 defaults,_netdev 0 0' >> /etc/fstab
mount /srv/ota/backups

# 3 · Bestand übernehmen
rsync -a /srv/ota/backups.lokal/ /srv/ota/backups/

# 4 · Weiter wie bisher
cd deploy && docker compose up -d
```

Die Oberfläche zeigt danach unter *Ablage* **„Netzlaufwerk"** statt „lokale Platte" —
daran lässt sich prüfen, ob der Mount wirklich greift.

> **`_netdev` in der fstab nicht vergessen.** Ohne diese Angabe versucht das System, das
> NFS vor dem Netzwerk einzuhängen; der Mount schlägt fehl, OTA schreibt dann munter in
> das leere lokale Verzeichnis darunter — und niemand merkt es, bis die Sicherung
> gebraucht wird.

## Prüfen, dass es funktioniert

```bash
./scripts/test-backup.sh
```

Der Test legt eine Markierung in ein echtes Profil, sichert, stellt wieder her und prüft,
dass die Markierung verschwunden und der alte Stand aufgehoben ist. Er prüft ausserdem,
dass ein normaler Nutzer weder die Sicherungen sieht noch eine auslösen kann, und dass
die Wiederherstellung bei laufender Session abgelehnt wird.

> **Ein Backup, dessen Wiederherstellung nie geprüft wurde, ist kein Backup.**
> Das gilt auch für die Datenbank — deren Wiederherstellung ist noch nicht automatisiert
> und gehört einmal von Hand durchgespielt.

## Was noch fehlt

- Die **Datenbanksicherung** läuft bisher nur über `make backup`, nicht über den Zeitplan
- **Container-Sicherungen** lassen sich anlegen, aber noch nicht über die Oberfläche
  zurückspielen
- Eine geprüfte **Wiederherstellung der Datenbank** ist Abnahmekriterium für M7
