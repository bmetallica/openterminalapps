import { useEffect, useMemo, useState } from 'react'
import {
  CapacityFader, ChipSelect, Combobox, Field, KeyValueRows, Led, Segmented, Toggle,
} from '../components/controls'
import { OnceScripts } from '../components/OnceScripts'
import { Workbench } from '../components/Workbench'
import { cores as coresLabel, gb, idleLabel } from '../lib/format'
import {
  ApiError, api,
  type Allocation, type Group, type Host, type HostImage, type NetzProfil,
  type Template,
} from '../lib/api'
import { AppIcon } from '../components/AppIcon'
import { Skeleton } from './Skeleton'
import { t as tr, useLang } from '../lib/i18n'
import { Software } from './Software'

const GB = 1024 ** 3
const ALL_CATEGORIES = ['Entwicklung', 'Produktivität', 'Büro', 'Multimedia', 'Kommunikation', 'KI-Werkzeug']
const IDLE_STEPS = [15, 30, 60, 240, 480, 100000]

const RIGHTS_META: { key: string; name: string; note: string; group: string }[] = [
  { key: 'clipboardDown', group: 'Zwischenablage', name: 'Einfügen erlauben', note: 'Browser → Session. Entspricht AcceptCutText' },
  { key: 'clipboardUp', group: 'Zwischenablage', name: 'Kopieren erlauben', note: 'Session → Browser. Entspricht SendCutText' },
  { key: 'clipboardImages', group: 'Zwischenablage', name: 'Bilder übertragen', note: 'image/png zusätzlich zu Text' },
  { key: 'clipboardPrimary', group: 'Zwischenablage', name: 'Markieren und Mittelklick', note: 'X-PRIMARY zusätzlich zu Strg+C. Ab Werk aus' },
  { key: 'uploads', group: 'Dateien', name: 'Dateien hochladen', note: 'Ablegen im Uploads-Ordner der Session' },
  { key: 'downloads', group: 'Dateien', name: 'Dateien herunterladen', note: 'Aus der Session auf den eigenen Rechner' },
  { key: 'audio', group: 'Geräte', name: 'Ton', note: 'Audioausgabe der Session im Browser' },
  { key: 'microphone', group: 'Geräte', name: 'Mikrofon', note: 'Zugriff auf das Mikrofon des Nutzers' },
  { key: 'webcam', group: 'Geräte', name: 'Kamera', note: 'Zugriff auf die Kamera des Nutzers' },
  { key: 'printing', group: 'Sonstiges', name: 'Drucken', note: 'Druckaufträge als PDF an den Browser' },
]

type Draft = Template & { env_rows: { k: string; v: string }[] }

function toDraft(t: Template): Draft {
  return { ...t, env_rows: Object.entries(t.env ?? {}).map(([k, v]) => ({ k, v: String(v) })) }
}

function toPayload(d: Draft) {
  return {
    friendly_name: d.friendly_name,
    description: d.description,
    icon: d.icon,
    categories: d.categories,
    mode: d.mode,
    stream_engine: d.stream_engine,
    net_profile_id: d.net_profile_id ?? null,
    image_ref: d.image_ref,
    cores: d.cores,
    memory_bytes: Math.round(d.memory_bytes),
    x_res: d.x_res,
    y_res: d.y_res,
    idle_minutes: d.idle_minutes,
    idle_action: d.idle_action,
    persistence_scope: d.persistence_scope,
    rights: d.rights,
    env: Object.fromEntries(d.env_rows.filter((r) => r.k).map((r) => [r.k, r.v])),
    // Fehlte bis zum 2026-08-28: Das Feld liess sich bearbeiten und wurde
    // beim Speichern stillschweigend verworfen.
    start_script: d.start_script,
    skeleton_enforce: d.skeleton_enforce,
    user_shelf: d.user_shelf,
    group_shelf: d.group_shelf,
    is_enabled: d.is_enabled,
    group_ids: d.group_ids,
  }
}

function Editor({ tpl, host, groups, images, netzprofile, onSaved, onClose, onToast }: {
  tpl: Template
  host: Host | null
  groups: Group[]
  images: HostImage[]
  netzprofile: NetzProfil[]
  onSaved: () => void
  onClose: () => void
  onToast: (m: string, tone?: 'ok' | 'bad') => void
}) {
  // "Software" steht direkt neben "Apps", weil es derselbe Vorgang in zwei
  // Schritten ist: erst einbauen, dann freigeben.
  const TABS = tpl.mode === 'workspace'
    ? ['Allgemein', 'Apps', 'Software', 'Skeleton', 'Ressourcen', 'Rechte', 'Umgebung', 'Einmal', 'Zuteilung']
    : ['Allgemein', 'Software', 'Skeleton', 'Ressourcen', 'Rechte', 'Umgebung', 'Einmal', 'Zuteilung']

  const [draft, setDraft] = useState<Draft>(() => toDraft(tpl))
  const [tab, setTab] = useState(TABS[0])
  const [allocs, setAllocs] = useState<Allocation[] | null>(null)
  const [openUser, setOpenUser] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)

  const set = <K extends keyof Draft>(k: K, v: Draft[K]) => setDraft({ ...draft, [k]: v })

  const freeBytes = host ? host.memory_available : 8 * GB
  const freeGb = freeBytes / GB
  const hostCores = host?.cores ?? 4

  useEffect(() => {
    if (tab !== 'Zuteilung') return
    api.allocations(tpl.id).then(setAllocs).catch(() => setAllocs([]))
  }, [tab, tpl.id])

  async function save() {
    setBusy(true)
    try {
      await api.updateTemplate(tpl.id, toPayload(draft))
      onToast(`${draft.friendly_name} gespeichert`)
      onSaved()
    } catch (err) {
      onToast(err instanceof ApiError ? err.message : tr('Speichern fehlgeschlagen'), 'bad')
    } finally {
      setBusy(false)
    }
  }

  async function setOverride(userId: string, patch: { cores?: number | null; memory_bytes?: number | null }) {
    const alloc = allocs?.find((a) => a.user_id === userId)
    if (!alloc) return
    const body = {
      scope: 'user',
      target_id: userId,
      cores: patch.cores !== undefined ? patch.cores : (alloc.cores_from === 'Nutzer' ? alloc.cores : null),
      memory_bytes: patch.memory_bytes !== undefined
        ? patch.memory_bytes
        : (alloc.memory_from === 'Nutzer' ? alloc.memory_bytes : null),
    }
    try {
      await api.setOverride(tpl.id, body)
      setAllocs(await api.allocations(tpl.id))
    } catch (err) {
      onToast(err instanceof ApiError ? err.message : tr('Zuteilung fehlgeschlagen'), 'bad')
    }
  }

  /** Löscht den Workspace, nachdem die Folgen genannt wurden.
   *
   * Ein Dialog statt eines stillen Klicks: Der Workspace nimmt seinen
   * App-Katalog, seine Zuteilungen und seine Image-Fassungen mit. Was er
   * *nicht* mitnimmt, ist ebenso wichtig — die Profile der Nutzer bleiben,
   * und das steht in der Frage.
   */
  async function remove() {
    const ok = window.confirm(
      tr('„{name}“ löschen?', { name: tpl.friendly_name }) + '\n\n'
      + tr('App-Katalog, Zuteilungen je Nutzer und die Image-Fassungen dieses Workspace verschwinden mit. Die Profile der Nutzer bleiben erhalten.'))
    if (!ok) return
    setBusy(true)
    try {
      await api.deleteTemplate(tpl.id)
      onToast(tr('{name} gelöscht', { name: tpl.friendly_name }))
      onSaved()
      onClose()
    } catch (err) {
      onToast(err instanceof ApiError ? err.message : tr('Löschen fehlgeschlagen'), 'bad')
    } finally {
      setBusy(false)
    }
  }

  /* Von OTA gebaute Images zuerst: Sie sind fast immer gemeint, und
     dazwischen liegen sonst fünfzig fremde Einträge. */
  const imageOptions = [...images]
    .sort((a, b) => Number(b.origin === 'ota') - Number(a.origin === 'ota')
      || a.ref.localeCompare(b.ref))
    .map((i) => ({
      value: i.ref,
      label: i.ref,
      sub: `${(i.size_bytes / GB).toFixed(2)} GB${i.origin === 'ota' ? ' · OTA' : ''}`,
    }))

  const groupDelta = draft.group_ids.length - tpl.group_ids.length

  return (
    <Workbench
      crumb={tr('Workspaces')}
      title={draft.friendly_name || tr('Neuer Workspace')}
      subtitle={draft.image_ref}
      tabs={TABS} tabLabel={tr} tab={tab} onTab={setTab} onBack={onClose}
      actions={
        <>
          {/* Löschen steht abgesetzt: Es ist nicht dieselbe Art Handlung wie
              Speichern und gehört nicht in dieselbe Reihe. */}
          <button className="btn btn--halt btn--sm" style={{ marginRight: 10 }}
            disabled={busy} onClick={() => void remove()}>{tr('Löschen')}</button>
          <button className="btn btn--ghost" onClick={onClose}>{tr('Verwerfen')}</button>
          <button className="btn btn--primary" disabled={busy} onClick={() => void save()}>
            {busy ? tr('Wird gespeichert…') : tr('Änderungen speichern')}
          </button>
        </>
      }
    >
      {tab === 'Allgemein' && (
        <>
          <Field label={tr('Anzeigename')} hint={tr('So erscheint der Workspace auf der Kachel im Dashboard.')}>
            <div className="row-item">
              <input value={draft.friendly_name} aria-label={tr('Anzeigename')}
                onChange={(e) => set('friendly_name', e.target.value)} />
            </div>
          </Field>

          <Field label={tr('Beschreibung')} hint={tr('Ein Satz, der Nutzern sagt, wofür sie diesen Workspace öffnen.')}>
            <div className="row-item">
              <input value={draft.description} aria-label={tr('Beschreibung')}
                onChange={(e) => set('description', e.target.value)} />
            </div>
          </Field>

          <Field label={tr('Image')}
            hint={tr('Die Auswahl zeigt, was auf diesem Host liegt — von OTA gebaute zuerst. Ein Image, das noch nicht da ist, holst du unter Images.')}>
            <Combobox label={tr('Image')} value={draft.image_ref}
              options={imageOptions}
              onChange={(v) => set('image_ref', v)} />
            {/* Die Auswahl war bisher ein geschlossener Kreis: Was nicht
                zufällig auf dem Host lag, liess sich nicht eintragen. Hier
                steht die Adresse frei — sie muss beim Start vorhanden sein,
                nicht beim Speichern. */}
            <div className="row-item" style={{ marginTop: 8 }}>
              <input value={draft.image_ref} spellCheck={false}
                placeholder="kasmweb/gimp:1.18.0-rolling-weekly"
                aria-label={tr('Image-Adresse')}
                onChange={(e) => set('image_ref', e.target.value)} />
            </div>
            {draft.image_ref && !images.some((i) => i.ref === draft.image_ref) && (
              <p className="note-warn" style={{ marginTop: 8 }}>
                {tr('Dieses Image liegt nicht auf dem Host. Hol es unter Images, sonst scheitert der erste Start.')}
              </p>
            )}
          </Field>

          <Field label={tr('Betriebsart')}
            hint={draft.mode === 'workspace'
              ? tr('Ein Linux je Nutzer mit mehreren Apps darin. Der Standard.')
              : tr('Eine Anwendung als Wegwerf-Container. Für selten genutzte Werkzeuge.')}>
            <Segmented label={tr('Betriebsart')} value={draft.mode}
              options={[
                { value: 'workspace' as const, label: tr('Arbeitsplatz') },
                { value: 'single_app' as const, label: tr('Einzelne App') },
              ]}
              onChange={(v) => set('mode', v)} />
          </Field>

          <Field label={tr('Streaming')}
            hint={draft.stream_engine === 'selkies'
              ? tr('H.264 über WebRTC. Die Vorgabe, und der Weg des eigenen Basisimages.')
              : tr('RFB über KasmVNC. Nötig für Images von Kasm — die bringen kein Selkies mit.')}>
            <Segmented label={tr('Streaming')} value={draft.stream_engine ?? 'selkies'}
              options={[
                { value: 'selkies' as const, label: tr('Selkies (WebRTC)') },
                { value: 'kasmvnc' as const, label: tr('KasmVNC (RFB)') },
              ]}
              onChange={(v) => set('stream_engine', v)} />
          </Field>

          <Field label={tr('Netz')}
            hint={tr('Was dieser Arbeitsplatz im Netz erreichen darf. Ohne Profil gilt die Vorgabe: Internet ja, Firmennetz nein, Nachbarsitzung nein.')}>
            <select value={draft.net_profile_id ?? ''}
              aria-label={tr('Netzprofil')}
              onChange={(e) => set('net_profile_id', e.target.value || null)}>
              <option value="">{tr('Vorgabe (Internet, kein Firmennetz)')}</option>
              {netzprofile.map((p) => (
                <option key={p.id} value={p.id}>{p.name}</option>
              ))}
            </select>
          </Field>

          <Field label={tr('Kategorien')} hint={tr('Bestimmt, unter welchem Filter der Workspace erscheint.')}>
            <ChipSelect label={tr('Kategorien')} selected={draft.categories} options={ALL_CATEGORIES}
              onChange={(v) => set('categories', v)} />
          </Field>

          <Field label={tr('Sichtbarkeit')}>
            <Toggle on={draft.is_enabled} name={tr('Workspace ist aktiv')}
              note={draft.is_enabled
                ? tr('Zugewiesene Nutzer können ihn starten.')
                : tr('Niemand kann ihn starten, die Zuweisung bleibt bestehen.')}
              onChange={(v) => set('is_enabled', v)} />
          </Field>
        </>
      )}

      {tab === 'Software' && (
        <Software tpl={tpl} onToast={onToast} onChanged={onSaved} />
      )}

      {tab === 'Apps' && (
        <>
          <p className="sub" style={{ marginBottom: 6 }}>
            {tr('Diese Anwendungen sind im Golden Image installiert. Jede bekommt beim Start ein eigenes Display im selben Container und teilt sich mit den anderen das Zuhause.')}
          </p>
          <p className="note-warn">
            {tr('Extensions wandern nicht zwischen den Editoren. Jeder bezieht sie aus seiner eigenen Quelle.')}
          </p>
          {draft.apps.length === 0 ? (
            <p className="assign__empty" style={{ marginTop: 18 }}>
              {tr('Für dieses Image ist noch kein App-Katalog hinterlegt. Er entsteht mit dem Golden Image.')}
            </p>
          ) : (
            <div className="applist">
              {draft.apps.map((a) => (
                <div key={a.slug} className={`applist__row${a.blocked_reason ? ' is-blocked' : ''}`}>
                  <AppIcon className="tile__icon" url={a.icon_url} glyph={a.icon} size={18} />
                  <span className="applist__body">
                    <span className="applist__name">{a.name}</span>
                    {a.blocked_reason
                      ? <span className="applist__block">{a.blocked_reason}</span>
                      : a.registry_hint && <span className="applist__reg">{tr('Extensions aus:')} {a.registry_hint}</span>}
                  </span>
                  <Toggle on={a.is_enabled && !a.blocked_reason} name=""
                    ariaLabel={tr('{app} bereitstellen', { app: a.name })}
                    onChange={(v) => !a.blocked_reason && set('apps',
                      draft.apps.map((x) => (x.slug === a.slug ? { ...x, is_enabled: v } : x)))} />
                </div>
              ))}
            </div>
          )}
        </>
      )}

      {tab === 'Ressourcen' && (
        <>
          {draft.mode === 'workspace' && (
            <p className="note-info">
              {tr('Die Werte gelten für den Container als Ganzes, nicht je App. Er muss auf die Spitze ausgelegt sein — auf alles, was ein Nutzer gleichzeitig offen hat.')}
            </p>
          )}

          <Field label={tr('Prozessorkerne')} hint={tr('Dieser Host hat {n} Kerne.', { n: hostCores })}>
            <CapacityFader aria-label={tr('Prozessorkerne')}
              value={draft.cores} min={0.5} max={8} step={0.5} limit={hostCores}
              format={(v) => v.toString().replace('.', ',')}
              unit={draft.cores === 1 ? tr('Kern') : tr('Kerne')}
              ticks={[0.5, 2, 4, 6, 8]} tickLabel={(t) => String(t)}
              overMessage={tr('Über {n} Kernen teilen sich die Sessions die CPU.', { n: hostCores })}
              onChange={(v) => set('cores', v)} />
          </Field>

          <Field label={tr('Arbeitsspeicher')}
            hint={host
              ? tr('Der Host hat {total} GB, davon sind gerade {free} GB frei.',
                   { total: gb(host.memory_total, 0), free: gb(freeBytes) })
              : tr('Host-Auslastung nicht verfügbar.')}>
            <CapacityFader aria-label={tr('Arbeitsspeicher')}
              value={draft.memory_bytes / GB} min={0.5} max={16} step={0.1} limit={freeGb}
              format={(v) => gb(v * GB)} unit="GB"
              ticks={[0.5, 4, 8, 12, 16]} tickLabel={(t) => String(t)}
              overMessage={tr('Mehr als {free} GB sind gerade nicht frei. Der Start würde abgelehnt.',
                { free: gb(freeBytes) })}
              onChange={(v) => set('memory_bytes', v * GB)} />
          </Field>

          <Field label={tr('Auflösung')} hint={tr('Nutzer können sie in der Session jederzeit ändern.')}>
            <Combobox label={tr('Auflösung')} value={`${draft.x_res}x${draft.y_res}`}
              options={[
                { value: '1280x720', label: '1280 × 720', sub: 'HD' },
                { value: '1920x1080', label: '1920 × 1080', sub: 'Full HD' },
                { value: '2560x1440', label: '2560 × 1440', sub: 'QHD' },
              ]}
              onChange={(v) => {
                const [x, y] = v.split('x').map(Number)
                setDraft({ ...draft, x_res: x, y_res: y })
              }} />
          </Field>

          <Field label={tr('Sitzung endet nach Inaktivität')}
            hint={tr('Gemessen ab dem letzten Lebenszeichen des Browsers.')}>
            <CapacityFader aria-label={tr('Zeit bis zur Inaktivität')}
              value={Math.max(0, IDLE_STEPS.indexOf(draft.idle_minutes))}
              min={0} max={IDLE_STEPS.length - 1} step={1}
              format={(i) => idleLabel(IDLE_STEPS[i])}
              ticks={[0, 1, 2, 3, 4, 5]} tickLabel={(i) => idleLabel(IDLE_STEPS[i])}
              onChange={(i) => set('idle_minutes', IDLE_STEPS[i])} />
          </Field>

          <Field label={tr('Was dann passiert')}
            hint={draft.idle_action === 'delete'
              ? tr('Der Container wird entfernt. Das persistente Profil bleibt erhalten.')
              : draft.idle_action === 'pause'
                ? tr('Der Container behält seinen Arbeitsspeicher und ist sofort wieder da.')
                : tr('Der Container wird gestoppt und beim nächsten Mal neu gestartet.')}>
            <Segmented label={tr('Aktion bei Inaktivität')} value={draft.idle_action}
              options={[
                { value: 'pause' as const, label: tr('Pausieren') },
                { value: 'stop' as const, label: tr('Stoppen') },
                { value: 'delete' as const, label: tr('Löschen'), tone: 'halt' as const },
              ]}
              onChange={(v) => set('idle_action', v)} />
          </Field>

          <Field label={tr('Eigene Ablage')}
            hint={draft.user_shelf
              ? tr('Liegt im Container unter /mnt/austausch und als „Austausch" im Home. Jeder sieht nur seine eigene.')
              : tr('Ohne sie führt kein Weg über den Browser in diesen Container hinein oder heraus — ausser dem, den die Rechte ohnehin erlauben.')}>
            <Toggle on={draft.user_shelf}
              name={tr('Eigene Ablage einhängen')}
              note={tr('Der übliche Weg, Dateien hinein und heraus zu bekommen')}
              onChange={(v) => set('user_shelf', v)} />
          </Field>

          <Field label={tr('Gruppenlaufwerke')}
            hint={draft.group_shelf
              ? tr('Je Gruppe des Nutzers ein Ordner unter /mnt/gruppen und als „Gruppen" im Home. Alle Mitglieder sehen dasselbe.')
              : tr('Ohne sie bleibt dieser Arbeitsplatz abgeschottet — auch von den Dateien der eigenen Gruppen.')}>
            <Toggle on={draft.group_shelf}
              name={tr('Gruppenlaufwerke einhängen')}
              note={tr('Der übliche Weg, im Team an denselben Dateien zu arbeiten')}
              onChange={(v) => set('group_shelf', v)} />
          </Field>

          <Field label={tr('Persistentes Profil')}
            hint={draft.persistence_scope === 'user'
              ? tr('Ein gemeinsames Home für alle Workspaces dieses Nutzers.')
              : draft.persistence_scope === 'template'
                ? tr('Ein eigenes Home nur für diesen Workspace-Typ.')
                : tr('Nichts wird gespeichert. Jeder Start beginnt beim Golden Image.')}>
            <Segmented label={tr('Persistenz')} value={draft.persistence_scope}
              options={[
                { value: 'user' as const, label: tr('Pro Nutzer') },
                { value: 'template' as const, label: tr('Pro Workspace') },
                { value: 'none' as const, label: tr('Flüchtig') },
              ]}
              onChange={(v) => set('persistence_scope', v)} />
          </Field>
        </>
      )}

      {tab === 'Rechte' && (
        <>
          <p className="sub" style={{ marginBottom: 16 }}>
            {tr('Gilt für alle Nutzer dieses Workspace. Gruppen können strenger sein, nie großzügiger.')}
          </p>
          {['Zwischenablage', 'Dateien', 'Geräte', 'Sonstiges'].map((grp) => (
            <div key={grp} style={{ marginBottom: 18 }}>
              <div className="section__head" style={{ marginBottom: 4 }}>
                <span className="silk">{tr(grp)}</span><span className="section__rule" />
              </div>
              {grp === 'Zwischenablage' && draft.mode === 'workspace' && (
                <p className="note-info" style={{ marginTop: 10, marginBottom: 6 }}>
                  {tr('Die Brücke hält die Zwischenablage über alle Apps im Container gleich. Wird das Kopieren hier abgeschaltet, läuft auch die Brücke nicht.')}
                </p>
              )}
              {RIGHTS_META.filter((r) => r.group === grp).map((r) => (
                <Toggle key={r.key} on={!!draft.rights[r.key]} name={tr(r.name)} note={tr(r.note)}
                  onChange={(v) => set('rights', { ...draft.rights, [r.key]: v })} />
              ))}
            </div>
          ))}
        </>
      )}

      {tab === 'Skeleton' && (
        <Skeleton tpl={tpl} enforce={draft.skeleton_enforce ?? []}
          onEnforce={(v) => set('skeleton_enforce', v)} onToast={onToast} />
      )}

      {tab === 'Umgebung' && (
        <>
          <Field label={tr('Umgebungsvariablen')}
            hint={tr('Keine Geheimnisse hier — Umgebungsvariablen sind über docker inspect lesbar und landen in Logs.')}>
            <KeyValueRows rows={draft.env_rows} onChange={(v) => set('env_rows', v)}
              keyPlaceholder={tr('Name')} valuePlaceholder={tr('Wert')} addLabel={tr('Variable hinzufügen')} />
          </Field>

          <Field label={tr('Skript beim Start')}
            hint={tr('Läuft bei jedem Sessionstart als Nutzer im Container, bevor der Arbeitsplatz bereit ist. Für alles, was ins Home gehört, aber nicht ins Image.')}>
            <textarea className="build__log" spellCheck={false}
              style={{ minHeight: 200, width: '100%', color: 'var(--text)', resize: 'vertical' }}
              value={draft.start_script} aria-label={tr('Skript beim Start')}
              placeholder={'# $OTA_SHARED zeigt auf die gemeinsame Ablage.\n'
                + 'mkdir -p "$HOME/.pki"\n'
                + 'cp "$OTA_SHARED"/zertifikate/*.crt "$HOME/.pki/" 2>/dev/null || true\n'}
              onChange={(e) => set('start_script', e.target.value)} />
            <p className="note-info" style={{ marginTop: 10 }}>
              {tr('Nicht für Installationen — die gehören ins Golden Image, sonst wartet jeder Nutzer bei jedem Start darauf. Scheitert das Skript, startet der Arbeitsplatz trotzdem; die Ausgabe steht im Container unter /tmp/ota-start.log.')}
            </p>
          </Field>
        </>
      )}

      {tab === 'Einmal' && <OnceScripts templateId={tpl.id} onToast={onToast} />}

      {tab === 'Zuteilung' && (
        <>
          <Field label={tr('Gruppen')} hint={tr('Nur Mitglieder dieser Gruppen sehen den Workspace in ihrem Dashboard.')}>
            <div className="assign">
              <div className="assign__col">
                <div className="assign__head"><span className="silk">{tr('Verfügbar')}</span></div>
                <div className="assign__list">
                  {groups.filter((g) => !draft.group_ids.includes(g.id)).map((g) => (
                    <button key={g.id} className="assign__item"
                      onClick={() => set('group_ids', [...draft.group_ids, g.id])}>
                      <span aria-hidden="true" style={{ color: 'var(--mute)' }}>+</span>
                      {g.name}
                      <span className="assign__count">{g.member_count}</span>
                    </button>
                  ))}
                  {groups.every((g) => draft.group_ids.includes(g.id)) &&
                    <p className="assign__empty">{tr('Alle Gruppen zugewiesen')}</p>}
                </div>
              </div>
              <div className="assign__col">
                <div className="assign__head"><span className="silk">Zugewiesen</span></div>
                <div className="assign__list">
                  {draft.group_ids.map((id) => {
                    const g = groups.find((x) => x.id === id)
                    if (!g) return null
                    return (
                      <button key={id} className="assign__item"
                        onClick={() => set('group_ids', draft.group_ids.filter((x) => x !== id))}>
                        <span aria-hidden="true" style={{ color: 'var(--halt)' }}>−</span>
                        {g.name}
                        <span className="assign__count">{g.member_count}</span>
                      </button>
                    )
                  })}
                  {draft.group_ids.length === 0 &&
                    <p className="assign__empty">{tr('Niemand sieht diesen Workspace')}</p>}
                </div>
              </div>
            </div>
            {groupDelta !== 0 && (
              <p className="delta">
                {groupDelta > 0
                  ? `${groupDelta} Gruppe${groupDelta > 1 ? 'n kommen' : ' kommt'} hinzu. Betroffene Nutzer sehen den Workspace nach dem Speichern.`
                  : `${-groupDelta} Gruppe${-groupDelta > 1 ? 'n verlieren' : ' verliert'} den Zugriff. Laufende Sessions bleiben bestehen.`}
              </p>
            )}
          </Field>

          <div className="section__head" style={{ marginTop: 26 }}>
            <span className="silk">{tr('Ressourcen je Nutzer')}</span>
            <span className="section__rule" />
          </div>
          <p className="sub" style={{ marginBottom: 14 }}>
            Ohne eigene Zuteilung gilt die Vorgabe der Vorlage. Das Spezifischste gewinnt:
            Vorlage, dann Gruppe, dann Nutzer. Änderungen wirken auf die nächste Session.
          </p>

          {allocs === null ? (
            <p className="sub">Wird geladen…</p>
          ) : allocs.length === 0 ? (
            <p className="assign__empty">
              Erst eine Gruppe zuweisen und speichern — dann erscheinen hier deren Mitglieder.
            </p>
          ) : (
            <div className="alloc">
              {allocs.map((a) => {
                const open = openUser === a.user_id
                const custom = a.cores_from !== 'Vorlage' || a.memory_from !== 'Vorlage'
                return (
                  <div key={a.user_id} className={`alloc__row${open ? ' is-open' : ''}`}>
                    <button className="alloc__head" aria-expanded={open}
                      onClick={() => setOpenUser(open ? null : a.user_id)}>
                      <span className="alloc__name">{a.username}</span>
                      <span className="alloc__val data">{coresLabel(a.cores)}</span>
                      <span className="alloc__val data">{gb(a.memory_bytes)} GB</span>
                      <span className={`alloc__src${custom ? ' is-custom' : ''}`}>
                        {a.cores_from === a.memory_from ? a.cores_from : 'gemischt'}
                      </span>
                      <span className="alloc__caret" aria-hidden="true">{open ? '▲' : '▼'}</span>
                    </button>

                    {open && (
                      <div className="alloc__body">
                        <Field label={tr('Prozessorkerne für diesen Nutzer')}
                          inherited={a.cores_from !== 'Nutzer' ? tr(a.cores_from) : undefined}
                          onReset={a.cores_from === 'Nutzer'
                            ? () => void setOverride(a.user_id, { cores: null })
                            : undefined}>
                          <CapacityFader aria-label={tr('Prozessorkerne für {name}', { name: a.username })}
                            value={a.cores} min={0.5} max={8} step={0.5} limit={hostCores}
                            format={(v) => v.toString().replace('.', ',')}
                            unit={a.cores === 1 ? tr('Kern') : tr('Kerne')}
                            ticks={[0.5, 2, 4, 6, 8]} tickLabel={(x) => String(x)}
                            overMessage={tr('Über {n} Kernen teilen sich die Sessions die CPU.',
                              { n: hostCores })}
                            onChange={(v) => void setOverride(a.user_id, { cores: v })} />
                        </Field>

                        <Field label={tr('Arbeitsspeicher für diesen Nutzer')}
                          inherited={a.memory_from !== 'Nutzer' ? tr(a.memory_from) : undefined}
                          onReset={a.memory_from === 'Nutzer'
                            ? () => void setOverride(a.user_id, { memory_bytes: null })
                            : undefined}>
                          <CapacityFader aria-label={tr('Arbeitsspeicher für {name}', { name: a.username })}
                            value={a.memory_bytes / GB} min={0.5} max={16} step={0.1} limit={freeGb}
                            format={(v) => gb(v * GB)} unit="GB"
                            ticks={[0.5, 4, 8, 12, 16]} tickLabel={(x) => String(x)}
                            overMessage={tr('Mehr als {free} GB sind gerade nicht frei.',
                              { free: gb(freeBytes) })}
                            onChange={(v) => void setOverride(a.user_id, { memory_bytes: Math.round(v * GB) })} />
                        </Field>
                      </div>
                    )}
                  </div>
                )
              })}
            </div>
          )}
        </>
      )}
    </Workbench>
  )
}

export function Workspaces({ onToast }: { onToast: (m: string, tone?: 'ok' | 'bad') => void }) {
  useLang()
  const [list, setList] = useState<Template[] | null>(null)
  const [groups, setGroups] = useState<Group[]>([])
  const [images, setImages] = useState<HostImage[]>([])
  const [host, setHost] = useState<Host | null>(null)
  const [netzprofile, setNetzprofile] = useState<NetzProfil[]>([])
  const [editing, setEditing] = useState<Template | null>(null)
  const [failed, setFailed] = useState<string | null>(null)

  async function load() {
    try {
      const [t, g, i, h, n] = await Promise.all([
        api.templates(), api.groups(), api.images(), api.host(),
        // Ohne Recht auf die Einstellungen gibt es keine Profile zu sehen —
        // dann bleibt die Auswahl bei der Vorgabe, statt die Seite zu kippen.
        api.netProfiles().catch(() => [] as NetzProfil[]),
      ])
      setList(t); setGroups(g); setImages(i); setHost(h); setNetzprofile(n)
      setFailed(null)
    } catch (err) {
      setFailed(err instanceof ApiError ? err.message : 'Laden fehlgeschlagen')
    }
  }

  useEffect(() => { void load() }, [])

  const committed = useMemo(
    () => (list ?? []).filter((t) => t.is_enabled).reduce((a, t) => a + t.memory_bytes, 0),
    [list],
  )

  async function create() {
    try {
      const t = await api.createTemplate({
        friendly_name: 'Neuer Arbeitsplatz',
        description: '',
        image_ref: images[0]?.ref ?? 'ota/base-desktop:1',
        mode: 'workspace',
        stream_engine: 'selkies',
        cores: 2, memory_bytes: 2 * GB,
        rights: { clipboardUp: true, clipboardDown: true, clipboardImages: true },
        group_ids: [],
      })
      onToast(tr('Workspace angelegt'))
      await load()
      setEditing(t)
    } catch (err) {
      onToast(err instanceof ApiError ? err.message : tr('Anlegen fehlgeschlagen'), 'bad')
    }
  }

  if (failed) {
    return (
      <div className="wrap">
        <div className="empty">
          <p className="empty__title">{tr('Die Verwaltung konnte nicht geladen werden')}</p>
          <p className="empty__body">{failed}</p>
          <button className="btn" onClick={() => void load()}>Erneut versuchen</button>
        </div>
      </div>
    )
  }
  if (!list || !host) return <div className="wrap"><p className="sub">Wird geladen…</p></div>

  const usedPct = ((host.memory_total - host.memory_available) / host.memory_total) * 100

  // Bearbeiten ersetzt die Liste, statt sie zu überlagern: Man ist dann eine
  // Ebene tiefer (Workspaces / Arbeitsplatz) und nicht in einem Dialog.
  if (editing) {
    return (
      <Editor tpl={editing} host={host} groups={groups} images={images}
        netzprofile={netzprofile}
        onClose={() => setEditing(null)}
        onSaved={() => { setEditing(null); void load() }}
        onToast={onToast} />
    )
  }

  return (
    <div className="wrap">
      <header className="topbar">
        <div>
          <p className="silk" style={{ marginBottom: 6 }}>{tr('Verwaltung')}</p>
          <h1 className="h-page">Workspaces</h1>
        </div>
        <button className="btn btn--primary" onClick={() => void create()}>{tr('Workspace anlegen')}</button>
      </header>

      <div className="meters">
        <div className="panel meter">
          <div className="meter__top"><span className="silk">{tr('Arbeitsspeicher frei')}</span>
            <span className="meter__val">{gb(host.memory_available)} GB</span></div>
          <div className="meter__bar">
            <div className="meter__fill" data-tone={usedPct > 85 ? 'caution' : undefined}
              style={{ width: `${usedPct}%` }} />
          </div>
          <p className="meter__note">{tr('von {n} GB', { n: gb(host.memory_total, 0) })}</p>
        </div>

        <div className="panel meter">
          <div className="meter__top"><span className="silk">{tr('Zugesagt je Session')}</span>
            <span className="meter__val">{gb(committed)} GB</span></div>
          <div className="meter__bar">
            <div className="meter__fill" data-tone={committed > host.memory_available ? 'halt' : 'caution'}
              style={{ width: `${Math.min(100, (committed / host.memory_total) * 100)}%` }} />
          </div>
          <p className="meter__note">
            {tr('wenn alle {n} Workspaces gleichzeitig laufen',
              { n: list.filter((t) => t.is_enabled).length })}
          </p>
        </div>

        <div className="panel meter">
          <div className="meter__top"><span className="silk">{tr('Kerne')}</span>
            <span className="meter__val">{host.cores}</span></div>
          <div className="meter__bar"><div className="meter__fill" style={{ width: '100%' }} /></div>
          <p className="meter__note">
            Docker {host.docker_version} · {tr('{n} Container', { n: host.running_containers })}
          </p>
        </div>
      </div>

      <section className="section">
        {list.length === 0 ? (
          <div className="empty">
            <p className="empty__title">{tr('Noch kein Workspace angelegt')}</p>
            <p className="empty__body">
              {tr('Lege einen Arbeitsplatz an und weise ihn einer Gruppe zu — dann erscheint er im Dashboard der Nutzer.')}
            </p>
            <button className="btn btn--primary" onClick={() => void create()}>{tr('Workspace anlegen')}</button>
          </div>
        ) : (
          <div className="panel" style={{ padding: '14px 0 0' }}>
            <table className="tbl">
              <thead>
                <tr>
                  <th style={{ paddingLeft: 20 }}>{tr('Workspace')}</th>
                  <th>{tr('Art')}</th>
                  <th>{tr('Ressourcen')}</th>
                  <th>{tr('Gruppen')}</th>
                  <th>{tr('Status')}</th>
                </tr>
              </thead>
              <tbody>
                {list.map((t) => (
                  <tr key={t.id} tabIndex={0} onClick={() => setEditing(t)}
                    onKeyDown={(e) => { if (e.key === 'Enter') setEditing(t) }}>
                    <td style={{ paddingLeft: 20 }}>
                      <div style={{ display: 'flex', alignItems: 'center', gap: 11 }}>
                        <span className="tile__icon" style={{ width: 28, height: 28, fontSize: 14 }}
                          aria-hidden="true">{t.icon}</span>
                        <div>
                          <div style={{ fontWeight: 500 }}>{t.friendly_name}</div>
                          <div className="data" style={{ fontSize: 11, color: 'var(--mute)' }}>{t.image_ref}</div>
                        </div>
                      </div>
                    </td>
                    <td style={{ color: 'var(--label)', fontSize: 12.5 }}>
                      {t.mode === 'workspace' ? 'Arbeitsplatz' : 'Einzelne App'}
                    </td>
                    <td className="data" style={{ color: 'var(--label)' }}>
                      {t.cores} × {gb(t.memory_bytes)} GB
                    </td>
                    <td style={{ color: 'var(--label)' }}>
                      {t.group_ids.length
                        ? t.group_ids.map((g) => groups.find((x) => x.id === g)?.name).filter(Boolean).join(', ')
                        : '—'}
                    </td>
                    <td><Led status={t.is_enabled ? 'live' : 'stopped'} /></td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </section>

    </div>
  )
}
