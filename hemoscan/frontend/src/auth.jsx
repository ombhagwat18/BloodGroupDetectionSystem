import { createContext, useCallback, useContext, useEffect, useMemo, useState } from 'react'
import { api, getToken, setToken } from './api'

export const ROLES = {
  admin: 'Administrator',
  doctor: 'Doctor',
  lab_tech: 'Lab technician',
  operator: 'Operator',
}

// Mirrors the server's rules in backend/app/main.py (STAFF / REVIEWERS). The server is the real
// enforcement; this only decides which tabs and buttons are shown.
const STAFF = ['admin', 'doctor', 'operator']
const PERMISSIONS = {
  scan: STAFF,                                  // live capture, upload, enrol fingerprint
  patientCreate: STAFF,
  patientEdit: ['admin', 'doctor'],
  patientDelete: ['admin'],
  review: ['admin', 'doctor', 'lab_tech'],      // confirm / reject against the lab result
  assign: ['admin', 'doctor'],                  // link a scan to a patient
  scanDelete: ['admin'],
  train: ['admin'],
  devices: ['admin'],
  users: ['admin'],
}

const Ctx = createContext(null)
export const useAuth = () => useContext(Ctx)

export function AuthProvider({ children }) {
  const [user, setUser] = useState(null)
  const [ready, setReady] = useState(false)   // false while we check a stored token

  useEffect(() => {
    if (!getToken()) { setReady(true); return }
    api.me().then(setUser).catch(() => setToken(null)).finally(() => setReady(true))
  }, [])

  useEffect(() => {
    const out = () => setUser(null)
    window.addEventListener('hemoscan-logout', out)
    return () => window.removeEventListener('hemoscan-logout', out)
  }, [])

  const signIn = useCallback((res) => { setToken(res.token); setUser(res.user) }, [])
  const logout = useCallback(() => { setToken(null); setUser(null) }, [])
  const can = useCallback((perm) => !!user && (PERMISSIONS[perm] || []).includes(user.role), [user])

  const value = useMemo(() => ({ user, ready, signIn, logout, can }), [user, ready, signIn, logout, can])
  return <Ctx.Provider value={value}>{children}</Ctx.Provider>
}
