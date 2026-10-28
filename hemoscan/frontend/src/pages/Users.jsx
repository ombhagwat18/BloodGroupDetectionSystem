import { useCallback, useEffect, useState } from 'react'
import { KeyRound, Plus, Trash2 } from 'lucide-react'
import { api, fmtDate } from '../api'
import { ROLES, useAuth } from '../auth'
import { Empty, Field, Modal } from '../components/ui'

const ROLE_HELP = {
  admin: 'Everything, including users, training and devices.',
  doctor: 'Patients, scans, confirm results, assign scans to patients.',
  lab_tech: 'View everything, confirm or reject results against lab reports.',
  operator: 'Register patients, enrol fingerprints, run scans. Cannot confirm results.',
}

function NewUser({ onSaved, onClose }) {
  const [f, setF] = useState({ username: '', full_name: '', role: 'operator', password: '' })
  const [err, setErr] = useState('')
  const set = (k) => (e) => setF({ ...f, [k]: e.target.value })
  const save = async (e) => {
    e.preventDefault(); setErr('')
    try { onSaved(await api.createUser({ ...f, username: f.username.trim() })) } catch (x) { setErr(x.message) }
  }
  return (
    <Modal title="New user" onClose={onClose}>
      <form onSubmit={save}>
        <Field label="Username *"><input required minLength={3} autoFocus value={f.username} onChange={set('username')} /></Field>
        <Field label="Full name"><input value={f.full_name} onChange={set('full_name')} /></Field>
        <Field label="Role">
          <select value={f.role} onChange={set('role')}>{Object.entries(ROLES).map(([k, v]) => <option key={k} value={k}>{v}</option>)}</select>
          <div className="muted small" style={{ marginTop: 4 }}>{ROLE_HELP[f.role]}</div>
        </Field>
        <Field label="Temporary password (8+ characters) *"><input required type="password" minLength={8} autoComplete="new-password" value={f.password} onChange={set('password')} /></Field>
        {err && <div className="banner bad">{err}</div>}
        <div className="row"><span className="spacer" /><button type="button" className="btn" onClick={onClose}>Cancel</button><button className="btn primary">Create user</button></div>
      </form>
    </Modal>
  )
}

export default function Users() {
  const { user: me } = useAuth()
  const [list, setList] = useState(null)
  const [adding, setAdding] = useState(false)
  const [err, setErr] = useState('')
  const load = useCallback(() => api.users().then(setList).catch((e) => { setErr(e.message); setList([]) }), [])
  useEffect(() => { load() }, [load])

  const act = async (fn) => { setErr(''); try { await fn(); load() } catch (e) { setErr(e.message) } }
  const resetPw = (u) => {
    const pw = window.prompt(`New password for ${u.username} (8+ characters):`)
    if (pw) act(() => api.updateUser(u.id, { password: pw }))
  }
  const remove = (u) => { if (window.confirm(`Delete user ${u.username}? This cannot be undone.`)) act(() => api.deleteUser(u.id)) }

  return (
    <>
      <div className="page-head">
        <div><h1>Users</h1><p>Who can sign in, and what each role is allowed to do.</p></div>
        <button className="btn primary" onClick={() => setAdding(true)}><Plus size={16} />Add user</button>
      </div>
      {err && <div className="banner bad">{err}</div>}
      <div className="card">
        {!list ? <Empty>Loading…</Empty> : list.length === 0 ? <Empty>No users.</Empty> : (
          <div className="table-wrap"><table>
            <thead><tr><th>Username</th><th>Name</th><th>Role</th><th>Status</th><th>Last sign-in</th><th /></tr></thead>
            <tbody>
              {list.map((u) => {
                const self = u.id === me.id
                return (
                  <tr key={u.id}>
                    <td><b>{u.username}</b>{self && <span className="muted small"> (you)</span>}</td>
                    <td>{u.full_name || <span className="muted">—</span>}</td>
                    <td>
                      <select value={u.role} onChange={(e) => act(() => api.updateUser(u.id, { role: e.target.value }))} aria-label={`Role of ${u.username}`}>
                        {Object.entries(ROLES).map(([k, v]) => <option key={k} value={k}>{v}</option>)}
                      </select>
                    </td>
                    <td>
                      <button className={`pill ${u.active ? 'ok' : 'gray'}`} style={{ cursor: self ? 'default' : 'pointer', border: 0 }} disabled={self}
                        onClick={() => act(() => api.updateUser(u.id, { active: !u.active }))} title={self ? '' : 'Click to enable / disable'}>
                        {u.active ? 'Active' : 'Disabled'}
                      </button>
                    </td>
                    <td className="muted">{fmtDate(u.last_login)}</td>
                    <td>
                      <div className="row" style={{ justifyContent: 'flex-end', gap: 6 }}>
                        <button className="btn sm" onClick={() => resetPw(u)} aria-label={`Reset password of ${u.username}`}><KeyRound size={14} />Reset password</button>
                        {!self && <button className="btn sm danger" onClick={() => remove(u)} aria-label={`Delete ${u.username}`}><Trash2 size={14} /></button>}
                      </div>
                    </td>
                  </tr>
                )
              })}
            </tbody>
          </table></div>
        )}
      </div>
      <div className="card" style={{ marginTop: 16 }}>
        <h2>What each role can do</h2>
        <div className="table-wrap"><table>
          <tbody>{Object.entries(ROLES).map(([k, v]) => <tr key={k}><td><b>{v}</b></td><td className="muted">{ROLE_HELP[k]}</td></tr>)}</tbody>
        </table></div>
      </div>
      {adding && <NewUser onClose={() => setAdding(false)} onSaved={() => { setAdding(false); load() }} />}
    </>
  )
}
