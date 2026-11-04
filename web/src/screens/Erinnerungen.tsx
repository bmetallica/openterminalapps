import { type ErweiterungAnsicht as Ansicht } from '../lib/api'
import { ErweiterungAnsicht } from '../components/ErweiterungAnsicht'
import { t, useLang } from '../lib/i18n'

/** Die Kennung der Gedächtnis-Erweiterung (plugin_ota-opencode). */
export const GEDAECHTNIS = 'gedaechtnis'

/**
 * „opencode — Erinnerungen": die Ansicht der Gedächtnis-Erweiterung als
 * eigener Punkt der Seitenleiste (Kapitel 39).
 *
 * Bis zum 2026-11-04 eine Lasche unter Mein Konto. Dort suchte sie niemand:
 * Wer mit opencode arbeitet, will nachsehen, was es behalten hat, und nicht
 * in den Einstellungen seines Kontos. Der Punkt erscheint nur für Menschen,
 * denen die Erweiterung eine Ansicht anbietet — also nur für Berechtigte.
 */
export function Erinnerungen({ ansicht }: { ansicht: Ansicht }) {
  useLang()
  return (
    <div className="wrap">
      <header className="topbar">
        <div>
          <p className="silk" style={{ marginBottom: 6 }}>opencode</p>
          <h1 className="h-page">{t('Erinnerungen')}</h1>
        </div>
      </header>
      <ErweiterungAnsicht url={ansicht.url} titel={ansicht.titel} hoehe="calc(100vh - 150px)" />
    </div>
  )
}
