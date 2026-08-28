import { useEffect, useState } from 'react'
import { ChipSelect, Drawer, Field, Led, Toggle } from '../components/controls'
import {
  ApiError, api,
  type Group, type Permission, type User,
} from '../lib/api'
import { ago } from '../lib/format'
import { t as tr, useLang } from '../lib/i18n'

type Tab = 'Nutzer' | 'Gruppen'

/** Nutzer anlegen und ändern. */
function UserEditor({ user, groups, onSaved, onClose, onToast }: {
  user: User | null
  groups: Group[]
  onSaved: () => void
  onClose: () => void
  onToast: (m: string, tone?: 'ok' | 'bad') => void
}) {
  const isNew = user === null
  const [username, setUsername] = useState(user?.username ?? '')
  const [displayName, setDisplayName] = useState(user?.display_name ?? '')
  const [email, setEmail] = useState(user?.email ?? '')
  const [password, setPassword] = useState('')
  const [isActive, setIsActive] = useState(user?.is_active ?? true)
  const [groupIds, setGroupIds] = useState<string[]>(user?.group_ids ?? [])
  const [busy, setBusy] = useState(false)

  const bySlug = Object.fromEntries(groups.map((g) => [g.name, g.id]))
  const selected = groupIds.map((id) => groups.find((g) => g.id === id)?.name ?? '').filter(Boolean)

  async function save() {
    // Die eigentliche Prüfung macht die API — hier steht sie nur, damit der
    // Hinweis am Feld erscheint und nicht als Fehlermeldung von weit her.
    if (!email.trim()) {
      onToast(tr('Ohne E-Mail kommt dieses Konto in keine angebundene Anwendung.'), 'bad')
      return
    }
    setBusy(true)
    try {
      const body = {
        username,
        display_name: displayName || null,
        email: email.trim(),
        password: password || null,
        is_active: isActive,
        group_ids: groupIds,
      }
      if (isNew) await api.createUser(body)
      else await api.updateUser(user.id, body)
      onToast(isNew ? `${username} angelegt` : `${username} gespeichert`)
      onSaved()
    } catch (err) {
      onToast(err instanceof ApiError ? err.message : tr('Speichern fehlgeschlagen'), 'bad')
    } finally {
      setBusy(false)
    }
  }

  async function resetTotp() {
    if (!user) return
    setBusy(true)
    try {
      const res = await api.resetTotp(user.id)
      onToast(res.status)
    } catch (err) {
      onToast(err instanceof ApiError ? err.message : tr('Abnehmen fehlgeschlagen'), 'bad')
    } finally {
      setBusy(false)
    }
  }

  async function remove() {
    if (!user) return
    setBusy(true)
    try {
      const res = await api.deleteUser(user.id)
      onToast(res.status)
      onSaved()
    } catch (err) {
      onToast(err instanceof ApiError ? err.message : tr('Löschen fehlgeschlagen'), 'bad')
    } finally {
      setBusy(false)
    }
  }

  return (
    <Drawer
      title={isNew ? tr('Nutzer anlegen') : username}
      subtitle={isNew ? undefined
        : user?.auth_provider === 'local' ? tr('Lokales Konto') : user?.auth_provider}
      onClose={onClose}
      footer={
        <>
          {!isNew && (
            <button className="btn btn--halt" style={{ marginRight: 'auto' }}
              disabled={busy} onClick={() => void remove()}>{tr('Löschen')}</button>
          )}
          <button className="btn btn--ghost" onClick={onClose}>{tr('Verwerfen')}</button>
          <button className="btn btn--primary" disabled={busy || !username} onClick={() => void save()}>
            {busy ? tr('Wird gespeichert…') : isNew ? tr('Nutzer anlegen') : tr('Speichern')}
          </button>
        </>
      }
    >
      <Field label={tr('Benutzername')}
        hint={isNew ? tr('Wird für die Anmeldung verwendet und lässt sich später nicht ändern.') : undefined}>
        <div className="row-item">
          <input value={username} disabled={!isNew} aria-label={tr('Benutzername')}
            onChange={(e) => setUsername(e.target.value)} />
        </div>
      </Field>

      <Field label={tr('Anzeigename')}>
        <div className="row-item">
          <input value={displayName} aria-label={tr('Anzeigename')}
            onChange={(e) => setDisplayName(e.target.value)} />
        </div>
      </Field>

      <Field label={tr('E-Mail')}
        hint={tr('Pflicht. Angebundene Anwendungen erkennen Menschen daran wieder — ohne Adresse kommt niemand dort hinein.')}>
        <div className="row-item">
          <input value={email} type="email" required aria-label={tr('E-Mail')}
            placeholder="vorname.nachname@firma.de"
            onChange={(e) => setEmail(e.target.value)} />
        </div>
      </Field>

      <Field label={isNew ? tr('Startpasswort') : tr('Neues Passwort')}
        hint={tr('Mindestens 12 Zeichen. Der Nutzer muss es bei der ersten Anmeldung wechseln.')}>
        <div className="row-item">
          <input value={password} type="text" autoComplete="new-password"
            placeholder={isNew ? '' : tr('leer lassen, um es nicht zu ändern')}
            aria-label={tr('Passwort')}
            onChange={(e) => setPassword(e.target.value)} />
        </div>
      </Field>

      <Field label={tr('Gruppen')} hint={tr('Bestimmt, welche Workspaces der Nutzer sieht und was er darf.')}>
        <ChipSelect label={tr('Gruppen')} selected={selected} options={groups.map((g) => g.name)}
          onChange={(names) => setGroupIds(names.map((n) => bySlug[n]).filter(Boolean))} />
      </Field>

      <Field label={tr('Konto')}>
        <Toggle on={isActive} name={tr('Konto ist aktiv')}
          note={isActive ? tr('Der Nutzer kann sich anmelden.')
                         : tr('Anmeldung gesperrt, Daten bleiben erhalten.')}
          onChange={setIsActive} />
      </Field>

      {!isNew && (
        <Field label={tr('Zweiter Faktor')}
          hint={tr('Für den Fall, dass Telefon und Rückfallcodes verloren sind. Ohne diesen Weg käme der Mensch nie wieder herein. Alle Sitzungen des Kontos werden dabei beendet, und es steht mit deinem Namen im Protokoll.')}>
          <button className="btn btn--sm" disabled={busy}
            onClick={() => void resetTotp()}>
            {tr('Zweiten Faktor abnehmen')}
          </button>
        </Field>
      )}
    </Drawer>
  )
}

/** Gruppen anlegen und ändern. */
function GroupEditor({ group, permissions, onSaved, onClose, onToast }: {
  group: Group | null
  permissions: Permission[]
  onSaved: () => void
  onClose: () => void
  onToast: (m: string, tone?: 'ok' | 'bad') => void
}) {
  const isNew = group === null
  const [name, setName] = useState(group?.name ?? '')
  const [priority, setPriority] = useState(group?.priority ?? 100)
  const [perms, setPerms] = useState<string[]>(group?.permissions ?? [])
  const [requireTotp, setRequireTotp] = useState(group?.require_totp ?? false)
  const [busy, setBusy] = useState(false)

  const byText = Object.fromEntries(permissions.map((p) => [p.text, p.key]))
  const selected = perms.map((k) => permissions.find((p) => p.key === k)?.text ?? '').filter(Boolean)

  async function save() {
    setBusy(true)
    try {
      const body = {
        name, description: null, priority, permissions: perms,
        require_totp: requireTotp,
      }
      if (isNew) await api.createGroup(body)
      else await api.updateGroup(group.id, body)
      onToast(isNew ? `${name} angelegt` : `${name} gespeichert`)
      onSaved()
    } catch (err) {
      onToast(err instanceof ApiError ? err.message : tr('Speichern fehlgeschlagen'), 'bad')
    } finally {
      setBusy(false)
    }
  }

  async function remove() {
    if (!group) return
    setBusy(true)
    try {
      const res = await api.deleteGroup(group.id)
      onToast(res.status)
      onSaved()
    } catch (err) {
      onToast(err instanceof ApiError ? err.message : tr('Löschen fehlgeschlagen'), 'bad')
    } finally {
      setBusy(false)
    }
  }

  return (
    <Drawer
      title={isNew ? tr('Gruppe anlegen') : name}
      subtitle={group?.is_system
        ? tr('Systemgruppe — Name und Priorität sind festgelegt') : undefined}
      onClose={onClose}
      footer={
        <>
          {!isNew && !group.is_system && (
            <button className="btn btn--halt" style={{ marginRight: 'auto' }}
              disabled={busy} onClick={() => void remove()}>{tr('Löschen')}</button>
          )}
          <button className="btn btn--ghost" onClick={onClose}>{tr('Verwerfen')}</button>
          <button className="btn btn--primary" disabled={busy || !name} onClick={() => void save()}>
            {busy ? tr('Wird gespeichert…') : isNew ? tr('Gruppe anlegen') : tr('Speichern')}
          </button>
        </>
      }
    >
      <Field label={tr('Name')}>
        <div className="row-item">
          <input value={name} disabled={group?.is_system} aria-label={tr('Gruppenname')}
            onChange={(e) => setName(e.target.value)} />
        </div>
      </Field>

      <Field label={tr('Priorität')}
        hint={tr('Kleinere Zahl gewinnt, wenn zwei Gruppen widersprechende Ressourcen vorgeben.')}>
        <div className="row-item">
          <input type="number" min={1} max={9999} value={priority}
            disabled={group?.is_system} aria-label={tr('Priorität')}
            onChange={(e) => setPriority(Number(e.target.value))} />
        </div>
      </Field>

      <Field label={tr('Rechte')}
        hint={tr('Ohne Rechte sieht ein Mitglied nur sein eigenes Dashboard. „Vollzugriff auf alles" schliesst alle übrigen ein.')}>
        <ChipSelect label={tr('Rechte')} selected={selected} options={permissions.map((p) => p.text)}
          onChange={(texts) => setPerms(texts.map((x) => byText[x]).filter(Boolean))} />
      </Field>

      <Toggle on={requireTotp} name={tr('Zweiter Faktor ist Pflicht')}
        note={tr('Mitglieder ohne zweiten Faktor können keinen Arbeitsplatz starten, bis sie ihn unter „Mein Konto“ eingerichtet haben. Die Anmeldung selbst bleibt möglich — sonst käme niemand an die Einrichtung.')}
        ariaLabel={tr('Zweiter Faktor ist Pflicht')}
        onChange={setRequireTotp} />
    </Drawer>
  )
}

export function People({ onToast }: { onToast: (m: string, tone?: 'ok' | 'bad') => void }) {
  useLang()
  const [tab, setTab] = useState<Tab>('Nutzer')
  const [users, setUsers] = useState<User[] | null>(null)
  const [groups, setGroups] = useState<Group[]>([])
  const [permissions, setPermissions] = useState<Permission[]>([])
  const [editUser, setEditUser] = useState<User | null | undefined>()
  const [editGroup, setEditGroup] = useState<Group | null | undefined>()
  const [failed, setFailed] = useState<string | null>(null)

  async function load() {
    try {
      const [u, g, p] = await Promise.all([api.users(), api.groups(), api.permissions()])
      setUsers(u); setGroups(g); setPermissions(p); setFailed(null)
    } catch (err) {
      setFailed(err instanceof ApiError ? err.message : 'Laden fehlgeschlagen')
    }
  }
  useEffect(() => { void load() }, [])

  if (failed) {
    return (
      <div className="wrap"><div className="empty">
        <p className="empty__title">{tr('Konnte nicht geladen werden')}</p>
        <p className="empty__body">{failed}</p>
        <button className="btn" onClick={() => void load()}>Erneut versuchen</button>
      </div></div>
    )
  }
  if (!users) return <div className="wrap"><p className="sub">Wird geladen…</p></div>

  return (
    <div className="wrap">
      <header className="topbar">
        <div>
          <p className="silk" style={{ marginBottom: 6 }}>{tr('Verwaltung')}</p>
          <h1 className="h-page">{tr('Nutzer und Gruppen')}</h1>
        </div>
        <button className="btn btn--primary"
          onClick={() => (tab === 'Nutzer' ? setEditUser(null) : setEditGroup(null))}>
          {tab === 'Nutzer' ? tr('Nutzer anlegen') : tr('Gruppe anlegen')}
        </button>
      </header>

      <div className="seg" role="radiogroup" aria-label={tr('Ansicht')} style={{ marginBottom: 20 }}>
        {(['Nutzer', 'Gruppen'] as Tab[]).map((x) => (
          <button key={x} type="button" role="radio" aria-checked={tab === x}
            className={`seg__opt${tab === x ? ' is-on' : ''}`} onClick={() => setTab(x)}>
            {tr(x)} <span className="data" style={{ opacity: .6 }}>
              {x === 'Nutzer' ? users.length : groups.length}
            </span>
          </button>
        ))}
      </div>

      <div className="panel" style={{ padding: '14px 0 0' }}>
        {tab === 'Nutzer' ? (
          <table className="tbl">
            <thead>
              <tr>
                <th style={{ paddingLeft: 20 }}>{tr('Nutzer')}</th>
                <th>{tr('Gruppen')}</th>
                <th>{tr('Zuletzt angemeldet')}</th>
                <th>{tr('Status')}</th>
              </tr>
            </thead>
            <tbody>
              {users.map((u) => (
                <tr key={u.id} tabIndex={0} onClick={() => setEditUser(u)}
                  onKeyDown={(e) => { if (e.key === 'Enter') setEditUser(u) }}>
                  <td style={{ paddingLeft: 20 }}>
                    <div style={{ fontWeight: 500 }}>{u.username}</div>
                    {u.display_name && u.display_name !== u.username && (
                      <div style={{ fontSize: 12, color: 'var(--mute)' }}>{u.display_name}</div>
                    )}
                  </td>
                  <td style={{ color: 'var(--label)' }}>
                    {u.group_ids.map((g) => groups.find((x) => x.id === g)?.name)
                      .filter(Boolean).join(', ') || '—'}
                  </td>
                  <td className="data" style={{ color: 'var(--mute)', fontSize: 12 }}>
                    {u.last_login_at ? ago(new Date(u.last_login_at).getTime()) : tr('noch nie')}
                  </td>
                  <td><Led status={u.is_active ? 'running' : 'stopped'} /></td>
                </tr>
              ))}
            </tbody>
          </table>
        ) : (
          <table className="tbl">
            <thead>
              <tr>
                <th style={{ paddingLeft: 20 }}>{tr('Gruppe')}</th>
                <th>{tr('Priorität')}</th>
                <th>{tr('Rechte')}</th>
                <th>{tr('Mitglieder')}</th>
              </tr>
            </thead>
            <tbody>
              {groups.map((g) => (
                <tr key={g.id} tabIndex={0} onClick={() => setEditGroup(g)}
                  onKeyDown={(e) => { if (e.key === 'Enter') setEditGroup(g) }}>
                  <td style={{ paddingLeft: 20 }}>
                    <div style={{ fontWeight: 500 }}>{g.name}</div>
                    {g.is_system && <div className="silk" style={{ marginTop: 2 }}>{tr('Systemgruppe')}</div>}
                  </td>
                  <td className="data" style={{ color: 'var(--label)' }}>{g.priority}</td>
                  <td style={{ color: 'var(--label)', fontSize: 12.5 }}>
                    {g.permissions.length
                      ? g.permissions.map((k) => permissions.find((p) => p.key === k)?.text ?? k).join(', ')
                      : tr('nur eigenes Dashboard')}
                  </td>
                  <td className="data" style={{ color: 'var(--label)' }}>{g.member_count}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>

      {editUser !== undefined && (
        <UserEditor user={editUser} groups={groups} onToast={onToast}
          onClose={() => setEditUser(undefined)}
          onSaved={() => { setEditUser(undefined); void load() }} />
      )}
      {editGroup !== undefined && (
        <GroupEditor group={editGroup} permissions={permissions} onToast={onToast}
          onClose={() => setEditGroup(undefined)}
          onSaved={() => { setEditGroup(undefined); void load() }} />
      )}
    </div>
  )
}
