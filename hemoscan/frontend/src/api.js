async function req(method, url, body, isForm) {
  const res = await fetch(url, {
    method,
    headers: body && !isForm ? { 'Content-Type': 'application/json' } : undefined,
    body: body ? (isForm ? body : JSON.stringify(body)) : undefined,
  })
  if (!res.ok) {
    let msg = res.statusText
    try {
      const j = await res.json()
      msg = typeof j.detail === 'string' ? j.detail : JSON.stringify(j.detail)
    } catch { /* keep statusText */ }
    throw new Error(msg)
  }
  return res.json()
}

export const api = {
  stats: () => req('GET', '/api/stats'),
  model: () => req('GET', '/api/model'),
  devices: () => req('GET', '/api/devices'),
  commands: () => req('GET', '/api/commands'),
  sendCommand: (c) => req('POST', '/api/commands', c),
  patients: (q = '') => req('GET', '/api/patients?q=' + encodeURIComponent(q)),
  patient: (id) => req('GET', `/api/patients/${id}`),
  createPatient: (p) => req('POST', '/api/patients', p),
  updatePatient: (id, p) => req('PUT', `/api/patients/${id}`, p),
  deletePatient: (id) => req('DELETE', `/api/patients/${id}`),
  patientScans: (id) => req('GET', `/api/patients/${id}/scans`),
  scans: (params = {}) => req('GET', '/api/scans?' + new URLSearchParams(params)),
  scan: (id) => req('GET', `/api/scans/${id}`),
  patchScan: (id, b) => req('PATCH', `/api/scans/${id}`, b),
  deleteScan: (id) => req('DELETE', `/api/scans/${id}`),
  uploadScan: (file, patientId) => {
    const f = new FormData()
    f.append('file', file)
    return req('POST', '/api/scans/upload' + (patientId ? `?patient_id=${patientId}` : ''), f, true)
  },
}

export const GROUPS = ['A+', 'A-', 'B+', 'B-', 'AB+', 'AB-', 'O+', 'O-']

export const fmtDate = (t) =>
  t ? new Date(t * 1000).toLocaleString([], { dateStyle: 'medium', timeStyle: 'short' }) : '—'
