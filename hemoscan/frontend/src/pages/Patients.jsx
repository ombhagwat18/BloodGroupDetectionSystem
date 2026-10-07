import { useCallback, useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { Fingerprint, Plus, Search } from 'lucide-react'
import { api, GROUPS } from '../api'
import { Blood, Empty, Field, Modal } from '../components/ui'

export const EMPTY = { name: '', age: '', sex: '', phone: '', blood_group: '', allergies: '', conditions: '', notes: '' }

export function PatientForm({ initial, onSaved, onClose }) {
  const [f, setF] = useState({ ...EMPTY, ...Object.fromEntries(Object.entries(initial || {}).filter(([k]) => k in EMPTY).map(([k, v]) => [k, v ?? ''])) })
  const [err, setErr] = useState('')
  const set = (k) => (e) => setF({ ...f, [k]: e.target.value })
  const save = async (e) => {
    e.preventDefault(); setErr('')
    const body = { ...f, age: f.age === '' ? null : +f.age, sex: f.sex || null, blood_group: f.blood_group || null }
    try { onSaved(initial?.id ? await api.updatePatient(initial.id, body) : await api.createPatient(body)) } catch (x) { setErr(x.message) }
  }
  return (
    <Modal title={initial?.id ? 'Edit patient' : 'New patient'} onClose={onClose}>
      <form onSubmit={save}>
        <Field label="Full name *"><input required value={f.name} onChange={set('name')} autoFocus /></Field>
        <div className="grid g3">
          <Field label="Age"><input type="number" min="0" max="130" value={f.age} onChange={set('age')} /></Field>
          <Field label="Sex"><select value={f.sex} onChange={set('sex')}><option value="">—</option><option>Female</option><option>Male</option><option>Other</option></select></Field>
          <Field label="Blood group (lab-confirmed)"><select value={f.blood_group} onChange={set('blood_group')}><option value="">Unknown</option>{GROUPS.map((g) => <option key={g}>{g}</option>)}</select></Field>
        </div>
        <Field label="Phone"><input value={f.phone} onChange={set('phone')} /></Field>
        <Field label="Allergies"><input value={f.allergies} onChange={set('allergies')} placeholder="e.g. Penicillin" /></Field>
        <Field label="Medical conditions"><input value={f.conditions} onChange={set('conditions')} placeholder="e.g. Anaemia, diabetes" /></Field>
        <Field label="Notes"><textarea rows={3} value={f.notes} onChange={set('notes')} /></Field>
        {err && <div className="banner bad">{err}</div>}
        <div className="row"><span className="spacer" /><button type="button" className="btn" onClick={onClose}>Cancel</button><button className="btn primary">Save</button></div>
      </form>
    </Modal>
  )
}

export default function Patients() {
  const [list, setList] = useState(null)
  const [q, setQ] = useState('')
  const [adding, setAdding] = useState(false)
  const nav = useNavigate()
  const load = useCallback(() => api.patients(q).then(setList).catch(() => setList([])), [q])
  useEffect(() => { const t = setTimeout(load, 200); return () => clearTimeout(t) }, [load])

  return (
    <>
      <div className="page-head">
        <div><h1>Patients</h1><p>Medical records linked to fingerprints enrolled on the sensor.</p></div>
        <button className="btn primary" onClick={() => setAdding(true)}><Plus size={16} />Add patient</button>
      </div>
      <div className="card">
        <div className="row" style={{ marginBottom: 12 }}>
          <div className="search"><Search size={16} /><input placeholder="Search name, ID or phone" value={q} onChange={(e) => setQ(e.target.value)} /></div>
          <span className="muted small">{list ? `${list.length} patient${list.length === 1 ? '' : 's'}` : ''}</span>
        </div>
        {!list ? <Empty>Loading…</Empty> : list.length === 0 ? <Empty>No patients found.</Empty> : (
          <div className="table-wrap"><table>
            <thead><tr><th>ID</th><th>Name</th><th>Age / Sex</th><th>Blood group</th><th>Fingerprint</th><th>Scans</th></tr></thead>
            <tbody>
              {list.map((p) => (
                <tr key={p.id} className="click" onClick={() => nav(`/patients/${p.id}`)}>
                  <td className="muted">{p.code}</td>
                  <td><b>{p.name}</b></td>
                  <td>{[p.age, p.sex].filter((x) => x != null && x !== '').join(' · ') || '—'}</td>
                  <td><Blood group={p.blood_group} /></td>
                  <td>{p.sensor_slot ? <span className="pill ok"><Fingerprint size={13} />Slot {p.sensor_slot}</span> : <span className="pill gray">Not enrolled</span>}</td>
                  <td>{p.scan_count}</td>
                </tr>
              ))}
            </tbody>
          </table></div>
        )}
      </div>
      {adding && <PatientForm onClose={() => setAdding(false)} onSaved={(p) => { setAdding(false); nav(`/patients/${p.id}`) }} />}
    </>
  )
}
