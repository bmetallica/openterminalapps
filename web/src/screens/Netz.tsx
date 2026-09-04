import { useEffect, useState } from 'react'
import { Field } from '../components/controls'
import {
  ApiError, api,
  type Grundregel, type NetzFreigabe, type NetzProfil, type NetzRegel,
  type NetzStufe, type NetzZeile, type Template, type User,
} from '../lib/api'
import { t, useLang } from '../lib/i18n'

/**
 * Das Netz der Arbeitsplätze — Profile, globale Freigaben, Übersicht.
 *
 * Jeder Arbeitsplatz hängt an einem eigenen Kabel, alle Kabel enden im Router,
 * und der Router ist der einzige Weg nach draussen. Was hier eingestellt wird,
 * sagt ihm, was er durchlässt; durchgesetzt wird es dort und nicht hier
 * (`firewall.md`).
 */

const STUFEN: { wert: NetzStufe; text: string; hinweis: string }[] = [
  { wert: 'abgeschottet', text: 'Abgeschottet',
    hinweis: 'Nur was OTA selbst braucht. Kein Internet, kein Firmennetz.' },
  { wert: 'internet', text: 'Internet',
    hinweis: 'Internet ja, Firmennetz nein. Die Vorgabe.' },
  { wert: 'aus', text: 'Aus',
    hinweis: 'Der Router lässt alles durch. Verlangt eine Begründung.' },
]

function bytesKurz(n: number): string {
  if (!n) return '—'
  const einheiten = ['B', 'KB', 'MB', 'GB', 'TB']
  let i = 0
  let wert = n
  while (wert >= 1024 && i < einheiten.length - 1) { wert /= 1024; i += 1 }
  return `${wert.toFixed(wert < 10 && i > 0 ? 1 : 0)} ${einheiten[i]}`
}

/** Eine Freigabeliste — dieselbe Form für Profile und für die globale Liste. */
function Regeln({ regeln, onChange, disabled }: {
  regeln: NetzRegel[]
  onChange: (r: NetzRegel[]) => void
  disabled?: boolean
}) {
  const setze = (i: number, teil: Partial<NetzRegel>) =>
    onChange(regeln.map((r, k) => (k === i ? { ...r, ...teil } : r)))

  return (
    <div className="netz__regeln">
      {regeln.length === 0 && (
        <p className="sub">{t('Keine Freigaben — es gilt allein die Stufe.')}</p>
      )}
      {regeln.map((regel, i) => (
        <div key={i} className="netz__regel">
          <input type="text" value={regel.ziel} disabled={disabled}
            placeholder={t('192.168.66.10, 10.20.0.0/16 oder git.firma.de')}
            aria-label={t('Ziel')}
            onChange={(e) => setze(i, { ziel: e.target.value })} />
          <input type="text" value={regel.ports} disabled={disabled}
            placeholder="443" aria-label={t('Ports')} style={{ maxWidth: 120 }}
            onChange={(e) => setze(i, { ports: e.target.value })} />
          <select value={regel.protokoll} disabled={disabled}
            aria-label={t('Protokoll')} style={{ maxWidth: 110 }}
            onChange={(e) => setze(i, { protokoll: e.target.value as NetzRegel['protokoll'] })}>
            <option value="beide">{t('beide')}</option>
            <option value="tcp">TCP</option>
            <option value="udp">UDP</option>
          </select>
          <input type="text" value={regel.notiz} disabled={disabled}
            placeholder={t('Wofür? (Pflicht)')} aria-label={t('Notiz')}
            onChange={(e) => setze(i, { notiz: e.target.value })} />
          <button className="btn btn--sm btn--halt" disabled={disabled}
            onClick={() => onChange(regeln.filter((_, k) => k !== i))}>
            {t('Weg')}
          </button>
        </div>
      ))}
      <button className="btn btn--sm" disabled={disabled}
        onClick={() => onChange([...regeln, {
          ziel: '', ports: '443', protokoll: 'beide', notiz: '',
        }])}>
        {t('Freigabe hinzufügen')}
      </button>
    </div>
  )
}

export function Netz({ onToast }: { onToast: (m: string, tone?: 'ok' | 'bad') => void }) {
  useLang()
  const [profile, setProfile] = useState<NetzProfil[] | null>(null)
  const [global, setGlobal] = useState<NetzRegel[] | null>(null)
  const [zeilen, setZeilen] = useState<NetzZeile[] | null>(null)
  const [offen, setOffen] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)
  const [nat, setNat] = useState<{ zeile: NetzZeile; port: string; tage: string; notiz: string } | null>(null)
  // Alle Freigaben — auch die zu Arbeitsplätzen, die gerade nicht laufen.
  // Genau deshalb eine eigene Liste: Eine Freigabe gilt für einen Menschen an
  // einem Arbeitsplatz und überlebt den Feierabend. Wer sie nur in der
  // Übersicht der laufenden Sitzungen zeigte, könnte sie danach weder sehen
  // noch entfernen — und keine neue für einen ruhenden Arbeitsplatz anlegen.
  const [freigaben, setFreigaben] = useState<NetzFreigabe[]>([])
  const [nutzer, setNutzer] = useState<User[]>([])
  const [vorlagen, setVorlagen] = useState<Template[]>([])
  const [neu, setNeu] = useState({ user: '', template: '', port: '8080', tage: '30', notiz: '' })
  // Was jede Sitzung ohnehin darf. Sichtbar, aber nicht änderbar — die Werte
  // kommen aus der Umgebung und aus dem Aufbau.
  const [grund, setGrund] = useState<Grundregel[]>([])
  const [grundOffen, setGrundOffen] = useState(false)
  const [neuesProfil, setNeuesProfil] = useState('')

  const laden = () => {
    void api.netProfiles().then(setProfile).catch(() => setProfile([]))
    void api.netzGlobal().then(setGlobal).catch(() => setGlobal([]))
    void api.netzUebersicht().then(setZeilen).catch(() => setZeilen([]))
    void api.netzFreigaben().then(setFreigaben).catch(() => setFreigaben([]))
    void api.netzGrundregeln().then(setGrund).catch(() => setGrund([]))
    void api.users().then(setNutzer).catch(() => setNutzer([]))
    void api.templates().then(setVorlagen).catch(() => setVorlagen([]))
  }
  useEffect(laden, [])
  // Die Übersicht zeigt Zähler — die sollen sich bewegen.
  useEffect(() => {
    const uhr = setInterval(() => { void api.netzUebersicht().then(setZeilen).catch(() => {}) }, 15000)
    return () => clearInterval(uhr)
  }, [])

  async function tun(was: () => Promise<unknown>, note: string) {
    setBusy(true)
    try {
      await was()
      onToast(note)
      laden()
    } catch (err) {
      onToast(err instanceof ApiError ? err.message : t('Fehlgeschlagen'), 'bad')
    } finally {
      setBusy(false)
    }
  }

  // Ein eigenes Feld statt `window.prompt`: Der Rest der Anwendung fragt
  // nirgends über einen Browser-Dialog nach einem Namen, und ein Dialog lässt
  // sich weder beschriften noch übersetzen.
  const anlegen = () => {
    const name = neuesProfil.trim()
    if (!name) return
    void tun(() => api.createNetProfile({
      name, description: '', stufe: 'internet', regeln: [], begruendung: '',
    }), t('Profil angelegt')).then(() => setNeuesProfil(''))
  }

  if (!profile || !global || !zeilen) {
    return <div className="wrap"><p className="sub">{t('Wird geladen…')}</p></div>
  }

  return (
    <div className="wrap">
      <header className="topbar">
        <div>
          <p className="silk" style={{ marginBottom: 6 }}>{t('Verwaltung')}</p>
          <h1 className="h-page">{t('Netz')}</h1>
        </div>
      </header>

      <p className="note-info" style={{ maxWidth: 720 }}>
        {t('Jeder Arbeitsplatz hängt in einem eigenen Netz und erreicht die Aussenwelt nur über den Router. Ohne Freigabe gilt: kein Firmennetz, keine Nachbarsitzung, kein Wirt.')}
      </p>

      {/* --------------------------------------------- Grundregelsatz */}
      <div className="section__head" style={{ marginTop: 26 }}>
        <span className="silk">{t('Was ohne Zutun gilt')}</span><span className="section__rule" />
      </div>
      <div className="panel" style={{ padding: '14px 20px', maxWidth: 900 }}>
        <div className="viewer__row">
          <button className="btn btn--sm btn--ghost"
            onClick={() => setGrundOffen(!grundOffen)}>{grundOffen ? '▾' : '▸'}</button>
          <span>{t('{n} Regeln, die für jeden Arbeitsplatz gelten — unabhängig vom Profil',
            { n: grund.length })}</span>
        </div>
        {grundOffen && (
          <>
            <p className="sub" style={{ margin: '12px 0' }}>
              {t('Diese Regeln sind abgeleitet, nicht eingetragen: Sie kommen aus der Umgebung (deploy/.env) und aus dem Aufbau selbst. Hier zu sehen, geändert werden sie dort, wo sie herkommen.')}
            </p>
            <div style={{ overflowX: 'auto' }}>
              <table className="tbl">
                <thead>
                  <tr>
                    <th>{t('Ziel')}</th><th>{t('Ports')}</th><th>{t('Protokoll')}</th>
                    <th>{t('Warum')}</th><th>{t('Herkunft')}</th>
                  </tr>
                </thead>
                <tbody>
                  {grund.map((r, i) => (
                    <tr key={i}>
                      <td className="data">{r.ziel}</td>
                      <td className="data">{r.ports}</td>
                      <td>{r.protokoll}</td>
                      <td className="sub">{r.grund}</td>
                      <td className="data sub">{r.herkunft}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </>
        )}
      </div>

      {/* ------------------------------------------------ Netzübersicht */}
      <div className="section__head" style={{ marginTop: 26 }}>
        <span className="silk">{t('Wer läuft gerade wo')}</span><span className="section__rule" />
      </div>

      {zeilen.length === 0
        ? <p className="sub">{t('Zurzeit läuft kein Arbeitsplatz.')}</p>
        : (
          <div className="panel" style={{ padding: '4px 0', overflowX: 'auto' }}>
            <table className="tbl">
              <thead>
                <tr>
                  <th>{t('Nutzer')}</th><th>{t('Arbeitsplatz')}</th><th>{t('Adresse')}</th>
                  <th>{t('Profil')}</th><th>{t('Verkehr')}</th><th>{t('Abgewiesen')}</th>
                  <th>{t('Freigaben nach aussen')}</th><th />
                </tr>
              </thead>
              <tbody>
                {zeilen.map((z) => (
                  <tr key={z.session_id}>
                    <td>{z.user}</td>
                    <td>{z.template}</td>
                    <td className="data">{z.adresse || '—'}</td>
                    <td>
                      {z.profil}
                      <span className={`pill pill--${z.stufe === 'aus' ? 'halt' : z.stufe === 'abgeschottet' ? 'live' : 'paused'}`}
                        style={{ marginLeft: 8 }}>
                        {STUFEN.find((s) => s.wert === z.stufe)?.text ?? z.stufe}
                      </span>
                    </td>
                    <td className="data">{bytesKurz(z.bytes)}</td>
                    {/* Abgewiesene Pakete sind das interessanteste Signal: Ein
                        Arbeitsplatz, der plötzlich hundert Ziele anspricht, ist
                        ein Portscan und sieht genau so aus. */}
                    <td className={`data${z.verworfen > 1000 ? ' is-warn' : ''}`}>
                      {z.verworfen || '—'}
                    </td>
                    <td>
                      {z.forwards.length === 0
                        ? <span className="sub">—</span>
                        : z.forwards.map((f) => (
                          <div key={f.id} className="data" style={{ whiteSpace: 'nowrap' }}>
                            {f.aussen} → {f.innen}
                            {f.expires_at && (
                              <span className="sub" style={{ marginLeft: 6 }}>
                                {f.abgelaufen
                                  ? t('abgelaufen')
                                  : t('bis {datum}', { datum: new Date(f.expires_at).toLocaleDateString() })}
                              </span>
                            )}
                            <button className="btn btn--sm btn--ghost" disabled={busy}
                              style={{ marginLeft: 8 }}
                              onClick={() => void tun(() => api.deleteNetzFreigabe(f.id),
                                t('Freigabe entfernt'))}>
                              {t('Weg')}
                            </button>
                          </div>
                        ))}
                    </td>
                    <td>
                      <button className="btn btn--sm" disabled={busy}
                        onClick={() => setNat({ zeile: z, port: '8080', tage: '30', notiz: '' })}>
                        {t('+ NAT')}
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}

      {nat && (
        <div className="panel" style={{ padding: '18px 20px', marginTop: 12, maxWidth: 620 }}>
          <p className="silk" style={{ marginBottom: 10 }}>
            {t('Port von {user} nach aussen freigeben', { user: nat.zeile.user })}
          </p>
          <Field label={t('Port im Arbeitsplatz')}
            hint={t('Der Port, auf dem die eigene Anwendung im Arbeitsplatz lauscht.')}>
            <input type="number" min={1} max={65535} value={nat.port}
              onChange={(e) => setNat({ ...nat, port: e.target.value })} />
          </Field>
          <Field label={t('Für wie viele Tage')}
            hint={t('0 heisst unbefristet. Der Ablauf wird durchgesetzt, nicht nur angezeigt.')}>
            <input type="number" min={0} max={3650} value={nat.tage}
              onChange={(e) => setNat({ ...nat, tage: e.target.value })} />
          </Field>
          <Field label={t('Wofür')}
            hint={t('Pflicht. Ohne Notiz traut sich später niemand, die Freigabe wieder zu entfernen.')}>
            <input type="text" value={nat.notiz}
              onChange={(e) => setNat({ ...nat, notiz: e.target.value })} />
          </Field>
          <div className="viewer__row" style={{ marginTop: 12 }}>
            <button className="btn btn--sm btn--primary" disabled={busy}
              onClick={() => {
                const zeile = nat.zeile
                void tun(() => api.createNetzFreigabe({
                  // Die Freigabe hängt am Menschen und am Arbeitsplatz, nicht
                  // an der Sitzung: Sonst wäre sie nach dem nächsten Feierabend
                  // weg, denn jede Sitzung bekommt ein neues Netz.
                  user_id: zeile.user_id, template_id: zeile.template_id,
                  innen: Number(nat.port), protokoll: 'tcp',
                  notiz: nat.notiz, tage: Number(nat.tage),
                }), t('Freigabe angelegt')).then(() => setNat(null))
              }}>
              {t('Freigeben')}
            </button>
            <button className="btn btn--sm btn--ghost" onClick={() => setNat(null)}>
              {t('Abbrechen')}
            </button>
          </div>
        </div>
      )}

      {/* ------------------------------------------------ Portfreigaben */}
      <div className="section__head" style={{ marginTop: 30 }}>
        <span className="silk">{t('Portfreigaben über den Wirt')}</span>
        <span className="section__rule" />
      </div>
      <p className="sub" style={{ maxWidth: 720, marginBottom: 12 }}>
        {t('Eine Freigabe gilt für einen Menschen an einem Arbeitsplatz — nicht für eine Sitzung. Sie bleibt bestehen, wenn er Feierabend macht, und greift beim nächsten Start wieder auf die dann gültige Adresse.')}
      </p>

      {freigaben.length > 0 && (
        <div className="panel" style={{ padding: '4px 0', overflowX: 'auto', marginBottom: 12 }}>
          <table className="tbl">
            <thead>
              <tr>
                <th>{t('Nutzer')}</th><th>{t('Arbeitsplatz')}</th>
                <th>{t('Aussen')}</th><th>{t('Innen')}</th>
                <th>{t('Bis')}</th><th>{t('Wofür')}</th><th>{t('Zustand')}</th><th />
              </tr>
            </thead>
            <tbody>
              {freigaben.map((f) => (
                <tr key={f.id}>
                  <td>{f.user}</td>
                  <td>{f.template}</td>
                  <td className="data">{f.aussen}</td>
                  <td className="data">{f.innen}/{f.protokoll}</td>
                  <td className="data">
                    {f.expires_at ? new Date(f.expires_at).toLocaleDateString() : t('unbefristet')}
                  </td>
                  <td className="sub">{f.notiz}</td>
                  <td>
                    <span className={`pill pill--${f.abgelaufen ? 'halt' : f.aktiv ? 'live' : 'paused'}`}>
                      {f.abgelaufen ? t('abgelaufen')
                        : f.aktiv ? t('greift') : t('wartet auf Start')}
                    </span>
                  </td>
                  <td>
                    <button className="btn btn--sm btn--halt" disabled={busy}
                      onClick={() => void tun(() => api.deleteNetzFreigabe(f.id),
                        t('Freigabe entfernt'))}>
                      {t('Weg')}
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      <div className="panel" style={{ padding: '18px 20px', maxWidth: 900 }}>
        <p className="silk" style={{ marginBottom: 10 }}>{t('Neue Freigabe')}</p>
        <div className="netz__regel">
          <select value={neu.user} aria-label={t('Nutzer')}
            onChange={(e) => setNeu({ ...neu, user: e.target.value })}>
            <option value="">{t('Nutzer wählen…')}</option>
            {nutzer.map((u) => <option key={u.id} value={u.id}>{u.username}</option>)}
          </select>
          <select value={neu.template} aria-label={t('Arbeitsplatz')}
            onChange={(e) => setNeu({ ...neu, template: e.target.value })}>
            <option value="">{t('Arbeitsplatz wählen…')}</option>
            {vorlagen.map((v) => (
              <option key={v.id} value={v.id}>{v.friendly_name}</option>
            ))}
          </select>
          <input type="number" min={1} max={65535} value={neu.port}
            aria-label={t('Port im Arbeitsplatz')}
            onChange={(e) => setNeu({ ...neu, port: e.target.value })} />
          <input type="text" value={neu.notiz} placeholder={t('Wofür? (Pflicht)')}
            aria-label={t('Wofür')}
            onChange={(e) => setNeu({ ...neu, notiz: e.target.value })} />
          <button className="btn btn--sm btn--primary"
            disabled={busy || !neu.user || !neu.template || !neu.notiz.trim()}
            onClick={() => void tun(() => api.createNetzFreigabe({
              user_id: neu.user, template_id: neu.template,
              innen: Number(neu.port), protokoll: 'tcp',
              notiz: neu.notiz, tage: Number(neu.tage),
            }), t('Freigabe angelegt')).then(() => setNeu({
              ...neu, port: '8080', notiz: '',
            }))}>
            {t('Freigeben')}
          </button>
        </div>
        <p className="sub" style={{ marginTop: 8 }}>
          {t('Der Port auf dem Wirt wird aus dem Bereich vergeben, den der Router beim Start veröffentlicht hat. Gültig für {n} Tage — 0 heisst unbefristet.', { n: neu.tage })}
        </p>
      </div>

      {/* --------------------------------------------- Globale Freigaben */}
      <div className="section__head" style={{ marginTop: 30 }}>
        <span className="silk">{t('Freigaben für alle Arbeitsplätze')}</span>
        <span className="section__rule" />
      </div>
      <div className="panel" style={{ padding: '18px 20px', maxWidth: 900 }}>
        <p className="sub" style={{ marginBottom: 12 }}>
          {t('Der Dateiserver, das interne Rechenzentrum, der Paketspiegel — was jeder erreichen soll, steht hier und nicht in jedem Profil.')}
        </p>
        <Regeln regeln={global} onChange={setGlobal} disabled={busy} />
        <button className="btn btn--sm btn--primary" disabled={busy} style={{ marginTop: 12 }}
          onClick={() => void tun(() => api.saveNetzGlobal(global), t('Globale Freigaben gesetzt'))}>
          {t('Speichern')}
        </button>
      </div>

      {/* ------------------------------------------------------ Profile */}
      <div className="section__head" style={{ marginTop: 30 }}>
        <span className="silk">{t('Netzprofile')}</span><span className="section__rule" />
      </div>

      {profile.map((p) => (
        <div key={p.id} className="panel" style={{ padding: '14px 20px', marginBottom: 10, maxWidth: 900 }}>
          <div className="viewer__row">
            <button className="btn btn--sm btn--ghost"
              onClick={() => setOffen(offen === p.id ? null : p.id)}>
              {offen === p.id ? '▾' : '▸'}
            </button>
            <strong>{p.name}</strong>
            <span className={`pill pill--${p.stufe === 'aus' ? 'halt' : p.stufe === 'abgeschottet' ? 'live' : 'paused'}`}>
              {STUFEN.find((s) => s.wert === p.stufe)?.text ?? p.stufe}
            </span>
            <span className="sub">{t('{n} Freigaben', { n: p.regeln.length })}</span>
            <span className="sub" style={{ marginLeft: 'auto' }}>
              {p.in_benutzung > 0
                ? t('{n} Arbeitsplätze', { n: p.in_benutzung })
                : t('nicht zugewiesen')}
            </span>
            <button className="btn btn--sm btn--halt" disabled={busy || p.in_benutzung > 0}
              title={p.in_benutzung > 0 ? t('Gilt noch für Arbeitsplätze.') : undefined}
              onClick={() => void tun(() => api.deleteNetProfile(p.id), t('Profil gelöscht'))}>
              {t('Löschen')}
            </button>
          </div>

          {offen === p.id && (
            <div style={{ marginTop: 14 }}>
              <Field label={t('Stufe')}
                hint={STUFEN.find((s) => s.wert === p.stufe)?.hinweis ?? ''}>
                <select value={p.stufe}
                  onChange={(e) => setProfile(profile.map((q) => (q.id === p.id
                    ? { ...q, stufe: e.target.value as NetzStufe } : q)))}>
                  {STUFEN.map((s) => (
                    <option key={s.wert} value={s.wert}>{t(s.text)}</option>
                  ))}
                </select>
              </Field>
              {p.stufe === 'aus' && (
                <Field label={t('Begründung')}
                  hint={t('Warum braucht dieser Arbeitsplatz keine Einschränkung? Steht im Protokoll.')}>
                  <input type="text" value={p.begruendung}
                    onChange={(e) => setProfile(profile.map((q) => (q.id === p.id
                      ? { ...q, begruendung: e.target.value } : q)))} />
                </Field>
              )}
              <Regeln regeln={p.regeln} disabled={busy}
                onChange={(r) => setProfile(profile.map((q) => (q.id === p.id
                  ? { ...q, regeln: r } : q)))} />
              <button className="btn btn--sm btn--primary" disabled={busy} style={{ marginTop: 12 }}
                onClick={() => void tun(() => api.saveNetProfile(p.id, {
                  name: p.name, description: p.description, stufe: p.stufe,
                  regeln: p.regeln, begruendung: p.begruendung,
                }), t('Profil gespeichert'))}>
                {t('Speichern')}
              </button>
            </div>
          )}
        </div>
      ))}

      <div className="panel" style={{ padding: '14px 20px', maxWidth: 900 }}>
        <div className="viewer__row">
          <input type="text" value={neuesProfil} style={{ maxWidth: 280 }}
            placeholder={t('Name des neuen Profils')} aria-label={t('Name des neuen Profils')}
            onChange={(e) => setNeuesProfil(e.target.value)}
            onKeyDown={(e) => { if (e.key === 'Enter') anlegen() }} />
          <button className="btn btn--sm" disabled={busy || !neuesProfil.trim()}
            onClick={anlegen}>
            {t('Profil anlegen')}
          </button>
          <span className="sub">
            {t('Beginnt mit der Stufe „Internet" und ohne Freigaben — beides danach änderbar.')}
          </span>
        </div>
      </div>
    </div>
  )
}
