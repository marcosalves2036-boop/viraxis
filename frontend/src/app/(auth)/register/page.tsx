'use client'
import { useState } from 'react'
import Link from 'next/link'
import { auth } from '@/lib/api'

export default function RegisterPage() {
  const [name, setName]         = useState('')
  const [email, setEmail]       = useState('')
  const [password, setPassword] = useState('')
  const [error, setError]       = useState('')
  const [loading, setLoading]   = useState(false)
  const [done, setDone]         = useState(false)
  const [resending, setResending] = useState(false)
  const [resendMsg, setResendMsg] = useState('')

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault()
    setError('')
    setLoading(true)
    try {
      await auth.register(email, password, name)
      setDone(true)
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : 'Erro ao criar conta')
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

  if (done) {
    return (
      <div className="min-h-screen flex items-center justify-center px-4">
        <div className="w-full max-w-sm text-center">
          <div className="inline-flex items-center justify-center w-16 h-16 rounded-full bg-brand-500/20 mb-6">
            <svg className="w-8 h-8 text-brand-400" fill="none" viewBox="0 0 24 24" stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2}
                d="M3 8l7.89 5.26a2 2 0 002.22 0L21 8M5 19h14a2 2 0 002-2V7a2 2 0 00-2-2H5a2 2 0 00-2 2v10a2 2 0 002 2z" />
            </svg>
          </div>
          <h2 className="text-xl font-bold text-white mb-2">Verifique seu email</h2>
          <p className="text-gray-400 text-sm mb-6">
            Enviamos um link de verificação para<br />
            <span className="text-white font-medium">{email}</span>
          </p>
          <div className="card text-left space-y-3">
            <p className="text-gray-400 text-sm">Não recebeu o email?</p>
            {resendMsg && (
              <p className="text-green-400 text-sm">{resendMsg}</p>
            )}
            <button
              onClick={handleResend}
              disabled={resending}
              className="btn-primary w-full justify-center py-2.5 text-sm"
            >
              {resending ? 'Enviando...' : 'Reenviar link de verificação'}
            </button>
          </div>
          <p className="text-center text-sm text-gray-500 mt-4">
            Já verificou?{' '}
            <Link href="/login" className="text-brand-500 hover:text-brand-400">
              Fazer login
            </Link>
          </p>
        </div>
      </div>
    )
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
