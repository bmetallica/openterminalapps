# Auth-Roadmap — OTA als Anwendungsportal über einem zentralen Identity Provider

*Stand 2026-08-28. **Entwurf zum Durchdenken, nicht zum Bauen.** Nichts hiervon ist umgesetzt.*

Dieses Dokument steht neben [`roadmap.md`](roadmap.md) und beschreibt einen Umbau, der tiefer geht
als alles bisher: Er berührt jeden Weg, auf dem jemand in OTA hineinkommt.

---

## 1 · Warum überhaupt

Heute ist OTA sein eigener Identity Provider. Das reicht für OTA und für nichts sonst:

```
Browser ──► OTA ──► eigene Nutzertabelle
                    Argon2id, JWT im HttpOnly-Cookie, TOTP, LDAP-Bind
```

Sobald eine **zweite** Anwendung dazukommt — Open WebUI ist der Anlass, aber es wäre auch Grafana
oder GitLab —, gibt es genau drei Möglichkeiten:

1. Jede Anwendung bekommt ihre eigene Benutzerverwaltung. Dann pflegt jemand dieselben Menschen
   dreimal, und beim Austritt vergisst er die dritte.
2. OTA reicht Benutzername und Passwort weiter. Das ist der Weg, der bei
   [§17.9](plan.md) ausdrücklich verworfen wurde, und er wird durch eine zweite Anwendung nicht
   besser.
3. OTA wird selbst ein vollwertiger OIDC-Provider. Das heisst: Autorisierungs-Code-Fluss,
   Token-Signatur und -Rotation, Discovery, JWKS, Consent, Refresh-Token-Widerruf, Back-Channel-
   Logout. Alles davon ist Sicherheitscode, den man nicht „nebenbei richtig" schreibt.

Der vierte Weg ist der hier: **OTA hört auf, Identity Provider zu sein, und wird sein Manager.**

---

## 2 · Das Zielbild

```
                         ┌───────────────────────┐
                         │       Keycloak        │
                         │                       │
                         │ lokale Benutzer       │
                         │ LDAP/AD-Föderation    │
                         │ Gruppen, Rollen       │
                         │ MFA, Sessions, SSO    │
                         │ OIDC / SAML           │
                         └───────────┬───────────┘
                                     │
                       OIDC (Anmeldung) + Admin-API (Verwaltung)
                                     │
                         ┌───────────▼───────────┐
                         │          OTA          │
                         │                       │
                         │ Anwendungsportal      │
                         │ Zugriff je Anwendung  │
                         │ Nutzer-/Gruppenpflege │
                         │ Keycloak-Verwaltung   │
                         │ Arbeitsplätze         │
                         └──────┬───────┬────────┘
                                │       │
                    ┌───────────┘       └───────────┐
                    ▼                               ▼
             eigene Sessions                    Fremde Web-Apps
             (KasmVNC-Streams)          Open WebUI · Grafana · GitLab
                                              je als OIDC-Client
```

Drei Zuständigkeiten, sauber getrennt:

| | Frage | Zuständig |
|---|---|---|
| **Keycloak** | Wer bist du? | Anmeldung, Identität, SSO, AD/LDAP, MFA, Sitzungen |
| **OTA** | Welche Anwendungen darfst du **sehen und betreten**? | Katalog, Zugriff je Gruppe, Arbeitsplätze |
| **Anwendung** | Was darfst du **darin** tun? | Open-WebUI-RBAC, Grafana-Rechte, … |

Die dritte Zeile ist die wichtigste und die, die man am leichtesten übergeht: **OTA baut das
Rechtemodell fremder Anwendungen nicht nach.** OTA entscheidet, ob jemand die Kachel sieht und die
Tür aufgeht. Was dahinter erlaubt ist, entscheidet die Anwendung.

---

## 3 · Was das für den Bestand heisst

Ehrliche Bilanz. OTA hat heute rund **1.250 Zeilen** Authentifizierungs- und Identitätscode:

| Datei | Zeilen | Schicksal |
|---|---:|---|
| `api/ota/directory.py` | 282 | **entfällt** — LDAP macht Keycloak |
| `api/ota/identity.py` | 199 | **entfällt weitgehend** — die JIT-/Adopt-Regeln wandern nach Keycloak |
| `api/ota/routers/identity.py` | 117 | **wird umgebaut** — schreibt künftig gegen die Keycloak-Admin-API |
| `api/ota/routers/auth.py` | 399 | **schrumpft stark** — Passwortprüfung, Sperre, TOTP entfallen |
| `api/ota/security.py` | 250 | **bleibt grösstenteils** — Cookie, Rechte, Session-Eigentum |

Das ist der unbequeme Teil: **M6 ist gerade fertig geworden und würde grösstenteils wieder
abgeräumt.** 29 Prüfungen gegen ein echtes OpenLDAP im Container, die Filter-Maskierung, die
Adopt-Regeln, die Sicherung gegen Namensgleichheit — all das gibt es dann bei Keycloak schon.

Das spricht nicht gegen den Umbau. Es spricht dagegen, ihn als „kleine Erweiterung" zu planen.

### Was bleibt, und zwar zwingend

**OTA behält sein eigenes Sitzungscookie.** Das ist kein Rückschritt, sondern eine Notwendigkeit:

```
Browser ──► Traefik ──forwardAuth──► /api/internal/authz ──► darf er an diesen Bildschirm?
              │
              └──► /s/<session>/websockify   (WebSocket-Upgrade)
```

Vor **jedem** Request auf einen Session-Pfad steht `forwardAuth` — auch vor dem WebSocket-
Handshake. Ein Redirect nach Keycloak ist dort unmöglich: Ein WebSocket-Upgrade kann nicht
umgeleitet werden, und ein Stream, der alle fünf Minuten einen Autorisierungs-Code-Fluss
durchliefe, wäre kein Stream.

Also:

```
Anmeldung:  Browser ──► OTA ──► Keycloak ──► OTA setzt sein Cookie
Betrieb:    Browser ──► Traefik ──► forwardAuth prüft dieses Cookie
```

Keycloak steht an der Haustür. Dahinter gilt weiter OTAs Cookie. `read_token`, `token_epoch` und
`may_attach_to_session` bleiben unverändert.

### Der Anschlusspunkt ist schon da

`User` hat bereits die richtigen Felder:

```python
auth_provider: Mapped[str]          # "local" | "ldap"  →  künftig "keycloak"
external_id:   Mapped[str | None]   # künftig der Keycloak-`sub`
```

Die Nutzertabelle bleibt — sie ist die **Projektion**, nicht die Quelle. Sie muss bleiben, weil an
ihr Fremdschlüssel hängen: Sessions, Profile, Kontingente, Protokoll, Gruppenzuordnung. Wer sie
abschaffen wollte, müsste OTA neu schreiben.

---

## 4 · Das Identitätsmodell

Die zentrale Designentscheidung, und die einzige, die man später nicht mehr billig korrigiert.

### Führende Quelle: Keycloak. Schlüssel: `sub`.

```
Keycloak                          OTA
────────                          ───
sub  f7bca1d2-…      ──────────►  users.external_id      (eindeutig, unveränderlich)
preferred_username   ──────────►  users.username         (Anzeige, änderbar)
email, name          ──────────►  users.email, display_name
groups[]             ──────────►  users.groups           (bei jeder Anmeldung abgeglichen)
```

**Nicht der Benutzername ist der Schlüssel, sondern `sub`.** Der Grund ist nicht Theorie: In einem
AD wird geheiratet, und aus `anna.schmidt` wird `anna.mueller`. Mit dem Namen als Schlüssel wäre
das ein neuer Mensch mit leerem Zuhause.

### Und genau daran hängt ein Problem, das wir jetzt lösen müssen

`api/ota/security.py:240` bildet den Profilpfad so:

```python
return f"{root}/{user.username}/{tpl.slug}"      # /srv/ota/profiles/anna.schmidt/…
```

Dasselbe gilt für die eigene Ablage (`/srv/ota/userfiles/<username>`). Beide sind **nach dem Namen
benannt**, und der ist künftig veränderlich.

Drei Möglichkeiten:

1. **Pfade nach `sub` benennen.** Stabil, aber `/srv/ota/profiles/f7bca1d2-3e4a-…/` ist für eine
   Administration, die im Dateisystem nachsehen muss, unlesbar.
2. **Beim Namenswechsel umbenennen.** Lesbar, aber ein Verzeichniswechsel während einer laufenden
   Session ist ein sicherer Weg in kaputte Bind-Mounts.
3. **Nach `sub` benennen, mit einem Verweis unter dem Namen.** `f7bca1d2-…/` ist die Wahrheit,
   `anna.mueller → f7bca1d2-…` der Weg für Menschen. Beim Namenswechsel wandert nur der Verweis.

**Empfehlung: 3.** Sie kostet einmalig eine Migration bestehender Verzeichnisse und ist danach
gegen jede Umbenennung immun.

### Gruppen: zwei Ebenen, die nicht dasselbe sind

```
Keycloak-Gruppen              OTA-Zugriff                  Rechte in der Anwendung
────────────────              ───────────                  ───────────────────────
IT, GIS, KI, Verwaltung  ──►  Open WebUI: KI, IT      ──►  Open WebUI: KI darf Bilder
(aus AD oder lokal)           Grafana:    IT               IT ist dort Admin
                              QGIS:       GIS
```

Links kommt aus Keycloak. Mitte ist OTA. Rechts gehört der Anwendung — und Open WebUI etwa hat ein
eigenes, additiv wirkendes Rechtemodell, das OTA nicht anfassen sollte.

---

## 5 · Die Entscheidungen und ihre Folgen

### 5.1 Bestandskonten: übernehmen, Passwörter neu — **entschieden**

OTA hat heute Konten mit Argon2id-Hashes. Keycloak beherrscht Argon2 seit Fassung 24 als
Standardverfahren; ein Import roher PHC-Zeichenketten ist im Prinzip möglich, in der Praxis aber
von übereinstimmenden Parametern abhängig — und im Fehlerfall **still**: Es fällt erst auf, wenn
sich jemand nicht anmelden kann.

Deshalb der belastbare Weg:

```
Für jedes bestehende Konto:
  Name, E-Mail, Anzeigename, Gruppen, aktiv/gesperrt   →  nach Keycloak
  Passwort                                             →  einmalig neu vergeben
                                                          Wechsel beim ersten Login erzwungen
```

Das heisst konkret: `must_change_password` gibt es in Keycloak als `UPDATE_PASSWORD` unter den
erforderlichen Aktionen — dieselbe Mechanik wie heute bei `make admin`. Jeder Nutzer zahlt einmal
dreissig Sekunden; niemand steht vor einer Anmeldung, die aus unerfindlichen Gründen nicht geht.

Das Werkzeug dafür gehört in Etappe E und muss **wiederholbar** sein: Ein Migrationslauf, der beim
zweiten Aufruf Konten doppelt anlegt, wäre unbrauchbar. Abgleich über `username`, angelegt wird nur,
was fehlt.

### 5.2 Notzugang: ein Notfallkonto — **entschieden**

Ohne Vorkehrung gilt: **Keycloak weg = niemand kommt herein.** Laufende Sessions laufen weiter
(OTAs Cookie gilt), aber neue Anmeldungen scheitern — auch die der Administration, auch dann, wenn
das Problem in Keycloak selbst liegt. Eine Anlage, die sich bei einer kaputten
Föderationskonfiguration selbst aussperrt, ist keine.

Also bleibt **genau ein** lokales Administratorkonto bestehen. Die Bedingungen dafür sind der
eigentliche Inhalt dieser Entscheidung — ein Notzugang ohne sie ist nur eine zweite Tür:

- **Eigene Adresse**, nicht die normale Anmeldemaske (`/notfall`). Wer den regulären Weg benutzt,
  sieht keinen Ausweg und sucht auch keinen.
- **Kein Weg für andere.** Es ist ein einziges Konto, es lässt sich nicht vermehren, und es kann
  keiner Gruppe zugewiesen werden.
- **Jede Anmeldung wird protokolliert** und ist im Betriebsbild sichtbar. Ein Notzugang, den
  niemand bemerkt, ist eine Hintertür.
- **Zweite Stufe zwingend.** Er ist der einzige Anmeldeweg, der Keycloaks Absicherung umgeht —
  also braucht er eine eigene. Das ist der einzige Grund, aus dem OTAs TOTP-Code nicht restlos
  verschwindet (siehe 5.3).
- **Sichtbar abgelaufen.** Steht das Passwort länger als, sagen wir, ein Jahr unverändert, sagt das
  Betriebsbild es deutlich.

### 5.3 Zweite Stufe: nach Keycloak — **entschieden**

Die zweite Stufe gehört zur Anmeldung, und die liegt künftig bei Keycloak. Damit gilt sie für
**alle** angebundenen Anwendungen und nicht nur für OTA, und WebAuthn/Passkeys kämen ohne
Zusatzarbeit dazu — ein Punkt, der bisher unter M9 auf „irgendwann" stand.

Was das im Bestand heisst:

| Heute in OTA | Künftig |
|---|---|
| Einrichtung mit QR-Code unter „Mein Konto" | Keycloaks eigene Maske |
| Wiederherstellungscodes | Keycloak-Wiederherstellungscodes |
| `Group.require_totp` | Keycloak-Authentifizierungsfluss, an eine Gruppe gebunden |
| Rücksetzung durch Administratoren | derselbe Knopf in OTA, dahinter ein Admin-API-Aufruf |

Die Gruppenpflicht ist dabei der Punkt, der Arbeit macht: In OTA ist sie ein Feld, in Keycloak ein
Authentifizierungsfluss mit einer Bedingung. Das ist mehr als eine Übersetzung und gehört in
Etappe B geprüft, nicht in E.

**Eine Ausnahme bleibt:** Das Notfallkonto aus 5.2 braucht seine eigene zweite Stufe, weil es
Keycloak gerade nicht benutzt. OTAs TOTP-Code schrumpft also auf diesen einen Fall zusammen,
statt ganz zu verschwinden.

### 5.4 Eigene LDAP-Anbindung: bis Etappe E Rückweg, dann weg — **entschieden**

Sie funktioniert und ist geprüft. Sie parallel zu Keycloak zu behalten hiesse, zwei Wege zu
demselben AD zu pflegen — und der doppelte Weg ist genau die Sorte Konstruktion, in der später ein
Konto in einem Weg gesperrt und im anderen offen ist.

Bis Etappe E bleibt sie unverändert funktionsfähig: Sie ist der Rückweg, falls sich der Umbau als
Fehler herausstellt. Danach fallen `directory.py`, `identity.py` und `scripts/test-ldap.sh`
zusammen weg.

Bis dahin gilt: **keine Weiterentwicklung.** Was heute geht, geht; neue Wünsche an die
AD-Anbindung — verschachtelte Gruppen, `memberOf`, mehrere Verzeichnisse — werden nicht mehr in
OTA gebaut, sondern sind Argumente für den Umstieg. Wer das anders handhabt, baut zweimal.

### 5.5 Die Rechte des Verwaltungskontos

OTA braucht einen technischen Client (`ota-manager`) mit einem Dienstkonto. Was er wirklich braucht:

| Recht | Wofür | Umfang |
|---|---|---|
| `manage-users`, `query-users` | Konten anlegen, sperren, Gruppen setzen | eng |
| `manage-clients`, `query-clients` | OIDC-Clients für neue Anwendungen | mittel |
| `manage-realm` | LDAP-Föderation konfigurieren | **breit** |

Hier gibt es einen unangenehmen Befund, den die Vorüberlegung nicht enthielt: **Die LDAP-Anbindung
in Keycloak ist keine „Identity-Provider"-Ressource, sondern eine Benutzer-Föderation** und liegt
unter `components`. Deren Verwaltung verlangt `manage-realm` — ein Recht, das faktisch den ganzen
Realm umfasst.

Daraus folgt zwingend: **ein eigener Realm für OTA** (`ota`), niemals `master`. Dann ist der breite
Zugriff auf diesen Realm begrenzt, und der Keycloak-Server selbst bleibt ausserhalb.

Jede Änderung, die OTA in Keycloak schreibt, gehört zusätzlich ins OTA-Protokoll — die
Keycloak-Ereignisse allein sagen nur „`ota-manager` hat etwas geändert", nicht *wer* es in OTA
veranlasst hat.

### 5.6 Zwei Dinge, die im Zielbild fehlten

**Die Desktop-Verknüpfungen.** Seit `acba9a2` öffnen Anwendungen in einem eigenen Fenster ohne
Browserleiste. Eine OIDC-Anmeldung führt über eine **fremde Herkunft** (Keycloak) und wieder
zurück. Ein solcher Sprung verlässt den Geltungsbereich des Manifests — Chrome schiebt dafür eine
Leiste ein und kehrt danach zurück, aber „danach" ist hier nicht selbstverständlich. **Das muss
gemessen werden, bevor irgendetwas umgestellt wird**, sonst ist eine gerade gebaute Funktion still
kaputt.

**Kasm.** Läuft weiter parallel und hat seine eigene Anmeldung. Es könnte später ein weiterer
OIDC-Client werden; das ist kein Teil dieses Umbaus.

---

## 5a · Welcher Identity Provider: Keycloak — **entschieden**

Keycloak stand im Zielbild, weil es das naheliegendste ist — nicht, weil es geprüft wurde. Also
geprüft, und danach bewusst bestätigt: **Keycloak**, entschieden am 2026-08-28.

Die Begründung ist die konservative: die tiefste AD-Föderation im Feld, Apache-2.0, CNCF und Red
Hat statt eines einzelnen Unternehmens. Für eine Schicht, durch die künftig **jede** Anmeldung
läuft und die zehn Jahre tragen soll, wiegt Beständigkeit schwerer als Bequemlichkeit.

Der unterlegene Kandidat war authentik, und der Vollständigkeit halber steht unten, womit er
gepunktet hätte — falls die Entscheidung je überdacht wird.

### Zwei Anforderungen entscheiden fast alles

Der Kandidatenkreis wird nicht durch OIDC-Fähigkeiten bestimmt — das können alle. Er wird durch
zwei Dinge bestimmt, die aus OTAs Rolle als **Verwalter** folgen:

1. **AD/LDAP-Föderation mit Gruppen, zur Laufzeit über eine Schnittstelle konfigurierbar.** Nicht
   „kann LDAP", sondern: Gruppen kommen mit, und ein Administrator richtet es in OTAs Oberfläche
   ein, nicht in einer YAML-Datei auf dem Host.
2. **Nutzer, Gruppen und OIDC-Clients zur Laufzeit über eine Schnittstelle anlegbar.** Ohne das
   gibt es kein „Anwendung hinzufügen" in OTA.

An diesen beiden Punkten scheitern die meisten:

| Kandidat | Woran es scheitert |
|---|---|
| **Authelia** | Konfiguration liegt in YAML-Dateien auf der Platte. Keine Schnittstelle, über die OTA Nutzer oder Clients anlegen könnte. Damit fällt OTAs ganze Rolle als Verwalter weg. |
| **Dex** | Reiner Vermittler ohne eigenen Nutzerbestand — „lokale Benutzer ohne AD" gäbe es nur als statische Einträge in einer Datei. Konfiguration ebenfalls dateibasiert. |
| **Ory Hydra + Kratos** | Ausgezeichnete Schnittstellen, aber Hydra ist reines OAuth2 ohne Nutzer, Kratos Nutzer ohne OIDC-Provider, LDAP-Föderation gibt es nicht, und die Anmeldemasken schreibt man selbst. Also genau die Arbeit, die dieser Umbau vermeiden soll. |
| **Kanidm** | Will selbst die führende Quelle sein und ist ein LDAP-*Server*, kein Vermittler. AD-Föderation ist nicht sein Zweck. |
| **Zitadel** | Der knappste Fall — und ein klares Nein: LDAP nur als externe Anmeldung, **ohne Abgleich**, und ein Gruppenfilter fehlt. Damit kommen AD-Gruppen nicht mit, und OTAs gruppengesteuerter Zugriff hätte keine Grundlage. |

Übrig bleiben zwei ernsthafte Kandidaten.

### Keycloak

- Apache-2.0, CNCF, Red Hat im Rücken — die konservative Wahl für etwas, das zehn Jahre laufen soll
- Die **tiefste LDAP/AD-Föderation** im Feld: Abgleich, Gruppen-Mapper, Rückschreiben
- Die LDAP-Anbindung liegt unter `components` und ist über die Admin-API vollständig
  konfigurierbar (siehe 5.5 — mit der Folge, dass `manage-realm` nötig ist)
- **Der Preis ist Gewicht.** Empfohlen werden 4 GB, für den Produktivbetrieb mehr. Auf einem
  Rechner, auf dem schon Arbeitsplatz-Container mit je 2 GB laufen, ist das kein Detail.
- Erstkonfiguration ist erfahrungsgemäss ein halber Tag, nicht eine Stunde

### authentik

- MIT. LDAP-Quelle, OIDC-Provider, Gruppen, MFA, Flows sind im offenen Kern; kostenpflichtig sind
  Dinge, die OTA nicht braucht (KI-Risikoerkennung, Support-Zusagen, erweiterte Protokollierung).
  Der Anbieter sagt zu, **keine** Funktion aus dem offenen Teil herauszulösen.
- **Die Schnittstelle ist vollständig, und zwar nachweislich:** Die eigene Verwaltungsoberfläche
  läuft auf derselben öffentlichen API. Was ein Administrator dort tun kann, kann OTA auch —
  das ist genau die Garantie, die dieser Umbau braucht.
- **Deutlich leichter:** rund 250–350 MB für den ganzen Stapel einschliesslich Datenbank; seit
  Fassung 2025.10 ohne Redis.
- Risiko: ein Unternehmen, kein Konsortium. Für Infrastruktur, die zehn Jahre tragen soll, ist das
  der ernstzunehmende Gegeneinwand.

### Vorsicht bei zwei Begriffen

authentik unterscheidet **LDAP-Quelle** (Nutzer aus AD holen — das braucht OTA) von
**LDAP-Provider** (authentik selbst als LDAP-Server anbieten). Verwechslung führt zu einer
Konfiguration, die genau das Gegenteil tut.

### Wie entschieden wird: durch Messen, nicht durch Lesen

Beide Kandidaten behaupten, was OTA braucht. Die Frage ist nicht, ob sie es können, sondern ob der
**Weg über die Schnittstelle** so trägt, wie OTA ihn braucht. Das ist in einem Nachmittag
entscheidbar — mit demselben Vorgehen, das sich schon beim eigenen LDAP bewährt hat
(`scripts/ldap-test-server.sh`): ein Wegwerf-Verzeichnis im Container, und dagegen gemessen.

**Etappe 0 — Vergleich am lebenden Objekt.** Für beide Kandidaten dieselben fünf Fragen,
ausschliesslich über die Schnittstelle, kein Klick in der fremden Oberfläche:

1. AD-Föderation anlegen und die Verbindung testen
2. Eine AD-Gruppe erscheint als Gruppe, und ihre Mitglieder stimmen
3. Einen OIDC-Client anlegen, samt Redirect-URI und Gruppen-Claim
4. Ein lokales Konto anlegen, mit erzwungenem Passwortwechsel beim ersten Login
5. Ein Konto sperren, und die laufende Sitzung endet

Dazu gemessen: Arbeitsspeicher im Leerlauf, Startzeit, Grösse des Abbilds.

Wer beide Läufe besteht, gewinnt über die weichen Kriterien. Wer bei 1 oder 3 stolpert, ist raus —
egal wie gut der Rest aussieht.

### Eine schmale Schicht dazwischen

OTA spricht mit Keycloak **nicht verstreut**, sondern durch eine eigene Schicht — dieselbe Idee wie
`agent_client.py` gegenüber Docker. Nicht als Notausgang, sondern aus demselben Grund wie dort:
Keycloak-Eigenheiten sollen an **einer** Stelle stehen und nicht in fünfzehn Routern, und diese
Stelle lässt sich in den Prüfreihen ersetzen. Ungefähr zehn Vorgänge:

```
konto_anlegen · konto_sperren · konto_finden
gruppe_anlegen · gruppe_zuordnen · gruppen_eines_kontos
verzeichnis_konfigurieren · verzeichnis_testen
client_anlegen · client_entfernen
```

Damit hat der Umbau genau eine Naht zur fremden Software, und die Prüfreihen können sie
durchtrennen, ohne ein echtes Keycloak zu brauchen.

### Was die Entscheidung für Keycloak kostet

Keycloak ist der schwerste Dienst im Stapel; empfohlen werden 4 GB, im Produktivbetrieb mehr. Das
ist eingepreist und **keine offene Frage**: Wenn die Anlage produktiv 8 GB dafür braucht, bekommt
sie 8 GB. Eine Identitätsschicht, durch die jede Anmeldung läuft, ist keine Stelle zum Sparen.

Für **diese Entwicklungsmaschine** ist ein Deckel trotzdem sinnvoll, damit Keycloak beim Entwickeln
nicht die Arbeitsplatz-Container verdrängt — hier sind 15 GiB gesamt und 6,9 GiB frei, bei 3 GiB
Deckel je Arbeitsplatz:

```yaml
# nur für die Entwicklungsmaschine; produktiv unbegrenzt
environment:
  JAVA_OPTS_APPEND: "-Xms256m -Xmx512m"
mem_limit: 1g
```

Ohne Angabe bemisst die JVM ihren Heap an dem, was sie im Container sieht. Das ist produktiv
richtig und beim Entwickeln lästig — mehr steckt nicht dahinter.

---

## 5d · Wer Anwendungen anlegen darf — **entschieden**

Ab Etappe D bekommt „Anwendung anlegen" eine zweite Bedeutung. Bisher hiess es: ein Image
auswählen, Apps freigeben, Gruppen zuweisen — die Reichweite endet am Host. Künftig schreibt OTA
dabei einen OIDC-Client nach Keycloak, und darin steht eine Zeile, die alles ändert:

```
Redirect-URI    https://ai.firma.de/oauth/oidc/callback
```

Dorthin schickt Keycloak nach der Anmeldung den Autorisierungs-Code. **Wer die URI bestimmt,
bestimmt, wohin die Identität der Nutzer fliesst.**

Das Szenario, gegen das hier abgesichert wird:

```
Jemand legt an:
    Name          „Zeiterfassung"
    Redirect-URI  https://sammel-server.example/abholen
    Zugriff       alle

Auf dem Dashboard erscheint eine Kachel. Ein Kollege klickt, meldet sich
wie immer bei Keycloak an — und der Code für seine Identität landet auf
einem fremden Server. Von dort: Name, E-Mail, Gruppen. Je nach Zuschnitt
ein Token, dem weitere Anwendungen vertrauen.
```

Im Protokoll sieht das aus wie „hat eine Anwendung hinzugefügt". Es ist aber kategorisch etwas
anderes als „hat ein Image freigegeben": Das eine bleibt auf dem Rechner, das andere leitet
Identitäten nach draussen.

**Entschieden: ein eigenes Recht, und zusätzlich eine technische Schranke.**

### Das Recht

`anwendungen.verwalten`, getrennt von `templates.manage`. Wer Arbeitsplätze zusammenstellt — eine
Rolle, die man einem IT-Mitarbeiter gibt — erzeugt damit nicht automatisch OIDC-Clients. Beides
lässt sich derselben Person geben; es muss nur eine Entscheidung sein und keine Nebenwirkung.

### Die Schranke

Eine Liste erlaubter Ziel-Domains in den Einstellungen. Eine Redirect-URI ausserhalb wird
abgelehnt, **egal wer sie einträgt** — auch ein Administrator.

```
Erlaubte Ziele für Anwendungen
    firma.de
    *.firma.local

→ https://ai.firma.de/oauth/oidc/callback      angenommen
→ https://sammel-server.example/abholen        abgelehnt
```

Zwei Schlösser statt einem, und sie sichern gegen Verschiedenes: Das Recht gegen den, der es nicht
haben soll; die Liste gegen den Tippfehler dessen, der es hat. Der zweite Fall ist der
wahrscheinlichere.

Drei Regeln, damit die Schranke keine Kulisse wird:

- **Geprüft wird in der API, nicht im Formular.** Eine Prüfung, die nur im Browser stattfindet,
  ist keine.
- **Nur `https`**, und keine Platzhalter im Pfad. Keycloak erlaubt `*` in Redirect-URIs; OTA
  reicht das nicht durch.
- **Ist die Liste leer, ist nichts erlaubt** — nicht alles. Eine Schranke, die im
  Auslieferungszustand offen steht, wird nie geschlossen.

Beim Einrichten wird die Liste einmal gefüllt, mit einer Zeile in der Oberfläche, die erklärt,
warum sie nicht leer bleiben sollte.

---

## 5c · Wann ein Rechteentzug greift — **entschieden**

Fliegt jemand aus einer Gruppe, während er arbeitet: sofort hinauswerfen oder bis zur nächsten
Anmeldung gelten lassen? **Entschieden: bis zur nächsten Anmeldung.**

Das ist die richtige Antwort, weil die Alternative im Alltag mehr kaputt macht, als sie schützt.
Eine Gruppenänderung im AD ist in aller Regel eine organisatorische — jemand wechselt die
Abteilung, ein Projekt endet. Dass dabei mitten im Satz ein Editor verschwindet und ungesicherte
Arbeit mit ihm, ist kein Sicherheitsgewinn, sondern ein Datenverlust.

**Aber der Entzug einer Gruppe ist nicht dasselbe wie der Entzug eines Kontos.** Diese beiden Fälle
werden gern in einen Topf geworfen, und genau das wäre der Fehler:

| Was passiert | Wann es greift | Warum |
|---|---|---|
| Konto **gesperrt oder deaktiviert** | **sofort**, beim nächsten Aufruf | Jemand geht, wird entlassen, ein Zugang gilt als kompromittiert. Da zählt jede Minute. |
| **Abmeldung erzwungen** (`token_epoch`) | **sofort** | Ausdrückliche Handlung eines Administrators — sie soll wirken. |
| Aus einer **Gruppe entfernt** | bei der nächsten Anmeldung | Organisatorische Änderung, kein Vorfall. |
| Zugriff einer **Anwendung entzogen** | bei der nächsten Anmeldung | Dasselbe. Die Kachel verschwindet sofort, die laufende Sitzung läuft aus. |

Die ersten beiden Zeilen sind heute schon so und bleiben es: `forwardAuth` prüft bei **jedem**
Aufruf `is_active`, `is_locked` und `token_epoch` — auch vor jedem WebSocket-Handshake. Wer
gesperrt wird, ist im selben Moment vom Bildschirm weg.

Zwei Dinge gehören zur Ehrlichkeit dieser Entscheidung dazu:

- **Das Fenster ist begrenzt, aber nicht kurz.** Es endet mit der Sitzung, und die endet über
  `idle_minutes` der Vorlage — bei vier Stunden Leerlauf also frühestens nach vier Stunden.
- **Es gibt einen Weg, es sofort zu beenden.** Wer eine Gruppenänderung als dringend ansieht,
  erzwingt zusätzlich die Abmeldung. Der Knopf existiert, er wirkt sofort, und er steht im
  Protokoll. Das ist die richtige Aufteilung: der Normalfall bequem, der Ausnahmefall möglich.

---

## 5b · Mitgeliefert **oder** vorhanden — **entschieden**

Keycloak läuft im Stack, wie Datenbank und Registry. Und es muss möglich sein, stattdessen ein
**bereits vorhandenes** Keycloak anzubinden — wer eines betreibt, soll nicht ein zweites bekommen.

Das sind zwei Betriebsarten, und der Unterschied ist grösser, als er aussieht: Er entscheidet, was
OTA in dem Realm überhaupt darf.

| | **Mitgeliefert** (Vorgabe) | **Vorhanden** |
|---|---|---|
| Wer startet es | `make up`, wie die Datenbank | jemand anderes, vorher |
| Realm | OTA legt `ota` bei `make setup` an | muss existieren, wird angegeben |
| `ota-manager` | OTA erzeugt ihn samt Rechten | legt die dortige Administration an, OTA bekommt die Zugangsdaten |
| Datenbank | eigenes Schema in OTAs Postgres | fremd, geht OTA nichts an |
| Aktualisierung | mit OTA | fremd, geht OTA nichts an |
| OTA ist im Realm | führend | **Gast** |

### „Gast" ist der Teil, den man leicht übersieht

In einem fremden Keycloak teilt OTA sich den Realm womöglich mit anderen Systemen. Daraus folgt
dreierlei, und wer es übergeht, baut ein Werkzeug, das fremde Anlagen beschädigt:

- **Kein Löschen ohne Not.** Ein in OTA entferntes Konto wird im fremden Realm *deaktiviert* oder
  nur aus OTAs Gruppen genommen — nicht gelöscht. Es könnte drei anderen Anwendungen gehören.
- **Nur die eigenen Gruppen anfassen.** OTA arbeitet unterhalb eines vereinbarten Pfads
  (`/ota/...`) und lässt alles daneben in Ruhe.
- **Die Verzeichnisanbindung gehört womöglich nicht OTA.** Betreibt jemand schon ein Keycloak,
  hängt sein AD mit hoher Wahrscheinlichkeit längst daran. Dann hat OTA dort nichts zu
  konfigurieren, sondern nur zu verwenden.

### Was daraus für die Oberfläche folgt

OTA muss beim Start **feststellen, was es darf**, und die Oberfläche danach richten — statt einem
Administrator einen Knopf anzubieten, der in einem 403 endet:

```
beim Verbinden:
  darf ich Konten verwalten?      manage-users
  darf ich Clients verwalten?     manage-clients
  darf ich Föderation ändern?     manage-realm

Oberfläche:
  fehlt manage-realm   →  „Active Directory konfigurieren" ist nicht da,
                          stattdessen: „Wird vom vorhandenen Keycloak verwaltet."
  fehlt manage-clients →  Anwendungen anlegen zeigt die nötige Konfiguration
                          zum Übertragen an, statt sie selbst zu schreiben
```

Das ist keine Fleissarbeit am Rand, sondern der Unterschied zwischen einem Werkzeug, das man in
eine gewachsene Umgebung stellen kann, und einem, das man nur auf der grünen Wiese betreibt.

### Und es darf nicht abstürzen, wenn das fremde Keycloak schweigt

Beim mitgelieferten regelt das der Healthcheck: Die API startet nach Keycloak. Bei einem fremden
gibt es diese Gewissheit nicht — es kann beim Hochfahren von OTA gerade neu starten, wegen einer
Wartung stehen oder hinter einem VPN liegen, das noch nicht oben ist.

OTA startet dann trotzdem, meldet den Zustand unter **Betrieb** und lässt die Anmeldung scheitern,
solange es so bleibt. **Genau dafür gibt es das Notfallkonto aus 5.2** — hier fällt beides
zusammen, und hier zahlt sich die Entscheidung von vorhin aus.

---

## 5e · Vier Dinge, die noch niemand angefasst hat

Beim Durchgehen des Bestands gefunden. Keine Entscheidungen — Arbeit, die im Plan fehlte.

### Die Prüfreihen melden sich mit Benutzername und Passwort an

Alle vier Skriptreihen tun das, `scripts/test-authz.sh` allein neunmal:

```bash
api -X POST "$BASE/api/auth/login" -d '{"username":…,"password":…}'
```

Mit der Umstellung gibt es diesen Endpunkt so nicht mehr — und damit brechen **257 Prüfungen** auf
einen Schlag. Das ist kein Randproblem: Ohne Prüfreihen lässt sich der Umbau nicht verantworten,
und ausgerechnet er braucht sie am dringendsten.

Der Weg dafür ist vorgesehen: Keycloak kann für einen Client **Direct Access Grants** erlauben —
Benutzername und Passwort direkt gegen ein Token, ohne Browser. Ein eigener Client `ota-tests`,
nur dafür, im mitgelieferten Realm. Die Reihen tauschen dann eine Zeile aus und laufen weiter.

Gehört in **Etappe B**, zusammen mit der Umstellung selbst. Nicht danach.

### Keycloaks Daten sind nicht in der Sicherung

`make backup` sichert genau eine Datenbank und die Profile:

```makefile
pg_dump -U $POSTGRES_USER $POSTGRES_DB          # nur "ota"
tar … -C / srv/ota/profiles
```

Läuft Keycloak in einem eigenen Schema oder einer eigenen Datenbank, ist es **nicht dabei**. Eine
Wiederherstellung brächte dann OTA zurück, dessen Nutzer auf Identitäten zeigen, die es nicht mehr
gibt — Sessions, Profile und Kontingente hingen an `external_id`-Werten ohne Gegenstück.

Gehört in **Etappe A**, mit dem Dienst selbst. Und zusätzlich in die Wiederherstellungsprobe: Ein
Backup, dessen Wiederherstellung nie geprüft wurde, ist kein Backup.

### Zwei Uhren, die nichts voneinander wissen

Keycloak hat eigene Sitzungsdauern (SSO-Session, Token-Lebensdauer), OTA hat `idle_minutes` je
Vorlage und ein rollendes Cookie. Nach der Umstellung laufen beide nebeneinander.

Der unangenehme Fall: Keycloaks Sitzung läuft ab, OTAs Cookie ist frisch. Dann arbeitet jemand in
OTA weiter, während der Provider ihn längst nicht mehr kennt.

Vorschlag, in Etappe B zu bestätigen: **Innerhalb von OTA gilt OTAs Uhr.** Keycloaks Sitzung
entscheidet über die *Anmeldung*, nicht über die Weiterarbeit; ein Widerruf wirkt über
Back-Channel-Logout, nicht über Ablauf. Das ist verständlich und hat keine Lücke — vorausgesetzt,
Back-Channel-Logout funktioniert wirklich, und genau das ist zu prüfen.

### Abmelden — nur hier oder überall?

Klickt jemand in OTA auf **Abmelden**: gilt das nur für OTA, oder auch für Open WebUI und alles
Weitere?

Beides ist vertretbar. Für ein Portal spricht einiges dafür, dass „Abmelden" wirklich abmeldet —
sonst bleibt an einem geteilten Rechner eine offene Sitzung zurück, die niemand vermutet. Dagegen
spricht die Überraschung, dass ein Klick in OTA drei andere Fenster mitnimmt.

Vorschlag: **beides anbieten** — „Abmelden" für OTA, „Überall abmelden" daneben. Zu entscheiden in
Etappe D, wenn es die erste zweite Anwendung überhaupt gibt.

---

## 6 · Etappen

Jede Etappe endet in einem Zustand, in dem alles läuft. Keine Etappe lässt sich nur zusammen mit
der nächsten abschliessen.

### A · Keycloak steht daneben, ohne dass jemand es merkt
- Keycloak im Stack (`deploy/docker-compose.yml`), eigener Realm `ota`, eigene Datenbank
- **Beide Betriebsarten von Anfang an** (5b): mitgeliefert als Vorgabe, ein vorhandenes anbindbar.
  Nachträglich eingezogen wäre das ein Umbau — die Frage „darf ich das hier überhaupt?" durchzieht
  jeden Aufruf gegen die Admin-API
- Rechteprüfung beim Verbinden; die Oberfläche zeigt nur, was wirklich geht
- **Keycloaks Daten in `make backup`** und in die Wiederherstellungsprobe (5e)
- Nur intern erreichbar; Traefik veröffentlicht es unter `/auth`
- `ota-manager`-Client mit Dienstkonto, Rechte wie oben
- `make setup` erzeugt das Realm-Grundgerüst
- Das Notfallkonto (5.2) entsteht **hier**, nicht in E: Ab dem Moment, in dem Keycloak im
  Anmeldeweg steht, muss der Ausweg schon existieren
- **Fertig, wenn:** OTA unverändert weiterläuft und niemand einen Unterschied bemerkt

### B · OTA meldet sich über Keycloak an
- Autorisierungs-Code-Fluss mit PKCE; OTA tauscht den Code und setzt sein eigenes Cookie
- `users` wird über `sub` verknüpft; Gruppen bei jeder Anmeldung abgeglichen
- Abmeldung in Keycloak beendet OTA-Sitzungen über Back-Channel-Logout (`token_epoch` +1)
- Die Gruppenpflicht zur zweiten Stufe (`require_totp`) als Keycloak-Authentifizierungsfluss
  nachgebaut und geprüft — das ist mehr als eine Übersetzung (5.3)
- **Client `ota-tests` mit Direct Access Grants**, damit die vier Skriptreihen weiterlaufen (5e).
  Zusammen mit der Umstellung, nicht danach — sonst steht der Umbau ohne Prüfung da
- **Fertig, wenn:** Anmeldung, Streams, `forwardAuth` und die Desktop-Verknüpfungen unverändert
  funktionieren — gemessen, nicht vermutet

### C · OTA verwaltet Keycloak
- Nutzer und Gruppen: anlegen, sperren, zuordnen — über die Admin-API statt lokal
- AD/LDAP-Anbindung über die OTA-Oberfläche konfigurierbar, mit „Verbindung testen"
- Jede Änderung im OTA-Protokoll, mit dem Menschen, der sie veranlasst hat
- **Fertig, wenn:** eine Administration Keycloak für den Alltag nicht mehr öffnen muss

### D · Die erste fremde Anwendung
- Anwendungstyp „Externe Web-Anwendung" neben „Arbeitsplatz" im Katalog
- Neues Recht `anwendungen.verwalten` und die Liste erlaubter Ziel-Domains (5d) — beides **bevor**
  der erste Client entstehen kann, nicht danach
- OTA legt den OIDC-Client in Keycloak an, setzt Redirect-URI und Gruppen-Claim, zeigt die
  Konfiguration zum Übertragen
- Zugriff je Gruppe; die Kachel erscheint nur bei Berechtigten
- **Fertig, wenn:** Open WebUI ohne eigene Benutzerpflege läuft und Gruppen mitkommen

### E · Aufräumen
- Wiederholbarer Migrationslauf für Bestandskonten (5.1): Konten nach Keycloak, Passwörter neu,
  Wechsel beim ersten Login erzwungen
- Was ersetzt wurde, fällt weg: `directory.py`, `identity.py`, `scripts/test-ldap.sh`, die
  Passwortprüfung in `auth.py`, die TOTP-Einrichtung unter „Mein Konto"
- OTAs TOTP-Code schrumpft auf das Notfallkonto zusammen (5.2/5.3) statt zu verschwinden
- Profil- und Ablagepfade auf `sub` umgestellt, Verweise unter dem Namen angelegt (§4)
- **Fertig, wenn:** es für gewöhnliche Nutzer genau **einen** Anmeldeweg gibt — und daneben
  einen dokumentierten Notzugang, den das Betriebsbild zeigt

---

## 7 · Was dieser Umbau kostet

Damit die Entscheidung mit offenen Augen fällt:

- **Ein weiterer Dienst, und zwar der schwerste im Stapel.** Keycloak ist eine Java-Anwendung;
  empfohlen werden 4 GB, produktiv mehr. Das ist eingepreist — eine Identitätsschicht ist keine
  Stelle zum Sparen. Auf der Entwicklungsmaschine gedeckelt, produktiv nicht (5a).
- **Ein zweiter Ort für Wahrheit.** Nutzer stehen künftig in Keycloak *und* — als Projektion — in
  OTA. Jede Projektion kann veralten. Wann abgeglichen wird und was bei Widerspruch gilt, muss
  festgeschrieben sein, sonst wird es zur Fehlerquelle.
- **Eine neue Abhängigkeit im Anmeldeweg.** Siehe 5.2.
- **Verworfene Arbeit.** Siehe Abschnitt 3.

Dagegen steht: **ein** Anmeldeweg für beliebig viele Anwendungen, keine Passwortweitergabe, AD
ohne eigenen LDAP-Code, und OTA wird das, wonach es ohnehin aussieht — ein Anwendungsportal.

Keycloak steht unter Apache-2.0 und passt damit zur Lizenzlage von OTA. Es gehört ab Etappe A in
[`THIRD-PARTY-NOTICES.md`](THIRD-PARTY-NOTICES.md).

---

## 8 · Was ausdrücklich nicht passiert

- **Keine Passwortweitergabe an fremde Anwendungen.** Das war der Ausgangspunkt und bleibt es.
- **OTA wird kein OIDC-Provider.** Es ist Client und Verwalter, nichts sonst.
- **OTA baut fremde Rechtemodelle nicht nach.**
- **Kein Umbau ohne Rückweg.** Bis Etappe E bleibt der lokale Anmeldeweg funktionsfähig.

---

## 9 · Entscheidungen

| Nr. | Frage | Entscheidung | Stand |
|---|---|---|---|
| 1 | Bestandskonten und Passwörter | Konten übernehmen, Passwörter einmalig neu, Wechsel erzwungen | **entschieden** 2026-08-28 |
| 2 | Notzugang, wenn Keycloak steht | Ein Notfallkonto unter eigener Adresse, protokolliert, mit eigener zweiter Stufe | **entschieden** 2026-08-28 |
| 3 | Ort der zweiten Stufe | Keycloak — bis auf das Notfallkonto | **entschieden** 2026-08-28 |
| 4 | Eigene LDAP-Anbindung | Bis Etappe E Rückweg, dort entfernt; ab sofort eingefroren | **entschieden** 2026-08-28 |
| 5 | Profil- und Ablagepfade | Nach `sub` benannt, Verweis unter dem Namen | Vorschlag (§4) |
| 6 | Eigener Realm statt `master` | Ja, zwingend (falls Keycloak) | ergibt sich aus 5.5 |
| 7 | **Welcher Identity Provider** | **Keycloak** — die konservative Wahl: tiefste AD-Föderation, Apache-2.0, CNCF. Zitadel, Authelia, Dex, Ory und Kanidm sind an den Anforderungen gescheitert, authentik unterlag | **entschieden** 2026-08-28 |
| 7a | Speicherbedarf | Eingepreist. Produktiv bekommt Keycloak, was es braucht; auf der Entwicklungsmaschine ein Deckel, damit es die Arbeitsplätze nicht verdrängt | ergibt sich aus 5a |
| 9 | Mitgeliefert oder vorhanden | **Beides** — im Stack als Vorgabe, ein vorhandenes anbindbar; dort ist OTA Gast und löscht nichts | **entschieden** 2026-08-28 |
| 10 | Wann ein Rechteentzug greift | Gruppen bei der nächsten Anmeldung; Sperre und erzwungene Abmeldung sofort | **entschieden** 2026-08-28 |
| 11 | Wer Anwendungen anlegen darf | Eigenes Recht `anwendungen.verwalten` **und** eine Liste erlaubter Ziel-Domains; leere Liste erlaubt nichts | **entschieden** 2026-08-28 |
| 8 | Zugriff über eine eigene schmale Schicht | Ja — eine Naht zur fremden Software, in Prüfreihen ersetzbar | ergibt sich aus 5a |

### Noch offen, aber später zu beantworten

Diese Fragen blockieren die Planung nicht, müssen aber vor der jeweiligen Etappe geklärt sein:

*(Zurzeit keine.)*
