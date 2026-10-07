import { useEffect, useState } from 'react'
import { ApiError, api, type Me } from '../lib/api'
import { useMarke } from '../lib/branding'
import { setLang, t, useLang, type Lang } from '../lib/i18n'
import { setTheme, useTheme, type Theme } from '../lib/theme'

export function Login({ onDone, notfall = false, fehler }: {
  onDone: (me: Me) => void
  /** Der Notzugang: dieselbe Maske, aber sie sagt, was sie ist. */
  notfall?: boolean
  /** Was bei der zentralen Anmeldung schiefging, falls sie es versucht hat. */
  fehler?: string
}) {
  const lang = useLang()
  const gewand = useTheme()
  const marke = useMarke()
  const [username, setUsername] = useState('')
  const [password, setPassword] = useState('')
  const [totp, setTotp] = useState('')
  const [needsTotp, setNeedsTotp] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)

  // Unter /login: Gibt es noch lokale Konten, die umziehen müssen? Nein —
  // dann gleich weiter zur zentralen Anmeldung (Betreiber, 2026-10-08). Bis
  // dahin bot diese Seite jedem eine lokale Maske an, und ein in OTA
  // angelegtes Konto kam nur hier herein, an Keycloak vorbei.
  const [lokale, setLokale] = useState<boolean | null>(notfall ? true : null)
  const [umzug, setUmzug] = useState<string | null>(null)

  useEffect(() => {
    if (notfall) return
    api.anmeldung()
      .then((a) => {
        setLokale(a.lokale_konten)
        // Ein Fehler der zentralen Anmeldung bleibt stehen — sonst liefe der
        // Browser in eine Schleife: weiterleiten, scheitern, weiterleiten.
        if (!a.lokale_konten && !fehler) zentral()
      })
      .catch(() => setLokale(true))
  }, [notfall, fehler])

  function zentral(name = '') {
    const hint = name ? `&login_hint=${encodeURIComponent(name)}` : ''
    window.location.replace(`/api/auth/oidc/start?next=/${hint}`)
  }

  async function submit(e: React.FormEvent) {
    e.preventDefault()
    setBusy(true)
    setError(null)
    try {
      const me = await api.login(username, password, totp || undefined)
      if (notfall) { onDone(me); return }
      // Ein lokales Konto zieht jetzt um — mit diesem Passwort. Das
      // Notfallkonto bleibt lokal (409) und meldet sich einfach an.
      try {
        const u = await api.umziehen(password)
        setUmzug(u.status)
        setTimeout(() => window.location.replace(u.weiter), 2500)
      } catch {
        // Keycloak antwortet nicht o. ä.: Lieber lokal herein als gar nicht.
        // Der Umzug kommt beim nächsten Anmelden wieder.
        onDone(me)
      }
    } catch (err) {
      // Ein Konto der zentralen Anmeldung am falschen Eingang: hinüber, mit
      // dem schon getippten Namen.
      if (!notfall && err instanceof ApiError && err.status === 409) { zentral(username); return }
      const msg = err instanceof ApiError ? err.message : t('Anmeldung fehlgeschlagen')
      // Die API verlangt den zweiten Faktor erst, wenn Name und Passwort stimmen.
      if (msg.includes(t('Code aus deiner App'))) setNeedsTotp(true)
      setError(msg)
    } finally {
      setBusy(false)
    }
  }

  // Weiterleitung läuft — nichts zeigen, was gleich wieder verschwindet.
  if (!notfall && (lokale === null || (lokale === false && !fehler))) {
    return <div className="login"><p className="sub">{t('Anmeldung wird geöffnet…')}</p></div>
  }
  const formZeigen = notfall || lokale === true

  return (
    <div className="login">
      <form className="login__card panel" onSubmit={submit}>
        {/* Der einzige Bildschirm, auf dem sich die Anwendung vorstellt,
            statt benutzt zu werden — hier darf die Marke Farbe haben. Der
            Schriftzug steckt im Bild, deshalb keine zweite Überschrift. */}
        <img className={`login__logo${marke.logo_url ? ' login__logo--eigen' : ''}`}
          src={marke.logo_url ?? '/logo.svg'} alt={marke.name} />
        <p className="sub" style={{ marginBottom: notfall ? 12 : 22 }}>
          {notfall
            ? t('Notzugang mit lokalem Konto. Er umgeht die zentrale Anmeldung und wird protokolliert.')
            : formZeigen
              ? t('Hier melden sich nur noch Konten an, die noch nicht zur zentralen Anmeldung umgezogen sind. Beim Anmelden ziehen sie um — mit demselben Passwort.')
              : t('Melde dich an, um deinen Arbeitsplatz zu öffnen.')}
        </p>

        {notfall && (
          <p className="note-warn" style={{ marginBottom: 18 }}>
            {t('Dieser Weg ist für den Fall gedacht, dass die zentrale Anmeldung nicht erreichbar ist. Wenn sie läuft, nimm sie.')}
          </p>
        )}

        {typeof window !== 'undefined'
          && new URLSearchParams(window.location.search).has('abgemeldet') && (
          <p className="note-info" style={{ marginBottom: 18 }}>
            {t('Du bist abgemeldet — hier und bei der zentralen Anmeldung.')}
          </p>
        )}

        {fehler && (
          <p className="note-warn" style={{ marginBottom: 18 }}>
            {t('Die zentrale Anmeldung hat nicht geklappt: {grund}', { grund: fehler })}
          </p>
        )}

        {umzug && <p className="note-info" style={{ marginBottom: 18 }}>{umzug}</p>}

        {!notfall && (
          <div className="viewer__row" style={{ marginBottom: 18 }}>
            <button type="button" className={formZeigen ? 'btn' : 'btn btn--primary'}
              style={formZeigen ? undefined : { width: '100%', height: 40 }}
              onClick={() => zentral()}>
              {t('Über die zentrale Anmeldung')}
            </button>
          </div>
        )}

        {formZeigen && !umzug && <>
        <label className="field">
          <span className="field__label" style={{ display: 'block', marginBottom: 8 }}>{t('Benutzername')}</span>
          <div className="row-item">
            <input value={username} autoFocus autoComplete="username" required
              onChange={(e) => setUsername(e.target.value)} />
          </div>
        </label>

        <label className="field">
          <span className="field__label" style={{ display: 'block', marginBottom: 8 }}>{t('Passwort')}</span>
          <div className="row-item">
            <input type="password" value={password} autoComplete="current-password" required
              onChange={(e) => setPassword(e.target.value)} />
          </div>
        </label>

        {needsTotp && (
          <label className="field">
            <span className="field__label" style={{ display: 'block', marginBottom: 8 }}>{t('Code aus deiner App')}</span>
            <div className="row-item">
              {/* Kein maxLength von 6 und kein numerisches Tastenfeld: Hier
                  darf auch ein Rückfallcode stehen, und der hat Buchstaben
                  und einen Bindestrich. Mit der alten Begrenzung liess sich
                  einer gar nicht eingeben — der Weg für ein verlorenes
                  Telefon wäre damit versperrt gewesen. */}
              <input value={totp} autoComplete="one-time-code" maxLength={32}
                aria-label={t('Code aus deiner App')} autoFocus
                onChange={(e) => setTotp(e.target.value)} />
            </div>
            <p className="field__hint">
              {t('Sechs Ziffern aus der App — oder einer deiner Rückfallcodes.')}
            </p>
          </label>
        )}

        {error && <p className="login__error" role="alert">{error}</p>}

        <button className="btn btn--primary" style={{ width: '100%', height: 40 }} disabled={busy}>
          {busy ? t('Wird geprüft…') : t('Anmelden')}
        </button>
        </>}

        {/* Die Sprache muss schon vor der Anmeldung wählbar sein — sonst
            steht wer kein Deutsch liest vor einer deutschen Anmeldemaske. */}
        <div className="login__lang" role="radiogroup" aria-label={t('Sprache')}>
          {(['de', 'en'] as Lang[]).map((l) => (
            <button key={l} type="button" role="radio" aria-checked={lang === l}
              className={`login__langopt${lang === l ? ' is-on' : ''}`}
              onClick={() => setLang(l)}>
              {l === 'de' ? 'Deutsch' : 'English'}
            </button>
          ))}
        </div>

        {/* Aus demselben Grund wie die Sprache: Wer den hellen Bildschirm
            braucht, braucht ihn schon auf der Anmeldemaske. */}
        <div className="login__lang" role="radiogroup" aria-label={t('Gewand')}>
          {([['system', t('Wie der Rechner')], ['hell', t('Hell')],
             ['dunkel', t('Dunkel')]] as [Theme, string][]).map(([v, name]) => (
            <button key={v} type="button" role="radio" aria-checked={gewand === v}
              className={`login__langopt${gewand === v ? ' is-on' : ''}`}
              onClick={() => setTheme(v)}>
              {name}
            </button>
          ))}
        </div>
      </form>
    </div>
  )
}
