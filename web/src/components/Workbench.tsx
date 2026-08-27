import { useEffect } from 'react'
import { t } from '../lib/i18n'

/**
 * Ein Bearbeitungsbereich, der das Hauptfenster übernimmt.
 *
 * Vorher lag der Workspace-Editor in einer Seitenleiste von 560 px. Das ging,
 * solange darin ein Formular stand. Es geht nicht mehr, seit dort App-Listen,
 * Build-Protokolle und Zuteilungen je Nutzer liegen — Inhalte, die Breite
 * brauchen, um lesbar zu sein.
 *
 * Deshalb hier ein Wechsel der Ansicht statt einer Überlagerung: Aus
 * *Workspaces* wird *Workspaces / Arbeitsplatz*, mit Reitern darunter. Der
 * Weg zurück steht als erster Teil des Pfades, nicht als Kreuz in einer Ecke —
 * man ist nicht in einem Dialog, sondern eine Ebene tiefer.
 *
 * Die Seitenleiste bleibt, wo sie hingehört: für kurze Formulare, die man
 * neben dem Bestand ausfüllt (Nutzer, Gruppen).
 */
export function Workbench({
  crumb, title, subtitle, tabs, tabLabel, tab, onTab, onBack, actions, children,
}: {
  /** Die Ebene darüber. Ihr Text ist der Weg zurück. */
  crumb: string
  title: string
  subtitle?: string
  tabs: string[]
  /** Übersetzt die Beschriftung. Die Werte bleiben unverändert, damit der
      Vergleich mit `tab` sprachunabhängig ist. */
  tabLabel?: (s: string) => string
  tab: string
  onTab: (t: string) => void
  onBack: () => void
  actions?: React.ReactNode
  children: React.ReactNode
}) {
  // Escape führt eine Ebene zurück — dieselbe Geste wie in der Seitenleiste,
  // damit die Hand sie nicht neu lernen muss.
  useEffect(() => {
    const esc = (e: KeyboardEvent) => {
      if (e.key === 'Escape' && !(e.target as HTMLElement)?.closest('input, textarea')) onBack()
    }
    document.addEventListener('keydown', esc)
    return () => document.removeEventListener('keydown', esc)
  }, [onBack])

  return (
    <div className="wrap wb">
      <header className="wb__head">
        <div className="wb__ident">
          <nav className="wb__crumb" aria-label={t('Pfad')}>
            <button type="button" className="wb__up" onClick={onBack}>{crumb}</button>
            <span className="wb__sep" aria-hidden="true">/</span>
            <span className="wb__here">{title}</span>
          </nav>
          <h1 className="h-page">{title}</h1>
          {subtitle && <p className="sub data wb__sub">{subtitle}</p>}
        </div>
        {actions && <div className="wb__actions">{actions}</div>}
      </header>

      <nav className="wb__tabs" aria-label={t('Bereiche')}>
        {tabs.map((x) => (
          <button key={x} type="button"
            className={`wb__tab${x === tab ? ' is-on' : ''}`}
            aria-current={x === tab ? 'page' : undefined}
            onClick={() => onTab(x)}>
            {tabLabel ? tabLabel(x) : x}
          </button>
        ))}
      </nav>

      <div className="wb__body">{children}</div>
    </div>
  )
}
