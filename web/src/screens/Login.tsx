import { useState } from 'react'
import { ApiError, api, type Me } from '../lib/api'

export function Login({ onDone }: { onDone: (me: Me) => void }) {
  const [username, setUsername] = useState('')
  const [password, setPassword] = useState('')
  const [totp, setTotp] = useState('')
  const [needsTotp, setNeedsTotp] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)

  async function submit(e: React.FormEvent) {
    e.preventDefault()
    setBusy(true)
    setError(null)
    try {
      onDone(await api.login(username, password, totp || undefined))
    } catch (err) {
      const msg = err instanceof ApiError ? err.message : 'Anmeldung fehlgeschlagen'
      // Die API verlangt den zweiten Faktor erst, wenn Name und Passwort stimmen.
      if (msg.includes('Code aus deiner App')) setNeedsTotp(true)
      setError(msg)
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="login">
      <form className="login__card panel" onSubmit={submit}>
        <div className="login__mark" aria-hidden="true">O</div>
        <h1 className="h-card" style={{ marginBottom: 4 }}>OpenTerminalApps</h1>
        <p className="sub" style={{ marginBottom: 22 }}>Melde dich an, um deinen Arbeitsplatz zu öffnen.</p>

        <label className="field">
          <span className="field__label" style={{ display: 'block', marginBottom: 8 }}>Benutzername</span>
          <div className="row-item">
            <input value={username} autoFocus autoComplete="username" required
              onChange={(e) => setUsername(e.target.value)} />
          </div>
        </label>

        <label className="field">
          <span className="field__label" style={{ display: 'block', marginBottom: 8 }}>Passwort</span>
          <div className="row-item">
            <input type="password" value={password} autoComplete="current-password" required
              onChange={(e) => setPassword(e.target.value)} />
          </div>
        </label>

        {needsTotp && (
          <label className="field">
            <span className="field__label" style={{ display: 'block', marginBottom: 8 }}>Code aus deiner App</span>
            <div className="row-item">
              <input value={totp} inputMode="numeric" autoComplete="one-time-code" maxLength={6}
                onChange={(e) => setTotp(e.target.value)} />
            </div>
          </label>
        )}

        {error && <p className="login__error" role="alert">{error}</p>}

        <button className="btn btn--primary" style={{ width: '100%', height: 40 }} disabled={busy}>
          {busy ? 'Wird geprüft…' : 'Anmelden'}
        </button>
      </form>
    </div>
  )
}
