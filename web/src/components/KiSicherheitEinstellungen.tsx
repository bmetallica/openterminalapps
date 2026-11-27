import { useCallback, useEffect, useState } from 'react'
import { Field, Segmented, Toggle } from './controls'
import { ApiError, api, type KiSicherheitEinstellungen as Einst, type KiSicherheitStand, type KiSicherheitTest } from '../lib/api'
import { t as tr } from '../lib/i18n'

/**
 * Einstellungen → KI-Sicherheit (Handbuch Kapitel 41).
 *
 * Der KI-Durchgang prüft, was ein KI-Assistent liest (Werkzeug-Ergebnisse,
 * Dokumente), auf Prompt Injection: unsichtbare Zeichen, bekannte Muster und
 * auf Wunsch ein Modell auf einem eigenen KI-Server. Gezählt werden nur Fälle,
 * nie Inhalte (Betrieb → KI-Sicherheit).
 */
export function KiSicherheitEinstellungen({ onToast }: { onToast: (m: string, tone?: 'ok' | 'bad') => void }) {
  const [stand, setStand] = useState<KiSicherheitStand | null>(null)
  const [test, setTest] = useState<KiSicherheitTest | null>(null)
  const [busy, setBusy] = useState(false)

  const laden = useCallback(async () => {
    try { setStand(await api.kiSicherheit()) } catch { setStand(null) }
  }, [])
  useEffect(() => { void laden() }, [laden])

  async function setze(patch: Partial<Einst>, note = tr('Gespeichert.')) {
    setBusy(true)
    try {
      setStand(await api.kiSicherheitEinstellen(patch))
      onToast(note)
    } catch (err) {
      onToast(err instanceof ApiError ? err.message : tr('Hat nicht geklappt'), 'bad')
    } finally {
      setBusy(false)
    }
  }

  async function testen() {
    if (!stand?.modell) return
    setBusy(true); setTest(null)
    try {
      setTest(await api.kiSicherheitTest(stand.modell))
    } catch (err) {
      onToast(err instanceof ApiError ? err.message : tr('Hat nicht geklappt'), 'bad')
    } finally {
      setBusy(false)
    }
  }

  if (!stand) return <p className="sub">{tr('Wird geladen…')}</p>

  return (
    <div className="panel" style={{ padding: '16px 20px' }}>
      <p className="field__hint" style={{ marginTop: 0, marginBottom: 14 }}>
        {tr('Der KI-Durchgang prüft, was ein KI-Assistent bei der Arbeit liest: Dateien, Befehlsausgaben, Webseiten und Dokumente. Steht darin eine versteckte Anweisung an den Assistenten (Prompt Injection), wird sie erkannt. Was der Mensch selbst eintippt, bleibt ungeprüft. Gespeichert werden nur Zähler, nie Inhalte.')}
      </p>
      {!stand.aktiv && (
        <p className="note-warn" style={{ marginBottom: 14 }}>
          {tr('Der KI-Durchgang ist nicht aktiv (Einstellungen → IDE-AI). Ohne ihn prüft niemand.')}
        </p>
      )}

      <Field label={tr('KI-Sicherheit')}>
        <Toggle on={stand.an} name={stand.an ? tr('Eingeschaltet') : tr('Ausgeschaltet')}
          note={tr('Gilt sofort für alle Anfragen über den KI-Durchgang, auch für externe Dienste wie Open WebUI.')}
          onChange={(v) => { if (!busy) void setze({ an: v }, v ? tr('KI-Sicherheit ist eingeschaltet.') : tr('KI-Sicherheit ist ausgeschaltet.')) }} />
      </Field>

      {stand.an && (
        <>
          <Field label={tr('Betriebsart')}
            hint={tr('Beobachten zählt nur. Warnen setzt vor einen auffälligen Inhalt einen Hinweis an das Modell, ihn als Daten zu behandeln; die Arbeit läuft weiter. Sperren weist die Anfrage ab. Empfehlung: einige Tage beobachten, dann warnen.')}>
            <Segmented label={tr('Betriebsart')} value={stand.betriebsart}
              options={[
                { value: 'beobachten', label: tr('Beobachten') },
                { value: 'warnen', label: tr('Warnen') },
                { value: 'sperren', label: tr('Sperren'), tone: 'halt' },
              ]}
              onChange={(v) => void setze({ betriebsart: v })} />
          </Field>

          <Field label={tr('Stufe 1: unsichtbare Zeichen entfernen')}
            hint={tr('Unicode-Tag-Zeichen, Steuerzeichen für die Schreibrichtung und Ketten von Zeichen ohne Breite. Ein Mensch sieht sie nicht, das Modell liest sie. Sie werden immer entfernt, unabhängig von der Betriebsart.')}>
            <Toggle on={stand.unsichtbar} name={stand.unsichtbar ? tr('Eingeschaltet') : tr('Ausgeschaltet')}
              onChange={(v) => void setze({ unsichtbar: v })} />
          </Field>

          <Field label={tr('Stufe 2: bekannte Muster')}
            hint={tr('Formulierungen und Techniken, die in echten Dokumenten kaum vorkommen: „Ignoriere alle vorherigen Anweisungen“, gefälschte Systemprompts, Hinweise an die KI, Geheimhaltung vor dem Nutzer, Versand von Zugangsdaten, Datenabfluss über Bilder, versteckte HTML-Kommentare. Deutsch und Englisch.')}>
            <Toggle on={stand.muster} name={stand.muster ? tr('Eingeschaltet') : tr('Ausgeschaltet')}
              onChange={(v) => void setze({ muster: v })} />
          </Field>

          <Field label={tr('Stufe 3: Prüfung durch ein Modell')}
            hint={tr('Ein Sprachmodell auf einem eigenen KI-Server beurteilt jeden neuen Inhalt. Es erkennt auch Umschreibungen, kostet aber Rechenzeit. Beim Beobachten läuft die Prüfung im Hintergrund; beim Warnen und Sperren wartet die Anfrage darauf, höchstens bis zum Zeitlimit.')}>
            <Toggle on={stand.modell_an} name={stand.modell_an ? tr('Eingeschaltet') : tr('Ausgeschaltet')}
              onChange={(v) => {
                if (v && !stand.modell) { onToast(tr('Bitte zuerst ein Modell wählen.'), 'bad'); return }
                void setze({ modell_an: v })
              }} />
          </Field>

          <Field label={tr('Modell für die Prüfung')}
            hint={tr('Jedes Modell der angebundenen KI-Server. Ein kleines, schnelles Modell genügt meist; „Testen“ zeigt, ob es zuverlässig urteilt und wie lange es braucht.')}>
            <div className="viewer__row" style={{ gap: 10, flexWrap: 'wrap' }}>
              <select value={stand.modell} aria-label={tr('Modell für die Prüfung')}
                onChange={(ev) => { setTest(null); void setze({ modell: ev.target.value }) }}>
                <option value="">{tr('Modell wählen…')}</option>
                {stand.modelle.map((m) => <option key={m.id} value={m.id}>{m.titel || m.id}</option>)}
              </select>
              <button className="btn" disabled={busy || !stand.modell} onClick={() => void testen()}>
                {busy ? tr('Wird geprüft…') : tr('Testen')}
              </button>
            </div>
            {test && (
              <div className={test.ok ? 'note-info' : 'note-warn'} style={{ marginTop: 8 }}>
                <p style={{ margin: 0 }}>
                  {test.ok ? tr('Das Modell urteilt bei beiden Proben richtig.') : tr('Das Modell urteilt nicht zuverlässig. Ein anderes Modell wählen oder die Antwort prüfen.')}
                </p>
                <p style={{ margin: '6px 0 0' }}>
                  {tr('Probe mit versteckter Anweisung: {e} in {ms} ms', {
                    e: test.angriff.fehler ?? (test.angriff.richtig ? tr('erkannt') : tr('nicht erkannt')), ms: test.angriff.ms })}
                </p>
                <p style={{ margin: '2px 0 0' }}>
                  {tr('Harmlose Installationsanleitung: {e} in {ms} ms', {
                    e: test.harmlos.fehler ?? (test.harmlos.richtig ? tr('richtig als harmlos') : tr('Fehlalarm')), ms: test.harmlos.ms })}
                </p>
              </div>
            )}
          </Field>

          {stand.modell_an && (
            <>
              <Field label={tr('Was das Modell prüft')}
                hint={tr('Alle neuen Inhalte: gründlich, aber jede gelesene Datei kostet eine Anfrage an den KI-Server. Nur Auffälliges: nur, was Stufe 1 oder 2 gemeldet hat; das Modell bestätigt oder entkräftet.')}>
                <Segmented label={tr('Was das Modell prüft')} value={stand.umfang}
                  options={[
                    { value: 'alle', label: tr('Alle neuen Inhalte') },
                    { value: 'auffaellig', label: tr('Nur Auffälliges') },
                  ]}
                  onChange={(v) => void setze({ umfang: v })} />
              </Field>
              <Field label={tr('Zeitlimit je Prüfung')}
                hint={tr('Antwortet das Modell nicht rechtzeitig, geht die Anfrage ungeprüft weiter und es wird als Fehler gezählt.')}>
                <div className="numfield">
                  <input type="number" min={3} max={120} step={1} aria-label={tr('Zeitlimit je Prüfung')}
                    defaultValue={stand.zeitlimit}
                    onBlur={(e) => { const n = Number(e.target.value); if (n !== stand.zeitlimit) void setze({ zeitlimit: n }) }} />
                  <span className="numfield__unit">{tr('Sekunden')}</span>
                </div>
              </Field>
            </>
          )}

          <Field label={tr('Fallberichte')}
            hint={tr('Zu jedem Fall ein kurzer Bericht: das Werkzeug (Datei lesen, Befehl, Webseite), die Quelle (Dateiname, Adresse, Befehl) und je Treffer ein Ausschnitt von etwa 300 Zeichen um die Fundstelle. Passwörter, Tokens, Schlüssel und E-Mail-Adressen werden vorher unkenntlich gemacht, Heimatverzeichnisse als ~ geschrieben. Keine Person, kein Arbeitsplatz. Einen Bericht öffnet die Verwaltung nur mit Begründung; jede Einsicht steht im Prüfprotokoll. Weil hier Inhalte gespeichert werden: vor dem Einschalten mit Datenschutz und Personalvertretung abstimmen.')}>
            <Toggle on={stand.fallberichte} name={stand.fallberichte ? tr('Eingeschaltet') : tr('Ausgeschaltet')}
              onChange={(v) => {
                if (busy) return
                if (v && !window.confirm(tr('Fallberichte speichern Ausschnitte aus gelesenen Inhalten. Mit Datenschutz und Personalvertretung abgestimmt?'))) return
                void setze({ fallberichte: v }, v ? tr('Fallberichte sind eingeschaltet.') : tr('Fallberichte sind ausgeschaltet.'))
              }} />
          </Field>
          {stand.fallberichte && (
            <Field label={tr('Aufbewahrung der Fallberichte')}
              hint={tr('Danach löscht OTA einen Bericht von selbst. Empfehlung: 30 Tage. Das reicht, um einem Fall auch über Urlaub hinweg nachzugehen, und hält den Bestand an Inhalten klein. Höchstens {n} Tage.', { n: stand.fallbericht_tage_max })}>
              <div className="numfield">
                <input type="number" min={1} max={stand.fallbericht_tage_max} step={1} aria-label={tr('Aufbewahrung der Fallberichte')}
                  defaultValue={stand.fallbericht_tage}
                  onBlur={(e) => { const n = Number(e.target.value); if (n !== stand.fallbericht_tage) void setze({ fallbericht_tage: n }) }} />
                <span className="numfield__unit">{tr('Tage')}</span>
              </div>
            </Field>
          )}
        </>
      )}
    </div>
  )
}
