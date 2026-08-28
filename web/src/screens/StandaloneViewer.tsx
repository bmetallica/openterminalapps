import { useCallback, useEffect, useRef, useState } from 'react'
import { SessionViewer } from './SessionViewer'
import { InstallCard } from '../components/InstallButton'
import { ApiError, api, type Session, type Stream, type Template } from '../lib/api'
import { t, useLang } from '../lib/i18n'
import { viewPath, type Route } from '../lib/routes'

type State =
  | { phase: 'ablegen'; name: string; icon: string }
  | { phase: 'busy'; note: string }
  | { phase: 'ready'; session: Session; stream?: Stream }
  | { phase: 'failed'; note: string }

/**
 * Eine einzelne Anwendung in einem eigenen Tab.
 *
 * Der Unterschied zur Ansicht im Dashboard ist nicht die Darstellung, sondern
 * der Weg dorthin: Hier steht am Anfang eine Adresse und sonst nichts. Was
 * laufen muss, damit etwas zu sehen ist, stellt dieser Bildschirm selbst her —
 * bei `/launch/…` bis hin zum Starten des Containers.
 *
 * Warum das Warten hier steht und nicht im Dashboard: Eine Verknüpfung auf dem
 * Desktop wird angeklickt, wenn gerade nichts läuft. Das ist der Normalfall
 * dieser Adresse, nicht die Ausnahme.
 */
export function StandaloneViewer({ route, onToast }: {
  route: Extract<Route, { kind: 'view' } | { kind: 'launch' }>
  onToast: (m: string, tone?: 'ok' | 'bad') => void
}) {
  useLang()
  const [state, setState] = useState<State>({ phase: 'busy', note: t('Wird geladen…') })
  const [templates, setTemplates] = useState<Template[]>([])
  // Nur einmal starten, auch wenn React den Effekt zweimal ausführt.
  const started = useRef(false)

  const pick = useCallback((session: Session, display?: number): State => {
    const stream = display ? session.streams.find((s) => s.display_num === display) : undefined
    return { phase: 'ready', session, stream }
  }, [])

  // „Jetzt öffnen" auf der Ablege-Seite: dieselbe Adresse ohne `?ablegen`.
  // Neu geladen und nicht weitergeschaltet, weil der Startlauf unten genau
  // einmal läuft — und zwar beim Laden.
  const oeffnen = useCallback(() => {
    window.location.href = window.location.pathname
  }, [])

  useEffect(() => {
    if (started.current) return
    started.current = true

    void (async () => {
      try {
        const list = await api.templates()
        setTemplates(list)

        // Ablegen heisst ablegen — hier wird nichts gestartet.
        if (route.kind === 'launch' && route.install) {
          const tpl = list.find((x) => x.slug === route.templateSlug)
          if (!tpl) {
            setState({ phase: 'failed', note: t('Diesen Arbeitsplatz gibt es nicht.') })
            return
          }
          const app = route.appSlug
            ? tpl.apps.find((a) => a.slug === route.appSlug)
            : undefined
          if (route.appSlug && !app) {
            setState({ phase: 'failed', note: t('Diese Anwendung gibt es nicht.') })
            return
          }
          setState({
            phase: 'ablegen',
            name: app?.name ?? tpl.friendly_name,
            icon: app?.icon || tpl.icon || '▣',
          })
          return
        }

        if (route.kind === 'view') {
          const sessions = await api.sessions()
          const found = sessions.find((s) => s.id === route.sessionId)
          if (!found) {
            setState({ phase: 'failed', note: t('Diese Sitzung gibt es nicht mehr.') })
            return
          }
          setState(pick(found, route.display))
          return
        }

        // ---------------------------------------------------------- launch
        const tpl = list.find((x) => x.slug === route.templateSlug)
        if (!tpl) {
          setState({ phase: 'failed', note: t('Diesen Arbeitsplatz gibt es nicht.') })
          return
        }

        const sessions = await api.sessions()
        let session = sessions.find((s) => s.template_id === tpl.id)
        if (!session) {
          setState({ phase: 'busy', note: t('{name} wird gestartet…', { name: tpl.friendly_name }) })
          session = await api.startSession(tpl.id)
        }

        if (!route.appSlug) {
          setState(pick(session))
          return
        }

        const open = session.streams.find((s) => s.app_slug === route.appSlug)
        if (open) {
          setState(pick(session, open.display_num))
          return
        }

        const app = tpl.apps.find((a) => a.slug === route.appSlug)
        setState({ phase: 'busy', note: t('{name} wird gestartet…', { name: app?.name ?? route.appSlug }) })
        const updated = await api.startApp(session.id, route.appSlug)
        const stream = updated.streams.find((s) => s.app_slug === route.appSlug)
        setState(pick(updated, stream?.display_num))
      } catch (err) {
        setState({
          phase: 'failed',
          note: err instanceof ApiError ? err.message : t('Start fehlgeschlagen'),
        })
      }
    })()
  }, [route, pick])

  if (state.phase === 'ablegen') {
    return <InstallCard name={state.name} icon={state.icon} onOpen={oeffnen} />
  }

  if (state.phase === 'busy') {
    return (
      <div className="boot">
        <span className="silk">{state.note}</span>
      </div>
    )
  }

  if (state.phase === 'failed') {
    return (
      <div className="wrap"><div className="empty">
        <p className="empty__title">{t('Das lässt sich gerade nicht öffnen')}</p>
        <p className="empty__body">{state.note}</p>
        <button className="btn btn--primary" onClick={() => { window.location.href = '/' }}>
          {t('Zum Dashboard')}
        </button>
      </div></div>
    )
  }

  const { session, stream } = state
  return (
    <SessionViewer
      session={session}
      stream={stream}
      template={templates.find((x) => x.id === session.template_id)}
      standalone
      onSwitch={(next) => {
        setState({ phase: 'ready', session, stream: next })
        // Die Adresse mitführen, damit Neuladen dieselbe Ansicht zeigt.
        window.history.replaceState(null, '', viewPath(session.id, next?.display_num))
      }}
      onClose={() => { window.location.href = '/' }}
      onToast={onToast} />
  )
}
