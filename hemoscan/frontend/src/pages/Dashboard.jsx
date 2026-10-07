import { useCallback, useEffect, useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { Area, AreaChart, Bar, BarChart, CartesianGrid, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts'
import { ClipboardCheck, Fingerprint, Target, Users } from 'lucide-react'
import { api, fmtDate } from '../api'
import { useLive } from '../live'
import { Blood, Empty, StatusPill } from '../components/ui'

const BLUE = '#2563eb'
const axis = { fontSize: 12, fill: '#5b6b86' }

function Kpi({ icon: Icon, label, value, sub }) {
  return (
    <div className="card kpi">
      <div className="ic"><Icon size={22} /></div>
      <div><div className="v">{value}</div><div className="l">{label}{sub ? ` · ${sub}` : ''}</div></div>
    </div>
  )
}

export default function Dashboard() {
  const [stats, setStats] = useState(null)
  const [recent, setRecent] = useState([])
  const { subscribe } = useLive()
  const nav = useNavigate()

  const load = useCallback(() => {
    api.stats().then(setStats).catch(() => {})
    api.scans({ limit: 6 }).then(setRecent).catch(() => {})
  }, [])
  useEffect(() => { load() }, [load])
  useEffect(() => subscribe((m) => m.event === 'scan_created' && load()), [subscribe, load])

  if (!stats) return <Empty>Loading…</Empty>
  const hasGroups = stats.patients_by_group.some((g) => g.count)
  return (
    <>
      <div className="page-head">
        <div><h1>Dashboard</h1><p>Overview of patients, fingerprint scans and model performance.</p></div>
        <Link to="/scan" className="btn primary"><Fingerprint size={16} />New scan</Link>
      </div>

      <div className="grid g4" style={{ marginBottom: 16 }}>
        <Kpi icon={Users} label="Patients" value={stats.patients} />
        <Kpi icon={Fingerprint} label="Total scans" value={stats.scans} />
        <Kpi icon={ClipboardCheck} label="Awaiting review" value={stats.pending} />
        <Kpi icon={Target} label="Model vs lab" value={stats.agreement == null ? '—' : `${Math.round(stats.agreement * 100)}%`} sub={stats.agreement == null ? 'no confirmed scans yet' : `${stats.agreement_n} confirmed`} />
      </div>

      <div className="grid g2" style={{ marginBottom: 16 }}>
        <div className="card">
          <h2>Scans — last 14 days</h2>
          <ResponsiveContainer width="100%" height={230}>
            <AreaChart data={stats.daily} margin={{ left: -20, right: 8, top: 8 }}>
              <defs><linearGradient id="g" x1="0" y1="0" x2="0" y2="1"><stop offset="0%" stopColor={BLUE} stopOpacity={0.35} /><stop offset="100%" stopColor={BLUE} stopOpacity={0} /></linearGradient></defs>
              <CartesianGrid stroke="#e6eefb" vertical={false} />
              <XAxis dataKey="date" tick={axis} tickLine={false} axisLine={false} />
              <YAxis allowDecimals={false} tick={axis} tickLine={false} axisLine={false} />
              <Tooltip />
              <Area isAnimationActive={false} type="monotone" dataKey="scans" stroke={BLUE} strokeWidth={2.5} fill="url(#g)" />
            </AreaChart>
          </ResponsiveContainer>
        </div>
        <div className="card">
          <h2>Patients by blood group</h2>
          {hasGroups ? (
            <ResponsiveContainer width="100%" height={230}>
              <BarChart data={stats.patients_by_group} margin={{ left: -20, right: 8, top: 8 }}>
                <CartesianGrid stroke="#e6eefb" vertical={false} />
                <XAxis dataKey="group" tick={axis} tickLine={false} axisLine={false} />
                <YAxis allowDecimals={false} tick={axis} tickLine={false} axisLine={false} />
                <Tooltip cursor={{ fill: '#eef4ff' }} />
                <Bar isAnimationActive={false} dataKey="count" fill={BLUE} radius={[6, 6, 0, 0]} />
              </BarChart>
            </ResponsiveContainer>
          ) : <Empty>No patient has a blood group on record yet.<br />Confirm a scan against a lab result to fill this in.</Empty>}
        </div>
      </div>

      <div className="card">
        <div className="row"><h2 style={{ margin: 0 }}>Recent scans</h2><span className="spacer" /><Link to="/scans" className="small">View all</Link></div>
        {recent.length === 0 ? <Empty>No scans yet. Start one from <Link to="/scan">Live Scan</Link>.</Empty> : (
          <div className="table-wrap"><table>
            <thead><tr><th></th><th>Patient</th><th>Predicted</th><th>Confidence</th><th>Status</th><th>When</th></tr></thead>
            <tbody>
              {recent.map((s) => (
                <tr key={s.id} className="click" onClick={() => nav('/scans', { state: { open: s.id } })}>
                  <td><img className="thumb" src={s.image_url} alt="" /></td>
                  <td>{s.patient_name || <span className="muted">Unassigned</span>}</td>
                  <td><Blood group={s.predicted} /></td>
                  <td>{s.confidence != null ? `${(s.confidence * 100).toFixed(0)}%` : '—'}</td>
                  <td><StatusPill status={s.status} /></td>
                  <td className="muted">{fmtDate(s.created_at)}</td>
                </tr>
              ))}
            </tbody>
          </table></div>
        )}
      </div>
    </>
  )
}
