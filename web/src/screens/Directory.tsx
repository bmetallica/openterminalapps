import { useCallback, useEffect, useState } from 'react'
import { KcVerzeichnis } from '../components/KcVerzeichnis'
import { Field, Led, Toggle } from '../components/controls'
import { ApiError, api, type Group, type IdentityConfig, type KeycloakStatus } from '../lib/api'
import { ago } from '../lib/format'
import { t as tr, useLang } from '../lib/i18n'

/**
 * Die Anbindung an ein Verzeichnis (LDAP, Active Directory).
 *
 * Der Aufbau folgt der Reihenfolge, in der man das tatsächlich einrichtet:
 * verbinden, prüfen, zuordnen, einschalten. Der Schalter steht bewusst am
 * Ende und nicht oben — er ist die einzige Einstellung in OTA, bei der ein
 * Fehler Menschen aussperrt, und er soll nicht blind erreichbar sein.
 */
/**
 * Zustand des Identity Providers.
 *
 * Steht hier oben, weil diese Anbindung ihn ablösen wird (auth-roadmap.md).
 * Noch **ohne Wirkung auf die Anmeldung** — die macht OTA weiterhin selbst.
 * Was die Karte beantwortet, ist die Frage vor jedem weiteren Schritt: Läuft
 * er, und was darf OTA darin?
 *
 * Die Fähigkeiten stehen einzeln da und nicht als „verbunden": Bei einem
 * fremden Keycloak ist OTA Gast, und was es dort nicht darf, soll es hier
 * lesen können statt später an einem 403 zu scheitern.
 */
function KeycloakKarte() {
  const [st, setSt] = useState<KeycloakStatus | null>(null)
  const [laedt, setLaedt] = useState(true)

  useEffect(() => {
    api.keycloakStatus()
      .then(setSt).catch(() => setSt(null))
      .finally(() => setLaedt(false))
  }, [])

  if (laedt || !st) return null

  const NAMEN: Record<string, string> = {
    konten: tr('Konten'),
    gruppen: tr('Gruppen'),
    clients: tr('Anwendungen'),
    verzeichnis: tr('Verzeichnisanbindung'),
  }

  return (
    <>
      <div className="section__head">
        <span className="silk">{tr('Zentrale Identität')}</span>
        <span className="section__rule" />
        <Led status={st.erreichbar ? 'live' : 'fail'} />
      </div>
      <div className="panel" style={{ padding: '16px 20px', marginBottom: 18 }}>
        <div className="bay__facts" style={{ marginBottom: 12 }}>
          <span className="bay__fact"><span className="silk">{tr('Betriebsart')}</span>
            <b>{st.betriebsart === 'mitgeliefert' ? tr('Mitgeliefert') : tr('Vorhanden')}</b></span>
          <span className="bay__fact"><span className="silk">{tr('Realm')}</span>
            <b>{st.realm}</b></span>
          <span className="bay__fact"><span className="silk">{tr('Fassung')}</span>
            <b>{st.version ?? '—'}</b></span>
        </div>

        {st.fehler ? (
          <p className="note-warn" style={{ margin: 0 }}>{st.fehler}</p>
        ) : (
          <div className="strip">
            {Object.entries(st.faehigkeiten).map(([k, v]) => (
              <span key={k} className={`chip${v ? ' is-on' : ''}`}>
                {NAMEN[k] ?? k}
              </span>
            ))}
          </div>
        )}

        <p className="field__hint" style={{ marginTop: 12 }}>
          {st.betriebsart === 'mitgeliefert'
            ? tr('Läuft in diesem Stack. Die Anmeldung macht OTA vorerst weiterhin selbst — diese Anbindung wird sie später ablösen.')
            : tr('Ein fremdes Keycloak. OTA ist dort Gast: Es löscht nichts und fasst nur die eigenen Gruppen an. Was oben grau ist, darf das Dienstkonto nicht.')}
        </p>
      </div>
    </>
  )
}

export function Directory({ onToast }: { onToast: (m: string, tone?: 'ok' | 'bad') => void }) {
  useLang()
  const [cfg, setCfg] = useState<IdentityConfig | null>(null)
  const [groups, setGroups] = useState<Group[]>([])
  const [pw, setPw] = useState('')
  const [probe, setProbe] = useState('')
  const [result, setResult] = useState<Record<string, unknown> | null>(null)
  const [busy, setBusy] = useState(false)

  const load = useCallback(async () => {
    try {
      const [c, g] = await Promise.all([api.identity(), api.groups()])
      setCfg(c)
      setGroups(g)
    } catch (err) {
      onToast(err instanceof ApiError ? err.message : tr('Laden fehlgeschlagen'), 'bad')
    }
  }, [onToast])

  useEffect(() => { void load() }, [load])

  function set<K extends keyof IdentityConfig>(key: K, value: IdentityConfig[K]) {
    setCfg((c) => (c ? { ...c, [key]: value } : c))
  }

  async function save(extra: Partial<IdentityConfig> = {}, note?: string) {
    if (!cfg) return
    setBusy(true)
    try {
      const body: Record<string, unknown> = { ...cfg, ...extra }
      delete body.has_bind_password
      delete body.last_sync_at
      delete body.last_error
      if (pw) body.bind_password = pw
      else delete body.bind_password
      setCfg(await api.saveIdentity(body))
      setPw('')
      onToast(note ?? tr('Gespeichert.'))
    } catch (err) {
      onToast(err instanceof ApiError ? err.message : tr('Speichern fehlgeschlagen'), 'bad')
    } finally {
      setBusy(false)
    }
  }

  async function test() {
    setBusy(true)
    setResult(null)
    try {
      await save({}, tr('Gespeichert, wird geprüft…'))
      setResult(await api.testIdentity(probe))
    } catch (err) {
      onToast(err instanceof ApiError ? err.message : tr('Die Prüfung schlug fehl'), 'bad')
    } finally {
      setBusy(false)
    }
  }

  async function sync() {
    setBusy(true)
    try {
      const r = await api.syncIdentity()
      onToast(tr('{n} Konten geprüft, {a} geändert, {d} deaktiviert.',
        { n: String(r.geprueft), a: String(r.geaendert), d: String(r.deaktiviert) }))
      await load()
    } catch (err) {
      onToast(err instanceof ApiError ? err.message : tr('Abgleich fehlgeschlagen'), 'bad')
    } finally {
      setBusy(false)
    }
  }

  if (!cfg) return <p className="sub">{tr('Wird geladen…')}</p>

  // Was die Prüfung gefunden hat **und** was schon zugeordnet ist.
  //
  // Nur die Funde zu zeigen war falsch: Nach einem Neuladen der Seite stand
  // dort „erst prüfen", obwohl längst eine Zuordnung gespeichert war — und
  // die liess sich dann nicht mehr ändern, ohne erst wieder zu prüfen.
  const gefunden = Array.from(new Set([
    ...((result?.gruppen as string[] | undefined) ?? []),
    ...Object.keys(cfg.group_map ?? {}),
  ])).sort()
  const person = result?.person as Record<string, unknown> | undefined
  const hinweise = (result?.hinweise as string[] | undefined) ?? []
  const bereit = Boolean(cfg.server_uri && cfg.base_dn && cfg.bind_dn)

  return (
    <>
      <p className="sub" style={{ marginBottom: 16 }}>
        {tr('Konten aus einem Verzeichnis anmelden lassen, statt sie von Hand anzulegen. Lokale Konten bleiben davon unberührt — sie werden weiterhin lokal geprüft, auch wenn im Verzeichnis ein gleichnamiger Eintrag steht.')}
      </p>

      <KeycloakKarte />
      <KcVerzeichnis onToast={onToast} />

      <div className="section__head">
        <span className="silk">{tr('Verbindung (alte Anbindung)')}</span>
        <span className="section__rule" />
      </div>
      <p className="field__hint" style={{ marginTop: -6, marginBottom: 12 }}>
        {tr('Wird von der Anbindung über Keycloak abgelöst und nicht mehr weiterentwickelt. Sie bleibt als Rückweg bestehen, bis die Umstellung abgeschlossen ist.')}
      </p>
      <div className="panel" style={{ padding: '16px 20px', marginBottom: 18 }}>
        <Field label={tr('Adresse')}
          hint={tr('ldaps://server:636 für eine verschlüsselte Verbindung, oder ldap://server:389 mit StartTLS.')}>
          <div className="row-item">
            <input value={cfg.server_uri} spellCheck={false} placeholder="ldaps://dc01.firma.local:636"
              aria-label={tr('Adresse')} onChange={(e) => set('server_uri', e.target.value)} />
          </div>
        </Field>

        <Field label={tr('Verschlüsselung')}>
          <div className="chips" role="group" aria-label={tr('Verschlüsselung')}>
            {(['starttls', 'none'] as const).map((m) => (
              <button key={m} type="button" aria-pressed={cfg.tls_mode === m}
                className={`chip${cfg.tls_mode === m ? ' is-on' : ''}`}
                onClick={() => set('tls_mode', m)}>
                {m === 'starttls' ? tr('StartTLS') : tr('ohne')}
              </button>
            ))}
          </div>
          {cfg.tls_mode === 'none' && !cfg.server_uri.startsWith('ldaps://') && (
            <p className="note-warn" style={{ marginTop: 10 }}>
              {tr('Ohne Verschlüsselung geht jedes Anmeldepasswort im Klartext über das Netz. Für einen Testaufbau in Ordnung, für den Betrieb nicht.')}
            </p>
          )}
        </Field>

        <Field label={tr('Dienstkonto')}
          hint={tr('Wird zum Suchen gebraucht und braucht nur Leserecht. Der Mensch, der sich anmeldet, kennt seinen eigenen Eintrag nicht.')}>
          <div className="row-item">
            <input value={cfg.bind_dn} spellCheck={false} placeholder="cn=ota-dienst,dc=firma,dc=local"
              aria-label={tr('Dienstkonto')} onChange={(e) => set('bind_dn', e.target.value)} />
          </div>
          <div className="row-item" style={{ marginTop: 8 }}>
            <input type="password" value={pw} autoComplete="off"
              placeholder={cfg.has_bind_password ? tr('hinterlegt — leer lassen, um es zu behalten') : tr('Kennwort')}
              aria-label={tr('Kennwort des Dienstkontos')}
              onChange={(e) => setPw(e.target.value)} />
          </div>
        </Field>

        <Field label={tr('Basis')} hint={tr('Ab wo gesucht wird.')}>
          <div className="row-item">
            <input value={cfg.base_dn} spellCheck={false} placeholder="dc=firma,dc=local"
              aria-label={tr('Basis')} onChange={(e) => set('base_dn', e.target.value)} />
          </div>
        </Field>

        <Field label={tr('Anmeldemerkmal')}
          hint={tr('Womit sich jemand anmeldet: uid bei OpenLDAP, sAMAccountName im Active Directory.')}>
          <div className="row-item">
            <input value={cfg.login_attribute} spellCheck={false}
              aria-label={tr('Anmeldemerkmal')}
              onChange={(e) => set('login_attribute', e.target.value)} />
          </div>
        </Field>

        <Field label={tr('Gruppen-Basis')} hint={tr('Leer lassen, wenn die Gruppen unter derselben Basis liegen.')}>
          <div className="row-item">
            <input value={cfg.group_base_dn} spellCheck={false} placeholder="ou=groups,dc=firma,dc=local"
              aria-label={tr('Gruppen-Basis')} onChange={(e) => set('group_base_dn', e.target.value)} />
          </div>
        </Field>
      </div>

      <div className="section__head"><span className="silk">{tr('Prüfen')}</span><span className="section__rule" /></div>
      <div className="panel" style={{ padding: '16px 20px', marginBottom: 18 }}>
        <Field label={tr('Ein Name zur Probe')}
          hint={tr('Freiwillig. Mit einem Namen zeigt die Prüfung ausserdem, was das Verzeichnis über diesen Menschen liefert — vor allem seine Gruppen.')}>
          <div className="row-item">
            <input value={probe} spellCheck={false} placeholder="vorname.nachname"
              aria-label={tr('Ein Name zur Probe')} onChange={(e) => setProbe(e.target.value)} />
          </div>
        </Field>
        <button className="btn btn--primary" disabled={busy || !bereit} onClick={() => void test()}>
          {busy ? tr('Wird geprüft…') : tr('Speichern und prüfen')}
        </button>

        {result && (
          <div style={{ marginTop: 14 }}>
            <p className="sub">
              {tr('{n} Einträge sichtbar, {g} Gruppen.', {
                n: String(result.eintraege), g: String(gefunden.length),
              })}
            </p>
            {hinweise.map((h) => (
              <p key={h} className="note-warn" style={{ marginTop: 8 }}>{h}</p>
            ))}
            {person && (
              <p className="note-info" style={{ marginTop: 8 }}>
                <b>{String(person.name || person.login)}</b>{' · '}
                <span className="data">{String(person.dn)}</span>
                <br />
                {tr('Gruppen im Verzeichnis:')}{' '}
                <span className="data">{(person.gruppen as string[]).join(', ') || '—'}</span>
              </p>
            )}
          </div>
        )}
      </div>

      <div className="section__head"><span className="silk">{tr('Gruppen zuordnen')}</span><span className="section__rule" /></div>
      <div className="panel" style={{ padding: '16px 20px', marginBottom: 18 }}>
        <p className="sub" style={{ marginBottom: 12 }}>
          {tr('Was nicht zugeordnet ist, bringt keine Rechte mit. Ein Verzeichnis hat Dutzende Gruppen, die OTA nichts angehen — sie automatisch zu übernehmen hiesse, nach dem ersten Abgleich vierzig Gruppen zu haben, die niemand wollte.')}
        </p>
        {gefunden.length === 0 ? (
          <p className="field__hint">{tr('Noch nichts zugeordnet. Oben prüfen — dann stehen die Gruppen des Verzeichnisses hier zur Auswahl.')}</p>
        ) : (
          <div className="maprows">
            {gefunden.map((name) => (
              <div key={name} className="maprow">
                <span className="maprow__from data">{name}</span>
                <span className="maprow__arrow" aria-hidden="true">→</span>
                <select className="maprow__to" aria-label={tr('Zuordnung für {name}', { name })}
                  value={cfg.group_map[name] ?? ''}
                  onChange={(e) => {
                    const next = { ...cfg.group_map }
                    if (e.target.value) next[name] = e.target.value
                    else delete next[name]
                    set('group_map', next)
                  }}>
                  <option value="">{tr('— keine —')}</option>
                  {groups.map((g) => <option key={g.id} value={g.id}>{g.name}</option>)}
                </select>
              </div>
            ))}
            <button className="btn btn--sm" disabled={busy} style={{ marginTop: 10 }}
              onClick={() => void save({}, tr('Zuordnung gespeichert.'))}>
              {tr('Zuordnung speichern')}
            </button>
          </div>
        )}
      </div>

      <div className="section__head"><span className="silk">{tr('Betrieb')}</span><span className="section__rule" /></div>
      <div className="panel" style={{ padding: '16px 20px' }}>
        <Toggle on={cfg.jit_create} name={tr('Konten beim ersten Anmelden anlegen')}
          note={tr('Ohne das muss jedes Konto vorher von Hand angelegt werden.')}
          onChange={(v) => set('jit_create', v)} />
        <Toggle on={cfg.sync_enabled} name={tr('Nächtlich abgleichen')}
          note={tr('Holt Gruppenänderungen nach. Wer sich anmeldet, wird ohnehin bei jeder Anmeldung aufgefrischt.')}
          onChange={(v) => set('sync_enabled', v)} />

        <div className="viewer__row" style={{ marginTop: 12 }}>
          <button className="btn btn--sm" disabled={busy || !cfg.is_enabled}
            onClick={() => void sync()}>{tr('Jetzt abgleichen')}</button>
          {cfg.last_sync_at && (
            <span className="sub" style={{ alignSelf: 'center' }}>
              {tr('zuletzt {when}', { when: ago(new Date(cfg.last_sync_at).getTime()) })}
            </span>
          )}
        </div>

        {cfg.last_error && (
          <p className="note-warn" style={{ marginTop: 12 }}>{cfg.last_error}</p>
        )}

        <div style={{ marginTop: 18, paddingTop: 16, borderTop: '1px solid var(--edge)' }}>
          <Toggle on={cfg.is_enabled} name={tr('Anmeldung über das Verzeichnis einschalten')}
            note={cfg.is_enabled
              ? tr('Neue Namen werden im Verzeichnis gesucht. Lokale Konten bleiben lokal.')
              : tr('Abgeschaltet. An der Anmeldung ändert sich nichts.')}
            onChange={(v) => void save({ is_enabled: v },
              v ? tr('Verzeichnis-Anmeldung eingeschaltet.') : tr('Verzeichnis-Anmeldung abgeschaltet.'))} />
          <p className="note-info" style={{ marginTop: 10 }}>
            {tr('Das Passwort eines lokalen Kontos wird nie gegen das Verzeichnis geprüft — auch dann nicht, wenn dort ein Eintrag mit demselben Namen steht. Sonst könnte jeder, der im Verzeichnis einen Eintrag anlegen darf, ein bestehendes Konto übernehmen.')}
          </p>
        </div>
      </div>
    </>
  )
}
