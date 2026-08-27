import { useEffect, useState } from 'react'
import type { Session, Stream, Template } from '../lib/api'
import { t } from '../lib/i18n'

/**
 * „Auf den Desktop legen" — die Anwendung als eigenständiges Fenster.
 *
 * Wie eine Installation zustande kommt, entscheidet allein der Browser. Er
 * meldet sich mit `beforeinstallprompt`, sobald er die Seite für installierbar
 * hält, und erst dann darf gefragt werden. Deshalb erscheint dieser Knopf
 * nicht immer: Ohne das Ereignis gäbe es nichts, was er auslösen könnte, und
 * ein Knopf, der auf gut Glück nichts tut, ist schlimmer als keiner.
 *
 * Firefox kennt das Ereignis auf dem Rechner nicht. Dort steht statt des
 * Knopfes ein Satz, der den Weg über das Browsermenü nennt.
 */

type InstallPrompt = Event & {
  prompt: () => Promise<void>
  userChoice: Promise<{ outcome: 'accepted' | 'dismissed' }>
}

const MANIFEST_ID = 'ota-manifest'

/** Hängt das passende Manifest ins Dokument.
 *
 * Es gibt genau ein `<link rel="manifest">` pro Dokument. Für jede Anwendung
 * ein eigenes Manifest zu brauchen heisst deshalb: austauschen, sobald die
 * Ansicht wechselt — sonst installiert der Browser die zuletzt gesehene App
 * unter dem Namen der aktuellen.
 */
function useManifest(templateSlug: string | undefined, appSlug: string | undefined) {
  useEffect(() => {
    if (!templateSlug) return
    const href = `/api/pwa/manifest.webmanifest?template=${encodeURIComponent(templateSlug)}` +
      (appSlug ? `&app=${encodeURIComponent(appSlug)}` : '')

    let link = document.getElementById(MANIFEST_ID) as HTMLLinkElement | null
    if (!link) {
      link = document.createElement('link')
      link.id = MANIFEST_ID
      link.rel = 'manifest'
      document.head.appendChild(link)
    }
    link.href = href
  }, [templateSlug, appSlug])
}

export function InstallButton({ session, stream, template, onToast }: {
  session: Session
  stream?: Stream
  template?: Template
  onToast: (m: string, tone?: 'ok' | 'bad') => void
}) {
  const [prompt, setPrompt] = useState<InstallPrompt | null>(null)
  const [done, setDone] = useState(false)

  const appSlug = stream?.app_slug
  useManifest(template?.slug, appSlug)

  useEffect(() => {
    const onBefore = (e: Event) => {
      // Ohne das übernimmt der Browser die Frage selbst, zu einem Zeitpunkt,
      // den niemand gewählt hat. Wir heben sie auf, bis jemand danach fragt.
      e.preventDefault()
      setPrompt(e as InstallPrompt)
    }
    const onInstalled = () => { setDone(true); setPrompt(null) }
    window.addEventListener('beforeinstallprompt', onBefore)
    window.addEventListener('appinstalled', onInstalled)
    return () => {
      window.removeEventListener('beforeinstallprompt', onBefore)
      window.removeEventListener('appinstalled', onInstalled)
    }
  }, [])

  const label = stream
    ? template?.apps.find((a) => a.slug === stream.app_slug)?.name ?? stream.app_slug
    : session.template_name

  if (done) {
    return (
      <p className="field__hint" style={{ marginTop: 10 }}>
        {t('{name} liegt jetzt auf deinem Desktop.', { name: label })}
      </p>
    )
  }

  if (!prompt) {
    return (
      <p className="field__hint" style={{ marginTop: 10 }}>
        {t('Diese Anwendung lässt sich als Verknüpfung ablegen — in Firefox über das Browsermenü, in Chrome über das Symbol in der Adressleiste.')}
      </p>
    )
  }

  return (
    <div className="viewer__row" style={{ marginTop: 8 }}>
      <button className="btn btn--sm" onClick={() => {
        void prompt.prompt().then(() => prompt.userChoice).then(({ outcome }) => {
          if (outcome === 'accepted') onToast(t('Wird auf dem Desktop abgelegt…'))
          setPrompt(null)
        }).catch(() => onToast(t('Der Browser hat die Verknüpfung abgelehnt.'), 'bad'))
      }}>
        {t('Auf den Desktop legen')}
      </button>
    </div>
  )
}
