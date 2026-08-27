/** Typisierter Zugriff auf die OTA-API. */

export type Me = {
  id: string
  username: string
  display_name: string | null
  is_admin: boolean
  permissions: string[]
  groups: string[]
  locale: string
  must_change_password: boolean
}

export type App = {
  slug: string
  name: string
  icon: string
  registry_hint: string | null
  blocked_reason: string | null
  is_enabled: boolean
}

export type Template = {
  id: string
  slug: string
  friendly_name: string
  description: string
  icon: string
  categories: string[]
  mode: 'workspace' | 'single_app'
  image_ref: string
  cores: number
  memory_bytes: number
  x_res: number
  y_res: number
  idle_minutes: number
  idle_action: 'pause' | 'stop' | 'delete'
  persistence_scope: 'user' | 'template' | 'none'
  rights: Record<string, boolean>
  env: Record<string, string>
  is_enabled: boolean
  apps: App[]
  group_ids: string[]
  effective_cores: number | null
  effective_memory_bytes: number | null
}

export type Stream = {
  app_slug: string
  display_num: number
  status: string
  url: string
}

export type Session = {
  id: string
  template_id: string
  template_name: string
  template_icon: string
  template_mode: string
  username: string
  status: 'starting' | 'running' | 'paused' | 'stopped' | 'failed'
  cores: number
  memory_bytes: number
  started_at: string
  last_seen_at: string
  error: string | null
  url: string
  streams: Stream[]
}

export type Group = {
  id: string
  name: string
  slug: string
  priority: number
  permissions: string[]
  member_count: number
  is_system: boolean
}

export type User = {
  id: string
  username: string
  display_name: string | null
  email: string | null
  is_active: boolean
  is_locked: boolean
  auth_provider: string
  last_login_at: string | null
  group_ids: string[]
}

export type Permission = { key: string; text: string }

export type AdminSession = {
  id: string
  username: string
  template_name: string
  template_icon: string
  status: string
  cores: number
  memory_bytes: number
  started_at: string
  last_seen_at: string
  app_count: number
}

export type AuditEntry = {
  ts: string
  actor: string | null
  action: string
  object_type: string | null
  object_id: string | null
  ip: string | null
  detail: Record<string, unknown>
}

export type Backup = {
  id: string
  kind: 'profile' | 'container' | 'database'
  username: string | null
  template_slug: string | null
  path: string | null
  size_bytes: number
  file_count: number
  status: 'running' | 'ok' | 'failed'
  error: string | null
  log: string
  trigger: 'manual' | 'schedule' | 'pre_restore'
  actor: string | null
  started_at: string
  finished_at: string | null
}

export type BackupPolicy = {
  is_enabled: boolean
  hour: number
  minute: number
  weekdays: number[]
  include_profiles: boolean
  include_containers: boolean
  include_database: boolean
  keep_daily: number
  keep_weekly: number
  last_run_at?: string | null
  last_result?: string | null
}

export type BackupStorage = {
  path: string
  writable: boolean
  is_network: boolean
  fstype: string
  source: string
  disk_total: number
  disk_free: number
  used_by_backups: number
}

export type Host = {
  cores: number
  memory_total: number
  memory_available: number
  disk_total: number
  disk_free: number
  docker_version: string
  architecture: string
  running_containers: number
}

export type Allocation = {
  user_id: string
  username: string
  cores: number
  memory_bytes: number
  cores_from: string
  memory_from: string
  has_own_override: boolean
}

/** Fehler mit der Meldung, die die API geliefert hat — nicht "Fehler 500". */
export class ApiError extends Error {
  constructor(public status: number, message: string) {
    super(message)
    this.name = 'ApiError'
  }
}

async function call<T>(path: string, init: RequestInit = {}): Promise<T> {
  let res: Response
  try {
    res = await fetch(`/api${path}`, {
      credentials: 'same-origin',
      headers: init.body ? { 'Content-Type': 'application/json' } : undefined,
      ...init,
    })
  } catch {
    throw new ApiError(0, 'Keine Verbindung zum Server. Läuft OTA noch?')
  }

  if (res.status === 204) return undefined as T

  const text = await res.text()
  let data: unknown = null
  try { data = text ? JSON.parse(text) : null } catch { /* kein JSON */ }

  if (!res.ok) {
    const detail =
      (data && typeof data === 'object' && 'detail' in data && typeof data.detail === 'string')
        ? data.detail
        : `Unerwarteter Fehler (${res.status})`
    throw new ApiError(res.status, detail)
  }
  return data as T
}

export const api = {
  login: (username: string, password: string, totp?: string) =>
    call<Me>('/auth/login', { method: 'POST', body: JSON.stringify({ username, password, totp }) }),
  logout: () => call<void>('/auth/logout', { method: 'POST' }),
  me: () => call<Me>('/auth/me'),
  changePassword: (current_password: string, new_password: string) =>
    call<{ status: string }>('/auth/password', {
      method: 'POST', body: JSON.stringify({ current_password, new_password }),
    }),

  templates: () => call<Template[]>('/templates'),
  createTemplate: (body: unknown) =>
    call<Template>('/templates', { method: 'POST', body: JSON.stringify(body) }),
  updateTemplate: (id: string, body: unknown) =>
    call<Template>(`/templates/${id}`, { method: 'PUT', body: JSON.stringify(body) }),
  deleteTemplate: (id: string) =>
    call<{ status: string }>(`/templates/${id}`, { method: 'DELETE' }),
  allocations: (id: string) => call<Allocation[]>(`/templates/${id}/allocations`),
  setOverride: (id: string, body: unknown) =>
    call<{ status: string }>(`/templates/${id}/overrides`, {
      method: 'PUT', body: JSON.stringify(body),
    }),

  sessions: (allUsers = false) =>
    call<Session[]>(`/sessions${allUsers ? '?all_users=true' : ''}`),
  startSession: (template_id: string) =>
    call<Session>('/sessions', { method: 'POST', body: JSON.stringify({ template_id }) }),
  sessionAction: (id: string, action: 'pause' | 'unpause' | 'stop') =>
    call<Session>(`/sessions/${id}/${action}`, { method: 'POST' }),
  deleteSession: (id: string) =>
    call<{ status: string }>(`/sessions/${id}`, { method: 'DELETE' }),
  heartbeat: (id: string) =>
    call<{ status: string }>(`/sessions/${id}/heartbeat`, { method: 'POST' }),
  startApp: (id: string, slug: string) =>
    call<Session>(`/sessions/${id}/apps/${slug}`, { method: 'POST' }),
  stopApp: (id: string, slug: string) =>
    call<Session>(`/sessions/${id}/apps/${slug}`, { method: 'DELETE' }),
  setApps: (templateId: string, apps: unknown[]) =>
    call<Template>(`/templates/${templateId}/apps`, {
      method: 'PUT', body: JSON.stringify(apps),
    }),

  host: () => call<Host>('/admin/host'),
  images: () => call<{ ref: string; size_bytes: number }[]>('/admin/images'),
  users: () => call<User[]>('/admin/users'),
  groups: () => call<Group[]>('/admin/groups'),
  audit: (limit = 100) => call<AuditEntry[]>(`/admin/audit?limit=${limit}`),
  permissions: () => call<Permission[]>('/admin/permissions'),
  adminSessions: () => call<AdminSession[]>('/admin/sessions'),

  backups: () => call<Backup[]>('/backups'),
  backupStorage: () => call<BackupStorage>('/backups/storage'),
  backupPolicy: () => call<BackupPolicy>('/backups/policy'),
  saveBackupPolicy: (body: BackupPolicy) =>
    call<BackupPolicy>('/backups/policy', { method: 'PUT', body: JSON.stringify(body) }),
  runBackup: (body: { username?: string | null; include_container?: boolean }) =>
    call<{ status: string }>('/backups/run', { method: 'POST', body: JSON.stringify(body) }),
  restoreBackup: (id: string) =>
    call<{ status: string }>(`/backups/${id}/restore`, { method: 'POST' }),
  deleteBackup: (id: string) =>
    call<{ status: string }>(`/backups/${id}`, { method: 'DELETE' }),
  createUser: (body: unknown) =>
    call<User>('/admin/users', { method: 'POST', body: JSON.stringify(body) }),
  updateUser: (id: string, body: unknown) =>
    call<User>(`/admin/users/${id}`, { method: 'PUT', body: JSON.stringify(body) }),
  deleteUser: (id: string) =>
    call<{ status: string }>(`/admin/users/${id}`, { method: 'DELETE' }),
  createGroup: (body: unknown) =>
    call<Group>('/admin/groups', { method: 'POST', body: JSON.stringify(body) }),
  updateGroup: (id: string, body: unknown) =>
    call<Group>(`/admin/groups/${id}`, { method: 'PUT', body: JSON.stringify(body) }),
  deleteGroup: (id: string) =>
    call<{ status: string }>(`/admin/groups/${id}`, { method: 'DELETE' }),
}
