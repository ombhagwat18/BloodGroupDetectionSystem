import { useEffect, useState } from 'react'
import { Cpu, Wifi } from 'lucide-react'
import { api } from '../api'
import { useLive } from '../live'
import { Empty } from '../components/ui'

export default function Devices() {
  const { devices, model } = useLive()
  const [cmds, setCmds] = useState([])
  useEffect(() => { const l = () => api.commands().then(setCmds).catch(() => {}); l(); const t = setInterval(l, 4000); return () => clearInterval(t) }, [])
  const host = location.hostname === 'localhost' ? '<laptop-ip>' : location.hostname

  return (
    <>
      <div className="page-head"><div><h1>Device &amp; Model</h1><p>ESP32 + R307 connection status, ML model and setup details.</p></div></div>
      <div className="grid g2" style={{ marginBottom: 16 }}>
        <div className="card">
          <h2><Wifi size={18} />ESP32 devices</h2>
          {devices.length === 0 ? <Empty>No device has connected yet.</Empty> : devices.map((d) => (
            <div key={d.device_id} className="row" style={{ padding: '10px 0', borderBottom: '1px solid #edf2fa' }}>
              <div style={{ flex: 1, minWidth: 160 }}>
                <b>{d.device_id}</b>
                <div className="muted small">{d.ip || '—'} · fw {d.fw || '—'} · state {d.state}{d.template_count != null ? ` · ${d.template_count} fingerprints stored` : ''}</div>
              </div>
              <span className={`pill ${d.online ? 'ok' : 'gray'}`}><span className="dot" />{d.online ? 'Online' : 'Offline'}</span>
              <span className={`pill ${d.sensor_ok ? 'ok' : 'bad'}`}>R307 {d.sensor_ok ? 'OK' : 'not found'}</span>
            </div>
          ))}
        </div>
        <div className="card">
          <h2><Cpu size={18} />ML model</h2>
          {model && (
            <>
              <div className="row"><span className={`pill ${model.mode === 'model' ? 'ok' : model.mode === 'demo' ? 'warn' : 'bad'}`}>{model.mode === 'model' ? 'Loaded' : model.mode === 'demo' ? 'Demo mode (random output)' : 'Not loaded'}</span></div>
              <p className="small muted" style={{ margin: '10px 0 4px' }}>{model.architecture} · input {model.input} · classes {model.classes.join(', ')}</p>
              <div className="small">File: <code>{model.path}</code></div>
              {model.error && <div className="banner bad" style={{ marginTop: 10 }}>{model.error}</div>}
              {model.mode !== 'model' && <div className="banner info" style={{ marginTop: 10 }}>Export <code>fingerprint_model.h5</code> from the notebook (last cells) — or run <code>python train_model.py --data …</code> — and put it in <code>backend/models/</code>, then restart the API.</div>}
            </>
          )}
        </div>
      </div>

      <div className="grid g2">
        <div className="card">
          <h2>ESP32 connection settings</h2>
          <p className="small muted">Put these in the firmware (<code>hemoscan_esp32.ino</code>). The ESP32 and this laptop must be on the same WiFi.</p>
          <pre>{`SERVER_URL = "http://${host}:8000"\nDEVICE_KEY = "hemoscan-dev-key"\nDEVICE_ID  = "esp32-01"`}</pre>
          <p className="small muted">Allow port 8000 through Windows Firewall, and run the API with <code>--host 0.0.0.0</code>.</p>
        </div>
        <div className="card">
          <h2>Recent commands</h2>
          {cmds.length === 0 ? <Empty>No commands sent yet.</Empty> : (
            <table><thead><tr><th>#</th><th>Type</th><th>Status</th></tr></thead>
              <tbody>{cmds.slice(0, 8).map((c) => (
                <tr key={c.id}><td className="muted">{c.id}</td><td>{c.type}</td>
                  <td><span className={`pill ${c.status === 'done' ? 'ok' : c.status === 'failed' ? 'bad' : 'warn'}`}>{c.status}</span>{c.status === 'failed' && c.result ? <span className="muted small"> {c.result}</span> : null}</td></tr>))}</tbody></table>
          )}
        </div>
      </div>
    </>
  )
}
