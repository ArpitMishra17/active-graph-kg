import { create } from 'zustand'

interface RateLimitState {
  limit: number | null
  remaining: number | null
  reset: string | null
  isWarning: boolean
  setRateLimit: (remaining: number, limit: number, reset: string) => void
  clear: () => void
}

export const useRateLimitStore = create<RateLimitState>((set) => ({
  limit: null,
  remaining: null,
  reset: null,
  isWarning: false,

  setRateLimit: (remaining: number, limit: number, reset: string) => {
    set({
      limit,
      remaining,
      reset,
      // Warn when remaining < 5
      isWarning: remaining < 5,
    })
  },

  clear: () => {
    set({
      limit: null,
      remaining: null,
      reset: null,
      isWarning: false,
    })
  },
}))
