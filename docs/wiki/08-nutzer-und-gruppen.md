# 8 · Nutzer, Gruppen und Rechte

*Für Administratoren.* 🔨 M2, AD-Anbindung 🔨 M6

## Grundsatz

Die Nutzerverwaltung von OTA ist **eigenständig**. LDAP/AD und OIDC sind zuschaltbare Zusätze, keine
Voraussetzung. Es gibt keinen Zwang zu einem externen Identity-Provider.

## Rollen

Zwei Systemgruppen, nicht löschbar:

| Gruppe | Darf |
|---|---|
| **`admins`** | Alles: Workspaces, Golden Images, Nutzer, Gruppen, Zuweisungen, Registries, alle Sessions, Audit-Log, globale Einstellungen |
| **`users`** | Nur das Eigene: zugewiesene Workspaces starten, eigene Sessions verwalten, eigene Einstellungen |

Weitere Gruppen sind frei anlegbar und dienen der Zuweisung und den Ressourcen-Abweichungen
([Kapitel 6](06-ressourcen-und-zuteilung.md)).

Im Datenmodell existieren feingranulare Rechte (`images.manage`, `users.manage`, `sessions.view_all`,
`settings.manage`, `audit.view`), damit später Rollen wie „Support" (darf Sessions sehen, nichts
konfigurieren) ohne Schemaänderung möglich sind.

### Durchsetzung

An drei Stellen, nicht nur im Menü:

1. Route-Schutz im Frontend — Komfort
2. Prüfung an **jedem** API-Endpunkt — die Wahrheit
3. Abfrage-Beschränkung: Nicht-Admins bekommen ausschließlich die eigenen Datensätze; nicht „alles
   holen und im Frontend filtern"

## Passwörter und Anmeldung

- **Argon2id**, Mindestlänge 12, Abgleich gegen bekannt kompromittierte Passwörter
- Sitzung über `HttpOnly`/`Secure`/`SameSite`-Cookie, kurze Gültigkeit, Erneuerung mit Rotation
- Bei Fehlversuchen exponentiell steigende Wartezeit je Konto und IP, Sperre nach N Versuchen
- Alles im Audit-Log

## Zwei-Faktor

TOTP je Nutzer aktivierbar, je Gruppe erzwingbar. Recovery-Codes bei der Einrichtung.
WebAuthn/Passkeys 🔨 M9.

## Active Directory und LDAP 🔨 M6

Unter *Authentifizierung → LDAP/AD*:

- LDAPS oder StartTLS, Bind-DN und Suchbasis
- Login-Attribut wählbar (`sAMAccountName` oder `userPrincipalName`)
- **Gruppen-Mapping**: AD-Gruppe → OTA-Gruppe
- Nutzeranlage beim ersten Login, optional
- Nächtlicher Abgleich für Deaktivierungen

Der **Test-Button** prüft die Verbindung und zeigt für einen Beispielnutzer, welche OTA-Gruppen sich
daraus ergäben — bevor gespeichert wird.

> **Ein lokaler Administrator bleibt immer aktiv.** Die Oberfläche verhindert das Löschen des letzten
> lokalen Admin-Kontos. Ein LDAP-Ausfall darf niemanden aussperren.

## Netzlaufwerke im Arbeitsplatz 🔨 M6

Erst mit dem Arbeitsplatz sinnvoll: ein Nutzer, ein Container, eine Identität. Vier Wege, geordnet
nach Sauberkeit:

| Weg | Was passiert | Bewertung |
|---|---|---|
| **1 · Kerberos-SSO mit Delegation** | Browser meldet sich per Negotiate an, OTA holt per eingeschränkter Delegation ein Ticket für den Fileserver | Sauberste Lösung. **Ein Passwort erreicht OTA nie.** Verlangt SPNs und konfigurierte Delegation |
| **2 · Kerberos-Ticket-Injektion** | OTA prüft gegen AD, holt dabei ein Ticket und legt es in den Container. Mount per `sec=krb5` | **Standardweg.** Kein Passwort im Container, Ticket läuft nach ~10 h ab |
| **3 · Nutzer verbindet selbst** | Knopf im Container, Passworteingabe dort | **Immer verfügbar.** Null Risiko für die Plattform |
| **4 · Passwort-Durchreichung** | OTA hält das Passwort für die Sitzungsdauer | **Standardmäßig aus.** Macht OTA zum Passwortspeicher |

**Weg 4 ist bewusst nicht die Voreinstellung.** Er ist bequem, aber er vergrößert den Schadensradius
erheblich: Wer OTA kompromittiert, bekommt Passwörter statt nur Sitzungen. Wer ihn einschalten will,
sieht im Admin-UI einen unmissverständlichen Hinweis.

**Unabhängig vom Weg gilt:**
- Zugangsdaten niemals als Umgebungsvariable — über `docker inspect` lesbar und in Logs sichtbar
- Niemals ins Golden Image und nie ins persistente Profil
- Ablage in einer `tmpfs`-Datei mit `0600`, die nie auf Platte geht
- Damit Dateirechte auf den Shares stimmen, wird die UID/GID aus dem Verzeichnis übernommen

## Offboarding

Beim Ausscheiden: Konto deaktivieren, Sessions beenden, Profil archivieren, dann löschen. Profile
enthalten personenbezogene Daten (SSH-Schlüssel, Browser-Verlauf) und unterliegen der DSGVO.

## Audit-Log

Erfasst Anmeldungen, Session-Start und -Ende sowie alle administrativen Änderungen — **keine
Inhalte**. Aufbewahrung konfigurierbar, Vorgabe 90 Tage, CSV-Export.

Session-Recording und Tastaturprotokollierung sind **bewusst nicht implementiert**. Falls später
gewünscht: vorher Mitbestimmung und Zweckbindung klären.
