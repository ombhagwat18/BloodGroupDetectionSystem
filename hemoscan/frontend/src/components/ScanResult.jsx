import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { CheckCircle2, TriangleAlert, XCircle, UserRound } from 'lucide-react'
import { api, GROUPS, fmtDate } from '../api'
import { Blood, ProbBars, StatusPill } from './ui'

/** Image + prediction + review actions for one scan. onChange(scan) fires after any edit. */
export default function ScanResult({ scan: initial, onChange }) {
  const [scan, setScan] = useState(initial)
  const [patients, setPatients] = useState([])
  const [group, setGroup] = useState(initial.confirmed_group || initial.predicted || 'O+')
  const [err, setErr] = useState('')

  useEffect(() => { setScan(initial); setGroup(initial.confirmed_group || initial.predicted || 'O+') }, [initial])
  useEffect(() => { api.patients().then(setPatients).catch(() => {}) }, [])

  const patch = async (body) => {
    setErr('')
    try {
      const s = await api.patchScan(scan.id, body)
      setScan(s)
      onChange && onChange(s)
    } catch (e) { setErr(e.message) }
  }

  const low = scan.confidence != null && scan.confidence < 0.6
  return (
    <div className="grid" style={{ gridTemplateColumns: 'minmax(160px, 220px) 1fr', alignItems: 'start' }}>
      <div className="fp-box"><img src={scan.image_url} alt="fingerprint" /></div>
      <div>
        <div className="row" style={{ marginBottom: 10 }}>
          <StatusPill status={scan.status} />
          <span className="muted small">Scan #{scan.id} · {fmtDate(scan.created_at)}</span>
        </div>

        {scan.predicted ? (
          <div className="row" style={{ gap: 18, alignItems: 'center', marginBottom: 12 }}>
            <Blood group={scan.confirmed_group || scan.predicted} big />
            <div>
              <div className="muted small">{scan.confirmed_group ? 'Confirmed blood group' : 'Predicted blood group'}</div>
              <div style={{ fontSize: 22, fontWeight: 700 }}>{(scan.confidence * 100).toFixed(1)}% <span className="muted small" style={{ fontWeight: 500 }}>model confidence</span></div>
              {scan.confirmed_group && scan.confirmed_group !== scan.predicted && <span className="pill warn">Model said {scan.predicted}</span>}
            </div>
          </div>
        ) : (
          <div className="banner warn"><TriangleAlert size={16} />No prediction — the ML model is not loaded (see Device &amp; Model).</div>
        )}

        {scan.mode === 'demo' && <div className="banner warn"><TriangleAlert size={16} />DEMO mode: this prediction is random, not from the trained model.</div>}
        {!scan.quality_ok && <div className="banner warn"><TriangleAlert size={16} />Low image quality ({scan.quality}/100). Clean the sensor and the finger, then rescan.</div>}
        {low && scan.quality_ok && <div className="banner info"><TriangleAlert size={16} />Confidence is low — treat as inconclusive.</div>}

        <ProbBars probs={scan.probs} />

        <div className="row small muted" style={{ margin: '10px 0' }}>
          <span>Image quality {scan.quality}/100</span>
          {scan.sensor_slot ? <span>· sensor match slot {scan.sensor_slot}</span> : null}
        </div>

        <div className="field">
          <label><UserRound size={12} style={{ verticalAlign: -1 }} /> Patient</label>
          <div className="row">
            <select style={{ flex: 1, minWidth: 160 }} value={scan.patient_id || ''} onChange={(e) => e.target.value ? patch({ patient_id: +e.target.value }) : patch({ unassign: true })}>
              <option value="">— Unassigned —</option>
              {patients.map((p) => <option key={p.id} value={p.id}>{p.code} · {p.name}</option>)}
            </select>
            {scan.patient_id && <Link to={`/patients/${scan.patient_id}`} className="small">Open record</Link>}
          </div>
        </div>

        <div className="field">
          <label>Lab-confirmed blood group</label>
          <div className="row">
            <select style={{ width: 100 }} value={group} onChange={(e) => setGroup(e.target.value)}>
              {GROUPS.map((g) => <option key={g}>{g}</option>)}
            </select>
            <button className="btn primary" onClick={() => patch({ confirmed_group: group })}><CheckCircle2 size={16} />Confirm</button>
            <button className="btn danger" onClick={() => patch({ status: 'rejected' })}><XCircle size={16} />Reject scan</button>
          </div>
        </div>
        {err && <div className="banner bad">{err}</div>}
      </div>
    </div>
  )
}
