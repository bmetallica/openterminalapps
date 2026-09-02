import { useCallback, useEffect, useRef, useState } from 'react'
import { ApiError, api, type GroupDrive, type SharedListing } from '../lib/api'
import { t } from '../lib/i18n'

/**
 * Die Ablagen, klein genug für die Kontrollleiste.
 *
 * Der Grund, dass es sie hier gibt: Wer mitten in der Arbeit eine Datei
 * braucht, will nicht zurück ins Dashboard. Der Weg ist derselbe wie unter
 * „Meine Ablage" — was hier landet, liegt eine Sekunde später im Container
 * unter `/mnt/austausch` und als „Austausch" im Home.
 *
 * Oben lässt sich zwischen der eigenen Ablage und den Laufwerken der eigenen
 * Gruppen umschalten. Die Umschaltung erscheint nur, wenn es überhaupt eine
 * Gruppe gibt — ein Wähler mit einem einzigen Eintrag ist kein Wähler.
 *
 * Ziehen und Ablegen funktioniert **im Elternfenster**, nicht im Stream. Das
 * ist keine Einschränkung dieser Ansicht, sondern die Grenze des iframes: Ein
 * Ziehvorgang aus dem Betriebssystem endet dort, wo der ferne Desktop
 * anfängt. Die Leiste liegt davor und fängt ihn auf.
 */
export function ShelfPanel({ onToast }: {
  onToast: (m: string, tone?: 'ok' | 'bad') => void
}) {
  const [data, setData] = useState<SharedListing | null>(null)
  // '' heisst: die eigene Ablage. Sonst die Kennung eines Gruppenlaufwerks.
  const [laufwerk, setLaufwerk] = useState('')
  const [gruppen, setGruppen] = useState<GroupDrive[]>([])
  const [path, setPath] = useState('')
  const [over, setOver] = useState(false)
  const [busy, setBusy] = useState<string | null>(null)
  const picker = useRef<HTMLInputElement>(null)

  const load = useCallback(async (where: string) => {
    try {
      setData(laufwerk
        ? await api.groupList(laufwerk, where)
        : await api.filesList(where))
    } catch {
      setData(null)
    }
  }, [laufwerk])

  useEffect(() => { void load(path) }, [load, path])

  useEffect(() => {
    // Scheitert das, bleibt die Liste leer und die Umschaltung aus. Ein
    // Fehler wäre hier auch keine Hilfe: Wer keine Gruppe hat, soll nicht
    // erfahren, dass es Gruppen gibt.
    api.myGroupDrives().then(setGruppen).catch(() => setGruppen([]))
  }, [])

  async function upload(files: FileList | File[]) {
    const list = Array.from(files)
    if (list.length === 0) return
    for (const file of list) {
      setBusy(file.name)
      try {
        if (laufwerk) await api.groupUpload(laufwerk, path, file)
        else await api.filesUpload(path, file)
      } catch (err) {
        onToast(err instanceof ApiError ? err.message
          : t('{name} liess sich nicht ablegen.', { name: file.name }), 'bad')
      }
    }
    setBusy(null)
    onToast(t('{n} Datei(en) abgelegt.', { n: list.length }))
    await load(path)
  }

  const teile = path ? path.split('/') : []

  return (
    <div className="viewer__group"
      onDragOver={(e) => { e.preventDefault(); setOver(true) }}
      onDragLeave={() => setOver(false)}
      onDrop={(e) => { e.preventDefault(); setOver(false); void upload(e.dataTransfer.files) }}>

      <span className="silk">
        {laufwerk ? t('Gruppenlaufwerk') : t('Meine Ablage')}
      </span>

      {gruppen.length > 0 && (
        <div className="chips" style={{ marginTop: 6 }}>
          <button type="button" className={`chip chip--sm${laufwerk === '' ? ' is-on' : ''}`}
            aria-pressed={laufwerk === ''}
            onClick={() => { setLaufwerk(''); setPath('') }}>
            {t('Meine')}
          </button>
          {gruppen.map((g) => (
            <button key={g.id} type="button"
              className={`chip chip--sm${laufwerk === g.id ? ' is-on' : ''}`}
              aria-pressed={laufwerk === g.id}
              onClick={() => { setLaufwerk(g.id); setPath('') }}>
              {g.name}
            </button>
          ))}
        </div>
      )}

      <p className="field__hint" style={{ marginTop: 6 }}>
        {laufwerk
          ? t('Im Container unter /mnt/gruppen und als „Gruppen" im Home. Alle Mitglieder sehen dasselbe.')
          : t('Im Container unter /mnt/austausch und als „Austausch" im Home.')}
      </p>

      {teile.length > 0 && (
        <button className="btn btn--sm btn--ghost" style={{ marginTop: 8 }}
          onClick={() => setPath(teile.slice(0, -1).join('/'))}>
          ↑ {teile[teile.length - 1]}
        </button>
      )}

      <div className={`drop drop--sm${over ? ' is-over' : ''}`} style={{ marginTop: 8 }}>
        {busy ? t('{name} wird abgelegt…', { name: busy }) : t('Dateien hierher ziehen')}
      </div>

      <div className="shelf">
        {data === null ? (
          <p className="field__hint">{t('Wird geladen…')}</p>
        ) : data.entries.length === 0 ? (
          <p className="field__hint">{t('Hier liegt nichts')}</p>
        ) : data.entries.map((e) => {
          const full = path ? `${path}/${e.name}` : e.name
          return (
            <div key={e.name} className="shelf__row">
              {e.is_dir ? (
                <button className="shelf__name" onClick={() => setPath(full)}>
                  <span aria-hidden="true">▦</span> {e.name}
                </button>
              ) : (
                <a className="shelf__name" download
                  href={laufwerk
                    ? `/api/groupfiles/${laufwerk}/file?path=${encodeURIComponent(full)}`
                    : `/api/files/file?path=${encodeURIComponent(full)}`}>
                  <span aria-hidden="true">▢</span> {e.name}
                </a>
              )}
              <button className="shelf__drop" aria-label={t('{name} löschen', { name: e.name })}
                onClick={() => {
                  if (!window.confirm(t('„{name}" löschen?', { name: e.name }))) return
                  void (laufwerk ? api.groupRemove(laufwerk, full) : api.filesRemove(full))
                    .then(() => load(path))
                    .catch(() => onToast(t('Löschen fehlgeschlagen'), 'bad'))
                }}>✕</button>
            </div>
          )
        })}
      </div>

      <div className="viewer__row" style={{ marginTop: 8 }}>
        <button className="btn btn--sm" onClick={() => picker.current?.click()}>
          {t('Dateien wählen')}
        </button>
        <input ref={picker} type="file" multiple hidden
          onChange={(e) => { void upload(e.target.files ?? []); e.target.value = '' }} />
      </div>
    </div>
  )
}
