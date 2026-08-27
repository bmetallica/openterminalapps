/**
 * Adressen der Anwendung.
 *
 * Bis hierher lebte alles unter „/" und der Zustand nur im Speicher. Das ging,
 * solange eine Session im selben Fenster geöffnet wurde. Es geht nicht mehr,
 * sobald eine Anwendung in einem eigenen Tab läuft oder vom Desktop aus
 * gestartet wird: Beides braucht eine Adresse, die man aufschreiben kann.
 *
 * Zwei Formen, mit unterschiedlichem Zweck:
 *
 *   /view/s/<session>[/<display>]   Zeigt eine **bestimmte laufende** Session.
 *                                   Entsteht beim Öffnen aus dem Dashboard.
 *   /launch/<vorlage>[/<app>]       Sorgt dafür, dass etwas läuft, und zeigt
 *                                   es dann. Startet notfalls einen Container.
 *                                   Das ist die Adresse für Verknüpfungen auf
 *                                   dem Desktop — dort weiss niemand, welche
 *                                   Session-Nummer heute gilt.
 *
 * Wer nicht angemeldet ist, landet auf der Anmeldung und danach wieder hier:
 * Die Adresse bleibt in der Leiste stehen, es wird nichts umgeleitet.
 */

export type Route =
  | { kind: 'app' }
  | { kind: 'view'; sessionId: string; display?: number }
  | { kind: 'launch'; templateSlug: string; appSlug?: string }

const UUID = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i
const SLUG = /^[a-z0-9][a-z0-9-]{0,63}$/

export function parseRoute(path = window.location.pathname): Route {
  const parts = path.split('/').filter(Boolean)

  if (parts[0] === 'view' && parts[1] === 's' && UUID.test(parts[2] ?? '')) {
    const display = parts[3] !== undefined ? Number(parts[3]) : undefined
    return {
      kind: 'view',
      sessionId: parts[2],
      display: Number.isInteger(display) && display! > 0 ? display : undefined,
    }
  }

  if (parts[0] === 'launch' && SLUG.test(parts[1] ?? '')) {
    return {
      kind: 'launch',
      templateSlug: parts[1],
      appSlug: SLUG.test(parts[2] ?? '') ? parts[2] : undefined,
    }
  }

  return { kind: 'app' }
}

export function viewPath(sessionId: string, display?: number): string {
  return display && display > 1 ? `/view/s/${sessionId}/${display}` : `/view/s/${sessionId}`
}

export function launchPath(templateSlug: string, appSlug?: string): string {
  return appSlug ? `/launch/${templateSlug}/${appSlug}` : `/launch/${templateSlug}`
}

/** Öffnet eine Adresse in einem eigenen Tab.
 *
 * `noopener` ist hier kein Ritual: Ohne das behielte der neue Tab eine
 * Referenz auf `window.opener` — und in diesem Tab läuft eine fremde
 * Anwendung im iframe.
 */
export function openInTab(path: string): void {
  window.open(path, '_blank', 'noopener')
}
