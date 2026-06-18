'use client'
import { useState } from 'react'
import { useRouter } from 'next/navigation'
import Link from 'next/link'
import { auth, setToken } from '@/lib/api'

export default function RegisterPage() {
  const router = useRouter()
  const [name, setName]         = useState('')
  const [email, setEmail]       = useState('')
  const [password, setPassword] = useState('')
  const [error, setError]       = useState('')
  const [loading, setLoading]   = useState(false)

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault()
    setError('')
    setLoading(true)
    try {
      const { access_token } = await auth.register(email, password, name)
      setToken(access_token)
      router.push('/dashboard')
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : 'Erro ao criar conta')
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="min-h-screen flex items-center justify-center px-4">
      <div className="w-full max-w-sm">
        <div className="text-center mb-8">
          <div className="inline-flex items-center justify-center w-12 h-12 rounded-xl bg-brand-500 mb-4">
            <svg className="w-7 h-7 text-white" fill="none" viewBox="0 0 24 24" stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2}
                d="M13 10V3L4 14h7v7l9-11h-7z" />
            </svg>
          </div>
          <h1 className="text-2xl font-bold text-white">VIRAXIS</h1>
          <p className="text-gray-400 text-sm mt-1">Criar sua conta</p>
        </div>

        <div className="card">
          <form onSubmit={handleSubmit} className="space-y-4">
            <div>
              <label className="label">Nome completo</label>
              <input
                type="text" value={name} onChange={e => setName(e.target.value)}
                placeholder="Marcos Alves" required className="input"
              />
            </div>
            <div>
              <label className="label">Email</label>
              <input
                type="email" value={email} onChange={e => setEmail(e.target.value)}
                placeholder="seu@email.com" required className="input"
              />
            </div>
            <div>
              <label className="label">Senha</label>
              <input
                type="password" value={password} onChange={e => setPassword(e.target.value)}
                placeholder="mínimo 8 caracteres" minLength={8} required className="input"
              />
            </div>
            {error && (
              <p className="text-red-400 text-sm bg-red-900/30 border border-red-800 rounded-lg px-3 py-2">
                {error}
              </p>
            )}
            <button type="submit" disabled={loading} className="btn-primary w-full justify-center py-2.5">
              {loading ? 'Criando conta...' : 'Criar conta'}
            </button>
          </form>
        </div>

        <p className="text-center text-sm text-gray-500 mt-4">
          Já tem conta?{' '}
          <Link href="/login" className="text-brand-500 hover:text-brand-400">
            Entrar
          </Link>
        </p>
      </div>
    </div>
  )
}
