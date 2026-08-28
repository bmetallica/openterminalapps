import { useCallback, useEffect, useState } from 'react'
import { Field, Toggle } from '../components/controls'
import { ApiError, api, type Group, type WebApp, type WebAppIn } from '../lib/api'
import { t as tr, useLang } from '../lib/i18n'

/**
 * Fremde Web-Anwendungen im Katalog (auth-roadmap.md, Etappe D).
 *
 * OTA betreibt sie nicht. Es entscheidet, wer sie sieht, und hat in Keycloak
 * den OIDC-Client dafür angelegt. Was jemand *innerhalb* der Anwendung darf,
 * entscheidet die Anwendung — OTA baut ihr Rechtemodell nicht nach.
 *
 * Der Bildschirm sagt an zwei Stellen deutlich, worum es geht: Die
 * Redirect-Adresse bestimmt, **wohin die Identität der Nutzer fliesst**, und
 * das Geheimnis kommt genau einmal — danach steht es nur noch in Keycloak.
 */
const LEER: WebAppIn = {
  name: '', description: '', icon: '◇', url: '', redirect_uri: '',
  is_enabled: true, sort_order: 0, group_ids: [],
}

export function WebApps({ onToast }: { onToast: (m: string, tone?: 'ok' | 'bad') => void }) {
  useLang()
  const [liste, setListe] = useState<WebApp[] | null>(null)
  const [gruppen, setGruppen] = useState<Group[]>([])
  const [offen, setOffen] = useState<string | null>(null)
  const [entwurf, setEntwurf] = useState<WebAppIn>(LEER)
  const [geheimnis, setGeheimnis] = useState<{ fuer: string; wert: string } | null>(null)

  const laden = useCallback(async () => {
    const [a, g] = await Promise.all([api.webApps(), api.groups().catch(() => [])])
    setListe(a)
    setGruppen(g)
  }, [])

  useEffect(() => { void laden() }, [laden])

  function bearbeiten(a: WebApp | null) {
    setGeheimnis(null)
    setOffen(a ? a.id : 'neu')
    setEntwurf(a ? {
      name: a.name, description: a.description, icon: a.icon, url: a.url,
      redirect_uri: a.redirect_uri, is_enabled: a.is_enabled,
      sort_order: a.sort_order, group_ids: a.group_ids,
    } : LEER)
  }

  async function sichern() {
    try {
      if (offen === 'neu') {
        const neu = await api.addWebApp(entwurf)
        if (neu.client_secret) setGeheimnis({ fuer: neu.name, wert: neu.client_secret })
      } else if (offen) {
        await api.saveWebApp(offen, entwurf)
      }
      setOffen(null)
      await laden()
      onToast(tr('Gespeichert.'))
    } catch (err) {
      onToast(err instanceof ApiError ? err.message : tr('Speichern fehlgeschlagen'), 'bad')
    }
  }

  const set = <K extends keyof WebAppIn>(k: K, v: WebAppIn[K]) =>
    setEntwurf((e) => ({ ...e, [k]: v }))

  if (liste === null) return <div className="wrap"><p className="sub">{tr('Wird geladen…')}</p></div>

  return (
    <div className="wrap">
      <header className="topbar">
        <div>
          <p className="silk" style={{ marginBottom: 6 }}>{tr('Verwaltung')}</p>
          <h1 className="h-page">{tr('Web-Anwendungen')}</h1>
        </div>
        {offen === null && (
          <button className="btn btn--primary" onClick={() => bearbeiten(null)}>
            {tr('Anwendung hinzufügen')}
          </button>
        )}
      </header>

      <p className="sub" style={{ marginBottom: 18 }}>
        {tr('Fremde Anwendungen, die dieselbe Anmeldung benutzen. OTA legt den Zugang in Keycloak an und entscheidet, wer die Kachel sieht — was jemand darin darf, entscheidet die Anwendung selbst.')}
      </p>

      {geheimnis && (
        <div className="note-warn" style={{ marginBottom: 18 }}>
          <p style={{ marginTop: 0 }}>
            <b>{tr('Das Geheimnis für {name} — es wird nur dieses eine Mal gezeigt.', { name: geheimnis.fuer })}</b>
          </p>
          <pre className="build__log" style={{ margin: 0, whiteSpace: 'pre-wrap' }}>{geheimnis.wert}</pre>
          <p style={{ marginBottom: 0 }}>
            {tr('Trag es jetzt in der Anwendung ein. Danach steht es nur noch in Keycloak; verloren heisst: ein neues erzeugen.')}
          </p>
        </div>
      )}

      {liste.length === 0 && offen === null && (
        <div className="empty">
          <p className="empty__title">{tr('Noch keine Anwendung')}</p>
          <p className="empty__body">
            {tr('Bevor die erste entstehen kann, muss unter Einstellungen stehen, wohin Anwendungen ihre Anmeldung schicken dürfen. Solange dort nichts steht, ist nichts erlaubt.')}
          </p>
        </div>
      )}

      {liste.map((a) => (
        <div key={a.id} className="panel" style={{ padding: 16, marginBottom: 12 }}>
          <div className="bay__title-row">
            <h3 className="h-card">
              <span aria-hidden="true" style={{ marginRight: 8 }}>{a.icon}</span>{a.name}
            </h3>
            <span className="silk data">{a.is_enabled ? tr('sichtbar') : tr('aus')}</span>
          </div>
          <p className="field__hint" style={{ marginTop: 4 }}>{a.url}</p>
          <p className="field__hint" style={{ marginTop: 2 }}>
            {tr('Anmeldung geht zurück an')} <code>{a.redirect_uri}</code>
          </p>
          <p className="field__hint" style={{ marginTop: 2 }}>
            {tr('Zugriff')}: {a.group_ids.length === 0
              ? tr('alle')
              : gruppen.filter((g) => a.group_ids.includes(g.id)).map((g) => g.name).join(', ')}
          </p>
          <div className="viewer__row" style={{ marginTop: 12 }}>
            <button className="btn btn--sm" onClick={() => bearbeiten(a)}>{tr('Bearbeiten')}</button>
            <button className="btn btn--sm" onClick={() => {
              if (!window.confirm(tr('Ein neues Geheimnis erzeugen? Das alte gilt danach nicht mehr, und die Anwendung meldet sich erst wieder an, wenn das neue dort eingetragen ist.'))) return
              void api.newWebAppSecret(a.id)
                .then((r) => setGeheimnis({ fuer: a.name, wert: r.client_secret }))
                .catch(() => onToast(tr('Hat nicht geklappt'), 'bad'))
            }}>{tr('Neues Geheimnis')}</button>
            <button className="btn btn--sm btn--halt" onClick={() => {
              if (!window.confirm(tr('„{name}" entfernen? Der Zugang in Keycloak geht mit.', { name: a.name }))) return
              void api.removeWebApp(a.id).then(() => laden())
                .catch(() => onToast(tr('Löschen fehlgeschlagen'), 'bad'))
            }}>{tr('Löschen')}</button>
          </div>
        </div>
      ))}

      {offen !== null && (
        <div className="panel" style={{ padding: 16 }}>
          <Field label={tr('Name')} hint={tr('So heisst die Kachel im Dashboard.')}>
            <div className="row-item">
              <input value={entwurf.name} onChange={(e) => set('name', e.target.value)} />
            </div>
          </Field>

          <Field label={tr('Symbol')} hint={tr('Ein Zeichen. Es steht auf der Kachel.')}>
            <div className="row-item" style={{ maxWidth: 120 }}>
              <input value={entwurf.icon} onChange={(e) => set('icon', e.target.value)} />
            </div>
          </Field>

          <Field label={tr('Beschreibung')}>
            <div className="row-item">
              <input value={entwurf.description} onChange={(e) => set('description', e.target.value)} />
            </div>
          </Field>

          <Field label={tr('Adresse der Anwendung')} hint={tr('Wohin die Kachel führt.')}>
            <div className="row-item">
              <input value={entwurf.url} placeholder="https://ai.firma.de/"
                onChange={(e) => set('url', e.target.value)} />
            </div>
          </Field>

          <Field label={tr('Rückadresse der Anmeldung')}
            hint={tr('Dorthin schickt Keycloak nach der Anmeldung. Wer sie bestimmt, bestimmt, wohin die Identität der Nutzer fliesst — sie muss auf der Liste erlaubter Ziele stehen.')}>
            <div className="row-item">
              <input value={entwurf.redirect_uri} placeholder="https://ai.firma.de/oauth/oidc/callback"
                onChange={(e) => set('redirect_uri', e.target.value)} />
            </div>
          </Field>

          <Field label={tr('Zugriff')} hint={tr('Ohne Auswahl sehen alle die Kachel.')}>
            <div className="strip">
              {gruppen.map((g) => {
                const an = (entwurf.group_ids ?? []).includes(g.id)
                return (
                  <button key={g.id} type="button" className={`chip${an ? ' is-on' : ''}`}
                    onClick={() => set('group_ids', an
                      ? (entwurf.group_ids ?? []).filter((x) => x !== g.id)
                      : [...(entwurf.group_ids ?? []), g.id])}>
                    {g.name}
                  </button>
                )
              })}
            </div>
          </Field>

          <Field label={tr('Sichtbar')}>
            <Toggle on={entwurf.is_enabled} name={tr('Im Dashboard anzeigen')}
              onChange={(v) => set('is_enabled', v)} />
          </Field>

          <div className="viewer__row" style={{ marginTop: 12 }}>
            <button className="btn btn--primary" onClick={() => void sichern()}>{tr('Speichern')}</button>
            <button className="btn" onClick={() => setOffen(null)}>{tr('Abbrechen')}</button>
          </div>
        </div>
      )}
    </div>
  )
}
