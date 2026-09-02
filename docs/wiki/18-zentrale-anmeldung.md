# 18 · Zentrale Anmeldung (Keycloak)

*Für Administratoren.* ✅ Anmeldung, Verzeichnis, fremde Anwendungen, Notzugang

Seit dem 2026-08-28 ist OTA nicht mehr sein eigener Identity Provider. Es ist das **Portal** über
einem zentralen Keycloak — und dessen Verwalter. Der Hintergrund, die Abwägungen und alle
Entscheidungen stehen in [`auth-roadmap.md`](../../auth-roadmap.md); hier steht, wie man damit
arbeitet.

## Drei Zuständigkeiten, sauber getrennt

| | Frage | Zuständig |
|---|---|---|
| **Keycloak** | Wer bist du? | Anmeldung, Identität, SSO, AD/LDAP, zweite Stufe (Passkey oder Einmalkennwort), Sitzungen |
| **OTA** | Welche Anwendungen darfst du **sehen und betreten**? | Katalog, Zugriff je Gruppe, Arbeitsplätze |
| **Die Anwendung** | Was darfst du **darin** tun? | Open-WebUI-Rechte, Grafana-Rollen, … |

Die dritte Zeile ist die, die man am leichtesten übergeht: **OTA baut das Rechtemodell fremder
Anwendungen nicht nach.** Es entscheidet, ob jemand die Kachel sieht und die Tür aufgeht.

## Wie sich jemand anmeldet

```
Browser ──► OTA ──► Keycloak ──► OTA setzt sein eigenes Cookie ──► Arbeitsplatz
```

Keycloak liegt unter **`/auth` derselben Adresse** wie OTA. Das ist kein Schönheitsfehler, sondern
Voraussetzung: Eine Desktop-Verknüpfung öffnet ein Fenster ohne Adressleiste, und ein Sprung zu
einer fremden Herkunft verliesse dessen Geltungsbereich. So bleibt die Anmeldung im selben Fenster.

**Hinter der Haustür gilt OTAs Cookie.** Vor jedem Session-Pfad steht Traefiks `forwardAuth`, auch
vor dem WebSocket-Handshake — und ein Upgrade lässt sich nicht nach Keycloak umleiten.

## Der Notzugang

**`https://<host>:8443/notfall`** — ein lokales Administratorkonto, das ohne Keycloak funktioniert.

`make admin` legt es beim Einrichten an (`notfall`) und druckt sein Passwort **einmal**. Es ist der
Weg herein, wenn Keycloak nicht antwortet oder eine Verzeichniskonfiguration die Anmeldung
blockiert. Ohne ihn wäre eine Anlage nach einem solchen Fehler nicht mehr zu betreten.

Er ist bewusst genau **einer**, unter einer eigenen Adresse, und jede Anmeldung darüber steht im
Protokoll. Die Übernahme (unten) lässt ihn unangetastet.

## Ein Active Directory anbinden

**Einstellungen → Verzeichnis in Keycloak.**

Adresse, Basis, Dienstkonto eintragen, **Verbindung testen**, speichern, **Jetzt abgleichen**. OTA
schreibt die Anbindung über die Verwaltungsschnittstelle nach Keycloak; die Keycloak-Konsole muss
niemand öffnen.

```
Adresse       ldaps://dc01.firma.local:636
Basis         OU=Users,DC=firma,DC=local
Dienstkonto   CN=svc-keycloak,OU=Dienste,DC=firma,DC=local
```

Angelegt wird sie **nur lesend** (`editMode: READ_ONLY`): OTA schreibt nie ins Verzeichnis zurück.
Das Kennwort des Dienstkontos geht nur hinein — leer lassen heisst „nicht anfassen", nicht
„löschen".

> **Begriffsfalle.** In Keycloak ist das eine *Benutzer-Föderation* und **kein** „Identity
> Provider" — so heissen dort fremde OIDC- und SAML-Anbieter. Wer im falschen Menü sucht, findet
> nichts.

Ein Verzeichniseintrag kann **kein bestehendes Konto übernehmen.** Steht im AD ein `bmetallica` und
gibt es hier schon eines, wird der Import abgelehnt. Das ist der Angriff, gegen den die Regel
steht: Wer im Verzeichnis etwas anlegen darf, legte sonst einen Eintrag mit dem Namen des
Administrators an.

## Die zweite Stufe

Sie liegt in Keycloak, nicht mehr in OTA. Was in OTA ein Feld an der Gruppe war (`require_totp`),
ist dort ein Anmeldefluss mit einer Bedingung — und Gruppen taugen als Bedingung nicht, Rollen
schon. Deshalb:

```
Realm-Rolle  zweiter-faktor  →  wer sie trägt, richtet beim Anmelden einen zweiten Faktor ein
```

OTA hängt die Rolle an jeden, dessen Gruppe sie verlangt. Der Anmeldefluss ist eine **Kopie** des
eingebauten (`ota-browser`) — Keycloak lässt eingebaute nicht ändern, und eine Kopie lässt sich mit
einem Handgriff wieder abhängen: `browserFlow` zurück auf `browser`.

### Passkey oder Einmalkennwort ✅

Als zweiter Faktor geht beides. Wer einen **Passkey** hinterlegt hat — Fingerabdruck,
Gesichtserkennung, ein Sicherheitsschlüssel —, weist sich damit aus; wer keinen hat, bekommt wie
bisher die Abfrage des **Einmalkennworts**.

Hinterlegt wird ein Passkey in Keycloaks Kontoverwaltung unter *Signing in → Passkey*. Die dafür
nötige Aktion (`webauthn-register`) ist im Realm ab Werk eingeschaltet; im Browser meldet sich OTA
dabei als „OpenTerminalApps".

```
Bedingung: Rolle zweiter-faktor            REQUIRED
├─ ota-passkey                             ALTERNATIVE
│    ├─ Bedingung: beim Nutzer eingerichtet  REQUIRED
│    └─ WebAuthn                             REQUIRED
└─ ota-einmalkennwort                      ALTERNATIVE
     └─ Einmalkennwort                       REQUIRED
```

> **Warum zwei Zweige und nicht einfach zwei Alternativen nebeneinander.**
>
> Der naheliegende Aufbau wäre, Einmalkennwort und Passkey beide auf ALTERNATIVE zu stellen: „such
> dir was aus". Am 2026-09-02 gegen dieses Keycloak gemessen: Wer die Rolle trägt und **noch keins
> von beiden** eingerichtet hat, kommt dann gar nicht mehr herein — die Anmeldung endet mit
> *„Invalid username or password"*. Also nicht nur eine Sperre, sondern eine mit einer
> irreführenden Meldung, bei der niemand auf die Ursache käme.
>
> Auch eine vorgemerkte Ersteinrichtung hilft nicht: Vorgemerkte Aktionen laufen **nach** der
> Anmeldung, und so weit kommt es gar nicht.
>
> Mit den zwei Zweigen fällt jemand ohne Passkey durch die erste Bedingung und landet im zweiten
> Zweig, wo das Einmalkennwort notfalls seine eigene Einrichtung anstösst. Es gibt damit keinen
> Zustand, in dem niemand mehr hereinkommt — und genau das prüft `scripts/test-authz.sh` bei jedem
> Lauf.

Wer einen Passkey hat, bekommt das Einmalkennwort nicht mehr angeboten. Das ist bewusst so: Zwei
Wege nebeneinander sind zwei Wege, die ein Angreifer probieren kann, und der schwächere gewinnt.

## Fremde Anwendungen anbinden

**Anwendungen → Anwendung hinzufügen.** OTA legt den OIDC-Client in Keycloak an und zeigt die
Konfiguration zum Übertragen.

Zwei Schlösser sichern das ab, und sie sichern gegen Verschiedenes:

* Das Recht **`anwendungen.verwalten`**, getrennt von `templates.manage`. Wer Arbeitsplätze
  zusammenstellt, erzeugt nicht nebenbei Zugänge, über die Identitäten nach draussen fliessen.
* Eine **Liste erlaubter Ziele** unter Einstellungen. Sie ist im Auslieferungszustand **leer** und
  erlaubt dann nichts — nicht alles.

Warum das nötig ist: In einem OIDC-Client steht eine Zeile, die alles entscheidet.

```
Redirect-URI    https://ai.firma.de/oauth/oidc/callback
```

Dorthin schickt Keycloak nach der Anmeldung den Code. **Wer sie bestimmt, bestimmt, wohin die
Identität der Nutzer fliesst.** Im Protokoll sieht das aus wie „hat eine Anwendung hinzugefügt".

Das Client-Geheimnis kommt **einmal** zurück und steht danach nur noch in Keycloak.

Zum Zertifikat — die Stelle, an der die erste Anbindung verlässlich scheitert — siehe
[Kapitel 10](10-zertifikate-und-https.md).

## Bestandskonten übernehmen

**Einstellungen → Übernahme.** Sie holt lokale Konten nach Keycloak: Name, E-Mail, Gruppen und die
Rolle für die zweite Stufe wandern mit, das Passwort wird **einmalig neu** vergeben und muss beim
ersten Anmelden gewechselt werden.

Warum nicht die vorhandenen Hashes mitnehmen: Ein Import hängt an übereinstimmenden Parametern und
scheitert im Zweifel **still** — es fällt erst auf, wenn sich jemand nicht anmelden kann.

Drei Eigenschaften, die dabei nicht verhandelbar sind:

* **Ohne Notfallkonto läuft der Lauf nicht.** Wer alle Konten auf einen Dienst umstellt, der
  ausfallen kann, braucht vorher einen Weg zurück.
* **Der lokale Hash geht weg.** Ihn stehenzulassen hiesse, einen zweiten Weg offenzuhalten — an
  Keycloak und der zweiten Stufe vorbei.
* **Es gibt einen Rückweg je Konto.** *Zurücknehmen* macht ein einzelnes Konto wieder lokal und
  deaktiviert es in Keycloak. Ein Weg zurück, den es erst im Notfall zu erfinden gilt, ist keiner.

Wer übernommen ist und sich unter `/login` anzumelden versucht, bekommt keinen „falsches
Passwort"-Fehler, sondern den Hinweis, wo der richtige Eingang ist.

## Das Aussehen der Anmeldemaske

Sie trägt OTAs Farben — dieselbe Fläche, dieselbe Schrift, derselbe helle Hauptknopf. Das Thema
liegt unter `deploy/keycloak-theme/ota` und wird als Verzeichnis eingehängt; ein Bau-Schritt ist
nicht nötig.

> **Wer daran arbeitet, muss den Themenspeicher abschalten.** Keycloak liest eine Themendatei
> einmal und hält sie fest — ein Neustart räumt das nicht ab, und der Browser darf sie 30 Tage
> behalten. Man ändert dann eine Datei und sieht nichts.
>
> ```
> KEYCLOAK_THEME_CACHE=false
> KEYCLOAK_THEME_MAX_AGE=-1
> ```
>
> Für den Betrieb wieder auf `true` und `2592000`.

### Die Maske folgt dem Gewand

Wer in OTA auf **hell** gestellt hat, bekommt auch die Anmeldemaske hell. Das geht, weil Keycloak
hinter demselben Ingress liegt wie OTA — also auf derselben Herkunft, und damit liest die Maske
denselben `localStorage`, in dem OTA die Wahl ablegt (`resources/js/gewand.js` im Theme).

Ohne das bekäme jemand mit hellem Gewand eine dunkle Anmeldemaske und danach eine helle Anwendung.
Das sieht nicht nach einer Anlage aus, sondern nach zweien — und genau diesen Zweifel darf eine
Anmeldeseite nie auslösen.

> **Wenn Keycloak auf einem eigenen Namen läuft**, ist es eine fremde Herkunft und die Maske bleibt
> beim dunklen Gewand. Das ist kein Fehler, sondern die Grenze von `localStorage`; es fällt nur
> auf, wenn jemand hell eingestellt hat.

## Ein vorhandenes Keycloak benutzen

Wer schon eines betreibt, setzt in `deploy/.env`:

```
OTA_IDP_MODE=vorhanden
OTA_KEYCLOAK_URL=https://auth.firma.de
OTA_KEYCLOAK_REALM=firma
OTA_KEYCLOAK_SECRET=<Geheimnis des Clients ota-manager>
```

Dort ist OTA **Gast**: Der Realm gehört jemand anderem. Es löscht keine Konten (nur deaktivieren),
fasst nur Gruppen unterhalb von `/ota` an, und die Verzeichnisanbindung gehört vermutlich schon
jemandem. OTA stellt beim Verbinden fest, welche Rechte es hat, und zeigt nur, was wirklich geht —
statt einen Knopf anzubieten, der in einem 403 endet.

Der Client `ota-manager` und der Realm müssen dort **vorher** angelegt sein; `make identity` fasst
ein fremdes Keycloak nicht an.
