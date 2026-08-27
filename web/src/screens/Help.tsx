import { useEffect, useMemo, useRef, useState } from 'react'
import { ApiError, api, type HelpChapter, type HelpPage } from '../lib/api'
import { renderMarkdown } from '../lib/markdown'
import { t, useLang } from '../lib/i18n'

/**
 * Das Handbuch im Programm.
 *
 * Die Kapitel kommen aus `docs/wiki/`. Welche jemand sieht, entscheidet die
 * API anhand der Rechte — hier wird nichts ausgeblendet, was der Server
 * ausliefern würde.
 */
export function Help({ onToast }: { onToast: (m: string, tone?: 'ok' | 'bad') => void }) {
  const lang = useLang()
  const [chapters, setChapters] = useState<HelpChapter[] | null>(null)
  const [slug, setSlug] = useState<string | null>(null)
  const [page, setPage] = useState<HelpPage | null>(null)
  const [query, setQuery] = useState('')
  const [failed, setFailed] = useState<string | null>(null)
  const body = useRef<HTMLDivElement>(null)

  useEffect(() => {
    api.help()
      .then((c) => { setChapters(c); setSlug((s) => s ?? c[0]?.slug ?? null) })
      .catch((err) => setFailed(err instanceof ApiError ? err.message : t('Handbuch konnte nicht geladen werden')))
  }, [])

  useEffect(() => {
    if (!slug) return
    setPage(null)
    api.helpPage(slug)
      .then(setPage)
      .catch((err) => onToast(err instanceof ApiError ? err.message : t('Handbuch konnte nicht geladen werden'), 'bad'))
  }, [slug, onToast])

  // Nach jedem Kapitelwechsel oben anfangen — sonst landet man mitten im Text.
  useEffect(() => { body.current?.scrollTo({ top: 0 }) }, [page])

  const html = useMemo(() => (page ? renderMarkdown(page.markdown) : ''), [page])

  const groups = useMemo(() => {
    const list = (chapters ?? []).filter(
      (c) => !query || c.title.toLowerCase().includes(query.toLowerCase()))
    const out: { section: string; items: HelpChapter[] }[] = []
    for (const c of list) {
      const last = out[out.length - 1]
      if (last && last.section === c.section) last.items.push(c)
      else out.push({ section: c.section, items: [c] })
    }
    return out
  }, [chapters, query])

  /* Verweise zwischen Kapiteln bleiben im Programm. Ein Klick-Abfangen am
     Container reicht — jedes Kapitel neu zu verdrahten wäre unnötig. */
  function onBodyClick(e: React.MouseEvent) {
    const target = (e.target as HTMLElement).closest('a[data-chapter]')
    if (!target) return
    e.preventDefault()
    const next = target.getAttribute('data-chapter')
    if (next && chapters?.some((c) => c.slug === next)) setSlug(next)
    else onToast(t('Dieses Kapitel ist für dich nicht freigegeben.'), 'bad')
  }

  if (failed) {
    return (
      <div className="wrap"><div className="empty">
        <p className="empty__title">{t('Handbuch nicht verfügbar')}</p>
        <p className="empty__body">{failed}</p>
      </div></div>
    )
  }

  return (
    <div className="wrap">
      <header className="topbar">
        <div>
          <p className="silk" style={{ marginBottom: 6 }}>{t('Handbuch')}</p>
          <h1 className="h-page">{t('Hilfe')}</h1>
        </div>
      </header>

      {lang === 'en' && (
        <p className="sub" style={{ marginBottom: 16 }}>
          The handbook itself is written in German. The interface follows your language setting.
        </p>
      )}

      <div className="book">
        <aside className="book__index" aria-label={t('Kapitel')}>
          <input className="book__find" type="search" value={query} placeholder={t('Kapitel durchsuchen')}
            onChange={(e) => setQuery(e.target.value)} />

          {groups.map((g) => (
            <div key={g.section} className="book__group">
              <p className="silk book__section">{t(g.section)}</p>
              {g.items.map((c) => (
                <button key={c.slug} type="button"
                  className={`book__item${c.slug === slug ? ' is-on' : ''}`}
                  aria-current={c.slug === slug ? 'page' : undefined}
                  onClick={() => setSlug(c.slug)}>
                  {c.title}
                </button>
              ))}
            </div>
          ))}

          {chapters && groups.length === 0 && (
            <p className="sub" style={{ padding: '10px 12px' }}>{t('Kein Kapitel passt zur Suche.')}</p>
          )}
        </aside>

        <div className="book__page" ref={body} onClick={onBodyClick}>
          {page
            ? <div className="md" dangerouslySetInnerHTML={{ __html: html }} />
            : <p className="sub">{t('Wird geladen…')}</p>}
        </div>
      </div>
    </div>
  )
}
