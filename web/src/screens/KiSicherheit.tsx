import { useCallback, useEffect, useState } from 'react'
import { Segmented } from '../components/controls'
import { ApiError, api, type KiSicherheitStand, type KiSicherheitStatistik } from '../lib/api'
import { getLang, t as tr, useLang } from '../lib/i18n'
import { GitGeheimnisseSicht } from './GitGeheimnisse'

/**
 * Sicherheit: zwei Bereiche auf einer Seite.
 *
 * * **KI-Durchgang** (Handbuch Kapitel 41): Was der KI-Durchgang an Prompt
 *   Injection erkannt hat.
 * * **OTA-Git** (Kapitel 27): Geheimnisse, die beim Push erkannt wurden
 *   (GitGeheimnisse.tsx).
 *
 * Gezeigt wird nur, was gezählt wird: Fälle je Tag, Typ, Stufe, Aktion,
 * Anwendung und Herkunft. Kein Inhalt, keine Person, kein Arbeitsplatz —
 * deshalb ohne Auskunft und Begründung wie bei der KI-Nutzung.
 */

const SPANNEN: [string, number][] = [['24 h', 1], ['7 Tage', 7], ['30 Tage', 30], ['90 Tage', 90], ['1 Jahr', 365]]

/** Was ein Falltyp bedeutet — die Erklärung für Verwaltung und Datenschutz. */
const TYPEN: Record<string, { name: string; text: string }> = {
  'tag-zeichen': { name: 'Unsichtbare Tag-Zeichen', text: 'Unicode-Zeichen aus dem Bereich U+E0000, die ein Mensch nicht sieht, das Modell aber als Text liest („ASCII Smuggling“). In Code und Dokumenten kommen sie nicht vor.' },
  'richtungszeichen': { name: 'Steuerzeichen für die Schreibrichtung', text: 'Drehen die Anzeige von Text um. Was ein Mensch liest, ist dann etwas anderes als das, was beim Modell ankommt.' },
  'nullbreite': { name: 'Ketten von Zeichen ohne Breite', text: 'Drei und mehr unsichtbare Zeichen hintereinander, ein bekanntes Mittel, Nachrichten zu verstecken.' },
  'anweisungen-ignorieren': { name: 'Aufforderung, Anweisungen zu ignorieren', text: '„Ignoriere alle vorherigen Anweisungen …“: der Klassiker, um die Vorgaben des Assistenten auszuhebeln.' },
  'rollenwechsel': { name: 'Rollenwechsel', text: 'Versuch, den Assistenten zu einer anderen Rolle ohne Regeln zu machen („du bist jetzt … ohne Einschränkungen“, Entwicklermodus).' },
  'falscher-systemprompt': { name: 'Gefälschter Systemprompt', text: 'Steuerzeichen oder Überschriften, mit denen Text so tut, als käme er vom System statt aus einer Datei.' },
  'an-den-assistenten': { name: 'Nachricht an die KI', text: 'Text, der sich ausdrücklich an einen KI-Assistenten richtet („Hinweis an die KI: …“). In einem Dokument für Menschen ist das ein starkes Zeichen.' },
  'geheimhaltung': { name: 'Geheimhaltung vor dem Nutzer', text: 'Aufforderung, etwas vor dem Menschen zu verbergen („sag dem Nutzer nichts“). Legitime Inhalte verlangen das nie.' },
  'geheimnisse-senden': { name: 'Versand von Zugangsdaten', text: 'Befehle oder Aufforderungen, Schlüssel, Passwörter oder Tokens an eine Adresse zu schicken.' },
  'bild-abfluss': { name: 'Datenabfluss über ein Bild', text: 'Ein Bild, dessen Adresse Daten mitnimmt. Zeigt eine Oberfläche es an, gehen die Daten an fremde Server.' },
  'versteckter-kommentar': { name: 'Versteckter Kommentar', text: 'Ein HTML-Kommentar mit Anweisungen an eine KI. In der gerenderten Ansicht unsichtbar, im Text für das Modell lesbar.' },
  'modell-anweisung': { name: 'Modell: Anweisung an den Assistenten', text: 'Das Prüfmodell hat eine Anweisung an den Assistenten erkannt, auch wenn kein bekanntes Muster passte.' },
  'modell-datenabfluss': { name: 'Modell: Datenabfluss', text: 'Das Prüfmodell hat den Versuch erkannt, Daten nach außen zu bringen.' },
  'modell-rollenwechsel': { name: 'Modell: Rollenwechsel', text: 'Das Prüfmodell hat den Versuch erkannt, die Rolle des Assistenten zu ändern.' },
  'modell-verschleierung': { name: 'Modell: Verschleierung', text: 'Das Prüfmodell hat versteckte oder verschleierte Anweisungen erkannt.' },
  'modell-sonstiges': { name: 'Modell: Sonstiges', text: 'Das Prüfmodell hält den Inhalt für eine Injection, ohne sie einem Typ zuzuordnen.' },
}
const STUFEN: Record<string, string> = { unsichtbar: 'Stufe 1', muster: 'Stufe 2', modell: 'Stufe 3' }
const AKTIONEN: Record<string, string> = { entfernt: 'entfernt', gezaehlt: 'gezählt', gewarnt: 'gewarnt', gesperrt: 'gesperrt' }
const FEHLER: Record<string, string> = {
  zeitueberschreitung: 'Modell antwortete nicht rechtzeitig',
  'nicht-erreichbar': 'KI-Server nicht erreichbar',
  unklar: 'Antwort des Modells nicht lesbar',
  'kein-modell': 'Kein Prüfmodell erreichbar',
  'interner-fehler': 'Fehler in der Prüfung',
}
const HINWEISE: Record<string, string> = {
  gekuerzt: 'Sehr lange Inhalte nur teilweise vom Modell geprüft',
  uebersprungen: 'Prüfungen übersprungen, weil zu viele warteten',
}

export const zahl = (n: number) => n.toLocaleString(getLang() === 'en' ? 'en-US' : 'de-DE')

export function KiSicherheit({ onToast, onEinstellungen }: {
  onToast: (m: string, tone?: 'ok' | 'bad') => void
  onEinstellungen: (abschnitt: string) => void
}) {
  useLang()
  const [tage, setTage] = useState(30)
  const [bereich, setBereich] = useState<'ki' | 'git'>(() => {
    try { return localStorage.getItem('ota.sicherheit.bereich') === 'git' ? 'git' : 'ki' } catch { return 'ki' }
  })
  const bereichSetzen = (b: 'ki' | 'git') => {
    setBereich(b)
    try { localStorage.setItem('ota.sicherheit.bereich', b) } catch { /* egal */ }
  }
  const [stat, setStat] = useState<KiSicherheitStatistik | null>(null)
  const [stand, setStand] = useState<KiSicherheitStand | null>(null)
  const [fehler, setFehler] = useState('')

  const laden = useCallback(async () => {
    try {
      const [s, e] = await Promise.all([api.kiSicherheitStatistik(tage), api.kiSicherheit()])
      setStat(s); setStand(e); setFehler('')
    } catch (err) {
      setFehler(err instanceof ApiError ? err.message : tr('Hat nicht geklappt'))
    }
  }, [tage])
  useEffect(() => {
    void laden()
    const timer = setInterval(() => { void laden() }, 60_000)
    return () => clearInterval(timer)
  }, [laden])

  async function loeschen() {
    if (!window.confirm(tr('Alle Zähler der KI-Sicherheit löschen? Das steht im Protokoll.'))) return
    try {
      const r = await api.kiSicherheitLoeschen()
      onToast(tr('{n} Zeilen gelöscht.', { n: r.zeilen })); void laden()
    } catch (err) {
      onToast(err instanceof ApiError ? err.message : tr('Hat nicht geklappt'), 'bad')
    }
  }

  const geprueft = stat ? Object.values(stat.geprueft).reduce((a, b) => a + b, 0) : 0
  const summeAktion = (a: string) => stat?.faelle_nach_aktion[a] ?? 0
  const fehlerSumme = stat ? Object.values(stat.fehler).reduce((a, b) => a + b, 0) : 0

  return (
    <div className="wrap">
      <header className="topbar">
        <div>
          <p className="silk" style={{ marginBottom: 6 }}>{tr('Verwaltung')}</p>
          <h1 className="h-page">{tr('Sicherheit')}</h1>
        </div>
        <button className="btn" onClick={() => onEinstellungen(bereich === 'git' ? 'git' : 'ki-sicherheit')}>{tr('Einstellungen')}</button>
      </header>

      <div className="ki-leiste">
        <Segmented label={tr('Bereich')} value={bereich}
          options={[
            { value: 'ki', label: tr('KI-Durchgang: Prompt Injection') },
            { value: 'git', label: tr('OTA-Git: Geheimnisse beim Push') },
          ]}
          onChange={bereichSetzen} />
      </div>

      {bereich === 'ki' && stand && <Lage stand={stand} />}

      <div className="ki-leiste">
        <Segmented label={tr('Zeitraum')} value={String(tage)}
          options={SPANNEN.map(([name, n]) => ({ value: String(n), label: tr(name) }))}
          onChange={(v) => setTage(Number(v))} />
      </div>

      {bereich === 'git' ? <GitGeheimnisseSicht tage={tage} onToast={onToast} /> : <>
      {fehler && <p className="note-warn">{fehler}</p>}
      {!stat ? <p className="sub">{tr('Wird geladen…')}</p> : (
        <>
          <div className="ki-kacheln">
            <Kachel wert={zahl(geprueft)} name={tr('Inhalte geprüft')}
              hint={tr('{w} Werkzeug-Ergebnisse, {d} Dokumente', { w: zahl(stat.geprueft.werkzeug || 0), d: zahl(stat.geprueft.dokument || 0) })} />
            <Kachel wert={zahl(stat.modell_geprueft)} name={tr('davon vom Modell beurteilt')} />
            <Kachel wert={zahl(stat.summe_faelle)} name={tr('Fälle')} ton={stat.summe_faelle ? 'warn' : undefined}
              hint={tr('Auffällige Inhalte. Ein Inhalt kann mehrere Typen treffen: {n} Treffer.', { n: zahl(stat.summe_treffer) })} />
            <Kachel wert={zahl(summeAktion('entfernt'))} name={tr('nur unsichtbare Zeichen, entfernt')} />
            <Kachel wert={zahl(summeAktion('gewarnt'))} name={tr('mit Warnung weitergegeben')} />
            <Kachel wert={zahl(summeAktion('gesperrt'))} name={tr('gesperrt')} ton={summeAktion('gesperrt') ? 'halt' : undefined} />
            {fehlerSumme > 0 && <Kachel wert={zahl(fehlerSumme)} name={tr('Prüfungen gescheitert')} ton="warn" />}
          </div>

          <Verlauf verlauf={stat.verlauf} tage={tage} />

          <section className="panel ki-sicher__teil">
            <h2 className="ki-titel">{tr('Treffer nach Typ')}</h2>
            {stat.faelle.length === 0 ? (
              <p className="sub">{tr('Im Zeitraum keine Fälle.')}</p>
            ) : (
              <div className="ki-sicher__tabelle">
                <table className="tbl">
                  <thead><tr>
                    <th>{tr('Typ')}</th><th>{tr('Stufe')}</th><th>{tr('Was das bedeutet')}</th>
                    <th style={{ textAlign: 'right' }}>{tr('Treffer')}</th><th>{tr('Aktion')}</th>
                  </tr></thead>
                  <tbody>
                    {stat.faelle.map((f) => (
                      <tr key={`${f.stufe}:${f.typ}`}>
                        <td><b>{tr(TYPEN[f.typ]?.name ?? f.typ)}</b></td>
                        <td>{tr(STUFEN[f.stufe] ?? f.stufe)}</td>
                        <td className="sub" style={{ maxWidth: 420 }}>{TYPEN[f.typ] ? tr(TYPEN[f.typ].text) : ''}</td>
                        <td className="data" style={{ textAlign: 'right' }}>{zahl(f.summe)}</td>
                        <td>{Object.entries(f.aktionen).map(([a, n]) => `${tr(AKTIONEN[a] ?? a)} ${zahl(n)}`).join(' · ')}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </section>

          <div className="ki-torten">
            <Balken titel={tr('Fälle nach Anwendung')} werte={stat.anwendungen.map((a) => ({ name: anwendungName(a.name), wert: a.faelle }))} />
            <Balken titel={tr('Fälle nach Herkunft')} werte={stat.herkunft.map((a) => ({ name: herkunftName(a.name), wert: a.faelle }))} />
          </div>

          {(fehlerSumme > 0 || Object.keys(stat.hinweise).length > 0) && (
            <section className="panel ki-sicher__teil">
              <h2 className="ki-titel">{tr('Zustand der Prüfung')}</h2>
              <ul className="ki-sicher__liste">
                {Object.entries(stat.fehler).map(([k, n]) => <li key={k}>{tr(FEHLER[k] ?? k)}: <b className="data">{zahl(n)}</b></li>)}
                {Object.entries(stat.hinweise).map(([k, n]) => <li key={k}>{tr(HINWEISE[k] ?? k)}: <b className="data">{zahl(n)}</b></li>)}
              </ul>
            </section>
          )}

          <section className="panel ki-sicher__teil">
            <h2 className="ki-titel">{tr('Was hier gezählt wird, und was nicht')}</h2>
            <p className="sub">{tr('Geprüft wird nur, was ein KI-Assistent liest und nicht vom Menschen stammt: Ergebnisse von Werkzeugen (Dateien, Befehlsausgaben, Webseiten) und Dokumente, die Open WebUI mitschickt. Die Eingaben des Menschen und der Systemprompt bleiben ungeprüft.')}</p>
            <p className="sub">{tr('Gespeichert werden ausschließlich Zähler je Stunde: Herkunft (alle Arbeitsplätze zusammen oder ein externer Dienst), Anwendung, Stufe, Typ und Aktion. Kein Text, kein Ausschnitt, keine Person, kein Arbeitsplatz. Der Inhalt wird nur im Speicher des KI-Durchgangs geprüft; von jedem geprüften Abschnitt bleibt dort nur eine Prüfsumme, damit eine Unterhaltung nicht bei jedem Aufruf neu zählt.')}</p>
            <p className="sub">{tr('Aufbewahrung: {n} Tage, danach löscht OTA die Zähler von selbst.', { n: stand?.frist_tage ?? 365 })}{' '}
              {stat.seit && tr('Erster Eintrag: {d}.', { d: new Date(stat.seit).toLocaleDateString(getLang() === 'en' ? 'en-GB' : 'de-DE') })}</p>
            <button className="btn btn--ghost" onClick={() => void loeschen()}>{tr('Alle Zähler löschen')}</button>
          </section>
        </>
      )}
      </>}
    </div>
  )
}

function Lage({ stand }: { stand: KiSicherheitStand }) {
  const art = { beobachten: tr('beobachten'), warnen: tr('warnen'), sperren: tr('sperren') }[stand.betriebsart]
  const stufen = [stand.unsichtbar && tr('Stufe 1'), stand.muster && tr('Stufe 2'),
    stand.modell_an && tr('Stufe 3 ({m})', { m: stand.modell })].filter(Boolean).join(' · ')
  if (!stand.an) {
    return <p className="note-warn" style={{ marginBottom: 16 }}>{tr('Die KI-Sicherheit ist ausgeschaltet. Es wird nichts geprüft; die Zahlen unten stammen aus der Zeit, in der sie lief.')}</p>
  }
  if (!stand.aktiv) {
    return <p className="note-warn" style={{ marginBottom: 16 }}>{tr('Der KI-Durchgang ist nicht aktiv (Einstellungen → IDE-AI). Ohne ihn prüft niemand.')}</p>
  }
  return (
    <p className="note-info" style={{ marginBottom: 16 }}>
      {tr('Eingeschaltet, Betriebsart {a}. Aktiv: {s}.', { a: art, s: stufen || tr('keine Stufe') })}
    </p>
  )
}

export function Kachel({ wert, name, hint, ton }: { wert: string; name: string; hint?: string; ton?: 'warn' | 'halt' }) {
  return (
    <div className={`ki-kachel${ton ? ` ki-kachel--${ton}` : ''}`} title={hint}>
      <div className="ki-kachel__wert">{wert}</div>
      <div className="ki-kachel__name">{name}</div>
    </div>
  )
}

/** Fälle je Tag als Säulen; geprüfte Inhalte und Sperren im Tooltip und in der Tabelle darunter. */
export function Verlauf({ verlauf, tage, geprueftName = 'Inhalte geprüft' }: { verlauf: KiSicherheitStatistik['verlauf']; tage: number; geprueftName?: string }) {
  const [tabelle, setTabelle] = useState(false)
  // Lückenlos: auch Tage ohne Zahlen bekommen ihren Platz.
  const heute = new Date()
  const tageListe: string[] = []
  for (let i = Math.min(tage, 365) - 1; i >= 0; i--) {
    const d = new Date(Date.UTC(heute.getUTCFullYear(), heute.getUTCMonth(), heute.getUTCDate() - i))
    tageListe.push(d.toISOString().slice(0, 10))
  }
  const nach = Object.fromEntries(verlauf.map((v) => [v.tag, v]))
  const reihe = tageListe.map((t) => nach[t] ?? { tag: t, geprueft: 0, faelle: 0, gesperrt: 0 })
  const max = Math.max(1, ...reihe.map((r) => r.faelle))
  const datum = (t: string) => new Date(t + 'T12:00:00Z').toLocaleDateString(getLang() === 'en' ? 'en-GB' : 'de-DE', { day: '2-digit', month: '2-digit' })
  return (
    <section className="panel ki-sicher__teil">
      <div className="viewer__row" style={{ justifyContent: 'space-between', marginBottom: 8 }}>
        <h2 className="ki-titel" style={{ margin: 0 }}>{tr('Fälle je Tag')}</h2>
        <button className="btn btn--ghost" onClick={() => setTabelle(!tabelle)}>{tabelle ? tr('Als Grafik') : tr('Als Tabelle')}</button>
      </div>
      {tabelle ? (
        <div className="ki-sicher__tabelle">
          <table className="tbl">
            <thead><tr><th>{tr('Tag')}</th><th style={{ textAlign: 'right' }}>{tr(geprueftName)}</th>
              <th style={{ textAlign: 'right' }}>{tr('Fälle')}</th><th style={{ textAlign: 'right' }}>{tr('gesperrt')}</th></tr></thead>
            <tbody>{[...reihe].reverse().filter((r) => r.geprueft || r.faelle).map((r) => (
              <tr key={r.tag}><td>{datum(r.tag)}</td><td className="data" style={{ textAlign: 'right' }}>{zahl(r.geprueft)}</td>
                <td className="data" style={{ textAlign: 'right' }}>{zahl(r.faelle)}</td><td className="data" style={{ textAlign: 'right' }}>{zahl(r.gesperrt)}</td></tr>
            ))}</tbody>
          </table>
        </div>
      ) : (
        <>
          <div className="ki-saeulen" role="img" aria-label={tr('Fälle je Tag')}>
            {reihe.map((r) => (
              <div key={r.tag} className="ki-saeulen__spalte"
                title={tr('{d}: {f} Fälle, {g} geprüft, {s} gesperrt', { d: datum(r.tag), f: zahl(r.faelle), g: zahl(r.geprueft), s: zahl(r.gesperrt) })}>
                <div className={`ki-saeulen__balken${r.gesperrt ? ' ki-saeulen__balken--halt' : ''}`}
                  style={{ height: r.faelle ? `${Math.max(3, (r.faelle / max) * 100)}%` : 0 }} />
              </div>
            ))}
          </div>
          <div className="ki-saeulen__achse">
            <span>{datum(reihe[0].tag)}</span><span className="data">{tr('höchstens {n} je Tag', { n: zahl(max) })}</span><span>{datum(reihe[reihe.length - 1].tag)}</span>
          </div>
        </>
      )}
    </section>
  )
}

function Balken({ titel, werte }: { titel: string; werte: { name: string; wert: number }[] }) {
  const max = Math.max(1, ...werte.map((w) => w.wert))
  return (
    <section className="panel ki-torte">
      <h2 className="ki-titel">{titel}</h2>
      {werte.length === 0 ? <p className="sub">{tr('Im Zeitraum keine Fälle.')}</p> : (
        <div className="ki-sicher__balken">
          {werte.map((w) => (
            <div key={w.name} className="ki-sicher__zeile" title={`${w.name}: ${zahl(w.wert)}`}>
              <span className="ki-sicher__name">{w.name}</span>
              <span className="ki-sicher__spur"><span style={{ width: `${(w.wert / max) * 100}%` }} /></span>
              <span className="data">{zahl(w.wert)}</span>
            </div>
          ))}
        </div>
      )}
    </section>
  )
}

function anwendungName(w: string): string {
  if (w.startsWith('x:')) return tr('Externer Dienst {n}', { n: w.slice(2) })
  return ({ opencode: 'opencode', continue: 'Continue', vscode: 'VS Code', pycharm: 'PyCharm', cline: 'Cline', roo: 'Roo Code',
    kilo: 'Kilo Code', aider: 'Aider', copilot: 'Copilot', intellij: 'IntelliJ', jetbrains: 'JetBrains', python: 'Python',
    node: 'Node', java: 'Java', skript: tr('Skript'), sonstiges: tr('Sonstiges') } as Record<string, string>)[w] ?? w
}

function herkunftName(h: string): string {
  if (h === 'arbeitsplatz') return tr('Arbeitsplätze')
  if (h.startsWith('extern:')) return tr('Externer Dienst {n}', { n: h.slice(7) })
  return h
}
