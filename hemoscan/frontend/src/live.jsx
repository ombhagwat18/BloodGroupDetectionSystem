import { createContext, useContext, useEffect, useRef, useState, useCallback } from 'react'
import { api } from './api'

const Ctx = createContext(null)
export const useLive = () => useContext(Ctx)

/** One WebSocket for the whole app + a light poll of device status as a fallback. */
export function LiveProvider({ children }) {
  const [connected, setConnected] = useState(false)
  const [devices, setDevices] = useState([])
  const [model, setModel] = useState(null)
  const listeners = useRef(new Set())

  const subscribe = useCallback((fn) => {
    listeners.current.add(fn)
    return () => listeners.current.delete(fn)
  }, [])

  const refreshDevices = useCallback(() => api.devices().then(setDevices).catch(() => {}), [])

  useEffect(() => {
    api.model().then(setModel).catch(() => {})
    refreshDevices()
    const t = setInterval(refreshDevices, 5000)
    return () => clearInterval(t)
  }, [refreshDevices])

  useEffect(() => {
    let ws, retry, closed = false
    const open = () => {
      ws = new WebSocket(`${location.protocol === 'https:' ? 'wss' : 'ws'}://${location.host}/ws`)
      let ka
      ws.onopen = () => {
        setConnected(true)
        ka = setInterval(() => ws.readyState === 1 && ws.send('ping'), 20000) // keep proxies from idling us out
      }
      ws.onclose = () => {
        clearInterval(ka)
        setConnected(false)
        if (!closed) retry = setTimeout(open, 2000)
      }
      ws.onmessage = (m) => {
        try {
          const msg = JSON.parse(m.data)
          if (msg.event === 'device') refreshDevices()
          listeners.current.forEach((fn) => fn(msg))
        } catch { /* ignore malformed */ }
      }
    }
    open()
    return () => { closed = true; clearTimeout(retry); ws && ws.close() }
  }, [refreshDevices])

  const device = devices.find((d) => d.online) || devices[0] || null
  return <Ctx.Provider value={{ connected, devices, device, model, subscribe, refreshDevices }}>{children}</Ctx.Provider>
}
