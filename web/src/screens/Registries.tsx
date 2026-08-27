import { useCallback, useEffect, useMemo, useState } from 'react'
import { Field } from '../components/controls'
import { Workbench } from '../components/Workbench'
import {
  ApiError, api,
  type Registry, type RegistryEntry, type Host,
} from '../lib/api'
import { ago, gb } from '../lib/format'
import { t as tr, useLang } from '../lib/i18n'

/**
 * Kataloge fremder Registries — und was man daraus übernimmt.
 *
 * Der Wunsch dahinter: nicht jede Anwendung selbst bauen müssen. Kasm
 * veröffentlicht Kataloge mit fertigen Images, allein im offiziellen 86
 * Stück, und die lassen sich hier durchsuchen und übernehmen.
 *
 * Zwei Dinge, die diese Ansicht bewusst deutlich sagt, statt sie zu
 * verschweigen:
 *
 *   **Grösse.** Ein Katalogeintrag wiegt gern 5 bis 10 GB. Sie steht an jedem
 *   Eintrag, und wenn der freie Platz knapp wird, steht es auch dort.
 *
 *   **Herkunft.** Eine Registry ist eine Vertrauensentscheidung. Was von dort
 *   kommt, läuft anschliessend im eigenen Netz.
 */
export function Registries({ onToast }: { onToast: (m: string, tone?: 'ok' | 'bad') => void }) {
  useLang()
  const [list, setList] = useState<Registry[] | null>(null)
  const [suggested, setSuggested] = useState<{ name: string; url: string }[]>([])
  const [open, setOpen] = useState<Registry | null>(null)
  const [url, setUrl] = useState('')
  const [busy, setBusy] = useState(false)
  const [failed, setFailed] = useState<string | null>(null)

  const load = useCallback(async () => {
    try {
      setList(await api.registries())
      setFailed(null)
    } catch (err) {
      setFailed(err instanceof ApiError ? err.message : tr('Laden fehlgeschlagen'))
    }
  }, [])

  useEffect(() => {
    void load()
    api.suggestedRegistries().then(setSuggested).catch(() => {})
  }, [load])

  async function add(address: string) {
    const wanted = address.trim()
    if (!wanted) return
    setBusy(true)
    try {
      const added = await api.addRegistry(wanted)
      setUrl('')
      await load()
      onToast(tr('{name} eingetragen — {n} Anwendungen im Katalog.',
        { name: added.name, n: added.entry_count }))
    } catch (err) {
      onToast(err instanceof ApiError ? err.message : tr('Eintragen fehlgeschlagen'), 'bad')
    } finally {
      setBusy(false)
    }
  }

  async function refresh(registry: Registry) {
    setBusy(true)
    try {
      await api.refreshRegistry(registry.id)
      await load()
      onToast(tr('{name} aufgefrischt.', { name: registry.name }))
    } catch (err) {
      onToast(err instanceof ApiError ? err.message : tr('Auffrischen fehlgeschlagen'), 'bad')
    } finally {
      setBusy(false)
    }
  }

  async function remove(registry: Registry) {
    if (!window.confirm(tr('„{name}" entfernen? Bereits übernommene Workspaces bleiben.',
      { name: registry.name }))) return
    try {
      const result = await api.removeRegistry(registry.id)
      await load()
      onToast(result.status)
    } catch (err) {
      onToast(err instanceof ApiError ? err.message : tr('Löschen fehlgeschlagen'), 'bad')
    }
  }

  if (open) {
    return <Catalog registry={open} onBack={() => { setOpen(null); void load() }} onToast={onToast} />
  }

  if (failed) {
    return (
      <div className="wrap"><div className="empty">
        <p className="empty__title">{tr('Konnte nicht geladen werden')}</p>
        <p className="empty__body">{failed}</p>
      </div></div>
    )
  }
  if (!list) return <div className="wrap"><p className="sub">{tr('Wird geladen…')}</p></div>

  const known = new Set(list.map((r) => r.url))

  return (
    <div className="wrap">
      <header className="topbar">
        <div>
          <p className="silk" style={{ marginBottom: 6 }}>{tr('Verwaltung')}</p>
          <h1 className="h-page">{tr('Registries')}</h1>
        </div>
      </header>

      <p className="sub" style={{ marginBottom: 18 }}>
        {tr('Fremde Kataloge mit fertigen Anwendungen. Eintragen liest nur den Katalog — heruntergeladen wird erst, was du übernimmst und startest.')}
      </p>

      <div className="panel" style={{ padding: '18px 20px', marginBottom: 22 }}>
        <Field label={tr('Registry eintragen')}
          hint={tr('Die Adresse ohne Schema-Pfad. OTA liest dort {schema}.', { schema: '/1.1/list.json' })}>
          <div className="row-item">
            <input value={url} spellCheck={false}
              placeholder="https://registry.kasmweb.com"
              aria-label={tr('Adresse der Registry')} disabled={busy}
              onChange={(e) => setUrl(e.target.value)}
              onKeyDown={(e) => { if (e.key === 'Enter') { e.preventDefault(); void add(url) } }} />
            <button className="btn btn--primary" disabled={busy || !url.trim()}
              onClick={() => void add(url)}>
              {busy ? tr('Wird gelesen…') : tr('Eintragen')}
            </button>
          </div>
        </Field>

        {suggested.some((s) => !known.has(s.url)) && (
          <div className="chips" style={{ marginTop: 6 }}>
            {suggested.filter((s) => !known.has(s.url)).map((s) => (
              <button key={s.url} type="button" className="chip chip--add"
                disabled={busy} title={s.url} onClick={() => void add(s.url)}>
                <span aria-hidden="true" style={{ marginRight: 6 }}>+</span>{s.name}
              </button>
            ))}
          </div>
        )}
      </div>

      {list.length === 0 ? (
        <div className="empty">
          <p className="empty__title">{tr('Noch keine Registry eingetragen')}</p>
          <p className="empty__body">
            {tr('Trage eine Adresse ein oder nimm einen der Vorschläge oben.')}
          </p>
        </div>
      ) : (
        <div className="panel" style={{ padding: '14px 0 0' }}>
          <table className="tbl">
            <thead>
              <tr>
                <th style={{ paddingLeft: 20 }}>{tr('Registry')}</th>
                <th>{tr('Anwendungen')}</th>
                <th>{tr('Übernommen')}</th>
                <th>{tr('Zuletzt gelesen')}</th>
                <th />
              </tr>
            </thead>
            <tbody>
              {list.map((r) => (
                <tr key={r.id} tabIndex={0} style={{ cursor: 'pointer' }}
                  onClick={() => setOpen(r)}
                  onKeyDown={(e) => { if (e.key === 'Enter') setOpen(r) }}>
                  <td style={{ paddingLeft: 20 }}>
                    <div style={{ fontWeight: 500 }}>{r.name}</div>
                    <div className="data" style={{ fontSize: 11, color: 'var(--mute)' }}>{r.url}</div>
                    {r.fetch_error && (
                      <div style={{ fontSize: 11.5, color: 'var(--halt)', marginTop: 3 }}>
                        {r.fetch_error}
                      </div>
                    )}
                  </td>
                  <td className="data" style={{ color: 'var(--label)' }}>{r.entry_count}</td>
                  <td className="data" style={{ color: 'var(--label)' }}>{r.imported_count}</td>
                  <td className="data" style={{ color: 'var(--mute)', fontSize: 12 }}>
                    {r.last_fetched_at ? ago(new Date(r.last_fetched_at).getTime()) : '—'}
                  </td>
                  <td style={{ textAlign: 'right', paddingRight: 20, whiteSpace: 'nowrap' }}>
                    <button className="btn btn--sm btn--ghost" disabled={busy}
                      onClick={(e) => { e.stopPropagation(); void refresh(r) }}>
                      {tr('Auffrischen')}
                    </button>
                    <button className="btn btn--sm btn--ghost" style={{ marginLeft: 6 }}
                      onClick={(e) => { e.stopPropagation(); void remove(r) }}>
                      {tr('Entfernen')}
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      <p className="note-warn" style={{ marginTop: 18 }}>
        {tr('Eine Registry ist eine Vertrauensentscheidung. Ihr Katalog trägt zwar eine Signatur, aber der Schlüssel dafür liegt beim Betreiber — OTA prüft sie nicht. Was du übernimmst, läuft anschliessend in deinem Netz.')}
      </p>
    </div>
  )
}

// ------------------------------------------------------------------ Katalog

function Catalog({ registry, onBack, onToast }: {
  registry: Registry
  onBack: () => void
  onToast: (m: string, tone?: 'ok' | 'bad') => void
}) {
  const [entries, setEntries] = useState<RegistryEntry[] | null>(null)
  const [host, setHost] = useState<Host | null>(null)
  const [query, setQuery] = useState('')
  const [category, setCategory] = useState('Alle')
  const [busy, setBusy] = useState<string | null>(null)

  const load = useCallback(() => {
    api.registryEntries(registry.id).then(setEntries).catch(() => setEntries([]))
  }, [registry.id])

  useEffect(() => {
    load()
    api.host().then(setHost).catch(() => {})
  }, [load])

  const categories = useMemo(() => {
    const all = new Set<string>()
    for (const e of entries ?? []) e.categories.forEach((c) => all.add(c))
    return ['Alle', ...[...all].sort()]
  }, [entries])

  const shown = useMemo(() => (entries ?? []).filter((e) => {
    if (category !== 'Alle' && !e.categories.includes(category)) return false
    if (!query) return true
    const needle = query.toLowerCase()
    return e.friendly_name.toLowerCase().includes(needle)
      || e.description.toLowerCase().includes(needle)
  }), [entries, query, category])

  async function take(entry: RegistryEntry) {
    setBusy(entry.sha)
    try {
      const result = await api.importRegistryEntry(registry.id, entry.sha)
      load()
      onToast(result.status)
    } catch (err) {
      onToast(err instanceof ApiError ? err.message : tr('Übernehmen fehlgeschlagen'), 'bad')
    } finally {
      setBusy(null)
    }
  }

  const freeGb = host ? host.disk_free / 1024 ** 3 : null

  /* Wie Docker die Architektur nennt, gegenüber dem, was der Host meldet.
     Ein reines arm64-Image auf einem amd64-Host liesse sich übernehmen und
     würde erst beim Start scheitern — mit einer Meldung, die niemand mit
     diesem Katalog in Verbindung bringt. */
  const archMap: Record<string, string> = {
    x86_64: 'amd64', amd64: 'amd64', aarch64: 'arm64', arm64: 'arm64',
    armv7l: 'arm', armhf: 'arm',
  }
  const reported = host?.architecture ?? ''
  const arch = archMap[reported] ?? reported

  return (
    <Workbench
      crumb={tr('Registries')} title={registry.name} subtitle={registry.url}
      tabs={[tr('Katalog')]} tab={tr('Katalog')} onTab={() => {}} onBack={onBack}
      actions={
        <span className="sub">
          {tr('{n} von {total} Anwendungen', { n: shown.length, total: entries?.length ?? 0 })}
        </span>
      }
    >
      <div className="row-item" style={{ maxWidth: 460, marginBottom: 14 }}>
        <input value={query} type="search" placeholder={tr('Katalog durchsuchen')}
          aria-label={tr('Katalog durchsuchen')}
          onChange={(e) => setQuery(e.target.value)} />
      </div>

      <div className="chips" style={{ marginBottom: 20 }}>
        {categories.map((c) => (
          <button key={c} type="button" aria-pressed={c === category}
            className={`chip${c === category ? ' is-on' : ''}`}
            onClick={() => setCategory(c)}>{c === 'Alle' ? tr('Alle') : c}</button>
        ))}
      </div>

      {!entries ? <p className="sub">{tr('Wird geladen…')}</p> : (
        <div className="catalog">
          {shown.map((e) => {
            const sizeGb = e.uncompressed_size_mb / 1024
            // Warnen, wenn dieses eine Image ein Viertel des freien Platzes
            // nimmt. Die Zahl steht ohnehin da; hier geht es um den Moment
            // vor dem Klick.
            const heavy = freeGb !== null && sizeGb > freeGb / 4
            const fits = !arch || e.architectures.length === 0
              || e.architectures.includes(arch)
            return (
              <article key={e.sha} className="catalog__item">
                {/* Über die eigene API, nicht direkt: Die Inhaltsregel lässt
                    keine fremden Bildquellen zu, und sie dafür je Registry
                    aufzuweichen wäre für ein Symbol ein schlechter Tausch. */}
                {e.icon_url
                  ? <img className="catalog__icon" loading="lazy" alt=""
                      src={`/api/admin/registries/${registry.id}/icon?sha=${e.sha}`}
                      onError={(ev) => { ev.currentTarget.style.visibility = 'hidden' }} />
                  : <span className="catalog__icon" aria-hidden="true">▢</span>}
                <div className="catalog__body">
                  <div className="catalog__head">
                    <b>{e.friendly_name}</b>
                    <span className="data catalog__size" data-heavy={heavy || undefined}>
                      {sizeGb >= 1 ? `${sizeGb.toFixed(1)} GB` : `${e.uncompressed_size_mb} MB`}
                    </span>
                  </div>
                  <p className="catalog__desc">{e.description}</p>
                  <div className="catalog__meta data">
                    {e.image_ref}
                    {e.categories.length > 0 && ` · ${e.categories.join(', ')}`}
                  </div>
                  {heavy && (
                    <p className="catalog__warn">
                      {tr('Das ist ein grosser Teil der freien {free} GB auf diesem Host.',
                        { free: gb(host!.disk_free, 0) })}
                    </p>
                  )}
                  {!fits && (
                    <p className="catalog__warn">
                      {tr('Nur für {archs} — dieser Host ist {here}.',
                        { archs: e.architectures.join(', '), here: arch })}
                    </p>
                  )}
                </div>
                {e.imported_template_id ? (
                  <span className="silk catalog__done">{tr('übernommen')}</span>
                ) : (
                  <button className="btn btn--sm" disabled={busy === e.sha || !fits}
                    title={fits ? undefined : tr('Läuft auf dieser Architektur nicht.')}
                    onClick={() => void take(e)}>
                    {busy === e.sha ? tr('Wird übernommen…') : tr('Übernehmen')}
                  </button>
                )}
              </article>
            )
          })}
          {shown.length === 0 && (
            <p className="sub">{tr('Nichts passt zu dieser Suche.')}</p>
          )}
        </div>
      )}

      <p className="note-info" style={{ marginTop: 20 }}>
        {tr('Übernehmen legt nur eine Vorlage an — abgeschaltet, ohne Gruppe. Das Image wird erst beim ersten Start geholt. Die Lizenz der Anwendung gilt unverändert; dass ein Katalog sie listet, sagt darüber nichts.')}
      </p>
    </Workbench>
  )
}
