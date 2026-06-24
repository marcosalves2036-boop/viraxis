"use client";

import Link from "next/link";
import { useState } from "react";
import { api } from "@/lib/api";

export default function CadastroPage() {
  const [fullName, setFullName] = useState("");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);
  const [success, setSuccess] = useState(false);

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setError("");
    if (password.length < 8) {
      setError("Senha deve ter pelo menos 8 caracteres");
      return;
    }
    setLoading(true);
    try {
      await api.register(email, password, fullName);
      setSuccess(true);
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : "Erro ao criar conta");
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="min-h-screen flex items-center justify-center px-4 relative overflow-hidden">
      <div className="hero-glow w-[500px] h-[500px] bg-violet-700" style={{ top: "20%", left: "50%", transform: "translateX(-50%)" }} />

      <div className="relative z-10 w-full max-w-md">
        {/* Logo */}
        <div className="text-center mb-8">
          <Link href="/" className="text-2xl font-black gradient-text">VIRAXIS</Link>
          <p className="text-white/40 text-sm mt-2">Crie seu escritório viral grátis</p>
        </div>

        {success ? (
          /* ── Tela de sucesso / verificação ── */
          <div className="card-glass rounded-2xl p-8 text-center">
            <div className="text-5xl mb-4">📧</div>
            <h1 className="text-xl font-bold mb-3">Verifique seu email</h1>
            <p className="text-white/50 text-sm mb-6">
              Enviamos um link de confirmação para{" "}
              <span className="text-violet-400 font-medium">{email}</span>.
              Clique no link para ativar sua conta.
            </p>
            <p className="text-white/30 text-xs mb-6">
              Não recebeu? Verifique sua pasta de spam ou{" "}
              <button
                className="text-violet-400 hover:text-violet-300 underline transition-colors"
                onClick={async () => {
                  try {
                    await api.resendVerification(email);
                    alert("Email reenviado!");
                  } catch {
                    alert("Erro ao reenviar. Tente novamente.");
                  }
                }}
              >
                clique aqui para reenviar
              </button>
              .
            </p>
            <Link
              href="/login"
              className="inline-block py-3 px-6 bg-violet-600 hover:bg-violet-500 text-white font-semibold rounded-xl transition-colors text-sm"
            >
              Ir para o login
            </Link>
          </div>
        ) : (
          /* ── Formulário de cadastro ── */
          <div className="card-glass rounded-2xl p-8">
            <h1 className="text-xl font-bold mb-6">Criar conta</h1>

            <form onSubmit={handleSubmit} className="space-y-4">
              <div>
                <label className="block text-sm text-white/60 mb-1.5">Nome completo</label>
                <input
                  type="text"
                  required
                  value={fullName}
                  onChange={(e) => setFullName(e.target.value)}
                  placeholder="Seu nome"
                  className="w-full bg-white/[0.06] border border-white/10 rounded-xl px-4 py-3 text-sm text-white placeholder-white/20 focus:outline-none focus:border-violet-500/60 transition-colors"
                />
              </div>

              <div>
                <label className="block text-sm text-white/60 mb-1.5">Email</label>
                <input
                  type="email"
                  required
                  value={email}
                  onChange={(e) => setEmail(e.target.value)}
                  placeholder="voce@exemplo.com"
                  className="w-full bg-white/[0.06] border border-white/10 rounded-xl px-4 py-3 text-sm text-white placeholder-white/20 focus:outline-none focus:border-violet-500/60 transition-colors"
                />
              </div>

              <div>
                <label className="block text-sm text-white/60 mb-1.5">Senha</label>
                <input
                  type="password"
                  required
            