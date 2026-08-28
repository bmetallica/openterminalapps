import { useCallback, useEffect, useState } from 'react'
import { Dashboard } from './screens/Dashboard'
import { Login } from './screens/Login'
import { Monitor } from './screens/Monitor'
import { People } from './screens/People'
import { WebApps } from './screens/WebApps'
import { Workspaces } from './screens/Workspaces'
import { Help } from './screens/Help'
import { Settings } from './screens/Settings'
import { Images } from './screens/Images'
import { Storage } from './screens/Storage'
import { Account } from './screens/Account'
import { Registries } from './screens/Registries'
import { StandaloneViewer } from './screens/StandaloneViewer'
import { anmeldePfad, openInTab, parseRoute, viewPath, type Route } from './lib/routes'
import { ApiError, api, type Host, type Me, type Session, type Stream, type Template } from './lib/api'
import { gb } from './lib/format'
import { setLang, t, useLang, type Lang } from './lib/i18n'
import './styles/app.css'

type View = 'dashboard' | 'workspaces' | 'webapps' | 'images' | 'registries' | 'storage'
  | 'files' | 'people' | 'monitor' | 'settings' | 'account' | 'help'
type Toast = { id: number; msg: string; tone: 'ok' | 'bad' }

const NAV: { id: View; glyph: string; cap: string; adminOnly: boolean }[] = [
  { id: 'dashboard', glyph: '▣', cap: 'Start', adminOnly: false },
  { id: 'workspaces', glyph: '⬡', cap: 'Workspaces', adminOnly: true },
  // Fremde Web-Anwendungen. Eigener Punkt und nicht ein Reiter bei den
  // Workspaces: Das eine läuft hier, das andere woanders — und wer es
  // anlegt, bestimmt, wohin Identitäten fliessen (auth-roadmap.md §5d).
  { id: 'webapps', glyph: '◇', cap: 'Anwendungen', adminOnly: true },
  { id: 'images', glyph: '⬢', cap: 'Images', adminOnly: true },
  { id: 'registries', glyph: '◇', cap: 'Registries', adminOnly: true },
  // Zwei Ablagen, zwei Zwecke — deshalb zwei Einträge.
  //
  // Die eigene gehört jedem, auch Administratoren: Sie ist der Weg, Dateien
  // in den eigenen Container und wieder heraus zu bekommen. Die gemeinsame
  // ist der Weg der Verwaltung zu allen; wer sie nicht verwaltet, hat dort
  // nichts zu bestellen und sieht sie ohnehin in seinem Container.
  { id: 'files', glyph: '▤', cap: 'Meine Ablage', adminOnly: false },
  { id: 'storage', glyph: '▦', cap: 'Gemeinsame Ablage', adminOnly: true },
  { id: 'people', glyph: '◔', cap: 'Nutzer', adminOnly: true },
  { id: 'monitor', glyph: '◈', cap: 'Betrieb', adminOnly: true },
  { id: 'settings', glyph: '⚙', cap: 'Einstellungen', adminOnly: true },
  // Das Handbuch steht allen offen. Welche Kapitel jemand sieht, entscheidet
  // die API anhand der Rechte — Betriebs- und Verwaltungskapitel bleiben
  // Administratoren vorbehalten.
  { id: 'help', glyph: '?', cap: 'Hilfe', adminOnly: false },
]

/* Das eigene Konto sitzt unten bei „Abmelden", nicht oben bei den Ansichten:
   Es ist nichts, was man beim Arbeiten braucht, sondern etwas, das zur
   eigenen Person gehört. */

export default function App() {
  useLang()
  // Die Adresse wird einmal gelesen und dann festgehalten. Innerhalb der
  // Anwendung wird nicht navigiert — sie hat genau drei Einstiege, und alle
  // drei stehen beim Laden fest.
  const [route] = useState<Route>(() => parseRoute())
  const [me, setMe] = useState<Me | null>(null)
  const [checking, setChecking] = useState(true)
  const [view, setView] = useState<View>('dashboard')
  const [templates, setTemplates] = useState<Template[]>([])
  const [host, setHost] = useState<Host | null>(null)
  const [toasts, setToasts] = useState<Toast[]>([])

  const toast = useCallback((msg: string, tone: 'ok' | 'bad' = 'ok') => {
    const id = Date.now() + Math.random()
    setToasts((t) => [...t, { id, msg, tone }])
    setTimeout(() => setToasts((t) => t.filter((x) => x.id !== id)), tone === 'bad' ? 6000 : 2800)
  }, [])

  // Beim Laden prüfen, ob noch eine gültige Sitzung besteht.
  useEffect(() => {
    api.me().then(setMe).catch(() => setMe(null)).finally(() => setChecking(false))
  }, [])

  // Host-Auslastung nur für Admins — normale Nutzer bekommen dafür keine Rechte.
  useEffect(() => {
    if (!me?.is_admin) return
    const load = () => { api.host().then(setHost).catch(() => {}) }
    load()
    const timer = setInterval(load, 20_000)
    return () => clearInterval(timer)
  }, [me])

  // Für den App-Umschalter im Viewer wird der Katalog gebraucht.
  useEffect(() => {
    if (!me) return
    api.templates().then(setTemplates).catch(() => {})
  }, [me])

  /** Öffnet eine Session in einem eigenen Tab.
   *
   * Früher ersetzte die Ansicht das Dashboard. Das war unpraktisch, sobald
   * jemand mehr als eine Anwendung offen hat: Zurück zum Dashboard hiess, die
   * laufende Anwendung zu verlassen. Ein Tab je Anwendung entspricht dem, was
   * Leute von ihrem Desktop kennen — und der Weg zurück ist ein Klick auf den
   * ersten Tab.
   */
  function openSession(s: Session, stream?: Stream) {
    openInTab(viewPath(s.id, stream?.display_num))
  }

  async function logout() {
    await api.logout().catch(() => {})
    // Ausdrücklich auf die Anmeldeseite und nicht zurück in die
    // Weiterleitung: Wer sich gerade abgemeldet hat, will nicht im selben
    // Atemzug wieder angemeldet werden. Dort stehen beide Wege — die zentrale
    // Anmeldung und, solange es sie gibt, die lokale.
    //
    // Und **ohne** `setMe(null)` davor. Das war ein Wettlauf: Der leere
    // Zustand liess sofort neu zeichnen, die Weiterleitung zur zentralen
    // Anmeldung feuerte noch im selben Bild, und der Mensch war abgemeldet
    // und im selben Moment wieder angemeldet. Die Seite wird ohnehin
    // verlassen; den Zustand aufzuräumen ist dann niemandes Aufgabe mehr.
    window.location.href = '/login'
  }

  if (checking) {
    return (
      <div className="boot">
        <img className="boot__mark" src="/icon.svg" alt="" aria-hidden="true" />
        <span className="silk">{t('OpenTerminalApps startet…')}</span>
      </div>
    )
  }

  if (!me) {
    const fertig = (u: Me) => { setMe(u); toast(t('Willkommen, {name}', { name: u.username })) }

    // Der Notzugang. Eigene Adresse, damit ihn niemand versehentlich benutzt
    // — und damit er da ist, wenn Keycloak es nicht ist (auth-roadmap.md §5.2).
    if (route.kind === 'notfall') return <Login onDone={fertig} notfall />

    // `/login` ist der Landeplatz und **zugleich** die lokale Anmeldung.
    //
    // Beides in einem, weil es solange beides sein muss: Ohne Landeplatz
    // liefe der Browser bei einem Fehler in eine Schleife — weiterleiten,
    // scheitern, wieder weiterleiten. Und ohne lokale Maske käme bis zur
    // Übernahme der Bestandskonten (auth-roadmap.md §5.1) niemand mehr
    // herein, der noch nicht in Keycloak steht. Genau hier wäre der
    // Administrator ausgesperrt, der diesen Umbau macht.
    //
    // Mit der Übernahme fällt dieser Weg weg; übrig bleibt der Notzugang.
    if (route.kind === 'login') return <Login onDone={fertig} fehler={route.fehler} />

    // Der Normalfall: hinüber zu Keycloak. Die Adresse, auf der wir stehen,
    // geht mit — wer auf eine Desktop-Verknüpfung geklickt hat, landet danach
    // in seiner Anwendung und nicht im Dashboard.
    window.location.replace(anmeldePfad())
    return (
      <div className="boot">
        <img className="boot__mark" src="/icon.svg" alt="" aria-hidden="true" />
        <span className="silk">{t('Anmeldung wird geöffnet…')}</span>
      </div>
    )
  }

  // Angemeldet und auf einer Anmeldeadresse: Da gibt es nichts mehr zu tun.
  if (route.kind === 'login' || route.kind === 'notfall') {
    window.location.replace('/')
    return <div className="boot"><span className="silk">{t('Einen Moment…')}</span></div>
  }

  if (route.kind !== 'app') {
    return (
      <>
        <StandaloneViewer route={route} onToast={toast} />
        <Toasts items={toasts} />
      </>
    )
  }

  // Die gemeinsame Ablage hängt nicht am Administrator, sondern am Recht:
  // Wer Images oder Vorlagen verwaltet, verteilt auch, was hineingehört.
  const darfVerteilen = me.is_admin
    || me.permissions.includes('images.manage')
    || me.permissions.includes('templates.manage')
  const darfAnwendungen = me.is_admin || me.permissions.includes('anwendungen.verwalten')
  const visible = NAV.filter((n) =>
    n.id === 'storage' ? darfVerteilen
      : n.id === 'webapps' ? darfAnwendungen
        : !n.adminOnly || me.is_admin)

  /* Der Rückfall auf das Dashboard fängt den Fall ab, dass jemand seine
     Rechte verliert, während eine Verwaltungsansicht offen ist.
     `account` steht bewusst nicht in NAV — es ist keine Ansicht der Anlage,
     sondern die des eigenen Kontos — muss hier aber trotzdem gelten. Ohne
     diese Ausnahme sprang der Punkt „Mein Konto" wirkungslos zurück. */
  const outsideNav: View[] = ['account']
  const current = visible.some((n) => n.id === view) || outsideNav.includes(view)
    ? view : 'dashboard'
  const freePct = host ? (host.memory_available / host.memory_total) * 100 : null

  return (
    <div className="shell">
      <nav className="rail" aria-label={t('Hauptnavigation')}>
        {/* Das Symbol der Anwendung, nicht nachgezeichnet: Es bringt seine
            eigene Fläche mit, deshalb sitzt es ohne Hintergrund hier. */}
        <img className="rail__mark" src="/icon.svg" alt="" aria-hidden="true" />

        {visible.map((n) => (
          <button key={n.id} className={`rail__btn${current === n.id ? ' is-on' : ''}`}
            onClick={() => setView(n.id)} aria-current={current === n.id ? 'page' : undefined}>
            <span className="rail__glyph" aria-hidden="true">{n.glyph}</span>
            <span className="rail__cap">{t(n.cap)}</span>
          </button>
        ))}

        <div className="rail__spacer" />

        <button className={`rail__btn${current === 'account' ? ' is-on' : ''}`}
          onClick={() => setView('account')}
          aria-current={current === 'account' ? 'page' : undefined}>
          <span className="rail__glyph" aria-hidden="true">◔</span>
          <span className="rail__cap">{t('Mein Konto')}</span>
        </button>

        <LangSwitch />

        <button className="rail__btn" onClick={() => void logout()}
          title={t('Abmelden ({name})', { name: me.username })}>
          <span className="rail__glyph" aria-hidden="true">⇥</span>
          <span className="rail__cap">{t('Abmelden')}</span>
        </button>

        {freePct !== null && host && (
          <div className="rail__host" title={t('{free} GB von {total} GB frei',
            { free: gb(host.memory_available), total: gb(host.memory_total, 0) })}>
            <span className={`led ${freePct < 15 ? 'led--fail' : 'led--live'}`}>
              <span className="led__dot" aria-hidden="true" />
            </span>
            <b className="data">{Math.round(freePct)}%</b>
            <span className="silk" style={{ fontSize: 8 }}>{t('frei')}</span>
          </div>
        )}
      </nav>

      <main className="main">
        {me.must_change_password && (
          <PasswordGate onDone={() => setMe({ ...me, must_change_password: false })} onToast={toast} />
        )}
        {/* Kein Riegel vor der ganzen Oberfläche: Der Weg zur Einrichtung
            führt durch sie hindurch. Der Riegel sitzt beim Start einer
            Session, wo er auch serverseitig hält. */}
        {me.must_setup_totp && !me.must_change_password && (
          <div className="gate-note" role="status">
            <b>{t('Zweiter Faktor ist für deine Gruppe Pflicht.')}</b>
            <span>{t('Bis er eingerichtet ist, lässt sich kein Arbeitsplatz starten.')}</span>
            <button className="btn btn--sm btn--primary" onClick={() => setView('account')}>
              {t('Jetzt einrichten')}
            </button>
          </div>
        )}
        {current === 'dashboard' && (
          <Dashboard me={me} onOpen={openSession} onToast={toast} />
        )}
        {current === 'workspaces' && <Workspaces onToast={toast} />}
        {current === 'webapps' && <WebApps onToast={toast} />}
        {current === 'images' && <Images onToast={toast} />}
        {current === 'registries' && <Registries onToast={toast} />}
        {current === 'storage' && (
          <Storage onToast={toast}
            canWrite={me.is_admin || me.permissions.includes('images.manage')
              || me.permissions.includes('templates.manage')} />
        )}
        {current === 'files' && (
          <Storage onToast={toast} shelf="eigen" canWrite />
        )}
        {current === 'people' && <People onToast={toast} />}
        {current === 'monitor' && <Monitor onToast={toast} />}
        {current === 'settings' && <Settings onToast={toast} />}
        {current === 'account' && <Account me={me} onMe={setMe} onToast={toast} />}
        {current === 'help' && <Help onToast={toast} />}
      </main>

      <Toasts items={toasts} />
    </div>
  )
}

/** Sprachumschalter in der Leiste.
 *
 * Bewusst zwei sichtbare Schalter statt eines Klapp-Menüs: Bei genau zwei
 * Möglichkeiten ist die aktuelle Sprache damit auf einen Blick zu sehen, und
 * der Wechsel kostet einen Klick statt zwei.
 */
function LangSwitch() {
  const current = useLang()
  return (
    <div className="rail__lang" role="radiogroup" aria-label={t('Sprache')}>
      {(['de', 'en'] as Lang[]).map((l) => (
        <button key={l} type="button" role="radio" aria-checked={current === l}
          className={`rail__langopt${current === l ? ' is-on' : ''}`}
          title={l === 'de' ? 'Deutsch' : 'English'}
          onClick={() => setLang(l)}>
          {l.toUpperCase()}
        </button>
      ))}
    </div>
  )
}

function Toasts({ items }: { items: Toast[] }) {
  return (
    <div className="toasts" role="status" aria-live="polite">
      {items.map((t) => (
        <div key={t.id} className={`toast${t.tone === 'bad' ? ' toast--bad' : ''}`}>
          <span className={`led ${t.tone === 'bad' ? 'led--fail' : 'led--live'}`}>
            <span className="led__dot" aria-hidden="true" />
          </span>
          {t.msg}
        </div>
      ))}
    </div>
  )
}

/** Erzwungener Passwortwechsel nach dem ersten Login. */
function PasswordGate({ onDone, onToast }: {
  onDone: () => void
  onToast: (m: string, tone?: 'ok' | 'bad') => void
}) {
  const [current, setCurrent] = useState('')
  const [next, setNext] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)

  async function submit(e: React.FormEvent) {
    e.preventDefault()
    setBusy(true)
    setError(null)
    try {
      await api.changePassword(current, next)
      onToast(t('Passwort geändert'))
      onDone()
    } catch (err) {
      setError(err instanceof ApiError ? err.message : t('Wechsel fehlgeschlagen'))
    } finally {
      setBusy(false)
    }
  }

  return (
    <>
      <div className="scrim" />
      <form className="drawer" style={{ width: 'min(460px, 100vw)' }} onSubmit={submit}>
        <header className="drawer__head">
          <div>
            <h2 className="h-card">{t('Passwort ändern')}</h2>
            <p className="sub" style={{ marginTop: 4 }}>
              {t('Dein Konto wurde mit einem Einmal-Passwort angelegt. Bitte vergib ein eigenes.')}
            </p>
          </div>
        </header>
        <div className="drawer__body">
          <label className="field">
            <span className="field__label" style={{ display: 'block', marginBottom: 8 }}>{t('Aktuelles Passwort')}</span>
            <div className="row-item">
              <input type="password" value={current} required autoFocus
                onChange={(e) => setCurrent(e.target.value)} />
            </div>
          </label>
          <label className="field">
            <span className="field__label" style={{ display: 'block', marginBottom: 8 }}>{t('Neues Passwort')}</span>
            <div className="row-item">
              <input type="password" value={next} required
                onChange={(e) => setNext(e.target.value)} />
            </div>
            <p className="field__hint">{t('Mindestens 12 Zeichen.')}</p>
          </label>
          {error && <p className="login__error" role="alert">{error}</p>}
        </div>
        <footer className="drawer__foot">
          <button className="btn btn--primary" disabled={busy}>
            {busy ? t('Wird gespeichert…') : t('Passwort setzen')}
          </button>
        </footer>
      </form>
    </>
  )
}
