# Was noch zu tun ist

Eine Liste, kein Wunschzettel. Alles hier ist entweder **gemessen** oder beim Aufräumen
aufgefallen; wo es herkommt, steht dabei. Nach Wirkung geordnet, nicht nach Aufwand.

**Stand: 2026-09-04**

---

## Erledigt am 2026-09-04

| # | Was | Wie es ausging |
|---|---|---|
| 1 | **Zeichensatz mitgeliefert** statt von Google geladen | Archivo (variabel, die Gestaltung braucht die Breitenachse) und IBM Plex Mono, Bereiche latin und latin-ext, 256 KB. Im Browser nachgemessen: beide laden echt, **keine einzige Anfrage an einen fremden Host**. Google ist aus `index.html` und aus der CSP verschwunden. |
| 2 | **Aufschalten protokolliert** | Eintrag `session.attached` mit dem Namen des Eigentümers. Gedrosselt auf einen Eintrag je Viertelstunde und Paar — die Rechteprüfung läuft vor *jedem* Zugriff, ein Eintrag je Anfrage wäre Rauschen. Der eigene Bildschirm erzeugt keinen Eintrag. Drei neue Prüfungen. |
| 3 | **Dateirechte** | `/srv/ota/{profiles,backups,userfiles,groupfiles,shared}` auf 0700, Archive und Datenbankabzüge auf 0600, jedes Zuhause auf 0700 — zwei standen auf **777**. Der Agent setzt es beim Anlegen mit. **Eine Falle dabei**: Die gemeinsame Ablage wird als Ganzes eingehängt, dort zählt ihr Modus auch im Container — sie gehört jetzt dem Container-Nutzer, sonst sieht der Arbeitsplatz ein leeres Verzeichnis. |
| 4 | **Passwortregel in Keycloak** | `length(12) and notUsername and notEmail` — dieselbe Untergrenze, die OTAs eigene Anmeldung seit jeher verlangt. In `scripts/keycloak-init.sh` mitgenommen, idempotent, und auch für einen Realm, den es schon gibt. |

---

## Sicherheit

| # | Was | Woher |
|---|---|---|
| 5 | **`/containers/{cid}/exec` am Agent löschen.** Führt einen beliebigen Befehl in einem beliebigen Container aus und wird von niemandem aufgerufen. | [`security.md`](security.md#m1) |
| 6 | **Keycloaks Verwaltungsoberfläche** von aussen schliessen (`ipAllowList` in Traefik). OTA steuert Keycloak von innen; die Konsole muss nicht im Netz stehen. | [`security.md`](security.md#m4) |
| 7 | **`script-src 'unsafe-inline'`** aus der CSP nehmen. Es wird für genau ein Skript im Kopf von `index.html` gebraucht — eigene Datei oder `nonce`. | [`security.md`](security.md#m5) |
| 8 | **TOTP-Startwerte und das AD-Kennwort verschlüsseln** (Schlüssel aus der `.env`). Schützt nicht gegen einen kompromittierten Wirt, aber gegen ein abhandengekommenes Sicherungsarchiv — und das ist der wahrscheinlichere Fall. | [`security.md`](security.md#m2) |
| 9 | **Kennzahlen-Merkmal zeitkonstant vergleichen** (`secrets.compare_digest`). Der Agent macht es nebenan richtig. | [`security.md`](security.md#n1) |
| 10 | **Bremse vor `/api/auth/*`** (`rateLimit` in Traefik). Heute steht dort nur die Kontosperre — und die lässt sich gegen einen Kollegen richten. | [`security.md`](security.md#n2) |
| 11 | **Protokolle begrenzen**: `max-size`/`max-file` an jeden Dienst. Sie wachsen unbegrenzt und enthalten IP-Adressen. | [`security.md`](security.md#n3) |
| 12 | **HSTS einschalten**, sobald ein Zertifikat einer anerkannten CA im Einsatz ist. Die Middleware liegt fertig daneben. | [`security.md`](security.md#n6) |
| 13 | **Abgleich gegen Schwachstellenlisten.** `make sbom` erzeugt die Stückliste; sie durch einen Scanner zu schicken gehört in den Betrieb. | [`security.md`](security.md#abhängigkeiten) |

---

## Datenschutz

| # | Was | Woher |
|---|---|---|
| 14 | **Aufbewahrungsfristen** für `audit_log` (Vorschlag: Anmeldungen 90 Tage, Verwaltungsvorgänge 1 Jahr) und für die Container-Protokolle (14 Tage). Heute löscht sich **nur** die Sicherung von selbst. | [`dsgvo.md`](dsgvo.md) §4 |
| 15 | **„Konto endgültig entfernen"** — Zuhause, Ablagen, Keycloak-Konto und der Name im Protokoll. Ein Löschersuchen braucht heute fünf Schritte an fünf Stellen, und es gibt keine Anleitung dafür. | [`dsgvo.md`](dsgvo.md) §4.1 |
| 16 | **Datenschutzhinweis** als Kapitel im Handbuch. Niemand erfährt beim Anmelden, was protokolliert wird. | [`dsgvo.md`](dsgvo.md) §5 |
| 17 | **Auskunftsfunktion** je Konto: alles zusammenstellen, was OTA über einen Menschen hat. | [`dsgvo.md`](dsgvo.md) §5 |
| 18 | **Betriebsvereinbarung anstossen** — Protokoll, Aufschalten, Netzzahlen sind mitbestimmungspflichtig (§ 87 Abs. 1 Nr. 6 BetrVG). | [`dsgvo.md`](dsgvo.md) §6 |
| 19 | **Schwellwertanalyse dokumentieren** (Art. 35). Eine Seite; die vollständige Folgenabschätzung ist wahrscheinlich nicht zwingend. | [`dsgvo.md`](dsgvo.md) §9 |
| 20 | **Fristen für die Netzzahlen**, sobald jemand `/metrics` abholt: Rohwerte 7 Tage, Tagessummen 90 Tage. Heute werden sie nirgends gespeichert — mit einem Prometheus davor ändert sich das. | [`dsgvo.md`](dsgvo.md) §2.2 |

---

## Aufräumen und Betrieb

| # | Was | Woher |
|---|---|---|
| 21 | **`signal`** zeigt auf ein Abbild, das nicht lokal liegt. Die Vorlage ist abgeschaltet, also harmlos — wer sie einschaltet, muss es erst holen. | Aufräumen 2026-09-03 |
| 22 | **Rund 70 MB Ballast** im Basisimage (`libdnnl3.6`, `libflite1`) hängen als Abhängigkeiten an GStreamer. Herauszubekommen nur mit `--force-depends`, was das Paketsystem beschädigt zurücklässt — bewusst drin. | [`HANDOVER.md`](HANDOVER.md) |
| 23 | **Unbestätigte Beobachtung**: Selkies scheint den TURN-Server alle 60 Sekunden an der laufenden Strecke auszutauschen. Im Betrieb bisher ohne Wirkung, nie nachgemessen. | [`HANDOVER.md`](HANDOVER.md) |
| 24 | **Prüfkonten entfernen** vor dem Produktivgang: `kc-pruef`, `ota-testnutzer`, `test`. Der Notzugang bleibt. | [`dsgvo.md`](dsgvo.md), Nachbemerkung |
| 25 | **Rückstände aus Prüfläufen** im Zuhause des Notfallkontos (`ota-pruef-skeleton-*`). Kein Schaden, aber die Reihen sollten aufräumen, was sie anlegen. | [`dsgvo.md`](dsgvo.md), Nachbemerkung |

---

## Grössere Vorhaben

| # | Was | Woher |
|---|---|---|
| 26 | **Mehrere Hosts (M10).** Braucht eine zweite Maschine. Vom Betreiber auf später gelegt. | [`roadmap.md`](roadmap.md) |
| 27 | **Selkies nachmessen**, was noch fehlt: Bildqualität gegen KasmVNC auf denselben Inhalten. CPU, Bandbreite und Reaktionszeit sind gemessen. | [`docs/wiki/20-selkies-versuch.md`](docs/wiki/20-selkies-versuch.md) |
| 28 | **Woher die Grundlast kommt.** Selkies kostet im Leerlauf ein Drittel Kern, und die Bildrate ist es nachweislich **nicht**. Vermutung: Abgreifen des Bildschirms und Farbumrechnung. Nicht nachgemessen. | [`docs/wiki/20-selkies-versuch.md`](docs/wiki/20-selkies-versuch.md) |
| 29 | **Wie viele Sitzungen trägt ein TURN?** Eine Verbindung belegt vier Relay-Ports; der Vorgabebereich reicht gerechnet für rund zwanzig. Gemessen ist das nicht. | [`docs/wiki/20-selkies-versuch.md`](docs/wiki/20-selkies-versuch.md) |

---

## Ausdrücklich nicht

Damit niemand sie wieder aufnimmt, ohne dass es jemand entscheidet:

* **Firefox-Erweiterung signieren** — vom Betreiber ausgenommen.
* **GPU-Durchreichung** — die Maschine hat eine QEMU-Standard-VGA.
* **code-server, Guacamole für RDP-Ziele, Kerberos und Netzlaufwerke** — gestrichen am 2026-09-03.
* **Passwort-Durchreichung an Netzlaufwerke** — ausdrücklich verworfen (`plan.md` §17.9).
* **Inhalte mitschneiden, TLS aufbrechen, besuchte Adressen protokollieren** — das wäre der Punkt,
  an dem aus einer Firewall eine Überwachungsanlage wird.
