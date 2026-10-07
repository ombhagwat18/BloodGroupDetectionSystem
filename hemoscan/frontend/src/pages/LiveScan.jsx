import { useEffect, useRef, useState } from 'react'
import { Fingerprint, Upload, ScanLine, Square } from 'lucide-react'
import { api } from '../api'
import { useLive } from '../live'
import ScanResult from '../components/ScanResult'

const STEPS = [
  ['queued', 'Command sent to ESP32'],
  ['waiting_finger', 'Place finger on the R307 sensor'],
  ['reading_image', 'Reading fingerprint image from sensor'],
  ['analyzing', 'Analysing with ML model'],
  ['done', 'Result ready'],
]
const ORDER = STEPS.map((s) => s[0])

export default function LiveScan() {
  const { device, subscribe } = useLive()
  const [patients, setPatients] = useState([])
  const [patientId, setPatientId] = useState('')
  const [phase, setPhase] = useState(null) // current step key or null when idle
  const [message, setMessage] = useState('')
  const [cmdId, setCmdId] = useState(null)
  const [scan, setScan] = useState(null)
  const [err, setErr] = useState('')
  const file = useRef()
  const cmdRef = useRef(null)

  useEffect(() => { api.patients().then(setPatients).catch(() => {}) }, [])
  useEffect(() => { cmdRef.current = cmdId }, [cmdId])

  useEffect(() => subscribe((msg) => {
    const d = msg.data
    if (msg.event === 'device_event' && d.command_id === cmdRef.current) {
      setMessage(d.message)
      if (ORDER.includes(d.state)) setPhase(d.state === 'reading_image' ? 'reading_image' : d.state)
      if (['failed', 'timeout', 'cancelled'].includes(d.state)) { setPhase(null); setErr(d.message || 'Capture failed') }
    }
    if (msg.event === 'scan_created' && d.command_id === cmdRef.current) {
      setScan(d); setPhase('done'); setCmdId(null)
    }
  }), [subscribe])

  const online = device && device.online
  const busy = phase && phase !== 'done'

  const start = async () => {
    setErr(''); setScan(null)
    try {
      const c = await api.sendCommand({ type: 'capture', device_id: device?.device_id || 'esp32-01', patient_id: patientId ? +patientId : null })
      setCmdId(c.id); cmdRef.current = c.id; setPhase('queued'); setMessage('')
    } catch (e) { setErr(e.message) }
  }
  const cancel = async () => {
    try { await api.sendCommand({ type: 'cancel', device_id: device?.device_id || 'esp32-01' }) } catch { /* ignore */ }
    setPhase(null); setCmdId(null)
  }
  const upload = async (f) => {
    if (!f) return
    setErr(''); setPhase('analyzing')
    try { setScan(await api.uploadScan(f, patientId)); setPhase('done') } catch (e) { setErr(e.message); setPhase(null) }
    file.current.value = ''
  }

  const at = phase ? ORDER.indexOf(phase) : -1
  return (
    <>
      <div className="page-head">
        <div><h1>Live Scan</h1><p>Capture a fingerprint from the R307 sensor and screen for blood group.</p></div>
      </div>
      <div className="grid g-main">
        <div className="card">
          <h2><ScanLine size={18} />Result</h2>
          {scan ? <ScanResult scan={scan} onChange={setScan} /> : (
            <div className="row" style={{ gap: 24, alignItems: 'flex-start' }}>
              <div className={`fp-box${busy ? ' scanning' : ''}`} style={{ width: 220 }}>
                <Fingerprint size={72} strokeWidth={1.2} />
              </div>
              <div className="muted" style={{ flex: 1, minWidth: 180, paddingTop: 8 }}>
                {busy ? (message || 'Working…') : 'Choose a patient (optional) and press “Start capture”. If the finger was enrolled on the sensor, the patient is identified automatically.'}
              </div>
            </div>
          )}
        </div>

        <div className="grid">
          <div className="card">
            <h2><Fingerprint size={18} />Capture</h2>
            {!online && <div className="banner warn">ESP32 is offline. Power it up (or run <code>tools/esp32_simulator.py</code>), or upload an image below.</div>}
            <div className="field">
              <label>Patient (optional)</label>
              <select value={patientId} onChange={(e) => setPatientId(e.target.value)} disabled={busy}>
                <option value="">Identify by fingerprint / assign later</option>
                {patients.map((p) => <option key={p.id} value={p.id}>{p.code} · {p.name}</option>)}
              </select>
            </div>
            <div className="row">
              <button className="btn primary" onClick={start} disabled={!online || busy}><Fingerprint size={16} />Start capture</button>
              {busy && <button className="btn" onClick={cancel}><Square size={14} />Cancel</button>}
              <button className="btn" onClick={() => file.current.click()} disabled={busy}><Upload size={16} />Upload image</button>
              <input ref={file} type="file" accept="image/*" hidden onChange={(e) => upload(e.target.files[0])} />
            </div>
            {err && <div className="banner bad" style={{ marginTop: 12 }}>{err}</div>}
          </div>

          <div className="card">
            <h2>Progress</h2>
            <div className="steps">
              {STEPS.map(([k, label], i) => (
                <div key={k} className={`step ${phase && i < at ? 'done' : ''} ${phase && i === at ? (phase === 'done' ? 'done' : 'now') : ''}`}>
                  <span className="n">{phase && (i < at || phase === 'done') ? '✓' : i + 1}</span>
                  <span>{label}</span>
                </div>
              ))}
            </div>
          </div>
        </div>
      </div>
    </>
  )
}
