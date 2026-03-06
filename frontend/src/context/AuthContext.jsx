import { createContext, useContext, useState, useEffect } from 'react'

const AuthContext = createContext(null)

export function AuthProvider({ children }) {
  const user = { email: 'local', name: 'Local' }
  const loading = false

  function authHeaders() { return {} }
  function login() {}
  function logout() {}

  return (
    <AuthContext.Provider value={{ user, token: null, login, logout, authHeaders, loading }}>
      {children}
    </AuthContext.Provider>
  )
}

export function useAuth() {
  return useContext(AuthContext)
}
