import { useEffect, useState } from 'react'
import { CapacityFader, Field } from '../components/controls'
import { ApiError, api, type GlobalSettings } from '../lib/api'
import { idleLabel } from '../lib/format'
import { t, useLang } from '../lib/i18n'

/**
 * Was im laufenden Betrieb umstellbar ist.
 *
 * Zurzeit genau eine Sache — deshalb ist dieser Bildschirm kurz. Er bekommt
 * trotzdem einen eigenen Platz und keinen Winkel in „Betrieb": Die Frist gilt
 * für die ganze Anlage, nicht für eine Session, und wer sie sucht, sucht sie
 * unter Einstellungen.
 */
export function Settings({ onToast }: { onToast: (m: string, tone?: 'ok' | 'bad') => void }) {
  useLang()
  const [data, setData] = useState<GlobalSettings | null>(null)
  const [failed, setFailed] = useState<string | null>(null)

  useEffect(() => {
    api.settings().then(setData)
      .catch((err) => setFailed(err instanceof ApiError ? err.message : t('Laden fehlgeschlagen')))
  }, [])

  async function save(minutes: number) {
    const before = data
    // Sofort anzeigen: Ein Regler, der erst nach der Antwort springt, fühlt
    // sich kaputt an. Bei einem Fehler geht er zurück.
    setData((d) => (d ? { ...d, auth_idle_minutes: minutes } : d))
    try {
      setData(await api.saveSettings({ auth_idle_minutes: minutes }))
      onToast(t('Anmeldefrist auf {value} gesetzt', { value: idleLabel(minutes) }))
    } catch (err) {
      setData(before)
      onToast(err instanceof ApiError ? err.message : t('Speichern fehlgeschlagen'), 'bad')
    }
  }

  if (failed) {
    return (
      <div className="wrap"><div className="empty">
        <p className="empty__title">{t('Konnte nicht geladen werden')}</p>
        <p className="empty__body">{failed}</p>
      </div></div>
    )
  }
  if (!data) return <div className="wrap"><p className="sub">{t('Wird geladen…')}</p></div>

  const steps = data.auth_idle_steps
  const index = Math.max(0, steps.indexOf(data.auth_idle_minutes))

  return (
    <div className="wrap">
      <header className="topbar">
        <div>
          <p className="silk" style={{ marginBottom: 6 }}>{t('Verwaltung')}</p>
          <h1 className="h-page">{t('Einstellungen')}</h1>
        </div>
      </header>

      <div className="section__head">
        <span className="silk">{t('Anmeldung')}</span><span className="section__rule" />
      </div>

      <div className="panel" style={{ padding: '18px 20px', maxWidth: 620 }}>
        <Field
          label={t('Abmelden nach Untätigkeit')}
          hint={t('Die Frist läuft nur, solange niemand etwas tut. Wer in einer Session arbeitet, wird nicht abgemeldet — jede Anfrage schiebt sie nach vorn.')}>
          <CapacityFader
            aria-label={t('Abmelden nach Untätigkeit')}
            value={index} min={0} max={steps.length - 1} step={1}
            format={(i) => idleLabel(steps[i])}
            ticks={steps.map((_, i) => i)}
            tickLabel={(i) => idleLabel(steps[i])}
            onChange={(i) => void save(steps[i])} />
        </Field>

        <p className="note-info" style={{ marginTop: 6 }}>
          {t('Gilt ab der nächsten Anmeldung und für jede Sitzung, die danach weiterläuft. Bereits ausgestellte Zugänge behalten ihre alte Frist bis zu ihrer nächsten Verlängerung.')}
        </p>
      </div>
    </div>
  )
}
