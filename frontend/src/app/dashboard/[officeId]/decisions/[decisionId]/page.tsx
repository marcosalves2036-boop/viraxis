'use client'
import { useState, useEffect, useCallback } from 'react'
import { useRouter, useParams } from 'next/navigation'
import { offices, type DecisionResponse } from '@/lib/api'

export default function DecisionPage() {
  const router     = useRouter()
  const params     = useParams()
  const officeId   = params.officeId as string
  const decisionId = params.decisionId as string

  const [decision, setDecision]     = useState<DecisionResponse | null>(null)
  const [loading, setLoading]       = useState(true)
  const [approving, setApproving]   = useState(false)
  const [rendering, setRendering]   = useState(false)
  const [error, setError]           = useState('')

  const load = useCallback(async () => {
    try {
      const d = await offices.getDecision(officeId, decisionId)
      setDecision(d)
    } catch {
      router.replace(`/dashboard/${officeId}`)
    } finally {
      setLoading(false)
    }
  }, [officeId, decisionId, router])

  useEffect(() => { load() }, [load])

  async function approve() {
    setApproving(true)
    setError('')
    try {
      const d = await offices.approveDecision(officeId, decisionId)
      setDecision(d)
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : 'Erro ao aprovar')
    } finally {
      setApproving(false)
    }
  }

  async function render() {
    setRendering(true)
    setError('')
    try {
      const r = await offices.renderDecision(officeId, decisionId)
      router.push(`/dashboard/${officeId}/content/${r.content_item_id}`)
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : 'Erro ao gerar roteiro')
      setRendering(false)
    }
  }

  if (loading || !decision) return (
    <div className="min-h-screen flex items-center justify-center text-gray-500">Carregando...</div>
  )

  const isPending  = decision.status === 'pending'
  const isApproved = decision.status === 'approved'
  const isDone     = decision.status === 'done'
  const isExecuting = decision.status === 'executing'

  return (
    <div className="min-h-screen">
      <header className="border-b border-gray-800 bg-gray-950/80 backdrop-blur sticky top-0 z-10">
        <div className="max-w-3xl mx-auto px-4 h-14 flex items-center gap-3">
          <button onClick={() => router.push(`/dashboard/${officeId}`)}
            className="text-gray-500 hover:text-gray-300 transition-colors">
            <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M15 19l-7-7 7-7" />
            </svg>
          </button>
          <div className="w-px h-4 bg-gray-700" />
          <span className="font-semibold text-white">Decisão do BRAIN</span>
        </div>
      </header>

      <main className="max-w-3xl mx-auto px-4 py-8 space-y-4">

        {/* Card principal da decisão */}
        <div className="card space-y-4">
          <div className="flex items-start justify-between gap-4">
            <div>
              <div className="flex items-center gap-2 mb-2">
                <span className="badge bg-brand-500/20 text-brand-400 border border-brand-500/30 text-xs uppercase">
                  {decision.decision_type}
                </span>
                <span className="text-gray-600 text-xs">{decision.selected_platform}</span>
              </div>
              <h2 className="text-lg font-bold text-white">{decision.selected_topic}</h2>
            </div>
            <div className="text-right shrink-0">
              <div className="text-2xl font-bold text-brand-400">
                {Math.round(decision.confidence_score * 100)}%
              </div>
              <div className="text-gray-500 text-xs">confiança</div>
            </div>
          </div>

          <div className="border-t border-gray-800 pt-4 grid grid-cols-1 sm:grid-cols-2 gap-4">
            <div>
              <p className="text-gray-500 text-xs mb-1">Arquétipo</p>
              <p className="text-white text-sm font-medium">{decision.selected_archetype}</p>
            </div>
            <div>
              <p className="text-gray-500 text-xs mb-1">Plataforma</p>
              <p className="text-white text-sm font-medium">{decision.selected_platform}</p>
            </div>
          </div>

          <div className="border-t border-gray-800 pt-4">
            <p className="text-gray-500 text-xs mb-2">Hipótese</p>
            <p className="text-gray-300 text-sm leading-relaxed">{decision.hypothesis}</p>
          </div>
        </div>

        {/* Ações */}
        {error && (
          <p className="text-red-400 text-sm bg-red-900/20 border border-red-900 rounded-lg px-3 py-2">
            {error}
          </p>
        )}

        {isPending && (
          <div className="card bg-yellow-900/10 border-yellow-800/50">
            <div className="flex items-center gap-3 mb-3">
              <svg className="w-5 h-5 text-yellow-400 shrink-0" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2}
                  d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z" />
              </svg>
              <p className="text-yellow-300 text-sm font-medium">Esta decisão aguarda sua aprovação</p>
            </div>
            <p className="text-gray-400 text-sm mb-4">
              Revise o tema e a hipótese acima. Se estiver bom, aprove para o RENDERER gerar o roteiro completo.
            </p>
            <button onClick={approve} disabled={approving} className="btn-primary">
              {approving ? 'Aprovando...' : '✓ Aprovar decisão'}
            </button>
          </div>
        )}

        {isApproved && (
          <div className="card bg-blue-900/10 border-blue-800/50">
            <div className="flex items-center gap-3 mb-3">
              <svg className="w-5 h-5 text-blue-400 shrink-0" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2}
                  d="M15.232 5.232l3.536 3.536m-2.036-5.036a2.5 2.5 0 113.536 3.536L6.5 21.036H3v-3.572L16.732 3.732z" />
              </svg>
              <p className="text-blue-300 text-sm font-medium">Decisão aprovada — pronta para gerar roteiro</p>
            </div>
            <p className="text-gray-400 text-sm mb-4">
              O agente RENDERER vai criar um roteiro completo com hook, desenvolvimento, clímax e CTA.
              Isso pode levar 30–60 segundos.
            </p>
            <button onClick={render} disabled={rendering} className="btn-primary">
              {rendering ? (
                <>
                  <svg className="w-4 h-4 animate-spin" fill="none" viewBox="0 0 24 24">
                    <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4"/>
                    <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8v8z"/>
                  </svg>
                  Gerando roteiro... (aguarde ~30s)
                </>
              ) : '🎬 Gerar roteiro com RENDERER'}
            </button>
          </div>
        )}

        {isExecuting && (
          <div className="card bg-purple-900/10 border-purple-800/50 text-center py-6">
            <svg className="w-8 h-8 animate-spin text-purple-400 mx-auto mb-3" fill="none" viewBox="0 0 24 24">
              <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4"/>
              <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8v8z"/>
            </svg>
            <p className="text-purple-300 font-medium">RENDERER gerando roteiro...</p>
            <p className="text-gray-500 text-sm mt-1">Aguarde e recarregue a página em instantes</p>
          </div>
        )}

        {isDone && (
          <div className="card bg-green-900/10 border-green-800/50 text-center py-6">
            <div className="w-12 h-12 rounded-full bg-green-900/50 flex items-center justify-center mx-auto mb-3">
              <svg className="w-6 h-6 text-green-400" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M5 13l4 4L19 7" />
              </svg>
            </div>
            <p className="text-green-300 font-medium">Pipeline concluído!</p>
            <button onClick={() => router.push(`/dashboard/${officeId}`)} className="btn-outline mt-3">
              Ver escritório
            </button>
          </div>
        )}
      </main>
    </div>
  )
}
