import { useEffect, useMemo, useState } from 'react'
import { Toggle } from '../components/controls'
import { ApiError, api, type NewsBeitrag, type NewsIn } from '../lib/api'
import { renderMarkdown } from '../lib/markdown'
import { getLang, t as tr, useLang } from '../lib/i18n'

/* News: Meldungen der Verwaltung an alle (Handbuch Kapitel 11).

   Wer `settings.manage` hat, schreibt direkt auf dieser Seite — Markdown mit
   Vorschau, derselbe Renderer wie das Handbuch. Der maskiert jedes HTML, ein
   Beitrag kann also nichts ausführen.

   Beim Öffnen gilt alles als gelesen; der Punkt in der Seitenleiste
   verschwindet. Was seit dem letzten Besuch neu ist, trägt hier ein „Neu". */

const LEER: NewsIn = { titel: '', text: '', angeheftet: false, entwurf: false }

function datum(iso: string): string {
  return new Date(iso).toLocaleDateString(getLang() === 'de' ? 'de-DE' : 'en-GB', {
    day: '2-digit', month: 'long', year: 'numeric',
  })
}

function Editor({ start, onSave, onCancel, busy }: {
  start: NewsIn
  onSave: (b: NewsIn) => void
  onCancel: () => void
  busy: boolean
}) {
  const [b, setB] = useState<NewsIn>(start)
  const [vorschau, setVorschau] = useState(false)
  const html = useMemo(() => (vorschau ? renderMarkdown(b.text) : ''), [vorschau, b.text])
  return (
    <div className="panel news__editor">
      <input className="input news__titel-eingabe" value={b.titel} maxLength={200} autoFocus
        placeholder={tr('Titel')} aria-label={tr('Titel')}
        onChange={(e) => setB({ ...b, titel: e.target.value })} />
      <div className="seg" role="radiogroup" aria-label={tr('Ansicht')} style={{ margin: '12px 0 10px' }}>
        {[false, true].map((v) => (
          <button key={String(v)} type="button" role="radio" aria-checked={vorschau === v}
            className={`seg__opt${vorschau === v ? ' is-on' : ''}`} onClick={() => setVorschau(v)}>
            {v ? tr('Vorschau') : tr('Schreiben')}
          </button>
        ))}
      </div>
      {vorschau ? (
        <div className="md news__vorschau" dangerouslySetInnerHTML={{ __html: html || '<p>—</p>' }} />
      ) : (
        <textarea className="input news__text" spellCheck rows={14} value={b.text}
          aria-label={tr('Text (Markdown)')}
          placeholder={tr('Text in Markdown: **fett**, *kursiv*, `Code`, ## Überschrift, - Liste, [Link](https://…)')}
          onChange={(e) => setB({ ...b, text: e.target.value })} />
      )}
      <div className="news__schalter">
        <Toggle on={b.angeheftet} name={tr('Oben anheften')}
          note={tr('Steht über allen anderen, bis du es wieder abschaltest.')}
          onChange={(v) => setB({ ...b, angeheftet: v })} />
        <Toggle on={b.entwurf} name={tr('Entwurf')}
          note={tr('Nur für die Verwaltung sichtbar, ohne Hinweis an die Nutzer.')}
          onChange={(v) => setB({ ...b, entwurf: v })} />
      </div>
      <div className="news__knoepfe">
        <button className="btn btn--ghost" onClick={onCancel} disabled={busy}>{tr('Abbrechen')}</button>
        <button className="btn btn--primary" disabled={busy || !b.titel.trim()} onClick={() => onSave(b)}>
          {b.entwurf ? tr('Entwurf speichern') : tr('Veröffentlichen')}
        </button>
      </div>
    </div>
  )
}

export function News({ onToast, onGelesen }: {
  onToast: (m: string, tone?: 'ok' | 'bad') => void
  onGelesen: () => void
}) {
  useLang()
  const [daten, setDaten] = useState<{ beitraege: NewsBeitrag[]; gelesen_bis: string; darf_schreiben: boolean } | null>(null)
  const [fehler, setFehler] = useState<string | null>(null)
  // `neu` für einen neuen Beitrag, sonst die Kennung des bearbeiteten.
  const [bearbeiten, setBearbeiten] = useState<string | null>(null)
  const [loeschFrage, setLoeschFrage] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)

  async function laden() {
    try {
      setDaten(await api.news()); setFehler(null)
    } catch (err) {
      setFehler(err instanceof ApiError ? err.message : tr('Laden fehlgeschlagen'))
    }
  }

  useEffect(() => {
    // Erst laden, dann als gelesen markieren: So weiss die Liste noch, was
    // seit dem letzten Besuch neu war.
    void laden().then(() => api.newsGelesen().then(onGelesen).catch(() => undefined))
  }, [])

  async function speichern(b: NewsIn) {
    setBusy(true)
    try {
      if (bearbeiten === 'neu') await api.newsAnlegen(b)
      else if (bearbeiten) await api.newsAendern(bearbeiten, b)
      onToast(b.entwurf ? tr('Entwurf gespeichert') : tr('Veröffentlicht'))
      setBearbeiten(null)
      await laden()
    } catch (err) {
      onToast(err instanceof ApiError ? err.message : tr('Speichern fehlgeschlagen'), 'bad')
    } finally {
      setBusy(false)
    }
  }

  async function loeschen(id: string) {
    setBusy(true)
    try {
      await api.newsLoeschen(id)
      onToast(tr('Beitrag gelöscht'))
      setLoeschFrage(null)
      await laden()
    } catch (err) {
      onToast(err instanceof ApiError ? err.message : tr('Löschen fehlgeschlagen'), 'bad')
    } finally {
      setBusy(false)
    }
  }

  const kopf = (
    <header className="topbar">
      <div>
        <p className="silk" style={{ marginBottom: 6 }}>{tr('Neuigkeiten der Verwaltung')}</p>
        <h1 className="h-page">{tr('News')}</h1>
      </div>
      {daten?.darf_schreiben && bearbeiten === null && (
        <button className="btn btn--primary" onClick={() => setBearbeiten('neu')}>{tr('Neuer Beitrag')}</button>
      )}
    </header>
  )

  if (fehler) {
    return (
      <div className="wrap">{kopf}<div className="empty">
        <p className="empty__title">{tr('Konnte nicht geladen werden')}</p>
        <p className="empty__body">{fehler}</p>
        <button className="btn" onClick={() => void laden()}>{tr('Erneut versuchen')}</button>
      </div></div>
    )
  }
  if (!daten) return <div className="wrap">{kopf}<p className="sub">{tr('Wird geladen…')}</p></div>

  const gelesenBis = new Date(daten.gelesen_bis).getTime()

  return (
    <div className="wrap news">
      {kopf}
      {bearbeiten === 'neu' && (
        <Editor start={LEER} busy={busy} onSave={(b) => void speichern(b)} onCancel={() => setBearbeiten(null)} />
      )}
      {daten.beitraege.length === 0 && bearbeiten !== 'neu' && (
        <div className="empty">
          <p className="empty__title">{tr('Noch keine News')}</p>
          <p className="empty__body">
            {daten.darf_schreiben
              ? tr('Hier erscheinen Meldungen an alle Nutzer — Wartungsfenster, neue Workspaces, Änderungen. Neue Beiträge zeigt die Seitenleiste mit einem Punkt an.')
              : tr('Hier erscheinen Meldungen der Verwaltung, etwa Wartungsfenster oder neue Workspaces.')}
          </p>
        </div>
      )}
      {daten.beitraege.map((b) => {
        if (bearbeiten === b.id) {
          return (
            <Editor key={b.id} start={b} busy={busy}
              onSave={(x) => void speichern(x)} onCancel={() => setBearbeiten(null)} />
          )
        }
        const neu = !b.entwurf && b.veroeffentlicht_am !== null
          && new Date(b.veroeffentlicht_am).getTime() > gelesenBis
        return (
          <article key={b.id} className={`panel news__beitrag${b.angeheftet ? ' is-pinned' : ''}`}>
            <header className="news__kopf">
              <div>
                <h2 className="news__titel">
                  {b.titel}
                  {neu && <span className="news__marke news__marke--neu">{tr('Neu')}</span>}
                  {b.angeheftet && <span className="news__marke">{tr('Angeheftet')}</span>}
                  {b.entwurf && <span className="news__marke news__marke--entwurf">{tr('Entwurf')}</span>}
                </h2>
                <p className="news__meta">
                  {datum(b.veroeffentlicht_am ?? b.erstellt_am)}
                  {b.autor && <> · {b.autor}</>}
                  {b.veroeffentlicht_am && b.geaendert_am > b.veroeffentlicht_am
                    && Date.parse(b.geaendert_am) - Date.parse(b.veroeffentlicht_am) > 60_000 && (
                    <> · {tr('geändert am {d}', { d: datum(b.geaendert_am) })}</>
                  )}
                </p>
              </div>
              {daten.darf_schreiben && (
                <div className="tbl__aktionen">
                  {loeschFrage === b.id ? (
                    <>
                      <span className="silk">{tr('Beitrag löschen?')}</span>
                      <button className="btn btn--sm btn--halt" disabled={busy}
                        onClick={() => void loeschen(b.id)}>{tr('Löschen')}</button>
                      <button className="btn btn--sm btn--ghost"
                        onClick={() => setLoeschFrage(null)}>{tr('Abbrechen')}</button>
                    </>
                  ) : (
                    <>
                      <button className="btn btn--sm" onClick={() => setBearbeiten(b.id)}>{tr('Bearbeiten')}</button>
                      <button className="btn btn--sm btn--halt" onClick={() => setLoeschFrage(b.id)}>{tr('Löschen')}</button>
                    </>
                  )}
                </div>
              )}
            </header>
            <div className="md" dangerouslySetInnerHTML={{ __html: renderMarkdown(b.text) }} />
          </article>
        )
      })}
    </div>
  )
}
