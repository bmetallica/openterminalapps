import { useCallback, useEffect, useState } from 'react'
import { ChipSelect, Field, Toggle } from './controls'
import {
  ApiError, api, type Group, type IdeAiModell, type IdeAiServerModell, type IdeAiStand,
  type IdeAiWeiterer, type KiStatus,
} from '../lib/api'
import { getLang, t as tr } from '../lib/i18n'

/**
 * Einstellungen → IDE-AI (Handbuch Kapitel 28).
 *
 * Continue in VS Code, VSCodium und PyCharm, verbunden mit dem eigenen
 * KI-Server. Hier stehen Server, Modelle samt Kontextfenster und alles, was
 * OTA in `~/.continue/config.yaml` schreibt. Es wirkt beim nächsten Start
 * oder Fortsetzen eines Arbeitsplatzes; die Freigabe in der Firewall sofort.
 */

type WeitererEntwurf = Omit<IdeAiWeiterer, 'api_key_gesetzt'> & { _vorher: string }
type Entwurf = Omit<IdeAiStand, 'api_key_gesetzt' | 'fassungen' | 'ki_url' | 'durchgang_aktiv' |
  'modelle_alle' | 'weitere' | 'extern' | 'extern_port'> & { weitere: WeitererEntwurf[] }

const KONTEXT = 8192
const ANTWORT = 2048

function entwurfAus(s: IdeAiStand): Entwurf {
  const {
    api_key_gesetzt: _a, fassungen: _f, ki_url: _k, durchgang_aktiv: _d, modelle_alle: _m,
    extern: _x, extern_port: _p, ...rest
  } = s
  return {
    ...rest, modelle: s.modelle.map((m) => ({ ...m })),
    weitere: s.weitere.map(({ api_key_gesetzt: _g, ...w }) => ({
      ...w, modelle: w.modelle.map((m) => ({ ...m })), _vorher: w.kuerzel })),
  }
}

export function IdeAiEinstellungen({ onToast }: {
  onToast: (m: string, tone?: 'ok' | 'bad') => void
}) {
  const [stand, setStand] = useState<IdeAiStand | null>(null)
  const [e, setE] = useState<Entwurf | null>(null)
  const [schluessel, setSchluessel] = useState<string | null>(null)
  const [server, setServer] = useState<IdeAiServerModell[] | null>(null)
  const [gruppen, setGruppen] = useState<Group[]>([])
  const [busy, setBusy] = useState<string | null>(null)
  const [test, setTest] = useState<Record<string, string>>({})
  // Neue Schlüssel der weiteren Server, je Zeile; null = unverändert.
  const [weitereSchluessel, setWeitereSchluessel] = useState<(string | null)[]>([])
  const [lage, setLage] = useState<KiStatus | null>(null)

  const laden = useCallback(async () => {
    try {
      const s = await api.ideAi()
      setStand(s); setE(entwurfAus(s)); setSchluessel(null)
      setWeitereSchluessel(s.weitere.map(() => null))
    } catch { setStand(null) }
    try { setGruppen(await api.groups()) } catch { /* egal */ }
    try { setLage(await api.kiStatus()) } catch { setLage(null) }
  }, [])
  useEffect(() => { void laden() }, [laden])

  async function tun(was: string, fn: () => Promise<string | void>) {
    setBusy(was)
    try {
      const m = await fn()
      if (m) onToast(m)
    } catch (err) {
      onToast(err instanceof ApiError ? err.message : tr('Hat nicht geklappt'), 'bad')
    } finally {
      setBusy(null)
    }
  }

  if (!stand || !e) return <p className="sub">{tr('Wird geladen…')}</p>

  const geaendert = JSON.stringify(entwurfAus(stand)) !== JSON.stringify(e) || schluessel !== null
    || weitereSchluessel.some((x) => x !== null)
  const setze = (patch: Partial<Entwurf>) => setE({ ...e, ...patch })

  async function speichern(patch: Partial<Entwurf> = {}) {
    const voll = { ...e!, ...patch }
    const body = {
      ...voll, ...(schluessel !== null ? { api_key: schluessel } : {}),
      weitere: voll.weitere.map(({ _vorher, ...w }, i) => ({
        ...w, kuerzel_vorher: _vorher,
        ...(weitereSchluessel[i] != null ? { api_key: weitereSchluessel[i] } : {}),
      })),
    }
    const s = await api.ideAiEinstellen(body)
    setStand(s); setE(entwurfAus(s)); setSchluessel(null)
    setWeitereSchluessel(s.weitere.map(() => null))
    try { setLage(await api.kiStatus()) } catch { /* egal */ }
  }
  function weiterenAendern(i: number, patch: Partial<WeitererEntwurf>) {
    setze({ weitere: e!.weitere.map((w, j) => (j === i ? { ...w, ...patch } : w)) })
  }

  function abrufen() {
    void tun('abrufen', async () => {
      const liste = await api.ideAiModelle(e!.url, schluessel ?? undefined)
      setServer(liste)
      return liste.length
        ? tr('{n} Modelle gefunden.', { n: liste.length })
        : tr('Der Server meldet keine Modelle.')
    })
  }

  // Die gewählten Modelle zuerst, in ihrer Reihenfolge; dann, was der Server
  // sonst noch anbietet. Ein gewähltes Modell, das der Server nicht mehr
  // nennt, bleibt sichtbar — sonst verschwände es stumm.
  const gewaehlt = new Map(e.modelle.map((m) => [m.id, m]))
  const zeilen: { id: string; info?: IdeAiServerModell; m?: IdeAiModell }[] = [
    ...e.modelle.map((m) => ({ id: m.id, m, info: server?.find((s) => s.id === m.id) })),
    ...(server ?? []).filter((s) => !gewaehlt.has(s.id)).map((s) => ({ id: s.id, info: s })),
  ]

  function waehlen(id: string, an: boolean, info?: IdeAiServerModell) {
    if (an) {
      setze({ modelle: [...e!.modelle, { id, titel: info?.titel ?? '', kontext: info?.kontext ?? KONTEXT, max_tokens: ANTWORT }],
        standard: e!.standard || id })
    } else {
      const rest = e!.modelle.filter((m) => m.id !== id)
      setze({ modelle: rest, standard: e!.standard === id ? (rest[0]?.id ?? '') : e!.standard,
        autocomplete: e!.autocomplete === id ? '' : e!.autocomplete })
    }
  }
  function aendern(id: string, patch: Partial<IdeAiModell>) {
    setze({ modelle: e!.modelle.map((m) => (m.id === id ? { ...m, ...patch } : m)) })
  }

  const gruppenNamen = gruppen.filter((g) => e.gruppen.includes(g.id)).map((g) => g.name)
  const byName = Object.fromEntries(gruppen.map((g) => [g.name, g.id]))
  const fehlen = !stand.fassungen.vscode || !stand.fassungen.jetbrains

  return (
    <div className="panel" style={{ padding: '16px 20px' }}>
      <p className="field__hint" style={{ marginTop: 0, marginBottom: 14 }}>
        {tr('Ein KI-Assistent in VS Code, VSCodium und PyCharm (Continue), verbunden mit eurem eigenen KI-Server — vLLM, llama.cpp oder jeder andere Server mit OpenAI-Schnittstelle. OTA bringt ihn aus der eigenen Paketquelle in jeden Arbeitsplatz mit passendem Editor und richtet ihn ein.')}
      </p>

      <Field label={tr('IDE-AI')}>
        <Toggle on={stand.an} name={stand.an ? tr('Eingeschaltet') : tr('Ausgeschaltet')}
          note={stand.an
            ? tr('Gilt ab dem nächsten Start oder Fortsetzen eines Arbeitsplatzes.')
            : tr('Ausgeschaltet entfernt OTA Continue beim nächsten Start wieder aus den Editoren.')}
          onChange={(v) => {
            if (busy) return
            void tun(v ? 'an' : 'aus', async () => {
              await speichern({ an: v })
              return v ? tr('IDE-AI ist eingeschaltet.') : tr('IDE-AI ist ausgeschaltet.')
            })
          }} />
        <p className={fehlen ? 'note-warn' : 'field__hint'} style={{ marginTop: 6 }}>
          {fehlen
            ? tr('Die Pakete fehlen in der Paketquelle. Auf dem Host: scripts/build-ide-ai-deb.sh --hochladen')
            : tr('In der Paketquelle: VS Code/VSCodium {v}, PyCharm/IntelliJ {j}', {
              v: stand.fassungen.vscode ?? '', j: stand.fassungen.jetbrains ?? '' })}
        </p>
      </Field>

      <Field label={tr('Adresse des KI-Servers')}
        hint={tr('Die OpenAI-Schnittstelle, mit /v1 — z. B. http://192.168.50.2:3000/v1 (vLLM) oder http://192.168.50.3:8080/v1 (llama.cpp). Ohne Pfad ergänzt OTA /v1.')}>
        <div className="row-item">
          <input value={e.url} placeholder="http://192.168.50.2:3000/v1" aria-label={tr('Adresse des KI-Servers')}
            onChange={(ev) => setze({ url: ev.target.value })} />
          <button className="btn" disabled={busy !== null || !e.url.trim()} onClick={abrufen}>
            {busy === 'abrufen' ? tr('Wird abgerufen…') : tr('Modelle abrufen')}
          </button>
        </div>
      </Field>

      <Field label={tr('Name und Kürzel')}
        hint={tr('Wie der Server in der Statistik und bei mehreren Servern heißt. Das Kürzel unterscheidet Modelle gleichen Namens auf verschiedenen Servern (kürzel/modell).')}>
        <div className="row-item">
          <input value={e.name} aria-label={tr('Name des KI-Servers')} style={{ maxWidth: 260 }}
            onChange={(ev) => setze({ name: ev.target.value })} />
          <input value={e.kuerzel} aria-label={tr('Kürzel des KI-Servers')} style={{ flex: '0 0 120px', width: 120 }}
            onChange={(ev) => setze({ kuerzel: ev.target.value })} />
        </div>
      </Field>

      <Field label={tr('API-Schlüssel')}
        hint={e.durchgang
          ? tr('Nur, wenn der Server einen verlangt (vLLM --api-key, llama.cpp --api-key). Mit dem Durchgang bleibt er im Durchgang und kommt nicht in die Arbeitsplätze.')
          : tr('Nur, wenn der Server einen verlangt (vLLM --api-key, llama.cpp --api-key). Er steht danach in der Konfiguration im Zuhause.')}>
        <div className="row-item">
          <input type="password" autoComplete="new-password" value={schluessel ?? ''}
            placeholder={stand.api_key_gesetzt ? tr('gesetzt — leer lassen, um ihn zu behalten') : tr('keiner')}
            aria-label={tr('API-Schlüssel')} onChange={(ev) => setSchluessel(ev.target.value)} />
          {stand.api_key_gesetzt && schluessel === null && (
            <button className="btn" onClick={() => setSchluessel('')}>{tr('Entfernen')}</button>
          )}
        </div>
      </Field>

      <Field label={tr('Modelle')}
        hint={tr('Was die Menschen in Continue zur Auswahl haben; das Standardmodell steht oben. Kontextfenster und Antwortlänge in Tokens — das Kontextfenster höchstens so groß, wie der Server es zulässt (vLLM --max-model-len, llama.cpp --ctx-size je Platz).')}>
        {zeilen.length === 0 ? (
          <p className="sub">{tr('Noch keine Modelle. Adresse eintragen und „Modelle abrufen“.')}</p>
        ) : (
          <div style={{ overflowX: 'auto' }}>
            <table className="tbl ide-ai__modelle">
              <thead>
                <tr>
                  <th>{tr('Anbieten')}</th><th>{tr('Standard')}</th><th>{tr('Modell')}</th>
                  <th>{tr('Kontextfenster')}</th><th>{tr('Antwortlänge')}</th><th />
                </tr>
              </thead>
              <tbody>
                {zeilen.map(({ id, m, info }) => (
                  <tr key={id}>
                    <td>
                      <input type="checkbox" checked={!!m} aria-label={tr('{m} anbieten', { m: id })}
                        onChange={(ev) => waehlen(id, ev.target.checked, info)} />
                    </td>
                    <td>
                      <input type="radio" name="ide-ai-standard" disabled={!m} checked={e.standard === id}
                        aria-label={tr('{m} als Standard', { m: id })} onChange={() => setze({ standard: id })} />
                    </td>
                    <td>
                      <span className="data">{id}</span>
                      {(info?.titel || info?.beschreibung) && (
                        <div className="sub" style={{ fontSize: 12 }}>
                          {[info.titel, info.beschreibung].filter(Boolean).join(' · ')}
                        </div>
                      )}
                      {m && !info && server && (
                        <div className="note-warn" style={{ fontSize: 12 }}>{tr('Der Server nennt dieses Modell nicht mehr.')}</div>
                      )}
                    </td>
                    <td>
                      {m && (
                        <input type="number" min={512} step={1024} value={m.kontext} style={{ width: 110 }}
                          aria-label={tr('Kontextfenster von {m}', { m: id })}
                          onChange={(ev) => aendern(id, { kontext: Number(ev.target.value) })} />
                      )}
                    </td>
                    <td>
                      {m && (
                        <input type="number" min={16} step={256} value={m.max_tokens} style={{ width: 100 }}
                          aria-label={tr('Antwortlänge von {m}', { m: id })}
                          onChange={(ev) => aendern(id, { max_tokens: Number(ev.target.value) })} />
                      )}
                    </td>
                    <td>
                      {m && stand.modelle.some((x) => x.id === id) && (
                        <button className="btn" disabled={busy !== null}
                          onClick={() => void tun(`test-${id}`, async () => {
                            const r = await api.ideAiTesten(id)
                            const text = r.antwort
                              ? tr('Antwort nach {ms} ms: {a}', { ms: r.ms, a: r.antwort })
                              : r.denkt
                                ? tr('Antwort nach {ms} ms, aber nur Überlegungen und kein Text — die Antwortlänge reicht nicht.', { ms: r.ms })
                                : tr('Leere Antwort nach {ms} ms ({g}).', { ms: r.ms, g: r.abbruch })
                            setTest({ ...test, [id]: text })
                          })}>
                          {busy === `test-${id}` ? tr('Wird gefragt…') : tr('Testen')}
                        </button>
                      )}
                      {test[id] && <div className="sub" style={{ fontSize: 12, maxWidth: 260 }}>{test[id]}</div>}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </Field>

      <Field label={tr('Vervollständigung beim Tippen')}
        hint={tr('Schlägt beim Schreiben den Rest der Zeile vor. Braucht ein schnelles Modell, am besten ein eigenes für Code; mit einem großen Chat-Modell eher aus.')}>
        <select value={e.autocomplete} aria-label={tr('Vervollständigung beim Tippen')}
          onChange={(ev) => setze({ autocomplete: ev.target.value })}>
          <option value="">{tr('Aus')}</option>
          {e.modelle.map((m) => <option key={m.id} value={m.id}>{m.titel || m.id}</option>)}
        </select>
      </Field>

      <Field label={tr('Werkzeuge (Agent-Modus)')}>
        <Toggle on={e.werkzeuge} name={e.werkzeuge ? tr('Erlaubt') : tr('Nur Chat')}
          note={tr('Das Modell darf Dateien lesen und ändern und Befehle vorschlagen — jeweils mit Bestätigung. Braucht einen Server mit Werkzeugaufrufen (vLLM: --enable-auto-tool-choice und --tool-call-parser; llama.cpp: --jinja).')}
          onChange={(v) => setze({ werkzeuge: v })} />
      </Field>

      <Field label={tr('Temperatur')} hint={tr('Leer: was der Server vorgibt. Niedrig (0,1–0,3) für Code, höher für freie Texte.')}>
        <input type="number" min={0} max={2} step={0.1} style={{ width: 110 }} aria-label={tr('Temperatur')}
          value={e.temperatur ?? ''}
          onChange={(ev) => setze({ temperatur: ev.target.value === '' ? null : Number(ev.target.value) })} />
      </Field>

      <Field label={tr('Zeitlimit')} hint={tr('Wie lange Continue auf eine Antwort wartet. Ein Server, der das Modell erst laden muss (llama-swap), braucht beim ersten Mal länger.')}>
        <div className="numfield">
          <input type="number" min={10} max={3600} value={e.zeitlimit} aria-label={tr('Zeitlimit')}
            onChange={(ev) => setze({ zeitlimit: Number(ev.target.value) })} />
          <span className="numfield__unit">{tr('Sekunden')}</span>
        </div>
      </Field>

      <Field label={tr('Firmenproxy')}>
        <Toggle on={e.ohne_proxy} name={e.ohne_proxy ? tr('Direkt zum KI-Server') : tr('Über den Firmenproxy')}
          note={tr('Ein KI-Server im eigenen Netz wird direkt angesprochen, auch wenn die Arbeitsplätze sonst über den Firmenproxy gehen.')}
          onChange={(v) => setze({ ohne_proxy: v })} />
      </Field>

      <Field label={tr('Regeln für das Modell')}
        hint={tr('Hinweise, die bei jeder Anfrage mitgehen — eine Zeile je Regel, z. B. „Antworte auf Deutsch.“')}>
        <textarea rows={3} value={e.regeln} aria-label={tr('Regeln für das Modell')} style={{ width: '100%' }}
          onChange={(ev) => setze({ regeln: ev.target.value })} />
      </Field>

      <h3 className="ide-ai__abschnitt">{tr('Weitere KI-Server')}</h3>
      <p className="field__hint" style={{ marginTop: 0 }}>
        {e.durchgang
          ? tr('Der Server oben gilt für alle. Jeder weitere kommt für die gewählten Gruppen dazu; Continue und opencode sehen die Modelle ihrer Server in einer Liste, und der Durchgang leitet jede Anfrage an den Server, zu dem das Modell gehört.')
          : tr('Weitere Server wirken nur mit dem KI-Durchgang (unten) — ohne ihn kennen die Werkzeuge nur den Server oben.')}
      </p>
      {e.weitere.map((w, i) => (
        <WeitererServer key={i} w={w} gesetzt={!!stand.weitere[i]?.api_key_gesetzt && w._vorher === stand.weitere[i]?.kuerzel}
          schluessel={weitereSchluessel[i] ?? null} busy={busy} onToast={onToast}
          onSchluessel={(v) => setWeitereSchluessel(weitereSchluessel.map((x, j) => (j === i ? v : x)))}
          onChange={(patch) => weiterenAendern(i, patch)}
          onEntfernen={() => {
            setze({ weitere: e.weitere.filter((_, j) => j !== i) })
            setWeitereSchluessel(weitereSchluessel.filter((_, j) => j !== i))
          }}
          tun={tun} gruppen={gruppen} />
      ))}
      <button className="btn" style={{ marginBottom: 18 }} onClick={() => {
        setze({ weitere: [...e.weitere, { name: '', kuerzel: `ki${e.weitere.length + 2}`, url: '', modelle: [], gruppen: [], _vorher: '' }] })
        setWeitereSchluessel([...weitereSchluessel, ''])
      }}>{tr('+ Weiteren KI-Server')}</button>

      <h3 className="ide-ai__abschnitt">{tr('KI-Durchgang und Nutzungsstatistik')}</h3>
      <Field label={tr('KI-Durchgang')}>
        <Toggle on={e.durchgang} name={e.durchgang ? tr('Eingeschaltet') : tr('Ausgeschaltet')}
          note={tr('Continue und opencode sprechen {u} an statt den Server direkt. Die Firewall leitet außerdem alles, was aus einem Arbeitsplatz an die Adresse eines KI-Servers geht, über den Durchgang — auch Skripte und alte Konfigurationen. Antwortet er nicht, geht der Verkehr wieder direkt.', { u: stand.ki_url })}
          onChange={(v) => setze({ durchgang: v, statistik: v ? e.statistik : false })} />
        {stand.durchgang && lage && (
          <p className={lage.firewall?.bereit ? 'field__hint' : 'note-warn'} style={{ marginTop: 6 }}>
            {lage.firewall?.bereit
              ? tr('Der Durchgang antwortet, die Firewall leitet um (Ziele: {n}).', { n: lage.firewall?.ziele?.length ?? 0 })
              : tr('Der Durchgang antwortet nicht — der Verkehr geht direkt zum KI-Server. docker logs ota-ki')}
          </p>
        )}
      </Field>
      <Field label={tr('Nutzungsstatistik')}>
        <Toggle on={e.statistik} name={e.statistik ? tr('Eingeschaltet') : tr('Ausgeschaltet')}
          note={tr('Zählt je Anfrage Zeit, Mensch, Arbeitsplatz, Modell und Tokens — nie Inhalte. Zu sehen unter Betrieb → KI-Nutzung. Eine Auswertung je Person kann der Zustimmung des Betriebsrats bedürfen; informiert die Menschen, bevor ihr sie einschaltet.')}
          onChange={(v) => { if (e.durchgang || !v) setze({ statistik: v }) }} />
        {!e.durchgang && <p className="field__hint" style={{ marginTop: 6 }}>{tr('Braucht den KI-Durchgang.')}</p>}
      </Field>
      <Field label={tr('Aufbewahrung')}
        hint={tr('Einzelne Anfragen für kurze Zeiträume und die Werkzeuge; Stundensummen für Graphen über Wochen. 0 bei den Stundensummen: unbegrenzt. Älteres löscht OTA einmal am Tag.')}>
        <div className="row-item" style={{ gap: 18, flexWrap: 'wrap' }}>
          <div className="numfield">
            <input type="number" min={1} max={3650} value={e.frist_roh} aria-label={tr('Aufbewahrung einzelner Anfragen')}
              onChange={(ev) => setze({ frist_roh: Number(ev.target.value) })} />
            <span className="numfield__unit">{tr('Tage einzeln')}</span>
          </div>
          <div className="numfield">
            <input type="number" min={0} max={36500} value={e.frist_stunden} aria-label={tr('Aufbewahrung der Stundensummen')}
              onChange={(ev) => setze({ frist_stunden: Number(ev.target.value) })} />
            <span className="numfield__unit">{tr('Tage Stundensummen')}</span>
          </div>
        </div>
      </Field>

      <Field label={tr('Wer darf')}
        hint={tr('Ohne Gruppe alle. Sonst nur Mitglieder dieser Gruppen; Administratoren immer.')}>
        <ChipSelect label={tr('Gruppen')} selected={gruppenNamen} options={gruppen.map((g) => g.name)}
          onChange={(namen) => setze({ gruppen: namen.map((n) => byName[n]).filter(Boolean) })} />
      </Field>

      {geaendert && (
        <div className="viewer__row" style={{ gap: 10, marginBottom: 14 }}>
          <button className="btn btn--primary" disabled={busy !== null}
            onClick={() => void tun('speichern', async () => {
              await speichern()
              return stand.an ? tr('Gespeichert — gilt ab dem nächsten Start eines Arbeitsplatzes.') : tr('Gespeichert.')
            })}>
            {busy === 'speichern' ? tr('Wird gespeichert…') : tr('Speichern')}
          </button>
          <button className="btn" disabled={busy !== null}
            onClick={() => { setE(entwurfAus(stand)); setSchluessel(null) }}>{tr('Verwerfen')}</button>
        </div>
      )}

      <p className="field__hint" style={{ marginTop: 4 }}>
        {tr('Solange IDE-AI an ist, gibt die Firewall den KI-Server für alle Arbeitsplätze frei. Wer die erste Zeile seiner ~/.continue/config.yaml löscht, pflegt die Datei selbst — Handbuch Kapitel 28.')}
      </p>

      <ExterneDienste stand={stand} busy={busy} tun={tun} onStand={setStand} />
    </div>
  )
}

/**
 * Externe Dienste (Open WebUI …) am zweiten Eingang des Durchgangs. Jeder
 * bekommt einen eigenen Schlüssel; OTA zeigt ihn genau einmal und speichert
 * nur seinen Hash. Wer fragt, sagt der Dienst in Kopfzeilen — die gelten nur
 * mit gültigem Schlüssel und gehen nicht weiter zum KI-Server.
 */
function ExterneDienste({ stand, busy, tun, onStand }: {
  stand: IdeAiStand; busy: string | null
  tun: (was: string, fn: () => Promise<string | void>) => Promise<void>
  onStand: (s: IdeAiStand) => void
}) {
  const [name, setName] = useState('Open WebUI')
  const [neu, setNeu] = useState<{ kuerzel: string; schluessel: string } | null>(null)
  const adresse = stand.extern_port ? `http://${window.location.hostname}:${stand.extern_port}/v1` : ''
  return (
    <>
      <h3 className="ide-ai__abschnitt">{tr('Externe Dienste (z. B. Open WebUI)')}</h3>
      <p className="field__hint" style={{ marginTop: 0 }}>
        {tr('Ein Dienst außerhalb der Arbeitsplätze spricht die KI über den Durchgang an: dieselben Modelle, dieselbe Gruppenregel, dieselbe Statistik. Den Schlüssel des KI-Servers kennt er nicht.')}
      </p>
      {!stand.durchgang ? (
        <p className="field__hint">{tr('Braucht den KI-Durchgang.')}</p>
      ) : (
        <>
          {adresse ? (
            <p className="field__hint">{tr('Adresse für den Dienst')}: <code>{adresse}</code></p>
          ) : (
            <p className="note-warn">
              {tr('Der Eingang ist am Host noch nicht veröffentlicht. In deploy/.env OTA_KI_EXTERN_PORT=8791 setzen und make update ausführen — das startet den Router neu, die Arbeitsplätze sind kurz ohne Netz.')}
            </p>
          )}
          {stand.extern.length > 0 && (
            <table className="tbl ide-ai__modelle" style={{ marginBottom: 10 }}>
              <thead><tr><th>{tr('Name')}</th><th>{tr('Kürzel')}</th><th>{tr('Wer fragt')}</th><th>{tr('Angelegt')}</th><th /></tr></thead>
              <tbody>
                {stand.extern.map((d) => (
                  <tr key={d.kuerzel} style={{ cursor: 'default' }}>
                    <td>{d.name}</td>
                    <td className="data">{d.kuerzel}</td>
                    <td className="sub">{d.kopf ? tr('aus den Kopfzeilen') : tr('nicht zugeordnet')}</td>
                    <td className="sub">{new Date(d.am).toLocaleDateString(getLang() === 'en' ? 'en-GB' : 'de-DE')}</td>
                    <td style={{ textAlign: 'right' }}>
                      <button className="btn btn--sm btn--ghost" disabled={busy !== null}
                        onClick={() => {
                          if (!confirm(tr('„{n}“ entfernen? Sein Schlüssel gilt dann sofort nicht mehr.', { n: d.name }))) return
                          void tun('extern', async () => {
                            onStand(await api.ideAiExternLoeschen(d.kuerzel))
                            if (neu?.kuerzel === d.kuerzel) setNeu(null)
                            return tr('Entfernt.')
                          })
                        }}>{tr('Entfernen')}</button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
          {neu && (
            <div className="note-info">
              <b>{tr('Der Schlüssel — jetzt kopieren, er wird nicht noch einmal angezeigt:')}</b>
              <div style={{ display: 'flex', gap: 8, alignItems: 'center', margin: '8px 0' }}>
                <code style={{ wordBreak: 'break-all' }}>{neu.schluessel}</code>
                <button className="btn btn--sm" onClick={() => {
                  void navigator.clipboard?.writeText(neu.schluessel)
                }}>{tr('Kopieren')}</button>
              </div>
              <div style={{ fontSize: 13 }}>
                {tr('In Open WebUI: Administration → Einstellungen → Verbindungen → OpenAI-API, Adresse {a} und diesen Schlüssel. Damit OTA weiß, wer fragt, braucht der Container von Open WebUI die Umgebungsvariable ENABLE_FORWARD_USER_INFO_HEADERS=true.', { a: adresse || 'http://<host>:<port>/v1' })}
              </div>
            </div>
          )}
          <div className="row-item" style={{ gap: 8, flexWrap: 'wrap', marginBottom: 6 }}>
            <input className="input" style={{ maxWidth: 260 }} value={name} maxLength={60}
              aria-label={tr('Name des Dienstes')} onChange={(ev) => setName(ev.target.value)} />
            <button className="btn" disabled={busy !== null || !name.trim()}
              onClick={() => void tun('extern', async () => {
                const r = await api.ideAiExternAnlegen(name.trim(), true)
                setNeu({ kuerzel: r.kuerzel, schluessel: r.schluessel }); onStand(r.stand)
              })}>{tr('+ Dienst anlegen')}</button>
          </div>
        </>
      )}
    </>
  )
}

/** Ein weiterer KI-Server: Adresse, Schlüssel, Modelle. */
function WeitererServer({ w, gesetzt, schluessel, busy, onToast, onSchluessel, onChange, onEntfernen, tun, gruppen }: {
  w: WeitererEntwurf
  gruppen: Group[]
  gesetzt: boolean
  schluessel: string | null
  busy: string | null
  onToast: (m: string, tone?: 'ok' | 'bad') => void
  onSchluessel: (v: string | null) => void
  onChange: (patch: Partial<WeitererEntwurf>) => void
  onEntfernen: () => void
  tun: (was: string, fn: () => Promise<string | void>) => Promise<void>
}) {
  const [angebot, setAngebot] = useState<IdeAiServerModell[] | null>(null)
  const [antwort, setAntwort] = useState<Record<string, string>>({})
  const gewaehlt = new Map(w.modelle.map((m) => [m.id, m]))
  const zeilen = [
    ...w.modelle.map((m) => ({ id: m.id, m: m as IdeAiModell | undefined })),
    ...(angebot ?? []).filter((x) => !gewaehlt.has(x.id)).map((x) => ({ id: x.id, m: undefined })),
  ]
  void onToast
  return (
    <div className="ide-ai__weiterer">
      <div className="row-item" style={{ flexWrap: 'wrap' }}>
        <input value={w.name} placeholder={tr('Name, z. B. GPU-Server 2')} aria-label={tr('Name des KI-Servers')}
          style={{ maxWidth: 220 }} onChange={(ev) => onChange({ name: ev.target.value })} />
        <input value={w.kuerzel} aria-label={tr('Kürzel des KI-Servers')} style={{ flex: '0 0 110px', width: 110 }}
          onChange={(ev) => onChange({ kuerzel: ev.target.value })} />
        <button className="btn btn--halt" onClick={onEntfernen}>{tr('Entfernen')}</button>
      </div>
      <div className="row-item" style={{ marginTop: 8 }}>
        <input value={w.url} placeholder="http://192.168.50.4:8000/v1" aria-label={tr('Adresse des KI-Servers')}
          onChange={(ev) => onChange({ url: ev.target.value })} />
        <button className="btn" disabled={busy !== null || !w.url.trim()}
          onClick={() => void tun(`abrufen-${w.kuerzel}`, async () => {
            const liste = await api.ideAiModelle(w.url, schluessel ?? undefined, w._vorher || undefined)
            setAngebot(liste)
            return liste.length ? tr('{n} Modelle gefunden.', { n: liste.length }) : tr('Der Server meldet keine Modelle.')
          })}>
          {busy === `abrufen-${w.kuerzel}` ? tr('Wird abgerufen…') : tr('Modelle abrufen')}
        </button>
      </div>
      <div className="row-item" style={{ marginTop: 8 }}>
        <input type="password" autoComplete="new-password" value={schluessel ?? ''}
          placeholder={gesetzt ? tr('gesetzt — leer lassen, um ihn zu behalten') : tr('API-Schlüssel (keiner)')}
          aria-label={tr('API-Schlüssel')} onChange={(ev) => onSchluessel(ev.target.value)} />
        {gesetzt && schluessel === null && (
          <button className="btn" onClick={() => onSchluessel('')}>{tr('Entfernen')}</button>
        )}
      </div>
      <div style={{ marginTop: 10 }}>
        <ChipSelect label={tr('Gruppen')} selected={gruppen.filter((g) => w.gruppen.includes(g.id)).map((g) => g.name)}
          options={gruppen.map((g) => g.name)}
          onChange={(namen) => onChange({ gruppen: namen.map((n) => gruppen.find((g) => g.name === n)?.id).filter((x): x is string => !!x) })} />
        <p className="field__hint" style={{ marginTop: 4 }}>
          {w.gruppen.length
            ? tr('Nur Mitglieder dieser Gruppen bekommen diesen Server zusätzlich zum ersten; Administratoren immer. Erreichbar ist er dann nur über den Durchgang.')
            : tr('Ohne Gruppe bekommen ihn alle, die IDE-AI oder opencode haben.')}
        </p>
      </div>
      {zeilen.length > 0 && (
        <div style={{ overflowX: 'auto', marginTop: 8 }}>
          <table className="tbl ide-ai__modelle">
            <thead>
              <tr><th>{tr('Anbieten')}</th><th>{tr('Modell')}</th><th>{tr('Kontextfenster')}</th><th>{tr('Antwortlänge')}</th><th /></tr>
            </thead>
            <tbody>
              {zeilen.map(({ id, m }) => (
                <tr key={id}>
                  <td>
                    <input type="checkbox" checked={!!m} aria-label={tr('{m} anbieten', { m: id })}
                      onChange={(ev) => {
                        const info = angebot?.find((x) => x.id === id)
                        onChange({ modelle: ev.target.checked
                          ? [...w.modelle, { id, titel: info?.titel ?? '', kontext: info?.kontext ?? KONTEXT, max_tokens: ANTWORT }]
                          : w.modelle.filter((x) => x.id !== id) })
                      }} />
                  </td>
                  <td><span className="data">{id}</span></td>
                  <td>{m && (
                    <input type="number" min={512} step={1024} value={m.kontext} style={{ width: 110 }}
                      aria-label={tr('Kontextfenster von {m}', { m: id })}
                      onChange={(ev) => onChange({ modelle: w.modelle.map((x) => (x.id === id ? { ...x, kontext: Number(ev.target.value) } : x)) })} />
                  )}</td>
                  <td>{m && (
                    <input type="number" min={16} step={256} value={m.max_tokens} style={{ width: 100 }}
                      aria-label={tr('Antwortlänge von {m}', { m: id })}
                      onChange={(ev) => onChange({ modelle: w.modelle.map((x) => (x.id === id ? { ...x, max_tokens: Number(ev.target.value) } : x)) })} />
                  )}</td>
                  <td>
                    {m && w._vorher && (
                      <button className="btn" disabled={busy !== null}
                        onClick={() => void tun(`test-${w.kuerzel}-${id}`, async () => {
                          const r = await api.ideAiTesten(id, w._vorher)
                          setAntwort({ ...antwort, [id]: r.antwort
                            ? tr('Antwort nach {ms} ms: {a}', { ms: r.ms, a: r.antwort })
                            : tr('Leere Antwort nach {ms} ms ({g}).', { ms: r.ms, g: r.abbruch }) })
                        })}>
                        {busy === `test-${w.kuerzel}-${id}` ? tr('Wird gefragt…') : tr('Testen')}
                      </button>
                    )}
                    {antwort[id] && <div className="sub" style={{ fontSize: 12, maxWidth: 260 }}>{antwort[id]}</div>}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  )
}
