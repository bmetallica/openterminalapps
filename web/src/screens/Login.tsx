import { useState } from 'react'
import { ApiError, api, type Me } from '../lib/api'
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
  const [username, setUsername] = useState('')
  const [password, setPassword] = useState('')
  const [totp, setTotp] = useState('')
  const [needsTotp, setNeedsTotp] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)

  async function submit(e: React.FormEvent) {
    e.preventDefault()
    setBusy(true)
    setError(null)
    try {
      onDone(await api.login(username, password, totp || undefined))
    } catch (err) {
      const msg = err instanceof ApiError ? err.message : t('Anmeldung fehlgeschlagen')
      // Die API verlangt den zweiten Faktor erst, wenn Name und Passwort stimmen.
      if (msg.includes(t('Code aus deiner App'))) setNeedsTotp(true)
      setError(msg)
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="login">
      <form className="login__card panel" onSubmit={submit}>
        {/* Der einzige Bildschirm, auf dem sich die Anwendung vorstellt,
            statt benutzt zu werden — hier darf die Marke Farbe haben. Der
            Schriftzug steckt im Bild, deshalb keine zweite Überschrift. */}
        <img className="login__logo" src="/logo.svg" alt="OpenTerminalApps" />
        <p className="sub" style={{ marginBottom: notfall ? 12 : 22 }}>
          {notfall
            ? t('Notzugang mit lokalem Konto. Er umgeht die zentrale Anmeldung und wird protokolliert.')
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

        {!notfall && (
          <div className="viewer__row" style={{ marginBottom: 18 }}>
            <button type="button" className="btn"
              onClick={() => { window.location.href = '/api/auth/oidc/start?next=/' }}>
              {t('Über die zentrale Anmeldung')}
            </button>
          </div>
        )}

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
