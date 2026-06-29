'use client'
import { useState, useEffect, useCallback } from 'react'
import { useRouter } from 'next/navigation'
import { offices, clearToken, isLoggedIn, type OfficeResponse } from '@/lib/api'

const NICHES = [
  'Finanças e Investimentos', 'Desenvolvimento Pessoal', 'Saúde e Fitness',
  'Tecnologia', 'Empreendedorismo', 'Entretenimento', 'Educação', 'Outro',
]

const PLATFORMS = ['TikTok', 'Instagram Reels', 'YouTube Shorts', 'Kwai']

export default function DashboardPage() {
  const router = useRouter()
  const [officeList, setOfficeList] = useState<OfficeResponse[]>([])
  const [loading, setLoading]       = useState(true)
  const [showForm, setShowForm]     = useState(false)
  const [creating, setCreating]     = useState(false)
  const [error, setError]           = useState('')

  // form
  const [name, setName]             = useState('')
  const [niche, setNiche]           = useState(NICHES[0])
  const [audience, setAudience]     = useState('')
  const [platform, setPlatform]     = useState(PLATFORMS[0])

  const load = useCallback(async () => {
    if (!isLoggedIn()) { router.replace('/login'); return }
    try {
      const data = await offices.list()
      setOfficeList(data)
    } catch {
      clearToken(); router.replace('/login')
    } finally {
      setLoading(false)
    }
  }, [router])

  useEffect(() => { load() }, [load])

  async function handleCreate(e: React.FormEvent) {
    e.preventDefault()
    setError('')
    setCreating(true)
    try {
      await offices.create({
        name,
        niche,
        target_audience: audience,
        platforms: [platform],
      })
      setShowForm(false)
      setName(''); setAudience('')
      await load()
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : 'Erro ao criar')
    } finally {
      setCreating(false)
    }
  }

  function logout() { clearToken(); router.replace('/login') }

  const statusColor: Record<string, string> = {
    active:   'bg-green-900 text-green-300',
    inactive: 'bg-gray-800 text-gray-400',
    paused:   'bg-yellow-900 text-yellow-300',
  }

  return (
    <div className="min-h-screen">
      {/* Header */}
      <header className="border-b border-gray-800 bg-gray-950/80 backdrop-blur sticky top-0 z-10">
        <div className="max-w-5xl mx-auto px-4 h-14 flex items-center justify-between">
          <div className="flex items-center gap-2">
            <div className="w-7 h-7 rounded-lg bg-brand-500 flex items-center justify-center">
              <svg className="w-4 h-4 text-white" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M13 10V3L4 14h7v7l9-11h-7z" />
              </svg>
            </div>
            <span className="font-bold text-white">VIRAXIS</span>
          </div>
          <button onClick={logout} className="btn-ghost text-xs">Sair</button>
        </div>
      </header>

      <main className="max-w-5xl mx-auto px-4 py-8">
        {/* Title row */}
        <div className="flex items-center justify-between mb-6">
          <div>
            <h2 className="text-xl font-bold text-white">Escritórios</h2>
            <p className="text-gray-400 text-sm">Cada escritório é um canal de conteúdo autônomo</p>
          </div>
          <button onClick={() => setShowForm(true)} className="btn-primary">
            <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 4v16m8-8H4" />
            </svg>
            Novo escritório
          </button>
        </div>

        {/* Create form */}
        {showForm && (
          <div className="card mb-6">
            <h3 className="font-semibold text-white mb-4">Novo escritório</h3>
            <form onSubmit={handleCreate} className="space-y-4">
              <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
                <div>
                  <label className="label">Nome do canal</label>
                  <input value={name} onChange={e => setName(e.target.value)}
                    placeholder="Ex: Finanças Rápidas" required className="input" />
                </div>
                <div>
                  <label className="label">Nicho</label>
                  <select value={niche} onChange={e => setNiche(e.target.value)} className="input">
                    {NICHES.map(n => <option key={n}>{n}</option>)}
                  </select>
                </div>
                <div>
                  <label className="label">Plataforma principal</label>
                  <select value={platform} onChange={e => setPlatform(e.target.value)} className="input">
                    {PLATFORMS.map(p => <option key={p}>{p}</option>)}
                  </select>
                </div>
                <div>
                  <label className="label">Público-alvo</label>
                  <input value={audience} onChange={e => setAudience(e.target.value)}
                    placeholder="Ex: jovens 18-30 interessados em renda extra" className="input" />
                </div>
              </div>
              {error && <p className="text-red-400 text-sm">{error}</p>}
              <div className="flex gap-2">
                <button type="submit" disabled={creating} className="btn-primary">
                  {creating ? 'Criando...' : 'Criar'}
                </button>
                <button type="button" onClick={() => setShowForm(false)} className="btn-outline">
                  Cancelar
                </button>
              </div>
            </form>
          </div>
        )}

        {/* Office list */}
        {loading ? (
          <div className="text-center py-16 text-gray-500">Carregando...</div>
        ) : officeList.length === 0 ? (
          <div className="text-center py-16">
            <div className="w-16 h-16 rounded-2xl bg-gray-800 flex items-center justify-center mx-auto mb-4">
              <svg className="w-8 h-8 text-gray-600" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5}
                  d="M19 21V5a2 2 0 00-2-2H7a2 2 0 00-2 2v16m14 0h2m-2 0h-5m-9 0H3m2 0h5M9 7h1m-1 4h1m4-4h1m-1 4h1m-5 10v-5a1 1 0 011-1h2a1 1 0 011 1v5m-4 0h4" />
              </svg>
            </div>
            <p className="text-gray-400 mb-2">Nenhum escritório ainda</p>
            <p className="text-gray-600 text-sm">Crie seu primeiro canal de conteúdo</p>
          </div>
        ) : (
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
            {officeList.map(o => (
              <button
                key={o.id}
                onClick={() => router.push(`/dashboard/${o.id}`)}
                className="card text-left hover:border-gray-600 hover:bg-gray-800/50 transition-all group"
              >
                <div className="flex items-start justify-between mb-3">
                  <div className="w-10 h-10 rounded-xl bg-brand-500/20 flex items-center justify-center">
                    <svg className="w-5 h-5 text-brand-500" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2}
                        d="M13 10V3L4 14h7v7l9-11h-7z" />
                    </svg>
                  </div>
                  <span className={`badge text-xs ${statusColor[o.status] ?? 'bg-gray-800 text-gray-400'}`}>
                    {o.status}
                  </span>
                </div>
                <h3 className="font-semibold text-white group-hover:text-brand-400 transition-colors">
                  {o.name}
                </h3>
                {o.niche_profile && (
                  <p className="text-gray-400 text-xs mt-1">{o.niche_profile.niche_name}</p>
                )}
                <p className="text-gray-600 text-xs mt-2">
                  {new Date(o.created_at).toLocaleDateString('pt-BR')}
                </p>
              </button>
            ))}
          </div>
        )}
      </main>
    </div>
  )
}
