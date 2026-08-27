import { useEffect, useState } from 'react'
import { Field, Segmented, Toggle } from '../components/controls'
import { ApiError, api, type Recipe, type RecipeKind } from '../lib/api'
import { t as tr, useLang } from '../lib/i18n'

/**
 * Ein Rezept aus wenigen Fragen bauen.
 *
 * Bisher gab es drei fest eingebaute Rezepte und sonst ein leeres Skriptfeld.
 * Wer eine vierte Anwendung brauchte, sass wieder vor genau dem, was diese
 * Oberfläche vermeiden soll.
 *
 * Vier Muster decken fast alles ab, was in einen Arbeitsplatz soll. Die
 * Führung fragt je Muster nur nach dem, was sich nicht ableiten lässt — und
 * zeigt daneben, was daraus wird. Das Skript wird nicht versteckt: Wer es
 * anders will, schreibt darin weiter, und dann gilt seine Fassung.
 */

const KINDS: { value: RecipeKind; label: string; blurb: string }[] = [
  { value: 'apt_repo', label: 'APT-Depot',
    blurb: 'Ein fremdes Paketdepot einbinden und daraus installieren. Der häufigste Fall — so kommen Firefox, Chrome und VSCodium ins Image.' },
  { value: 'deb_url', label: '.deb-Datei',
    blurb: 'Ein einzelnes Debian-Paket von einer Adresse holen. Für Software, die als Datei ausgeliefert wird statt über ein Depot.' },
  { value: 'tarball', label: 'Archiv',
    blurb: 'Ein .tar.gz nach /opt auspacken und einen Starter anlegen. Für alles mit eigenem Verzeichnis — JetBrains, Blender.' },
  { value: 'appimage', label: 'AppImage',
    blurb: 'Eine AppImage-Datei ablegen und ausführbar machen.' },
  { value: 'script', label: 'Eigenes Skript',
    blurb: 'Freier Text. Wenn keines der Muster passt.' },
]

const GLYPHS = ['▢', '◎', '◈', '⌨', '▤', '▶', '▦', '⚙', '◍', '▮']

type Params = Record<string, string | boolean>

export function RecipeBuilder({ existing, onDone, onCancel, onToast }: {
  /** Zum Ändern oder als Vorlage einer Kopie. Ohne: neues Rezept. */
  existing?: Recipe
  onDone: () => void
  onCancel: () => void
  onToast: (m: string, tone?: 'ok' | 'bad') => void
}) {
  useLang()
  const copy = Boolean(existing?.is_builtin)
  const [name, setName] = useState(existing ? (copy ? `${existing.name} (Kopie)` : existing.name) : '')
  const [glyph, setGlyph] = useState(existing?.glyph ?? '▢')
  const [why, setWhy] = useState(existing?.why ?? '')
  const [kind, setKind] = useState<RecipeKind>(existing?.kind ?? 'apt_repo')
  const [params, setParams] = useState<Params>((existing?.params as Params) ?? {})
  const [script, setScript] = useState(existing?.script ?? '')
  // Wurde der Text von Hand angefasst? Dann wird er nicht mehr überschrieben.
  const [touched, setTouched] = useState(false)
  const [problem, setProblem] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)

  const set = (key: string, value: string | boolean) =>
    setParams((p) => ({ ...p, [key]: value }))

  /* Die Vorschau kommt vom Server, nicht aus dem Browser: Dort entsteht auch
     das echte Skript, und zwei Erzeuger für dasselbe liefen irgendwann
     auseinander. */
  useEffect(() => {
    if (kind === 'script' || touched) return
    const timer = setTimeout(() => {
      void api.previewRecipe(kind, params)
        .then((r) => { setScript(r.script); setProblem(null) })
        .catch((err) => setProblem(err instanceof ApiError ? err.message : null))
    }, 350)
    return () => clearTimeout(timer)
  }, [kind, params, touched])

  async function save() {
    if (!name.trim()) {
      onToast(tr('Das Rezept braucht einen Namen.'), 'bad')
      return
    }
    setBusy(true)
    try {
      const body = { name, glyph, why, kind, params, script: touched ? script : '' }
      if (existing && !existing.is_builtin) await api.updateRecipe(existing.id, body)
      else await api.createRecipe(body)
      onToast(tr('Rezept „{name}" gespeichert.', { name }))
      onDone()
    } catch (err) {
      onToast(err instanceof ApiError ? err.message : tr('Speichern fehlgeschlagen'), 'bad')
    } finally {
      setBusy(false)
    }
  }

  const current = KINDS.find((k) => k.value === kind)!

  return (
    <div className="recipe">
      <div className="recipe__form">
        <Field label={tr('Name')} hint={tr('So steht es später auf der Schaltfläche.')}>
          <div className="row-item">
            <button type="button" className="tile__icon applist__glyph"
              title={tr('Anderes Zeichen wählen')}
              onClick={() => setGlyph(GLYPHS[(GLYPHS.indexOf(glyph) + 1) % GLYPHS.length])}>
              {glyph}
            </button>
            <input value={name} autoFocus placeholder="Audacity"
              aria-label={tr('Name')} onChange={(e) => setName(e.target.value)} />
          </div>
        </Field>

        <Field label={tr('Art')} hint={current.blurb}>
          <Segmented label={tr('Art')} value={kind}
            options={KINDS.map((k) => ({ value: k.value, label: tr(k.label) }))}
            onChange={(v) => { setKind(v); setTouched(false) }} />
        </Field>

        {kind === 'apt_repo' && (
          <>
            <Field label={tr('Adresse des Schlüssels')}
              hint={tr('Der Signaturschlüssel des Depots. Ohne ihn nimmt apt nichts an.')}>
              <div className="row-item">
                <input value={String(params.key_url ?? '')} spellCheck={false}
                  placeholder="https://packages.mozilla.org/apt/repo-signing-key.gpg"
                  aria-label={tr('Adresse des Schlüssels')}
                  onChange={(e) => set('key_url', e.target.value)} />
              </div>
            </Field>
            <Field label={tr('Depot-Zeile')}
              hint={tr('Wie in einer sources.list. Den Teil mit signed-by lässt du weg — der wird eingesetzt.')}>
              <div className="row-item">
                <input value={String(params.repo_line ?? '')} spellCheck={false}
                  placeholder="deb https://packages.mozilla.org/apt mozilla main"
                  aria-label={tr('Depot-Zeile')}
                  onChange={(e) => set('repo_line', e.target.value)} />
              </div>
            </Field>
            <Field label={tr('Paket')} hint={tr('Was aus diesem Depot installiert werden soll.')}>
              <div className="row-item">
                <input value={String(params.package ?? '')} spellCheck={false}
                  placeholder="firefox" aria-label={tr('Paket')}
                  onChange={(e) => set('package', e.target.value)} />
              </div>
            </Field>
            <Field label={tr('Vorrang')}>
              <Toggle on={Boolean(params.pin)} name={tr('Diesem Depot Vorrang geben')}
                note={tr('Nötig, wenn die Distribution ein gleichnamiges Paket führt — sonst gewinnt deren Fassung. Genau der Fall bei Firefox auf Ubuntu.')}
                onChange={(v) => set('pin', v)} />
            </Field>
          </>
        )}

        {kind === 'deb_url' && (
          <Field label={tr('Adresse der Datei')}
            hint={tr('Fehlende Abhängigkeiten zieht apt selbst nach.')}>
            <div className="row-item">
              <input value={String(params.url ?? '')} spellCheck={false}
                placeholder="https://beispiel.de/programm_1.2_amd64.deb"
                aria-label={tr('Adresse der Datei')}
                onChange={(e) => set('url', e.target.value)} />
            </div>
          </Field>
        )}

        {(kind === 'tarball' || kind === 'appimage') && (
          <>
            <Field label={tr('Adresse der Datei')}>
              <div className="row-item">
                <input value={String(params.url ?? '')} spellCheck={false}
                  placeholder={kind === 'tarball'
                    ? 'https://download.jetbrains.com/idea/ideaIC.tar.gz'
                    : 'https://beispiel.de/Programm.AppImage'}
                  aria-label={tr('Adresse der Datei')}
                  onChange={(e) => set('url', e.target.value)} />
              </div>
            </Field>
            <Field label={tr('Kennung')}
              hint={tr('Kleingeschrieben, ohne Leerzeichen. Wird zum Verzeichnis unter /opt und zum Befehl.')}>
              <div className="row-item">
                <input value={String(params.slug ?? '')} spellCheck={false}
                  placeholder="idea" aria-label={tr('Kennung')}
                  onChange={(e) => set('slug', e.target.value)} />
              </div>
            </Field>
            {kind === 'tarball' && (
              <Field label={tr('Programm im Archiv')}
                hint={tr('Pfad innerhalb des Archivs, ohne das oberste Verzeichnis.')}>
                <div className="row-item">
                  <input value={String(params.binary ?? '')} spellCheck={false}
                    placeholder="bin/idea.sh" aria-label={tr('Programm im Archiv')}
                    onChange={(e) => set('binary', e.target.value)} />
                </div>
              </Field>
            )}
            <Field label={tr('Anzeigename im Menü')}
              hint={tr('Unter diesem Namen findet OTA die Anwendung später im Image wieder.')}>
              <div className="row-item">
                <input value={String(params.name ?? '')} placeholder="IntelliJ IDEA"
                  aria-label={tr('Anzeigename im Menü')}
                  onChange={(e) => set('name', e.target.value)} />
              </div>
            </Field>
          </>
        )}

        <Field label={tr('Wozu es da ist')}
          hint={tr('Ein Satz, der beim Überfahren der Schaltfläche erscheint. Am hilfreichsten ist der Grund, warum es kein einfaches Paket tut.')}>
          <div className="row-item">
            <input value={why} aria-label={tr('Wozu es da ist')}
              placeholder={tr('Nicht in den Ubuntu-Quellen.')}
              onChange={(e) => setWhy(e.target.value)} />
          </div>
        </Field>
      </div>

      <div className="recipe__out">
        <div className="section__head" style={{ marginBottom: 10 }}>
          <span className="silk">{tr('Das wird ausgeführt')}</span>
          <span className="section__rule" />
          {touched && (
            <button type="button" className="btn btn--sm btn--ghost"
              onClick={() => setTouched(false)}>{tr('Wieder erzeugen')}</button>
          )}
        </div>

        {problem && <p className="note-warn" style={{ marginBottom: 10 }}>{problem}</p>}

        <textarea className="build__log recipe__script" spellCheck={false}
          value={script} aria-label={tr('Skript')}
          onChange={(e) => { setScript(e.target.value); setTouched(true) }} />

        <p className="field__hint" style={{ marginTop: 8 }}>
          {touched
            ? tr('Von Hand geändert — die Angaben oben überschreiben den Text nicht mehr.')
            : tr('Läuft als root im Image, nach den Paketen. Änderst du hier etwas, bleibt deine Fassung stehen.')}
        </p>

        <div className="viewer__row" style={{ marginTop: 14 }}>
          <button className="btn btn--primary" disabled={busy} onClick={() => void save()}>
            {busy ? tr('Wird gespeichert…') : tr('Rezept speichern')}
          </button>
          <button className="btn btn--ghost" onClick={onCancel}>{tr('Abbrechen')}</button>
        </div>
      </div>
    </div>
  )
}
