import { useCallback, useEffect, useMemo, useState } from 'react'
import { ApiError, api, type SoftwareStand } from '../lib/api'
import { ago } from '../lib/format'
import { t as tr, useLang } from '../lib/i18n'

/**
 * Verwaltung → Softwaremonitoring (Handbuch Kapitel 11).
 *
 * Welche Anwendung in welchem Arbeitsplatz steckt, eine Whitelist, und was
 * nicht darauf steht. Ziel ist, Wildwuchs zu bemerken: Nach Rücksprache wird
 * eine Anwendung freigegeben, oder der Nutzer deinstalliert sie — dann fehlt
 * sie bei der nächsten Erfassung, und die Meldung verschwindet von selbst.
 */

type Toast = (m: string, tone?: 'ok' | 'bad') => void

const QUELLEN: Record<string, string> = {
  apt: 'apt', desktop: 'Startmenü', flatpak: 'Flatpak', snap: 'Snap',
}

const STATUS: Record<string, string> = {
  running: 'läuft', starting: 'startet', paused: 'pausiert', angehalten: 'angehalten',
}

function zustand(s: string): string {
  return tr(STATUS[s] ?? s)
}

function seit(iso?: string | null): string {
  return iso ? ago(new Date(iso).getTime()) : '—'
}

export function Softwaremonitoring({ onToast }: { onToast: Toast }) {
  useLang()
  const [data, setData] = useState<SoftwareStand | null>(null)
  const [failed, setFailed] = useState<string | null>(null)
  const [busy, setBusy] = useState<string | null>(null)
  const [suche, setSuche] = useState('')
  const [offen, setOffen] = useState<Record<string, boolean>>({})
  const [nurAbweichungen, setNurAbweichungen] = useState(false)
  const [neuName, setNeuName] = useState('')

  const load = useCallback(async () => {
    try {
      setData(await api.software())
      setFailed(null)
    } catch (err) {
      setFailed(err instanceof ApiError ? err.message : tr('Laden fehlgeschlagen'))
    }
  }, [])
  useEffect(() => { void load() }, [load])

  async function tun(was: string, fn: () => Promise<string | void>) {
    setBusy(was)
    try {
      const m = await fn()
      if (m) onToast(m)
      await load()
    } catch (err) {
      onToast(err instanceof ApiError ? err.message : tr('Hat nicht geklappt'), 'bad')
    } finally {
      setBusy(null)
    }
  }

  const q = suche.trim().toLowerCase()
  const plaetze = useMemo(() => (data?.arbeitsplaetze ?? []).filter((p) =>
    !q || p.user.toLowerCase().includes(q) || p.vorlage.toLowerCase().includes(q)
    || p.anwendungen.some((a) => a.name.includes(q) || a.titel.toLowerCase().includes(q))), [data, q])

  const whitelist = (data?.whitelist ?? []).filter((w) =>
    !q || w.name.includes(q) || w.titel.toLowerCase().includes(q))

  const kopf = (
    <header className="topbar">
      <div>
        <p className="silk" style={{ marginBottom: 6 }}>{tr('Verwaltung')}</p>
        <h1 className="h-page">{tr('Softwaremonitoring')}</h1>
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

  const letzte = data.letzte
  const fehler = Array.isArray(letzte?.fehler) ? letzte?.fehler : letzte?.fehler ? [letzte.fehler] : []

  return (
    <div className="wrap">
      {kopf}

      <p className="sub" style={{ maxWidth: 820 }}>
        {tr('Jede Stunde liest OTA die Anwendungen jedes laufenden Arbeitsplatzes: von Hand installierte Debian-Pakete, Programme im Startmenü (auch im Zuhause, etwa AppImages), Flatpak und Snap — ohne Versionen und ohne Bibliotheken. Was nicht auf der Whitelist steht, erscheint unten und auf dem Dashboard der Administratoren. Wird es deinstalliert, verschwindet die Meldung bei der nächsten Erfassung.')}
      </p>

      <div className="panel" style={{ padding: '12px 20px', margin: '14px 0 22px' }}>
        <div className="viewer__row" style={{ alignItems: 'center', flexWrap: 'wrap', gap: 10 }}>
          <span style={{ marginRight: 'auto' }}>
            {letzte
              ? <>
                {tr('Letzte Erfassung')}: <b>{seit(letzte.zeit)}</b>
                {letzte.ok
                  ? <> · {tr('{n} Arbeitsplätze', { n: letzte.container ?? 0 })}</>
                  : <> · <span className="note-warn">{String(letzte.fehler ?? tr('Gescheitert'))}</span></>}
                {' · '}{tr('alle {n} Min.', { n: data.intervall_minuten })}
              </>
              : tr('Noch nie erfasst.')}
          </span>
          <button className="btn" disabled={busy !== null}
            onClick={() => void tun('erfassen', async () => {
              const r = await api.softwareErfassen()
              return r.ok ? tr('{n} Arbeitsplätze erfasst.', { n: r.container ?? 0 })
                : String(r.fehler ?? tr('Gescheitert'))
            })}>
            {busy === 'erfassen' ? tr('Wird erfasst…') : tr('Jetzt erfassen')}
          </button>
        </div>
        {letzte?.ok && fehler.length > 0 && (
          <p className="note-warn" style={{ margin: '8px 0 0' }}>
            {tr('Nicht lesbar')}: {fehler.join(' · ')}
          </p>
        )}
      </div>

      {/* ------------------------------------------------ Meldungen */}
      <div className="section__head">
        <span className="silk">{tr('Nicht auf der Whitelist')}</span>
        <span className="section__rule" />
        <span className="silk data">{data.meldungen.length}</span>
      </div>

      {data.meldungen.length === 0 ? (
        <p className="sub" style={{ marginBottom: 22 }}>
          {data.whitelist.length === 0 && data.arbeitsplaetze.length > 0
            ? tr('Die Whitelist ist leer — unten lässt sie sich aus dem aktuellen Stand befüllen.')
            : tr('Alles, was installiert ist, steht auf der Whitelist.')}
        </p>
      ) : (
        <div className="panel" style={{ padding: '4px 0', overflowX: 'auto', marginBottom: 22 }}>
          <table className="tbl">
            <thead>
              <tr>
                <th>{tr('Anwendung')}</th><th>{tr('Herkunft')}</th><th>{tr('Wo')}</th>
                <th>{tr('Seit')}</th><th />
              </tr>
            </thead>
            <tbody>
              {data.meldungen.map((m) => (
                <tr key={m.name}>
                  <td><b className="data">{m.name}</b>{m.titel && <div className="sub">{m.titel}</div>}</td>
                  <td className="sub">{tr(QUELLEN[m.quelle] ?? m.quelle)}</td>
                  <td>
                    {m.orte.map((o) => (
                      <div key={o.session_id}>
                        {o.user} <span className="sub">· {o.vorlage}{o.status !== 'running' ? ` · ${zustand(o.status)}` : ''}</span>
                      </div>
                    ))}
                  </td>
                  <td className="sub">{seit(m.erstmals)}</td>
                  <td style={{ textAlign: 'right' }}>
                    <button className="btn btn--sm btn--primary" disabled={busy !== null}
                      onClick={() => void tun(`frei-${m.name}`, async () => {
                        await api.softwareFreigeben([m.name])
                        return tr('{name} steht jetzt auf der Whitelist.', { name: m.name })
                      })}>
                      {tr('In die Whitelist')}
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {/* ------------------------------------------------ Arbeitsplätze */}
      <div className="section__head">
        <span className="silk">{tr('Arbeitsplätze')}</span>
        <span className="section__rule" />
        <span className="silk data">{data.arbeitsplaetze.length}</span>
      </div>

      <div className="viewer__row" style={{ gap: 10, marginBottom: 10, flexWrap: 'wrap' }}>
        <div className="row-item" style={{ flex: '1 1 260px' }}>
          <input value={suche} placeholder={tr('Nutzer, Vorlage oder Anwendung')}
            aria-label={tr('Suchen')} onChange={(e) => setSuche(e.target.value)} />
        </div>
        <button className={`chip${nurAbweichungen ? ' is-on' : ''}`}
          onClick={() => setNurAbweichungen(!nurAbweichungen)}>
          {tr('Nur nicht freigegebene')}
        </button>
      </div>

      {plaetze.length === 0 ? (
        <p className="sub" style={{ marginBottom: 22 }}>
          {data.arbeitsplaetze.length === 0
            ? tr('Noch keine Daten. Erfasst werden laufende Arbeitsplätze.')
            : tr('Nichts gefunden.')}
        </p>
      ) : (
        <div style={{ marginBottom: 22 }}>
          {plaetze.map((p) => {
            const nicht = p.anwendungen.filter((a) => !a.frei)
            const zeigen = p.anwendungen.filter((a) => (!nurAbweichungen || !a.frei)
              && (!q || p.user.toLowerCase().includes(q) || p.vorlage.toLowerCase().includes(q)
                || a.name.includes(q) || a.titel.toLowerCase().includes(q)))
            const auf = offen[p.session_id] ?? false
            return (
              <div key={p.session_id} className="panel" style={{ padding: '10px 16px', marginBottom: 8 }}>
                <div className="viewer__row" style={{ alignItems: 'center', cursor: 'pointer' }}
                  onClick={() => setOffen({ ...offen, [p.session_id]: !auf })}>
                  <span className="data">{auf ? '▾' : '▸'}</span>
                  <b>{p.user}</b>
                  <span className="sub">· {p.vorlage}{p.klasse === 'root' ? ' · root' : ''} · {zustand(p.status)}</span>
                  <span style={{ marginLeft: 'auto' }} className="sub">
                    {tr('{n} Anwendungen', { n: p.anwendungen.length })}
                    {nicht.length > 0 && <> · <span className="note-warn" style={{ display: 'inline' }}>
                      {tr('{n} nicht freigegeben', { n: nicht.length })}</span></>}
                    {' · '}{seit(p.zuletzt)}
                  </span>
                </div>
                {auf && (
                  <div className="strip" style={{ marginTop: 10 }}>
                    {zeigen.map((a) => (
                      <span key={a.name} className={`chip${a.frei ? '' : ' is-on'}`}
                        title={`${a.titel ? a.titel + ' · ' : ''}${tr(QUELLEN[a.quelle] ?? a.quelle)}${a.frei ? '' : ' · ' + tr('nicht auf der Whitelist')}`}>
                        {a.frei ? '' : '⚠ '}{a.name}
                      </span>
                    ))}
                  </div>
                )}
              </div>
            )
          })}
        </div>
      )}

      {/* ------------------------------------------------ Whitelist */}
      <div className="section__head">
        <span className="silk">{tr('Whitelist')}</span>
        <span className="section__rule" />
        <span className="silk data">{data.whitelist.length}</span>
      </div>

      <div className="panel" style={{ padding: '14px 20px' }}>
        <p className="field__hint" style={{ marginTop: 0 }}>
          {tr('Gilt für alle Arbeitsplätze, nur der Name zählt — keine Version, keine Herkunft. Auch was das Image mitbringt, muss hier stehen.')}
        </p>
        <div className="viewer__row" style={{ gap: 10, flexWrap: 'wrap', marginBottom: 12 }}>
          <button className="btn" disabled={busy !== null}
            onClick={() => {
              if (!window.confirm(tr('Alles, was gerade in irgendeinem erfassten Arbeitsplatz installiert ist, kommt auf die Whitelist. Fortfahren?'))) return
              void tun('befuellen', async () => {
                const r = await api.softwareErstbefuellen()
                return tr('{n} Anwendungen aufgenommen.', { n: r.neu.length })
              })
            }}>
            {tr('Aus dem aktuellen Stand befüllen')}
          </button>
          <div className="row-item" style={{ flex: '1 1 220px' }}>
            <input value={neuName} placeholder={tr('Name, z. B. gimp')} aria-label={tr('Anwendung aufnehmen')}
              onChange={(e) => setNeuName(e.target.value)} />
          </div>
          <button className="btn" disabled={busy !== null || !neuName.trim()}
            onClick={() => void tun('neu', async () => {
              await api.softwareFreigeben([neuName.trim()])
              setNeuName('')
              return tr('Aufgenommen.')
            })}>
            {tr('Aufnehmen')}
          </button>
        </div>
        {q && <p className="field__hint">{tr('Gefiltert: {n} von {m}', { n: whitelist.length, m: data.whitelist.length })}</p>}
        {whitelist.length > 0 && (
          <div className="strip">
            {whitelist.map((w) => (
              <span key={w.name} className="chip" title={`${w.titel ? w.titel + ' · ' : ''}${w.von} · ${seit(w.am)}`}>
                {w.name}
                <button className="btn btn--sm btn--ghost" style={{ marginLeft: 4, padding: '0 4px' }}
                  aria-label={tr('Von der Whitelist nehmen')} disabled={busy !== null}
                  onClick={() => void tun(`weg-${w.name}`, async () => {
                    await api.softwareEntziehen(w.name)
                    return tr('{name} steht nicht mehr auf der Whitelist.', { name: w.name })
                  })}>×</button>
              </span>
            ))}
          </div>
        )}
      </div>
    </div>
  )
}
