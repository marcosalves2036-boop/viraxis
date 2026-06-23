'use client'
import { useState, useEffect, useCallback } from 'react'
import { useRouter, useParams } from 'next/navigation'
import { content, type ContentItemResponse, type ScriptSection } from '@/lib/api'

const sectionMeta: Record<string, { label: string; color: string; icon: string }> = {
  hook:        { label: 'Hook',        color: 'border-l-red-500',    icon: '🎣' },
  development: { label: 'Desenvolvimento', color: 'border-l-yellow-500', icon: '📈' },
  climax:      { label: 'Clímax',      color: 'border-l-purple-500', icon: '🔥' },
  cta:         { label: 'CTA',         color: 'border-l-green-500',  icon: '👆' },
}

function SectionCard({ s }: { s: ScriptSection }) {
  const meta = sectionMeta[s.section] ?? { label: s.section, color: 'border-l-gray-500', icon: '📝' }
  return (
    <div className={`card border-l-4 ${meta.color} space-y-3`}>
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2">
          <span className="text-lg">{meta.icon}</span>
          <span className="font-semibold text-white">{meta.label}</span>
        </div>
        <span className="text-gray-500 text-xs">{s.duration_estimate_seconds}s</span>
      </div>
      <p className="text-gray-300 text-sm leading-relaxed whitespace-pre-wrap">{s.content}</p>
      {s.visual_notes && (
        <div className="border-t border-gray-800 pt-3">
          <p className="text-gray-600 text-xs mb-1">Notas visuais</p>
          <p className="text-gray-500 text-xs italic">{s.visual_notes}</p>
        </div>
      )}
    </div>
  )
}

export default function ContentPage() {
  const router   = useRouter()
  const params   = useParams()
  const officeId = params.officeId as string
  const itemId   = params.itemId as string

  const [item, setItem]       = useState<ContentItemResponse | null>(null)
  const [loading, setLoading] = useState(true)
  const [copied, setCopied]   = useState(false)
  const [view, setView]       = useState<'sections' | 'full'>('sections')

  const load = useCallback(async () => {
    try {
      const d = await content.get(itemId)
      setItem(d)
    } catch {
      router.replace(`/dashboard/${officeId}`)
    } finally {
      setLoading(false)
    }
  }, [itemId, officeId, router])

  useEffect(() => { load() }, [load])

  function copyScript() {
    if (!item) return
    const text = item.renderer_output?.sections
      ? item.renderer_output.sections
          .map(s => `[${sectionMeta[s.section]?.label ?? s.section}]\n${s.content}`)
          .join('\n\n')
      : item.script
    navigator.clipboard.writeText(text).then(() => {
      setCopied(true)
      setTimeout(() => setCopied(false), 2000)
    })
  }

  if (loading || !item) return (
    <div className="min-h-screen flex items-center justify-center text-gray-500">Carregando roteiro...</div>
  )

  const ro      = item.renderer_output
  const sections: ScriptSection[] = ro?.sections ?? []
  const totalDur = ro?.total_duration_estimate_seconds ?? item.duration_seconds ?? 0

  return (
    <div className="min-h-screen">
      <header className="border-b border-gray-800 bg-gray-950/80 backdrop-blur sticky top-0 z-10">
        <div className="max-w-3xl mx-auto px-4 h-14 flex items-center justify-between">
          <div className="flex items-center gap-3">
            <button onClick={() => router.push(`/dashboard/${officeId}`)}
              className="text-gray-500 hover:text-gray-300 transition-colors">
              <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M15 19l-7-7 7-7" />
              </svg>
            </button>
            <div className="w-px h-4 bg-gray-700" />
            <span className="font-semibold text-white">Roteiro</span>
          </div>
          <button onClick={copyScript} className="btn-outline text-xs gap-1.5">
            {copied ? (
              <><svg className="w-4 h-4 text-green-400" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M5 13l4 4L19 7" />
              </svg> Copiado!</>
            ) : (
              <><svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2}
                  d="M8 16H6a2 2 0 01-2-2V6a2 2 0 012-2h8a2 2 0 012 2v2m-6 12h8a2 2 0 002-2v-8a2 2 0 00-2-2h-8a2 2 0 00-2 2v8a2 2 0 002 2z" />
              </svg> Copiar roteiro</>
            )}
          </button>
        </div>
      </header>

      <main className="max-w-3xl mx-auto px-4 py-8 space-y-6">

        {/* Título e métricas */}
        <div>
          <h1 className="text-2xl font-bold text-white mb-4">{item.title}</h1>
          <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
            {[
              { label: 'Duração total',  value: `${totalDur}s` },
              { label: 'Arquétipo',     value: ro?.archetype_applied ?? '—' },
              { label: 'Confiança',     value: ro ? `${Math.round(ro.confidence_score * 100)}%` : '—' },
              { label: 'Plataforma',    value: item.platform ?? '—' },
            ].map(m => (
              <div key={m.label} className="bg-gray-800/60 rounded-xl p-3">
                <p className="text-gray-500 text-xs">{m.label}</p>
                <p className="text-white font-semibold text-sm mt-0.5 truncate">{m.value}</p>
              </div>
            ))}
          </div>
        </div>

        {/* Adaptações de plataforma */}
        {ro?.platform_adaptations && (
          <div className="card bg-brand-500/5 border-brand-500/20">
            <p className="text-gray-500 text-xs mb-1">Adaptações para a plataforma</p>
            <p className="text-gray-300 text-sm">{ro.platform_adaptations}</p>
          </div>
        )}

        {/* Toggle sections / full */}
        <div className="flex gap-1 bg-gray-800 rounded-lg p-1 w-fit">
          <button
            onClick={() => setView('sections')}
            className={`px-3 py-1.5 rounded-md text-sm font-medium transition-all ${
              view === 'sections' ? 'bg-gray-700 text-white' : 'text-gray-500 hover:text-gray-300'
            }`}
          >
            Por seção
          </button>
          <button
            onClick={() => setView('full')}
            className={`px-3 py-1.5 rounded-md text-sm font-medium transition-all ${
              view === 'full' ? 'bg-gray-700 text-white' : 'text-gray-500 hover:text-gray-300'
            }`}
          >
            Roteiro completo
          </button>
        </div>

        {/* Conteúdo */}
        {view === 'sections' ? (
          sections.length > 0 ? (
            <div className="space-y-4">
              {sections.map((s, i) => <SectionCard key={i} s={s} />)}
            </div>
          ) : (
            <div className="card text-gray-500 text-sm text-center py-8">
              Seções não disponíveis — veja o roteiro completo
            </div>
          )
        ) : (
          <div className="card">
            <pre className="text-gray-300 text-sm leading-relaxed whitespace-pre-wrap font-sans">
              {item.script}
            </pre>
          </div>
        )}

        {/* Ação final */}
        <div className="card bg-gray-800/40 border-dashed text-center py-6">
          <p className="text-gray-400 text-sm mb-1">Roteiro pronto para gravação</p>
          <p className="text-gray-600 text-xs">Publicação nas redes sociais disponível no Sprint 2</p>
        </div>

      </main>
    </div>
  )
}
