import { useCallback, useEffect, useRef, useState } from 'react'
import { Field, Segmented } from '../components/controls'
import {
  ApiError, api,
  type RepoAuftrag, type RepoModus, type RepoPaket, type RepoUebersicht,
} from '../lib/api'
import { gb, size } from '../lib/format'
import { t as tr, useLang } from '../lib/i18n'

/**
 * Verwaltung → Paketquellen (Handbuch Kapitel 26).
 *
 * Eine eigene Paketquelle für Debian 13: ein Spiegel von trixie, trixie-updates,
 * trixie-security und Dockers Paketquelle, dazu eigene Pakete und
 * festgehaltene Stände. Zweck (Betreiber, 2026-10-07): Ausfallsicherheit —
 * Arbeitsplätze und Bildbauer installieren auch dann, wenn draussen etwas
 * fehlt — und eigene Pakete.
 *
 * Abgeglichen wird **nur von Hand**. Das Alter des Spiegels steht deshalb
 * oben und wird gelb und rot, damit „von Hand" nicht „nie" bedeutet.
 */

type Tab = 'Spiegel' | 'Eigene Pakete' | 'Snapshots' | 'Dateien'
type Toast = (m: string, tone?: 'ok' | 'bad') => void

const MODI: { value: RepoModus; label: string; note: string }[] = [
  { value: 'zuerst', label: 'Eigene zuerst',
    note: 'Arbeitsplätze nehmen Pakete von hier; was hier fehlt, kommt wie bisher aus dem Internet.' },
  { value: 'nur', label: 'Nur eigene',
    note: 'Die Internetquellen im Arbeitsplatz werden abgeschaltet. Was hier fehlt, lässt sich nicht installieren.' },
  { value: 'aus', label: 'Aus',
    note: 'Nichts wird eingetragen. Der Spiegel bleibt, wie er ist.' },
]

function zeit(iso?: string | null): string {
  if (!iso) return '—'
  const d = new Date(iso)
  return Number.isNaN(d.getTime()) ? iso : d.toLocaleString()
}

function fehler(err: unknown, sonst: string): string {
  return err instanceof ApiError ? err.message : tr(sonst)
}

export function Paketquellen({ onToast }: { onToast: Toast }) {
  useLang()
  const [data, setData] = useState<RepoUebersicht | null>(null)
  const [failed, setFailed] = useState<string | null>(null)
  const [tab, setTab] = useState<Tab>('Spiegel')
  const [auftrag, setAuftrag] = useState<RepoAuftrag | null>(null)
  const lief = useRef(false)

  const load = useCallback(async () => {
    try {
      setData(await api.repo())
      setFailed(null)
    } catch (err) {
      setFailed(fehler(err, 'Laden fehlgeschlagen'))
    }
  }, [])

  // Der laufende Auftrag (Abgleich, Dateien holen) wird alle zwei Sekunden
  // nachgelesen, solange er läuft — und danach einmal die ganze Übersicht.
  const pruefeAuftrag = useCallback(async () => {
    try {
      const a = await api.repoAuftrag()
      setAuftrag(a)
      if (lief.current && !a.laeuft) {
        void load()
        onToast(a.ergebnis === 'ok'
          ? tr('{art}: fertig', { art: tr(a.art) })
          : tr('{art}: {ergebnis}', { art: tr(a.art), ergebnis: a.ergebnis }),
        a.ergebnis === 'ok' ? 'ok' : 'bad')
      }
      lief.current = a.laeuft
    } catch { /* Dienst kurz weg — beim nächsten Mal wieder */ }
  }, [load, onToast])

  useEffect(() => { void load(); void pruefeAuftrag() }, [load, pruefeAuftrag])
  useEffect(() => {
    if (!auftrag?.laeuft) return
    const id = window.setInterval(() => void pruefeAuftrag(), 2000)
    return () => window.clearInterval(id)
  }, [auftrag?.laeuft, pruefeAuftrag])

  async function anstossen(was: 'abgleich' | 'dateien') {
    try {
      const r = was === 'abgleich' ? await api.repoAbgleich() : await api.repoDateien()
      onToast(tr(r.status))
      lief.current = true
      await pruefeAuftrag()
    } catch (err) {
      onToast(fehler(err, 'Starten fehlgeschlagen'), 'bad')
    }
  }

  async function speichern(neu: Partial<RepoUebersicht['einstellungen']>) {
    if (!data) return
    const body = { ...data.einstellungen, ...neu }
    try {
      const r = await api.repoEinstellungen(body)
      setData({ ...data, einstellungen: body })
      onToast(tr(r.status))
    } catch (err) {
      onToast(fehler(err, 'Speichern fehlgeschlagen'), 'bad')
    }
  }

  const kopf = (
    <header className="topbar">
      <div>
        <p className="silk" style={{ marginBottom: 6 }}>{tr('Verwaltung')}</p>
        <h1 className="h-page">{tr('Paketquellen')}</h1>
      </div>
    </header>
  )

  if (failed) {
    return (
      <div className="wrap">{kopf}<div className="empty">
        <p className="empty__title">{tr('Konnte nicht geladen werden')}</p>
        <p className="empty__body">{failed}</p>
        <button className="btn" onClick={() => void load()}>{tr('Erneut versuchen')}</button>
      </div></div>
    )
  }
  if (!data) return <div className="wrap">{kopf}<p className="sub">{tr('Wird geladen…')}</p></div>

  if (!data.aktiv) {
    return (
      <div className="wrap">{kopf}<div className="empty">
        <p className="empty__title">{tr('Die eigene Paketquelle ist nicht eingeschaltet')}</p>
        <p className="empty__body">
          {tr('Sie ist ein Zusatz und ab Werk aus. Einschalten: in deploy/.env')}{' '}
          <code className="data">OTA_REPO=1</code>{' '}
          {tr('setzen und')}{' '}<code className="data">make update</code>{' '}
          {tr('ausführen. Ein Vollspiegel braucht grob 100 bis 130 GB — Handbuch Kapitel 26.')}
        </p>
      </div></div>
    )
  }
  if (!data.erreichbar || !data.status) {
    return (
      <div className="wrap">{kopf}<div className="empty">
        <p className="empty__title">{tr('Der Dienst der Paketquelle antwortet nicht')}</p>
        <p className="empty__body">{data.fehler ?? ''}</p>
        <button className="btn" onClick={() => void load()}>{tr('Erneut versuchen')}</button>
      </div></div>
    )
  }

  const st = data.status
  const ein = data.einstellungen
  const alter = data.alter_tage
  const ton = alter == null ? 'halt'
    : alter >= ein.alter_rot ? 'halt' : alter >= ein.alter_gelb ? 'caution' : undefined
  const laeuft = !!auftrag?.laeuft
  const snapNamen = Object.keys(st.snapshots).sort()

  return (
    <div className="wrap">
      {kopf}

      <div className="meters" style={{ marginBottom: 20 }}>
        <div className="panel meter">
          <div className="meter__top"><span className="silk">{tr('Stand des Spiegels')}</span>
            <span className={`meter__val${ton ? ' is-warn' : ''}`}
              style={ton === 'halt' ? { color: 'var(--halt)' } : undefined}>
              {alter == null ? tr('nie abgeglichen')
                : alter < 1 ? tr('heute') : tr('vor {n} Tagen', { n: Math.floor(alter) })}
            </span></div>
          <div className="meter__bar">
            <div className="meter__fill" data-tone={ton}
              style={{ width: `${Math.min(100, ((alter ?? ein.alter_rot) / ein.alter_rot) * 100)}%` }} />
          </div>
          <p className="meter__note">
            {tr('Gelb ab {g}, rot ab {r} Tagen. Abgeglichen wird nur von Hand.',
              { g: ein.alter_gelb, r: ein.alter_rot })}
          </p>
        </div>
        <div className="panel meter">
          <div className="meter__top"><span className="silk">{tr('Belegt')}</span>
            <span className="meter__val">{gb(st.belegt)} GB</span></div>
          <p className="meter__note">
            {st.vollspiegel ? tr('Vollspiegel') : tr('Gefiltert: {f}', { f: st.filter })}
          </p>
        </div>
        <div className="panel meter">
          <div className="meter__top"><span className="silk">{tr('Platz frei')}</span>
            <span className="meter__val">{gb(st.frei)} GB</span></div>
          <p className="meter__note">{tr('Eigene Pakete: {n}', { n: st.eigene_pakete })}</p>
        </div>
      </div>

      <div className="panel" style={{ padding: '18px 20px', marginBottom: 22 }}>
        <Field label={tr('Arbeitsplätze und Bildbauer')}
          hint={tr(MODI.find((m) => m.value === ein.modus)?.note ?? '') + ' '
            + tr('Gilt für Debian-13-Images ab dem nächsten Start; andere Images bleiben unberührt.')}>
          <Segmented value={ein.modus} label={tr('Betriebsart')}
            options={MODI.map((m) => ({ value: m.value, label: tr(m.label),
              tone: m.value === 'nur' ? 'halt' as const : undefined }))}
            onChange={(v) => void speichern({ modus: v })} />
        </Field>
      </div>

      {/* Läuft ein Auftrag, steht sein Protokoll offen da. Danach klappt es
          zu — der Ausgang steht in der Kopfzeile, die Einzelheiten braucht
          man nur, wenn etwas schiefging. */}
      {auftrag && (auftrag.laeuft || auftrag.protokoll) && (
        <details key={`${auftrag.start}-${auftrag.laeuft}`} className="panel"
          open={auftrag.laeuft || (auftrag.ergebnis !== 'ok' && auftrag.ergebnis !== '')}
          style={{ padding: '14px 20px', marginBottom: 22 }}>
          <summary className="silk" style={{ cursor: 'pointer' }}>
            {tr(auftrag.art)}{' · '}
            {auftrag.laeuft ? tr('läuft…')
              : auftrag.ergebnis === 'ok' ? tr('fertig')
                : <span className="is-warn">{auftrag.ergebnis}</span>}
            {' · '}<span className="data">{zeit(auftrag.start)}</span>
          </summary>
          <Protokoll text={auftrag.protokoll ?? ''} />
        </details>
      )}

      <div className="seg" role="radiogroup" aria-label={tr('Ansicht')} style={{ marginBottom: 20 }}>
        {(['Spiegel', 'Eigene Pakete', 'Snapshots', 'Dateien'] as Tab[]).map((x) => (
          <button key={x} type="button" role="radio" aria-checked={tab === x}
            className={`seg__opt${tab === x ? ' is-on' : ''}`} onClick={() => setTab(x)}>
            {tr(x)}
            {x === 'Eigene Pakete' && <span className="data" style={{ opacity: .6 }}> {st.eigene_pakete}</span>}
            {x === 'Snapshots' && <span className="data" style={{ opacity: .6 }}> {snapNamen.length}</span>}
          </button>
        ))}
      </div>

      {tab === 'Spiegel' && (
        <>
          <div className="row-item" style={{ marginBottom: 14, gap: 10 }}>
            <button className="btn btn--primary" disabled={laeuft} onClick={() => void anstossen('abgleich')}>
              {laeuft ? tr('Läuft…') : tr('Jetzt abgleichen')}
            </button>
            <span className="sub">
              {tr('Zuletzt:')} {zeit(st.letzter_abgleich?.zeit)}
            </span>
          </div>
          <div className="panel" style={{ padding: '14px 0 0', overflowX: 'auto', marginBottom: 22 }}>
            <table className="tbl">
              <thead><tr>
                <th style={{ paddingLeft: 20 }}>{tr('Spiegel')}</th>
                <th>{tr('Quelle')}</th>
                <th>{tr('Pakete')}</th>
                <th>{tr('Ausgeliefert wird')}</th>
              </tr></thead>
              <tbody>
                {st.spiegel.map((s) => (
                  <tr key={s.name} style={{ cursor: 'default' }}>
                    <td style={{ paddingLeft: 20 }}><b>{s.name}</b></td>
                    <td className="data" style={{ fontSize: 12 }}>{s.quelle}</td>
                    <td className="data">{s.angelegt ? s.pakete : '—'}</td>
                    <td className="data" style={{ fontSize: 12 }}>
                      {s.aktuell.startsWith('fest-')
                        ? <span className="is-warn">{tr('zurückgedreht: {s}', { s: s.aktuell })}</span>
                        : s.aktuell || tr('noch nicht abgeglichen')}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <div className="panel" style={{ padding: '18px 20px', maxWidth: 620 }}>
            <Field label={tr('Ab wann das Alter warnt (Tage)')}
              hint={tr('Gelb und rot oben bei „Stand des Spiegels".')}>
              <div className="row-item" style={{ gap: 10, maxWidth: 320 }}>
                <input type="number" min={1} aria-label={tr('gelb ab')} defaultValue={ein.alter_gelb}
                  onBlur={(e) => { const n = Number(e.target.value); if (n > 0 && n !== ein.alter_gelb) void speichern({ alter_gelb: n }) }} />
                <input type="number" min={1} aria-label={tr('rot ab')} defaultValue={ein.alter_rot}
                  onBlur={(e) => { const n = Number(e.target.value); if (n > 0 && n !== ein.alter_rot) void speichern({ alter_rot: n }) }} />
              </div>
            </Field>
            <p className="meter__note">
              {tr('Signiert mit')} <code className="data">{st.schluessel}</code>{' · '}
              <a className="repo-link data" href="/repo/ota-repo.asc" target="_blank" rel="noreferrer">ota-repo.asc</a>
            </p>
          </div>
        </>
      )}

      {tab === 'Eigene Pakete' && <EigenePakete onToast={onToast} onAenderung={() => void load()} />}

      {tab === 'Snapshots' && (
        <Snapshots data={data} onToast={onToast} onAenderung={() => void load()}
          onBauen={(name) => void speichern({ bau_snapshot: name })} />
      )}

      {tab === 'Dateien' && (
        <>
          <p className="sub" style={{ marginBottom: 14 }}>
            {tr('Was das Aufsetzen ohne Internet braucht und in keiner Paketquelle steht: die Python-Pakete, die Selkies braucht (gegen die Prüfsummen aus OTAs Fork geprüft), clipnotify und das Sysbox-Paket. Das Bauskript des Basisimages und die Sysbox-Einrichtung nehmen sie von hier. Selkies selbst liegt als Quellcode in OTAs Repository.')}
          </p>
          <div className="row-item" style={{ marginBottom: 14 }}>
            <button className="btn btn--primary" disabled={laeuft} onClick={() => void anstossen('dateien')}>
              {laeuft ? tr('Läuft…') : tr('Dateien holen')}
            </button>
          </div>
          {st.dateien.length === 0 ? (
            <div className="empty"><p className="empty__title">{tr('Noch keine Dateien')}</p></div>
          ) : (
            <div className="panel" style={{ padding: '14px 0 0', overflowX: 'auto' }}>
              <table className="tbl">
                <thead><tr>
                  <th style={{ paddingLeft: 20 }}>{tr('Datei')}</th><th>{tr('Grösse')}</th>
                </tr></thead>
                <tbody>
                  {st.dateien.map((d) => (
                    <tr key={d.pfad} style={{ cursor: 'default' }}>
                      <td style={{ paddingLeft: 20 }}>
                        <a className="repo-link data" href={`/repo/dateien/${d.pfad}`}>{d.pfad}</a>
                      </td>
                      <td className="data">{size(d.groesse)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </>
      )}
    </div>
  )
}

/** Das Protokoll eines Auftrags — scrollt mit, solange man unten ist. */
function Protokoll({ text }: { text: string }) {
  const ref = useRef<HTMLPreElement>(null)
  useEffect(() => {
    const el = ref.current
    if (el && el.scrollHeight - el.scrollTop - el.clientHeight < 60) el.scrollTop = el.scrollHeight
  }, [text])
  return <pre ref={ref} className="build__log" style={{ marginTop: 10 }}>{text || '…'}</pre>
}

function EigenePakete({ onToast, onAenderung }: { onToast: Toast; onAenderung: () => void }) {
  const [liste, setListe] = useState<RepoPaket[] | null>(null)
  const [drag, setDrag] = useState(false)
  const [busy, setBusy] = useState(false)
  const input = useRef<HTMLInputElement>(null)

  const load = useCallback(async () => {
    try { setListe(await api.repoPakete()) } catch (err) { onToast(fehler(err, 'Laden fehlgeschlagen'), 'bad') }
  }, [onToast])
  useEffect(() => { void load() }, [load])

  async function hochladen(dateien: FileList | null) {
    if (!dateien?.length) return
    setBusy(true)
    for (const datei of Array.from(dateien)) {
      try {
        const p = await api.repoHochladen(datei)
        onToast(tr('{name} {version} aufgenommen', { name: p.name, version: p.version }))
      } catch (err) {
        onToast(`${datei.name}: ${fehler(err, 'Hochladen fehlgeschlagen')}`, 'bad')
      }
    }
    setBusy(false)
    await load()
    onAenderung()
  }

  async function loeschen(p: RepoPaket) {
    if (!window.confirm(tr('{name} {version} aus der Paketquelle entfernen? In Arbeitsplätzen schon Installiertes bleibt.',
      { name: p.name, version: p.version }))) return
    try {
      const r = await api.repoPaketLoeschen(p.schluessel)
      onToast(tr(r.status))
      await load()
      onAenderung()
    } catch (err) {
      onToast(fehler(err, 'Löschen fehlgeschlagen'), 'bad')
    }
  }

  return (
    <>
      <p className="sub" style={{ marginBottom: 14 }}>
        {tr('Ein .deb für amd64 oder all. Es läuft bei der Installation als root in jedem Arbeitsplatz — hochladen dürfen deshalb nur Administratoren, und jeder Vorgang steht im Protokoll.')}
      </p>
      <div className={`dropzone${drag ? ' is-over' : ''}`} style={{ marginBottom: 18, alignItems: 'center', justifyContent: 'center' }}
        onDragOver={(e) => { e.preventDefault(); setDrag(true) }}
        onDragLeave={() => setDrag(false)}
        onDrop={(e) => { e.preventDefault(); setDrag(false); void hochladen(e.dataTransfer.files) }}>
        <p className="sub">{busy ? tr('Wird aufgenommen…') : tr('.deb-Dateien hierher ziehen oder')}</p>
        <button className="btn" disabled={busy} onClick={() => input.current?.click()}>{tr('Datei wählen')}</button>
        <input ref={input} type="file" accept=".deb" multiple hidden
          onChange={(e) => { void hochladen(e.target.files); e.target.value = '' }} />
      </div>
      {liste === null ? <p className="sub">{tr('Wird geladen…')}</p>
        : liste.length === 0 ? (
          <div className="empty"><p className="empty__title">{tr('Noch keine eigenen Pakete')}</p></div>
        ) : (
          <div className="panel" style={{ padding: '14px 0 0', overflowX: 'auto' }}>
            <table className="tbl">
              <thead><tr>
                <th style={{ paddingLeft: 20 }}>{tr('Paket')}</th><th>{tr('Fassung')}</th>
                <th>{tr('Architektur')}</th><th>{tr('Von')}</th><th>{tr('Wann')}</th><th />
              </tr></thead>
              <tbody>
                {liste.map((p) => (
                  <tr key={p.schluessel} style={{ cursor: 'default' }}>
                    <td style={{ paddingLeft: 20 }}><b>{p.name}</b></td>
                    <td className="data">{p.version}</td>
                    <td className="data">{p.arch}</td>
                    <td>{p.von ?? '—'}</td>
                    <td className="data" style={{ fontSize: 12 }}>{zeit(p.zeit)}</td>
                    <td style={{ textAlign: 'right', paddingRight: 20 }}>
                      <button className="btn btn--sm" onClick={() => void loeschen(p)}>{tr('Entfernen')}</button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
    </>
  )
}

function Snapshots({ data, onToast, onAenderung, onBauen }: {
  data: RepoUebersicht; onToast: Toast; onAenderung: () => void; onBauen: (name: string) => void
}) {
  const [name, setName] = useState('')
  const [notiz, setNotiz] = useState('')
  const [busy, setBusy] = useState(false)
  const snaps = data.status?.snapshots ?? {}
  const namen = Object.keys(snaps).sort((a, b) => snaps[b].zeit.localeCompare(snaps[a].zeit))
  const bau = data.einstellungen.bau_snapshot

  async function anlegen() {
    setBusy(true)
    try {
      await api.repoSnapshot(name.trim(), notiz.trim())
      onToast(tr('Stand „{name}" festgehalten', { name: name.trim() }))
      setName(''); setNotiz('')
      onAenderung()
    } catch (err) {
      onToast(fehler(err, 'Anlegen fehlgeschlagen'), 'bad')
    } finally {
      setBusy(false)
    }
  }

  async function aktion(was: 'zurueck' | 'loeschen', n: string) {
    const frage = was === 'zurueck'
      ? tr('Die Spiegel wieder mit dem Stand „{name}" ausliefern? Eigene Pakete bleiben, wie sie sind. Der nächste Abgleich schaltet wieder auf neu.', { name: n })
      : tr('Stand „{name}" löschen? Das lässt sich nicht rückgängig machen.', { name: n })
    if (!window.confirm(frage)) return
    setBusy(true)
    try {
      const r = was === 'zurueck' ? await api.repoZurueckdrehen(n) : await api.repoSnapshotLoeschen(n)
      onToast(tr(r.status))
      onAenderung()
    } catch (err) {
      onToast(fehler(err, 'Fehlgeschlagen'), 'bad')
    } finally {
      setBusy(false)
    }
  }

  return (
    <>
      <p className="sub" style={{ marginBottom: 14 }}>
        {tr('Ein Snapshot hält den heutigen Stand aller Spiegel und der eigenen Pakete fest, unter eigener Adresse (/repo/snap/<name>/). Er bleibt, bis du ihn löschst.')}
      </p>
      <div className="panel" style={{ padding: '18px 20px', marginBottom: 22, maxWidth: 720 }}>
        <Field label={tr('Stand festhalten')}
          hint={tr('Kleinbuchstaben, Ziffern und Bindestriche, z. B. 2026-10-vor-update.')}>
          <div className="row-item" style={{ gap: 10 }}>
            <input value={name} placeholder="2026-10-vor-update" aria-label={tr('Name')} spellCheck={false}
              onChange={(e) => setName(e.target.value.toLowerCase())} disabled={busy} />
            <input value={notiz} placeholder={tr('Notiz (optional)')} aria-label={tr('Notiz')}
              onChange={(e) => setNotiz(e.target.value)} disabled={busy} />
            <button className="btn btn--primary" disabled={busy || !name.trim()} onClick={() => void anlegen()}>
              {tr('Festhalten')}
            </button>
          </div>
        </Field>
        <Field label={tr('Bildbauer baut gegen')}
          hint={tr('Ein festgehaltener Stand macht Images reproduzierbar: Derselbe Bau ergibt dieselben Fassungen, auch nach einem Abgleich.')}>
          <select value={bau} aria-label={tr('Bildbauer baut gegen')} onChange={(e) => onBauen(e.target.value)}>
            <option value="">{tr('den aktuellen Stand')}</option>
            {namen.map((n) => <option key={n} value={n}>{n}</option>)}
          </select>
        </Field>
      </div>
      {namen.length === 0 ? (
        <div className="empty"><p className="empty__title">{tr('Noch kein Stand festgehalten')}</p></div>
      ) : (
        <div className="panel" style={{ padding: '14px 0 0', overflowX: 'auto' }}>
          <table className="tbl">
            <thead><tr>
              <th style={{ paddingLeft: 20 }}>{tr('Name')}</th><th>{tr('Wann')}</th>
              <th>{tr('Von')}</th><th>{tr('Notiz')}</th><th />
            </tr></thead>
            <tbody>
              {namen.map((n) => (
                <tr key={n} style={{ cursor: 'default' }}>
                  <td style={{ paddingLeft: 20 }}>
                    <b className="data">{n}</b>
                    {bau === n && <span className="chip" style={{ marginLeft: 8 }}>{tr('Bildbauer')}</span>}
                  </td>
                  <td className="data" style={{ fontSize: 12 }}>{zeit(snaps[n].zeit)}</td>
                  <td>{snaps[n].von || '—'}</td>
                  <td>{snaps[n].notiz}</td>
                  <td style={{ textAlign: 'right', paddingRight: 20, whiteSpace: 'nowrap' }}>
                    <button className="btn btn--sm" disabled={busy} onClick={() => void aktion('zurueck', n)}>
                      {tr('Zurückdrehen')}
                    </button>{' '}
                    <button className="btn btn--sm" disabled={busy || bau === n}
                      title={bau === n ? tr('Gegen diesen Stand wird gebaut.') : undefined}
                      onClick={() => void aktion('loeschen', n)}>{tr('Löschen')}</button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </>
  )
}
