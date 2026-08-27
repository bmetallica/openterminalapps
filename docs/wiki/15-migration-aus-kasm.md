# 15 · Ein Profil aus Kasm übernehmen

*Für Administratoren.* ✅

Übernommen wird das **Profil**, nicht der Container. Der Container entsteht in OTA aus dem
Golden Image neu; wertvoll ist das Home des Nutzers.

**Kasm bleibt dabei unangetastet** und läuft weiter. Das Skript kopiert, es verschiebt
nicht.

## Vorgehen

```bash
cd /opt/openterminalapps

./scripts/migrate-kasm-profile.sh --dry-run bmetallica   # zeigt, was käme
./scripts/migrate-kasm-profile.sh bmetallica             # kopiert
./scripts/migrate-kasm-profile.sh --verify bmetallica    # prüft nach
```

Das Skript ist **idempotent** — ein zweiter Lauf gleicht nur die Unterschiede ab. Ein
bereits vorhandenes OTA-Profil wird vorher beiseitegelegt, nicht überschrieben.

Läuft eine Session des Nutzers, bricht es ab. Ein Profil unter einem geöffneten Editor
auszutauschen führt auf beiden Seiten zu Datenverlust.

## Was mitkommt — und was nicht

**Mitgenommen** wird alles, was Arbeit ist: Einstellungen, Extensions, SSH- und
GPG-Schlüssel, Git-Konfiguration, XFCE-Layout, Browser-Profil, Editor-Verlauf.

**Weggelassen** wird, was jederzeit neu entsteht oder nach dem Umzug stören würde:

| Ausgeschlossen | Warum |
|---|---|
| `CacheStorage` der Erweiterungen | Service-Worker-Cache. Im gemessenen Profil **193 MB** und vollständig nachladbar |
| Chromes Modelle und Listen | `component_crx_cache`, `WasmTtsEngine`, `Safe Browsing`, Wörterbücher — zusammen über **91 MB**, alle nachladbar |
| Editor-Caches | `Cache`, `CachedData`, `CachedExtensionVSIXs`, `GPUCache` |
| `core.*` | Absturzabbilder aus alten Sitzungen |
| `.Xauthority`, `.ICEauthority`, Sockets | Laufzeitkram der alten Sitzung, der im neuen Container stört |
| `.kasmpasswd`, `.vnc/` | Das alte VNC-Passwort. OTA vergibt pro Session ein eigenes Geheimnis — das alte mitzunehmen wäre schlicht falsch |

**Ergebnis im Testlauf:** 805 MB Rohdaten wurden zu **63 MB**, ohne dass eine Nutzerdatei
fehlte.

## Abnahme

`--verify` prüft, dass das Wesentliche angekommen ist, und zeigt die übernommene
`settings.json` zur Sichtkontrolle:

```
✓ Profil vorhanden                    ✓ Continue-Konfiguration übernommen
✓ VS-Code-Einstellungen übernommen    ✓ Kein Absturzabbild mitgekommen
✓ Extensions übernommen               ✓ Kein altes VNC-Passwort mitgekommen
✓ SSH-Schlüssel übernommen            ✓ Eigentümer ist 1000:1000
✓ GPG-Verzeichnis übernommen          ✓ XFCE-Einstellungen übernommen
```

Danach den Arbeitsplatz starten und hineinsehen — das ist die einzige Abnahme, die zählt.

## Wenn etwas nicht stimmt

Das bisherige OTA-Profil liegt als `user.vor-migration-<zeitstempel>` daneben:

```bash
cd /srv/ota/profiles/<nutzer>
mv user user.verworfen
mv user.vor-migration-<zeitstempel> user
chown -R 1000:1000 user
```

Und das Kasm-Profil unter `/srv/kasm_profiles/<nutzer>` ist ohnehin unverändert — der
Umzug lässt sich beliebig oft wiederholen.

## Der umgekehrte Weg

Es gibt keinen. OTA schreibt nie nach `/srv/kasm_profiles`. Wer zurück will, arbeitet
einfach wieder in Kasm — dort ist alles noch so, wie es war.
