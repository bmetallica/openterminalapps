import { useCallback, useEffect, useRef, useState } from 'react'
import { ApiError, api, type SharedListing } from '../lib/api'
import { ago } from '../lib/format'
import { t as tr, useLang } from '../lib/i18n'

/**
 * Die gemeinsame Ablage.
 *
 * Ein Ort für Dateien, die in jedem Arbeitsplatz gebraucht werden: ein
 * Firmenzertifikat, ein Installationspaket, eine Vorlagendatei. In den
 * Containern liegt sie **nur lesbar** unter `/mnt/ota` und als „Gemeinsam" im
 * Home — der Weg hinein führt ausschliesslich hier entlang.
 *
 * Ziehen und Ablegen als Hauptweg, ein Knopf daneben. Das Ziehen ist bequemer,
 * aber es ist unsichtbar: Wer nicht weiss, dass es geht, findet es nie.
 * Deshalb beides.
 */
export function Storage({ onToast, canWrite }: {
  onToast: (m: string, tone?: 'ok' | 'bad') => void
  canWrite: boolean
}) {
  useLang()
  const [data, setData] = useState<SharedListing | null>(null)
  const [path, setPath] = useState('')
  const [over, setOver] = useState(false)
  const [busy, setBusy] = useState<string | null>(null)
  const [failed, setFailed] = useState<string | null>(null)
  const picker = useRef<HTMLInputElement>(null)

  const load = useCallback(async (where: string) => {
    try {
      setData(await api.sharedList(where))
      setFailed(null)
    } catch (err) {
      setFailed(err instanceof ApiError ? err.message : tr('Laden fehlgeschlagen'))
    }
  }, [])

  useEffect(() => { void load(path) }, [load, path])

  async function upload(files: FileList | File[]) {
    const list = Array.from(files)
    if (list.length === 0) return
    for (const file of list) {
      setBusy(file.name)
      try {
        await api.sharedUpload(path, file)
      } catch (err) {
        onToast(err instanceof ApiError ? err.message
          : tr('{name} liess sich nicht ablegen.', { name: file.name }), 'bad')
      }
    }
    setBusy(null)
    onToast(tr('{n} Datei(en) abgelegt.', { n: list.length }))
    await load(path)
  }

  async function makeDir() {
    const name = window.prompt(tr('Name des Ordners'))
    if (!name) return
    try {
      await api.sharedMkdir(path, name)
      await load(path)
    } catch (err) {
      onToast(err instanceof ApiError ? err.message : tr('Anlegen fehlgeschlagen'), 'bad')
    }
  }

  async function remove(name: string, isDir: boolean) {
    const full = path ? `${path}/${name}` : name
    const question = isDir
      ? tr('Ordner „{name}" mit allem darin löschen?', { name })
      : tr('„{name}" löschen?', { name })
    if (!window.confirm(question)) return
    try {
      await api.sharedRemove(full)
      await load(path)
    } catch (err) {
      onToast(err instanceof ApiError ? err.message : tr('Löschen fehlgeschlagen'), 'bad')
    }
  }

  if (failed) {
    return (
      <div className="wrap"><div className="empty">
        <p className="empty__title">{tr('Konnte nicht geladen werden')}</p>
        <p className="empty__body">{failed}</p>
        <button className="btn" onClick={() => void load(path)}>{tr('Erneut versuchen')}</button>
      </div></div>
    )
  }
  if (!data) return <div className="wrap"><p className="sub">{tr('Wird geladen…')}</p></div>

  const parts = path ? path.split('/') : []

  return (
    <div className="wrap"
      onDragOver={(e) => { if (canWrite) { e.preventDefault(); setOver(true) } }}
      onDragLeave={() => setOver(false)}
      onDrop={(e) => {
        if (!canWrite) return
        e.preventDefault()
        setOver(false)
        void upload(e.dataTransfer.files)
      }}>

      <header className="topbar">
        <div>
          <p className="silk" style={{ marginBottom: 6 }}>{tr('Verwaltung')}</p>
          <h1 className="h-page">{tr('Ablage')}</h1>
        </div>
        {canWrite && (
          <div style={{ display: 'flex', gap: 10 }}>
            <button className="btn" onClick={() => void makeDir()}>{tr('Ordner anlegen')}</button>
            <button className="btn btn--primary" onClick={() => picker.current?.click()}>
              {tr('Dateien wählen')}
            </button>
            <input ref={picker} type="file" multiple hidden
              onChange={(e) => { void upload(e.target.files ?? []); e.target.value = '' }} />
          </div>
        )}
      </header>

      <p className="sub" style={{ marginBottom: 18 }}>
        {tr('Liegt in jedem Arbeitsplatz unter /mnt/ota und als „Gemeinsam" im Home — dort nur lesbar. Geschrieben wird ausschliesslich hier.')}
      </p>

      {/* Pfad als Weg zurück, wie im Workspace-Editor. */}
      <nav className="wb__crumb" style={{ marginBottom: 14 }} aria-label={tr('Pfad')}>
        <button type="button" className="wb__up" onClick={() => setPath('')}>{tr('Ablage')}</button>
        {parts.map((part, i) => (
          <span key={i} style={{ display: 'contents' }}>
            <span className="wb__sep" aria-hidden="true">/</span>
            {i === parts.length - 1
              ? <span className="wb__here">{part}</span>
              : <button type="button" className="wb__up"
                  onClick={() => setPath(parts.slice(0, i + 1).join('/'))}>{part}</button>}
          </span>
        ))}
      </nav>

      {canWrite && (
        <div className={`drop${over ? ' is-over' : ''}`}>
          {busy
            ? tr('{name} wird abgelegt…', { name: busy })
            : tr('Dateien hierher ziehen')}
        </div>
      )}

      {data.entries.length === 0 ? (
        <div className="empty">
          <p className="empty__title">{tr('Hier liegt nichts')}</p>
          <p className="empty__body">
            {canWrite
              ? tr('Zieh Dateien in die Fläche oben oder leg einen Ordner an.')
              : tr('Die Administration legt hier Dateien für alle Arbeitsplätze ab.')}
          </p>
        </div>
      ) : (
        <div className="panel" style={{ padding: '14px 0 0' }}>
          <table className="tbl">
            <thead>
              <tr>
                <th style={{ paddingLeft: 20 }}>{tr('Name')}</th>
                <th>{tr('Grösse')}</th>
                <th>{tr('Geändert')}</th>
                <th />
              </tr>
            </thead>
            <tbody>
              {data.entries.map((e) => (
                <tr key={e.name} style={{ cursor: e.is_dir ? 'pointer' : 'default' }}
                  onClick={() => e.is_dir && setPath(path ? `${path}/${e.name}` : e.name)}>
                  <td style={{ paddingLeft: 20 }}>
                    <span aria-hidden="true" style={{ marginRight: 10, color: 'var(--mute)' }}>
                      {e.is_dir ? '▦' : '▢'}
                    </span>
                    {e.name}
                  </td>
                  <td className="data" style={{ color: 'var(--label)' }}>
                    {e.is_dir ? '—' : size(e.size_bytes)}
                  </td>
                  <td className="data" style={{ color: 'var(--mute)', fontSize: 12 }}>
                    {ago(e.modified * 1000)}
                  </td>
                  <td style={{ textAlign: 'right', paddingRight: 20, whiteSpace: 'nowrap' }}>
                    {!e.is_dir && (
                      <a className="btn btn--sm btn--ghost" onClick={(ev) => ev.stopPropagation()}
                        href={`/api/shared/file?path=${encodeURIComponent(path ? `${path}/${e.name}` : e.name)}`}
                        download>{tr('Herunterladen')}</a>
                    )}
                    {canWrite && (
                      <button className="btn btn--sm btn--ghost" style={{ marginLeft: 6 }}
                        onClick={(ev) => { ev.stopPropagation(); void remove(e.name, e.is_dir) }}>
                        {tr('Löschen')}
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
        {tr('Belegt insgesamt {size}. Was hier liegt, sieht jeder Nutzer in jedem Arbeitsplatz — es ist kein Ort für Vertrauliches.',
          { size: size(data.total_bytes) })}
      </p>
    </div>
  )
}

function size(bytes: number): string {
  if (bytes >= 1024 ** 3) return `${(bytes / 1024 ** 3).toFixed(2).replace('.', ',')} GB`
  if (bytes >= 1024 ** 2) return `${(bytes / 1024 ** 2).toFixed(1).replace('.', ',')} MB`
  if (bytes >= 1024) return `${Math.round(bytes / 1024)} KB`
  return `${bytes} B`
}
