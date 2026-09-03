import { useEffect, useRef, useState } from 'react'
import { CapacityFader, Field } from '../components/controls'
import { ApiError, api, type GlobalSettings } from '../lib/api'
import { VORGABE, setzeMarke, useMarke } from '../lib/branding'
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
        <span className="silk">{t('Marke')}</span><span className="section__rule" />
      </div>
      <div style={{ maxWidth: 620 }}>
        <MarkeAendern onToast={onToast} />
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

/**
 * Name, Farbe und Zeichen der Anlage.
 *
 * Bewusst der letzte Abschnitt und bewusst klein gehalten: Das hier ist kein
 * Baukasten für Gestaltung. Drei Dinge entscheiden, ob sich eine Anlage nach
 * „unser Werkzeug" anfühlt — wie sie heisst, welche Farbe sie hat und welches
 * Zeichen oben steht. Alles darüber hinaus wäre ein zweites Stylesheet mit
 * einer Oberfläche davor.
 *
 * Der Name wird beim Verlassen des Feldes gespeichert, die Farbe beim
 * Loslassen des Wählers. Ein „Speichern"-Knopf für zwei Felder wäre eine
 * Schaltfläche, die nur daran erinnert, dass man sie noch drücken muss.
 */
function MarkeAendern({ onToast }: { onToast: (m: string, tone?: 'ok' | 'bad') => void }) {
  const marke = useMarke()
  const [busy, setBusy] = useState(false)
  const [name, setName] = useState(marke.name)
  const dateiwahl = useRef<HTMLInputElement>(null)

  async function tun(was: () => Promise<typeof marke>, note: string) {
    setBusy(true)
    try {
      setzeMarke(await was())
      onToast(note)
    } catch (err) {
      onToast(err instanceof ApiError ? err.message : t('Speichern fehlgeschlagen'), 'bad')
      setName(marke.name)
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="panel" style={{ padding: '18px 20px' }}>
      <Field
        label={t('Name der Anlage')}
        hint={t('Steht im Reiter des Browsers, auf der Anmeldemaske und in der Verknüpfung auf dem Desktop.')}>
        <input type="text" maxLength={48} value={name} disabled={busy}
          aria-label={t('Name der Anlage')}
          onChange={(e) => setName(e.target.value)}
          onBlur={() => {
            const neu = name.trim()
            if (!neu || neu === marke.name) { setName(marke.name); return }
            void tun(() => api.saveBranding({ name: neu }),
              t('Die Anlage heisst jetzt {name}', { name: neu }))
          }} />
      </Field>

      <Field
        label={t('Akzentfarbe')}
        hint={t('Die eine Farbe, die aus der Fläche heraussticht: aktive Schaltflächen, Regler, Markierungen. Für das helle Gewand wird sie automatisch abgedunkelt.')}>
        <div className="viewer__row">
          <input type="color" value={marke.accent} disabled={busy}
            aria-label={t('Akzentfarbe')}
            style={{ width: 52, height: 34, padding: 2 }}
            onChange={(e) => void tun(
              () => api.saveBranding({ accent: e.target.value }),
              t('Akzentfarbe gesetzt'))} />
          <span className="data">{marke.accent}</span>
          {marke.accent.toUpperCase() !== VORGABE.accent && (
            <button className="btn btn--sm btn--ghost" disabled={busy}
              onClick={() => void tun(
                () => api.saveBranding({ accent: VORGABE.accent }),
                t('Akzentfarbe zurückgesetzt'))}>
              {t('Zurücksetzen')}
            </button>
          )}
        </div>
      </Field>

      <Field
        label={t('Zeichen')}
        hint={t('SVG, PNG, WebP oder JPEG, höchstens 512 KB. Ein quadratisches Zeichen passt am besten — es steht auch klein in der Leiste und im Reiter des Browsers.')}>
        <div className="viewer__row">
          {marke.logo_url && (
            <img src={marke.logo_url} alt=""
              style={{ width: 44, height: 44, objectFit: 'contain' }} />
          )}
          <button className="btn btn--sm" disabled={busy}
            onClick={() => dateiwahl.current?.click()}>
            {marke.has_logo ? t('Anderes Zeichen') : t('Zeichen hochladen')}
          </button>
          {marke.has_logo && (
            <button className="btn btn--sm btn--ghost" disabled={busy}
              onClick={() => void tun(() => api.clearLogo(), t('Zeichen entfernt'))}>
              {t('Entfernen')}
            </button>
          )}
          <input ref={dateiwahl} type="file" hidden
            accept="image/svg+xml,image/png,image/webp,image/jpeg"
            aria-label={t('Zeichen hochladen')}
            onChange={(e) => {
              const datei = e.target.files?.[0]
              // Das Feld zurücksetzen, sonst löst dieselbe Datei beim zweiten
              // Mal kein `change` mehr aus — und es sieht aus, als täte der
              // Knopf nichts.
              e.target.value = ''
              if (datei) void tun(() => api.uploadLogo(datei), t('Zeichen übernommen'))
            }} />
        </div>
      </Field>
    </div>
  )
}
