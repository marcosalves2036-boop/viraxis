'use client'
import { useState, useEffect, useCallback, useRef } from 'react'
import { useParams } from 'next/navigation'
import Link from 'next/link'

const BASE = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000'

function getToken() {
  if (typeof window === 'undefined') return null
  return localStorage.getItem('viraxis_token')
}

async function apiReq<T>(method: string, path: string, body?: unknown): Promise<T> {
  const headers: Record<string, string> = { 'Content-Type': 'application/json' }
  const token = getToken()
  if (token) headers['Authorization'] = `Bearer ${token}`
  const res = await fetch(`${BASE}${path}`, {
    method,
    headers,
    body: body ? JSON.stringify(body) : undefined,
  })
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: res.statusText }))
    throw new Error(err.detail ?? 'Erro desconhecido')
  }
  if (res.status === 204) return undefined as T
  return res.json()
}

interface RawVideo {
  id: string
  office_id: string
  original_filename: string
  r2_key: string
  r2_url: string | null
  file_size_bytes: number | null
  duration_seconds: number | null
  mime_type: string
  status: string
  title: string | null
  description: string | null
  tags: string[]
  created_at: string
}

function formatBytes(bytes: number | null) {
  if (!bytes) return '—'
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(0)} KB`
  return `${(bytes / 1024 / 1024).toFixed(1)} MB`
}

function formatDuration(seconds: number | null) {
  if (!seconds) return '—'
  const m = Math.floor(seconds / 60)
  const s = Math.floor(seconds % 60)
  return `${m}:${s.toString().padStart(2, '0')}`
}

const statusBadge: Record<string, string> = {
  ready:      'bg-green-900/50 text-green-300 border-green-800',
  pending:    'bg-yellow-900/50 text-yellow-300 border-yellow-800',
  processing: 'bg-blue-900/50 text-blue-300 border-blue-800',
  failed:     'bg-red-900/50 text-red-300 border-red-800',
}

export default function VideosPage() {
  const params   = useParams()
  const officeId = params.officeId as string

  const [videos, setVideos]     = useState<RawVideo[]>([])
  const [loading, setLoading]   = useState(true)
  const [uploading, setUploading] = useState(false)
  const [uploadProgress, setUploadProgress] = useState(0)
  const [error, setError]       = useState('')
  const [success, setSuccess]   = useState('')
  const fileRef = useRef<HTMLInputElement>(null)

  const load = useCallback(async () => {
    try {
      const data = await apiReq<RawVideo[]>('GET', `/raw-videos?office_id=${officeId}`)
      setVideos(data)
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : 'Erro ao carregar vídeos')
    } finally {
      setLoading(false)
    }
  }, [officeId])

  useEffect(() => { load() }, [load])

  async function handleFileChange(e: React.ChangeEvent<HTMLInputElement>) {
    const file = e.target.files?.[0]
    if (!file) return

    setError('')
    setSuccess('')
    setUploading(true)
    setUploadProgress(0)

    try {
      // 1. Obter presigned URL
      const presign = await apiReq<{ upload_url: string; r2_key: string }>(
        'POST', '/raw-videos/presign',
        {
          office_id: officeId,
          filename: file.name,
          mime_type: file.type || 'video/mp4',
          file_size_bytes: file.size,
        }
      )

      // 2. Upload direto para R2 via presigned URL
      setUploadProgress(10)
      const uploadRes = await fetch(presign.upload_url, {
        method: 'PUT',
        body: file,
        headers: { 'Content-Type': file.type || 'video/mp4' },
      })

      if (!uploadRes.ok) {
        throw new Error('Falha no upload para o armazenamento. Tente novamente.')
      }
      setUploadProgress(80)

      // 3. Registrar metadados no backend
      await apiReq<RawVideo>('POST', '/raw-videos', {
        office_id: officeId,
        r2_key: presign.r2_key,
        original_filename: file.name,
        mime_type: file.type || 'video/mp4',
        file_size_bytes: file.size,
        title: file.name.replace(/\.[^.]+$/, ''),
      })

      setUploadProgress(100)
      setSuccess(`"${file.name}" enviado com sucesso!`)
      await load()
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : 'Erro no upload')
    } finally {
      setUploading(false)
      setUploadProgress(0)
      if (fileRef.current) fileRef.current.value = ''
    }
  }

  async function handleDelete(video: RawVideo) {
    if (!confirm(`Remover "${video.title || video.original_filename}"?`)) return
    try {
      await apiReq('DELETE', `/raw-videos/${video.id}`)
      setVideos(prev => prev.filter(v => v.id !== video.id))
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : 'Erro ao remover')
    }
  }

  return (
    <div className="min-h-screen bg-gray-950 text-white p-6">
      <div className="max-w-5xl mx-auto">

        {/* Header */}
        <div className="flex items-center justify-between mb-8">
          <div>
            <Link href={`/dashboard/${officeId}`} className="text-gray-400 hover:text-white text-sm mb-2 inline-block">
              ← Voltar ao escritório
            </Link>
            <h1 className="text-2xl font-bold">Biblioteca de Vídeos</h1>
            <p className="text-gray-400 text-sm mt-1">
              Clips brutos que o BRAIN pode usar para gerar conteúdo
            </p>
          </div>

          {/* Upload button */}
          <div>
            <input
              ref={fileRef}
              type="file"
              accept="video/*"
              onChange={handleFileChange}
              className="hidden"
              id="video-upload"
            />
            <label
              htmlFor="video-upload"
              className={`btn-primary px-5 py-2.5 cursor-pointer inline-flex items-center gap-2 ${
                uploading ? 'opacity-50 cursor-not-allowed pointer-events-none' : ''
              }`}
            >
              <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2}
                  d="M4 16v1a3 3 0 003 3h10a3 3 0 003-3v-1m-4-8l-4-4m0 0L8 8m4-4v12" />
              </svg>
              {uploading ? `Enviando... ${uploadProgress}%` : 'Upload de vídeo'}
            </label>
          </div>
        </div>

        {/* Progress bar */}
        {uploading && (
          <div className="mb-4">
            <div className="w-full bg-gray-800 rounded-full h-2">
              <div
                className="bg-brand-500 h-2 rounded-full transition-all duration-300"
                style={{ width: `${uploadProgress}%` }}
              />
            </div>
          </div>
        )}

        {/* Alerts */}
        {error && (
          <div className="mb-4 p-3 bg-red-900/30 border border-red-800 rounded-lg text-red-400 text-sm">
            {error}
          </div>
        )}
        {success && (
          <div className="mb-4 p-3 bg-green-900/30 border border-green-800 rounded-lg text-green-400 text-sm">
            {success}
          </div>
        )}

        {/* Video list */}
        {loading ? (
          <div className="text-center py-16 text-gray-500">Carregando...</div>
        ) : videos.length === 0 ? (
          <div className="text-center py-16">
            <div className="inline-flex items-center justify-center w-16 h-16 rounded-full bg-gray-800 mb-4">
              <svg className="w-8 h-8 text-gray-500" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5}
                  d="M15 10l4.553-2.069A1 1 0 0121 8.87v6.26a1 1 0 01-1.447.894L15 14M5 18h8a2 2 0 002-2V8a2 2 0 00-2-2H5a2 2 0 00-2 2v8a2 2 0 002 2z" />
              </svg>
            </div>
            <p className="text-gray-400 text-sm">Nenhum vídeo ainda.</p>
            <p className="text-gray-600 text-xs mt-1">Faça upload de clips para o BRAIN usar como referência.</p>
          </div>
        ) : (
          <div className="space-y-3">
            {videos.map(video => (
              <div key={video.id} className="card flex items-center gap-4">
                {/* Icon */}
                <div className="flex-shrink-0 w-12 h-12 rounded-lg bg-gray-800 flex items-center justify-center">
                  <svg className="w-6 h-6 text-brand-400" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5}
                      d="M15 10l4.553-2.069A1 1 0 0121 8.87v6.26a1 1 0 01-1.447.894L15 14M5 18h8a2 2 0 002-2V8a2 2 0 00-2-2H5a2 2 0 00-2 2v8a2 2 0 002 2z" />
                  </svg>
                </div>

                {/* Info */}
                <div className="flex-1 min-w-0">
                  <p className="font-medium text-white truncate">
                    {video.title || video.original_filename}
                  </p>
                  <p className="text-xs text-gray-500 mt-0.5">
                    {video.original_filename} · {formatBytes(video.file_size_bytes)} · {formatDuration(video.duration_seconds)}
                  </p>
                  {video.tags.length > 0 && (
                    <div className="flex gap-1 mt-1 flex-wrap">
                      {video.tags.map(tag => (
                        <span key={tag} className="text-xs bg-gray-800 text-gray-400 px-2 py-0.5 rounded">
                          {tag}
                        </span>
                      ))}
                    </div>
                  )}
                </div>

                {/* Status + Actions */}
                <div className="flex items-center gap-3 flex-shrink-0">
                  <span className={`text-xs px-2 py-1 rounded border ${statusBadge[video.status] ?? 'bg-gray-800 text-gray-400 border-gray-700'}`}>
                    {video.status}
                  </span>
                  <button
                    onClick={() => handleDelete(video)}
                    className="text-gray-500 hover:text-red-400 transition-colors p-1"
                    title="Remover"
                  >
                    <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2}
                        d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16" />
                    </svg>
                  </button>
                </div>
              </div>
            ))}
          </div>
        )}

        {/* Count */}
        {!loading && videos.length > 0 && (
          <p className="text-center text-gray-600 text-xs mt-6">
            {videos.length} vídeo{videos.length !== 1 ? 's' : ''} na biblioteca
          </p>
        )}
      </div>
    </div>
  )
}
