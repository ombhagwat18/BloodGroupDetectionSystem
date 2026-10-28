import { useEffect, useState } from 'react'
import { Droplet } from 'lucide-react'
import { api } from '../api'
import { useAuth } from '../auth'
import { Field } from '../components/ui'

/** Sign-in form. While the database has no users it becomes the one-time "create admin" form. */
export default function Login() {
  const { signIn } = useAuth()
  const [needsSetup, setNeedsSetup] = useState(null)
  const [f, setF] = useState({ username: '', full_name: '', password: '', confirm: '' })
  const [err, setErr] = useState('')
  const [busy, setBusy] = useState(false)
  const set = (k) => (e) => setF({ ...f, [k]: e.target.value })

  useEffect(() => { api.authStatus().then((s) => setNeedsSetup(s.needs_setup)).catch(() => setNeedsSetup(false)) }, [])

  const submit = async (e) => {
    e.preventDefault(); setErr('')
    if (needsSetup && f.password !== f.confirm) { setErr('The two passwords do not match.'); return }
    setBusy(true)
    try {
      signIn(needsSetup
        ? await api.setup({ username: f.username.trim(), full_name: f.full_name, role: 'admin', password: f.password })
        : await api.login({ username: f.username, password: f.password }))
    } catch (x) { setErr(x.message) } finally { setBusy(false) }
  }

  return (
    <div style={{ minHeight: '100vh', display: 'grid', placeItems: 'center', padding: 16 }}>
      <form className="card" style={{ width: 'min(400px, 100%)' }} onSubmit={submit}>
        <div className="brand" style={{ marginBottom: 14 }}><div className="brand-mark"><Droplet size={20} /></div>HemoScan</div>
        {needsSetup === null ? <p className="muted">Loading…</p> : (
          <>
            <h2 style={{ marginBottom: 4 }}>{needsSetup ? 'Create the admin account' : 'Sign in'}</h2>
            <p className="muted small" style={{ marginTop: 0 }}>
              {needsSetup ? 'First start: this account manages all other users. You will not be asked again.' : 'Use the account your administrator gave you.'}
            </p>
            <Field label="Username"><input required autoFocus autoComplete="username" value={f.username} onChange={set('username')} minLength={needsSetup ? 3 : undefined} /></Field>
            {needsSetup && <Field label="Full name"><input value={f.full_name} onChange={set('full_name')} /></Field>}
            <Field label={needsSetup ? 'Password (8+ characters)' : 'Password'}>
              <input required type="password" autoComplete={needsSetup ? 'new-password' : 'current-password'} minLength={needsSetup ? 8 : undefined} value={f.password} onChange={set('password')} />
            </Field>
            {needsSetup && <Field label="Repeat password"><input required type="password" autoComplete="new-password" value={f.confirm} onChange={set('confirm')} /></Field>}
            {err && <div className="banner bad">{err}</div>}
            <button className="btn primary" style={{ width: '100%', justifyContent: 'center' }} disabled={busy}>
              {busy ? 'Please wait…' : needsSetup ? 'Create admin and sign in' : 'Sign in'}
            </button>
          </>
        )}
      </form>
    </div>
  )
}
