/** Typisierter Zugriff auf die OTA-API. */

import { t } from './i18n'

export type Me = {
  id: string
  username: string
  display_name: string | null
  is_admin: boolean
  permissions: string[]
  groups: string[]
  locale: string
  must_change_password: boolean
  /** Ist der zweite Faktor eingerichtet? Das Geheimnis selbst kommt nie hierher. */
  totp_enabled: boolean
  recovery_left: number
  /** Eine Gruppe verlangt den zweiten Faktor, er ist aber nicht eingerichtet. */
  must_setup_totp: boolean
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
  /** Läuft bei jedem Sessionstart als Nutzer im Container. */
  start_script: string
  /** Pfade im Skeleton, die bei jedem Start überschreiben. */
  skeleton_enforce: string[]
  user_shelf: boolean
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

export type MyStorage = {
  bytes: number
  quota_bytes: number
  /** null, wenn kein Kontingent gesetzt ist. */
  percent: number | null
  level: 'in Ordnung' | 'knapp' | 'voll' | 'ohne Grenze' | 'unbekannt'
}

export type Group = {
  id: string
  name: string
  slug: string
  priority: number
  permissions: string[]
  member_count: number
  is_system: boolean
  /** Mitglieder ohne zweiten Faktor können keinen Arbeitsplatz starten. */
  require_totp: boolean
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

export type GlobalSettings = {
  auth_idle_minutes: number
  auth_idle_steps: number[]
  /** 0 heisst jeweils: keine Grenze. */
  profile_quota_gb: number
  disk_floor_gb: number
}

/** Ein Programm, wie es im Image gefunden wurde. */
export type DiscoveredApp = {
  slug: string
  name: string
  icon: string
  exec_cmd: string
  exec_args: string
  categories: string[]
  /** Braucht ein Terminal um sich herum — startet sonst auf leerem Bildschirm. */
  needs_terminal: boolean
  binary: string
  /** Steht schon im Katalog dieses Workspace? */
  in_catalog: boolean
  is_enabled: boolean
  fixed_display: number | null
  /** Leer heisst: für alle sichtbar, die den Arbeitsplatz sehen. */
  group_ids: string[]
  /** null heisst: die Auflösung des Arbeitsplatzes. */
  x_res: number | null
  y_res: number | null
  /** Im Katalog, aber im Image nicht mehr vorhanden. */
  missing: boolean
}

/** Was das Image über einen Paketnamen weiss. */
export type Registry = {
  id: string
  name: string
  url: string
  schema_version: string
  icon_url: string | null
  is_enabled: boolean
  auto_update: boolean
  last_fetched_at: string | null
  workspace_count: number
  fetch_error: string | null
  entry_count: number
  imported_count: number
}

export type RegistryEntry = {
  sha: string
  friendly_name: string
  description: string
  categories: string[]
  architectures: string[]
  icon_url: string | null
  image_ref: string
  available_tags: string[]
  uncompressed_size_mb: number
  /** Gesetzt, sobald daraus eine Vorlage entstanden ist. */
  imported_template_id: string | null
}

export type TotpSetup = { secret: string; uri: string; qr_svg: string }

export type RecipeKind = 'apt_repo' | 'deb_url' | 'tarball' | 'appimage' | 'script'

export type Recipe = {
  id: string
  slug: string
  name: string
  glyph: string
  why: string
  kind: RecipeKind
  params: Record<string, unknown>
  script: string
  /** Mitgeliefert: nicht änderbar, aber kopierbar. */
  is_builtin: boolean
  created_by: string | null
}

export type SharedEntry = {
  name: string
  is_dir: boolean
  size_bytes: number
  /** Unix-Zeit in Sekunden. */
  modified: number
}

/** Ein Skript, das je Nutzer genau einmal läuft. */
export type OnceScript = {
  id: string
  name: string
  body: string
  is_enabled: boolean
  sort_order: number
  created_at: string
  ran_count: number
  failed: { username: string; ran_at: string; exit_code: number; output: string }[]
}

export type OnceScriptIn = {
  name: string
  body: string
  is_enabled: boolean
  sort_order: number
}

/** Zustand des Identity Providers (auth-roadmap.md, Etappe A). */
export type KeycloakStatus = {
  betriebsart: string
  adresse: string
  realm: string
  erreichbar: boolean
  fehler: string | null
  version: string | null
  faehigkeiten: Record<string, boolean>
}

/** Die Verzeichnisanbindung, wie Keycloak sie führt. */
export type KcVerzeichnis = {
  eingerichtet: boolean
  server_uri?: string
  base_dn?: string
  bind_dn?: string
  user_filter?: string
  login_attribute?: string
  kind?: string
  hat_kennwort?: boolean
  is_enabled?: boolean
}

export type KcVerzeichnisIn = {
  server_uri: string
  base_dn: string
  bind_dn: string
  bind_password: string
  user_filter: string
  login_attribute: string
  kind: string
  is_enabled: boolean
}

/** Eine fremde Web-Anwendung im Katalog. */
export type WebApp = {
  id: string
  slug: string
  name: string
  description: string
  icon: string
  url: string
  redirect_uri: string
  client_id: string
  is_enabled: boolean
  sort_order: number
  group_ids: string[]
  /** Nur beim Anlegen gefüllt — danach steht es allein in Keycloak. */
  client_secret: string | null
}

export type WebAppIn = {
  name: string
  slug?: string
  description: string
  icon: string
  url: string
  redirect_uri: string
  is_enabled: boolean
  sort_order: number
  group_ids?: string[] | null
}

export type SharedListing = {
  path: string
  entries: SharedEntry[]
  total_bytes: number
}

export type HostImage = {
  ref: string
  size_bytes: number
  /** 'ota' = selbst gebaut, 'kasm' = gehört dem anderen System, 'fremd' = sonst. */
  origin: 'ota' | 'kasm' | 'fremd'
  used_by: string[]
}

export type PullJob = {
  id: string
  ref: string
  status: 'running' | 'ok' | 'failed'
  detail: string
  size_bytes: number
}

export type PackageCheck = {
  name: string
  available: boolean
  candidate: string
  /** Vorhanden, aber nur als Verweis auf ein Snap — im Container nutzlos. */
  snap_stub: boolean
  suggestions: string[]
}

export type Build = {
  id: string
  version: number
  base_image: string
  apt_packages: string[]
  vscode_extensions: string[]
  setup_script: string
  comment: string
  status: 'queued' | 'building' | 'ok' | 'failed'
  log: string
  image_ref: string | null
  size_bytes: number
  is_current: boolean
  built_by: string | null
  started_at: string
  finished_at: string | null
}

export type FreezePreview = {
  aenderungen: { art: string; pfad: string; geheimnis: boolean }[]
  gesamt: number
  gekuerzt: boolean
  uebersprungen: number
  geheimnisse: string[]
  /** Wird vor dem Einfrieren aus dem Container entfernt. */
  entfernt: string[]
  session_id: string
}

export type IdentityConfig = {
  is_enabled: boolean
  server_uri: string
  tls_mode: 'starttls' | 'none'
  tls_verify: boolean
  ca_cert: string
  bind_dn: string
  /** Das Kennwort selbst kommt nie zurück — nur, ob eines hinterlegt ist. */
  has_bind_password: boolean
  base_dn: string
  login_attribute: string
  user_filter: string
  mail_attribute: string
  name_attribute: string
  group_base_dn: string
  group_filter: string
  member_attribute: string
  group_name_attribute: string
  /** Gruppenname im Verzeichnis → Gruppen-Kennung in OTA. */
  group_map: Record<string, string>
  jit_create: boolean
  sync_enabled: boolean
  last_sync_at: string | null
  last_error: string | null
}

export type SkeletonEntry = {
  name: string
  pfad: string
  verzeichnis: boolean
  bytes: number
}

export type HelpChapter = { slug: string; title: string; section: string }
export type HelpPage = { slug: string; title: string; markdown: string }

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

/* Meldungen des Servers laufen durch dieselbe Übersetzung wie die Oberfläche.
   Das geht auf, weil der deutsche Satz der Schlüssel ist: Was im Wörterbuch
   steht, erscheint übersetzt; alles andere bleibt, wie der Server es sagt. */
async function call<T>(path: string, init: RequestInit = {}): Promise<T> {
  let res: Response
  try {
    res = await fetch(`/api${path}`, {
      credentials: 'same-origin',
      // Bei FormData setzt der Browser den Content-Type samt Grenzmarke
      // selbst. Einen eigenen zu setzen macht die Übertragung unbrauchbar.
      headers: init.body && !(init.body instanceof FormData)
        ? { 'Content-Type': 'application/json' } : undefined,
      ...init,
    })
  } catch {
    throw new ApiError(0, t('Keine Verbindung zum Server. Läuft OTA noch?'))
  }

  if (res.status === 204) return undefined as T

  const text = await res.text()
  let data: unknown = null
  try { data = text ? JSON.parse(text) : null } catch { /* kein JSON */ }

  if (!res.ok) {
    const detail =
      (data && typeof data === 'object' && 'detail' in data && typeof data.detail === 'string')
        ? data.detail
        : t('Unerwarteter Fehler ({code})', { code: res.status })
    throw new ApiError(res.status, t(detail))
  }
  return data as T
}

export const api = {
  login: (username: string, password: string, totp?: string) =>
    call<Me>('/auth/login', { method: 'POST', body: JSON.stringify({ username, password, totp }) }),
  logout: () => call<void>('/auth/logout', { method: 'POST' }),
  me: () => call<Me>('/auth/me'),
  setLocale: (locale: string) =>
    call<Me>('/auth/locale', { method: 'PUT', body: JSON.stringify({ locale }) }),
  totpSetup: () => call<TotpSetup>('/auth/totp/setup', { method: 'POST' }),
  totpActivate: (secret: string, code: string) =>
    call<{ codes: string[] }>('/auth/totp/activate', {
      method: 'POST', body: JSON.stringify({ secret, code }),
    }),
  totpRenewCodes: (password: string) =>
    call<{ codes: string[] }>('/auth/totp/recovery', {
      method: 'POST', body: JSON.stringify({ password }),
    }),
  totpDisable: (password: string, code: string) =>
    call<{ status: string }>('/auth/totp', {
      method: 'DELETE', body: JSON.stringify({ password, code }),
    }),
  changePassword: (current_password: string, new_password: string) =>
    call<{ status: string }>('/auth/password', {
      method: 'POST', body: JSON.stringify({ current_password, new_password }),
    }),

  templates: () => call<Template[]>('/templates'),

  help: () => call<HelpChapter[]>('/help'),
  helpPage: (slug: string) => call<HelpPage>(`/help/${slug}`),
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
  onceScripts: (templateId: string) =>
    call<OnceScript[]>(`/templates/${templateId}/once`),
  addOnceScript: (templateId: string, body: OnceScriptIn) =>
    call<OnceScript>(`/templates/${templateId}/once`, {
      method: 'POST', body: JSON.stringify(body),
    }),
  saveOnceScript: (templateId: string, id: string, body: OnceScriptIn) =>
    call<OnceScript>(`/templates/${templateId}/once/${id}`, {
      method: 'PUT', body: JSON.stringify(body),
    }),
  removeOnceScript: (templateId: string, id: string) =>
    call<{ status: string }>(`/templates/${templateId}/once/${id}`, { method: 'DELETE' }),
  runOnceAgain: (templateId: string, id: string, nurGescheiterte = false) =>
    call<{ status: string; count: number }>(
      `/templates/${templateId}/once/${id}/again?nur_gescheiterte=${nurGescheiterte}`,
      { method: 'POST' }),

  discoverApps: (templateId: string) =>
    call<DiscoveredApp[]>(`/templates/${templateId}/apps/discover`),

  sharedList: (path = '') =>
    call<SharedListing>(`/shared?path=${encodeURIComponent(path)}`),
  sharedUpload: (path: string, file: File) => {
    // FormData statt JSON: Der Browser setzt die Grenze zwischen den Teilen
    // selbst. Ein eigener Content-Type hier würde sie überschreiben und die
    // Datei unbrauchbar machen — deshalb wird er bewusst nicht gesetzt.
    const body = new FormData()
    body.append('file', file)
    return call<{ name: string; size_bytes: number }>(
      `/shared/upload?path=${encodeURIComponent(path)}`, { method: 'POST', body })
  },
  sharedMkdir: (path: string, name: string) =>
    call<{ name: string }>('/shared/dir', {
      method: 'POST', body: JSON.stringify({ path, name }),
    }),
  sharedRemove: (path: string) =>
    call<{ status: string }>(`/shared?path=${encodeURIComponent(path)}`, { method: 'DELETE' }),

  // Die eigene Ablage. Derselbe Schnitt, ein anderer Ort — und ohne
  // Empfänger: Wem sie gehört, steht im Cookie und nicht in der Adresse.
  filesList: (path = '') =>
    call<SharedListing>(`/files?path=${encodeURIComponent(path)}`),
  filesUpload: (path: string, file: File) => {
    const body = new FormData()
    body.append('file', file)
    return call<{ name: string; size_bytes: number }>(
      `/files/upload?path=${encodeURIComponent(path)}`, { method: 'POST', body })
  },
  filesMkdir: (path: string, name: string) =>
    call<{ name: string }>('/files/dir', {
      method: 'POST', body: JSON.stringify({ path, name }),
    }),
  filesRemove: (path: string) =>
    call<{ status: string }>(`/files?path=${encodeURIComponent(path)}`, { method: 'DELETE' }),

  webApps: () => call<WebApp[]>('/webapps'),
  addWebApp: (b: WebAppIn) =>
    call<WebApp>('/webapps', { method: 'POST', body: JSON.stringify(b) }),
  saveWebApp: (id: string, b: WebAppIn) =>
    call<WebApp>(`/webapps/${id}`, { method: 'PUT', body: JSON.stringify(b) }),
  removeWebApp: (id: string) =>
    call<{ status: string }>(`/webapps/${id}`, { method: 'DELETE' }),
  newWebAppSecret: (id: string) =>
    call<{ client_secret: string }>(`/webapps/${id}/geheimnis`, { method: 'POST' }),

  keycloakStatus: () => call<KeycloakStatus>('/admin/identity/keycloak'),
  kcVerzeichnis: () => call<KcVerzeichnis>('/admin/identity/keycloak/verzeichnis'),
  kcVerzeichnisSetzen: (b: KcVerzeichnisIn) =>
    call<KcVerzeichnis>('/admin/identity/keycloak/verzeichnis', {
      method: 'PUT', body: JSON.stringify(b),
    }),
  kcVerzeichnisTest: (b: KcVerzeichnisIn) =>
    call<{ verbindung: boolean; anmeldung: boolean; hinweise: string[] }>(
      '/admin/identity/keycloak/verzeichnis/test', { method: 'POST', body: JSON.stringify(b) }),
  kcVerzeichnisWeg: () =>
    call<KcVerzeichnis>('/admin/identity/keycloak/verzeichnis', { method: 'DELETE' }),
  kcVerzeichnisAbgleich: (voll = false) =>
    call<{ added?: number; updated?: number; failed?: number; status?: string }>(
      `/admin/identity/keycloak/verzeichnis/abgleich?voll=${voll}`, { method: 'POST' }),

  registries: () => call<Registry[]>('/admin/registries'),
  suggestedRegistries: () =>
    call<{ name: string; url: string }[]>('/admin/registries/suggested'),
  addRegistry: (url: string) =>
    call<Registry>('/admin/registries', { method: 'POST', body: JSON.stringify({ url }) }),
  refreshRegistry: (id: string) =>
    call<Registry>(`/admin/registries/${id}/refresh`, { method: 'POST' }),
  removeRegistry: (id: string) =>
    call<{ status: string }>(`/admin/registries/${id}`, { method: 'DELETE' }),
  registryEntries: (id: string) =>
    call<RegistryEntry[]>(`/admin/registries/${id}/entries`),
  importRegistryEntry: (id: string, sha: string, tag?: string) =>
    call<{ template_id: string; slug: string; image_ref: string; status: string }>(
      `/admin/registries/${id}/import`,
      { method: 'POST', body: JSON.stringify({ sha, tag }) }),

  recipes: () => call<Recipe[]>('/admin/recipes'),
  previewRecipe: (kind: string, params: Record<string, unknown>) =>
    call<{ script: string }>('/admin/recipes/preview', {
      method: 'POST', body: JSON.stringify({ kind, params }),
    }),
  createRecipe: (body: unknown) =>
    call<Recipe>('/admin/recipes', { method: 'POST', body: JSON.stringify(body) }),
  updateRecipe: (id: string, body: unknown) =>
    call<Recipe>(`/admin/recipes/${id}`, { method: 'PUT', body: JSON.stringify(body) }),
  deleteRecipe: (id: string) =>
    call<{ status: string }>(`/admin/recipes/${id}`, { method: 'DELETE' }),

  checkPackages: (templateId: string, names: string[]) =>
    call<PackageCheck[]>(
      `/templates/${templateId}/packages?names=${encodeURIComponent(names.join(','))}`),

  // `app` wählt den Teilbaum einer einzelnen Anwendung. Leer heisst: das
  // Skeleton des Workspace selbst.
  skeletonList: (templateId: string, path = '', app = '') =>
    call<{ pfad: string; eintraege: SkeletonEntry[] }>(
      `/templates/${templateId}/skeleton?path=${encodeURIComponent(path)}`
      + `&app=${encodeURIComponent(app)}`),
  skeletonUpload: (templateId: string, path: string, file: File, app = '') => {
    const body = new FormData()
    body.append('file', file, file.name)
    return call<unknown>(
      `/templates/${templateId}/skeleton/upload?path=${encodeURIComponent(path)}`
      + `&app=${encodeURIComponent(app)}`,
      { method: 'POST', body })
  },
  skeletonMkdir: (templateId: string, path: string, name: string, app = '') =>
    call<unknown>(`/templates/${templateId}/skeleton/dir`, {
      method: 'POST', body: JSON.stringify({ path, name, app }),
    }),
  skeletonRemove: (templateId: string, path: string, app = '') =>
    call<{ status: string }>(
      `/templates/${templateId}/skeleton?path=${encodeURIComponent(path)}`
      + `&app=${encodeURIComponent(app)}`,
      { method: 'DELETE' }),

  builds: (templateId: string) => call<Build[]>(`/templates/${templateId}/builds`),
  freezePreview: (templateId: string) =>
    call<FreezePreview>(`/templates/${templateId}/freeze/preview`),
  freeze: (templateId: string, body: { comment?: string; trotz_geheimnissen?: boolean }) =>
    call<Build>(`/templates/${templateId}/freeze`, {
      method: 'POST', body: JSON.stringify(body),
    }),
  build: (templateId: string, id: string) =>
    call<Build>(`/templates/${templateId}/builds/${id}`),
  startBuild: (templateId: string, body: {
    apt_packages: string[]; vscode_extensions?: string[]
    setup_script?: string; comment?: string
  }) => call<Build>(`/templates/${templateId}/builds`, {
    method: 'POST', body: JSON.stringify(body),
  }),
  activateBuild: (templateId: string, id: string) =>
    call<Build>(`/templates/${templateId}/builds/${id}/activate`, { method: 'POST' }),
  deleteBuild: (templateId: string, id: string) =>
    call<{ status: string }>(`/templates/${templateId}/builds/${id}`,
      { method: 'DELETE' }),

  setApps: (templateId: string, apps: unknown[]) =>
    call<Template>(`/templates/${templateId}/apps`, {
      method: 'PUT', body: JSON.stringify(apps),
    }),

  host: () => call<Host>('/admin/host'),
  images: () => call<HostImage[]>('/admin/images'),
  pullImage: (ref: string) =>
    call<PullJob>('/admin/images/pull', { method: 'POST', body: JSON.stringify({ ref }) }),
  pullStatus: (jobId: string) => call<PullJob>(`/admin/images/pull/${jobId}`),
  removeImage: (ref: string) =>
    call<{ status: string }>(`/admin/images?ref=${encodeURIComponent(ref)}`, { method: 'DELETE' }),
  users: () => call<User[]>('/admin/users'),
  groups: () => call<Group[]>('/admin/groups'),
  audit: (limit = 100) => call<AuditEntry[]>(`/admin/audit?limit=${limit}`),
  permissions: () => call<Permission[]>('/admin/permissions'),
  identity: () => call<IdentityConfig>('/admin/identity'),
  saveIdentity: (body: unknown) =>
    call<IdentityConfig>('/admin/identity', { method: 'PUT', body: JSON.stringify(body) }),
  testIdentity: (probe: string) =>
    call<Record<string, unknown>>('/admin/identity/test', {
      method: 'POST', body: JSON.stringify({ probe_login: probe }),
    }),
  syncIdentity: () =>
    call<{ geprueft: number; geaendert: number; deaktiviert: number; fehler: number }>(
      '/admin/identity/sync', { method: 'POST' }),

  settings: () => call<GlobalSettings>('/admin/settings'),
  myStorage: () => call<MyStorage>('/auth/storage'),

  resetTotp: (userId: string) =>
    call<{ status: string }>(`/admin/users/${userId}/reset-totp`, { method: 'POST' }),

  profileUsage: (username: string) =>
    call<{ username: string; bytes: number; gemessen: string }>(
      `/admin/users/${encodeURIComponent(username)}/usage`),

  saveSettings: (body: Partial<GlobalSettings>) =>
    call<GlobalSettings>('/admin/settings', { method: 'PUT', body: JSON.stringify(body) }),
  adminSessions: () => call<AdminSession[]>('/admin/sessions'),

  backups: () => call<Backup[]>('/backups'),
  backupStorage: () => call<BackupStorage>('/backups/storage'),
  backupPolicy: () => call<BackupPolicy>('/backups/policy'),
  saveBackupPolicy: (body: BackupPolicy) =>
    call<BackupPolicy>('/backups/policy', { method: 'PUT', body: JSON.stringify(body) }),
  runBackup: (body: {
    username?: string | null
    include_container?: boolean
    database_only?: boolean
  }) => call<{ status: string }>('/backups/run', { method: 'POST', body: JSON.stringify(body) }),
  restoreIntoSession: (id: string) =>
    call<{ status: string }>(`/backups/${id}/restore-into-session`, { method: 'POST' }),
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
