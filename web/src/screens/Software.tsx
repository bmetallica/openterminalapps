import { useCallback, useEffect, useRef, useState } from 'react'
import { Field, Toggle } from '../components/controls'
import {
  ApiError, api,
  type Build, type DiscoveredApp, type FreezePreview, type Group,
  type PackageCheck, type Recipe, type Template,
} from '../lib/api'
import { RecipeBuilder } from './RecipeBuilder'
import { ago, gb } from '../lib/format'
import { t as tr, useLang } from '../lib/i18n'

/**
 * Software in den Arbeitsplatz einbauen und als Anwendung freigeben.
 *
 * Der Weg von „ich hätte gern GIMP" bis „GIMP steht im Dashboard" führt über
 * zwei Schritte, und die stehen hier untereinander, weil sie in dieser
 * Reihenfolge passieren:
 *
 *   1. **Einbauen.** Pakete auswählen, Image bauen, neue Fassung aktivieren.
 *   2. **Freigeben.** Im neuen Image nachsehen, was dazugekommen ist, und
 *      auswählen, was die Nutzer bekommen.
 *
 * Schritt 2 fragt niemanden nach einem Startbefehl. Jedes Linux-Paket bringt
 * eine `.desktop`-Datei mit, in der Name, Symbol und Aufruf stehen — OTA liest
 * sie aus dem gebauten Image. Was bleibt, ist eine Liste mit Schaltern.
 */

/* Häufig Gefragtes als Vorschlag. Nicht als abschliessende Liste gemeint:
   Das Feld darunter nimmt jeden Paketnamen. Der Sinn ist, den Normalfall
   ohne Tippen zu erledigen. */
const SUGGESTIONS: { pkg: string; label: string; glyph: string }[] = [
  { pkg: 'gimp', label: 'GIMP', glyph: '◈' },
  { pkg: 'inkscape', label: 'Inkscape', glyph: '◈' },
  { pkg: 'libreoffice', label: 'LibreOffice', glyph: '▤' },
  { pkg: 'thunderbird', label: 'Thunderbird', glyph: '◍' },
  { pkg: 'vlc', label: 'VLC', glyph: '▶' },
  { pkg: 'meld', label: 'Meld', glyph: '⌨' },
  { pkg: 'filezilla', label: 'FileZilla', glyph: '◍' },
  { pkg: 'remmina', label: 'Remmina', glyph: '◍' },
  { pkg: 'keepassxc', label: 'KeePassXC', glyph: '⚙' },
  { pkg: 'git', label: 'Git', glyph: '⌨' },
  { pkg: 'python3-pip', label: 'pip', glyph: '⌨' },
]

const BUSY = new Set(['queued', 'building'])

export function Software({ tpl, onToast, onChanged }: {
  tpl: Template
  onToast: (m: string, tone?: 'ok' | 'bad') => void
  onChanged: () => void
}) {
  useLang()
  const [packages, setPackages] = useState<string[]>([])
  const [custom, setCustom] = useState('')
  const [script, setScript] = useState('')
  const [scriptOpen, setScriptOpen] = useState(false)
  const [extensions, setExtensions] = useState('')
  const [extOpen, setExtOpen] = useState(false)
  const [builds, setBuilds] = useState<Build[] | null>(null)
  const [watching, setWatching] = useState<Build | null>(null)
  const [apps, setApps] = useState<DiscoveredApp[] | null>(null)
  const [busy, setBusy] = useState(false)
  // Was das Image von den gewählten Paketen hält. Siehe checkPackages().
  const [checks, setChecks] = useState<Record<string, PackageCheck>>({})
  const [checking, setChecking] = useState(false)
  // Rezepte kommen aus der Datenbank, nicht mehr aus einer festen Liste im
  // Browser: Sie sollen sich anlegen und ändern lassen.
  const [recipes, setRecipes] = useState<Recipe[]>([])
  const [editing, setEditing] = useState<Recipe | null | undefined>()
  // Für die Sichtbarkeit je Anwendung. Ohne Gruppen gibt es nichts zu wählen,
  // und die Zeile bleibt aus.
  const [groups, setGroups] = useState<Group[]>([])
  const [visFor, setVisFor] = useState<string | null>(null)
  // Vorschau aufs Einfrieren. Erst ansehen, dann entscheiden.
  const [frost, setFrost] = useState<FreezePreview | null>(null)
  const [frostFehler, setFrostFehler] = useState<string | null>(null)
  const logBox = useRef<HTMLPreElement>(null)

  useEffect(() => { api.groups().then(setGroups).catch(() => {}) }, [])

  const loadRecipes = useCallback(() => {
    api.recipes().then(setRecipes).catch(() => {})
  }, [])
  useEffect(loadRecipes, [loadRecipes])

  useEffect(() => {
    api.builds(tpl.id).then((list) => {
      setBuilds(list)
      setWatching(list.find((b) => BUSY.has(b.status)) ?? null)
    }).catch(() => setBuilds([]))
  }, [tpl.id])

  /* Ein laufender Build meldet sich, statt abgefragt zu werden.
     Der Server fragt den Agent weiterhin ab — anders kommt man an den
     Fortschritt von `docker build` nicht heran —, aber hierher kommt nur der
     Zuwachs, und zwar sobald er da ist. Bei einem Protokoll von mehreren
     hundert Kilobyte ist das der Unterschied zwischen einem ruhigen Fenster
     und einem, das ruckelt.

     Fällt der Strom aus — ein Zwischenstück, das ihn nicht durchlässt, ein
     Browser ohne EventSource —, übernimmt die alte Abfrage. Lieber langsam
     als blind. */
  const buildId = watching && BUSY.has(watching.status) ? watching.id : null

  const finish = useCallback((b: Build) => {
    void api.builds(tpl.id).then(setBuilds)
    onToast(b.status === 'ok'
      ? tr('Fassung {n} ist gebaut. Jetzt aktivieren.', { n: b.version })
      : tr('Der Build ist gescheitert. Das Protokoll sagt, woran.'),
      b.status === 'ok' ? 'ok' : 'bad')
  }, [tpl.id, onToast])

  useEffect(() => {
    if (!buildId) return
    let live = true
    let poll: ReturnType<typeof setInterval> | null = null

    const startPolling = () => {
      if (poll || !live) return
      poll = setInterval(() => {
        void api.build(tpl.id, buildId).then((b) => {
          if (!live) return
          setWatching(b)
          if (!BUSY.has(b.status)) finish(b)
        }).catch(() => {})
      }, 2500)
    }

    let source: EventSource | null = null
    try {
      source = new EventSource(`/api/templates/${tpl.id}/builds/${buildId}/stream`)
    } catch {
      startPolling()
    }

    if (source) {
      source.onmessage = (ev) => {
        const { chunk } = JSON.parse(ev.data) as { chunk: string }
        setWatching((w) => (w && w.id === buildId ? { ...w, log: w.log + chunk } : w))
      }
      source.addEventListener('status', (ev) => {
        const data = JSON.parse((ev as MessageEvent).data) as { status: Build['status'] }
        const status = data.status
        setWatching((w) => (w && w.id === buildId ? { ...w, status } : w))
      })
      source.addEventListener('end', () => {
        source?.close()
        // Zum Schluss einmal den ganzen Datensatz holen: Grösse, Adresse und
        // Prüfsumme stehen nicht im Protokoll.
        void api.build(tpl.id, buildId).then((b) => {
          if (!live) return
          setWatching(b)
          if (!BUSY.has(b.status)) finish(b)
        }).catch(() => {})
      })
      source.onerror = () => {
        source?.close()
        startPolling()
      }
    }

    return () => {
      live = false
      source?.close()
      if (poll) clearInterval(poll)
    }
  }, [buildId, tpl.id, finish])

  // Beim Wachsen des Protokolls unten bleiben — sonst muss man mitscrollen.
  useEffect(() => {
    const box = logBox.current
    if (box) box.scrollTop = box.scrollHeight
  }, [watching?.log])

  function addPackage(name: string) {
    const clean = name.trim().toLowerCase()
    if (!clean || packages.includes(clean)) return
    const next = [...packages, clean]
    setPackages(next)
    setCustom('')
    void verify(next)
  }

  function dropPackage(name: string) {
    setPackages(packages.filter((p) => p !== name))
  }

  /** Fragt das Image, ob es diese Pakete kennt.
   *
   * Vor dem Bauen, nicht danach: Ein Build dauert Minuten und scheitert an
   * einem Debian-Namen auf einem Ubuntu-Image erst ganz am Ende.
   */
  async function verify(names: string[]) {
    const open = names.filter((n) => !(n in checks))
    if (open.length === 0) return
    setChecking(true)
    try {
      const result = await api.checkPackages(tpl.id, open)
      setChecks((prev) => ({
        ...prev, ...Object.fromEntries(result.map((r) => [r.name, r])),
      }))
    } catch {
      /* Dann eben ungeprüft — der Build sagt es sonst. */
    } finally {
      setChecking(false)
    }
  }

  function useRecipe(id: string) {
    const recipe = recipes.find((r) => r.id === id)
    if (!recipe) return
    setScriptOpen(true)
    setScript((current) => (current.includes(recipe.script)
      ? current
      : `${current.trimEnd()}${current.trim() ? '\n\n' : ''}${recipe.script}\n`))
  }

  async function removeRecipe(recipe: Recipe) {
    if (!window.confirm(tr('Rezept „{name}" löschen?', { name: recipe.name }))) return
    try {
      await api.deleteRecipe(recipe.id)
      setEditing(undefined)
      loadRecipes()
      onToast(tr('Rezept „{name}" gelöscht.', { name: recipe.name }))
    } catch (err) {
      onToast(err instanceof ApiError ? err.message : tr('Löschen fehlgeschlagen'), 'bad')
    }
  }

  async function build() {
    if (packages.length === 0 && !script.trim()) {
      onToast(tr('Es ist nichts ausgewählt, was eingebaut werden soll.'), 'bad')
      return
    }
    const bad = packages.filter((p) => checks[p] && !checks[p].available)
    if (bad.length > 0) {
      onToast(tr('{list} gibt es in diesem Image nicht. Der Build würde daran scheitern.',
        { list: bad.join(', ') }), 'bad')
      return
    }
    setBusy(true)
    try {
      const started = await api.startBuild(tpl.id, {
        apt_packages: packages,
        vscode_extensions: extensions.split(/[\s,]+/).filter(Boolean),
        setup_script: script,
        comment: packages.join(', ').slice(0, 240),
      })
      setWatching(started)
      setBuilds(await api.builds(tpl.id))
      onToast(tr('Der Build läuft. Das dauert ein paar Minuten.'))
    } catch (err) {
      onToast(err instanceof ApiError ? err.message : tr('Start fehlgeschlagen'), 'bad')
    } finally {
      setBusy(false)
    }
  }

  async function activate(b: Build) {
    setBusy(true)
    try {
      await api.activateBuild(tpl.id, b.id)
      setBuilds(await api.builds(tpl.id))
      setApps(null)
      onChanged()
      onToast(tr('Fassung {n} ist jetzt in Betrieb. Neue Sessions bekommen sie.', { n: b.version }))
    } catch (err) {
      onToast(err instanceof ApiError ? err.message : tr('Aktivieren fehlgeschlagen'), 'bad')
    } finally {
      setBusy(false)
    }
  }

  async function discover() {
    setBusy(true)
    try {
      setApps(await api.discoverApps(tpl.id))
    } catch (err) {
      onToast(err instanceof ApiError ? err.message : tr('Durchsehen fehlgeschlagen'), 'bad')
    } finally {
      setBusy(false)
    }
  }

  async function frostVorschau() {
    setBusy(true)
    setFrostFehler(null)
    try {
      setFrost(await api.freezePreview(tpl.id))
    } catch (err) {
      setFrost(null)
      setFrostFehler(err instanceof ApiError ? err.message : tr('Vorschau fehlgeschlagen'))
    } finally {
      setBusy(false)
    }
  }

  async function einfrieren() {
    if (!frost) return
    setBusy(true)
    try {
      const b = await api.freeze(tpl.id, {
        comment: tr('Eingefroren aus der laufenden Session'),
        trotz_geheimnissen: (frost.geheimnisse ?? []).length > 0,
      })
      setFrost(null)
      setBuilds(await api.builds(tpl.id))
      onChanged()
      onToast(tr('Fassung {n} eingefroren. Jetzt aktivieren.', { n: b.version }))
    } catch (err) {
      onToast(err instanceof ApiError ? err.message : tr('Einfrieren fehlgeschlagen'), 'bad')
    } finally {
      setBusy(false)
    }
  }

  async function removeBuild(b: Build) {
    setBusy(true)
    try {
      const res = await api.deleteBuild(tpl.id, b.id)
      setBuilds(await api.builds(tpl.id))
      if (watching?.id === b.id) setWatching(null)
      onToast(res.status)
    } catch (err) {
      onToast(err instanceof ApiError ? err.message : tr('Entfernen fehlgeschlagen'), 'bad')
    } finally {
      setBusy(false)
    }
  }

  async function saveApps() {
    if (!apps) return
    setBusy(true)
    try {
      // Nur was angeboten werden soll, kommt in den Katalog. Aus seiner
      // Reihenfolge leitet sich die Displaynummer ab — deshalb bleibt sie so,
      // wie die Liste sie zeigt.
      await api.setApps(tpl.id, apps.filter((a) => a.is_enabled).map((a) => ({
        slug: a.slug,
        name: a.name,
        icon: a.icon,
        exec_cmd: a.exec_cmd,
        exec_args: a.exec_args,
        is_enabled: true,
        fixed_display: a.fixed_display,
        group_ids: a.group_ids ?? [],
        x_res: a.x_res, y_res: a.y_res,
      })))
      onChanged()
      onToast(tr('{n} Anwendungen freigegeben.', { n: apps.filter((a) => a.is_enabled).length }))
    } catch (err) {
      onToast(err instanceof ApiError ? err.message : tr('Speichern fehlgeschlagen'), 'bad')
    } finally {
      setBusy(false)
    }
  }

  const running = watching && BUSY.has(watching.status)

  return (
    <>
      {/* ---------------------------------------------- 1. Einbauen */}
      <div className="section__head" style={{ marginBottom: 10 }}>
        <span className="silk">{tr('Software einbauen')}</span>
        <span className="section__rule" />
      </div>

      <p className="sub" style={{ marginBottom: 14 }}>
        {tr('Ausgewählte Pakete kommen ins Golden Image. Laufende Sessions bleiben unberührt — die neue Fassung gilt ab dem nächsten Start.')}
      </p>

      <Field label={tr('Pakete')}
        hint={tr('Debian-Paketnamen. Was hier steht, wird beim Bauen mit apt installiert.')}>
        <div className="chips" style={{ marginBottom: 10 }}>
          {SUGGESTIONS.map((s) => {
            const on = packages.includes(s.pkg)
            return (
              <button key={s.pkg} type="button" aria-pressed={on}
                className={`chip${on ? ' is-on' : ''}`}
                onClick={() => (on
                  ? setPackages(packages.filter((p) => p !== s.pkg))
                  : addPackage(s.pkg))}>
                <span aria-hidden="true" style={{ marginRight: 6 }}>{s.glyph}</span>
                {s.label}
              </button>
            )
          })}
        </div>

        {packages.filter((p) => !SUGGESTIONS.some((s) => s.pkg === p)).length > 0 && (
          <div className="chips" style={{ marginBottom: 10 }}>
            {packages.filter((p) => !SUGGESTIONS.some((s) => s.pkg === p)).map((p) => (
              <button key={p} type="button"
                className={`chip is-on${checks[p] && !checks[p].available ? ' chip--bad' : ''}`}
                onClick={() => dropPackage(p)}>
                {p} <span aria-hidden="true" style={{ marginLeft: 6, opacity: .6 }}>✕</span>
              </button>
            ))}
          </div>
        )}

        <div className="row-item">
          <input value={custom} placeholder={tr('Weiteres Paket, z. B. audacity')}
            aria-label={tr('Paketname')}
            onChange={(e) => setCustom(e.target.value)}
            onKeyDown={(e) => { if (e.key === 'Enter') { e.preventDefault(); addPackage(custom) } }} />
          <button type="button" className="btn btn--sm" onClick={() => addPackage(custom)}>
            {tr('Hinzufügen')}
          </button>
        </div>

        {/* Was das Image von der Auswahl hält. Nur Auffälliges wird gezeigt —
            ein Häkchen hinter jedem Paket wäre nur Rauschen. */}
        {checking && <p className="field__hint">{tr('Wird im Image nachgeschlagen…')}</p>}
        {packages.map((p) => checks[p]).filter((c) => c && !c.available).map((c) => (
          <p key={c.name} className="note-warn" style={{ marginTop: 8 }}>
            <b>{c.name}</b>{' — '}
            {c.snap_stub
              ? tr('gibt es hier nur als Verweis auf ein Snap. Im Container läuft kein Snap; installiert würde ein Platzhalter ohne Programm. Nimm dafür ein Rezept unten.')
              : tr('kennt dieses Image nicht.')}
            {c.suggestions.length > 0 && (
              <span style={{ display: 'block', marginTop: 6 }}>
                {tr('Gemeint war vielleicht:')}{' '}
                {c.suggestions.map((s) => (
                  <button key={s} type="button" className="chip"
                    style={{ marginRight: 6 }}
                    onClick={() => { dropPackage(c.name); addPackage(s) }}>{s}</button>
                ))}
              </span>
            )}
          </p>
        ))}
      </Field>

      <Field label={tr('Rezepte')}
        hint={tr('Für Software, die kein einfaches Paket ist. Ein Rezept hängt seine Schritte unten an — sichtbar und änderbar.')}>
        <div className="chips">
          {recipes.map((r) => (
            <span key={r.id} className="recipe__chip">
              <button type="button" title={r.why}
                className={`chip${script.includes(r.script) ? ' is-on' : ''}`}
                onClick={() => useRecipe(r.id)}>
                <span aria-hidden="true" style={{ marginRight: 6 }}>{r.glyph}</span>{r.name}
              </button>
              {/* Bearbeiten sitzt am Rezept, nicht in einer eigenen Liste:
                  Dort sucht man es, wenn man es gerade benutzt. */}
              <button type="button" className="recipe__edit"
                aria-label={tr('{name} bearbeiten', { name: r.name })}
                title={r.is_builtin ? tr('Mitgeliefert — als Kopie öffnen') : tr('Ändern')}
                onClick={() => setEditing(r)}>▸</button>
            </span>
          ))}
          <button type="button" className="chip chip--add" onClick={() => setEditing(null)}>
            <span aria-hidden="true" style={{ marginRight: 6 }}>+</span>{tr('Neues Rezept')}
          </button>
        </div>
      </Field>

      {editing !== undefined && (
        <div className="panel" style={{ padding: '18px 20px', marginBottom: 20 }}>
          <div className="section__head" style={{ marginBottom: 14 }}>
            <span className="silk">
              {editing === null ? tr('Neues Rezept')
                : editing.is_builtin ? tr('Kopie von {name}', { name: editing.name })
                  : tr('{name} ändern', { name: editing.name })}
            </span>
            <span className="section__rule" />
            {editing && !editing.is_builtin && (
              <button type="button" className="btn btn--sm btn--halt"
                onClick={() => void removeRecipe(editing)}>{tr('Löschen')}</button>
            )}
          </div>
          <RecipeBuilder
            existing={editing ?? undefined}
            onDone={() => { setEditing(undefined); loadRecipes() }}
            onCancel={() => setEditing(undefined)}
            onToast={onToast} />
        </div>
      )}

      <Field label={tr('VS-Code-Erweiterungen')}
        hint={tr('Kennungen wie ms-python.python, durch Leerzeichen oder Komma getrennt. Sie werden beim Bauen installiert, nicht beim Start — sonst wartet jeder Nutzer bei jedem Start auf Downloads.')}>
        <Toggle on={extOpen} name={tr('Erweiterungen mitbauen')}
          note={tr('Sie landen ausschliesslich in Microsofts VS Code. VSCodium hat seinen eigenen Satz aus Open VSX und sieht diese hier nicht — dieselbe Kennung ist dort nicht dieselbe Installation.')}
          onChange={setExtOpen} />
        {extOpen && (
          <textarea className="viewer__clip" style={{ marginTop: 10, minHeight: 70 }}
            value={extensions} spellCheck={false}
            placeholder={'ms-python.python\nesbenp.prettier-vscode'}
            aria-label={tr('VS-Code-Erweiterungen')}
            onChange={(e) => setExtensions(e.target.value)} />
        )}
      </Field>

      <Field label={tr('Eigene Schritte')}
        hint={tr('Für alles, was apt nicht kann. Läuft als root im Image, nach den Paketen.')}>
        <Toggle on={scriptOpen} name={tr('Eigenes Skript verwenden')}
          note={tr('Nur nötig, wenn ein Paket nicht reicht — etwa für ein fremdes Repository.')}
          onChange={setScriptOpen} />
        {scriptOpen && (
          <textarea className="viewer__clip" style={{ marginTop: 10, minHeight: 130 }}
            value={script} spellCheck={false}
            placeholder={'#!/usr/bin/env bash\nset -e\n'}
            aria-label={tr('Eigenes Skript')}
            onChange={(e) => setScript(e.target.value)} />
        )}
      </Field>

      <div className="viewer__row" style={{ marginTop: 4, marginBottom: 22 }}>
        <button className="btn btn--primary" disabled={busy || !!running} onClick={() => void build()}>
          {running ? tr('Build läuft…') : tr('Image bauen')}
        </button>
        {packages.length > 0 && (
          <span className="sub" style={{ alignSelf: 'center' }}>
            {tr('{n} Pakete ausgewählt', { n: packages.length })}
          </span>
        )}
      </div>

      {watching && (
        <div className="panel" style={{ padding: '14px 16px', marginBottom: 22 }}>
          <div className="bay__title-row" style={{ marginBottom: 8 }}>
            <span className="silk">
              {tr('Fassung {n}', { n: watching.version })} · {tr(statusText(watching.status))}
            </span>
          </div>
          <pre ref={logBox} className="build__log">{watching.log || tr('Wird vorbereitet…')}</pre>
        </div>
      )}

      {/* ------------------------------------------ Session einfrieren */}
      <div className="section__head" style={{ marginBottom: 10 }}>
        <span className="silk">{tr('Session einfrieren')}</span>
        <span className="section__rule" />
      </div>

      <div className="panel" style={{ padding: '16px 20px', marginBottom: 22 }}>
        <p className="sub" style={{ marginBottom: 12 }}>
          {tr('Der kurze Weg: In deinem eigenen Arbeitsplatz einrichten, was alle bekommen sollen — und daraus eine neue Fassung machen. Was ausserhalb deines Home passiert ist, kommt mit; dein Home selbst nicht, dort liegen deine Schlüssel.')}
        </p>

        {!frost ? (
          <>
            <button className="btn" disabled={busy} onClick={() => void frostVorschau()}>
              {busy ? tr('Wird verglichen…') : tr('Ansehen, was mitkäme')}
            </button>
            {frostFehler && (
              <p className="note-warn" style={{ marginTop: 10 }}>{frostFehler}</p>
            )}
          </>
        ) : (
          <>
            <p className="sub" style={{ marginBottom: 10 }}>
              {tr('{n} Änderung(en) ausserhalb des Home, {skip} übersprungen.', {
                n: String(frost.gesamt), skip: String(frost.uebersprungen),
              })}
            </p>

            {(frost.entfernt ?? []).length > 0 && (
              <p className="note-info" style={{ marginBottom: 10 }}>
                {tr('Wird vorher entfernt: {list} — sonst bekäme jeder Nutzer des Images root.',
                  { list: frost.entfernt.join(', ') })}
              </p>
            )}

            {(frost.geheimnisse ?? []).length > 0 && (
              <p className="note-warn" style={{ marginBottom: 10 }}>
                <b>{tr('{n} Datei(en) sehen nach einem Geheimnis aus.', {
                  n: String(frost.geheimnisse.length),
                })}</b>{' '}
                {tr('Sie kämen ins Image und damit zu jedem, der es benutzt: {list}', {
                  list: frost.geheimnisse.slice(0, 6).join(', '),
                })}
              </p>
            )}

            <div className="build__log" style={{ maxHeight: 220 }}>
              {frost.aenderungen.map((a) => (
                <div key={a.pfad} className={a.geheimnis ? 'frost__row is-secret' : 'frost__row'}>
                  <span className="frost__kind">{a.art}</span> {a.pfad}
                </div>
              ))}
              {frost.gekuerzt && (
                <div className="frost__row" style={{ color: 'var(--mute)' }}>
                  {tr('… und weitere. Insgesamt {n}.', { n: String(frost.gesamt) })}
                </div>
              )}
            </div>

            <div className="viewer__row" style={{ marginTop: 12 }}>
              <button className="btn btn--primary" disabled={busy}
                onClick={() => void einfrieren()}>
                {busy
                  ? tr('Wird eingefroren…')
                  : (frost.geheimnisse ?? []).length > 0
                    ? tr('Trotz der Funde einfrieren')
                    : tr('Als neue Fassung einfrieren')}
              </button>
              <button className="btn btn--ghost" disabled={busy}
                onClick={() => setFrost(null)}>{tr('Abbrechen')}</button>
            </div>
          </>
        )}
      </div>

      {/* ---------------------------------------------- Fassungen */}
      {builds && builds.length > 0 && (
        <>
          <div className="section__head" style={{ marginBottom: 10 }}>
            <span className="silk">{tr('Fassungen')}</span>
            <span className="section__rule" />
          </div>
          <div className="panel" style={{ padding: '10px 0 0', marginBottom: 22 }}>
            <table className="tbl">
              <thead>
                <tr>
                  <th style={{ paddingLeft: 20 }}>{tr('Fassung')}</th>
                  <th>{tr('Inhalt')}</th>
                  <th>{tr('Grösse')}</th>
                  <th>{tr('Gebaut')}</th>
                  <th>{tr('Status')}</th>
                  <th />
                </tr>
              </thead>
              <tbody>
                {[...builds].sort((a, b) => b.version - a.version).map((b) => (
                  <tr key={b.id} style={{ cursor: 'default' }}>
                    <td style={{ paddingLeft: 20 }} className="data">v{b.version}</td>
                    <td style={{ color: 'var(--label)', fontSize: 12.5 }}>
                      {b.comment || tr('ohne Zusätze')}
                    </td>
                    <td className="data" style={{ color: 'var(--label)' }}>
                      {b.size_bytes ? `${gb(b.size_bytes)} GB` : '—'}
                    </td>
                    <td className="data" style={{ color: 'var(--mute)', fontSize: 12 }}>
                      {ago(new Date(b.started_at).getTime())}
                      {b.built_by ? ` · ${b.built_by}` : ''}
                    </td>
                    <td style={{ color: 'var(--label)', fontSize: 12.5 }}>
                      {b.is_current
                        ? <b style={{ color: 'var(--live)' }}>{tr('in Betrieb')}</b>
                        : tr(statusText(b.status))}
                    </td>
                    <td style={{ textAlign: 'right', paddingRight: 20 }}>
                      {b.status === 'ok' && !b.is_current && (
                        <button className="btn btn--sm" disabled={busy}
                          onClick={() => void activate(b)}>{tr('Aktivieren')}</button>
                      )}
                      {/* Die aktive Fassung nicht: Sie zu löschen liesse die
                          Vorlage auf ein Image zeigen, das es nicht gibt. */}
                      {!b.is_current && (
                        <button className="btn btn--sm btn--halt" disabled={busy}
                          style={{ marginLeft: 8 }}
                          onClick={() => void removeBuild(b)}>{tr('Entfernen')}</button>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </>
      )}

      {/* ---------------------------------------------- 2. Freigeben */}
      <div className="section__head" style={{ marginBottom: 10 }}>
        <span className="silk">{tr('Anwendungen freigeben')}</span>
        <span className="section__rule" />
      </div>

      <p className="sub" style={{ marginBottom: 14 }}>
        {tr('OTA sieht im aktiven Image nach, was installiert ist, und liest Name, Symbol und Startbefehl aus den Programmdateien. Du entscheidest nur, was die Nutzer bekommen.')}
      </p>

      {!apps ? (
        <button className="btn" disabled={busy} onClick={() => void discover()}>
          {busy ? tr('Wird durchgesehen…') : tr('Im Image nachsehen')}
        </button>
      ) : (
        <>
          <div className="applist">
            {apps.map((a, i) => (
              <div key={a.slug} className={`applist__row${a.missing ? ' is-blocked' : ''}`}>
                <button type="button" className="tile__icon applist__glyph"
                  title={tr('Anderes Zeichen wählen')}
                  onClick={() => setApps(apps.map((x, j) =>
                    j === i ? { ...x, icon: nextGlyph(x.icon) } : x))}>
                  {a.icon}
                </button>
                <span className="applist__body">
                  <input className="applist__rename" value={a.name}
                    aria-label={tr('Name von {app}', { app: a.name })}
                    onChange={(e) => setApps(apps.map((x, j) =>
                      j === i ? { ...x, name: e.target.value } : x))} />
                  <span className="applist__reg data">
                    {a.exec_cmd}{a.exec_args ? ` ${a.exec_args}` : ''}
                  </span>
                  {a.missing && (
                    <span className="applist__block">
                      {tr('Im aktiven Image nicht mehr vorhanden.')}
                    </span>
                  )}
                  {a.needs_terminal && !a.missing && (
                    <span className="applist__block">
                      {tr('Braucht ein Terminal — startet allein auf leerem Bildschirm.')}
                    </span>
                  )}

                  {/* Auflösung. Der Strom passt sich anschliessend dem
                      Browserfenster an — das hier ist der Anfangswert, und der
                      entscheidet, wie eine Anwendung ihre Oberfläche zuerst
                      aufbaut. Steht nichts da, gilt die des Arbeitsplatzes. */}
                  {a.is_enabled && !a.missing && (
                    <span className="applist__res">
                      <label>
                        {tr('Auflösung')}
                        <input type="number" min={640} max={7680} step={80}
                          placeholder={String(tpl.x_res)}
                          aria-label={tr('Breite von {app}', { app: a.name })}
                          value={a.x_res ?? ''}
                          onChange={(e) => setApps(apps.map((x, j) => j === i
                            ? { ...x, x_res: e.target.value ? Number(e.target.value) : null }
                            : x))} />
                        <span aria-hidden="true">×</span>
                        <input type="number" min={480} max={4320} step={60}
                          placeholder={String(tpl.y_res)}
                          aria-label={tr('Höhe von {app}', { app: a.name })}
                          value={a.y_res ?? ''}
                          onChange={(e) => setApps(apps.map((x, j) => j === i
                            ? { ...x, y_res: e.target.value ? Number(e.target.value) : null }
                            : x))} />
                      </label>
                    </span>
                  )}

                  {/* Sichtbarkeit. Nur eine Zeile, solange nichts eingeschränkt
                      ist — die meisten Anwendungen sind für alle da, und dafür
                      soll niemand durch eine Gruppenliste blättern. */}
                  {groups.length > 0 && a.is_enabled && !a.missing && (
                    <>
                      <button type="button" className="applist__vis"
                        aria-expanded={visFor === a.slug}
                        onClick={() => setVisFor(visFor === a.slug ? null : a.slug)}>
                        {(a.group_ids ?? []).length === 0
                          ? tr('Sichtbar für alle')
                          : tr('Nur für: {names}', {
                            names: groups
                              .filter((g) => (a.group_ids ?? []).includes(g.id))
                              .map((g) => g.name).join(', ') || tr('gelöschte Gruppe'),
                          })}
                      </button>
                      {visFor === a.slug && (
                        <span className="chips applist__chips" role="group"
                          aria-label={tr('Sichtbar für welche Gruppen')}>
                          {groups.map((g) => {
                            const on = (a.group_ids ?? []).includes(g.id)
                            return (
                              <button key={g.id} type="button" aria-pressed={on}
                                className={`chip${on ? ' is-on' : ''}`}
                                onClick={() => setApps(apps.map((x, j) => j === i ? {
                                  ...x,
                                  group_ids: on
                                    ? (x.group_ids ?? []).filter((id) => id !== g.id)
                                    : [...(x.group_ids ?? []), g.id],
                                } : x))}>
                                {g.name}
                              </button>
                            )
                          })}
                        </span>
                      )}
                    </>
                  )}
                </span>
                <Toggle on={a.is_enabled} name=""
                  ariaLabel={tr('{app} bereitstellen', { app: a.name })}
                  onChange={(v) => setApps(apps.map((x, j) =>
                    j === i ? { ...x, is_enabled: v } : x))} />
              </div>
            ))}
          </div>

          <div className="viewer__row" style={{ marginTop: 14 }}>
            <button className="btn btn--primary" disabled={busy} onClick={() => void saveApps()}>
              {tr('Auswahl übernehmen')}
            </button>
            <button className="btn btn--ghost" disabled={busy} onClick={() => void discover()}>
              {tr('Neu durchsehen')}
            </button>
          </div>
          <p className="field__hint" style={{ marginTop: 10 }}>
            {tr('Die Reihenfolge bestimmt, welches Display eine Anwendung bekommt. Wer sie ändert, muss laufende Arbeitsplätze neu starten.')}
          </p>
        </>
      )}
    </>
  )
}

function statusText(status: string): string {
  return { queued: 'wartet', building: 'wird gebaut', ok: 'fertig', failed: 'gescheitert' }[status]
    ?? status
}

/* Ein Klick, ein anderes Zeichen. Ein Emoji-Wähler wäre hier fehl am Platz:
   Die Oberfläche kennt eine feste Zeichensprache, und aus der soll gewählt
   werden — nicht aus allem, was Unicode hergibt. */
const GLYPHS = ['▢', '◎', '◈', '⌨', '▤', '▶', '▦', '⚙', '◍', '▮', '▣', '◔']

function nextGlyph(current: string): string {
  const i = GLYPHS.indexOf(current)
  return GLYPHS[(i + 1) % GLYPHS.length]
}
