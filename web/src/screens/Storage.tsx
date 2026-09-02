import { useCallback, useEffect, useRef, useState } from 'react'
import { ApiError, api, type GroupDrive, type SharedListing } from '../lib/api'
import { ago } from '../lib/format'
import { t as tr, useLang } from '../lib/i18n'

/**
 * Eine Ablage — es gibt drei, und dieselbe Ansicht zeigt alle.
 *
 * * **Gemeinsam** gehört der Verwaltung. Sie liegt in jedem Arbeitsplatz
 *   unter `/mnt/ota` und als „Gemeinsam" im Home, dort **nur lesbar**: der
 *   Weg der Administration zu den Nutzern, nicht umgekehrt.
 * * **Eigen** gehört einem Menschen. Sie liegt in seinem Arbeitsplatz unter
 *   `/mnt/austausch` und als „Austausch" im Home, **beschreibbar** — der
 *   schnelle Weg in den Container hinein und wieder heraus.
 * * Ein **Gruppenlaufwerk** gehört einer Gruppe: dieselben Dateien für alle
 *   Mitglieder, unter `/mnt/gruppen/<name>` und als „Gruppen" im Home,
 *   ebenfalls beschreibbar. Sie erscheinen als Umschaltung neben der eigenen
 *   Ablage — und nur, wenn es überhaupt eine gibt.
 *
 * Getrennt sind sie, weil sie verschiedene Fragen beantworten. Zusammen in
 * einer Ansicht sind sie, weil die Handgriffe dieselben sind: ziehen,
 * ablegen, herunterladen, löschen.
 *
 * Ziehen und Ablegen als Hauptweg, ein Knopf daneben. Das Ziehen ist bequemer,
 * aber es ist unsichtbar: Wer nicht weiss, dass es geht, findet es nie.
 * Deshalb beides.
 */
export type Shelf = 'gemeinsam' | 'eigen'

export function Storage({ onToast, canWrite, shelf = 'gemeinsam' }: {
  onToast: (m: string, tone?: 'ok' | 'bad') => void
  canWrite: boolean
  shelf?: Shelf
}) {
  const eigen = shelf === 'eigen'
  useLang()
  // '' heisst: die eigene Ablage (oder die gemeinsame, je nach `shelf`).
  // Sonst die Kennung eines Gruppenlaufwerks.
  const [laufwerk, setLaufwerk] = useState('')
  const [gruppen, setGruppen] = useState<GroupDrive[]>([])
  const gruppe = gruppen.find((g) => g.id === laufwerk)

  const holen = laufwerk
    ? (p: string) => api.groupList(laufwerk, p)
    : eigen ? api.filesList : api.sharedList
  const legen = laufwerk
    ? (p: string, f: File) => api.groupUpload(laufwerk, p, f)
    : eigen ? api.filesUpload : api.sharedUpload
  const ordnen = laufwerk
    ? (p: string, n: string) => api.groupMkdir(laufwerk, p, n)
    : eigen ? api.filesMkdir : api.sharedMkdir
  const werfen = laufwerk
    ? (p: string) => api.groupRemove(laufwerk, p)
    : eigen ? api.filesRemove : api.sharedRemove
  const quelle = laufwerk
    ? `/api/groupfiles/${laufwerk}/file`
    : eigen ? '/api/files/file' : '/api/shared/file'

  const [data, setData] = useState<SharedListing | null>(null)
  const [path, setPath] = useState('')
  const [over, setOver] = useState(false)
  const [busy, setBusy] = useState<string | null>(null)
  const [failed, setFailed] = useState<string | null>(null)
  const picker = useRef<HTMLInputElement>(null)

  const load = useCallback(async (where: string) => {
    try {
      setData(await holen(where))
      setFailed(null)
    } catch (err) {
      setFailed(err instanceof ApiError ? err.message : tr('Laden fehlgeschlagen'))
    }
  }, [holen])

  useEffect(() => { void load(path) }, [load, path])

  useEffect(() => {
    // Nur in der eigenen Ansicht. Die gemeinsame Ablage ist die der
    // Verwaltung; Gruppenlaufwerke gehören dort nicht dazwischen.
    if (!eigen) return
    api.myGroupDrives().then(setGruppen).catch(() => setGruppen([]))
  }, [eigen])

  async function upload(files: FileList | File[]) {
    const list = Array.from(files)
    if (list.length === 0) return
    for (const file of list) {
      setBusy(file.name)
      try {
        await legen(path, file)
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
      await ordnen(path, name)
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
      await werfen(full)
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
          <p className="silk" style={{ marginBottom: 6 }}>
            {gruppe ? tr('Gemeinsam im Team')
              : eigen ? tr('Deine Dateien') : tr('Verwaltung')}
          </p>
          <h1 className="h-page">
            {gruppe ? gruppe.name
              : eigen ? tr('Meine Ablage') : tr('Gemeinsame Ablage')}
          </h1>
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

      {gruppen.length > 0 && (
        <div className="chips" style={{ marginBottom: 14 }}>
          <button type="button" className={`chip${laufwerk === '' ? ' is-on' : ''}`}
            aria-pressed={laufwerk === ''}
            onClick={() => { setLaufwerk(''); setPath('') }}>
            {tr('Meine Ablage')}
          </button>
          {gruppen.map((g) => (
            <button key={g.id} type="button"
              className={`chip${laufwerk === g.id ? ' is-on' : ''}`}
              aria-pressed={laufwerk === g.id}
              onClick={() => { setLaufwerk(g.id); setPath('') }}>
              {g.name}
            </button>
          ))}
        </div>
      )}

      <p className="sub" style={{ marginBottom: 18 }}>
        {gruppe
          ? tr('Dieselben Dateien für alle Mitglieder von „{name}". Im Arbeitsplatz unter /mnt/gruppen/{name} und als „Gruppen" im Home — beschreibbar. Wer die Gruppe verlässt, sieht sie beim nächsten Sessionstart nicht mehr.', { name: gruppe.name })
          : eigen
          ? tr('Liegt in deinem Arbeitsplatz unter /mnt/austausch und als „Austausch" im Home — beschreibbar. Was du hier ablegst, liegt gleich darauf im Container; was du dort hineinlegst, findest du hier.')
          : tr('Liegt in jedem Arbeitsplatz unter /mnt/ota und als „Gemeinsam" im Home — dort nur lesbar. Geschrieben wird ausschliesslich hier.')}
      </p>

      {/* Pfad als Weg zurück, wie im Workspace-Editor. */}
      <nav className="wb__crumb" style={{ marginBottom: 14 }} aria-label={tr('Pfad')}>
        <button type="button" className="wb__up" onClick={() => setPath('')}>
          {gruppe ? gruppe.name : eigen ? tr('Meine Ablage') : tr('Gemeinsame Ablage')}
        </button>
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
            {gruppe
              ? tr('Was hier liegt, sehen alle Mitglieder. Zieh Dateien in die Fläche oben oder leg einen Ordner an.')
              : canWrite
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
                        href={`${quelle}?path=${encodeURIComponent(path ? `${path}/${e.name}` : e.name)}`}
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
        {eigen
          ? tr('Belegt insgesamt {size}. Das hier sieht ausser dir niemand — auch die Administration nicht.',
              { size: size(data.total_bytes) })
          : tr('Belegt insgesamt {size}. Was hier liegt, sieht jeder Nutzer in jedem Arbeitsplatz — es ist kein Ort für Vertrauliches.',
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
