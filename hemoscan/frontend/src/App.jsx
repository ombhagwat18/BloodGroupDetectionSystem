import { NavLink, Route, Routes } from 'react-router-dom'
import { Activity, Cpu, Droplet, Fingerprint, LayoutDashboard, TriangleAlert, Users, ScanLine } from 'lucide-react'
import { useLive } from './live'
import Dashboard from './pages/Dashboard'
import LiveScan from './pages/LiveScan'
import Patients from './pages/Patients'
import PatientDetail from './pages/PatientDetail'
import Scans from './pages/Scans'
import Devices from './pages/Devices'

const NAV = [
  ['/', 'Dashboard', LayoutDashboard],
  ['/scan', 'Live Scan', Fingerprint],
  ['/patients', 'Patients', Users],
  ['/scans', 'Scan History', ScanLine],
  ['/devices', 'Device & Model', Cpu],
]

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
  return (
    <div className="app">
      <aside className="sidebar">
        <div className="brand">
          <div className="brand-mark"><Droplet size={20} /></div>HemoScan
        </div>
        <nav className="nav">
          {NAV.map(([to, label, Icon]) => (
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
        <header className="topbar"><TopStatus /></header>
        <main className="content">
          <Routes>
            <Route path="/" element={<Dashboard />} />
            <Route path="/scan" element={<LiveScan />} />
            <Route path="/patients" element={<Patients />} />
            <Route path="/patients/:id" element={<PatientDetail />} />
            <Route path="/scans" element={<Scans />} />
            <Route path="/devices" element={<Devices />} />
          </Routes>
        </main>
      </div>
    </div>
  )
}
