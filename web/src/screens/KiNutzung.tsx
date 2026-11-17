import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import {
  ApiError, api, type KiAnonym, type KiAuskunft, type KiBenannt, type KiNutzerDetail,
  type KiUebersicht, type KiVerlauf,
} from '../lib/api'
import { getLang, t as tr, useLang } from '../lib/i18n'

/**
 * Betrieb → KI-Nutzung (Handbuch Kapitel 28).
 *
 * Wer die KI wie oft anspricht — gezählt vom KI-Durchgang (ota-ki), nie mit
 * Inhalten. Die Seite zeigt zuerst nur, was ohne Namen geht: Summen, Verlauf,
 * Anteile je Mensch und Arbeitsplatz nach Rang („Person 1“ ist im gewählten
 * Zeitraum und Maß die grösste, nicht immer dieselbe), Vorlagen, Modelle,
 * Tageszeiten. Namen und Einzelverläufe gibt es erst nach einer Begründung,
 * die im Prüfprotokoll landet (routers/ki_nutzung.py).
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
  const [metrik, setMetrik] = useState<Metrik>('anfragen')
  const [daten, setDaten] = useState<KiAnonym | null>(null)
  const [fehler, setFehler] = useState('')
  // Die Auskunft lebt nur hier im Speicher: Wer die Seite neu lädt oder
  // verlässt, muss wieder begründen.
  const [auskunft, setAuskunft] = useState<KiAuskunft | null>(null)
  const [wer, setWer] = useState<string | null>(null)

  const laden = useCallback(async () => {
    try {
      setDaten(await api.kiNutzung(iso(raum.von), iso(raum.bis), TZ)); setFehler('')
    } catch (err) {
      setFehler(err instanceof ApiError ? err.message : tr('Hat nicht geklappt'))
    }
  }, [raum])
  useEffect(() => { if (!wer) void laden() }, [laden, wer])

  // Abgelaufen ist abgelaufen — auch ohne dass jemand klickt.
  useEffect(() => {
    if (!auskunft) return
    const rest = new Date(auskunft.bis).getTime() - Date.now()
    const t = setTimeout(() => {
      setAuskunft(null); setWer(null)
      onToast(tr('Die Auskunft ist abgelaufen.'))
    }, Math.max(0, rest))
    return () => clearTimeout(t)
  }, [auskunft, onToast])

  const beenden = useCallback(() => { setAuskunft(null); setWer(null) }, [])
  const abgelehnt = useCallback((err: unknown) => {
    if (err instanceof ApiError && err.status === 403) beenden()
    onToast(err instanceof ApiError ? err.message : tr('Hat nicht geklappt'), 'bad')
  }, [beenden, onToast])

  if (wer && auskunft) {
    return (
      <div>
        <AuskunftLeiste auskunft={auskunft} onBeenden={beenden} />
        <NutzerDetail id={wer} merkmal={auskunft.merkmal} start={raum} onZurueck={() => setWer(null)}
          onFehler={abgelehnt} />
      </div>
    )
  }
  if (fehler) return <p className="note-warn">{fehler}</p>
  if (!daten) return <p className="sub">{tr('Wird geladen…')}</p>

  const wert = (x: { anfragen: number; tokens: number }) => metrik === 'anfragen' ? x.anfragen : x.tokens
  const nachRang = (liste: { anfragen: number; tokens: number }[], name: string) =>
    [...liste].sort((x, y) => wert(y) - wert(x)).map((x, i) => ({ name: tr(name, { n: i + 1 }), wert: wert(x) }))
  const benannt = (liste: KiBenannt[], leer: string) =>
    [...liste].sort((x, y) => wert(y) - wert(x)).map((x) => ({ name: x.name || tr(leer), wert: wert(x) }))
  const ohne = wert(daten.nicht_zuzuordnen)

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
        <Kachel wert={zahl(daten.summe.personen)} name={tr('Menschen')} />
        <Kachel wert={zahl(daten.summe.arbeitsplaetze)} name={tr('Arbeitsplätze')} />
        <Kachel wert={`${(daten.summe.dauer_mittel_ms / 1000).toLocaleString(getLang() === 'en' ? 'en-US' : 'de-DE', { maximumFractionDigits: 1 })} s`}
          name={tr('Mittlere Dauer')} />
        <Kachel wert={zahl(daten.summe.fehler)} name={tr('Fehler')} />
      </div>

      <div className="ki-leiste" style={{ marginBottom: 10 }}>
        <div className="seg" role="radiogroup" aria-label={tr('Größe')}>
          {(['anfragen', 'tokens'] as Metrik[]).map((m) => (
            <button key={m} type="button" role="radio" aria-checked={metrik === m}
              className={`seg__opt${metrik === m ? ' is-on' : ''}`} onClick={() => setMetrik(m)}>
              {m === 'anfragen' ? tr('Anfragen') : tr('Tokens')}
            </button>
          ))}
        </div>
        <span className="sub" style={{ fontSize: 12 }}>
          {tr('Ohne Namen: Menschen und Arbeitsplätze erscheinen nur nach ihrem Rang im gewählten Zeitraum.')}
        </span>
      </div>

      <div className="panel" style={{ padding: '14px 16px', marginBottom: 18 }}>
        <h3 className="ki-titel">{metrik === 'anfragen' ? tr('Anfragen im Verlauf') : tr('Tokens im Verlauf')}</h3>
        <Graf verlauf={daten.verlauf} raum={raum} namen={{ '': tr('Alle') }} metrik={metrik} onZoom={setRaum} />
      </div>

      <div className="ki-torten">
        <Torte titel={tr('Je Mensch')} metrik={metrik}
          teile={daten.personen.length ? nachRang(daten.personen, 'Person {n}') : []}
          rest={ohne ? { name: tr('nicht zuzuordnen'), wert: ohne } : undefined}
          leer={daten.summe.personen > 0
            ? tr('Erst ab {n} Menschen im Zeitraum — bei weniger wäre erkennbar, wer wer ist.', { n: daten.mindestens })
            : undefined} />
        <Torte titel={tr('Je Arbeitsplatz')} metrik={metrik}
          teile={daten.arbeitsplaetze.length ? nachRang(daten.arbeitsplaetze, 'Arbeitsplatz {n}') : []}
          leer={daten.summe.arbeitsplaetze > 0
            ? tr('Erst ab {n} Arbeitsplätzen im Zeitraum — bei weniger wäre erkennbar, wem welcher gehört.', { n: daten.mindestens })
            : undefined} />
        <Torte titel={tr('Je Vorlage')} metrik={metrik} teile={benannt(daten.vorlagen, 'nicht zuzuordnen')} />
        <Torte titel={tr('Je Modell')} metrik={metrik} teile={benannt(daten.modelle, 'unbekannt')} />
        {daten.server.length > 1 && (
          <Torte titel={tr('Je KI-Server')} metrik={metrik} teile={benannt(daten.server, 'unbekannt')} />
        )}
      </div>

      <div className="panel" style={{ padding: '14px 16px', marginBottom: 18 }}>
        <h3 className="ki-titel">{tr('Nach Tageszeit')}</h3>
        <Tageszeit werte={daten.tageszeit.map(wert)} metrik={metrik} />
      </div>

      {auskunft ? (
        <Personen auskunft={auskunft} raum={raum} onBeenden={beenden} onWer={setWer} onFehler={abgelehnt} />
      ) : (
        <AuskunftMaske onAuskunft={setAuskunft} onToast={onToast} />
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

/** Die Maske vor den Namen: ohne Begründung keine personenbezogenen Zahlen. */
function AuskunftMaske({ onAuskunft, onToast }: {
  onAuskunft: (a: KiAuskunft) => void; onToast: (m: string, tone?: 'ok' | 'bad') => void
}) {
  const [grund, setGrund] = useState('')
  const [busy, setBusy] = useState(false)
  const genug = grund.trim().length >= 10
  return (
    <div className="panel ki-maske">
      <h3 className="ki-titel">{tr('Personenbezogene Auskunft')}</h3>
      <p className="sub" style={{ margin: '0 0 10px' }}>
        {tr('Namen, einzelne Arbeitsplätze und ihr Verlauf erscheinen erst nach einer Begründung. Sie steht mit deinem Namen im Prüfprotokoll; die Auskunft gilt 30 Minuten und nur in diesem Fenster.')}
      </p>
      <textarea className="input" rows={3} maxLength={500} value={grund}
        aria-label={tr('Begründung für die Auskunft')}
        placeholder={tr('z. B. Ticket 4711: ungewöhnlich viele Fehler, Ursache klären; Kostenumlage Q3 nach Betriebsvereinbarung')}
        onChange={(e) => setGrund(e.target.value)} />
      <div className="ki-leiste" style={{ margin: '10px 0 0' }}>
        <button className="btn btn--primary" disabled={!genug || busy} onClick={() => {
          setBusy(true)
          api.kiAuskunft(grund.trim()).then((a) => { onAuskunft(a); setGrund('') })
            .catch((err) => onToast(err instanceof ApiError ? err.message : tr('Hat nicht geklappt'), 'bad'))
            .finally(() => setBusy(false))
        }}>{tr('Auskunft öffnen')}</button>
        {!genug && <span className="sub" style={{ fontSize: 12 }}>{tr('Mindestens 10 Zeichen.')}</span>}
      </div>
    </div>
  )
}

function AuskunftLeiste({ auskunft, onBeenden }: { auskunft: KiAuskunft; onBeenden: () => void }) {
  return (
    <div className="note-warn ki-auskunft">
      <span>
        <b>{tr('Auskunft offen bis {z}', { z: zeitText(new Date(auskunft.bis).getTime(), false) })}</b>
        {' · '}{tr('Grund')}: {auskunft.grund}
        <span className="sub"> · {tr('Vorgang')} {auskunft.vorgang}</span>
      </span>
      <button className="btn btn--sm" onClick={onBeenden}>{tr('Auskunft beenden')}</button>
    </div>
  )
}

/** Die alte Übersicht mit Namen — nur mit Auskunft. */
function Personen({ auskunft, raum, onBeenden, onWer, onFehler }: {
  auskunft: KiAuskunft; raum: Zeitraum; onBeenden: () => void; onWer: (id: string) => void
  onFehler: (err: unknown) => void
}) {
  const [d, setD] = useState<KiUebersicht | null>(null)
  useEffect(() => {
    void api.kiPersonen(auskunft.merkmal, iso(raum.von), iso(raum.bis), TZ).then(setD).catch(onFehler)
  }, [auskunft, raum, onFehler])
  return (
    <div className="panel ki-maske">
      <AuskunftLeiste auskunft={auskunft} onBeenden={onBeenden} />
      {!d ? <p className="sub">{tr('Wird geladen…')}</p> : d.nutzer.length === 0 ? (
        <div className="empty"><p className="empty__title">{tr('In diesem Zeitraum keine Anfragen')}</p></div>
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
              {d.nutzer.map((n) => (
                <tr key={n.user_id || 'unbekannt'} onClick={() => onWer(n.user_id || 'unbekannt')}>
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
    </div>
  )
}

type Stueck = { name: string; wert: number }

/**
 * Ringdiagramm: höchstens sieben Stücke, der Rest als „Übrige“. Farben in
 * fester Reihenfolge nach Rang; „nicht zuzuordnen“ grau, weil es kein
 * Mitglied der Reihe ist. Daneben die Legende mit Wert und Anteil — die
 * Farbe ist nie die einzige Auskunft.
 */
function Torte({ titel, teile, rest, leer, metrik }: {
  titel: string; teile: Stueck[]; rest?: Stueck; leer?: string; metrik: Metrik
}) {
  const [zeig, setZeig] = useState<number | null>(null)
  const stuecke = useMemo(() => {
    const positiv = teile.filter((x) => x.wert > 0)
    const raus: (Stueck & { farbe: string })[] = positiv.slice(0, 7)
      .map((x, i) => ({ ...x, farbe: `var(--serie-${i + 1})` }))
    if (positiv.length > 7) {
      raus.push({ name: tr('Übrige ({n})', { n: positiv.length - 7 }),
        wert: positiv.slice(7).reduce((a, x) => a + x.wert, 0), farbe: 'var(--serie-8)' })
    }
    if (rest && rest.wert > 0 && raus.length) raus.push({ ...rest, farbe: 'var(--mute)' })
    return raus
  }, [teile, rest])
  const summe = stuecke.reduce((a, x) => a + x.wert, 0)
  const R = 62, r = 40, M = 70

  let winkel = -Math.PI / 2
  const boegen = stuecke.map((x) => {
    const w = (x.wert / Math.max(1, summe)) * Math.PI * 2
    const a0 = winkel, a1 = winkel + w
    winkel = a1
    if (stuecke.length === 1) return `M${M},${M - R}A${R},${R} 0 1 1 ${M - 0.01},${M - R}Z M${M},${M - r}A${r},${r} 0 1 0 ${M + 0.01},${M - r}Z`
    const gross = w > Math.PI ? 1 : 0
    const p = (rad: number, a: number) => `${(M + rad * Math.cos(a)).toFixed(2)},${(M + rad * Math.sin(a)).toFixed(2)}`
    return `M${p(R, a0)}A${R},${R} 0 ${gross} 1 ${p(R, a1)}L${p(r, a1)}A${r},${r} 0 ${gross} 0 ${p(r, a0)}Z`
  })
  const anteil = (v: number) => `${((v / Math.max(1, summe)) * 100).toLocaleString(getLang() === 'en' ? 'en-US' : 'de-DE', { maximumFractionDigits: 1 })} %`

  return (
    <div className="panel ki-torte">
      <h3 className="ki-titel">{titel}</h3>
      {!stuecke.length ? (
        <p className="sub" style={{ fontSize: 13 }}>{leer ?? tr('In diesem Zeitraum keine Anfragen')}</p>
      ) : (
        <div className="ki-torte__inhalt">
          <svg width={M * 2} height={M * 2} viewBox={`0 0 ${M * 2} ${M * 2}`} role="img"
            aria-label={`${titel}: ${stuecke.map((x) => `${x.name} ${anteil(x.wert)}`).join(', ')}`}
            onMouseLeave={() => setZeig(null)}>
            {boegen.map((d, i) => (
              <path key={i} d={d} fill={stuecke[i].farbe} fillRule="evenodd" className="ki-torte__stueck"
                stroke="var(--bay)" strokeWidth={2} opacity={zeig === null || zeig === i ? 1 : 0.35}
                onMouseEnter={() => setZeig(i)} />
            ))}
            <text x={M} y={M - 2} textAnchor="middle" className="ki-torte__mitte">
              {zeig === null ? kurz(summe) : anteil(stuecke[zeig].wert)}
            </text>
            <text x={M} y={M + 14} textAnchor="middle" className="ki-graf__achse">
              {zeig === null ? (metrik === 'anfragen' ? tr('Anfragen') : tr('Tokens')) : kurz(stuecke[zeig].wert)}
            </text>
          </svg>
          <ul className="ki-torte__legende" onMouseLeave={() => setZeig(null)}>
            {stuecke.map((x, i) => (
              <li key={x.name} className={zeig === i ? 'is-on' : ''} onMouseEnter={() => setZeig(i)}>
                <span className="ki-punkt" style={{ background: x.farbe }} />
                <span className="ki-torte__name" title={x.name}>{x.name}</span>
                <span className="data">{kurz(x.wert)}</span>
                <span className="sub data">{anteil(x.wert)}</span>
              </li>
            ))}
          </ul>
        </div>
      )}
    </div>
  )
}

/** Säulen je Stunde des Tages, über den ganzen Zeitraum zusammengezählt. */
function Tageszeit({ werte, metrik }: { werte: number[]; metrik: Metrik }) {
  const box = useRef<HTMLDivElement>(null)
  const [breite, setBreite] = useState(800)
  const [zeig, setZeig] = useState<number | null>(null)
  useEffect(() => {
    if (!box.current) return
    const ro = new ResizeObserver(([e]) => setBreite(Math.max(280, e.contentRect.width)))
    ro.observe(box.current)
    return () => ro.disconnect()
  }, [])
  const H = 160, L = 46, R = 8, O = 8, U = 22
  const max = Math.max(1, ...werte)
  const oben = max <= 4 ? 4 : (() => {
    const p = 10 ** Math.floor(Math.log10(max))
    for (const f of [1, 2, 4, 5, 10]) if (f * p >= max) return f * p
    return 10 * p
  })()
  const feld = (breite - L - R) / 24
  const y = (v: number) => O + (1 - v / oben) * (H - O - U)
  const stunde = (h: number) => `${String(h).padStart(2, '0')}`
  if (!werte.some((v) => v > 0)) return <p className="sub">{tr('In diesem Zeitraum keine Anfragen')}</p>
  return (
    <div className="ki-graf" ref={box} onMouseLeave={() => setZeig(null)}>
      <svg height={H} viewBox={`0 0 ${breite} ${H}`} role="img" aria-label={tr('Nach Tageszeit')}>
        {[0, 0.5, 1].map((f) => (
          <g key={f}>
            <line className="ki-graf__gitter" x1={L} x2={breite - R} y1={y(oben * f)} y2={y(oben * f)} />
            <text className="ki-graf__achse" x={L - 6} y={y(oben * f) + 4} textAnchor="end">{kurz(oben * f)}</text>
          </g>
        ))}
        {werte.map((v, h) => {
          const x = L + h * feld + 2, b = Math.max(2, feld - 4), top = y(v), hoch = H - U - top
          return (
            <g key={h} onMouseEnter={() => setZeig(h)}>
              <rect x={L + h * feld} y={O} width={feld} height={H - O - U} fill="transparent" />
              {v > 0 && (
                <path fill="var(--serie-1)" opacity={zeig === null || zeig === h ? 1 : 0.45}
                  d={hoch > 4
                    ? `M${x},${H - U}V${top + 4}Q${x},${top} ${x + 4},${top}H${x + b - 4}Q${x + b},${top} ${x + b},${top + 4}V${H - U}Z`
                    : `M${x},${H - U}V${top}H${x + b}V${H - U}Z`} />
              )}
              {h % 3 === 0 && (
                <text className="ki-graf__achse" x={x + b / 2} y={H - 6} textAnchor="middle">{stunde(h)}</text>
              )}
            </g>
          )
        })}
      </svg>
      {zeig !== null && (
        <div className="ki-graf__tipp" style={{ left: Math.min(L + zeig * feld + feld, breite - 170), top: 8 }}>
          <b>{tr('{a}–{b} Uhr', { a: stunde(zeig), b: stunde((zeig + 1) % 24) })}</b>
          <div className="ki-graf__zeile">
            <span>{metrik === 'anfragen' ? tr('Anfragen') : tr('Tokens')}</span>
            <span className="data">{zahl(werte[zeig])}</span>
          </div>
        </div>
      )}
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

function NutzerDetail({ id, merkmal, start, onZurueck, onFehler }: {
  id?: string; merkmal?: string; start: Zeitraum; onZurueck?: () => void; onFehler: (err: unknown) => void
}) {
  // Ohne Kennung: die eigenen Zahlen (Seitenleiste → Meine KI-Nutzung).
  const eigen = id === undefined
  const [raum, setRaum] = useState<Zeitraum>(start)
  const [d, setD] = useState<KiNutzerDetail | null>(null)
  const [metrik, setMetrik] = useState<Metrik>('anfragen')

  useEffect(() => {
    void (eigen ? api.kiMeine(iso(raum.von), iso(raum.bis), TZ)
      : api.kiNutzer(merkmal ?? '', id, iso(raum.von), iso(raum.bis), TZ)).then(setD).catch(onFehler)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [id, merkmal, raum, eigen])

  const namen = useMemo(() => Object.fromEntries((d?.arbeitsplaetze ?? []).map((p) => [p.template_id, p.name])), [d])

  return (
    <div>
      {!eigen && (
        <div className="ki-leiste">
          <button className="btn btn--sm" onClick={onZurueck}>{tr('← Übersicht')}</button>
          <h2 style={{ margin: 0, fontSize: 18 }}>
            {d ? (d.nutzer.name || tr('nicht zuzuordnen')) : '…'}
            {d?.nutzer.anzeigename && <span className="sub" style={{ fontSize: 14 }}> · {d.nutzer.anzeigename}</span>}
          </h2>
        </div>
      )}
      <Zeitwahl raum={raum} onRaum={setRaum} />
      {!d ? <p className="sub">{tr('Wird geladen…')}</p> : (
        <>
          {(() => {
            const s = d.arbeitsplaetze.reduce((a, p) => ({ anfragen: a.anfragen + p.anfragen,
              ein: a.ein + p.ein, aus: a.aus + p.aus, fehler: a.fehler + p.fehler }),
            { anfragen: 0, ein: 0, aus: 0, fehler: 0 })
            return (
              <div className="ki-kacheln">
                <Kachel wert={zahl(s.anfragen)} name={tr('Anfragen')} />
                <Kachel wert={kurz(s.ein)} name={tr('Tokens hinein')} />
                <Kachel wert={kurz(s.aus)} name={tr('Tokens heraus')} />
                <Kachel wert={zahl(d.arbeitsplaetze.length)} name={tr('Arbeitsplätze')} />
                <Kachel wert={zahl(s.fehler)} name={tr('Fehler')} />
              </div>
            )
          })()}
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

/** Seitenleiste → Meine KI-Nutzung: die eigenen Zahlen, ohne Begründung. */
export function MeineKiNutzung({ onToast }: { onToast: (m: string, tone?: 'ok' | 'bad') => void }) {
  useLang()
  const [start] = useState<Zeitraum>(() => ({ von: Date.now() - TAG, bis: Date.now() }))
  const fehler = useCallback((err: unknown) =>
    onToast(err instanceof ApiError ? err.message : tr('Hat nicht geklappt'), 'bad'), [onToast])
  return (
    <div className="wrap">
      <header className="topbar">
        <div>
          <p className="silk" style={{ marginBottom: 6 }}>{tr('Deine eigenen Zahlen')}</p>
          <h1 className="h-page">{tr('Meine KI-Nutzung')}</h1>
        </div>
      </header>
      <p className="sub" style={{ marginTop: 0 }}>
        {tr('Wie oft deine Arbeitsplätze die KI angesprochen haben — gezählt ohne Inhalte. Was genau erfasst wird und wie lange, steht unter „DSGVO“.')}
      </p>
      <NutzerDetail start={start} onFehler={fehler} />
    </div>
  )
}

function werkzeugName(w: string): string {
  if (w.startsWith('x:')) return tr('Externer Dienst ({k})', { k: w.slice(2) })
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
