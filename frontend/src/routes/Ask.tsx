import { useState, useRef, useEffect } from 'react'
import { streamSSE } from '../lib/api/client'
import { useRateLimitStore } from '../lib/stores/rateLimitStore'
import { cn } from '../lib/utils/cn'

interface Citation {
  node_id: string
  classes: string[]
  drift_score: number
  age_days: number
  lineage?: any[]
  similarity?: number
}

interface StreamChunk {
  type: string
  text?: string
  answer?: string
  node_ids?: string[]
  top_similarity?: number
  count?: number
  citations?: Citation[]
  confidence?: number
  metadata?: unknown
}

export default function Ask() {
  const [question, setQuestion] = useState('')
  const [answer, setAnswer] = useState('')
  const [citations, setCitations] = useState<Citation[]>([])
  const [confidence, setConfidence] = useState<number | null>(null)
  const [isStreaming, setIsStreaming] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const abortControllerRef = useRef<AbortController | null>(null)

  const { remaining, limit, isWarning } = useRateLimitStore()

  const handleAsk = async (e: React.FormEvent) => {
    e.preventDefault()

    if (!question.trim() || isStreaming) {
      return
    }

    // Reset state
    setAnswer('')
    setCitations([])
    setConfidence(null)
    setError(null)
    setIsStreaming(true)

    // Create abort controller
    abortControllerRef.current = new AbortController()

    try {
      await streamSSE('/ask/stream', {
        body: {
          question: question.trim(),
          stream: true,
        },
        signal: abortControllerRef.current.signal,
        onChunk: (data) => {
          try {
            const chunk: StreamChunk = JSON.parse(data)

            // Handle token events (streaming answer)
            if (chunk.type === 'token' && chunk.text) {
              setAnswer((prev) => prev + chunk.text)
            }

            // Handle final event (answer complete with citations)
            if (chunk.type === 'final') {
              if (chunk.answer) {
                setAnswer(chunk.answer)
              }
              if (chunk.citations) {
                setCitations(chunk.citations)
              }
              if (chunk.confidence !== undefined) {
                setConfidence(chunk.confidence)
              }
              setIsStreaming(false)
            }
          } catch (err) {
            // If not JSON, treat as plain text
            setAnswer((prev) => prev + data)
          }
        },
        onComplete: () => {
          setIsStreaming(false)
        },
        onError: (err) => {
          setError(err.message || 'Streaming error occurred')
          setIsStreaming(false)
        },
      })
    } catch (err: any) {
      if (err.name === 'AbortError') {
        setError('Request was cancelled')
      } else {
        setError(err.message || 'Failed to get answer')
      }
      setIsStreaming(false)
    }
  }

  const handleStop = () => {
    if (abortControllerRef.current) {
      abortControllerRef.current.abort()
      setIsStreaming(false)
    }
  }

  // Cleanup on unmount
  useEffect(() => {
    return () => {
      if (abortControllerRef.current) {
        abortControllerRef.current.abort()
      }
    }
  }, [])

  return (
    <div className="min-h-screen bg-gray-50 py-8">
      <div className="max-w-4xl mx-auto px-4">
        {/* Header */}
        <div className="mb-8">
          <h1 className="text-3xl font-bold text-gray-900 mb-2">Ask Questions</h1>
          <p className="text-gray-600">
            Ask questions about your knowledge graph and get streaming LLM-powered answers
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
            {remaining}/{limit} requests remaining
            {isWarning && ' - Warning: Low quota!'}
          </div>
        )}

        {/* Question Form */}
        <form onSubmit={handleAsk} className="bg-white rounded-lg shadow-sm p-6 mb-6">
          <div className="mb-4">
            <label htmlFor="ask-input" className="block text-sm font-medium text-gray-700 mb-2">
              Your Question
            </label>
            <div className="flex gap-2">
              <input
                id="ask-input"
                data-testid="ask-input"
                type="text"
                value={question}
                onChange={(e) => setQuestion(e.target.value)}
                placeholder="What is Active Graph KG?"
                className="flex-1 px-4 py-2 border border-gray-300 rounded-md focus:ring-2 focus:ring-blue-500 focus:border-transparent"
                disabled={isStreaming}
              />
              {!isStreaming ? (
                <button
                  type="submit"
                  data-testid="ask-submit"
                  disabled={!question.trim()}
                  className="px-6 py-2 bg-blue-600 text-white rounded-md hover:bg-blue-700 disabled:bg-gray-300 disabled:cursor-not-allowed transition-colors"
                >
                  Ask
                </button>
              ) : (
                <button
                  type="button"
                  onClick={handleStop}
                  className="px-6 py-2 bg-red-600 text-white rounded-md hover:bg-red-700 transition-colors"
                >
                  Stop
                </button>
              )}
            </div>
          </div>
        </form>

        {/* Error Display */}
        {error && (
          <div className="bg-red-50 border border-red-200 rounded-lg p-4 mb-6">
            <p className="text-red-800 font-medium">Error</p>
            <p className="text-red-600 text-sm mt-1">{error}</p>
          </div>
        )}

        {/* Answer Display */}
        {(answer || isStreaming) && (
          <div className="bg-white rounded-lg shadow-sm mb-6">
            {/* Answer Header */}
            <div className="px-6 py-4 border-b border-gray-200 flex items-center justify-between">
              <h2 className="text-lg font-semibold text-gray-900">Answer</h2>
              {isStreaming && (
                <div className="flex items-center gap-2 text-sm text-blue-600">
                  <div className="animate-pulse w-2 h-2 bg-blue-600 rounded-full"></div>
                  Streaming...
                </div>
              )}
              {confidence !== null && !isStreaming && (
                <div className="text-sm text-gray-600">
                  Confidence: {(confidence * 100).toFixed(0)}%
                </div>
              )}
            </div>

            {/* Answer Content */}
            <div
              data-testid="ask-answer"
              className="px-6 py-4 prose prose-sm max-w-none"
            >
              <div className="text-gray-700 leading-relaxed whitespace-pre-wrap">
                {answer}
                {isStreaming && <span className="animate-pulse">▊</span>}
              </div>
            </div>

            {/* Citations */}
            {citations.length > 0 && (
              <div className="px-6 py-4 border-t border-gray-200">
                <h3 className="text-sm font-semibold text-gray-900 mb-3">
                  Citations ({citations.length})
                </h3>
                <div className="space-y-2">
                  {citations.map((citation, idx) => (
                    <div
                      key={citation.node_id}
                      className="bg-gray-50 rounded p-3 text-sm"
                    >
                      <div className="flex items-start justify-between mb-2">
                        <code className="text-xs font-mono text-gray-500 bg-gray-100 px-2 py-1 rounded">
                          {citation.node_id}
                        </code>
                        {citation.similarity !== undefined && (
                          <span className="text-xs text-gray-600">
                            {(citation.similarity * 100).toFixed(1)}% match
                          </span>
                        )}
                      </div>
                      <div className="flex flex-wrap gap-2 mb-2">
                        {citation.classes.map((cls) => (
                          <span
                            key={cls}
                            className="text-xs font-medium text-blue-700 bg-blue-100 px-2 py-1 rounded"
                          >
                            {cls}
                          </span>
                        ))}
                      </div>
                      <div className="flex gap-4 text-xs text-gray-600">
                        <span>Age: {citation.age_days.toFixed(1)} days</span>
                        <span>Drift: {(citation.drift_score * 100).toFixed(1)}%</span>
                      </div>
                    </div>
                  ))}
                </div>
              </div>
            )}
          </div>
        )}

        {/* Empty State */}
        {!answer && !isStreaming && !error && (
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
                d="M8.228 9c.549-1.165 2.03-2 3.772-2 2.21 0 4 1.343 4 3 0 1.4-1.278 2.575-3.006 2.907-.542.104-.994.54-.994 1.093m0 3h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z"
              />
            </svg>
            <h3 className="mt-2 text-sm font-medium text-gray-900">No question asked</h3>
            <p className="mt-1 text-sm text-gray-500">
              Enter a question above to get streaming answers from your knowledge graph.
            </p>
          </div>
        )}

        {/* Example Questions */}
        <div className="mt-6">
          <h3 className="text-sm font-medium text-gray-700 mb-2">Example Questions</h3>
          <div className="flex flex-wrap gap-2">
            {[
              'What is Active Graph KG?',
              'How does hybrid search work?',
              'What connectors are supported?',
              'Explain row-level security',
            ].map((example) => (
              <button
                key={example}
                onClick={() => setQuestion(example)}
                disabled={isStreaming}
                className="px-3 py-1 text-sm bg-gray-100 text-gray-700 rounded-full hover:bg-gray-200 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
              >
                {example}
              </button>
            ))}
          </div>
        </div>
      </div>
    </div>
  )
}
