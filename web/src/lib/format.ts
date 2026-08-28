export const GB = 1024 ** 3

export function gb(bytes: number, digits = 1): string {
  return (bytes / GB).toFixed(digits).replace('.', ',')
}

/**
 * Eine Grösse in der Einheit, die zu ihr passt.
 *
 * `gb()` ist richtig, wo Gigabyte die Einheit der Sache sind — Images,
 * Arbeitsspeicher, Kontingente. Für eine Konfigurationsdatei von 300 Bytes
 * ist „0,00 GB" keine Angabe, sondern eine Ausrede.
 */
export function size(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`
  if (bytes < 1024 ** 2) return `${(bytes / 1024).toFixed(0)} KB`
  if (bytes < 1024 ** 3) return `${(bytes / 1024 ** 2).toFixed(1).replace('.', ',')} MB`
  return `${gb(bytes, 2)} GB`
}

export function duration(ms: number): string {
  const min = Math.floor(ms / 60000)
  if (min < 60) return `${min} min`
  const h = Math.floor(min / 60)
  const rest = min % 60
  return rest ? `${h} h ${rest} min` : `${h} h`
}

export function ago(ts: number): string {
  const s = Math.floor((Date.now() - ts) / 1000)
  if (s < 60) return 'gerade eben'
  if (s < 3600) return `vor ${Math.floor(s / 60)} min`
  if (s < 86400) return `vor ${Math.floor(s / 3600)} h`
  return `vor ${Math.floor(s / 86400)} Tagen`
}

export function idleLabel(min: number): string {
  if (min >= 100000) return 'nie'
  if (min < 60) return `${min} min`
  const h = min / 60
  return Number.isInteger(h) ? `${h} h` : `${h.toFixed(1).replace('.', ',')} h`
}

export function cores(n: number): string {
  const v = n.toString().replace('.', ',')
  return `${v} ${n === 1 ? 'Kern' : 'Kerne'}`
}
