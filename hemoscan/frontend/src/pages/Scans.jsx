import { useCallback, useEffect, useState } from 'react'
import { useLocation } from 'react-router-dom'
import { Trash2 } from 'lucide-react'
import { api, fmtDate } from '../api'
import { useLive } from '../live'
import { Blood, Empty, Modal, StatusPill } from '../components/ui'
import ScanResult from '../components/ScanResult'

const TABS = [['', 'All'], ['pending', 'Needs review'], ['confirmed', 'Confirmed'], ['rejected', 'Rejected']]

export default function Scans() {
  const [tab, setTab] = useState('')
  const [list, setList] = useState(null)
  const [open, setOpen] = useState(null)
  const { subscribe } = useLive()
  const loc = useLocation()

  const load = useCallback(() => api.scans(tab ? { status: tab } : {}).then(setList).catch(() => setList([])), [tab])
  useEffect(() => { load() }, [load])
  useEffect(() => subscribe((m) => m.event === 'scan_created' && load()), [subscribe, load])
  useEffect(() => { if (loc.state?.open) api.scan(loc.state.open).then(setOpen).catch(() => {}) }, [loc.state])

  const del = async (e, s) => {
    e.stopPropagation()
    if (window.confirm(`Delete scan #${s.id}?`)) { await api.deleteScan(s.id); load() }
  }

  return (
    <>
      <div className="page-head">
        <div><h1>Scan History</h1><p>Review model predictions and confirm them against laboratory results.</p></div>
        <div className="tabs">{TABS.map(([k, l]) => <button key={k} className={tab === k ? 'on' : ''} onClick={() => setTab(k)}>{l}</button>)}</div>
      </div>
      <div className="card">
        {!list ? <Empty>Loading…</Empty> : list.length === 0 ? <Empty>No scans in this view.</Empty> : (
          <div className="table-wrap"><table>
            <thead><tr><th></th><th>#</th><th>Patient</th><th>Predicted</th><th>Confidence</th><th>Quality</th><th>Confirmed</th><th>Status</th><th>When</th><th></th></tr></thead>
            <tbody>{list.map((s) => (
              <tr key={s.id} className="click" onClick={() => setOpen(s)}>
                <td><img className="thumb" src={s.image_url} alt="" /></td>
                <td className="muted">{s.id}</td>
                <td>{s.patient_name || <span className="muted">Unassigned</span>}</td>
                <td><Blood group={s.predicted} /></td>
                <td>{s.confidence != null ? `${(s.confidence * 100).toFixed(0)}%` : '—'}</td>
                <td><span className={`pill ${s.quality_ok ? 'ok' : 'warn'}`}>{s.quality}</span></td>
                <td><Blood group={s.confirmed_group} /></td>
                <td><StatusPill status={s.status} /></td>
                <td className="muted">{fmtDate(s.created_at)}</td>
                <td><button className="btn sm danger" onClick={(e) => del(e, s)} aria-label="Delete scan"><Trash2 size={14} /></button></td>
              </tr>))}</tbody>
          </table></div>
        )}
      </div>
      {open && <Modal title="Scan review" wide onClose={() => { setOpen(null); load() }}><ScanResult scan={open} onChange={() => load()} /></Modal>}
    </>
  )
}
