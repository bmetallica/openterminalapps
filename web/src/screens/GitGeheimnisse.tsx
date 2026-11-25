import { useCallback, useEffect, useState } from 'react'
import { ApiError, api, type GitGeheimnisseStatistik } from '../lib/api'
import { getLang, t as tr } from '../lib/i18n'
import { Kachel, Verlauf, zahl } from './KiSicherheit'

/**
 * Sicherheit → OTA-Git: Geheimnisse beim Push (Handbuch Kapitel 27).
 *
 * Nur Zahlen: wie viele Pushes geprüft wurden, was mit den auffälligen
 * geschah und welche Arten von Geheimnissen gefunden wurden. Kein Fundort,
 * kein Repository, keine Person.
 */

const ARTEN: Record<string, { name: string; text: string }> = {
  'privater-schluessel': { name: 'Privater Schlüssel', text: 'Ein Block „-----BEGIN … PRIVATE KEY-----“: SSH, TLS, PGP. Wer ihn hat, kann sich als sein Eigentümer ausgeben.' },
  'cloud-schluessel': { name: 'Cloud-Zugangsschlüssel', text: 'Zugangsschlüssel von AWS (AKIA…) oder Google (AIza…). Erlauben Zugriff auf Konten und Kosten.' },
  'git-token': { name: 'Git-Token', text: 'Persönliche Zugangstoken von GitHub oder GitLab. Erlauben Lesen und Schreiben in fremden Repositories.' },
  'ki-schluessel': { name: 'API-Schlüssel eines KI-Anbieters', text: 'Schlüssel der Form sk-…, etwa von OpenAI oder Anthropic. Kosten Geld und geben Zugriff auf das Konto.' },
  'chat-token': { name: 'Chat-Token', text: 'Tokens von Slack (xox…). Erlauben das Lesen und Schreiben von Nachrichten.' },
  jwt: { name: 'JSON Web Token', text: 'Ein Anmeldetoken (eyJ…). Ist es noch gültig, meldet es jeden an, der es hat.' },
  'passwort-im-code': { name: 'Passwort im Code', text: 'Eine Zuweisung wie password = "…" mit einem echten Wert. Platzhalter wie „changeme“ oder „<dein-token>“ zählen nicht.' },
  'zugang-in-adresse': { name: 'Zugangsdaten in einer Adresse', text: 'Eine Adresse wie https://name:passwort@server. Platzhalter und Variablen zählen nicht.' },
  'env-datei': { name: '.env-Datei', text: 'Eine Datei .env (nicht .env.example). Dort stehen üblicherweise die Geheimnisse einer Anwendung.' },
  schluesseldatei: { name: 'Schlüsseldatei', text: 'Dateien wie id_rsa, *.key, *.p12, *.kdbx, .netrc oder .git-credentials.' },
}
const AKTIONEN: [string, string][] = [['gezaehlt', 'nur gezählt'], ['gewarnt', 'angenommen, mit Warnung'],
  ['gesperrt', 'abgewiesen'], ['uebergangen', 'als Fehlalarm übergangen']]

export function GitGeheimnisseSicht({ tage, onToast }: { tage: number; onToast: (m: string, tone?: 'ok' | 'bad') => void }) {
  const [stat, setStat] = useState<GitGeheimnisseStatistik | null>(null)
  const [fehler, setFehler] = useState('')

  const laden = useCallback(async () => {
    try { setStat(await api.gitGeheimnisseStatistik(tage)); setFehler('') } catch (err) {
      setFehler(err instanceof ApiError ? err.message : tr('Hat nicht geklappt'))
    }
  }, [tage])
  useEffect(() => {
    void laden()
    const timer = setInterval(() => { void laden() }, 60_000)
    return () => clearInterval(timer)
  }, [laden])

  async function loeschen() {
    if (!window.confirm(tr('Alle Zähler der Geheimnisprüfung löschen? Das steht im Protokoll.'))) return
    try {
      const r = await api.gitGeheimnisseLoeschen()
      onToast(tr('{n} Zeilen gelöscht.', { n: r.zeilen })); void laden()
    } catch (err) {
      onToast(err instanceof ApiError ? err.message : tr('Hat nicht geklappt'), 'bad')
    }
  }

  if (fehler) return <p className="note-warn">{fehler}</p>
  if (!stat) return <p className="sub">{tr('Wird geladen…')}</p>
  const art = { beobachten: tr('beobachten'), warnen: tr('warnen'), sperren: tr('sperren') }[stat.betriebsart]

  return (
    <>
      {!stat.git_an ? (
        <p className="note-warn" style={{ marginBottom: 16 }}>{tr('OTA-Git ist aus. Es wird nichts geprüft.')}</p>
      ) : !stat.an ? (
        <p className="note-warn" style={{ marginBottom: 16 }}>{tr('Die Geheimnisprüfung ist ausgeschaltet (Einstellungen → Git). Die Zahlen unten stammen aus der Zeit, in der sie lief.')}</p>
      ) : (
        <p className="note-info" style={{ marginBottom: 16 }}>{tr('Eingeschaltet, bei einem Fund: {a}.', { a: art })}</p>
      )}

      <div className="ki-kacheln">
        <Kachel wert={zahl(stat.geprueft)} name={tr('Pushes geprüft')} />
        <Kachel wert={zahl(stat.faelle)} name={tr('Pushes mit Fund')} ton={stat.faelle ? 'warn' : undefined}
          hint={tr('Ein Push kann mehrere Geheimnisse enthalten: {n} Treffer.', { n: zahl(stat.summe_treffer) })} />
        {AKTIONEN.map(([k, name]) => (stat.nach_aktion[k] ?? 0) > 0 && (
          <Kachel key={k} wert={zahl(stat.nach_aktion[k])} name={tr(name)} ton={k === 'gesperrt' ? 'halt' : undefined} />
        ))}
        {stat.gekuerzt > 0 && <Kachel wert={zahl(stat.gekuerzt)} name={tr('nur teilweise geprüft')} ton="warn"
          hint={tr('Pushes mit mehr als 1.000 neuen Commits oder 30 MB Änderungen: geprüft wurde der Anfang.')} />}
      </div>

      <Verlauf verlauf={stat.verlauf} tage={tage} geprueftName="Pushes geprüft" />

      <section className="panel ki-sicher__teil">
        <h2 className="ki-titel">{tr('Treffer nach Art')}</h2>
        {stat.treffer.length === 0 ? (
          <p className="sub">{tr('Im Zeitraum keine Fälle.')}</p>
        ) : (
          <div className="ki-sicher__tabelle">
            <table className="tbl">
              <thead><tr>
                <th>{tr('Art')}</th><th>{tr('Was das bedeutet')}</th><th style={{ textAlign: 'right' }}>{tr('Treffer')}</th>
              </tr></thead>
              <tbody>
                {stat.treffer.map((t) => (
                  <tr key={t.typ}>
                    <td><b>{tr(ARTEN[t.typ]?.name ?? t.typ)}</b></td>
                    <td className="sub" style={{ maxWidth: 480 }}>{ARTEN[t.typ] ? tr(ARTEN[t.typ].text) : ''}</td>
                    <td className="data" style={{ textAlign: 'right' }}>{zahl(t.anzahl)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </section>

      <section className="panel ki-sicher__teil">
        <h2 className="ki-titel">{tr('Was hier gezählt wird, und was nicht')}</h2>
        <p className="sub">{tr('Geprüft werden die neuen Commits jedes Pushes nach OTA-Git: hinzugefügte Zeilen und Dateinamen. Was schon im Repository war, wird nicht erneut geprüft.')}</p>
        <p className="sub">{tr('Gespeichert werden ausschließlich Zähler je Stunde: wie viele Pushes, was mit ihnen geschah und wie viele Treffer je Art. Kein Geheimnis, kein Dateiname, kein Repository, keine Person. Den Fundort sieht nur, wer pusht, in der Ausgabe von git.')}</p>
        <p className="sub">{tr('Aufbewahrung: {n} Tage, danach löscht OTA die Zähler von selbst.', { n: stat.frist_tage })}{' '}
          {stat.seit && tr('Erster Eintrag: {d}.', { d: new Date(stat.seit).toLocaleDateString(getLang() === 'en' ? 'en-GB' : 'de-DE') })}</p>
        <button className="btn btn--ghost" onClick={() => void loeschen()}>{tr('Alle Zähler löschen')}</button>
      </section>
    </>
  )
}
