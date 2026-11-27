import { Fragment, useCallback, useEffect, useState, type ReactNode } from 'react'
import { Segmented } from '../components/controls'
import { ApiError, api, type DsEintrag, type DsFilter, type DsLage, type DsPerson, type DsProtokoll, type DsPunkt, type DsRechte } from '../lib/api'
import { getLang, t as tr, useLang } from '../lib/i18n'
import { ACTION_TEXT } from './Monitor'

/**
 * Datenschutz: die Sicht der/des Datenschutzbeauftragten (Handbuch Kapitel 42).
 *
 * Für das Recht `datenschutz.pruefen` (Gruppe „datenschutz“) und für die
 * Verwaltung. Die Texte sind für Menschen geschrieben, die nicht aus der IT
 * kommen: Jeder Punkt sagt, was er bedeutet, nicht wie er technisch heißt.
 *
 * Nur lesend, bis auf zwei Dinge: Auskunft nach Art. 15 (mit Begründung im
 * Prüfprotokoll) und den Datenschutzhinweis ändern.
 */

type Bereich = 'lage' | 'rechte' | 'zugriffe' | 'protokoll' | 'auskunft'

export function Datenschutz({ onToast, onHinweis }: {
  onToast: (m: string, tone?: 'ok' | 'bad') => void
  onHinweis: () => void
}) {
  useLang()
  const [bereich, setBereich] = useState<Bereich>(() => {
    try { return (localStorage.getItem('ota.datenschutz.bereich') as Bereich) || 'lage' } catch { return 'lage' }
  })
  const setzen = (b: Bereich) => {
    setBereich(b)
    try { localStorage.setItem('ota.datenschutz.bereich', b) } catch { /* egal */ }
  }
  return (
    <div className="wrap">
      <header className="topbar">
        <div>
          <p className="silk" style={{ marginBottom: 6 }}>{tr('Für Datenschutzbeauftragte')}</p>
          <h1 className="h-page">{tr('Datenschutz')}</h1>
        </div>
        <button className="btn" onClick={onHinweis}>{tr('Datenschutzhinweis')}</button>
      </header>
      <p className="sub" style={{ maxWidth: 900, marginTop: 0 }}>
        {tr('Hier steht, welche Daten OTA über die Menschen erfasst, wie lange es sie aufbewahrt, wer worauf zugreifen darf und wer tatsächlich zugegriffen hat. Diese Seite ändert nichts an der Anlage. Ausnahmen: eine Auskunft nach Art. 15 erstellen und den Datenschutzhinweis bearbeiten.')}
      </p>
      <div className="ki-leiste">
        <Segmented label={tr('Bereich')} value={bereich}
          options={[
            { value: 'lage', label: tr('Überblick') },
            { value: 'rechte', label: tr('Wer darf was') },
            { value: 'zugriffe', label: tr('Zugriffe') },
            { value: 'protokoll', label: tr('Prüfprotokoll') },
            { value: 'auskunft', label: tr('Auskunft') },
          ]}
          onChange={setzen} />
      </div>
      {bereich === 'lage' && <Lage onHinweis={onHinweis} />}
      {bereich === 'rechte' && <Rechte />}
      {bereich === 'zugriffe' && <Protokoll zugriffe onToast={onToast} />}
      {bereich === 'protokoll' && <Protokoll zugriffe={false} onToast={onToast} />}
      {bereich === 'auskunft' && <Auskunft onToast={onToast} />}
    </div>
  )
}

const datum = (iso: string, mitZeit = true) => new Date(iso).toLocaleString(getLang() === 'en' ? 'en-GB' : 'de-DE',
  mitZeit ? { day: '2-digit', month: '2-digit', year: 'numeric', hour: '2-digit', minute: '2-digit' }
    : { day: '2-digit', month: '2-digit', year: 'numeric' })
const tage = (n: number) => n > 0 ? tr('{n} Tage', { n }) : tr('unbegrenzt')

// ------------------------------------------------------------------ Überblick

const BETRIEBSART: Record<string, string> = { beobachten: 'nur zählen', warnen: 'warnen', sperren: 'sperren' }

/** Titel, Erklärung und Stand eines Punkts — in Worten, nicht in Technik. */
function punktText(p: DsPunkt): { titel: string; was: string; stand: string } {
  const w = p.werte
  switch (p.id) {
    case 'protokoll': return {
      titel: tr('Prüfprotokoll'),
      was: tr('OTA schreibt mit, wer wann was in der Verwaltung getan hat, dazu Anmeldungen und das Starten von Arbeitsplätzen. So lässt sich später nachvollziehen, wer auf welche Daten zugegriffen hat.'),
      stand: tr('Anmeldungen und Starts von Arbeitsplätzen werden nach {a} gelöscht, alle anderen Einträge nach {b}.', { a: tage(w.verhalten_tage), b: tage(w.verwaltung_tage) }),
    }
    case 'syslog': return {
      titel: tr('Kopie des Prüfprotokolls auf einem zentralen Server'),
      was: tr('Eine zweite Kopie des Prüfprotokolls auf einem anderen Rechner (Syslog). Dort kann auch die Verwaltung von OTA nachträglich nichts ändern oder löschen.'),
      stand: p.an ? tr('Eingeschaltet, Ziel: {z}.', { z: w.ziel }) : tr('Ausgeschaltet.'),
    }
    case 'ki_statistik': return {
      titel: tr('Statistik über die Nutzung der KI'),
      was: tr('Zu jeder Anfrage an die KI: wann, von wem, aus welchem Arbeitsplatz, welches Modell und wie viel Text. Nicht gespeichert wird, was gefragt oder geantwortet wurde. Jeder Mensch sieht seine eigenen Zahlen unter „Meine KI-Nutzung“.'),
      stand: p.an ? tr('Eingeschaltet. Einzelne Anfragen werden nach {a} gelöscht, Summen je Stunde nach {b}.', { a: tage(w.frist_roh), b: tage(w.frist_stunden) }) : tr('Ausgeschaltet.'),
    }
    case 'ki_extern': return {
      titel: tr('Angebundene KI-Programme'),
      was: tr('Andere Programme, zum Beispiel Open WebUI, deren Anfragen an die KI über OTA laufen und mitgezählt werden. Sie teilen OTA dazu Namen oder E-Mail-Adresse der Person mit.'),
      stand: p.an ? (w.dienste as string[]).join(', ') : tr('Keine.'),
    }
    case 'ki_sicherheit': return {
      titel: tr('Schutz der KI vor Angriffen'),
      was: tr('OTA prüft Texte, die ein KI-Assistent liest (Dateien, Webseiten), auf versteckte Anweisungen. Gezählt wird nur, wie oft etwas auffiel, nicht bei wem.'),
      stand: p.an ? tr('Eingeschaltet. Bei einem Fund: {a}.', { a: tr(BETRIEBSART[w.betriebsart] ?? w.betriebsart) }) : tr('Ausgeschaltet.'),
    }
    case 'fallberichte': return {
      titel: tr('Fallberichte zur KI-Sicherheit'),
      was: tr('Zu jedem Fund ein kurzer Ausschnitt der auffälligen Textstelle, ohne Namen der Person. Die Verwaltung öffnet einen Bericht nur mit Begründung. Wer welchen Bericht geöffnet hat, steht unter „Zugriffe“. Den Inhalt der Berichte zeigt diese Seite bewusst nicht.'),
      stand: p.an ? tr('Eingeschaltet. Berichte werden nach {a} gelöscht.', { a: tage(w.frist_tage) }) : tr('Ausgeschaltet.'),
    }
    case 'git_geheimnisse': return {
      titel: tr('Prüfung auf Passwörter im Programmcode'),
      was: tr('Wenn jemand Programmcode in OTA-Git hochlädt, sucht OTA nach versehentlich mitgeschickten Passwörtern. Gezählt wird nur die Anzahl, nicht wer oder was.'),
      stand: p.an ? tr('Eingeschaltet. Bei einem Fund: {a}.', { a: tr(BETRIEBSART[w.betriebsart] ?? w.betriebsart) }) : tr('Ausgeschaltet.'),
    }
    case 'konto_daten': return {
      titel: tr('Dateien gelöschter Konten'),
      was: tr('Was mit den persönlichen Dateien eines Menschen geschieht, wenn sein Konto gelöscht wird.'),
      stand: p.an ? (w.tage > 0 ? tr('Werden {n} Tage nach dem Löschen des Kontos entfernt.', { n: w.tage }) : tr('Werden sofort mit dem Konto entfernt.'))
        : tr('Bleiben erhalten, bis jemand sie von Hand löscht.'),
    }
    case 'sicherungen': return {
      titel: tr('Sicherungen'),
      was: tr('Kopien der Arbeitsplätze und der Datenbank für den Fall eines Defekts. Was gelöscht wurde, steckt noch so lange in den Sicherungen, bis diese selbst gelöscht werden.'),
      stand: p.an ? tr('Automatisch. Aufbewahrt werden {t} tägliche und {w} wöchentliche Sicherungen.', { t: w.taeglich, w: w.woechentlich })
        : tr('Keine automatischen Sicherungen.'),
    }
    case 'hinweis': return {
      titel: tr('Datenschutzhinweis'),
      was: tr('Der Text, den alle Menschen in OTA unter „DSGVO“ lesen können. Die Gruppe Datenschutz darf ihn selbst ändern.'),
      stand: p.an ? tr('Eigener Text, zuletzt geändert am {d} von {v}.', { d: w.am ? datum(w.am, false) : '?', v: w.von || '?' })
        : tr('Es gilt der mitgelieferte Standardtext.'),
    }
    case 'erweiterung': return {
      titel: tr('Erweiterung: {n}', { n: w.name }),
      was: tr('Ein Zusatzdienst, zum Beispiel ein Gedächtnis für den KI-Assistenten. Er speichert eigene Daten der Menschen, die ihn nutzen.'),
      stand: p.an ? tr('Eingeschaltet für die Gruppen: {g}.', { g: (w.gruppen as string[]).join(', ') || tr('keine') }) : tr('Ausgeschaltet.'),
    }
    default: return { titel: p.id, was: '', stand: p.an ? tr('Eingeschaltet.') : tr('Ausgeschaltet.') }
  }
}

const HINWEISE: Record<string, string> = {
  hinweis_standard: 'Der Datenschutzhinweis ist noch der mitgelieferte Standardtext. Darin fehlen die verantwortliche Stelle und die Kontaktdaten der/des Datenschutzbeauftragten.',
  syslog_aus: 'Das Prüfprotokoll liegt nur in OTA selbst. Wer OTA vollständig verwaltet, könnte es verändern. Eine Kopie auf einem zentralen Server (Syslog) schützt davor.',
  konto_daten_behalten: 'Die Dateien gelöschter Konten werden nicht automatisch entfernt.',
  fallberichte_an: 'Fallberichte der KI-Sicherheit sind eingeschaltet. Darin stehen kurze Ausschnitte aus Dateien und Webseiten. Wer welchen Bericht geöffnet hat, steht unter „Zugriffe“.',
  ki_statistik_an: 'Die Nutzung der KI wird je Person erfasst. Die Verwaltung sieht die Zahlen einzelner Menschen nur mit Begründung; jede solche Einsicht steht unter „Zugriffe“.',
  ki_extern: 'Angebundene KI-Programme teilen OTA Namen oder E-Mail-Adresse der Person mit, damit Anfragen zugeordnet werden können.',
  protokoll_unbegrenzt: 'Für einen Teil des Prüfprotokolls ist keine Löschfrist gesetzt.',
}

function Lage({ onHinweis }: { onHinweis: () => void }) {
  const [lage, setLage] = useState<DsLage | null>(null)
  const [fehler, setFehler] = useState('')
  useEffect(() => {
    api.dsLage().then(setLage).catch((e) => setFehler(e instanceof ApiError ? e.message : tr('Hat nicht geklappt')))
  }, [])
  if (fehler) return <p className="note-warn">{fehler}</p>
  if (!lage) return <p className="sub">{tr('Wird geladen…')}</p>
  return (
    <>
      {lage.hinweise.length > 0 && (
        <section className="panel ki-sicher__teil">
          <h2 className="ki-titel">{tr('Zur Beachtung')}</h2>
          <ul className="ds-hinweise">
            {lage.hinweise.map((h) => <li key={h}>{tr(HINWEISE[h] ?? h)}</li>)}
          </ul>
        </section>
      )}
      <section className="panel ki-sicher__teil">
        <h2 className="ki-titel">{tr('Was OTA erfasst und wie lange')}</h2>
        <div className="ds-punkte">
          {lage.punkte.map((p, i) => {
            const t = punktText(p)
            return (
              <div key={`${p.id}-${i}`} className="ds-punkt">
                <div className="ds-punkt__kopf">
                  <b>{t.titel}</b>
                  <span className={`ds-marke${p.an ? ' ds-marke--an' : ''}`}>
                    {p.id === 'hinweis' ? (p.an ? tr('eigener Text') : tr('Standardtext')) : p.an ? tr('an') : tr('aus')}
                  </span>
                </div>
                <p className="sub" style={{ margin: '4px 0' }}>{t.was}</p>
                <p style={{ margin: 0 }}>{t.stand}</p>
                {p.id === 'hinweis' && <button className="btn btn--ghost btn--sm" style={{ marginTop: 6 }} onClick={onHinweis}>{tr('Ansehen und bearbeiten')}</button>}
              </div>
            )
          })}
        </div>
      </section>
    </>
  )
}

// ------------------------------------------------------------- Wer darf was

const RECHTE: Record<string, string> = {
  admin: 'Vollzugriff auf alles',
  'arbeitsplatz.terminal': 'Befehle in Arbeitsplätzen anderer ausführen und dort alle Dateien lesen',
  'sessions.view_all': 'Alle laufenden Arbeitsplätze sehen und beenden',
  'users.manage': 'Konten anlegen, ändern und sperren, Auskünfte erstellen',
  'groups.manage': 'Gruppen und damit Rechte vergeben',
  'settings.manage': 'Einstellungen ändern; KI-Nutzung einzelner Menschen mit Begründung einsehen',
  'audit.view': 'Prüfprotokoll lesen',
  'datenschutz.pruefen': 'Datenschutz prüfen (diese Seite)',
  'anwendungen.verwalten': 'Anmeldung über OTA für andere Programme einrichten',
  'arbeitsplatz.root': 'Eigener Arbeitsplatz mit Administratorrechten (nur im eigenen Arbeitsplatz)',
}

function Rechte() {
  const [r, setR] = useState<DsRechte | null>(null)
  useEffect(() => { api.dsRechte().then(setR).catch(() => setR(null)) }, [])
  if (!r) return <p className="sub">{tr('Wird geladen…')}</p>
  return (
    <>
      <section className="panel ki-sicher__teil">
        <h2 className="ki-titel">{tr('Weitreichende Rechte: wie viele Menschen sie haben')}</h2>
        <p className="sub">{tr('Rechte werden über Gruppen vergeben. Gezählt sind aktive Konten. Was jemand mit diesen Rechten getan hat, steht unter „Zugriffe“.')}</p>
        <table className="tbl">
          <tbody>
            {r.je_recht.map((x) => (
              <tr key={x.recht}><td>{tr(RECHTE[x.recht] ?? x.recht)}</td><td className="data" style={{ textAlign: 'right' }}>{x.anzahl}</td></tr>
            ))}
          </tbody>
        </table>
      </section>
      {r.gruppen.map((g) => (
        <section key={g.name} className="panel ki-sicher__teil">
          <h2 className="ki-titel">{tr('Gruppe „{n}“', { n: g.name })}{g.system ? ` · ${tr('fest eingebaut')}` : ''}</h2>
          {g.beschreibung && <p className="sub">{g.beschreibung}</p>}
          <p style={{ margin: '6px 0' }}><b>{tr('Darf:')}</b> {g.rechte.map((x) => tr(RECHTE[x] ?? x)).join('; ')}</p>
          <p style={{ margin: 0 }}><b>{tr('Mitglieder:')}</b>{' '}
            {g.mitglieder.length === 0 ? tr('niemand') : g.mitglieder.map((m) => (
              <span key={m.konto} className={m.aktiv ? '' : 'sub'} title={m.konto}>
                {m.name}{m.aktiv ? '' : ` (${tr('gesperrt')})`}
              </span>
            )).reduce<ReactNode[]>((a, b, i) => (i ? [...a, ', ', b] : [b]), [])}
          </p>
        </section>
      ))}
    </>
  )
}

// --------------------------------------------------- Zugriffe und Protokoll

const ARTEN: [string, string][] = [
  ['zugriffe', 'Alle'],
  ['einsicht', 'Einsicht in Daten anderer'],
  ['konten', 'Konten gesperrt oder gelöscht'],
  ['rechte', 'Rechte vergeben'],
  ['einstellungen', 'Datenschutz-Einstellungen'],
]

function vorTagen(n: number): string {
  const d = new Date(); d.setDate(d.getDate() - n)
  return d.toISOString().slice(0, 10)
}

/** Was im Detail eines Eintrags für Menschen wichtig ist: Begründung und betroffenes Konto. */
function details(e: DsEintrag): string {
  const d = e.detail || {}
  const teile: string[] = []
  if (d.grund) teile.push(tr('Begründung: {g}', { g: String(d.grund) }))
  const konto = e.konto
  if (konto) teile.push(tr('Konto: {k}', { k: String(konto) }))
  if (d.zeilen !== undefined && e.aktion === 'datenschutz.protokoll_exportiert') teile.push(tr('{n} Einträge', { n: d.zeilen }))
  return teile.join(' · ')
}

function Protokoll({ zugriffe, onToast }: { zugriffe: boolean; onToast: (m: string, tone?: 'ok' | 'bad') => void }) {
  const [von, setVon] = useState(vorTagen(30))
  const [bis, setBis] = useState(vorTagen(0))
  const [art, setArt] = useState(zugriffe ? 'zugriffe' : '')
  const [wer, setWer] = useState('')
  const [person, setPerson] = useState<DsPerson | null>(null)
  const [seite, setSeite] = useState(1)
  const [daten, setDaten] = useState<DsProtokoll | null>(null)
  const [offen, setOffen] = useState<number | null>(null)

  const filter: DsFilter = { von, bis, art: art || undefined, wer: wer || undefined, person: person?.id }
  const schluessel = JSON.stringify(filter)
  const laden = useCallback(async () => {
    try { setDaten(await api.dsProtokoll(JSON.parse(schluessel), seite)) } catch (err) {
      onToast(err instanceof ApiError ? err.message : tr('Hat nicht geklappt'), 'bad')
    }
  }, [schluessel, seite, onToast])
  useEffect(() => { void laden() }, [laden])
  useEffect(() => { setSeite(1) }, [schluessel])

  async function exportieren() {
    try {
      const { blob, datei } = await api.dsProtokollCsv(filter)
      const url = URL.createObjectURL(blob)
      const a = document.createElement('a'); a.href = url; a.download = datei
      document.body.appendChild(a); a.click(); a.remove()
      setTimeout(() => URL.revokeObjectURL(url), 10_000)
      onToast(tr('Exportiert. Der Export steht im Prüfprotokoll.'))
    } catch (err) {
      onToast(err instanceof ApiError ? err.message : tr('Hat nicht geklappt'), 'bad')
    }
  }

  const seiten = daten ? Math.max(1, Math.ceil(daten.gesamt / daten.je_seite)) : 1
  return (
    <section className="panel ki-sicher__teil">
      <h2 className="ki-titel">{zugriffe ? tr('Zugriffe auf Daten von Menschen') : tr('Prüfprotokoll')}</h2>
      <p className="sub">{zugriffe
        ? tr('Die Einträge im Prüfprotokoll, bei denen jemand auf Daten oder Bildschirme anderer zugegriffen, Konten gesperrt oder gelöscht, Rechte vergeben oder Datenschutz-Einstellungen geändert hat. Steht eine Begründung dabei, wird sie angezeigt.')
        : tr('Alles, was OTA protokolliert, mit Filtern. Wer nach einer bestimmten Person filtert, steht damit selbst im Protokoll.')}</p>
      {zugriffe && (
        <div className="ki-leiste">
          <Segmented label={tr('Art')} value={art} options={ARTEN.map(([v, l]) => ({ value: v, label: tr(l) }))} onChange={setArt} />
        </div>
      )}
      <div className="ds-filter">
        <label>{tr('von')} <input type="date" value={von} onChange={(e) => setVon(e.target.value)} /></label>
        <label>{tr('bis')} <input type="date" value={bis} onChange={(e) => setBis(e.target.value)} /></label>
        <label>{tr('Wer hat gehandelt')} <input type="search" value={wer} placeholder={tr('Name des Kontos')} onChange={(e) => setWer(e.target.value)} /></label>
        {!zugriffe && <PersonWahl person={person} setPerson={setPerson} label={tr('Betroffene Person')} />}
        <button className="btn btn--ghost" onClick={() => void exportieren()}>{tr('Als Tabelle herunterladen (CSV)')}</button>
      </div>
      {!daten ? <p className="sub">{tr('Wird geladen…')}</p> : daten.eintraege.length === 0 ? (
        <p className="sub">{tr('Keine Einträge im gewählten Zeitraum.')}</p>
      ) : (
        <>
          <p className="sub">{tr('{n} Einträge', { n: daten.gesamt.toLocaleString(getLang() === 'en' ? 'en-US' : 'de-DE') })}</p>
          <div className="ki-sicher__tabelle">
            <table className="tbl">
              <thead><tr><th>{tr('Zeit')}</th><th>{tr('Wer')}</th><th>{tr('Was')}</th><th>{tr('Einzelheiten')}</th></tr></thead>
              <tbody>
                {daten.eintraege.map((e, i) => (
                  <Fragment key={i}>
                    <tr onClick={() => setOffen(offen === i ? null : i)} style={{ cursor: 'pointer' }} title={tr('Klicken für alle Angaben')}>
                      <td className="data" style={{ whiteSpace: 'nowrap' }}>{datum(e.ts)}</td>
                      <td>{e.wer ?? tr('OTA selbst')}</td>
                      <td>{tr(ACTION_TEXT[e.aktion] ?? e.aktion)}</td>
                      <td className="sub">{details(e)}</td>
                    </tr>
                    {offen === i && (
                      <tr><td colSpan={4}>
                        <pre className="ki-sicher__auszug" style={{ whiteSpace: 'pre-wrap', margin: 0 }}>
                          {`${tr('Vorgang')}: ${e.aktion}\n${tr('Betrifft')}: ${e.objekt_art ?? '—'} ${e.objekt ?? ''}\n${tr('Adresse des Rechners')}: ${e.ip ?? '—'}\n${JSON.stringify(e.detail, null, 2)}`}
                        </pre>
                      </td></tr>
                    )}
                  </Fragment>
                ))}
              </tbody>
            </table>
          </div>
          <div className="viewer__row" style={{ gap: 8, marginTop: 10 }}>
            <button className="btn btn--ghost btn--sm" disabled={seite <= 1} onClick={() => setSeite(seite - 1)}>{tr('Zurück')}</button>
            <span className="sub">{tr('Seite {s} von {n}', { s: seite, n: seiten })}</span>
            <button className="btn btn--ghost btn--sm" disabled={seite >= seiten} onClick={() => setSeite(seite + 1)}>{tr('Weiter')}</button>
          </div>
        </>
      )}
    </section>
  )
}

function PersonWahl({ person, setPerson, label }: { person: DsPerson | null; setPerson: (p: DsPerson | null) => void; label: string }) {
  const [q, setQ] = useState('')
  const [treffer, setTreffer] = useState<DsPerson[]>([])
  useEffect(() => {
    if (q.trim().length < 2) { setTreffer([]); return }
    const t = setTimeout(() => { api.dsPersonen(q).then(setTreffer).catch(() => setTreffer([])) }, 250)
    return () => clearTimeout(t)
  }, [q])
  if (person) {
    return (
      <span className="ds-person">{label}: <b>{person.name}</b> ({person.konto})
        <button className="btn btn--ghost btn--sm" onClick={() => setPerson(null)}>{tr('entfernen')}</button></span>
    )
  }
  return (
    <span className="ds-suche">
      <label>{label} <input type="search" value={q} placeholder={tr('Name, Konto oder E-Mail')} onChange={(e) => setQ(e.target.value)} /></label>
      {treffer.length > 0 && (
        <ul className="ds-treffer">
          {treffer.map((p) => (
            <li key={p.id}><button className="btn btn--ghost btn--sm" onClick={() => { setPerson(p); setQ(''); setTreffer([]) }}>
              {p.name} ({p.konto}){p.aktiv ? '' : ` · ${tr('gesperrt')}`}
            </button></li>
          ))}
        </ul>
      )}
    </span>
  )
}

// ------------------------------------------------------------------ Auskunft

function Auskunft({ onToast }: { onToast: (m: string, tone?: 'ok' | 'bad') => void }) {
  const [person, setPerson] = useState<DsPerson | null>(null)
  const [grund, setGrund] = useState('')
  const [busy, setBusy] = useState(false)

  async function erstellen() {
    if (!person) return
    setBusy(true)
    try {
      const { blob, datei } = await api.dsAuskunft(person.id, grund)
      const url = URL.createObjectURL(blob)
      const a = document.createElement('a'); a.href = url; a.download = datei
      document.body.appendChild(a); a.click(); a.remove()
      setTimeout(() => URL.revokeObjectURL(url), 10_000)
      onToast(tr('Auskunft für {name} erstellt. Vor dem Herausgeben bitte liesmich.txt lesen.', { name: person.konto }))
      setGrund('')
    } catch (err) {
      onToast(err instanceof ApiError ? err.message : tr('Auskunft fehlgeschlagen'), 'bad')
    } finally { setBusy(false) }
  }

  return (
    <section className="panel ki-sicher__teil">
      <h2 className="ki-titel">{tr('Auskunft nach Art. 15 DSGVO')}</h2>
      <p className="sub">{tr('Erstellt eine ZIP-Datei mit allem, was OTA über einen Menschen gespeichert hat: Stammdaten, Gruppen, Einträge im Prüfprotokoll, Arbeitszeiten an Arbeitsplätzen, KI-Nutzung, Sicherungen, OTA-Git und eine Liste der eigenen Dateien (ohne deren Inhalt). Passwörter und Schlüssel sind nicht enthalten. Die Datei öffnet sich mit jedem Programm für ZIP-Dateien; die Tabellen darin öffnet Excel.')}</p>
      <p className="note-info">{tr('Vor dem Herausgeben: Das Prüfprotokoll in der Auskunft nennt auch die Namen von Verwaltern, die mit dem Konto zu tun hatten. Nach Art. 15 Abs. 4 DSGVO ist abzuwägen, ob diese geschwärzt werden. Die Datei liesmich.txt in der Auskunft erklärt jeden Teil.')}</p>
      <div className="ds-filter">
        <PersonWahl person={person} setPerson={setPerson} label={tr('Für wen')} />
      </div>
      {person && (
        <>
          <label className="ds-grund">{tr('Begründung (Pflicht), z. B. Aktenzeichen oder Datum des Antrags')}
            <textarea rows={2} value={grund} maxLength={500} onChange={(e) => setGrund(e.target.value)}
              placeholder={tr('z. B. Antrag auf Auskunft vom 27.11.2026, Az. DS-2026-014')} />
          </label>
          <p className="sub">{tr('Die Begründung steht zusammen mit dem eigenen Namen im Prüfprotokoll.')}</p>
          <button className="btn" disabled={busy || grund.trim().length < 10} onClick={() => void erstellen()}>
            {busy ? tr('Wird erstellt…') : tr('Auskunft erstellen und herunterladen')}
          </button>
        </>
      )}
    </section>
  )
}
