'use client'
import { useEffect, useState, Suspense } from 'react'
import { useSearchParams, useRouter } from 'next/navigation'
import Link from 'next/link'
import { auth } from '@/lib/api'

function VerifyEmailContent() {
  const searchParams = useSearchParams()
  const router = useRouter()
  const token = searchParams.get('token')

  const [status, setStatus] = useState<'loading' | 'success' | 'error'>('loading')
  const [message, setMessage] = useState('')

  useEffect(() => {
    if (!token) {
      setStatus('error')
      setMessage('Token não encontrado. Verifique o link recebido por email.')
      return
    }

    auth.verifyEmail(token)
      .then(res => {
        setStatus('success')
        setMessage(res.message)
        setTimeout(() => router.push('/login'), 3000)
      })
      .catch(err => {
        setStatus('error')
        setMessage(err instanceof Error ? err.message : 'Token inválido ou expirado.')
      })
  }, [token, router])

  return (
    <div className="min-h-screen flex items-center justify-center px-4">
      <div className="w-full max-w-sm text-center">
        {status === 'loading' && (
          <>
            <div className="inline-flex items-center justify-center w-16 h-16 rounded-full bg-brand-500/20 mb-6">
              <svg className="w-8 h-8 text-brand-400 animate-spin" fill="none" viewBox="0 0 24 24">
                <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4"/>
                <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z"/>
              </svg>
            </div>
            <h2 className="text-xl font-bold text-white mb-2">Verificando email...</h2>
            <p className="text-gray-400 text-sm">Aguarde um momento.</p>
          </>
        )}

        {status === 'success' && (
          <>
            <div className="inline-flex items-center justify-center w-16 h-16 rounded-full bg-green-500/20 mb-6">
              <svg className="w-8 h-8 text-green-400" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M5 13l4 4L19 7" />
              </svg>
            </div>
            <h2 className="text-xl font-bold text-white mb-2">Email verificado!</h2>
            <p className="text-gray-400 text-sm mb-6">{message}</p>
            <p className="text-gray-500 text-xs">Redirecionando para o login...</p>
            <Link href="/login" className="inline-block mt-4 text-brand-500 hover:text-brand-400 text-sm">
              Ir para login agora
            </Link>
          </>
        )}

        {status === 'error' && (
          <>
            <div className="inline-flex items-center justify-center w-16 h-16 rounded-full bg-red-500/20 mb-6">
              <svg className="w-8 h-8 text-red-400" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2}
                  d="M6 18L18 6M6 6l12 12" />
              </svg>
            </div>
            <h2 className="text-xl font-bold text-white mb-2">Link inválido</h2>
            <p className="text-gray-400 text-sm mb-6">{message}</p>
            <Link
              href="/register"
              className="inline-block btn-primary px-6 py-2.5 text-sm"
            >
              Criar conta novamente
            </Link>
          </>
        )}
      </div>
    </div>
  )
}

export default function VerifyEmailPage() {
  return (
    <Suspense fallback={
      <div className="min-h-screen flex items-center justify-center">
        <p className="text-gray-400">Carregando...</p>
      </div>
    }>
      <VerifyEmailContent />
    </Suspense>
  )
}
