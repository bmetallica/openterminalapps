import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import {
  ApiError, api, type KiNutzerDetail, type KiUebersicht, type KiVerlauf,
} from '../lib/api'
import { getLang, t as tr, useLang } from '../lib/i18n'

/**
 * Betrieb → KI-Nutzung (Handbuch Kapitel 28).
 *
 * Wer die KI wie oft anspricht — gezählt vom KI-Durchgang (ota-ki), nie mit
 * Inhalten. Oben die Übersicht je Mensch für einen wählbaren Zeitraum; ein
 * Klick auf einen Namen zeigt seine Arbeitsplätze mit einem Graphen, der sich
 * nach vorn und hinten erweitern und durch Aufziehen vergrößern lässt.
 */

const STUNDE = 3600_000
const TAG = 24 * STUNDE
const SPANNEN: [string, number][] = [['24 h', TAG], ['3 Tage', 3 * TAG], ['7 Tage', 7 * TAG], ['30 Tage', 30 * TAG]]
const TZ = Intl.DateTimeFormat().resolvedOptions().timeZone || 'UTC'

type Metrik = 'anfragen' | 'tokens'
type Zeitraum = { von: number; bis: number }

const zahl = (n: number) => n.toLocaleString(getLang() === 'en' ? 'en-US' : 'de-DE')
function kurz(n: number): string {
  if (n >= 1e9) return `${(n / 1e9).toFixed(1)} G`
  if (n >= 1e6) return `${(n / 1e6).toFixed(1)} M`
  if (n >= 1e4) return `${Math.round(n / 1e3)} k`
  return zahl(n)
}
function zeitText(ms: number, mitDatum: boolean): string {
  const d = new Date(ms)
  const loc = getLang() === 'en' ? 'en-GB' : 'de-DE'
  return mitDatum
    ? d.toLocaleString(loc, { day: '2-digit', month: '2-digit', hour: '2-digit', minute: '2-digit' })
    : d.toLocaleTimeString(loc, { hour: '2-digit', minute: '2-digit' })
}
const iso = (ms: number) => new Date(ms).toISOString()

export function KiNutzung({ onToast }: { onToast: (m: string, tone?: 'ok' | 'bad') => void }) {
  useLang()
  const [raum, setRaum] = useState<Zeitraum>(() => ({ von: Date.now() - TAG, bis: Date.now() }))
  const [daten, setDaten] = useState<KiUebersicht | null>(null)
  const [wer, setWer] = useState<string | null>(null)
  const [fehler, setFehler] = useState('')

  const laden = useCallback(async () => {
    try {
      setDaten(await api.kiNutzung(iso(raum.von), iso(raum.bis), TZ)); setFehler('')
    } catch (err) {
      setFehler(err instanceof ApiError ? err.message : tr('Hat nicht geklappt'))
    }
  }, [raum])
  useEffect(() => { if (!wer) void laden() }, [laden, wer])

  if (wer) {
    return <NutzerDetail id={wer} start={raum} onZurueck={() => setWer(null)} onToast={onToast} />
  }
  if (fehler) return <p className="note-warn">{fehler}</p>
  if (!daten) return <p className="sub">{tr('Wird geladen…')}</p>

  return (
    <div>
      {!daten.statistik && (
        <p className="note-warn" style={{ marginBottom: 14 }}>
          {tr('Die Nutzungsstatistik ist ausgeschaltet — einschalten unter Einstellungen → IDE-AI → KI-Durchgang und Nutzungsstatistik. Was schon gezählt ist, bleibt bis zu seiner Frist sichtbar.')}
        </p>
      )}
      <Zeitwahl raum={raum} onRaum={setRaum} />

      <div className="ki-kacheln">
        <Kachel wert={zahl(daten.summe.anfragen)} name={tr('Anfragen')} />
        <Kachel wert={kurz(daten.summe.ein)} name={tr('Tokens hinein')} />
        <Kachel wert={kurz(daten.summe.aus)} name={tr('Tokens heraus')} />
        <Kachel wert={zahl(daten.nutzer.filter((n) => n.bekannt).length)} name={tr('Menschen')} />
        <Kachel wert={zahl(daten.summe.fehler)} name={tr('Fehler')} />
      </div>

      <div className="panel" style={{ padding: '14px 16px', marginBottom: 18 }}>
        <Graf verlauf={daten.verlauf} raum={raum} namen={{ '': tr('Alle') }} metrik="anfragen"
          onZoom={setRaum} />
      </div>

      {daten.nutzer.length === 0 ? (
        <div className="empty">
          <p className="empty__title">{tr('In diesem Zeitraum keine Anfragen')}</p>
        </div>
      ) : (
        <div style={{ overflowX: 'auto' }}>
          <table className="tbl">
            <thead>
              <tr>
                <th>{tr('Mensch')}</th><th>{tr('Anfragen')}</th><th>{tr('Tokens hinein / heraus')}</th>
                <th>{tr('Arbeitsplätze')}</th><th>{tr('Meistes Modell')}</th><th>{tr('Verlauf')}</th>
                <th>{tr('Zuletzt')}</th>
              </tr>
            </thead>
            <tbody>
              {daten.nutzer.map((n) => (
                <tr key={n.user_id || 'unbekannt'} onClick={() => setWer(n.user_id || 'unbekannt')}>
                  <td>
                    <span className="data">{n.bekannt ? n.name : tr('nicht zuzuordnen')}</span>
                    {n.anzeigename && <div className="sub" style={{ fontSize: 12 }}>{n.anzeigename}</div>}
                  </td>
                  <td className="data">
                    {zahl(n.anfragen)}
                    {n.fehler > 0 && <span className="sub"> · {tr('{n} Fehler', { n: n.fehler })}</span>}
                    {n.verbindungen > 0 && <div className="sub" style={{ fontSize: 12 }}>
                      {tr('{n} verschlüsselt (nur Verbindungen)', { n: n.verbindungen })}</div>}
                  </td>
                  <td className="data">{kurz(n.ein)} / {kurz(n.aus)}</td>
                  <td className="data">{n.arbeitsplaetze}</td>
                  <td><span className="data">{n.modell}</span></td>
                  <td><Funke werte={n.funken} /></td>
                  <td className="sub">{zeitText(new Date(n.zuletzt).getTime(), true)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
      <p className="field__hint" style={{ marginTop: 14 }}>
        {tr('Einzelne Anfragen werden {r} Tage aufbewahrt, Stundensummen {s}. Wer die Zahlen eines Menschen öffnet, steht im Protokoll.', {
          r: daten.frist_roh, s: daten.frist_stunden ? tr('{n} Tage', { n: daten.frist_stunden }) : tr('unbegrenzt') })}
        {' '}
        <button className="btn btn--sm btn--ghost" onClick={() => {
          if (!confirm(tr('Alle gezählten KI-Anfragen löschen? Das lässt sich nicht rückgängig machen.'))) return
          void api.kiNutzungLoeschen().then((r) => {
            onToast(tr('{n} Anfragen und {s} Stundensummen gelöscht.', { n: r.anfragen, s: r.stunden }))
            void laden()
          }).catch((err) => onToast(err instanceof ApiError ? err.message : tr('Hat nicht geklappt'), 'bad'))
        }}>{tr('Alle Nutzungsdaten löschen')}</button>
      </p>
    </div>
  )
}

function Kachel({ wert, name }: { wert: string; name: string }) {
  return (
    <div className="ki-kachel">
      <div className="ki-kachel__wert">{wert}</div>
      <div className="ki-kachel__name">{name}</div>
    </div>
  )
}

/** Zeitraum wählen: feste Spannen, früher/später, eigene Grenzen. */
function Zeitwahl({ raum, onRaum }: { raum: Zeitraum; onRaum: (r: Zeitraum) => void }) {
  const spanne = raum.bis - raum.von
  const jetzt = Date.now()
  const amEnde = jetzt - raum.bis < 60_000
  const lokal = (ms: number) => {
    const d = new Date(ms - new Date(ms).getTimezoneOffset() * 60_000)
    return d.toISOString().slice(0, 16)
  }
  return (
    <div className="ki-leiste">
      <div className="seg" role="radiogroup" aria-label={tr('Zeitraum')}>
        {SPANNEN.map(([name, ms]) => (
          <button key={name} type="button" role="radio" aria-checked={amEnde && Math.abs(spanne - ms) < 60_000}
            className={`seg__opt${amEnde && Math.abs(spanne - ms) < 60_000 ? ' is-on' : ''}`}
            onClick={() => onRaum({ von: Date.now() - ms, bis: Date.now() })}>{tr(name)}</button>
        ))}
      </div>
      <button className="btn btn--sm" title={tr('Einen Tag früher beginnen')}
        onClick={() => onRaum({ von: raum.von - TAG, bis: raum.bis })}>{tr('« 1 Tag mehr')}</button>
      <button className="btn btn--sm" title={tr('Den Ausschnitt verschieben')}
        onClick={() => onRaum({ von: raum.von - spanne, bis: raum.bis - spanne })}>{tr('‹ früher')}</button>
      <button className="btn btn--sm" disabled={amEnde}
        onClick={() => {
          const bis = Math.min(jetzt, raum.bis + spanne)
          onRaum({ von: bis - spanne, bis })
        }}>{tr('später ›')}</button>
      <label className="sub" style={{ display: 'inline-flex', gap: 6, alignItems: 'center' }}>
        {tr('von')}
        <input type="datetime-local" value={lokal(raum.von)} aria-label={tr('von')}
          onChange={(ev) => { const v = new Date(ev.target.value).getTime(); if (v < raum.bis) onRaum({ ...raum, von: v }) }} />
        {tr('bis')}
        <input type="datetime-local" value={lokal(raum.bis)} aria-label={tr('bis')}
          onChange={(ev) => { const v = new Date(ev.target.value).getTime(); if (v > raum.von) onRaum({ ...raum, bis: Math.min(v, jetzt) }) }} />
      </label>
    </div>
  )
}

/** Kleine Verlaufslinie in der Tabelle. */
function Funke({ werte }: { werte: number[] }) {
  const max = Math.max(1, ...werte)
  const b = 96, h = 22
  const d = werte.map((v, i) => `${i ? 'L' : 'M'}${(i / Math.max(1, werte.length - 1)) * b},${h - 2 - (v / max) * (h - 4)}`).join('')
  return <svg className="ki-funke" width={b} height={h} aria-hidden="true"><path d={d} /></svg>
}

function NutzerDetail({ id, start, onZurueck, onToast }: {
  id: string; start: Zeitraum; onZurueck: () => void; onToast: (m: string, tone?: 'ok' | 'bad') => void
}) {
  const [raum, setRaum] = useState<Zeitraum>(start)
  const [d, setD] = useState<KiNutzerDetail | null>(null)
  const [metrik, setMetrik] = useState<Metrik>('anfragen')

  useEffect(() => {
    void api.kiNutzer(id, iso(raum.von), iso(raum.bis), TZ).then(setD)
      .catch((err) => onToast(err instanceof ApiError ? err.message : tr('Hat nicht geklappt'), 'bad'))
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [id, raum])

  const namen = useMemo(() => Object.fromEntries((d?.arbeitsplaetze ?? []).map((p) => [p.template_id, p.name])), [d])

  return (
    <div>
      <div className="ki-leiste">
        <button className="btn btn--sm" onClick={onZurueck}>{tr('← Übersicht')}</button>
        <h2 style={{ margin: 0, fontSize: 18 }}>
          {d ? (d.nutzer.name || tr('nicht zuzuordnen')) : '…'}
          {d?.nutzer.anzeigename && <span className="sub" style={{ fontSize: 14 }}> · {d.nutzer.anzeigename}</span>}
        </h2>
      </div>
      <Zeitwahl raum={raum} onRaum={setRaum} />
      {!d ? <p className="sub">{tr('Wird geladen…')}</p> : (
        <>
          <div className="panel" style={{ padding: '14px 16px', marginBottom: 18 }}>
            <div className="ki-leiste" style={{ marginBottom: 8 }}>
              <div className="seg" role="radiogroup" aria-label={tr('Größe')}>
                {(['anfragen', 'tokens'] as Metrik[]).map((m) => (
                  <button key={m} type="button" role="radio" aria-checked={metrik === m}
                    className={`seg__opt${metrik === m ? ' is-on' : ''}`} onClick={() => setMetrik(m)}>
                    {m === 'anfragen' ? tr('Anfragen') : tr('Tokens')}
                  </button>
                ))}
              </div>
              <span className="sub" style={{ fontSize: 12 }}>
                {tr('Im Graphen einen Bereich aufziehen, um ihn zu vergrößern.')}
                {d.verlauf.quelle === 'stunde' && d.verlauf.schritt === 3600 && ' ' + tr('Auflösung: Stunden.')}
                {d.verlauf.schritt === 86400 && ' ' + tr('Auflösung: Tage.')}
              </span>
            </div>
            <Graf verlauf={d.verlauf} raum={raum} namen={namen} metrik={metrik} onZoom={setRaum} />
          </div>

          <h3 className="ide-ai__abschnitt">{tr('Arbeitsplätze')}</h3>
          {d.arbeitsplaetze.length === 0 ? <p className="sub">{tr('In diesem Zeitraum keine Anfragen')}</p> : (
            <div style={{ overflowX: 'auto' }}>
              <table className="tbl ide-ai__modelle">
                <thead>
                  <tr><th>{tr('Arbeitsplatz')}</th><th>{tr('Anfragen')}</th><th>{tr('Tokens hinein / heraus')}</th>
                    <th>{tr('Mittlere Dauer')}</th><th>{tr('Zuletzt')}</th></tr>
                </thead>
                <tbody>
                  {d.arbeitsplaetze.map((p, i) => (
                    <tr key={p.template_id}>
                      <td>
                        <span className="ki-punkt" style={{ background: `var(--serie-${(i % 8) + 1})`, marginRight: 8 }} />
                        {p.name || tr('nicht zuzuordnen')}
                      </td>
                      <td className="data">
                        {zahl(p.anfragen)}
                        {p.fehler > 0 && <span className="sub"> · {tr('{n} Fehler', { n: p.fehler })}</span>}
                        {p.verbindungen > 0 && <div className="sub" style={{ fontSize: 12 }}>
                          {tr('{n} verschlüsselt (nur Verbindungen)', { n: p.verbindungen })}</div>}
                      </td>
                      <td className="data">{kurz(p.ein)} / {kurz(p.aus)}</td>
                      <td className="data">{(p.dauer_mittel_ms / 1000).toLocaleString(getLang() === 'en' ? 'en-US' : 'de-DE', { maximumFractionDigits: 1 })} s</td>
                      <td className="sub">{zeitText(new Date(p.zuletzt).getTime(), true)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}

          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(280px, 1fr))', gap: 18, marginTop: 8 }}>
            <div>
              <h3 className="ide-ai__abschnitt">{tr('Modelle')}</h3>
              <table className="tbl ide-ai__modelle">
                <tbody>
                  {d.modelle.map((m) => (
                    <tr key={m.server + m.modell}>
                      <td><span className="data">{m.modell}</span> <span className="sub">({m.server})</span></td>
                      <td className="data">{zahl(m.anfragen)}</td>
                      <td className="data sub">{kurz(m.ein + m.aus)} {tr('Tokens')}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            <div>
              <h3 className="ide-ai__abschnitt">{tr('Werkzeuge')}</h3>
              {d.werkzeuge.length === 0 ? (
                <p className="sub">{tr('Nur für die letzten {n} Tage (einzelne Anfragen).', { n: d.frist_roh })}</p>
              ) : (
                <table className="tbl ide-ai__modelle">
                  <tbody>
                    {d.werkzeuge.map((w) => (
                      <tr key={w.werkzeug}><td>{werkzeugName(w.werkzeug)}</td><td className="data">{zahl(w.anfragen)}</td></tr>
                    ))}
                  </tbody>
                </table>
              )}
            </div>
          </div>
        </>
      )}
    </div>
  )
}

function werkzeugName(w: string): string {
  switch (w) {
    case 'opencode': return 'opencode'
    case 'continue': return tr('Continue (IDE-AI)')
    case 'skript': return tr('Skript / Kommandozeile')
    case 'tls': return tr('verschlüsselt (nur Verbindungen)')
    default: return tr('sonstiges')
  }
}

/**
 * Linien je Reihe über der Zeit, mit Fadenkreuz und Tipp beim Überfahren und
 * Vergrößern durch Aufziehen. Eine Achse; Lücken sind Nullen, keine fehlenden
 * Werte — wer nichts fragt, fragt null Mal.
 */
function Graf({ verlauf, raum, namen, metrik, onZoom }: {
  verlauf: KiVerlauf; raum: Zeitraum; namen: Record<string, string>; metrik: Metrik
  onZoom: (r: Zeitraum) => void
}) {
  const box = useRef<HTMLDivElement>(null)
  const [breite, setBreite] = useState(800)
  const [zeig, setZeig] = useState<number | null>(null)
  const [zug, setZug] = useState<[number, number] | null>(null)
  useEffect(() => {
    if (!box.current) return
    const ro = new ResizeObserver(([e]) => setBreite(Math.max(280, e.contentRect.width)))
    ro.observe(box.current)
    return () => ro.disconnect()
  }, [])

  const H = 220, L = 46, R = 12, O = 10, U = 26
  const schritt = verlauf.schritt * 1000

  // Das Raster: jeder Eimer im Zeitraum, auch die leeren.
  const eimer = useMemo(() => {
    const raus: number[] = []
    const alle = Object.values(verlauf.reihen).flat().map((p) => new Date(p[0]).getTime())
    if (schritt >= TAG) {
      // Tage: lokale Mitternacht bis Mitternacht.
      const d = new Date(raum.von); d.setHours(0, 0, 0, 0)
      for (let t = d.getTime(); t < raum.bis; ) {
        raus.push(t); const n = new Date(t); n.setDate(n.getDate() + 1); t = n.getTime()
      }
    } else {
      for (let t = Math.floor(raum.von / schritt) * schritt; t < raum.bis; t += schritt) raus.push(t)
    }
    for (const t of alle) if (!raus.includes(t)) raus.push(t)
    return raus.sort((a, b) => a - b)
  }, [verlauf, raum, schritt])

  const reihen = useMemo(() => Object.keys(verlauf.reihen).sort((a, b) =>
    (namen[a] ?? a).localeCompare(namen[b] ?? b)).map((k, i) => {
    const werte = new Map(verlauf.reihen[k].map((p) => [new Date(p[0]).getTime(), metrik === 'anfragen' ? p[1] : p[2]]))
    return { k, farbe: `var(--serie-${(i % 8) + 1})`, name: namen[k] ?? (k ? k.slice(0, 8) : tr('nicht zuzuordnen')),
      werte: eimer.map((t) => werte.get(t) ?? 0) }
  }), [verlauf, eimer, metrik, namen])

  const max = Math.max(1, ...reihen.flatMap((r) => r.werte))
  // Gezählt wird ganz: Bei kleinen Zahlen keine Viertel an der Achse.
  const oben = max <= 4 ? 4 : (() => {
    const p = 10 ** Math.floor(Math.log10(max))
    for (const f of [1, 2, 4, 5, 10]) if (f * p >= max) return f * p
    return 10 * p
  })()
  const x = (t: number) => L + ((t - raum.von) / Math.max(1, raum.bis - raum.von)) * (breite - L - R)
  const y = (v: number) => O + (1 - v / oben) * (H - O - U)
  const tZu = (px: number) => raum.von + ((px - L) / (breite - L - R)) * (raum.bis - raum.von)
  const mitDatum = raum.bis - raum.von > TAG * 1.05
  const ticks = 6

  function nahe(px: number): number | null {
    if (!eimer.length) return null
    const t = tZu(px)
    let best = 0
    for (let i = 1; i < eimer.length; i++) if (Math.abs(eimer[i] - t) < Math.abs(eimer[best] - t)) best = i
    return best
  }
  const px = (ev: React.MouseEvent) => ev.clientX - (box.current?.getBoundingClientRect().left ?? 0)

  return (
    <div className="ki-graf" ref={box}
      onMouseMove={(ev) => { const p = px(ev); setZeig(nahe(p)); if (zug) setZug([zug[0], p]) }}
      onMouseLeave={() => { setZeig(null); setZug(null) }}
      onMouseDown={(ev) => { const p = px(ev); setZug([p, p]) }}
      onMouseUp={() => {
        if (zug && Math.abs(zug[1] - zug[0]) > 8) {
          const a = tZu(Math.min(...zug)), b = tZu(Math.max(...zug))
          if (b - a > 10 * 60_000) onZoom({ von: Math.max(raum.von, a), bis: Math.min(raum.bis, b) })
        }
        setZug(null)
      }}>
      <svg height={H} viewBox={`0 0 ${breite} ${H}`} role="img"
        aria-label={tr('Verlauf der KI-Anfragen')}>
        {[0, 0.25, 0.5, 0.75, 1].map((f) => (
          <g key={f}>
            <line className="ki-graf__gitter" x1={L} x2={breite - R} y1={y(oben * f)} y2={y(oben * f)} />
            <text className="ki-graf__achse" x={L - 6} y={y(oben * f) + 4} textAnchor="end">{kurz(oben * f)}</text>
          </g>
        ))}
        {Array.from({ length: ticks + 1 }, (_, i) => raum.von + (i / ticks) * (raum.bis - raum.von)).map((t, i) => (
          <text key={i} className="ki-graf__achse" x={x(t)} y={H - 8}
            textAnchor={i === 0 ? 'start' : i === ticks ? 'end' : 'middle'}>{zeitText(t, mitDatum)}</text>
        ))}
        {reihen.map((r) => (
          <path key={r.k} className="ki-graf__linie" stroke={r.farbe}
            d={r.werte.map((v, i) => `${i ? 'L' : 'M'}${x(eimer[i]).toFixed(1)},${y(v).toFixed(1)}`).join('')} />
        ))}
        {zeig !== null && eimer[zeig] !== undefined && (
          <g>
            <line className="ki-graf__fahne" x1={x(eimer[zeig])} x2={x(eimer[zeig])} y1={O} y2={H - U} />
            {reihen.map((r) => (
              <circle key={r.k} cx={x(eimer[zeig])} cy={y(r.werte[zeig])} r={4} fill={r.farbe}
                stroke="var(--bay)" strokeWidth={2} />
            ))}
          </g>
        )}
        {zug && Math.abs(zug[1] - zug[0]) > 2 && (
          <rect className="ki-graf__auswahl" x={Math.min(...zug)} y={O} width={Math.abs(zug[1] - zug[0])} height={H - O - U} />
        )}
      </svg>
      {zeig !== null && eimer[zeig] !== undefined && !zug && (
        <div className="ki-graf__tipp" style={{
          left: Math.min(x(eimer[zeig]) + 12, breite - 180), top: 8,
        }}>
          <b>{zeitText(eimer[zeig], true)}{schritt < TAG ? ` – ${zeitText(eimer[zeig] + schritt, false)}` : ''}</b>
          {reihen.map((r) => (
            <div key={r.k} className="ki-graf__zeile">
              <span><span className="ki-punkt" style={{ background: r.farbe, marginRight: 6 }} />{r.name}</span>
              <span className="data">{zahl(r.werte[zeig])}</span>
            </div>
          ))}
        </div>
      )}
      {reihen.length > 1 && (
        <div className="ki-legende">
          {reihen.map((r) => (
            <span key={r.k}><span className="ki-punkt" style={{ background: r.farbe }} />{r.name}</span>
          ))}
        </div>
      )}
      {reihen.length === 0 && <p className="sub" style={{ position: 'absolute', top: 80, width: '100%', textAlign: 'center' }}>
        {tr('In diesem Zeitraum keine Anfragen')}</p>}
    </div>
  )
}
