import axios, { AxiosError, AxiosInstance, InternalAxiosRequestConfig } from 'axios'
import { useAuthStore } from '../stores/authStore'
import { useRateLimitStore } from '../stores/rateLimitStore'

// Create axios instance
export const apiClient: AxiosInstance = axios.create({
  baseURL: import.meta.env.VITE_API_URL || '',
  headers: {
    'Content-Type': 'application/json',
  },
  timeout: 30000, // 30 seconds
})

// JWT validation regex
const JWT_REGEX = /^[A-Za-z0-9-_]+\.[A-Za-z0-9-_]+\.[A-Za-z0-9-_]+$/

// Request interceptor: Add Authorization header
apiClient.interceptors.request.use(
  (config: InternalAxiosRequestConfig) => {
    const token = useAuthStore.getState().token

    if (token && config.headers) {
      // Sanitize: remove all whitespace (newlines, spaces, tabs)
      const cleanToken = token.replace(/\s/g, '').trim()

      // Validate: JWT format must be header.payload.signature
      if (!JWT_REGEX.test(cleanToken)) {
        console.error('Invalid JWT format in request interceptor')
        return config // Skip auth header if invalid
      }

      config.headers.Authorization = `Bearer ${cleanToken}`
    }

    return config
  },
  (error) => {
    return Promise.reject(error)
  }
)

// Response interceptor: Handle rate limiting and errors
apiClient.interceptors.response.use(
  (response) => {
    // Extract and store rate limit headers
    const remaining = response.headers['x-ratelimit-remaining']
    const limit = response.headers['x-ratelimit-limit']
    const reset = response.headers['x-ratelimit-reset']

    if (remaining && limit && reset) {
      useRateLimitStore.getState().setRateLimit(
        parseInt(remaining, 10),
        parseInt(limit, 10),
        reset
      )
    }

    return response
  },
  async (error: AxiosError) => {
    // Handle 401 Unauthorized
    if (error.response?.status === 401) {
      // Token expired or invalid - logout
      useAuthStore.getState().logout()
      window.location.href = '/login'
      return Promise.reject(error)
    }

    // Handle 403 Forbidden (missing scope)
    if (error.response?.status === 403) {
      // User doesn't have required scope
      // UI should display appropriate message
      return Promise.reject(error)
    }

    // Handle 429 Too Many Requests
    if (error.response?.status === 429) {
      const retryAfter = error.response.headers['retry-after']

      if (retryAfter && error.config) {
        // Wait for Retry-After seconds, then retry
        const delayMs = parseInt(retryAfter, 10) * 1000

        console.warn(`Rate limited. Retrying after ${retryAfter}s...`)

        await new Promise((resolve) => setTimeout(resolve, delayMs))

        // Retry the request
        return apiClient.request(error.config)
      }
    }

    return Promise.reject(error)
  }
)

// Helper for SSE streaming
export async function streamSSE(
  url: string,
  options: {
    body?: unknown
    onChunk: (data: string) => void
    onError?: (error: Error) => void
    onComplete?: () => void
    signal?: AbortSignal
  }
): Promise<void> {
  const token = useAuthStore.getState().token

  if (!token) {
    throw new Error('No authentication token available')
  }

  // Sanitize: remove all whitespace (newlines, spaces, tabs)
  const cleanToken = token.replace(/\s/g, '').trim()

  // Validate: JWT format must be header.payload.signature
  if (!JWT_REGEX.test(cleanToken)) {
    throw new Error('Invalid JWT format in SSE streaming')
  }

  const response = await fetch(
    `${import.meta.env.VITE_API_URL || ''}${url}`,
    {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        Authorization: `Bearer ${cleanToken}`,
      },
      body: options.body ? JSON.stringify(options.body) : undefined,
      signal: options.signal,
    }
  )

  if (!response.ok) {
    // Handle HTTP errors
    if (response.status === 401) {
      useAuthStore.getState().logout()
      window.location.href = '/login'
      throw new Error('Unauthorized')
    }

    if (response.status === 429) {
      const retryAfter = response.headers.get('retry-after')
      throw new Error(`Rate limited. Retry after ${retryAfter}s`)
    }

    throw new Error(`HTTP ${response.status}: ${response.statusText}`)
  }

  // Extract rate limit headers
  const remaining = response.headers.get('x-ratelimit-remaining')
  const limit = response.headers.get('x-ratelimit-limit')
  const reset = response.headers.get('x-ratelimit-reset')

  if (remaining && limit && reset) {
    useRateLimitStore.getState().setRateLimit(
      parseInt(remaining, 10),
      parseInt(limit, 10),
      reset
    )
  }

  // Stream the response
  const reader = response.body?.getReader()
  const decoder = new TextDecoder()

  if (!reader) {
    throw new Error('Response body is not readable')
  }

  try {
    while (true) {
      const { done, value } = await reader.read()

      if (done) {
        options.onComplete?.()
        break
      }

      const chunk = decoder.decode(value, { stream: true })
      const lines = chunk.split('\n')

      for (const line of lines) {
        if (line.startsWith('data: ')) {
          const data = line.slice(6) // Remove 'data: ' prefix
          if (data === '[DONE]') {
            options.onComplete?.()
            return
          }
          options.onChunk(data)
        }
      }
    }
  } catch (error) {
    if (error instanceof Error) {
      options.onError?.(error)
    }
    throw error
  } finally {
    reader.releaseLock()
  }
}

export default apiClient
