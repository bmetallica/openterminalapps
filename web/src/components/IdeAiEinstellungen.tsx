import { useCallback, useEffect, useState } from 'react'
import { ChipSelect, Field, Toggle } from './controls'
import {
  ApiError, api, type Group, type IdeAiModell, type IdeAiServerModell, type IdeAiStand,
} from '../lib/api'
import { t as tr } from '../lib/i18n'

/**
 * Einstellungen → IDE-AI (Handbuch Kapitel 28).
 *
 * Continue in VS Code, VSCodium und PyCharm, verbunden mit dem eigenen
 * KI-Server. Hier stehen Server, Modelle samt Kontextfenster und alles, was
 * OTA in `~/.continue/config.yaml` schreibt. Es wirkt beim nächsten Start
 * oder Fortsetzen eines Arbeitsplatzes; die Freigabe in der Firewall sofort.
 */

type Entwurf = Omit<IdeAiStand, 'api_key_gesetzt' | 'fassungen'>

const KONTEXT = 8192
const ANTWORT = 2048

function entwurfAus(s: IdeAiStand): Entwurf {
  const { api_key_gesetzt: _a, fassungen: _f, ...rest } = s
  return { ...rest, modelle: s.modelle.map((m) => ({ ...m })) }
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

  const laden = useCallback(async () => {
    try {
      const s = await api.ideAi()
      setStand(s); setE(entwurfAus(s)); setSchluessel(null)
    } catch { setStand(null) }
    try { setGruppen(await api.groups()) } catch { /* egal */ }
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
  const setze = (patch: Partial<Entwurf>) => setE({ ...e, ...patch })

  async function speichern(patch: Partial<Entwurf> = {}) {
    const body = { ...e!, ...patch, ...(schluessel !== null ? { api_key: schluessel } : {}) }
    const s = await api.ideAiEinstellen(body)
    setStand(s); setE(entwurfAus(s)); setSchluessel(null)
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
        hint={tr('Die OpenAI-Schnittstelle, mit /v1 — z. B. http://192.168.1.2:3000/v1 (vLLM) oder http://192.168.1.3:8080/v1 (llama.cpp). Ohne Pfad ergänzt OTA /v1.')}>
        <div className="row-item">
          <input value={e.url} placeholder="http://192.168.1.2:3000/v1" aria-label={tr('Adresse des KI-Servers')}
            onChange={(ev) => setze({ url: ev.target.value })} />
          <button className="btn" disabled={busy !== null || !e.url.trim()} onClick={abrufen}>
            {busy === 'abrufen' ? tr('Wird abgerufen…') : tr('Modelle abrufen')}
          </button>
        </div>
      </Field>

      <Field label={tr('API-Schlüssel')}
        hint={tr('Nur, wenn der Server einen verlangt (vLLM --api-key, llama.cpp --api-key). Er steht danach in der Konfiguration im Zuhause.')}>
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
    </div>
  )
}
