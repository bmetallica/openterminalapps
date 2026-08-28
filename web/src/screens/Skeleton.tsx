import { useCallback, useEffect, useRef, useState } from 'react'
import { ApiError, api, type SkeletonEntry, type Template } from '../lib/api'
import { size } from '../lib/format'
import { t as tr, useLang } from '../lib/i18n'

/**
 * Womit ein Zuhause anfängt.
 *
 * Ein Verzeichnisbaum je Workspace, der beim **ersten** Start ins Home
 * kopiert wird. Einzelne Pfade lassen sich als *durchgesetzt* markieren — die
 * kommen bei jedem Start und überschreiben, was der Nutzer geändert hat.
 *
 * Dass das die Ausnahme ist und nicht die Regel, steht auch so in der
 * Oberfläche: Ein Zuhause gehört dem Menschen, der darin arbeitet. Für ein
 * Wurzelzertifikat ist Überschreiben richtig, für ein Farbschema nicht.
 */
export function Skeleton({ tpl, enforce, onEnforce, onToast }: {
  tpl: Template
  enforce: string[]
  onEnforce: (v: string[]) => void
  onToast: (m: string, tone?: 'ok' | 'bad') => void
}) {
  useLang()
  const [path, setPath] = useState('')
  const [entries, setEntries] = useState<SkeletonEntry[] | null>(null)
  const [busy, setBusy] = useState(false)
  const [drag, setDrag] = useState(false)
  const fileInput = useRef<HTMLInputElement>(null)

  const load = useCallback(async (p: string) => {
    try {
      const data = await api.skeletonList(tpl.id, p)
      setEntries(data.eintraege)
      setPath(data.pfad)
    } catch (err) {
      onToast(err instanceof ApiError ? err.message : tr('Laden fehlgeschlagen'), 'bad')
    }
  }, [tpl.id, onToast])

  useEffect(() => { void load('') }, [load])

  async function upload(files: FileList | null) {
    if (!files?.length) return
    setBusy(true)
    try {
      for (const f of Array.from(files)) await api.skeletonUpload(tpl.id, path, f)
      await load(path)
      onToast(tr('{n} Datei(en) abgelegt.', { n: String(files.length) }))
    } catch (err) {
      onToast(err instanceof ApiError ? err.message : tr('Hochladen fehlgeschlagen'), 'bad')
    } finally {
      setBusy(false)
    }
  }

  async function mkdir() {
    const name = window.prompt(tr('Name des Verzeichnisses'))
    if (!name) return
    setBusy(true)
    try {
      await api.skeletonMkdir(tpl.id, path, name)
      await load(path)
    } catch (err) {
      onToast(err instanceof ApiError ? err.message : tr('Anlegen fehlgeschlagen'), 'bad')
    } finally {
      setBusy(false)
    }
  }

  async function remove(entry: SkeletonEntry) {
    setBusy(true)
    try {
      const res = await api.skeletonRemove(tpl.id, entry.pfad)
      onEnforce(enforce.filter((p) => p !== entry.pfad && !p.startsWith(entry.pfad + '/')))
      await load(path)
      onToast(res.status)
    } catch (err) {
      onToast(err instanceof ApiError ? err.message : tr('Löschen fehlgeschlagen'), 'bad')
    } finally {
      setBusy(false)
    }
  }

  const up = path ? path.split('/').slice(0, -1).join('/') : null

  return (
    <>
      <p className="sub" style={{ marginBottom: 14 }}>
        {tr('Was hier liegt, kommt beim ersten Start in das Zuhause eines Nutzers — solange es noch leer ist. Danach gehört das Zuhause ihm. Punktdateien sind erlaubt und der Normalfall.')}
      </p>

      <div className="viewer__row" style={{ marginBottom: 12 }}>
        <button className="btn btn--sm" disabled={busy}
          onClick={() => fileInput.current?.click()}>{tr('Dateien ablegen')}</button>
        <button className="btn btn--sm btn--ghost" disabled={busy}
          onClick={() => void mkdir()}>{tr('Verzeichnis anlegen')}</button>
        <input ref={fileInput} type="file" multiple hidden
          aria-label={tr('Dateien ablegen')}
          onChange={(e) => void upload(e.target.files)} />
        <span className="sub" style={{ marginLeft: 'auto' }}>
          {tr('Pfad:')} <span className="data">~/{path}</span>
        </span>
      </div>

      <div className={`dropzone${drag ? ' is-over' : ''}`}
        onDragOver={(e) => { e.preventDefault(); setDrag(true) }}
        onDragLeave={() => setDrag(false)}
        onDrop={(e) => { e.preventDefault(); setDrag(false); void upload(e.dataTransfer.files) }}>

        {up !== null && (
          <button className="filerow filerow--up" onClick={() => void load(up)}>
            <span className="filerow__icon">▲</span>
            <span className="filerow__name">{tr('eine Ebene höher')}</span>
          </button>
        )}

        {entries === null ? (
          <p className="sub">{tr('Wird geladen…')}</p>
        ) : entries.length === 0 ? (
          <p className="sub" style={{ padding: '18px 4px' }}>
            {tr('Noch nichts hinterlegt. Dateien hierher ziehen oder oben ablegen.')}
          </p>
        ) : entries.map((e) => {
          const on = enforce.includes(e.pfad)
          return (
            <div key={e.pfad} className="filerow">
              <span className="filerow__icon">{e.verzeichnis ? '▣' : '▢'}</span>
              {e.verzeichnis ? (
                <button className="filerow__name filerow__link"
                  onClick={() => void load(e.pfad)}>{e.name}</button>
              ) : (
                <span className="filerow__name">{e.name}</span>
              )}
              <span className="filerow__size data">
                {size(e.bytes)}
              </span>
              <button type="button"
                className={`chip chip--sm${on ? ' is-on' : ''}`}
                aria-pressed={on}
                title={tr('Bei jedem Start überschreiben')}
                onClick={() => onEnforce(on
                  ? enforce.filter((p) => p !== e.pfad)
                  : [...enforce, e.pfad])}>
                {tr('durchsetzen')}
              </button>
              <button className="btn btn--sm btn--halt" disabled={busy}
                onClick={() => void remove(e)}>{tr('Löschen')}</button>
            </div>
          )
        })}
      </div>

      {enforce.length > 0 && (
        <p className="note-warn" style={{ marginTop: 14 }}>
          <b>{tr('{n} Pfad(e) werden bei jedem Start überschrieben:', { n: String(enforce.length) })}</b>{' '}
          <span className="data">{enforce.join(', ')}</span>{' '}
          {tr('Was der Nutzer dort ändert, ist beim nächsten Start weg. Für ein Wurzelzertifikat richtig, für Einstellungen selten.')}
        </p>
      )}

      <p className="note-info" style={{ marginTop: 14 }}>
        {tr('Änderungen an „durchsetzen“ gelten erst nach dem Speichern. Die Dateien selbst sind sofort abgelegt.')}
      </p>
    </>
  )
}
