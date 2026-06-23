'use client'
import { useState } from 'react'
import { useRouter } from 'next/navigation'
import Link from 'next/link'
import { auth, setToken } from '@/lib/api'

export default function LoginPage() {
  const router = useRouter()
  const [email, setEmail]       = useState('')
  const [password, setPassword] = useState('')
  const [error, setError]       = useState('')
  const [loading, setLoading]   = useState(false)
  const [unverified, setUnverified] = useState(false)
  const [resending, setResending]   = useState(false)
  const [resendMsg, setResendMsg]   = useState('')

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault()
    setError('')
    setUnverified(false)
    setResendMsg('')
    setLoading(true)
    try {
      const { access_token } = await auth.login(email, password)
      setToken(access_token)
      router.push('/dashboard')
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : 'Erro ao entrar'
      if (msg.includes('não verificado') || msg.includes('verificado')) {
        setUnverified(true)
      } else {
        setError(msg)
      }
    } finally {
      setLoading(false)
    }
  }

  async function handleResend() {
    setResending(true)
    setResendMsg('')
    try {
      await auth.resendVerification(email)
      setResendMsg('Novo link enviado! Verifique sua caixa de entrada.')
    } catch {
      setResendMsg('Erro ao reenviar. Tente novamente.')
    } finally {
      setResending(false)
    }
  }

  return (
    <div className="min-h-screen flex items-center justify-center px-4">
      <div className="w-full max-w-sm">
        {/* Logo */}
        <div className="text-center mb-8">
          <div className="inline-flex items-center justify-center w-12 h-12 rounded-xl bg-brand-500 mb-4">
            <svg className="w-7 h-7 text-white" fill="none" viewBox="0 0 24 24" stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2}
                d="M13 10V3L4 14h7v7l9-11h-7z" />
            </svg>
          </div>
          <h1 className="text-2xl font-bold text-white">VIRAXIS</h1>
          <p className="text-gray-400 text-sm mt-1">Entre na sua conta</p>
        </div>

        <div className="card">
          <form onSubmit={handleSubmit} className="space-y-4">
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
                placeholder="••••••••" required className="input"
              />
            </div>

            {error && (
              <p className="text-red-400 text-sm bg-red-900/30 border border-red-800 rounded-lg px-3 py-2">
                {error}
              </p>
            )}

            {unverified && (
              <div className="bg-amber-900/30 border border-amber-800 rounded-lg px-3 py-3 space-y-2">
                <p className="text-amber-400 text-sm">
                  Email não verificado. Verifique sua caixa de entrada ou reenvie o link.
                </p>
                {resendMsg ? (
                  <p className="text-green-400 text-xs">{resendMsg}</p>
                ) : (
                  <button
                    type="button"
                    onClick={handleResend}
                    disabled={resending || !email}
                    className="text-amber-300 text-xs underline hover:text-amber-200 disabled:opacity-50"
                  >
                    {resending ? 'Enviando...' : 'Reenviar link de verificação'}
                  </button>
                )}
              </div>
            )}

            <button type="submit" disabled={loading} className="btn-primary w-full justify-center py-2.5">
              {loading ? 'Entrando...' : 'Entrar'}
            </button>
          </form>
        </div>

        <div className="flex justify-between mt-4">
          <p className="text-sm text-gray-500">
            Não tem conta?{' '}
            <Link href="/register" className="text-brand-500 hover:text-brand-400">
              Criar conta
            </Link>
          </p>
          <Link href="/forgot-password" className="text-sm text-gray-500 hover:text-gray-400">
            Esqueci a senha
          </Link>
        </div>
      </div>
    </div>
  )
}
