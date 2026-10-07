import { useCallback, useEffect, useState } from 'react'
import { Link, useNavigate, useParams } from 'react-router-dom'
import { ArrowLeft, Fingerprint, HeartPulse, Pencil, Trash2, TriangleAlert } from 'lucide-react'
import { api, fmtDate } from '../api'
import { useLive } from '../live'
import { canDonateTo, canReceiveFrom, ageBand } from '../medical'
import { Blood, Empty, Modal, StatusPill, Toast } from '../components/ui'
import ScanResult from '../components/ScanResult'
import { PatientForm } from './Patients'

export default function PatientDetail() {
  const { id } = useParams()
  const nav = useNavigate()
  const { device, subscribe } = useLive()
  const [p, setP] = useState(null)
  const [scans, setScans] = useState([])
  const [editing, setEditing] = useState(false)
  const [open, setOpen] = useState(null)
  const [toast, setToast] = useState('')
  const [enrolling, setEnrolling] = useState(false)

  const load = useCallback(() => {
    api.patient(id).then(setP).catch(() => setP(false))
    api.patientScans(id).then(setScans).catch(() => {})
  }, [id])
  useEffect(() => { load() }, [load])
  useEffect(() => subscribe((m) => {
    if (m.event === 'enroll_result') { setEnrolling(false); setToast(m.data.ok ? 'Fingerprint enrolled on the sensor' : `Enrolment failed: ${m.data.error}`); load() }
    if (m.event === 'scan_created') load()
    if (m.event === 'device_event' && enrolling) setToast(m.data.message)
  }), [subscribe, load, enrolling])
  useEffect(() => { if (!toast) return; const t = setTimeout(() => setToast(''), 4000); return () => clearTimeout(t) }, [toast])

  if (p === false) return <Empty>Patient not found. <Link to="/patients">Back</Link></Empty>
  if (!p) return <Empty>Loading…</Empty>

  const enroll = async () => {
    try {
      await api.sendCommand({ type: 'enroll', patient_id: p.id, device_id: device?.device_id || 'esp32-01' })
      setEnrolling(true); setToast('Enrolment started — follow the prompts on the sensor')
    } catch (e) { setToast(e.message) }
  }
  const remove = async () => {
    if (!window.confirm(`Delete ${p.name} and unlink their scans?`)) return
    await api.deletePatient(p.id); nav('/patients')
  }
  const confirmed = scans.filter((s) => s.confirmed_group)
  const latestPred = scans.find((s) => s.predicted && s.status !== 'rejected')
  const mismatch = p.blood_group && latestPred && latestPred.predicted !== p.blood_group

  return (
    <>
      <div className="page-head">
        <div>
          <Link to="/patients" className="small row" style={{ gap: 4 }}><ArrowLeft size={14} />All patients</Link>
          <h1 style={{ marginTop: 6 }}>{p.name} <span className="muted" style={{ fontWeight: 500, fontSize: 15 }}>{p.code}</span></h1>
          <p>{[p.age != null && `${p.age} yrs (${ageBand(p.age)})`, p.sex, p.phone].filter(Boolean).join(' · ') || 'No demographics recorded'}</p>
        </div>
        <div className="row">
          <button className="btn" onClick={enroll} disabled={!device?.online || enrolling}><Fingerprint size={16} />{p.sensor_slot ? 'Re-enrol fingerprint' : 'Enrol fingerprint'}</button>
          <button className="btn" onClick={() => setEditing(true)}><Pencil size={16} />Edit</button>
          <button className="btn danger" onClick={remove}><Trash2 size={16} />Delete</button>
        </div>
      </div>

      <div className="grid g-main" style={{ marginBottom: 16 }}>
        <div className="card">
          <h2><HeartPulse size={18} />Medical profile</h2>
          <div className="grid g3" style={{ marginBottom: 14 }}>
            <div><div className="muted small">Blood group</div><div style={{ marginTop: 4 }}><Blood group={p.blood_group} /></div></div>
            <div><div className="muted small">Allergies</div><div>{p.allergies || '—'}</div></div>
            <div><div className="muted small">Conditions</div><div>{p.conditions || '—'}</div></div>
          </div>
          <div className="muted small">Notes</div>
          <div style={{ whiteSpace: 'pre-wrap', marginBottom: 12 }}>{p.notes || '—'}</div>
          <div className="row small muted">
            <span>Sensor: {p.sensor_slot ? `enrolled in slot ${p.sensor_slot}` : 'not enrolled'}</span>
            <span>· Registered {fmtDate(p.created_at)}</span>
          </div>
          {mismatch && (
            <div className="banner warn" style={{ marginTop: 12 }}><TriangleAlert size={16} />Latest fingerprint prediction ({latestPred.predicted}) differs from the recorded group ({p.blood_group}). The recorded, lab-confirmed group takes precedence.</div>
          )}
        </div>

        <div className="card">
          <h2>Transfusion compatibility</h2>
          {p.blood_group ? (
            <>
              <div className="muted small">Can donate red cells to</div>
              <div className="compat" style={{ margin: '6px 0 12px' }}>{canDonateTo(p.blood_group).map((g) => <Blood key={g} group={g} />)}</div>
              <div className="muted small">Can receive red cells from</div>
              <div className="compat" style={{ margin: '6px 0 12px' }}>{canReceiveFrom(p.blood_group).map((g) => <Blood key={g} group={g} />)}</div>
              <div className="muted small">ABO/Rh red-cell rules only. Crossmatching is still required.</div>
            </>
          ) : <Empty>Record a lab-confirmed blood group to see compatibility.</Empty>}
        </div>
      </div>

      <div className="card">
        <h2>Fingerprint scans ({scans.length}) <span className="muted small" style={{ fontWeight: 500 }}>· {confirmed.length} lab-confirmed</span></h2>
        {scans.length === 0 ? <Empty>No scans yet for this patient.</Empty> : (
          <div className="table-wrap"><table>
            <thead><tr><th></th><th>Predicted</th><th>Confidence</th><th>Confirmed</th><th>Status</th><th>When</th></tr></thead>
            <tbody>{scans.map((s) => (
              <tr key={s.id} className="click" onClick={() => setOpen(s)}>
                <td><img className="thumb" src={s.image_url} alt="" /></td>
                <td><Blood group={s.predicted} /></td>
                <td>{s.confidence != null ? `${(s.confidence * 100).toFixed(0)}%` : '—'}</td>
                <td><Blood group={s.confirmed_group} /></td>
                <td><StatusPill status={s.status} /></td>
                <td className="muted">{fmtDate(s.created_at)}</td>
              </tr>))}</tbody>
          </table></div>
        )}
      </div>

      {editing && <PatientForm initial={p} onClose={() => setEditing(false)} onSaved={(np) => { setEditing(false); setP(np) }} />}
      {open && <Modal title="Scan" wide onClose={() => { setOpen(null); load() }}><ScanResult scan={open} onChange={() => load()} /></Modal>}
      <Toast msg={toast} />
    </>
  )
}
