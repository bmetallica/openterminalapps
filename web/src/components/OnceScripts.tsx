import { useCallback, useEffect, useState } from 'react'
import { ApiError, api, type OnceScript } from '../lib/api'
import { ago } from '../lib/format'
import { t as tr } from '../lib/i18n'

/**
 * Einmal-Skripte eines Workspace.
 *
 * Der Fall, für den es sie gibt: Ein neues Golden Image bringt eine Anwendung
 * in einer neuen Fassung mit, und die braucht eine Änderung im Zuhause — eine
 * umgezogene Einstellungsdatei, ein neuer Pfad. Das Skeleton greift nicht
 * mehr, denn das Zuhause ist längst nicht mehr leer. Das Startskript greift,
 * liefe aber bei jedem Start wieder, obwohl die Sache nach dem ersten Mal
 * erledigt ist.
 *
 * Gebucht wird je Nutzer und Skript. Ein neues Skript ist ein neuer Eintrag
 * und läuft wieder für alle — genau so ist es gemeint.
 *
 * Was hier **nicht** passiert: ausführen. Ein Einmal-Skript läuft im
 * Container, und der läuft vielleicht gerade gar nicht. „Nochmal" nimmt
 * deshalb nur die Notiz zurück; nachgeholt wird es beim nächsten Start.
 */
export function OnceScripts({ templateId, onToast }: {
  templateId: string
  onToast: (m: string, tone?: 'ok' | 'bad') => void
}) {
  const [liste, setListe] = useState<OnceScript[] | null>(null)
  const [offen, setOffen] = useState<string | null>(null)
  const [name, setName] = useState('')
  const [body, setBody] = useState('')

  const laden = useCallback(async () => {
    try {
      setListe(await api.onceScripts(templateId))
    } catch {
      setListe([])
    }
  }, [templateId])

  useEffect(() => { void laden() }, [laden])

  function bearbeiten(s: OnceScript | null) {
    setOffen(s ? s.id : 'neu')
    setName(s?.name ?? '')
    setBody(s?.body ?? '')
  }

  async function sichern() {
    if (!name.trim()) { onToast(tr('Ohne Namen findet es später niemand wieder.'), 'bad'); return }
    const daten = { name: name.trim(), body, is_enabled: true, sort_order: 0 }
    try {
      if (offen === 'neu') await api.addOnceScript(templateId, daten)
      else if (offen) await api.saveOnceScript(templateId, offen, daten)
      setOffen(null)
      await laden()
      onToast(tr('Gespeichert. Es läuft beim nächsten Start jedes Nutzers, der es noch nicht hatte.'))
    } catch (err) {
      onToast(err instanceof ApiError ? err.message : tr('Speichern fehlgeschlagen'), 'bad')
    }
  }

  if (liste === null) return <p className="sub">{tr('Wird geladen…')}</p>

  return (
    <>
      <p className="sub" style={{ marginBottom: 16 }}>
        {tr('Läuft je Nutzer genau einmal, beim nächsten Start dieses Workspace — für Änderungen am Zuhause, die das Skeleton nicht mehr erreicht, weil dort schon etwas liegt.')}
      </p>

      {liste.length === 0 && offen === null && (
        <div className="empty">
          <p className="empty__title">{tr('Noch kein Einmal-Skript')}</p>
          <p className="empty__body">
            {tr('Typischer Fall: Ein Update braucht eine neue Einstellungsdatei im Home. Kopiere sie aus der gemeinsamen Ablage — $OTA_SHARED zeigt darauf.')}
          </p>
        </div>
      )}

      {liste.map((s) => (
        <div key={s.id} className="panel" style={{ padding: 16, marginBottom: 12 }}>
          <div className="bay__title-row">
            <h3 className="h-card">{s.name}</h3>
            <span className="silk data">
              {tr('{n}× gelaufen', { n: s.ran_count })}
              {s.failed.length > 0 && ` · ${tr('{n} gescheitert', { n: s.failed.length })}`}
            </span>
          </div>
          <p className="field__hint" style={{ marginTop: 4 }}>
            {tr('Angelegt {when}', { when: ago(new Date(s.created_at).getTime()) })}
          </p>

          {s.failed.length > 0 && (
            <div className="note-warn" style={{ marginTop: 10 }}>
              <p style={{ margin: '0 0 6px' }}>
                {tr('Bei {names} endete es mit einem Fehler.',
                  { names: s.failed.map((f) => f.username).join(', ') })}
              </p>
              <pre className="build__log" style={{ maxHeight: 140, margin: 0 }}>
                {s.failed[0].output || tr('(keine Ausgabe)')}
              </pre>
            </div>
          )}

          <div className="viewer__row" style={{ marginTop: 12 }}>
            <button className="btn btn--sm" onClick={() => bearbeiten(s)}>{tr('Bearbeiten')}</button>
            <button className="btn btn--sm" disabled={s.ran_count === 0} onClick={() => {
              if (!window.confirm(tr('„{name}" bei allen erneut laufen lassen? Es passiert beim nächsten Start, nicht sofort.', { name: s.name }))) return
              void api.runOnceAgain(templateId, s.id)
                .then((r) => { onToast(tr('Zurückgesetzt für {n} Nutzer.', { n: r.count })); return laden() })
                .catch(() => onToast(tr('Zurücksetzen fehlgeschlagen'), 'bad'))
            }}>{tr('Nochmal')}</button>
            <button className="btn btn--sm btn--halt" onClick={() => {
              if (!window.confirm(tr('„{name}" löschen? Die Buchführung geht mit.', { name: s.name }))) return
              void api.removeOnceScript(templateId, s.id)
                .then(() => laden())
                .catch(() => onToast(tr('Löschen fehlgeschlagen'), 'bad'))
            }}>{tr('Löschen')}</button>
          </div>
        </div>
      ))}

      {offen === null ? (
        <button className="btn btn--primary" onClick={() => bearbeiten(null)}>
          {tr('Einmal-Skript anlegen')}
        </button>
      ) : (
        <div className="panel" style={{ padding: 16 }}>
          <label className="field__label" htmlFor="once-name">{tr('Name')}</label>
          <input id="once-name" className="input" value={name}
            placeholder={tr('z. B. „VS Code 1.99 — settings.json umziehen"')}
            onChange={(e) => setName(e.target.value)} />

          <label className="field__label" htmlFor="once-body" style={{ marginTop: 12 }}>
            {tr('Skript')}
          </label>
          <textarea id="once-body" className="build__log" spellCheck={false}
            style={{ minHeight: 220, width: '100%', color: 'var(--text)', resize: 'vertical' }}
            value={body} onChange={(e) => setBody(e.target.value)}
            placeholder={'#!/usr/bin/env bash\n'
              + 'set -euo pipefail\n'
              + '# $OTA_SHARED  = gemeinsame Ablage,  $OTA_FILES = eigene Ablage\n'
              + 'mkdir -p "$HOME/.config/Code/User"\n'
              + 'cp "$OTA_SHARED/vscode/settings.json" "$HOME/.config/Code/User/settings.json"\n'} />

          <p className="note-info" style={{ marginTop: 10 }}>
            {tr('Läuft als Nutzer im Container, nicht als root — was dort entsteht, soll ihm gehören. Scheitert es, startet der Arbeitsplatz trotzdem, und es wird als gelaufen verbucht: Ein kaputtes Skript soll nicht bei jedem Start jedes Nutzers wieder anlaufen. Der Fehler steht dann hier.')}
          </p>

          <div className="viewer__row" style={{ marginTop: 12 }}>
            <button className="btn btn--primary" onClick={() => void sichern()}>{tr('Speichern')}</button>
            <button className="btn" onClick={() => setOffen(null)}>{tr('Abbrechen')}</button>
          </div>

          {offen !== 'neu' && (
            <p className="field__hint" style={{ marginTop: 10 }}>
              {tr('Eine Änderung am Text lässt es nicht erneut laufen. Wer es schon hatte, hat es gehabt — dafür ist „Nochmal" da.')}
            </p>
          )}
        </div>
      )}
    </>
  )
}
