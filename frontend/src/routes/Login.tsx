import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { useAuthStore } from '../lib/stores/authStore'

export default function Login() {
  const [token, setToken] = useState('')
  const [error, setError] = useState('')
  const { setToken: setAuthToken } = useAuthStore()
  const navigate = useNavigate()

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault()
    setError('')

    if (!token.trim()) {
      setError('Please enter a JWT token')
      return
    }

    try {
      // setToken will decode and validate the JWT
      setAuthToken(token.trim())
      // Navigate to dashboard on success
      navigate('/dashboard')
    } catch (err) {
      setError('Invalid or expired JWT token')
    }
  }

  return (
    <div className="min-h-screen flex items-center justify-center bg-gray-50 py-12 px-4 sm:px-6 lg:px-8">
      <div className="max-w-md w-full space-y-8">
        <div>
          <h1 className="text-center text-3xl font-bold text-gray-900">
            Active Graph KG
          </h1>
          <p className="mt-2 text-center text-sm text-gray-600">
            Sign in with your JWT token
          </p>
        </div>

        <form onSubmit={handleSubmit} className="mt-8 space-y-6">
          <div>
            <label htmlFor="token" className="block text-sm font-medium text-gray-700">
              JWT Token
            </label>
            <textarea
              id="token"
              name="token"
              rows={6}
              value={token}
              onChange={(e) => setToken(e.target.value)}
              className="mt-1 block w-full rounded-md border border-gray-300 shadow-sm focus:border-blue-500 focus:ring-blue-500 sm:text-sm p-3 font-mono text-xs"
              placeholder="eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9..."
            />
          </div>

          {error && (
            <div className="rounded-md bg-red-50 border border-red-200 p-3">
              <p className="text-sm text-red-800">{error}</p>
            </div>
          )}

          <button
            type="submit"
            className="w-full flex justify-center py-2 px-4 border border-transparent rounded-md shadow-sm text-sm font-medium text-white bg-blue-600 hover:bg-blue-700 focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-blue-500 disabled:bg-gray-300"
            disabled={!token.trim()}
          >
            Sign in
          </button>

          <div className="mt-4 text-xs text-gray-500">
            <p className="font-medium mb-1">For testing, use:</p>
            <code className="block bg-gray-100 p-2 rounded">
              python3 generate_test_jwt.py
            </code>
          </div>
        </form>
      </div>
    </div>
  )
}
