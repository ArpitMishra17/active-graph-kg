import { useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import apiClient from '../lib/api/client'
import { useRateLimitStore } from '../lib/stores/rateLimitStore'
import { cn } from '../lib/utils/cn'

interface Node {
  id: string
  classes: string[]
  props: {
    text?: string
    [key: string]: unknown
  }
  embedding?: number[]
}

// API returns array directly, not wrapped in object
type NodesResponse = Node[]

export default function Nodes() {
  const [page, setPage] = useState(1)
  const [limit] = useState(20)
  const [isCreating, setIsCreating] = useState(false)
  const [editingId, setEditingId] = useState<string | null>(null)
  const [deleteConfirmId, setDeleteConfirmId] = useState<string | null>(null)
  const [newNodeText, setNewNodeText] = useState('')
  const [newNodeClasses, setNewNodeClasses] = useState('Document')
  const [editNodeText, setEditNodeText] = useState('')

  const queryClient = useQueryClient()
  const { remaining, limit: rateLimit, isWarning } = useRateLimitStore()

  // Fetch nodes
  const nodesQuery = useQuery({
    queryKey: ['nodes', page, limit],
    queryFn: async () => {
      const { data } = await apiClient.get<NodesResponse>('/nodes', {
        params: { page, limit },
      })
      return data
    },
  })

  // Create node mutation
  const createMutation = useMutation({
    mutationFn: async (nodeData: { text: string; classes: string[] }) => {
      const { data } = await apiClient.post<Node>('/nodes', {
        classes: nodeData.classes,
        props: { text: nodeData.text },
      })
      return data
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['nodes'] })
      setIsCreating(false)
      setNewNodeText('')
      setNewNodeClasses('Document')
    },
  })

  // Update node mutation
  const updateMutation = useMutation({
    mutationFn: async ({ id, text }: { id: string; text: string }) => {
      const { data } = await apiClient.put<Node>(`/nodes/${id}`, {
        props: { text },
      })
      return data
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['nodes'] })
      setEditingId(null)
      setEditNodeText('')
    },
  })

  // Delete node mutation
  const deleteMutation = useMutation({
    mutationFn: async (id: string) => {
      await apiClient.delete(`/nodes/${id}`, {
        params: { hard: true },
      })
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['nodes'] })
      setDeleteConfirmId(null)
    },
  })

  const handleCreateNode = (e: React.FormEvent) => {
    e.preventDefault()
    if (!newNodeText.trim()) return

    createMutation.mutate({
      text: newNodeText.trim(),
      classes: newNodeClasses.split(',').map((c) => c.trim()).filter(Boolean),
    })
  }

  const handleUpdateNode = (id: string) => {
    if (!editNodeText.trim()) return
    updateMutation.mutate({ id, text: editNodeText.trim() })
  }

  const handleDeleteNode = (id: string) => {
    deleteMutation.mutate(id)
  }

  const startEdit = (node: Node) => {
    setEditingId(node.id)
    setEditNodeText(node.props.text || '')
  }

  const cancelEdit = () => {
    setEditingId(null)
    setEditNodeText('')
  }

  const totalPages = nodesQuery.data ? Math.ceil(nodesQuery.data.length / limit) : 1

  return (
    <div className="min-h-screen bg-gray-50 py-8">
      <div className="max-w-7xl mx-auto px-4">
        {/* Header */}
        <div className="mb-8 flex items-center justify-between">
          <div>
            <h1 className="text-3xl font-bold text-gray-900 mb-2">Nodes</h1>
            <p className="text-gray-600">
              Manage nodes in your knowledge graph
              {nodesQuery.data && ` (${nodesQuery.data.length} total)`}
            </p>
          </div>

          <button
            data-testid="node-create"
            onClick={() => setIsCreating(true)}
            disabled={isCreating}
            className="px-4 py-2 bg-blue-600 text-white rounded-md hover:bg-blue-700 disabled:bg-gray-300 disabled:cursor-not-allowed transition-colors"
          >
            Create Node
          </button>
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

        {/* Create Form */}
        {isCreating && (
          <div className="bg-white rounded-lg shadow-sm p-6 mb-6">
            <h2 className="text-lg font-semibold text-gray-900 mb-4">Create New Node</h2>
            <form onSubmit={handleCreateNode}>
              <div className="space-y-4">
                <div>
                  <label htmlFor="node-text-input" className="block text-sm font-medium text-gray-700 mb-2">
                    Text Content
                  </label>
                  <textarea
                    id="node-text-input"
                    data-testid="node-text"
                    rows={4}
                    value={newNodeText}
                    onChange={(e) => setNewNodeText(e.target.value)}
                    placeholder="Enter node text content..."
                    className="w-full px-3 py-2 border border-gray-300 rounded-md focus:ring-2 focus:ring-blue-500 focus:border-transparent"
                  />
                </div>

                <div>
                  <label htmlFor="node-classes" className="block text-sm font-medium text-gray-700 mb-2">
                    Classes (comma-separated)
                  </label>
                  <input
                    id="node-classes"
                    type="text"
                    value={newNodeClasses}
                    onChange={(e) => setNewNodeClasses(e.target.value)}
                    placeholder="Document, Code, Data"
                    className="w-full px-3 py-2 border border-gray-300 rounded-md focus:ring-2 focus:ring-blue-500 focus:border-transparent"
                  />
                </div>

                <div className="flex gap-2">
                  <button
                    type="submit"
                    data-testid="node-save"
                    disabled={!newNodeText.trim() || createMutation.isPending}
                    className="px-4 py-2 bg-blue-600 text-white rounded-md hover:bg-blue-700 disabled:bg-gray-300 disabled:cursor-not-allowed transition-colors"
                  >
                    {createMutation.isPending ? 'Creating...' : 'Create Node'}
                  </button>
                  <button
                    type="button"
                    onClick={() => {
                      setIsCreating(false)
                      setNewNodeText('')
                      setNewNodeClasses('Document')
                    }}
                    className="px-4 py-2 bg-gray-200 text-gray-700 rounded-md hover:bg-gray-300 transition-colors"
                  >
                    Cancel
                  </button>
                </div>

                {createMutation.isError && (
                  <div className="text-sm text-red-600">
                    Failed to create node. Please try again.
                  </div>
                )}
              </div>
            </form>
          </div>
        )}

        {/* Nodes List */}
        {nodesQuery.isLoading ? (
          <div className="bg-white rounded-lg shadow-sm p-12 text-center">
            <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-blue-600 mx-auto"></div>
            <p className="text-gray-600 mt-4">Loading nodes...</p>
          </div>
        ) : nodesQuery.isError ? (
          <div className="bg-red-50 border border-red-200 rounded-lg p-4">
            <p className="text-red-800 font-medium">Error loading nodes</p>
            <p className="text-red-600 text-sm mt-1">
              Failed to fetch nodes. Please try again.
            </p>
          </div>
        ) : nodesQuery.data?.length === 0 ? (
          <div className="bg-white rounded-lg shadow-sm p-12 text-center">
            <p className="text-gray-600">No nodes found. Create your first node to get started.</p>
          </div>
        ) : (
          <div className="bg-white rounded-lg shadow-sm overflow-hidden">
            <div className="divide-y divide-gray-200">
              {nodesQuery.data?.map((node) => (
                <div
                  key={node.id}
                  data-testid="node-row"
                  className="p-6 hover:bg-gray-50 transition-colors"
                >
                  {/* Edit Mode */}
                  {editingId === node.id ? (
                    <div>
                      <div className="mb-4">
                        <label className="block text-sm font-medium text-gray-700 mb-2">
                          Edit Text
                        </label>
                        <textarea
                          data-testid="node-text"
                          rows={4}
                          value={editNodeText}
                          onChange={(e) => setEditNodeText(e.target.value)}
                          className="w-full px-3 py-2 border border-gray-300 rounded-md focus:ring-2 focus:ring-blue-500 focus:border-transparent"
                        />
                      </div>
                      <div className="flex gap-2">
                        <button
                          data-testid="node-save"
                          onClick={() => handleUpdateNode(node.id)}
                          disabled={!editNodeText.trim() || updateMutation.isPending}
                          className="px-4 py-2 bg-blue-600 text-white rounded-md hover:bg-blue-700 disabled:bg-gray-300 disabled:cursor-not-allowed transition-colors text-sm"
                        >
                          {updateMutation.isPending ? 'Saving...' : 'Save'}
                        </button>
                        <button
                          onClick={cancelEdit}
                          className="px-4 py-2 bg-gray-200 text-gray-700 rounded-md hover:bg-gray-300 transition-colors text-sm"
                        >
                          Cancel
                        </button>
                      </div>
                    </div>
                  ) : (
                    <>
                      {/* View Mode */}
                      <div className="flex items-start justify-between mb-3">
                        <div className="flex items-center gap-2">
                          <code className="text-xs font-mono text-gray-500 bg-gray-100 px-2 py-1 rounded">
                            {node.id}
                          </code>
                          {node.classes.map((cls) => (
                            <span
                              key={cls}
                              className="text-xs font-medium text-blue-700 bg-blue-100 px-2 py-1 rounded"
                            >
                              {cls}
                            </span>
                          ))}
                        </div>
                      </div>

                      {node.props.text && (
                        <p className="text-gray-700 text-sm leading-relaxed mb-4">
                          {typeof node.props.text === 'string'
                            ? node.props.text
                            : String(node.props.text)}
                        </p>
                      )}

                      <div className="flex gap-2">
                        <button
                          onClick={() => startEdit(node)}
                          className="text-sm text-blue-600 hover:text-blue-700 font-medium"
                        >
                          Edit
                        </button>
                        <button
                          onClick={() => navigator.clipboard.writeText(node.id)}
                          className="text-sm text-gray-600 hover:text-gray-700 font-medium"
                        >
                          Copy ID
                        </button>
                        <button
                          data-testid="node-delete"
                          onClick={() => setDeleteConfirmId(node.id)}
                          className="text-sm text-red-600 hover:text-red-700 font-medium"
                        >
                          Delete
                        </button>
                      </div>
                    </>
                  )}

                  {/* Delete Confirmation */}
                  {deleteConfirmId === node.id && (
                    <div className="mt-4 p-4 bg-red-50 border border-red-200 rounded-md">
                      <p className="text-sm text-red-800 font-medium mb-3">
                        Are you sure you want to permanently delete this node?
                      </p>
                      <div className="flex gap-2">
                        <button
                          data-testid="confirm-delete"
                          onClick={() => handleDeleteNode(node.id)}
                          disabled={deleteMutation.isPending}
                          className="px-3 py-1 bg-red-600 text-white rounded text-sm hover:bg-red-700 disabled:bg-gray-300 disabled:cursor-not-allowed transition-colors"
                        >
                          {deleteMutation.isPending ? 'Deleting...' : 'Yes, Delete'}
                        </button>
                        <button
                          onClick={() => setDeleteConfirmId(null)}
                          className="px-3 py-1 bg-gray-200 text-gray-700 rounded text-sm hover:bg-gray-300 transition-colors"
                        >
                          Cancel
                        </button>
                      </div>
                    </div>
                  )}
                </div>
              ))}
            </div>

            {/* Pagination */}
            {totalPages > 1 && (
              <div className="px-6 py-4 border-t border-gray-200 flex items-center justify-between">
                <p className="text-sm text-gray-600">
                  Page {page} of {totalPages}
                </p>
                <div className="flex gap-2">
                  <button
                    onClick={() => setPage((p) => Math.max(1, p - 1))}
                    disabled={page === 1}
                    className="px-3 py-1 bg-gray-200 text-gray-700 rounded text-sm hover:bg-gray-300 disabled:bg-gray-100 disabled:cursor-not-allowed transition-colors"
                  >
                    Previous
                  </button>
                  <button
                    onClick={() => setPage((p) => Math.min(totalPages, p + 1))}
                    disabled={page === totalPages}
                    className="px-3 py-1 bg-gray-200 text-gray-700 rounded text-sm hover:bg-gray-300 disabled:bg-gray-100 disabled:cursor-not-allowed transition-colors"
                  >
                    Next
                  </button>
                </div>
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  )
}
