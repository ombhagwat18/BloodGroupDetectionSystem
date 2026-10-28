import { useCallback, useEffect, useState } from 'react'
import { Bar, BarChart, CartesianGrid, Legend, Line, LineChart, ReferenceLine, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts'
import { Award, BrainCircuit, Gauge, Play, Sigma, Square, Target } from 'lucide-react'
import { api } from '../api'
import { useAuth } from '../auth'
import { Empty } from '../components/ui'

const axis = { fontSize: 12, fill: '#5b6b86' }
const COLORS = { vgg_light: '#2563eb', resnet_small: '#059669', mobilenetv2_transfer: '#d97706', resnet50_transfer: '#7c3aed' }
const LABELS = {
  vgg_light: 'VGG-light (CNN, scratch)', resnet_small: 'ResNet-small (CNN, scratch)',
  mobilenetv2_transfer: 'MobileNetV2 (transfer)', resnet50_transfer: 'ResNet50 (transfer)',
  hog_svm: 'HOG + SVM (classical)', majority_class: 'Majority class (chance)',
}
// Numbers the original notebooks report (ml/notebooks). Shown only until this project's own training has run.
const REFERENCE = [
  { name: 'ResNet50 (ref.)', test: 81 }, { name: 'VGG16 (ref.)', test: 74 },
  { name: 'VGG-inspired (ref.)¹', test: 88 },
]
const pct = (v) => (v == null ? '—' : `${(v * 100).toFixed(1)}%`)

function Kpi({ icon: Icon, label, value, sub }) {
  return (
    <div className="card kpi">
      <div className="ic"><Icon size={22} /></div>
      <div><div className="v">{value}</div><div className="l">{label}{sub ? ` · ${sub}` : ''}</div></div>
    </div>
  )
}

export default function Models() {
  const { can } = useAuth()
  const [t, setT] = useState(null)
  const [err, setErr] = useState('')
  const [epochs, setEpochs] = useState(25)
  const load = useCallback(() => api.training().then(setT).catch((e) => setErr(e.message)), [])
  useEffect(() => {
    load()
    const id = setInterval(load, t?.running ? 2000 : 10000)
    return () => clearInterval(id)
  }, [load, t?.running])

  if (!t) return <Empty>{err || 'Loading…'}</Empty>
  const m = t.metrics || {}
  const sel = m.selected
  const prog = t.progress
  const names = prog ? Object.keys(prog.models) : []
  const maxEp = Math.max(0, ...names.map((n) => prog.models[n].epochs.length))
  const curve = Array.from({ length: maxEp }, (_, i) => {
    const row = { epoch: i + 1 }
    names.forEach((n) => { const e = prog.models[n].epochs[i]; if (e) row[n] = +(e.val_accuracy * 100).toFixed(1) })
    return row
  })
  const cur = prog?.current && prog.models[prog.current]
  const compare = m.candidates
    ? Object.entries(m.candidates).map(([n, r]) => ({ name: LABELS[n] || n, val: +(r.val_accuracy * 100).toFixed(1), test: +(r.test.accuracy * 100).toFixed(1) }))
    : REFERENCE
  const start = () => { setErr(''); api.startTraining({ epochs }).then(load).catch((e) => setErr(e.message)) }
  const stop = () => api.stopTraining().then(load).catch((e) => setErr(e.message))

  return (
    <>
      <div className="page-head">
        <div><h1>Models &amp; Training</h1><p>Accuracy of every candidate model, live training progress and per-class results.</p></div>
        <div className="row">
          <label className="row small" style={{ margin: 0 }}>Max epochs
            <input type="number" min={1} max={100} value={epochs} onChange={(e) => setEpochs(+e.target.value)} style={{ width: 72 }} disabled={t.running} />
          </label>
          {can('train') && (t.running
            ? <button className="btn danger" onClick={stop}><Square size={16} />Stop training</button>
            : <button className="btn primary" onClick={start} disabled={!t.dataset_found}><Play size={16} />Train all models</button>)}
        </div>
      </div>
      {err && <div className="banner bad">{err}</div>}
      {!t.dataset_found && <div className="banner warn">Dataset not found. Put the 8 class folders (A+ … O−) in <code>ml/data/dataset_blood_group/</code> to enable training.</div>}

      <div className="grid g4" style={{ marginBottom: 16 }}>
        <Kpi icon={Award} label="Selected model" value={sel ? (LABELS[sel] || sel).split(' (')[0] : '—'} sub={sel ? 'best validation accuracy' : 'not trained yet'} />
        <Kpi icon={Target} label="Test accuracy" value={pct(m.test_accuracy)} sub={m.split ? `${m.split.test} held-out images` : undefined} />
        <Kpi icon={Sigma} label="Macro F1" value={pct(m.test?.macro_f1)} />
        <Kpi icon={Gauge} label="Random guess" value="12.5%" sub="8 classes" />
      </div>

      <div className="grid g2" style={{ marginBottom: 16 }}>
        <div className="card">
          <div className="row" style={{ marginBottom: 12 }}>
            <h2 style={{ margin: 0 }}><BrainCircuit size={18} />Live training — validation accuracy</h2>
            <span className="spacer" />
            {prog && <span className={`pill ${t.running ? 'ok' : prog.status === 'done' ? 'gray' : 'warn'}`}>{t.running && <span className="dot pulse" />}{t.running ? 'Running' : prog.status}</span>}
          </div>
          {curve.length ? (
            <ResponsiveContainer width="100%" height={250}>
              <LineChart data={curve} margin={{ left: -16, right: 8, top: 8 }}>
                <CartesianGrid stroke="#e6eefb" vertical={false} />
                <XAxis dataKey="epoch" tick={axis} tickLine={false} axisLine={false} />
                <YAxis domain={[0, 100]} unit="%" tick={axis} tickLine={false} axisLine={false} />
                <Tooltip formatter={(v, n) => [`${v}%`, LABELS[n] || n]} labelFormatter={(e) => `Epoch ${e}`} />
                <Legend formatter={(n) => LABELS[n] || n} wrapperStyle={{ fontSize: 12 }} />
                <ReferenceLine y={12.5} stroke="#9aa6bb" strokeDasharray="4 4" />
                {names.map((n) => <Line key={n} isAnimationActive={false} type="monotone" dataKey={n} stroke={COLORS[n] || '#64748b'} strokeWidth={2.5} dot={false} connectNulls />)}
              </LineChart>
            </ResponsiveContainer>
          ) : <Empty>{prog ? prog.stage : 'No training run yet. Press "Train all models" — the curve updates after every epoch.'}</Empty>}
          {prog && (
            <div className="small muted" style={{ marginTop: 8 }}>
              {prog.stage}
              {cur && <div className="bar" style={{ marginTop: 6 }}><i style={{ width: `${(cur.epochs.length / cur.max_epochs) * 100}%` }} /></div>}
            </div>
          )}
        </div>

        <div className="card">
          <h2>Model comparison {m.candidates ? '' : <span className="pill warn">reference numbers</span>}</h2>
          <ResponsiveContainer width="100%" height={250}>
            <BarChart data={compare} margin={{ left: -16, right: 8, top: 8 }}>
              <CartesianGrid stroke="#e6eefb" vertical={false} />
              <XAxis dataKey="name" tick={{ ...axis, fontSize: 10 }} tickLine={false} axisLine={false} interval={0} />
              <YAxis domain={[0, 100]} unit="%" tick={axis} tickLine={false} axisLine={false} />
              <Tooltip formatter={(v) => `${v}%`} cursor={{ fill: '#eef4ff' }} />
              <Legend wrapperStyle={{ fontSize: 12 }} />
              <ReferenceLine y={12.5} stroke="#9aa6bb" strokeDasharray="4 4" />
              {m.candidates && <Bar isAnimationActive={false} dataKey="val" name="Validation" fill="#93b4f5" radius={[4, 4, 0, 0]} />}
              <Bar isAnimationActive={false} dataKey="test" name="Test" fill="#2563eb" radius={[4, 4, 0, 0]} />
            </BarChart>
          </ResponsiveContainer>
          {!m.candidates && <p className="small muted">Reported by the original notebooks, not reproduced here. ¹ Inflated: augmented copies of the same image were split across train and test. Train once to replace these with honest numbers.</p>}
        </div>
      </div>

      {m.test?.per_class ? (
        <div className="grid g2">
          <div className="card">
            <h2>Per-class results (test set)</h2>
            <div className="table-wrap"><table>
              <thead><tr><th>Group</th><th>Precision</th><th>Recall</th><th>F1</th><th>Images</th></tr></thead>
              <tbody>{Object.entries(m.test.per_class).map(([g, r]) => (
                <tr key={g}><td><b>{g}</b></td><td>{pct(r.precision)}</td><td>{pct(r.recall)}</td><td>{pct(r['f1-score'])}</td><td className="muted">{r.support}</td></tr>
              ))}</tbody>
            </table></div>
          </div>
          <div className="card">
            <h2>Confusion matrix (rows = true, columns = predicted)</h2>
            <div className="table-wrap"><table>
              <thead><tr><th></th>{m.classes.map((c) => <th key={c}>{c}</th>)}</tr></thead>
              <tbody>{m.test.confusion_matrix.map((row, i) => {
                const total = row.reduce((a, b) => a + b, 0) || 1
                return (
                  <tr key={i}><td><b>{m.classes[i]}</b></td>{row.map((v, j) => (
                    <td key={j} style={{ textAlign: 'center', background: `rgba(37,99,235,${(v / total) * 0.85})`, color: v / total > 0.5 ? '#fff' : undefined }}>{v}</td>
                  ))}</tr>
                )
              })}</tbody>
            </table></div>
          </div>
        </div>
      ) : null}

      {t.log.length > 0 && (
        <div className="card" style={{ marginTop: 16 }}>
          <h2>Training log (last lines)</h2>
          <pre style={{ margin: 0, maxHeight: 220 }}>{t.log.join('\n')}</pre>
        </div>
      )}
    </>
  )
}
