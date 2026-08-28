import { useEffect, useState } from 'react'
import { CapacityFader, Field } from '../components/controls'
import { ApiError, api, type GlobalSettings } from '../lib/api'
import { idleLabel } from '../lib/format'
import { Directory } from './Directory'
import { t, useLang } from '../lib/i18n'

/**
 * Was im laufenden Betrieb umstellbar ist.
 *
 * Alles hier gilt für die ganze Anlage, nicht für eine Session — deshalb ein
 * eigener Platz und kein Winkel in „Betrieb".
 */
export function Settings({ onToast }: { onToast: (m: string, tone?: 'ok' | 'bad') => void }) {
  useLang()
  const [data, setData] = useState<GlobalSettings | null>(null)
  const [failed, setFailed] = useState<string | null>(null)

  useEffect(() => {
    api.settings().then(setData)
      .catch((err) => setFailed(err instanceof ApiError ? err.message : t('Laden fehlgeschlagen')))
  }, [])

  async function save(patch: Partial<GlobalSettings>, note: string) {
    const before = data
    // Sofort anzeigen: Ein Regler, der erst nach der Antwort springt, fühlt
    // sich kaputt an. Bei einem Fehler geht er zurück.
    setData((d) => (d ? { ...d, ...patch } : d))
    try {
      setData(await api.saveSettings(patch))
      onToast(note)
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
            onChange={(i) => void save({ auth_idle_minutes: steps[i] },
              t('Anmeldefrist auf {value} gesetzt', { value: idleLabel(steps[i]) }))} />
        </Field>

        <p className="note-info" style={{ marginTop: 6 }}>
          {t('Gilt ab der nächsten Anmeldung und für jede Sitzung, die danach weiterläuft. Bereits ausgestellte Zugänge behalten ihre alte Frist bis zu ihrer nächsten Verlängerung.')}
        </p>
      </div>

      <div className="section__head" style={{ marginTop: 26 }}>
        <span className="silk">{t('Platz')}</span><span className="section__rule" />
      </div>

      <div className="panel" style={{ padding: '18px 20px', maxWidth: 620 }}>
        <Field
          label={t('Kontingent je Zuhause')}
          hint={t('Wie viel ein Nutzer in seinem Home belegen darf. Wer darüber liegt, startet keine neue Session mehr — laufende bleiben unberührt. 0 schaltet die Grenze ab.')}>
          <div className="numfield">
            <input type="number" min={0} max={10000} step={1}
              aria-label={t('Kontingent je Zuhause')}
              value={data.profile_quota_gb}
              onChange={(e) => setData({ ...data, profile_quota_gb: Number(e.target.value) })}
              onBlur={(e) => void save({ profile_quota_gb: Number(e.target.value) },
                Number(e.target.value) === 0
                  ? t('Kontingent abgeschaltet')
                  : t('Kontingent auf {n} GB gesetzt', { n: e.target.value }))} />
            <span className="numfield__unit">{t('GB')}</span>
          </div>
        </Field>

        <Field
          label={t('Untergrenze für den freien Plattenplatz')}
          hint={t('Fällt der freie Platz auf dem Host darunter, startet keine Session mehr. Ein volles Dateisystem bringt laufende Arbeitsplätze zum Stehen — das hier ist die Bremse davor. 0 schaltet sie ab.')}>
          <div className="numfield">
            <input type="number" min={0} max={10000} step={1}
              aria-label={t('Untergrenze für den freien Plattenplatz')}
              value={data.disk_floor_gb}
              onChange={(e) => setData({ ...data, disk_floor_gb: Number(e.target.value) })}
              onBlur={(e) => void save({ disk_floor_gb: Number(e.target.value) },
                Number(e.target.value) === 0
                  ? t('Untergrenze abgeschaltet')
                  : t('Untergrenze auf {n} GB gesetzt', { n: e.target.value }))} />
            <span className="numfield__unit">{t('GB')}</span>
          </div>
        </Field>

        <p className="note-info" style={{ marginTop: 6 }}>
          {t('Beides wirkt beim Start einer Session, nicht beim Schreiben einer Datei. Es ist kein Dateisystem-Kontingent — wer schon drin ist, kann weiter schreiben.')}
        </p>
      </div>

      <div className="section__head" style={{ marginTop: 30 }}>
        <span className="silk">{t('Verzeichnis (LDAP / Active Directory)')}</span>
        <span className="section__rule" />
      </div>
      <div style={{ maxWidth: 620 }}>
        <Directory onToast={onToast} />
      </div>
    </div>
  )
}
