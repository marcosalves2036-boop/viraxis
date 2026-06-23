'use client'
import { useState, useEffect, useCallback } from 'react'
import { useRouter, useParams } from 'next/navigation'
import { offices, type OfficeResponse, type DecisionResponse } from '@/lib/api'

const statusColors: Record<string, string> = {
  pending:   'bg-yellow-900/50 text-yellow-300 border-yellow-800',
  approved:  'bg-blue-900/50 text-blue-300 border-blue-800',
  executing: 'bg-purple-900/50 text-purple-300 border-purple-800',
  done:      'bg-green-900/50 text-green-300 border-green-800',
  rejected:  'bg-red-900/50 text-red-300 border-red-800',
}

const statusLabel: Record<string, string> = {
  pending:   'Aguardando aprovação',
  approved:  'Aprovada',
  executing: 'Gerando roteiro...',
  done:      'Concluída',
  rejected:  'Rejeitada',
}

export default function OfficePage() {
  const router   = useRouter()
  const params   = useParams()
  const officeId = params.officeId as string

  const [office, setOffice]         = useState<OfficeResponse | null>(null)
  const [decisions, setDecisions]   = useState<DecisionResponse[]>([])
  const [loading, setLoading]       = useState(true)
  const [runningBrain, setRunning]  = useState(false)
  const [brainResult, setBrainResult] = useState<string>('')
  const [scoutUrl, setScoutUrl]     = useState('')
  const [scoutLoading, setScoutLoading] = useState(false)
  const [error, setError]           = useState('')

  const load = useCallback(async () => {
    try {
      const [o, d] = await Promise.all([
        offices.get(officeId),
        offices.listDecisions(officeId),
      ])
      setOffice(o)
      setDecisions(d)
    } catch {
      router.replace('/dashboard')
    } finally {
      setLoading(false)
    }
  }, [officeId, router])

  useEffect(() => { load() }, [load])

  async function runBrain() {
    setRunning(true)
    setBrainResult('')
    setError('')
    try {
      const r = await offices.runBrain(officeId)
      setBrainResult(
        `✓ BRAIN decidiu: "${r.selected_topic}" para ${r.selected_platform} (confiança ${Math.round(r.confidence_score * 100)}%)`
      )
      await load()
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : 'Erro ao rodar BRAIN')
    } finally {
      setRunning(false)
    }
  }

  async function analyzeUrl(e: React.FormEvent) {
    e.preventDefault()
    setScoutLoading(true)
    setError('')
    try {
      await offices.analyzeUrl(officeId, scoutUrl)
      setScoutUrl('')
      setBrainResult('✓ Vídeo analisado pelo SCOUT — dados salvos para o BRAIN usar')
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : 'Erro ao analisar URL')
    } finally {
      setScoutLoading(false)
    }
  }

  if (loading) return (
    <div className="min-h-screen flex items-center justify-center text-gray-500">
      Carregando...
    </div>
  )

  return (
    <div className="min-h-screen">
      {/* Header */}
      <header className="border-b border-gray-800 bg-gray-950/80 backdrop-blur sticky top-0 z-10">
        <div className="max-w-5xl mx-auto px-4 h-14 flex items-center gap-3">
          <button onClick={() => router.push('/dashboard')}
            className="text-gray-500 hover:text-gray-300 transition-colors">
            <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M15 19l-7-7 7-7" />
            </svg>
          </button>
          <div className="w-px h-4 bg-gray-700" />
          <span className="font-semibold text-white">{office?.name}</span>
          {office?.niche_profile && (
            <span className="text-gray-500 text-sm">— {office.niche_profile.niche_name}</span>
          )}
        </div>
      </header>

      <main className="max-w-5xl mx-auto px-4 py-8 space-y-6">

        {/* Navegação rápida */}
        <div className="flex gap-2 flex-wrap">
          <Link
            href={`/dashboard/${officeId}/videos`}
            className="btn-outline text-sm px-4 py-2 flex items-center gap-2"
          >
            <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5}
                d="M15 10l4.553-2.069A1 1 0 0121 8.87v6.26a1 1 0 01-1.447.894L15 14M5 18h8a2 2 0 002-2V8a2 2 0 00-2-2H5a2 2 0 00-2 2v8a2 2 0 002 2z" />
            </svg>
            Biblioteca de Vídeos
          </Link>
        </div>

        {/* SCOUT — analisar vídeo viral */}
        <div className="card">
          <div className="flex items-center gap-3 mb-4">
            <div className="w-9 h-9 rounded-xl bg-cyan-900/50 flex items-center justify-center">
              <svg className="w-5 h-5 text-cyan-400" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2}
                  d="M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0z" />
              </svg>
            </div>
            <div>
              <h3 className="font-semibold text-white">SCOUT — Analisar vídeo viral</h3>
              <p className="text-gray-500 text-xs">Cole uma URL do YouTube para o agente extrair padrões virais</p>
            </div>
          </div>
          <form onSubmit={analyzeUrl} className="flex gap-2">
            <input
              value={scoutUrl} onChange={e => setScoutUrl(e.target.value)}
              placeholder="https://youtube.com/watch?v=..."
              className="input flex-1" required
            />
            <button type="submit" disabled={scoutLoading} className="btn-outline whitespace-nowrap">
              {scoutLoading ? 'Analisando...' : 'Analisar'}
            </button>
          </form>
        </div>

        {/* BRAIN — gerar decisão */}
        <div className="card">
          <div className="flex items-start justify-between">
            <div className="flex items-center gap-3">
              <div className="w-9 h-9 rounded-xl bg-brand-500/20 flex items-center justify-center">
                <svg className="w-5 h-5 text-brand-500" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2}
                    d="M9.663 17h4.673M12 3v1m6.364 1.636l-.707.707M21 12h-1M4 12H3m3.343-5.657l-.707-.707m2.828 9.9a5 5 0 117.072 0l-.548.547A3.374 3.374 0 0014 18.469V19a2 2 0 11-4 0v-.531c0-.895-.356-1.754-.988-2.386l-.548-.547z" />
                </svg>
              </div>
              <div>
                <h3 className="font-semibold text-white">BRAIN — Decidir próximo vídeo</h3>
                <p className="text-gray-500 text-xs">O agente analisa o nicho e decide tema, plataforma e arquétipo</p>
              </div>
            </div>
            <button
              onClick={runBrain}
              disabled={runningBrain}
              className="btn-primary"
            >
              {runningBrain ? (
                <>
                  <svg className="w-4 h-4 animate-spin" fill="none" viewBox="0 0 24 24">
                    <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4"/>
                    <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8v8z"/>
                  </svg>
                  Pensando...
                </>
              ) : 'Rodar BRAIN'}
            </button>
          </div>
          {brainResult && (
            <p className="mt-3 text-sm text-green-400 bg-green-900/20 border border-green-900 rounded-lg px-3 py-2">
              {brainResult}
            </p>
          )}
          {error && (
            <p className="mt-3 text-sm text-red-400 bg-red-900/20 border border-red-900 rounded-lg px-3 py-2">
              {error}
            </p>
          )}
        </div>

        {/* Decisões */}
        <div>
          <h3 className="font-semibold text-white mb-3">
            Decisões do BRAIN
            <span className="text-gray-500 font-normal text-sm ml-2">({decisions.length})</span>
          </h3>

          {decisions.length === 0 ? (
            <div className="card text-center py-8 text-gray-500 text-sm">
              Rode o BRAIN para gerar a primeira decisão
            </div>
          ) : (
            <div className="space-y-3">
              {decisions.map(d => (
                <button
                  key={d.id}
                  onClick={() => router.push(`/dashboard/${officeId}/decisions/${d.id}`)}
                  className="card w-full text-left hover:border-gray-600 hover:bg-gray-800/50 transition-all group"
                >
                  <div className="flex items-start justify-between gap-4">
                    <div className="flex-1 min-w-0">
                      <div className="flex items-center gap-2 mb-1">
                        <span className="text-xs text-gray-500 font-mono uppercase">{d.decision_type}</span>
                        <span className="text-gray-700">·</span>
                        <span className="text-xs text-gray-500">{d.selected_platform}</span>
                      </div>
                      <p className="font-medium text-white group-hover:text-brand-400 transition-colors truncate">
                        {d.selected_topic}
                      </p>
                      <p className="text-gray-400 text-sm mt-1 line-clamp-2">{d.hypothesis}</p>
                    </div>
                    <div className="flex flex-col items-end gap-2 shrink-0">
                      <span className={`badge border text-xs ${statusColors[d.status] ?? 'bg-gray-800 text-gray-400 border-gray-700'}`}>
                        {statusLabel[d.status] ?? d.status}
                      </span>
                      <span className="text-gray-600 text-xs">
                        {Math.round(d.confidence_score * 100)}% confiança
                      </span>
                    </div>
                  </div>
                </button>
              ))}
            </div>
          )}
        </div>
      </main>
    </div>
  )
}
