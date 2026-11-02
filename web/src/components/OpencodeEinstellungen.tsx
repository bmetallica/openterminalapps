import { useCallback, useEffect, useState } from 'react'
import { ChipSelect, Field, Toggle } from './controls'
import { ApiError, api, type Group, type OpencodeMcp, type OpencodeStand, type OpencodeVorschau, type User } from '../lib/api'
import { t as tr } from '../lib/i18n'

/**
 * Einstellungen → opencode (Handbuch Kapitel 38).
 *
 * opencode in jedem berechtigten Arbeitsplatz, mit dem KI-Server und den
 * Modellen aus IDE-AI, einem Zusatz zum Systemprompt (global und je Gruppe)
 * und den MCP-Servern der Erweiterungen. OTA schreibt dafür opencodes
 * verwaltete Konfiguration nach /etc/opencode/; was der Mensch selbst in
 * ~/.config/opencode einstellt, kommt dazu.
 */

type Entwurf = Pick<OpencodeStand, 'gruppen' | 'standard' | 'klein' | 'prompt' | 'prompt_gruppen' | 'zusatz' | 'mcp'>

function entwurfAus(s: OpencodeStand): Entwurf {
  return { gruppen: [...s.gruppen], standard: s.standard, klein: s.klein, prompt: s.prompt,
    prompt_gruppen: { ...s.prompt_gruppen }, zusatz: s.zusatz,
    mcp: s.mcp.map((m) => ({ ...m, gruppen: [...m.gruppen], befehl: m.befehl ? [...m.befehl] : undefined })) }
}

export function OpencodeEinstellungen({ onToast }: {
  onToast: (m: string, tone?: 'ok' | 'bad') => void
}) {
  const [stand, setStand] = useState<OpencodeStand | null>(null)
  const [e, setE] = useState<Entwurf | null>(null)
  const [gruppen, setGruppen] = useState<Group[]>([])
  const [nutzer, setNutzer] = useState<User[]>([])
  const [neueGruppe, setNeueGruppe] = useState('')
  const [vorschau, setVorschau] = useState<OpencodeVorschau | null>(null)
  const [fuer, setFuer] = useState<string>('')
  const [busy, setBusy] = useState<string | null>(null)

  const laden = useCallback(async () => {
    try {
      const s = await api.opencode()
      setStand(s); setE(entwurfAus(s))
    } catch { setStand(null) }
    try { setGruppen(await api.groups()) } catch { /* egal */ }
    try { setNutzer(await api.users()) } catch { /* egal */ }
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

  const geaendert = JSON.stringify(entwurfAus(stand)) !== JSON.stringify(e)
  const setze = (patch: Partial<Entwurf>) => setE({ ...e, ...patch })
  const gruppenNamen = gruppen.filter((g) => e.gruppen.includes(g.id)).map((g) => g.name)
  const byName = Object.fromEntries(gruppen.map((g) => [g.name, g.id]))
  const name = (gid: string) => gruppen.find((g) => g.id === gid)?.name ?? stand.gruppen_namen[gid] ?? gid
  const ohneServer = !stand.ki_url || stand.modelle.length === 0

  async function speichern(patch: Partial<OpencodeStand> = {}) {
    const s = await api.opencodeEinstellen({ ...e!, ...patch })
    setStand(s); setE(entwurfAus(s))
  }

  return (
    <div className="panel" style={{ padding: '16px 20px' }}>
      <p className="field__hint" style={{ marginTop: 0, marginBottom: 14 }}>
        {tr('opencode, der KI-Assistent im Terminal, in jedem berechtigten Arbeitsplatz — mit dem KI-Server und den Modellen aus IDE-AI. OTA bringt ihn aus der eigenen Paketquelle mit und schreibt seine verwaltete Konfiguration; eigene Einstellungen der Menschen in ~/.config/opencode kommen dazu.')}
      </p>

      <Field label={tr('opencode')}>
        <Toggle on={stand.an} name={stand.an ? tr('Eingeschaltet') : tr('Ausgeschaltet')}
          note={stand.an
            ? tr('Gilt ab dem nächsten Start oder Fortsetzen eines Arbeitsplatzes.')
            : tr('Ausgeschaltet entfernt OTA beim nächsten Start seine Konfiguration; das Programm bleibt.')}
          onChange={(v) => {
            if (busy) return
            void tun(v ? 'an' : 'aus', async () => {
              await speichern({ an: v })
              return v ? tr('opencode ist eingeschaltet.') : tr('opencode ist ausgeschaltet.')
            })
          }} />
        <p className={!stand.fassung || ohneServer ? 'note-warn' : 'field__hint'} style={{ marginTop: 6 }}>
          {ohneServer
            ? tr('Erst unter IDE-AI den KI-Server und mindestens ein Modell eintragen — opencode nutzt dieselben.')
            : !stand.fassung
              ? tr('Das Paket fehlt in der Paketquelle. Auf dem Host: scripts/build-opencode-deb.sh --hochladen')
              : tr('In der Paketquelle: opencode {v} · KI-Server {u}', { v: stand.fassung, u: stand.ki_url })}
        </p>
      </Field>

      <Field label={tr('Standardmodell')}
        hint={tr('Leer: das Standardmodell aus IDE-AI. Wer in ~/.config/opencode selbst eines gesetzt hat, behält seines.')}>
        <select value={e.standard} aria-label={tr('Standardmodell')} onChange={(ev) => setze({ standard: ev.target.value })}>
          <option value="">{tr('wie IDE-AI ({m})', { m: stand.ki_standard || '—' })}</option>
          {stand.modelle.map((m) => <option key={m.id} value={m.id}>{m.titel || m.id}</option>)}
        </select>
      </Field>

      <Field label={tr('Kleines Modell')}
        hint={tr('Für Titel und Zusammenfassungen. Ein schnelles Modell ohne Denken spart Wartezeit; leer: wie das Standardmodell.')}>
        <select value={e.klein} aria-label={tr('Kleines Modell')} onChange={(ev) => setze({ klein: ev.target.value })}>
          <option value="">{tr('wie das Standardmodell')}</option>
          {stand.modelle.map((m) => <option key={m.id} value={m.id}>{m.titel || m.id}</option>)}
        </select>
      </Field>

      <Field label={tr('Zusatz zum Systemprompt')}
        hint={tr('Geht bei jeder Anfrage an das Modell mit, für alle. Platzhalter: {anzeigename}, {nutzer}, {vorlage}, {datum}. Eine Vorgabe, keine Sicherheitsgrenze: Ein Projekt kann eigene Anweisungen mitbringen.')}>
        <textarea rows={4} value={e.prompt} aria-label={tr('Zusatz zum Systemprompt')} style={{ width: '100%' }}
          placeholder={tr('z. B. Antworte auf Deutsch. Keine Zugangsdaten in Code oder Commits.')}
          onChange={(ev) => setze({ prompt: ev.target.value })} />
      </Field>

      <Field label={tr('Je Gruppe')}
        hint={tr('Zusätzlich für Mitglieder dieser Gruppen, z. B. ein Styleguide. Wer in mehreren ist, bekommt alle Texte.')}>
        {Object.keys(e.prompt_gruppen).map((gid) => (
          <div key={gid} style={{ marginBottom: 10 }}>
            <div className="viewer__row" style={{ justifyContent: 'space-between' }}>
              <span className="silk">{name(gid)}</span>
              <button className="btn btn--ghost" onClick={() => {
                const rest = { ...e.prompt_gruppen }; delete rest[gid]; setze({ prompt_gruppen: rest })
              }}>{tr('Entfernen')}</button>
            </div>
            <textarea rows={3} value={e.prompt_gruppen[gid]} style={{ width: '100%' }}
              aria-label={tr('Zusatz für {g}', { g: name(gid) })}
              onChange={(ev) => setze({ prompt_gruppen: { ...e.prompt_gruppen, [gid]: ev.target.value } })} />
          </div>
        ))}
        <div className="row-item">
          <select value={neueGruppe} aria-label={tr('Gruppe hinzufügen')} onChange={(ev) => setNeueGruppe(ev.target.value)}>
            <option value="">{tr('Gruppe wählen…')}</option>
            {gruppen.filter((g) => !(g.id in e.prompt_gruppen)).map((g) => <option key={g.id} value={g.id}>{g.name}</option>)}
          </select>
          <button className="btn" disabled={!neueGruppe} onClick={() => {
            setze({ prompt_gruppen: { ...e.prompt_gruppen, [neueGruppe]: '' } }); setNeueGruppe('')
          }}>{tr('Hinzufügen')}</button>
        </div>
      </Field>

      <Field label={tr('Zusätzliche Konfiguration')}
        hint={tr('JSON, das OTA in die verwaltete Konfiguration einmischt und das Vorrang hat — für alles, was hier fehlt: reasoning, chat_template_kwargs, eigene Modelle für Compaction und Titel. mcp, plugin und instructions setzt OTA selbst.')}>
        <textarea rows={5} value={e.zusatz} aria-label={tr('Zusätzliche Konfiguration')} spellCheck={false}
          style={{ width: '100%', fontFamily: 'var(--mono, monospace)', fontSize: 12.5 }}
          placeholder={'{\n  "provider": { "ota": { "models": { "Hauptmodell": { "reasoning": true } } } },\n  "agent": { "compaction": { "model": "ota/Hauptmodell-nothink" } }\n}'}
          onChange={(ev) => setze({ zusatz: ev.target.value })} />
      </Field>

      <Field label={tr('Wer darf')}
        hint={tr('Ohne Gruppe alle. Sonst nur Mitglieder dieser Gruppen; Administratoren immer.')}>
        <ChipSelect label={tr('Gruppen')} selected={gruppenNamen} options={gruppen.map((g) => g.name)}
          onChange={(namen) => setze({ gruppen: namen.map((n) => byName[n]).filter(Boolean) })} />
      </Field>

      <Field label={tr('Weitere MCP-Server')}
        hint={tr('Werkzeuge für opencode, etwa ein Wiki, ein Ticketsystem oder GitHub. Entfernt über eine Adresse oder lokal als Befehl im Arbeitsplatz. Der Schlüssel bleibt auf dem Server und kommt als eigene Datei in den Arbeitsplatz. Je Server lässt sich festlegen, welche Gruppen ihn bekommen.')}>
        {e.mcp.map((m, i) => (
          <McpZeile key={i} m={m} gruppen={gruppen}
            aendern={(neu) => setze({ mcp: e.mcp.map((x, j) => (j === i ? neu : x)) })}
            weg={() => setze({ mcp: e.mcp.filter((_, j) => j !== i) })} />
        ))}
        <button className="btn" onClick={() => setze({ mcp: [...e.mcp, {
          name: '', typ: 'entfernt', an: true, gruppen: [], url: '', kopf: 'Authorization',
          praefix: 'Bearer ', freigeben: true }] })}>{tr('MCP-Server hinzufügen')}</button>
      </Field>

      <Field label={tr('Vorschau')}
        hint={tr('So sähe es für diesen Menschen aus — mit den Änderungen, die noch nicht gespeichert sind.')}>
        <div className="row-item">
          <select value={fuer} aria-label={tr('Vorschau für')} onChange={(ev) => setFuer(ev.target.value)}>
            <option value="">{tr('für mich')}</option>
            {nutzer.map((u) => <option key={u.id} value={u.id}>{u.display_name || u.username}</option>)}
          </select>
          <button className="btn" disabled={busy !== null} onClick={() => void tun('vorschau', async () => {
            setVorschau(await api.opencodeVorschau(fuer || null, e))
          })}>{busy === 'vorschau' ? tr('Wird erstellt…') : tr('Vorschau')}</button>
        </div>
        {vorschau && (
          <div style={{ marginTop: 10 }}>
            {!vorschau.berechtigt && <p className="note-warn">{tr('Dieser Mensch bekommt opencode nicht (ausgeschaltet oder nicht in einer berechtigten Gruppe).')}</p>}
            <p className={vorschau.tokens_geschaetzt > stand.prompt_warnung_tokens ? 'note-warn' : 'field__hint'}>
              {tr('Prompt-Zusatz: etwa {n} Tokens je Anfrage.', { n: vorschau.tokens_geschaetzt })}
              {vorschau.tokens_geschaetzt > stand.prompt_warnung_tokens && ' ' + tr('Das ist viel für lokale Modelle mit kleinem Kontext.')}
            </p>
            <p className="silk" style={{ margin: '8px 0 4px' }}>/etc/opencode/ota-anweisungen.md</p>
            <pre className="data" style={{ whiteSpace: 'pre-wrap', maxHeight: 260, overflow: 'auto' }}>{vorschau.anweisungen}</pre>
            <p className="silk" style={{ margin: '8px 0 4px' }}>/etc/opencode/opencode.jsonc</p>
            <pre className="data" style={{ whiteSpace: 'pre-wrap', maxHeight: 260, overflow: 'auto' }}>{vorschau.config}</pre>
          </div>
        )}
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
          <button className="btn" disabled={busy !== null} onClick={() => setE(entwurfAus(stand))}>{tr('Verwerfen')}</button>
        </div>
      )}

      <p className="field__hint" style={{ marginTop: 4 }}>
        {tr('Selbst installiertes opencode (Installationsskript, npm) lenkt OTA auf seine Fassung um; das Original bleibt als *.vor-ota liegen. Handbuch Kapitel 38.')}
      </p>
    </div>
  )
}

function McpZeile({ m, gruppen, aendern, weg }: {
  m: OpencodeMcp
  gruppen: Group[]
  aendern: (m: OpencodeMcp) => void
  weg: () => void
}) {
  const setze = (patch: Partial<OpencodeMcp>) => aendern({ ...m, ...patch })
  const namen = gruppen.filter((g) => m.gruppen.includes(g.id)).map((g) => g.name)
  const byName = Object.fromEntries(gruppen.map((g) => [g.name, g.id]))
  return (
    <div className="panel" style={{ padding: '10px 14px', marginBottom: 10, background: 'var(--well)' }}>
      <div className="row-item" style={{ flexWrap: 'wrap', gap: 8 }}>
        <input value={m.name} placeholder={tr('Name, z. B. wiki')} aria-label={tr('Name des MCP-Servers')}
          style={{ width: 160 }} onChange={(ev) => setze({ name: ev.target.value.toLowerCase() })} />
        <select value={m.typ} aria-label={tr('Art')} onChange={(ev) => setze({ typ: ev.target.value as OpencodeMcp['typ'] })}>
          <option value="entfernt">{tr('Entfernt (Adresse)')}</option>
          <option value="lokal">{tr('Lokal (Befehl)')}</option>
        </select>
        <label className="sub" style={{ display: 'flex', gap: 6, alignItems: 'center' }}>
          <input type="checkbox" checked={m.an} onChange={(ev) => setze({ an: ev.target.checked })} />{tr('an')}
        </label>
        <button className="btn btn--ghost" onClick={weg}>{tr('Entfernen')}</button>
      </div>
      {m.typ === 'entfernt' ? (
        <>
          <input value={m.url ?? ''} placeholder="https://mcp.firma.de/mcp" aria-label={tr('Adresse')}
            style={{ width: '100%', marginTop: 8 }} onChange={(ev) => setze({ url: ev.target.value })} />
          <div className="row-item" style={{ marginTop: 8, flexWrap: 'wrap', gap: 8 }}>
            <input value={m.kopf ?? 'Authorization'} aria-label={tr('Kopfzeile für den Schlüssel')} style={{ width: 160 }}
              title={tr('Kopfzeile für den Schlüssel')} onChange={(ev) => setze({ kopf: ev.target.value })} />
            <input value={m.praefix ?? ''} aria-label={tr('Vor dem Schlüssel')} style={{ width: 90 }}
              title={tr('Vor dem Schlüssel')} onChange={(ev) => setze({ praefix: ev.target.value })} />
            <label className="sub" style={{ display: 'flex', gap: 6, alignItems: 'center' }}>
              <input type="checkbox" checked={m.freigeben ?? true} onChange={(ev) => setze({ freigeben: ev.target.checked })} />
              {tr('In der Firewall freigeben')}
            </label>
          </div>
        </>
      ) : (
        <div className="row-item" style={{ marginTop: 8, flexWrap: 'wrap', gap: 8 }}>
          <input value={(m.befehl ?? []).join(' ')} placeholder="npx -y @modelcontextprotocol/server-github"
            aria-label={tr('Befehl')} style={{ flex: 1, minWidth: 260 }}
            onChange={(ev) => setze({ befehl: ev.target.value.split(' ').filter(Boolean) })} />
          <input value={m.variable ?? ''} placeholder="GITHUB_TOKEN" aria-label={tr('Umgebungsvariable für den Schlüssel')}
            title={tr('Umgebungsvariable für den Schlüssel')} style={{ width: 180 }}
            onChange={(ev) => setze({ variable: ev.target.value.toUpperCase() })} />
        </div>
      )}
      <div className="row-item" style={{ marginTop: 8, gap: 8 }}>
        <input type="password" autoComplete="new-password" value={m.schluessel ?? ''} aria-label={tr('API-Schlüssel')}
          placeholder={m.schluessel_gesetzt ? tr('gesetzt — leer lassen, um ihn zu behalten') : tr('API-Schlüssel (optional)')}
          onChange={(ev) => setze({ schluessel: ev.target.value })} />
        {m.schluessel_gesetzt && m.schluessel === undefined && (
          <button className="btn" onClick={() => setze({ schluessel: '' })}>{tr('Schlüssel entfernen')}</button>
        )}
      </div>
      <div style={{ marginTop: 8 }}>
        <span className="sub">{tr('Wer bekommt ihn — ohne Gruppe alle, die opencode bekommen:')}</span>
        <ChipSelect label={tr('Gruppen')} selected={namen} options={gruppen.map((g) => g.name)}
          onChange={(n) => setze({ gruppen: n.map((x) => byName[x]).filter(Boolean) })} />
      </div>
    </div>
  )
}
