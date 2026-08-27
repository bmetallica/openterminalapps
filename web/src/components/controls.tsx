import { useEffect, useRef, useState } from 'react'
import { t } from '../lib/i18n'

/* ============================================================
   SIGNATURE — Kapazitäts-Fader
   Die Schiene zeigt, ab welchem Wert dieser Host überbucht wäre.
   ============================================================ */

type FaderProps = {
  value: number
  min: number
  max: number
  step: number
  /** Ab hier ist der Host überbucht. Weglassen = keine Zone. */
  limit?: number
  format: (v: number) => string
  unit?: string
  ticks: number[]
  tickLabel: (v: number) => string
  overMessage?: string
  onChange: (v: number) => void
  'aria-label': string
}

export function CapacityFader({
  value, min, max, step, limit, format, unit, ticks, tickLabel, overMessage, onChange,
  'aria-label': ariaLabel,
}: FaderProps) {
  const pct = ((value - min) / (max - min)) * 100
  const limitPct = limit === undefined ? 100 : ((limit - min) / (max - min)) * 100
  const isOver = limit !== undefined && value > limit

  return (
    <div className={`fader${isOver ? ' is-over' : ''}`} style={{ ['--pct' as string]: `${pct}%`, ['--limit' as string]: `${limitPct}%` }}>
      <div className="fader__read">
        <span className="fader__value">{format(value)}</span>
        {unit && <span className="fader__unit">{unit}</span>}
      </div>

      <div className="fader__track">
        <div className="fader__rail" aria-hidden="true">
          <div className="fader__fill" />
          {limit !== undefined && limitPct < 100 && <div className="fader__over" />}
        </div>
        <input
          className="fader__input"
          type="range"
          min={min} max={max} step={step} value={value}
          aria-label={ariaLabel}
          aria-valuetext={format(value) + (unit ? ` ${unit}` : '')}
          onChange={(e) => onChange(Number(e.target.value))}
        />
      </div>

      <div className="fader__scale" aria-hidden="true">
        {ticks.map((t) => (
          <span key={t} className="fader__tick" style={{ left: `${((t - min) / (max - min)) * 100}%` }}>
            {tickLabel(t)}
          </span>
        ))}
      </div>

      {isOver && overMessage && (
        <p className="fader__warn"><span aria-hidden="true">▲</span>{overMessage}</p>
      )}
    </div>
  )
}

/* ============================================================
   Toggle
   ============================================================ */

export function Toggle({ on, name, note, ariaLabel, onChange }: {
  on: boolean; name: string; note?: string; ariaLabel?: string; onChange: (v: boolean) => void
}) {
  return (
    <button type="button" className="toggle" aria-pressed={on}
      aria-label={ariaLabel ?? undefined} onClick={() => onChange(!on)}>
      <span className="toggle__switch" aria-hidden="true"><span className="toggle__knob" /></span>
      <span className="toggle__body">
        <span className="toggle__name">{name}</span>
        {note && <span className="toggle__note">{note}</span>}
      </span>
    </button>
  )
}

/* ============================================================
   Segmented Control
   ============================================================ */

export function Segmented<T extends string>({ value, options, onChange, label }: {
  value: T
  options: { value: T; label: string; tone?: 'halt' }[]
  onChange: (v: T) => void
  label: string
}) {
  return (
    <div className="seg" role="radiogroup" aria-label={label}>
      {options.map((o) => (
        <button
          key={o.value} type="button" role="radio" aria-checked={value === o.value}
          data-tone={o.tone}
          className={`seg__opt${value === o.value ? ' is-on' : ''}`}
          onClick={() => onChange(o.value)}
        >{o.label}</button>
      ))}
    </div>
  )
}

/* ============================================================
   Combobox mit Suche
   ============================================================ */

export function Combobox({ value, options, onChange, label, placeholder }: {
  value: string
  options: { value: string; label: string; sub?: string }[]
  onChange: (v: string) => void
  label: string
  placeholder?: string
}) {
  const [open, setOpen] = useState(false)
  const [q, setQ] = useState('')
  const box = useRef<HTMLDivElement>(null)

  useEffect(() => {
    if (!open) return
    const away = (e: MouseEvent) => { if (box.current && !box.current.contains(e.target as Node)) setOpen(false) }
    const esc = (e: KeyboardEvent) => { if (e.key === 'Escape') setOpen(false) }
    document.addEventListener('mousedown', away)
    document.addEventListener('keydown', esc)
    return () => { document.removeEventListener('mousedown', away); document.removeEventListener('keydown', esc) }
  }, [open])

  const current = options.find((o) => o.value === value)
  const shown = options.filter((o) => o.label.toLowerCase().includes(q.toLowerCase()))

  return (
    <div className="select" ref={box}>
      <button
        type="button" className="select__btn" aria-haspopup="listbox" aria-expanded={open}
        aria-label={label} onClick={() => { setOpen(!open); setQ('') }}
      >
        <span>{current?.label ?? placeholder ?? t('Bitte wählen')}</span>
        {current?.sub && <span className="select__sub">{current.sub}</span>}
      </button>
      <span className="select__caret" aria-hidden="true">▼</span>

      {open && (
        <div className="pop" role="listbox">
          {options.length > 6 && (
            <input
              className="pop__search" autoFocus value={q} placeholder={t('Suchen…')}
              onChange={(e) => setQ(e.target.value)} aria-label={t('Auswahl durchsuchen')}
            />
          )}
          {shown.map((o) => (
            <button
              key={o.value} type="button" role="option" aria-selected={o.value === value}
              className={`pop__opt${o.value === value ? ' is-on' : ''}`}
              onClick={() => { onChange(o.value); setOpen(false) }}
            >
              <span>{o.label}</span>
              {o.sub && <span className="select__sub">{o.sub}</span>}
            </button>
          ))}
          {shown.length === 0 && <p className="pop__empty">{t('Nichts gefunden für „{q}"', { q })}</p>}
        </div>
      )}
    </div>
  )
}

/* ============================================================
   Chips — Mehrfachauswahl
   ============================================================ */

export function ChipSelect({ selected, options, onChange, label }: {
  selected: string[]; options: string[]; onChange: (v: string[]) => void; label: string
}) {
  return (
    <div className="chips" role="group" aria-label={label}>
      {options.map((o) => {
        const on = selected.includes(o)
        return (
          <button
            key={o} type="button" aria-pressed={on} className={`chip${on ? ' is-on' : ''}`}
            onClick={() => onChange(on ? selected.filter((s) => s !== o) : [...selected, o])}
          >{o}</button>
        )
      })}
    </div>
  )
}

/* ============================================================
   Zeilen-Builder für Key/Value
   ============================================================ */

export function KeyValueRows({ rows, onChange, keyPlaceholder, valuePlaceholder, addLabel }: {
  rows: { k: string; v: string }[]
  onChange: (r: { k: string; v: string }[]) => void
  keyPlaceholder: string
  valuePlaceholder: string
  addLabel: string
}) {
  return (
    <div className="rows">
      {rows.map((row, i) => (
        <div className="row-item" key={i}>
          <input
            value={row.k} placeholder={keyPlaceholder} aria-label={`${keyPlaceholder} ${i + 1}`}
            onChange={(e) => onChange(rows.map((r, j) => (j === i ? { ...r, k: e.target.value } : r)))}
          />
          <input
            value={row.v} placeholder={valuePlaceholder} aria-label={`${valuePlaceholder} ${i + 1}`}
            onChange={(e) => onChange(rows.map((r, j) => (j === i ? { ...r, v: e.target.value } : r)))}
          />
          <button
            type="button" className="btn btn--icon btn--ghost"
            aria-label={t('Zeile {n} entfernen', { n: i + 1 })}
            onClick={() => onChange(rows.filter((_, j) => j !== i))}
          >✕</button>
        </div>
      ))}
      <div>
        <button type="button" className="btn btn--sm" onClick={() => onChange([...rows, { k: '', v: '' }])}>
          <span aria-hidden="true">+</span>{addLabel}
        </button>
      </div>
    </div>
  )
}

/* ============================================================
   Feld-Gerüst mit Vererbungsmarke
   ============================================================ */

export function Field({ label, hint, inherited, onReset, children }: {
  label: string
  hint?: string
  inherited?: string
  onReset?: () => void
  children: React.ReactNode
}) {
  return (
    <div className="field">
      <div className="field__head">
        <span className="field__label">{label}</span>
        {inherited && (
          <span className="inherit">
            {t('geerbt von {source}', { source: inherited })}
            {onReset && <button type="button" onClick={onReset}>{t('zurücksetzen')}</button>}
          </span>
        )}
      </div>
      {children}
      {hint && <p className="field__hint">{hint}</p>}
    </div>
  )
}

/* ============================================================
   Status-LED
   ============================================================ */

/* Die API kennt technische Zustaende, die Oberflaeche zeigt Worte. Beide
   Vokabulare an einer Stelle zusammenzufuehren verhindert, dass irgendwo
   "RUNNING" statt "läuft" auftaucht. */
const STATUS_TEXT: Record<string, string> = {
  running: 'läuft',
  starting: 'startet',
  paused: 'pausiert',
  stopped: 'gestoppt',
  failed: 'fehlgeschlagen',
  live: 'läuft',
  fail: 'fehlgeschlagen',
}

const STATUS_CLASS: Record<string, string> = {
  running: 'led--live',
  starting: 'led--paused',
  paused: 'led--paused',
  stopped: 'led--stop',
  failed: 'led--fail',
  live: 'led--live',
  fail: 'led--fail',
}

/** Zustandsklasse fuer die farbige Kante einer Karte. */
export function stateClass(status: string): string {
  return {
    running: 'live', starting: 'paused', paused: 'paused',
    stopped: 'stopped', failed: 'fail',
  }[status] ?? 'stopped'
}

export function Led({ status }: { status: string }) {
  return (
    <span className={`led ${STATUS_CLASS[status] ?? 'led--stop'}`}>
      <span className="led__dot" aria-hidden="true" />
      <span className="led__text">{t(STATUS_TEXT[status] ?? status)}</span>
    </span>
  )
}

/* ============================================================
   Drawer
   ============================================================ */

export function Drawer({ title, subtitle, tabs, tabLabel, tab, onTab, onClose, footer, children }: {
  title: string
  subtitle?: string
  tabs?: string[]
  /** Übersetzt die Reiterbeschriftung. Die Werte selbst bleiben unverändert,
      damit der Vergleich mit `tab` sprachunabhängig bleibt. */
  tabLabel?: (s: string) => string
  tab?: string
  onTab?: (t: string) => void
  onClose: () => void
  footer?: React.ReactNode
  children: React.ReactNode
}) {
  useEffect(() => {
    const esc = (e: KeyboardEvent) => { if (e.key === 'Escape') onClose() }
    document.addEventListener('keydown', esc)
    return () => document.removeEventListener('keydown', esc)
  }, [onClose])

  return (
    <>
      <div className="scrim" onClick={onClose} />
      <aside className="drawer" role="dialog" aria-modal="true" aria-label={title}>
        <header className="drawer__head">
          <div>
            <h2 className="h-card">{title}</h2>
            {subtitle && <p className="sub" style={{ marginTop: 4 }}>{subtitle}</p>}
          </div>
          <button type="button" className="btn btn--icon btn--ghost" onClick={onClose} aria-label={t('Schliessen')}>✕</button>
        </header>

        {tabs && tab && onTab && (
          <nav className="drawer__tabs">
            {tabs.map((t) => (
              <button key={t} type="button" className={`drawer__tab${t === tab ? ' is-on' : ''}`} onClick={() => onTab(t)}>{tabLabel ? tabLabel(t) : t}</button>
            ))}
          </nav>
        )}

        <div className="drawer__body">{children}</div>
        {footer && <footer className="drawer__foot">{footer}</footer>}
      </aside>
    </>
  )
}
