import { getLang } from '../lib/i18n'
import { wirksam } from '../lib/theme'

/**
 * Die Ansicht einer Erweiterung, eingebettet in OTA (Handbuch Kapitel 39).
 *
 * Unter OTAs eigener Adresse (/x/<slug>/ansicht/…), also gleicher Herkunft:
 * Das Anmelde-Cookie geht mit, Traefik fragt die API (forwardAuth), und die
 * Erweiterung bekommt signierte Kopfzeilen mit dem Menschen. Sprache und
 * Hell/Dunkel reicht OTA in der Adresse weiter.
 */
export function ErweiterungAnsicht({ url, titel, hoehe = '72vh' }: { url: string; titel: string; hoehe?: string }) {
  const trenner = url.includes('?') ? '&' : '?'
  const src = `${url}${trenner}sprache=${getLang()}&thema=${wirksam()}`
  return (
    <iframe title={titel} src={src} className="erweiterung-ansicht"
      style={{ width: '100%', height: hoehe, border: '1px solid var(--edge)', borderRadius: 10, background: 'var(--ground)' }} />
  )
}
