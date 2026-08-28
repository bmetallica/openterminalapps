import { useEffect, useState } from 'react'
import type { Session, Stream, Template } from '../lib/api'
import { t } from '../lib/i18n'
import { installPath, openInTab } from '../lib/routes'

/**
 * „Auf den Desktop legen" — eine Anwendung als eigenständiges Fenster.
 *
 * Wie eine Ablage zustande kommt, entscheidet allein der Browser. Er meldet
 * sich mit `beforeinstallprompt`, sobald er die Seite dafür geeignet hält,
 * und erst dann darf gefragt werden. Ohne dieses Ereignis gibt es nichts
 * auszulösen — ein Knopf, der auf gut Glück nichts tut, ist schlimmer als
 * keiner.
 *
 * **Und er hält sich an die Adresse, auf der er steht.** Der Browser liest
 * das Manifest einmal kurz nach dem Laden; was danach im Dokument getauscht
 * wird, ändert an seiner Entscheidung nichts mehr. Ein Knopf im Viewer, der
 * behauptet, „diese Anwendung" abzulegen, legte in Wahrheit das Dashboard ab.
 * Deshalb führt der Weg über eine eigene Adresse, deren Manifest von Anfang
 * an die richtige Anwendung meint: `/launch/<vorlage>/<app>?ablegen`.
 *
 * Firefox kennt das Ereignis auf dem Rechner nicht. Dort steht statt des
 * Knopfes der Weg über das Browsermenü.
 */

type InstallPrompt = Event & {
  prompt: () => Promise<void>
  userChoice: Promise<{ outcome: 'accepted' | 'dismissed' }>
}

/** Fängt das Angebot des Browsers auf und hält es fest, bis jemand fragt. */
export function useInstallPrompt(): {
  prompt: InstallPrompt | null
  done: boolean
  clear: () => void
} {
  const [prompt, setPrompt] = useState<InstallPrompt | null>(null)
  const [done, setDone] = useState(false)

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

  return { prompt, done, clear: () => setPrompt(null) }
}

/** Der Hinweis im Viewer: verweist auf die Seite, auf der es wirklich geht. */
export function InstallButton({ session, stream, template }: {
  session: Session
  stream?: Stream
  template?: Template
  onToast?: (m: string, tone?: 'ok' | 'bad') => void
}) {
  if (!template) return null
  const label = stream
    ? template.apps.find((a) => a.slug === stream.app_slug)?.name ?? stream.app_slug
    : session.template_name

  return (
    <div className="viewer__row" style={{ marginTop: 8 }}>
      <button className="btn btn--sm"
        onClick={() => openInTab(installPath(template.slug, stream?.app_slug))}>
        {t('{name} auf den Desktop legen', { name: label })}
      </button>
    </div>
  )
}

/**
 * Die Seite, auf der abgelegt wird.
 *
 * Sie startet mit Absicht nichts. Wer ein Symbol anlegt, will noch nicht
 * arbeiten — und einen Container hochzufahren, damit jemand ein Symbol
 * bekommt, wäre die teuerste Art, nichts zu tun.
 */
export function InstallCard({ name, icon, onOpen }: {
  name: string
  icon: string
  onOpen: () => void
}) {
  const { prompt, done, clear } = useInstallPrompt()
  const [note, setNote] = useState<string | null>(null)

  return (
    <div className="wrap">
      <div className="place">
        <span className="place__icon" aria-hidden="true">{icon}</span>
        <h1 className="h-page">{name}</h1>

        {done || note ? (
          <p className="place__body">{note ?? t('{name} liegt jetzt auf deinem Desktop.', { name })}</p>
        ) : (
          <p className="place__body">
            {t('Als eigenes Fenster ohne Browserleiste. Wer noch nicht angemeldet ist, meldet sich beim Öffnen an — danach geht es direkt weiter.')}
          </p>
        )}

        {prompt && !done && (
          <button className="btn btn--primary" onClick={() => {
            void prompt.prompt().then(() => prompt.userChoice).then(({ outcome }) => {
              setNote(outcome === 'accepted'
                ? t('{name} liegt jetzt auf deinem Desktop.', { name })
                : t('Abgebrochen. Du kannst es jederzeit erneut versuchen.'))
              clear()
            }).catch(() => setNote(t('Der Browser hat die Verknüpfung abgelehnt.')))
          }}>
            {t('Auf den Desktop legen')}
          </button>
        )}

        {!prompt && !done && !note && (
          <p className="place__hint">
            {t('Dein Browser bietet das Ablegen über sein eigenes Menü an — in Chrome und Edge über das Symbol rechts in der Adressleiste, in Firefox über „Diese Seite installieren".')}
          </p>
        )}

        <button className="btn" onClick={onOpen}>{t('Jetzt öffnen')}</button>
      </div>
    </div>
  )
}
