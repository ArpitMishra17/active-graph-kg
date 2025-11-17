import { create } from 'zustand'
import { persist } from 'zustand/middleware'

export interface JWTClaims {
  sub: string
  tenant_id: string
  scopes: string[]
  email?: string
  name?: string
  iat: number
  exp: number
  aud: string
  iss: string
}

interface AuthState {
  token: string | null
  claims: JWTClaims | null
  isAuthenticated: boolean
  setToken: (token: string) => void
  logout: () => void
  parseToken: (token: string) => JWTClaims | null
}

// Helper to decode JWT without validation (validation happens on backend)
const decodeJWT = (token: string): JWTClaims | null => {
  try {
    const parts = token.split('.')
    if (parts.length !== 3) {
      return null
    }
    const payload = parts[1]
    const decoded = JSON.parse(atob(payload.replace(/-/g, '+').replace(/_/g, '/')))
    return decoded as JWTClaims
  } catch {
    return null
  }
}

export const useAuthStore = create<AuthState>()(
  persist(
    (set, get) => ({
      token: null,
      claims: null,
      isAuthenticated: false,

      setToken: (token: string) => {
        // Sanitize: remove all whitespace (newlines, spaces, tabs)
        const cleanToken = token.replace(/\s/g, '').trim()

        // Validate: JWT format must be header.payload.signature
        const JWT_REGEX = /^[A-Za-z0-9-_]+\.[A-Za-z0-9-_]+\.[A-Za-z0-9-_]+$/
        if (!JWT_REGEX.test(cleanToken)) {
          console.error('Invalid JWT format: token must be header.payload.signature')
          return
        }

        const claims = decodeJWT(cleanToken)
        if (!claims) {
          console.error('Failed to decode JWT token')
          return
        }

        // Check if token is expired
        const now = Math.floor(Date.now() / 1000)
        if (claims.exp < now) {
          console.error('JWT token is expired')
          return
        }

        set({
          token: cleanToken,
          claims,
          isAuthenticated: true,
        })
      },

      logout: () => {
        set({
          token: null,
          claims: null,
          isAuthenticated: false,
        })
      },

      parseToken: (token: string) => {
        return decodeJWT(token)
      },
    }),
    {
      name: 'auth-storage',
      // Don't persist sensitive data in localStorage in production
      // This is just for dev - production should use httpOnly cookies
      partialize: (state) => ({
        token: state.token,
        claims: state.claims,
        isAuthenticated: state.isAuthenticated,
      }),
    }
  )
)
