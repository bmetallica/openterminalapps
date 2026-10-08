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

## Die Eingänge ✅

*Seit dem 2026-10-08.* Es gibt zwei Eingänge, und nur zwei:

| Adresse | Für wen | Was passiert |
|---|---|---|
| **`/`** (jede Adresse) | alle | weiter zur zentralen Anmeldung (Keycloak) |
| **`/notfall`** | das Notfallkonto | lokale Maske, an Keycloak vorbei — für den Fall, dass es ausfällt |

**`/login`** ist kein dritter Eingang mehr, sondern ein Übergang:

- Gibt es **keine lokalen Konten** ausser dem Notfallkonto mehr, leitet `/login` sofort zur
  zentralen Anmeldung weiter.
- Gibt es noch welche (Bestandskonten aus der Zeit vor Keycloak), zeigt es die Maske. Meldet sich
  ein solches Konto dort an, **zieht es um** (unten) und wird zur zentralen Anmeldung weitergeleitet.
- Wer dort den Namen eines Kontos der zentralen Anmeldung eingibt, landet bei Keycloak — mit dem
  Namen schon im Feld.
- Mit `?fehler=…` (wenn bei Keycloak etwas schiefging) bleibt die Seite stehen und sagt, was war.
  Sonst liefe der Browser in eine Schleife.

Bis zum 2026-10-08 zeigte `/login` jedem eine lokale Maske. Ein Konto, das in OTA angelegt wurde,
kam **nur** dort herein — an der zentralen Anmeldung und ihrer zweiten Stufe vorbei. Gefunden auf
der Produktivanlage.

## Konten anlegen und pflegen ✅

*Seit dem 2026-10-08.* **Verwaltung → Nutzer → anlegen** legt das Konto **in Keycloak** an:

- **Das Startpasswort vergibt die Verwaltung.** Ob es beim ersten Anmelden geändert werden muss,
  auch (Schalter „Beim ersten Anmelden ändern", Vorgabe: ja). Es muss die Passwortregel von Keycloak
  erfüllen; eine Ablehnung kommt mit Keycloaks Begründung zurück.
- **Name, E-Mail, Gruppen, aktiv/gesperrt** und die Rolle für die zweite Stufe hält OTA in Keycloak
  nach, bei jeder Änderung. Die Gruppen sind Pflicht dort: Keycloak gibt sie bei jedem Anmelden mit,
  und OTA übernimmt sie — eine Gruppe, die nur in OTA stünde, wäre beim nächsten Anmelden weg.
- **Ein neues Passwort** aus der Verwaltung gilt in Keycloak, wieder wahlweise zum Ändern beim
  nächsten Anmelden.
- **Zweiten Faktor zurücksetzen** entfernt Einmalkennwort und Passkeys in Keycloak.
- **Löschen** entfernt das Konto aus OTA und **sperrt** es in Keycloak; gelöscht wird dort nie
  (ein Keycloak gehört womöglich noch anderen Anwendungen). Ohne die Sperre legte die nächste
  Anmeldung das Konto in OTA einfach wieder an. Wird derselbe Name später wieder angelegt, verknüpft
  OTA das gesperrte Konto und schaltet es wieder frei.
- **Ein Konto aus dem Verzeichnis** (AD/LDAP über die Föderation) gehört dem Verzeichnis: Name,
  Adresse und Passwort kommen von dort. Die Verwaltung setzt ihm kein Passwort (409); Gruppen und
  aktiv/gesperrt gehen trotzdem.

**Lokale Konten** entstehen über die Verwaltung nicht mehr. Lokal ist nur das Notfallkonto
(`make admin`, Einstellungen → Notfallkonto).

## Mein Konto bei der zentralen Anmeldung ✅

*Seit dem 2026-10-08.* Passwort und zweiter Faktor eines Kontos der zentralen Anmeldung stehen in
Keycloak, und dort werden sie geändert. **Mein Konto** führt hin und holt zurück (Keycloaks
„Application-Initiated Actions"): OTA sieht dabei kein Passwort, Keycloaks Passwortregel und zweite
Stufe gelten wie beim Anmelden.

| | Konto der zentralen Anmeldung | aus dem Verzeichnis | Notfallkonto |
|---|---|---|---|
| Passwort ändern | Knopf → Keycloak | **im Verzeichnis**, wie in der Firma üblich | Formular in OTA |
| Einmalkennwort | Knopf → Keycloak (`CONFIGURE_TOTP`) | Knopf → Keycloak | OTAs eigenes |
| Passkey | Knopf → Keycloak (`webauthn-register`) | Knopf → Keycloak | — |
| Ansehen, entfernen | Keycloaks Kontoseite (verlinkt) | dito | in OTA |

Die lokalen Wege (`/api/auth/password`, `/api/auth/totp/…`) lehnen ein solches Konto ab (409) —
dort gesetzt, wirkte es an der Anmeldung nicht und öffnete einen Weg an ihr vorbei.

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

### ldaps und die CA des Verzeichnisses ✅

`ldaps://…:636` ist der Weg; StartTLS auf 389 bietet die Oberfläche nicht an. Keycloak prüft das
Zertifikat des Verzeichnisses und kennt ab Werk nur die öffentlichen CAs der Java-Laufzeit. Stammt
das Zertifikat aus der Firmen-PKI, gehört deren CA als PEM-Datei nach
**`deploy/keycloak-truststore/`**, danach `docker restart ota-keycloak`. Das Verzeichnis ist
seit dem 2026-09-25 nach `/opt/keycloak/conf/truststores` eingehängt; vorher liess sich ein solches
Verzeichnis gar nicht verschlüsselt anbinden.

**Verbindung testen** sagt seitdem auch, *warum* es scheitert — Keycloak meldet den Grund, OTA las
ihn nur nie:

| Meldung | Heisst |
|---|---|
| „die verschlüsselte Verbindung scheitert" | CA fehlt im Truststore, oder das Zertifikat passt nicht zur Adresse (`ldaps://<IP>` braucht die IP im Zertifikat) |
| „Namen … nicht auflösen" | DNS des Hosts |
| „Am Port antwortet kein Verzeichnis" | falscher Port — `ldaps://` gehört zu 636 |
| „nicht erreichbar" | Firewall, Routing, oder das Verzeichnis läuft nicht |

Steht das Verzeichnis jenseits einer Firewall: [Kapitel 24](24-hinter-nat.md).

> **Begriffsfalle.** In Keycloak ist das eine *Benutzer-Föderation* und **kein** „Identity
> Provider" — so heissen dort fremde OIDC- und SAML-Anbieter. Wer im falschen Menü sucht, findet
> nichts.

Ein Verzeichniseintrag kann **kein bestehendes Konto übernehmen.** Steht im AD ein `bmetallica` und
gibt es hier schon eines, wird der Import abgelehnt. Das ist der Angriff, gegen den die Regel
steht: Wer im Verzeichnis etwas anlegen darf, legte sonst einen Eintrag mit dem Namen des
Administrators an.

## Die Passwortregel ✅

Der Realm verlangt seit dem 2026-09-04 mindestens **zwölf Zeichen**, und dass das Passwort weder
der Anmeldename noch die Mailadresse ist:

```
length(12) and notUsername(undefined) and notEmail(undefined)
```

Dieselbe Untergrenze gilt in OTAs eigener Anmeldung seit jeher. Ohne diese Zeile war der
**Hauptweg** schwächer als der Notzugang — Keycloak nimmt ohne Regel jede Länge, auch ein Zeichen.

Gesetzt wird sie von `scripts/keycloak-init.sh`, bei der Anlage **und** bei einem Realm, den es
schon gibt. Verschärfen lässt sie sich über `OTA_KC_PASSWORTREGEL` in `deploy/.env`, danach
`make identity`. Bestehende Passwörter bleiben gültig, bis sie das nächste Mal geändert werden —
Keycloak prüft die Regel beim Setzen, nicht rückwirkend.

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
* Eine **Liste erlaubter Ziele** unter **Einstellungen → Anwendungen**. Sie ist im
  Auslieferungszustand **leer** und erlaubt dann nichts — nicht alles. Solange sie leer ist, zeigt
  die Seite der Web-Anwendungen einen Knopf dorthin.

Eingetragen wird eine **Herkunft**, also Schema, Host und gegebenenfalls Port, ohne Pfad: etwa
`https://ai.firma.de` oder `http://192.168.66.225:3000`. Die Rückadresse einer Anwendung muss mit
einer davon beginnen. `http://` ist erlaubt und wird in der Liste als *unverschlüsselt* markiert —
der Anmeldecode geht dann im Klartext über die Leitung. Platzhalter (`*`) nimmt OTA nicht an.
Wird ein Ziel entfernt, bleiben Anwendungen dorthin angelegt, lassen sich aber nicht mehr ändern.

Warum das nötig ist: In einem OIDC-Client steht eine Zeile, die alles entscheidet.

```
Redirect-URI    https://ai.firma.de/oauth/oidc/callback
```

Dorthin schickt Keycloak nach der Anmeldung den Code. **Wer sie bestimmt, bestimmt, wohin die
Identität der Nutzer fliesst.** Im Protokoll sieht das aus wie „hat eine Anwendung hinzugefügt".

Das Client-Geheimnis kommt **einmal** zurück und steht danach nur noch in Keycloak.

Zum Zertifikat — die Stelle, an der die erste Anbindung verlässlich scheitert — siehe
[Kapitel 10](10-zertifikate-und-https.md).

### Eine Uhr für OTA und die Anwendungen ✅

*Seit dem 2026-10-08.* Wer in OTA angemeldet ist, kommt in eine angebundene Anwendung **ohne
Anmeldemaske** — solange er in OTA angemeldet ist, nicht nur eine halbe Stunde lang.

Vorher liefen zwei Uhren nebeneinander: OTAs eigene Sitzung (Einstellungen → *Abmelden nach
Untätigkeit*, etwa acht Stunden) und Keycloaks SSO-Sitzung (Vorgabe 30 Minuten ohne Kontakt).
Nach der Anmeldung arbeitet man nur noch mit OTAs Cookie, Keycloak hört nichts mehr. Nach einer
halben Stunde war man in OTA noch angemeldet, aber Open WebUI zeigte die Maske.

Jetzt gilt:

* **Gleiche Frist.** OTA stellt Keycloaks Leerlauf-Frist auf seine eigene — beim Start und bei
  jeder Änderung in den Einstellungen. Die Obergrenze einer SSO-Sitzung liegt bei einer Woche, weil
  OTA selbst keine kennt; Keycloaks Vorgabe von zehn Stunden hätte jeden, der länger am Stück
  arbeitet, hinausgeworfen.
* **Wachhalten.** Solange in OTA gearbeitet wird, frischt OTA die Keycloak-Anmeldung alle fünf
  Minuten auf. Das Refresh-Token dafür liegt als httponly-Cookie im Browser (`ota_kcwach`, nur für
  `/api`), nicht in der Datenbank — es gehört zu dieser einen Anmeldung auf diesem Gerät.
* **Gemeinsam enden.** Kennt Keycloak die Sitzung nicht mehr — anderswo abgemeldet, in der
  Konsole beendet —, endet bei der nächsten Auffrischung auch die Sitzung in OTA. Antwortet
  Keycloak nur gerade nicht, bleibt alles, wie es ist.

Wer über `/notfall` angemeldet ist, hat keine Keycloak-Sitzung; für ihn gibt es auch kein SSO.

> **Beim Auffrischen spricht OTA Keycloak intern an** (`http://keycloak:8080`), der Browser hat
> sich aber unter der öffentlichen Adresse angemeldet. Keycloak vergleicht beim Auffrischen den
> Aussteller im Token mit der Adresse, unter der er gefragt wird. OTA gibt deshalb die öffentliche
> Adresse aus dem Token als `X-Forwarded-*` mit — dieselben Kopfzeilen, die Traefik für den Browser
> setzt.

## Bestandskonten übernehmen

**Am einfachsten zieht ein Konto selbst um — beim nächsten Anmelden** (*seit dem 2026-10-08*):
Meldet es sich unter `/login` mit seinem lokalen Passwort an, legt OTA es in Keycloak an, **mit
genau diesem Passwort**, löscht den lokalen Hash und leitet zur zentralen Anmeldung weiter. Kein
Einmal-Passwort, kein Import von Hashes — OTA kennt das Passwort in diesem Moment ohnehin. Gibt es
in Keycloak schon ein Konto dieses Namens, wird verknüpft und dessen Passwort nicht angefasst. Ist
jenes Konto dort **gesperrt** (meist, weil es in OTA einmal gelöscht wurde), zieht nichts um: Das
Konto meldet sich weiter lokal an, bis die Verwaltung es klärt — etwa, indem sie das lokale Konto
löscht und neu anlegt; das verknüpft das gesperrte und entsperrt es mit dem vergebenen Passwort.
Antwortet Keycloak nicht, kommt das Konto lokal herein und zieht beim nächsten Mal um.

Für Konten, die sich lange nicht anmelden, gibt es den Lauf von Hand:

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

## Die Keycloak-Konsole ist erreichbar — mit Absicht

Der mitgelieferte Keycloak liegt hinter Traefik unter `/auth`, und dazu gehört auch seine
**Verwaltungsoberfläche** unter `/auth/admin/`. Wer OTA erreicht, erreicht also auch sie.

**Das ist eine Entscheidung, keine Nachlässigkeit.** OTA verwaltet Keycloak von innen — für den
Alltag muss dort niemand hinein. Aber wenn doch einmal etwas klemmt, das OTAs Oberfläche nicht
abdeckt (ein Anmeldefluss, ein Zertifikat der Föderation, ein Blick in die Sitzungen eines Kontos),
ist die Konsole der einzige Weg. Sie zuzumauern hiesse, sich im Fehlerfall selbst auszusperren.

Was daran hängt, und was der Betrieb dafür schuldet:

* **Das Passwort des Keycloak-Administrators ist damit so wichtig wie das des Wirts.** Es steht in
  `deploy/.env` (`KEYCLOAK_ADMIN_PW`), wird von `make setup` erzeugt und sollte nie ein zweites Mal
  irgendwo auftauchen.
* **Der zweite Faktor gehört auf dieses Konto**, nicht nur auf die der Anwender.
* **Die Bremse gegen Durchprobieren steht** — Keycloak sperrt nach fünf Fehlversuchen für 15
  Minuten, das gilt auch an der Konsole.
* **Diese Rechnung gilt für ein Intranet.** Sobald OTA aus dem Internet erreichbar wird, kippt sie:
  Dann gehört vor `/auth/admin` eine Einschränkung auf bekannte Adressen (`ipAllowList` in Traefik,
  `deploy/traefik/dynamic/middlewares.yml`). Der Anmeldeweg der Nutzer ist davon nicht betroffen —
  der läuft über `/auth/realms/…`, und OTAs eigener Zugriff geht ohnehin durch das interne Netz und
  nicht über Traefik.

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
