import { createContext, useContext, useEffect, useState } from 'react'
import api from './api'

const AuthContext = createContext(null)

export const RANK = { user: 1, admin: 2, superadmin: 3 }

// eslint-disable-next-line react-refresh/only-export-components
export const useAuth = () => useContext(AuthContext)

export function AuthProvider({ children }) {
  const [user, setUser] = useState(null)
  const [loading, setLoading] = useState(true)

  // Who am I? The server answers from the cookie (401 if not logged in).
  useEffect(() => {
    api.get('/auth/me')
      .then((r) => setUser(r.data))
      .catch(() => setUser(null))
      .finally(() => setLoading(false))
  }, [])

  // If the session expires while the dashboard is open, go back to the login page.
  useEffect(() => {
    const id = api.interceptors.response.use(
      (r) => r,
      (err) => {
        const url = err.config?.url || ''
        if (err.response?.status === 401 && !url.startsWith('/auth/')) setUser(null)
        return Promise.reject(err)
      },
    )
    return () => api.interceptors.response.eject(id)
  }, [])

  const login = async (username, password) => {
    const r = await api.post('/auth/login', { username, password })
    setUser(r.data)
  }

  const logout = async () => {
    try {
      await api.post('/auth/logout')
    } finally {
      setUser(null)
    }
  }

  // The server enforces permissions; this only decides what to show.
  const hasRole = (min) => Boolean(user) && RANK[user.role] >= RANK[min]

  return (
    <AuthContext.Provider value={{ user, loading, login, logout, hasRole }}>
      {children}
    </AuthContext.Provider>
  )
}
