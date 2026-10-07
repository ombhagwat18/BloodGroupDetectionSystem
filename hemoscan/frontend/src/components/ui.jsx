import { useEffect } from 'react'
import { X } from 'lucide-react'

export function Modal({ title, onClose, children, wide }) {
  useEffect(() => {
    const h = (e) => e.key === 'Escape' && onClose()
    window.addEventListener('keydown', h)
    return () => window.removeEventListener('keydown', h)
  }, [onClose])
  return (
    <div className="modal-bg" onMouseDown={(e) => e.target === e.currentTarget && onClose()}>
      <div className="modal" style={wide ? { maxWidth: 760 } : undefined}>
        <div className="row" style={{ marginBottom: 6 }}>
          <h2 style={{ margin: 0 }}>{title}</h2>
          <span className="spacer" />
          <button className="btn sm" onClick={onClose} aria-label="Close"><X size={16} /></button>
        </div>
        {children}
      </div>
    </div>
  )
}

export const Blood = ({ group, big }) => (
  <span className={`blood${big ? ' big' : ''}${group ? '' : ' none'}`}>{group || '—'}</span>
)

export function StatusPill({ status }) {
  const map = { pending: ['warn', 'Needs review'], confirmed: ['ok', 'Confirmed'], rejected: ['bad', 'Rejected'] }
  const [cls, label] = map[status] || ['gray', status]
  return <span className={`pill ${cls}`}>{label}</span>
}

export function ProbBars({ probs, top = 4 }) {
  if (!probs) return null
  const rows = Object.entries(probs).sort((a, b) => b[1] - a[1]).slice(0, top)
  return rows.map(([g, p]) => (
    <div className="bar-row" key={g}>
      <b>{g}</b>
      <div className="bar"><i style={{ width: `${p * 100}%` }} /></div>
      <span className="muted">{(p * 100).toFixed(1)}%</span>
    </div>
  ))
}

export const Empty = ({ children }) => <div className="empty">{children}</div>

export function Field({ label, children }) {
  return <div className="field"><label>{label}</label>{children}</div>
}

export function Toast({ msg }) {
  return msg ? <div className="toast">{msg}</div> : null
}
