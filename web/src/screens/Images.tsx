import { useCallback, useEffect, useState } from 'react'
import { Segmented } from '../components/controls'
import { ApiError, api, type HostImage } from '../lib/api'
import { t as tr, useLang } from '../lib/i18n'

type Filter = 'OTA' | 'Kasm' | 'Übrige' | 'Alle'

const ORIGIN: Record<Filter, string | null> = {
  OTA: 'ota', Kasm: 'kasm', 'Übrige': 'fremd', Alle: null,
}

/**
 * Die Images auf diesem Host.
 *
 * Warum es diesen Bildschirm gibt: Die Auswahlliste beim Anlegen eines
 * Workspace zeigte einfach *alles*, was auf dem Docker-Host getaggt ist — auf
 * dieser Maschine 58 Einträge, von Elasticsearch bis busybox. Woher die Liste
 * kam, war nicht zu erkennen, und was fehlte, liess sich nicht ergänzen.
 *
 * Hier steht dieselbe Liste, aber sortiert nach Herkunft und mit dem, was
 * fehlte: Images holen, und welche wegräumen, die niemand mehr braucht.
 *
 * Was OTA **nicht** tut: fremde Images anfassen. Kasm teilt sich diesen Host,
 * und seine Images gehören ihm.
 */
export function Images({ onToast }: { onToast: (m: string, tone?: 'ok' | 'bad') => void }) {
  useLang()
  const [list, setList] = useState<HostImage[] | null>(null)
  const [filter, setFilter] = useState<Filter>('OTA')
  const [ref, setRef] = useState('')
  const [pulling, setPulling] = useState<{ detail: string } | null>(null)
  const [failed, setFailed] = useState<string | null>(null)

  const load = useCallback(async () => {
    try {
      setList(await api.images())
      setFailed(null)
    } catch (err) {
      setFailed(err instanceof ApiError ? err.message : tr('Laden fehlgeschlagen'))
    }
  }, [])

  useEffect(() => { void load() }, [load])

  /** Holt ein Image und verfolgt den Fortschritt.
   *
   * Ein Kasm-Image bringt ein bis drei Gigabyte mit. Ohne Rückmeldung sähe
   * das minutenlang nach „nichts passiert" aus, und beim zweiten Klick liefen
   * zwei Ladevorgänge.
   */
  async function pull() {
    const wanted = ref.trim()
    if (!wanted) return
    setPulling({ detail: tr('wird begonnen') })
    try {
      const job = await api.pullImage(wanted)
      let state = job
      while (state.status === 'running') {
        await new Promise((r) => setTimeout(r, 1200))
        state = await api.pullStatus(job.id)
        setPulling({ detail: state.detail })
      }
      if (state.status === 'ok') {
        onToast(tr('{ref} liegt jetzt auf diesem Host.', { ref: wanted }))
        setRef('')
        await load()
      } else {
        onToast(state.detail || tr('Das Image liess sich nicht holen.'), 'bad')
      }
    } catch (err) {
      onToast(err instanceof ApiError ? err.message : tr('Das Image liess sich nicht holen.'), 'bad')
    } finally {
      setPulling(null)
    }
  }

  async function remove(image: HostImage) {
    if (!window.confirm(tr('{ref} vom Host entfernen?', { ref: image.ref }))) return
    try {
      await api.removeImage(image.ref)
      onToast(tr('{ref} entfernt.', { ref: image.ref }))
      await load()
    } catch (err) {
      onToast(err instanceof ApiError ? err.message : tr('Löschen fehlgeschlagen'), 'bad')
    }
  }

  if (failed) {
    return (
      <div className="wrap"><div className="empty">
        <p className="empty__title">{tr('Konnte nicht geladen werden')}</p>
        <p className="empty__body">{failed}</p>
        <button className="btn" onClick={() => void load()}>{tr('Erneut versuchen')}</button>
      </div></div>
    )
  }
  if (!list) return <div className="wrap"><p className="sub">{tr('Wird geladen…')}</p></div>

  const want = ORIGIN[filter]
  const shown = want ? list.filter((i) => i.origin === want) : list
  const total = shown.reduce((a, i) => a + i.size_bytes, 0)

  return (
    <div className="wrap">
      <header className="topbar">
        <div>
          <p className="silk" style={{ marginBottom: 6 }}>{tr('Verwaltung')}</p>
          <h1 className="h-page">{tr('Images')}</h1>
        </div>
      </header>

      <div className="panel" style={{ padding: '18px 20px', marginBottom: 22 }}>
        <span className="field__label">{tr('Image holen')}</span>
        <p className="field__hint" style={{ marginTop: 4, marginBottom: 10 }}>
          {tr('Adresse wie bei docker pull. Danach steht es beim Anlegen eines Workspace zur Auswahl.')}
        </p>
        <div className="row-item">
          <input value={ref} spellCheck={false}
            placeholder="kasmweb/gimp:1.18.0-rolling-weekly"
            aria-label={tr('Image-Adresse')}
            disabled={!!pulling}
            onChange={(e) => setRef(e.target.value)}
            onKeyDown={(e) => { if (e.key === 'Enter') { e.preventDefault(); void pull() } }} />
          <button className="btn btn--primary" disabled={!!pulling || !ref.trim()}
            onClick={() => void pull()}>
            {pulling ? tr('Wird geholt…') : tr('Holen')}
          </button>
        </div>
        {pulling && (
          <p className="field__hint data" style={{ marginTop: 8 }}>{pulling.detail}</p>
        )}
      </div>

      <div className="section__head" style={{ marginBottom: 12 }}>
        <span className="silk">{tr('Auf diesem Host')}</span>
        <span className="section__rule" />
        <span className="silk data">
          {tr('{n} · {size} GB', { n: shown.length, size: (total / 1024 ** 3).toFixed(1) })}
        </span>
      </div>

      <div style={{ marginBottom: 16 }}>
        <Segmented label={tr('Herkunft')} value={filter}
          options={[
            { value: 'OTA' as Filter, label: tr('Von OTA gebaut') },
            { value: 'Kasm' as Filter, label: tr('Von Kasm') },
            { value: 'Übrige' as Filter, label: tr('Übrige') },
            { value: 'Alle' as Filter, label: tr('Alle') },
          ]}
          onChange={setFilter} />
      </div>

      {shown.length === 0 ? (
        <div className="empty">
          <p className="empty__title">{tr('Nichts in dieser Gruppe')}</p>
          <p className="empty__body">
            {filter === 'OTA'
              ? tr('Sobald du im Workspace-Editor unter Software ein Image baust, erscheint es hier.')
              : tr('Hole ein Image über das Feld oben.')}
          </p>
        </div>
      ) : (
        <div className="panel" style={{ padding: '14px 0 0' }}>
          <table className="tbl">
            <thead>
              <tr>
                <th style={{ paddingLeft: 20 }}>{tr('Image')}</th>
                <th>{tr('Herkunft')}</th>
                <th>{tr('Grösse')}</th>
                <th>{tr('Benutzt von')}</th>
                <th />
              </tr>
            </thead>
            <tbody>
              {shown.map((i) => (
                <tr key={i.ref} style={{ cursor: 'default' }}>
                  <td style={{ paddingLeft: 20 }} className="data">{i.ref}</td>
                  <td style={{ color: 'var(--label)', fontSize: 12.5 }}>
                    {tr(originLabel(i.origin))}
                  </td>
                  <td className="data" style={{ color: 'var(--label)' }}>
                    {(i.size_bytes / 1024 ** 3).toFixed(2)} GB
                  </td>
                  <td style={{ color: i.used_by.length ? 'var(--text)' : 'var(--mute)', fontSize: 12.5 }}>
                    {i.used_by.join(', ') || '—'}
                  </td>
                  <td style={{ textAlign: 'right', paddingRight: 20 }}>
                    {i.used_by.length === 0 && i.origin !== 'kasm' && (
                      <button className="btn btn--sm btn--ghost" onClick={() => void remove(i)}>
                        {tr('Entfernen')}
                      </button>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      <p className="field__hint" style={{ marginTop: 14 }}>
        {tr('Images von Kasm bleiben unangetastet — sie gehören dem anderen System auf diesem Host. Ein Image, das ein Workspace benutzt, lässt sich nicht entfernen.')}
      </p>
    </div>
  )
}

function originLabel(origin: string): string {
  return { ota: 'Von OTA gebaut', kasm: 'Von Kasm', fremd: 'Übrige' }[origin] ?? origin
}
