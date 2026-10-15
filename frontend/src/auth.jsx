import { createContext, useContext, useEffect, useState } from 'react'

import { api } from './api.js'

// Token + user kept in localStorage so a refresh stays signed in.
const AuthContext = createContext(null)

export function AuthProvider({ children }) {
  const [token, setToken] = useState(() => localStorage.getItem('jobrix_token'))
  const [user, setUser] = useState(() => {
    const raw = localStorage.getItem('jobrix_user')
    return raw ? JSON.parse(raw) : null
  })

  useEffect(() => {
    if (token) localStorage.setItem('jobrix_token', token)
    else localStorage.removeItem('jobrix_token')
    if (user) localStorage.setItem('jobrix_user', JSON.stringify(user))
    else localStorage.removeItem('jobrix_user')
  }, [token, user])

  const login = async (email, password) => {
    const data = await api.post('/api/accounts/login/', { email, password })
    setToken(data.token)
    setUser(data.user)
    return data.user
  }

  const register = async (payload) => {
    const data = await api.post('/api/accounts/register/', payload)
    setToken(data.token)
    setUser(data.user)
    return data.user
  }

  const logout = async () => {
    try {
      if (token) await api.post('/api/accounts/logout/')
    } catch {
      /* token already invalid - clearing locally is enough */
    }
    setToken(null)
    setUser(null)
  }

  const value = {
    token,
    user,
    login,
    register,
    logout,
    isSeeker: user?.role === 'job_seeker',
    isRecruiter: user?.role === 'recruiter',
    isAdmin: user?.role === 'admin',
  }
  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>
}

export function useAuth() {
  return useContext(AuthContext)
}
