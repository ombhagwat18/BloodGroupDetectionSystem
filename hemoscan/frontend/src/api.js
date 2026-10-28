const TOKEN_KEY = 'hemoscan_token'
export const getToken = () => { try { return localStorage.getItem(TOKEN_KEY) } catch { return null } }
export const setToken = (t) => { try { t ? localStorage.setItem(TOKEN_KEY, t) : localStorage.removeItem(TOKEN_KEY) } catch { /* private mode */ } }
/** <img> tags cannot send headers, so scan images carry the token in the URL. */
export const imgUrl = (u) => (u && getToken() ? `${u}?token=${encodeURIComponent(getToken())}` : u)

async function req(method, url, body, isForm) {
  const headers = body && !isForm ? { 'Content-Type': 'application/json' } : {}
  const token = getToken()
  if (token) headers.Authorization = `Bearer ${token}`
  const res = await fetch(url, {
    method,
    headers,
    body: body ? (isForm ? body : JSON.stringify(body)) : undefined,
  })
  if (res.status === 401 && token) {  // expired or revoked session -> back to the login screen
    setToken(null)
    window.dispatchEvent(new Event('hemoscan-logout'))
  }
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
  authStatus: () => req('GET', '/api/auth/status'),
  setup: (b) => req('POST', '/api/auth/setup', b),
  login: (b) => req('POST', '/api/auth/login', b),
  me: () => req('GET', '/api/auth/me'),
  changePassword: (b) => req('POST', '/api/auth/password', b),
  users: () => req('GET', '/api/users'),
  createUser: (b) => req('POST', '/api/users', b),
  updateUser: (id, b) => req('PATCH', `/api/users/${id}`, b),
  deleteUser: (id) => req('DELETE', `/api/users/${id}`),
  stats: () => req('GET', '/api/stats'),
  model: () => req('GET', '/api/model'),
  training: () => req('GET', '/api/training'),
  startTraining: (b) => req('POST', '/api/training/start', b),
  stopTraining: () => req('POST', '/api/training/stop'),
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
