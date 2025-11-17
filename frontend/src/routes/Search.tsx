import { useState } from 'react'
import { useMutation } from '@tanstack/react-query'
import apiClient from '../lib/api/client'
import { useRateLimitStore } from '../lib/stores/rateLimitStore'
import { cn } from '../lib/utils/cn'

interface SearchResult {
  id: string
  similarity: number
  classes: string[]
  props: {
    text?: string
    [key: string]: unknown
  }
}

interface SearchResponse {
  results: SearchResult[]
}

export default function Search() {
  const [query, setQuery] = useState('')
  const [mode, setMode] = useState<'hybrid' | 'similarity' | 'bm25'>('hybrid')
  const [limit, setLimit] = useState(10)
  const [minScore, setMinScore] = useState(0.0)
  const [selectedClasses, setSelectedClasses] = useState<string[]>([])

  const { remaining, limit: rateLimit, isWarning } = useRateLimitStore()

  const searchMutation = useMutation({
    mutationFn: async (searchQuery: string) => {
      const payload: Record<string, unknown> = {
        query: searchQuery,
        mode,
        limit,
      }

      if (minScore > 0) {
        payload.min_similarity = minScore
      }

      if (selectedClasses.length > 0) {
        payload.classes = selectedClasses
      }

      const { data } = await apiClient.post<SearchResponse>('/search', payload)
      return data
    },
    onError: (error: any) => {
      console.error('Search error:', error)
      // Error handling is done by API client interceptor
    },
  })

  const handleSearch = (e: React.FormEvent) => {
    e.preventDefault()
    if (query.trim()) {
      searchMutation.mutate(query)
    }
  }

  const handleClassToggle = (className: string) => {
    setSelectedClasses((prev) =>
      prev.includes(className)
        ? prev.filter((c) => c !== className)
        : [...prev, className]
    )
  }

  const availableClasses = ['Document', 'Code', 'Data', 'Config', 'Schema']

  return (
    <div className="min-h-screen bg-gray-50 py-8">
      <div className="max-w-6xl mx-auto px-4">
        {/* Header */}
        <div className="mb-8">
          <h1 className="text-3xl font-bold text-gray-900 mb-2">Search Knowledge Graph</h1>
          <p className="text-gray-600">
            Hybrid search across nodes using vector similarity and text matching
          </p>
        </div>

        {/* Rate Limit Badge */}
        {remaining !== null && (
          <div
            className={cn(
              'mb-4 px-4 py-2 rounded-lg inline-block text-sm font-medium',
              isWarning
                ? 'bg-yellow-100 text-yellow-800 border border-yellow-300'
                : 'bg-blue-50 text-blue-700 border border-blue-200'
            )}
          >
            {remaining}/{rateLimit} requests remaining
            {isWarning && ' - Warning: Low quota!'}
          </div>
        )}

        {/* Search Form */}
        <form onSubmit={handleSearch} className="bg-white rounded-lg shadow-sm p-6 mb-6">
          {/* Query Input */}
          <div className="mb-4">
            <label htmlFor="search-input" className="block text-sm font-medium text-gray-700 mb-2">
              Search Query
            </label>
            <div className="flex gap-2">
              <input
                id="search-input"
                data-testid="search-input"
                type="text"
                value={query}
                onChange={(e) => setQuery(e.target.value)}
                placeholder="Enter your search query..."
                className="flex-1 px-4 py-2 border border-gray-300 rounded-md focus:ring-2 focus:ring-blue-500 focus:border-transparent"
              />
              <button
                type="submit"
                data-testid="search-submit"
                disabled={!query.trim() || searchMutation.isPending}
                className="px-6 py-2 bg-blue-600 text-white rounded-md hover:bg-blue-700 disabled:bg-gray-300 disabled:cursor-not-allowed transition-colors"
              >
                {searchMutation.isPending ? 'Searching...' : 'Search'}
              </button>
            </div>
          </div>

          {/* Filters */}
          <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
            {/* Mode Selector */}
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-2">
                Search Mode
              </label>
              <select
                value={mode}
                onChange={(e) => setMode(e.target.value as any)}
                className="w-full px-3 py-2 border border-gray-300 rounded-md focus:ring-2 focus:ring-blue-500"
              >
                <option value="hybrid">Hybrid (Vector + Text)</option>
                <option value="similarity">Similarity Only</option>
                <option value="bm25">Text Only (BM25)</option>
              </select>
            </div>

            {/* Limit */}
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-2">
                Results Limit
              </label>
              <input
                type="number"
                value={limit}
                onChange={(e) => setLimit(Number(e.target.value))}
                min={1}
                max={100}
                className="w-full px-3 py-2 border border-gray-300 rounded-md focus:ring-2 focus:ring-blue-500"
              />
            </div>

            {/* Min Score */}
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-2">
                Min Score (0-1)
              </label>
              <input
                type="number"
                value={minScore}
                onChange={(e) => setMinScore(Number(e.target.value))}
                min={0}
                max={1}
                step={0.1}
                className="w-full px-3 py-2 border border-gray-300 rounded-md focus:ring-2 focus:ring-blue-500"
              />
            </div>
          </div>

          {/* Class Filters */}
          <div className="mt-4">
            <label className="block text-sm font-medium text-gray-700 mb-2">
              Filter by Class
            </label>
            <div className="flex flex-wrap gap-2">
              {availableClasses.map((className) => (
                <button
                  key={className}
                  type="button"
                  onClick={() => handleClassToggle(className)}
                  className={cn(
                    'px-3 py-1 rounded-full text-sm font-medium transition-colors',
                    selectedClasses.includes(className)
                      ? 'bg-blue-600 text-white'
                      : 'bg-gray-100 text-gray-700 hover:bg-gray-200'
                  )}
                >
                  {className}
                </button>
              ))}
            </div>
          </div>
        </form>

        {/* Results */}
        {searchMutation.isError && (
          <div className="bg-red-50 border border-red-200 rounded-lg p-4 mb-6">
            <p className="text-red-800 font-medium">Search Error</p>
            <p className="text-red-600 text-sm mt-1">
              {(searchMutation.error as any)?.response?.data?.detail ||
                'Failed to perform search. Please try again.'}
            </p>
          </div>
        )}

        {searchMutation.isSuccess && (
          <div className="bg-white rounded-lg shadow-sm">
            {/* Results Header */}
            <div className="px-6 py-4 border-b border-gray-200">
              <h2 className="text-lg font-semibold text-gray-900">
                Search Results ({searchMutation.data.results.length})
              </h2>
            </div>

            {/* Results List */}
            {searchMutation.data.results.length === 0 ? (
              <div className="px-6 py-8 text-center text-gray-500">
                No results found. Try adjusting your search query or filters.
              </div>
            ) : (
              <div className="divide-y divide-gray-200">
                {searchMutation.data.results.map((result) => (
                  <div
                    key={result.id}
                    data-testid="search-result"
                    className="px-6 py-4 hover:bg-gray-50 transition-colors"
                  >
                    {/* Result Header */}
                    <div className="flex items-start justify-between mb-2">
                      <div className="flex items-center gap-2">
                        <code className="text-xs font-mono text-gray-500 bg-gray-100 px-2 py-1 rounded">
                          {result.id}
                        </code>
                        {result.classes.map((cls) => (
                          <span
                            key={cls}
                            className="text-xs font-medium text-blue-700 bg-blue-100 px-2 py-1 rounded"
                          >
                            {cls}
                          </span>
                        ))}
                      </div>
                      <div className="flex items-center gap-2">
                        <span
                          className={cn(
                            'text-sm font-medium px-2 py-1 rounded',
                            result.similarity >= 0.8
                              ? 'bg-green-100 text-green-800'
                              : result.similarity >= 0.6
                              ? 'bg-yellow-100 text-yellow-800'
                              : 'bg-gray-100 text-gray-700'
                          )}
                        >
                          {(result.similarity * 100).toFixed(1)}%
                        </span>
                      </div>
                    </div>

                    {/* Result Text */}
                    {result.props.text && (
                      <p className="text-gray-700 text-sm leading-relaxed">
                        {typeof result.props.text === 'string'
                          ? result.props.text.substring(0, 300)
                          : String(result.props.text).substring(0, 300)}
                        {((typeof result.props.text === 'string' ? result.props.text : String(result.props.text)).length > 300) && '...'}
                      </p>
                    )}

                    {/* Actions */}
                    <div className="mt-3 flex gap-2">
                      <button
                        onClick={() => navigator.clipboard.writeText(result.id)}
                        className="text-xs text-blue-600 hover:text-blue-700 font-medium"
                      >
                        Copy ID
                      </button>
                      <button className="text-xs text-gray-600 hover:text-gray-700 font-medium">
                        View Details
                      </button>
                    </div>
                  </div>
                ))}
              </div>
            )}
          </div>
        )}

        {/* Empty State */}
        {!searchMutation.data && !searchMutation.isError && !searchMutation.isPending && (
          <div className="bg-white rounded-lg shadow-sm px-6 py-12 text-center">
            <svg
              className="mx-auto h-12 w-12 text-gray-400"
              fill="none"
              viewBox="0 0 24 24"
              stroke="currentColor"
            >
              <path
                strokeLinecap="round"
                strokeLinejoin="round"
                strokeWidth={2}
                d="M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0z"
              />
            </svg>
            <h3 className="mt-2 text-sm font-medium text-gray-900">No search performed</h3>
            <p className="mt-1 text-sm text-gray-500">
              Enter a query above to search the knowledge graph.
            </p>
          </div>
        )}
      </div>
    </div>
  )
}
