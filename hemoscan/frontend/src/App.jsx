import { useState } from 'react'
import { Navigate, NavLink, Route, Routes } from 'react-router-dom'
import { Activity, BrainCircuit, Cpu, Droplet, Fingerprint, KeyRound, LayoutDashboard, LogOut, ShieldCheck, TriangleAlert, Users as UsersIcon, ScanLine } from 'lucide-react'
import { api } from './api'
import { ROLES, useAuth } from './auth'
import { LiveProvider, useLive } from './live'
import { Field, Modal } from './components/ui'
import Login from './pages/Login'
import UsersPage from './pages/Users'
import Dashboard from './pages/Dashboard'
import LiveScan from './pages/LiveScan'
import Patients from './pages/Patients'
import PatientDetail from './pages/PatientDetail'
import Scans from './pages/Scans'
import Devices from './pages/Devices'
import Models from './pages/Models'

// [path, label, icon, permission needed to see it (none = every signed-in user)]
const NAV = [
  ['/', 'Dashboard', LayoutDashboard],
  ['/scan', 'Live Scan', Fingerprint, 'scan'],
  ['/patients', 'Patients', UsersIcon],
  ['/scans', 'Scan History', ScanLine],
  ['/models', 'Models & Training', BrainCircuit],
  ['/devices', 'Device & Model', Cpu, 'devices'],
  ['/users', 'Users', ShieldCheck, 'users'],
]

function ChangePassword({ onClose }) {
  const [f, setF] = useState({ current: '', new: '', again: '' })
  const [err, setErr] = useState('')
  const [done, setDone] = useState(false)
  const set = (k) => (e) => setF({ ...f, [k]: e.target.value })
  const save = async (e) => {
    e.preventDefault(); setErr('')
    if (f.new !== f.again) { setErr('The new passwords do not match.'); return }
    try { await api.changePassword({ current: f.current, new: f.new }); setDone(true) } catch (x) { setErr(x.message) }
  }
  return (
    <Modal title="Change password" onClose={onClose}>
      {done ? (
        <><div className="banner info">Password changed.</div><div className="row"><span className="spacer" /><button className="btn primary" onClick={onClose}>Close</button></div></>
      ) : (
        <form onSubmit={save}>
          <Field label="Current password"><input required type="password" autoComplete="current-password" autoFocus value={f.current} onChange={set('current')} /></Field>
          <Field label="New password (8+ characters)"><input required type="password" minLength={8} autoComplete="new-password" value={f.new} onChange={set('new')} /></Field>
          <Field label="Repeat new password"><input required type="password" autoComplete="new-password" value={f.again} onChange={set('again')} /></Field>
          {err && <div className="banner bad">{err}</div>}
          <div className="row"><span className="spacer" /><button type="button" className="btn" onClick={onClose}>Cancel</button><button className="btn primary">Save</button></div>
        </form>
      )}
    </Modal>
  )
}

function UserMenu() {
  const { user, logout } = useAuth()
  const [pw, setPw] = useState(false)
  return (
    <>
      <span className="spacer" />
      <span className="pill gray" title={ROLES[user.role]}><ShieldCheck size={14} />{user.full_name || user.username} · {ROLES[user.role]}</span>
      <button className="btn sm" onClick={() => setPw(true)}><KeyRound size={14} />Password</button>
      <button className="btn sm" onClick={logout}><LogOut size={14} />Sign out</button>
      {pw && <ChangePassword onClose={() => setPw(false)} />}
    </>
  )
}

/** A tab the role may not open sends the user back to the dashboard (the API also refuses). */
function Guard({ perm, children }) {
  const { can } = useAuth()
  return !perm || can(perm) ? children : <Navigate to="/" replace />
}

function TopStatus() {
  const { connected, device, model } = useLive()
  const online = device && device.online
  return (
    <>
      <span className={`pill ${connected ? 'ok' : 'bad'}`}><span className={`dot ${connected ? 'pulse' : ''}`} />{connected ? 'Live' : 'Reconnecting…'}</span>
      <span className={`pill ${online ? (device.sensor_ok ? 'ok' : 'warn') : 'gray'}`}>
        <Activity size={14} />{online ? (device.sensor_ok ? `${device.device_id} · sensor OK` : `${device.device_id} · sensor error`) : 'ESP32 offline'}
      </span>
      <span className={`pill ${model?.mode === 'model' ? 'ok' : model?.mode === 'demo' ? 'warn' : 'bad'}`}>
        <Cpu size={14} />{model?.mode === 'model' ? 'Model loaded' : model?.mode === 'demo' ? 'DEMO predictions' : 'No model'}
      </span>
    </>
  )
}

export default function App() {
  const { user, ready } = useAuth()
  if (!ready) return null
  if (!user) return <Login />
  return <LiveProvider><Shell /></LiveProvider>
}

function Shell() {
  const { can } = useAuth()
  return (
    <div className="app">
      <aside className="sidebar">
        <div className="brand">
          <div className="brand-mark"><Droplet size={20} /></div>HemoScan
        </div>
        <nav className="nav">
          {NAV.filter(([, , , perm]) => !perm || can(perm)).map(([to, label, Icon]) => (
            <NavLink key={to} to={to} end={to === '/'}>
              <Icon size={18} />{label}
            </NavLink>
          ))}
        </nav>
        <div className="side-foot">Fingerprint-assisted blood group screening · R307 + ESP32</div>
      </aside>
      <div className="main">
        <div className="disclaimer">
          <TriangleAlert size={15} />
          Screening aid only. Fingerprint-based blood group predictions are experimental — always confirm with a laboratory test before any clinical decision or transfusion.
        </div>
        <header className="topbar"><TopStatus /><UserMenu /></header>
        <main className="content">
          <Routes>
            <Route path="/" element={<Dashboard />} />
            <Route path="/scan" element={<Guard perm="scan"><LiveScan /></Guard>} />
            <Route path="/patients" element={<Patients />} />
            <Route path="/patients/:id" element={<PatientDetail />} />
            <Route path="/scans" element={<Scans />} />
            <Route path="/models" element={<Models />} />
            <Route path="/devices" element={<Guard perm="devices"><Devices /></Guard>} />
            <Route path="/users" element={<Guard perm="users"><UsersPage /></Guard>} />
          </Routes>
        </main>
      </div>
    </div>
  )
}
