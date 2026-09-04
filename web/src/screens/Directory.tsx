import { useEffect, useState } from 'react'
import { KcVerzeichnis } from '../components/KcVerzeichnis'
import { Led } from '../components/controls'
import { api, type KeycloakStatus } from '../lib/api'
import { t as tr, useLang } from '../lib/i18n'

/**
 * Identität: Keycloak und das Verzeichnis dahinter.
 *
 * **Ein Weg, nicht zwei.** Bis zum 2026-09-04 stand hier zusätzlich eine
 * eigene LDAP-Anbindung — OTA sprach selbst mit dem Verzeichnis. Sie ist
 * entfallen: Angebunden wird in Keycloak, angemeldet wird über Keycloak
 * (`auth-roadmap.md`, Entscheidung 4).
 */

/**
 * Zustand des Identity Providers.
 *
 * Die Frage vor jedem weiteren Schritt: Läuft er, und was darf OTA darin?
 *
 * Die Fähigkeiten stehen einzeln da und nicht als „verbunden": Bei einem
 * fremden Keycloak ist OTA Gast, und was es dort nicht darf, soll es hier
 * lesen können statt später an einem 403 zu scheitern.
 */
function KeycloakKarte() {
  const [st, setSt] = useState<KeycloakStatus | null>(null)
  const [laedt, setLaedt] = useState(true)

  useEffect(() => {
    api.keycloakStatus()
      .then(setSt).catch(() => setSt(null))
      .finally(() => setLaedt(false))
  }, [])

  if (laedt || !st) return null

  const NAMEN: Record<string, string> = {
    konten: tr('Konten'),
    gruppen: tr('Gruppen'),
    clients: tr('Anwendungen'),
    verzeichnis: tr('Verzeichnisanbindung'),
  }

  return (
    <>
      <div className="section__head">
        <span className="silk">{tr('Zentrale Identität')}</span>
        <span className="section__rule" />
        <Led status={st.erreichbar ? 'live' : 'fail'} />
      </div>
      <div className="panel" style={{ padding: '16px 20px', marginBottom: 18 }}>
        <div className="bay__facts" style={{ marginBottom: 12 }}>
          <span className="bay__fact"><span className="silk">{tr('Betriebsart')}</span>
            <b>{st.betriebsart === 'mitgeliefert' ? tr('Mitgeliefert') : tr('Vorhanden')}</b></span>
          <span className="bay__fact"><span className="silk">{tr('Realm')}</span>
            <b>{st.realm}</b></span>
          <span className="bay__fact"><span className="silk">{tr('Fassung')}</span>
            <b>{st.version ?? '—'}</b></span>
        </div>

        {st.fehler ? (
          <p className="note-warn" style={{ margin: 0 }}>{st.fehler}</p>
        ) : (
          <div className="strip">
            {Object.entries(st.faehigkeiten).map(([k, v]) => (
              <span key={k} className={`chip${v ? ' is-on' : ''}`}>
                {NAMEN[k] ?? k}
              </span>
            ))}
          </div>
        )}

        <p className="field__hint" style={{ marginTop: 12 }}>
          {st.betriebsart === 'mitgeliefert'
            ? tr('Läuft in diesem Stack und macht die Anmeldung. OTA richtet ihn ein und verwaltet ihn von hier aus.')
            : tr('Ein fremdes Keycloak. OTA ist dort Gast: Es löscht nichts und fasst nur die eigenen Gruppen an. Was oben grau ist, darf das Dienstkonto nicht.')}
        </p>
      </div>
    </>
  )
}

export function Directory({ onToast }: { onToast: (m: string, tone?: 'ok' | 'bad') => void }) {
  useLang()
  return (
    <>
      <p className="sub" style={{ marginBottom: 16 }}>
        {tr('Ein Verzeichnis (LDAP oder Active Directory) wird in Keycloak angebunden — dort liegt die Anmeldung, und dort werden die Konten geführt. OTA übernimmt sie und ordnet ihre Gruppen zu.')}
      </p>
      <p className="note-info" style={{ marginBottom: 18 }}>
        {tr('Das lokale Notfallkonto bleibt davon unberührt. Es wird immer lokal geprüft — auch wenn im Verzeichnis ein gleichnamiger Eintrag steht.')}
      </p>

      <KeycloakKarte />
      <KcVerzeichnis onToast={onToast} />
    </>
  )
}
