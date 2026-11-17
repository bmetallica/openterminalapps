import { useEffect, useMemo, useState } from 'react'
import { ApiError, api, type DsgvoHinweis } from '../lib/api'
import { renderMarkdown } from '../lib/markdown'
import { getLang, t as tr, useLang } from '../lib/i18n'

/* DSGVO: der Datenschutzhinweis (Handbuch Kapitel 28, routers/dsgvo.py).

   Für alle sichtbar, solange die KI-Nutzungsstatistik läuft; die Verwaltung
   sieht den Punkt immer und kann den Text hier anpassen — Markdown wie bei
   den News. Ohne eigenen Text gilt der mitgelieferte in der Sprache der
   Oberfläche. Platzhalter setzt diese Seite ein, damit genannte Fristen
   stimmen, auch wenn jemand sie später ändert. */

const STANDARD_DE = `## Datenschutzhinweis zu OTA

OTA stellt dir Arbeitsplätze (Container) im Browser bereit. Dabei werden personenbezogene Daten verarbeitet. Hier steht, welche, wozu und wie lange.

### Betrieb der Arbeitsplätze

- **Was:** dein Konto, welche Arbeitsplätze du startest, anhältst und beendest (mit Zeitpunkten), die aktuelle Auslastung deiner laufenden Container (Prozessor, Arbeitsspeicher, Speicherplatz) und die darin installierten Anwendungen.
- **Wozu:** Betrieb, Kapazitätsplanung, Fehlersuche und Sicherheit.
- **Prüfprotokoll:** Vorgänge wie Anmeldungen, Änderungen durch die Verwaltung und jede Einsicht in personenbezogene Statistiken werden protokolliert.

### Nutzung der KI

Die KI-Nutzungsstatistik ist zurzeit **{statistik}**.

- **Was:** zu jeder Anfrage an einen KI-Server Zeitpunkt, Arbeitsplatz, Modell, Werkzeug, Zahl der Tokens, Dauer und Ergebnis. **Keine Inhalte:** Weder deine Fragen noch die Antworten werden gespeichert.
- **Wozu:** Kapazitäts- und Kostenplanung der KI-Server, Erkennen von Fehlern und Fehlkonfigurationen.
- **Wie lange:** einzelne Anfragen {frist_roh} Tage, stündliche Summen {frist_stunden}. Danach werden sie automatisch gelöscht.
- **Wer sieht was:** Die Verwaltung sieht im Normalfall nur Summen und Anteile ohne Namen. Personenbezogene Zahlen gibt es nur gegen eine Begründung, die zusammen mit dem Namen der einsehenden Person im Prüfprotokoll steht. Die Einsicht gilt jeweils 30 Minuten.
- **Deine eigenen Zahlen** siehst du jederzeit unter „Meine KI-Nutzung“ in der Seitenleiste.

### Deine Rechte

Du hast das Recht auf Auskunft, Berichtigung, Löschung, Einschränkung der Verarbeitung und Widerspruch (Art. 15–21 DSGVO) sowie auf Beschwerde bei einer Aufsichtsbehörde.

**Verantwortlich und Ansprechpartner:** *bitte durch die Verwaltung eintragen (Verantwortliche Stelle, Datenschutzbeauftragte/r).*
`

const STANDARD_EN = `## Privacy notice for OTA

OTA provides you with workspaces (containers) in the browser. This involves processing personal data. This page explains which data, why, and for how long.

### Running workspaces

- **What:** your account, which workspaces you start, pause and stop (with times), the current load of your running containers (CPU, memory, disk space) and the applications installed in them.
- **Why:** operation, capacity planning, troubleshooting and security.
- **Audit log:** actions such as sign-ins, changes made by administrators and every look at personal statistics are logged.

### AI usage

The AI usage statistics are currently **{statistik}**.

- **What:** for every request to an AI server the time, workspace, model, tool, number of tokens, duration and result. **No content:** neither your questions nor the answers are stored.
- **Why:** capacity and cost planning for the AI servers, detecting errors and misconfigurations.
- **How long:** individual requests {frist_roh} days, hourly totals {frist_stunden}. After that they are deleted automatically.
- **Who sees what:** administrators normally see only totals and shares without names. Personal figures are only available with a stated reason, which is recorded in the audit log together with the name of the person looking. Each such access is valid for 30 minutes.
- **Your own figures** are always available under “My AI usage” in the sidebar.

### Your rights

You have the right of access, rectification, erasure, restriction of processing and objection (Art. 15–21 GDPR) and the right to lodge a complaint with a supervisory authority.

**Controller and contact:** *to be filled in by the administrators (controller, data protection officer).*
`

function einsetzen(text: string, h: DsgvoHinweis): string {
  const en = getLang() === 'en'
  const w: Record<string, string> = {
    frist_roh: String(h.werte.frist_roh),
    frist_stunden: h.werte.frist_stunden
      ? (en ? `${h.werte.frist_stunden} days` : `${h.werte.frist_stunden} Tage`)
      : (en ? 'without limit' : 'unbegrenzt'),
    statistik: h.werte.statistik ? (en ? 'switched on' : 'eingeschaltet') : (en ? 'switched off' : 'ausgeschaltet'),
  }
  return text.replace(/\{(frist_roh|frist_stunden|statistik)\}/g, (_, k: string) => w[k])
}

export function Dsgvo({ onToast }: { onToast: (m: string, tone?: 'ok' | 'bad') => void }) {
  useLang()
  const [h, setH] = useState<DsgvoHinweis | null>(null)
  const [fehler, setFehler] = useState('')
  const [entwurf, setEntwurf] = useState<string | null>(null)
  const [vorschau, setVorschau] = useState(false)
  const [busy, setBusy] = useState(false)

  useEffect(() => {
    api.dsgvo().then(setH).catch((err) => setFehler(err instanceof ApiError ? err.message : tr('Laden fehlgeschlagen')))
  }, [])

  const standard = getLang() === 'en' ? STANDARD_EN : STANDARD_DE
  const text = h ? (h.text || standard) : ''
  const html = useMemo(() => (h ? renderMarkdown(einsetzen(vorschau && entwurf !== null ? entwurf : text, h),
    { umbrueche: true, html: true }) : ''), [h, text, entwurf, vorschau])

  async function speichern(neu: string) {
    setBusy(true)
    try {
      // Der unveränderte mitgelieferte Text wird nicht gespeichert: So
      // folgt er weiter der Sprache und künftigen Fassungen.
      const roh = neu.trim() === STANDARD_DE.trim() || neu.trim() === STANDARD_EN.trim() ? '' : neu
      setH(await api.dsgvoSetzen(roh))
      setEntwurf(null); setVorschau(false)
      onToast(tr('Gespeichert'))
    } catch (err) {
      onToast(err instanceof ApiError ? err.message : tr('Speichern fehlgeschlagen'), 'bad')
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="wrap">
      <header className="topbar">
        <div>
          <p className="silk" style={{ marginBottom: 6 }}>{tr('Datenschutz')}</p>
          <h1 className="h-page">{tr('DSGVO')}</h1>
        </div>
        {h?.darf_schreiben && entwurf === null && (
          <button className="btn btn--primary" onClick={() => { setEntwurf(text); setVorschau(false) }}>
            {tr('Bearbeiten')}
          </button>
        )}
      </header>
      {fehler && <p className="note-warn">{fehler}</p>}
      {!h && !fehler && <p className="sub">{tr('Wird geladen…')}</p>}
      {h?.darf_schreiben && (
        <p className={h.aktiv ? 'note-info' : 'note-warn'} style={{ marginBottom: 14 }}>
          {h.aktiv
            ? tr('Die KI-Nutzungsstatistik ist eingeschaltet: Diesen Punkt sehen alle in der Seitenleiste.')
            : tr('Die KI-Nutzungsstatistik ist aus: Diesen Punkt sieht zurzeit nur die Verwaltung. Sobald sie eingeschaltet wird, sehen ihn alle.')}
          {' '}{h.text ? tr('Eigener Text der Verwaltung.') : tr('Mitgelieferter Text.')}
          {' '}{tr('Platzhalter: {frist_roh}, {frist_stunden}, {statistik}.')}
        </p>
      )}
      {h && entwurf !== null && (
        <div className="panel news__editor">
          <div className="seg" role="radiogroup" aria-label={tr('Ansicht')} style={{ margin: '0 0 10px' }}>
            {[false, true].map((v) => (
              <button key={String(v)} type="button" role="radio" aria-checked={vorschau === v}
                className={`seg__opt${vorschau === v ? ' is-on' : ''}`} onClick={() => setVorschau(v)}>
                {v ? tr('Vorschau') : tr('Schreiben')}
              </button>
            ))}
          </div>
          {!vorschau && (
            <textarea className="input news__text" rows={22} value={entwurf} spellCheck
              aria-label={tr('Text (Markdown)')} onChange={(e) => setEntwurf(e.target.value)} />
          )}
          {vorschau && <div className="md news__vorschau" dangerouslySetInnerHTML={{ __html: html }} />}
          <div className="news__knoepfe">
            <button className="btn btn--ghost" disabled={busy}
              onClick={() => { if (confirm(tr('Den mitgelieferten Text wiederherstellen?'))) void speichern('') }}>
              {tr('Mitgelieferten Text verwenden')}
            </button>
            <button className="btn btn--ghost" disabled={busy} onClick={() => { setEntwurf(null); setVorschau(false) }}>
              {tr('Abbrechen')}
            </button>
            <button className="btn btn--primary" disabled={busy} onClick={() => void speichern(entwurf)}>
              {tr('Speichern')}
            </button>
          </div>
        </div>
      )}
      {h && entwurf === null && (
        <div className="panel news__beitrag">
          <div className="md" dangerouslySetInnerHTML={{ __html: html }} />
          {h.geaendert_am && h.text && (
            <p className="news__meta" style={{ marginTop: 14 }}>
              {tr('Zuletzt geändert am {d}', { d: new Date(h.geaendert_am).toLocaleDateString(getLang() === 'en' ? 'en-GB' : 'de-DE') })}
            </p>
          )}
        </div>
      )}
    </div>
  )
}
