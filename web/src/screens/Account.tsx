import { useEffect, useState } from 'react'
import { Field, Segmented } from '../components/controls'
import { ApiError, api, type Me, type TotpSetup } from '../lib/api'
import { getLang, setLang, t as tr, useLang, type Lang } from '../lib/i18n'

/**
 * Das eigene Konto.
 *
 * Bis hierher konnte ein normaler Nutzer sein Passwort nicht ändern — nur ein
 * Administrator konnte es für ihn setzen. Und der zweite Faktor wurde beim
 * Anmelden zwar geprüft, liess sich aber nirgends einrichten: Wer ihn wollte,
 * musste ein Geheimnis von Hand in die Datenbank schreiben.
 *
 * Beides steht jetzt hier, für jeden Angemeldeten. Nichts davon braucht
 * Verwaltungsrechte — es geht um das eigene Konto.
 */
export function Account({ me, onMe, onToast }: {
  me: Me
  onMe: (me: Me) => void
  onToast: (m: string, tone?: 'ok' | 'bad') => void
}) {
  useLang()
  const [tab, setTab] = useState<'Passwort' | 'Zwei-Faktor' | 'Sprache'>('Passwort')

  return (
    <div className="wrap">
      <header className="topbar">
        <div>
          <p className="silk" style={{ marginBottom: 6 }}>{tr('Angemeldet als {name}', { name: me.username })}</p>
          <h1 className="h-page">{tr('Mein Konto')}</h1>
        </div>
      </header>

      <nav className="wb__tabs" aria-label={tr('Bereiche')}>
        {(['Passwort', 'Zwei-Faktor', 'Sprache'] as const).map((x) => (
          <button key={x} type="button"
            className={`wb__tab${x === tab ? ' is-on' : ''}`}
            aria-current={x === tab ? 'page' : undefined}
            onClick={() => setTab(x)}>{tr(x)}</button>
        ))}
      </nav>

      <div className="wb__body">
        {tab === 'Passwort' && <PasswordPart onToast={onToast} />}
        {tab === 'Zwei-Faktor' && <TotpPart me={me} onMe={onMe} onToast={onToast} />}
        {tab === 'Sprache' && <LanguagePart onMe={onMe} onToast={onToast} />}
      </div>
    </div>
  )
}

// --------------------------------------------------------------- Passwort

function PasswordPart({ onToast }: { onToast: (m: string, tone?: 'ok' | 'bad') => void }) {
  const [current, setCurrent] = useState('')
  const [next, setNext] = useState('')
  const [again, setAgain] = useState('')
  const [busy, setBusy] = useState(false)

  async function submit(e: React.FormEvent) {
    e.preventDefault()
    if (next !== again) {
      onToast(tr('Die beiden neuen Passwörter sind nicht gleich.'), 'bad')
      return
    }
    setBusy(true)
    try {
      await api.changePassword(current, next)
      setCurrent(''); setNext(''); setAgain('')
      onToast(tr('Passwort geändert. Deine anderen Sitzungen sind jetzt abgemeldet.'))
    } catch (err) {
      onToast(err instanceof ApiError ? err.message : tr('Wechsel fehlgeschlagen'), 'bad')
    } finally {
      setBusy(false)
    }
  }

  return (
    <form onSubmit={submit} style={{ maxWidth: 460 }}>
      <Field label={tr('Aktuelles Passwort')}>
        <div className="row-item">
          <input type="password" value={current} required autoComplete="current-password"
            aria-label={tr('Aktuelles Passwort')} onChange={(e) => setCurrent(e.target.value)} />
        </div>
      </Field>
      <Field label={tr('Neues Passwort')} hint={tr('Mindestens 12 Zeichen.')}>
        <div className="row-item">
          <input type="password" value={next} required autoComplete="new-password"
            aria-label={tr('Neues Passwort')} onChange={(e) => setNext(e.target.value)} />
        </div>
      </Field>
      <Field label={tr('Noch einmal')}>
        <div className="row-item">
          <input type="password" value={again} required autoComplete="new-password"
            aria-label={tr('Noch einmal')} onChange={(e) => setAgain(e.target.value)} />
        </div>
      </Field>
      <p className="note-info" style={{ marginBottom: 14 }}>
        {tr('Ein Passwortwechsel meldet alle anderen Sitzungen ab — diese hier bleibt bestehen.')}
      </p>
      <button className="btn btn--primary" disabled={busy}>
        {busy ? tr('Wird gespeichert…') : tr('Passwort ändern')}
      </button>
    </form>
  )
}

// ------------------------------------------------------------- Zwei-Faktor

function TotpPart({ me, onMe, onToast }: {
  me: Me
  onMe: (me: Me) => void
  onToast: (m: string, tone?: 'ok' | 'bad') => void
}) {
  const [setup, setSetup] = useState<TotpSetup | null>(null)
  const [code, setCode] = useState('')
  const [password, setPassword] = useState('')
  const [codes, setCodes] = useState<string[] | null>(null)
  const [busy, setBusy] = useState(false)

  async function begin() {
    setBusy(true)
    try {
      setSetup(await api.totpSetup())
    } catch (err) {
      onToast(err instanceof ApiError ? err.message : tr('Einrichtung fehlgeschlagen'), 'bad')
    } finally {
      setBusy(false)
    }
  }

  async function activate() {
    if (!setup) return
    setBusy(true)
    try {
      const result = await api.totpActivate(setup.secret, code)
      setCodes(result.codes)
      setSetup(null); setCode('')
      onMe(await api.me())
    } catch (err) {
      onToast(err instanceof ApiError ? err.message : tr('Einrichtung fehlgeschlagen'), 'bad')
    } finally {
      setBusy(false)
    }
  }

  async function disable() {
    setBusy(true)
    try {
      await api.totpDisable(password, code)
      setPassword(''); setCode('')
      onMe(await api.me())
      onToast(tr('Zwei-Faktor abgeschaltet.'))
    } catch (err) {
      onToast(err instanceof ApiError ? err.message : tr('Abschalten fehlgeschlagen'), 'bad')
    } finally {
      setBusy(false)
    }
  }

  async function renew() {
    setBusy(true)
    try {
      setCodes((await api.totpRenewCodes(password)).codes)
      setPassword('')
      onMe(await api.me())
    } catch (err) {
      onToast(err instanceof ApiError ? err.message : tr('Erneuern fehlgeschlagen'), 'bad')
    } finally {
      setBusy(false)
    }
  }

  /* Die Codes erscheinen genau einmal. Danach liegen sie nur noch gehasht auf
     dem Server — wie Passwörter. Deshalb steht das auch dabei. */
  if (codes) {
    return (
      <div style={{ maxWidth: 560 }}>
        <div className="note-warn" style={{ marginBottom: 16 }}>
          {tr('Diese Codes siehst du nur jetzt. Drucke sie aus oder leg sie in deinen Passwortspeicher — mit ihnen kommst du herein, wenn dein Telefon weg ist. Jeder gilt einmal.')}
        </div>
        <pre className="build__log" style={{ maxHeight: 'none' }}>{codes.join('\n')}</pre>
        <div className="viewer__row" style={{ marginTop: 14 }}>
          <button className="btn" onClick={() => {
            void navigator.clipboard?.writeText(codes.join('\n'))
              .then(() => onToast(tr('Codes in die Zwischenablage kopiert.')))
              .catch(() => onToast(tr('Der Browser gibt die Zwischenablage nicht frei.'), 'bad'))
          }}>{tr('Kopieren')}</button>
          <button className="btn btn--primary" onClick={() => setCodes(null)}>
            {tr('Ich habe sie gesichert')}
          </button>
        </div>
      </div>
    )
  }

  if (setup) {
    return (
      <div style={{ maxWidth: 560 }}>
        <p className="sub" style={{ marginBottom: 16 }}>
          {tr('Scanne den Code mit deiner Authenticator-App und tippe danach die sechs Ziffern ein, die sie zeigt.')}
        </p>
        {/* Der Code kommt vom Server als SVG. Er enthält nur das Geheimnis
            dieses Kontos und keine fremden Inhalte. */}
        <div className="totp__qr" dangerouslySetInnerHTML={{ __html: setup.qr_svg }} />
        <Field label={tr('Geht das Scannen nicht?')}
          hint={tr('Dann trage dieses Geheimnis von Hand in der App ein.')}>
          <pre className="build__log" style={{ maxHeight: 'none' }}>{setup.secret}</pre>
        </Field>
        <Field label={tr('Code aus deiner App')}>
          <div className="row-item" style={{ maxWidth: 220 }}>
            <input value={code} inputMode="numeric" maxLength={6} autoFocus
              aria-label={tr('Code aus deiner App')}
              onChange={(e) => setCode(e.target.value)} />
          </div>
        </Field>
        <div className="viewer__row">
          <button className="btn btn--primary" disabled={busy || code.length < 6}
            onClick={() => void activate()}>{tr('Einschalten')}</button>
          <button className="btn btn--ghost" onClick={() => setSetup(null)}>{tr('Abbrechen')}</button>
        </div>
      </div>
    )
  }

  if (!me.totp_enabled) {
    return (
      <div style={{ maxWidth: 560 }}>
        <p className="sub" style={{ marginBottom: 16 }}>
          {tr('Mit dem zweiten Faktor reicht dein Passwort allein nicht mehr aus. Du brauchst dafür eine Authenticator-App auf dem Telefon.')}
        </p>
        <button className="btn btn--primary" disabled={busy} onClick={() => void begin()}>
          {busy ? tr('Wird vorbereitet…') : tr('Zwei-Faktor einrichten')}
        </button>
      </div>
    )
  }

  return (
    <div style={{ maxWidth: 560 }}>
      <p className="sub" style={{ marginBottom: 6 }}>
        <b style={{ color: 'var(--live)' }}>{tr('Zwei-Faktor ist eingeschaltet.')}</b>
      </p>
      <p className="field__hint" style={{ marginBottom: 20 }}>
        {me.recovery_left > 2
          ? tr('{n} Rückfallcodes übrig.', { n: me.recovery_left })
          : tr('Nur noch {n} Rückfallcodes übrig — erneuere sie.', { n: me.recovery_left })}
      </p>

      <Field label={tr('Passwort')} hint={tr('Für beide Handlungen unten.')}>
        <div className="row-item" style={{ maxWidth: 320 }}>
          <input type="password" value={password} autoComplete="current-password"
            aria-label={tr('Passwort')} onChange={(e) => setPassword(e.target.value)} />
        </div>
      </Field>

      <Field label={tr('Neue Rückfallcodes')}
        hint={tr('Die bisherigen gelten danach nicht mehr.')}>
        <button className="btn" disabled={busy || !password} onClick={() => void renew()}>
          {tr('Codes erneuern')}
        </button>
      </Field>

      <Field label={tr('Zwei-Faktor abschalten')}
        hint={tr('Verlangt zusätzlich einen gültigen Code — wer nur dein Passwort hat, soll ihn nicht entfernen können.')}>
        <div className="row-item" style={{ maxWidth: 220, marginBottom: 10 }}>
          <input value={code} inputMode="text" placeholder={tr('Code')}
            aria-label={tr('Code aus deiner App')}
            onChange={(e) => setCode(e.target.value)} />
        </div>
        <button className="btn btn--halt" disabled={busy || !password || !code}
          onClick={() => void disable()}>{tr('Abschalten')}</button>
      </Field>
    </div>
  )
}

// ---------------------------------------------------------------- Sprache

function LanguagePart({ onMe, onToast }: {
  onMe: (me: Me) => void
  onToast: (m: string, tone?: 'ok' | 'bad') => void
}) {
  const current = useLang()

  /* Der Umschalter in der Leiste wirkt sofort und liegt im Browser. Hier
     landet die Wahl zusätzlich am Konto, damit sie an einem anderen Rechner
     wieder gilt. */
  useEffect(() => { /* nur zum Neuzeichnen */ }, [current])

  async function choose(lang: Lang) {
    setLang(lang)
    try {
      onMe(await api.setLocale(lang))
      onToast(tr('Sprache gemerkt.'))
    } catch (err) {
      onToast(err instanceof ApiError ? err.message : tr('Speichern fehlgeschlagen'), 'bad')
    }
  }

  return (
    <div style={{ maxWidth: 460 }}>
      <Field label={tr('Sprache')}
        hint={tr('Gilt sofort und wird am Konto gemerkt — an einem anderen Rechner musst du sie nicht erneut suchen.')}>
        <Segmented label={tr('Sprache')} value={getLang()}
          options={[
            { value: 'de' as Lang, label: 'Deutsch' },
            { value: 'en' as Lang, label: 'English' },
          ]}
          onChange={(v) => void choose(v)} />
      </Field>

      <p className="note-info">
        {tr('Die Auflösung deiner Anwendungen musst du nicht einstellen: Der ferne Bildschirm folgt der Grösse deines Browserfensters.')}
      </p>
    </div>
  )
}
