"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";
import Link from "next/link";

const NICHES = [
  "Finanças pessoais", "Saúde & bem-estar", "Empreendedorismo", "Tecnologia & IA",
  "Marketing digital", "Desenvolvimento pessoal", "Fitness & academia", "Culinária",
  "Moda & estilo", "Viagens", "Relacionamentos", "Esportes",
];

const PLATFORMS = [
  { id: "tiktok", label: "TikTok", icon: "🎵" },
  { id: "instagram", label: "Instagram Reels", icon: "📸" },
  { id: "youtube", label: "YouTube Shorts", icon: "▶️" },
  { id: "twitter", label: "Twitter/X", icon: "🐦" },
];

export default function NovoEscritorioPage() {
  const router = useRouter();
  const [step, setStep] = useState(1);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [form, setForm] = useState({
    name: "",
    niche: "",
    custom_niche: "",
    platforms: [] as string[],
    target_audience: "",
    content_style: "educational",
  });

  function togglePlatform(id: string) {
    setForm(f => ({
      ...f,
      platforms: f.platforms.includes(id)
        ? f.platforms.filter(p => p !== id)
        : [...f.platforms, id],
    }));
  }

  async function handleSubmit() {
    setLoading(true);
    setError("");
    const token = localStorage.getItem("viraxis_token");
    try {
      const res = await fetch("/api/offices", {
        method: "POST",
        headers: { "Content-Type": "application/json", Authorization: `Bearer ${token}` },
        body: JSON.stringify({
          name: form.name,
          niche: form.custom_niche || form.niche,
          platforms: form.platforms,
          target_audience: form.target_audience,
          content_style: form.content_style,
        }),
      });
      const data = await res.json();
      if (!res.ok) throw new Error(data.detail ?? "Erro ao criar escritório");
      router.push(`/dashboard/canais?office_id=${data.id}`);
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : "Erro desconhecido");
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="max-w-2xl mx-auto space-y-6">
      <div>
        <Link href="/dashboard/escritorios" className="text-white/40 text-sm hover:text-white/70 transition-colors">
          ← Voltar
        </Link>
        <h1 className="text-2xl font-black text-white mt-2">Novo Escritório Viral</h1>
        <p className="text-white/40 text-sm mt-1">Configure seu escritório autônomo de conteúdo.</p>
      </div>

      {/* Progress */}
      <div className="flex gap-2">
        {[1, 2, 3].map(s => (
          <div key={s} className={`h-1 flex-1 rounded-full transition-colors ${s <= step ? "bg-violet-500" : "bg-white/10"}`} />
        ))}
      </div>

      <div className="card-glass rounded-2xl p-6 space-y-6">
        {/* Step 1: básico */}
        {step === 1 && (
          <>
            <h2 className="font-bold text-white">1. Informações básicas</h2>
            <div className="space-y-4">
              <div>
                <label className="block text-sm text-white/60 mb-1.5">Nome do escritório</label>
                <input
                  type="text"
                  value={form.name}
                  onChange={e => setForm(f => ({ ...f, name: e.target.value }))}
                  placeholder="Ex: Finance Hacks BR"
                  className="w-full bg-white/[0.06] border border-white/10 rounded-xl px-4 py-3 text-sm text-white placeholder-white/20 focus:outline-none focus:border-violet-500/60 transition-colors"
                />
              </div>
              <div>
                <label className="block text-sm text-white/60 mb-1.5">Nicho</label>
                <div className="grid grid-cols-2 gap-2 mb-3">
                  {NICHES.map(n => (
                    <button
                      key={n}
                      type="button"
                      onClick={() => setForm(f => ({ ...f, niche: n, custom_niche: "" }))}
                      className={`text-left px-3 py-2.5 rounded-xl text-sm border transition-all
                        ${form.niche === n
                          ? "bg-violet-600/20 border-violet-500/40 text-violet-300"
                          : "bg-white/[0.04] border-white/10 text-white/60 hover:border-white/20"}`}
                    >
                      {n}
                    </button>
                  ))}
                </div>
                <input
                  type="text"
                  value={form.custom_niche}
                  onChange={e => setForm(f => ({ ...f, custom_niche: e.target.value, niche: "" }))}
                  placeholder="Ou escreva um nicho personalizado..."
                  className="w-full bg-white/[0.06] border border-white/10 rounded-xl px-4 py-3 text-sm text-white placeholder-white/20 focus:outline-none focus:border-violet-500/60 transition-colors"
                />
              </div>
            </div>
          </>
        )}

        {/* Step 2: plataformas */}
        {step === 2 && (
          <>
            <h2 className="font-bold text-white">2. Plataformas alvo</h2>
            <p className="text-white/40 text-sm">Selecione onde o conteúdo será publicado.</p>
            <div className="grid grid-cols-2 gap-3">
              {PLATFORMS.map(p => (
                <button
                  key={p.id}
                  type="button"
                  onClick={() => togglePlatform(p.id)}
                  className={`flex items-center gap-3 px-4 py-4 rounded-xl border transition-all text-left
                    ${form.platforms.includes(p.id)
                      ? "bg-violet-600/20 border-violet-500/40"
                      : "bg-white/[0.04] border-white/10 hover:border-white/20"}`}
                >
                  <span className="text-2xl">{p.icon}</span>
                  <span className={`text-sm font-medium ${form.platforms.includes(p.id) ? "text-violet-300" : "text-white/60"}`}>
                    {p.label}
                  </span>
                </button>
              ))}
            </div>
            <div>
              <label className="block text-sm text-white/60 mb-1.5">Público-alvo</label>
              <textarea
                value={form.target_audience}
                onChange={e => setForm(f => ({ ...f, target_audience: e.target.value }))}
                placeholder="Descreva seu público-alvo. Ex: Jovens de 20-35 anos interessados em investimentos..."
                rows={3}
                className="w-full bg-white/[0.06] border border-white/10 rounded-xl px-4 py-3 text-sm text-white placeholder-white/20 focus:outline-none focus:border-violet-500/60 transition-colors resize-none"
              />
            </div>
          </>
        )}

        {/* Step 3: estilo */}
        {step === 3 && (
          <>
            <h2 className="font-bold text-white">3. Estilo de conteúdo</h2>
            <p className="text-white/40 text-sm">Como os agentes devem criar o conteúdo?</p>
            <div className="space-y-3">
              {[
                { id: "educational", label: "Educativo", desc: "Ensina algo útil ao público" },
                { id: "entertainment", label: "Entretenimento", desc: "Foca em engajamento e viralização" },
                { id: "inspirational", label: "Inspiracional", desc: "Motiva e conecta emocionalmente" },
                { id: "controversial", label: "Provocativo", desc: "Gera debate e alta retenção" },
              ].map(s => (
                <button
                  key={s.id}
                  type="button"
                  onClick={() => setForm(f => ({ ...f, content_style: s.id }))}
                  className={`w-full text-left px-4 py-4 rounded-xl border transition-all
                    ${form.content_style === s.id
                      ? "bg-violet-600/20 border-violet-500/40"
                      : "bg-white/[0.04] border-white/10 hover:border-white/20"}`}
                >
                  <p className={`font-medium text-sm ${form.content_style === s.id ? "text-violet-300" : "text-white/80"}`}>
                    {s.label}
                  </p>
                  <p className="text-white/40 text-xs mt-0.5">{s.desc}</p>
                </button>
              ))}
            </div>

            {error && (
              <div className="bg-red-500/10 border border-red-500/30 rounded-xl px-4 py-3 text-sm text-red-300">
                {error}
              </div>
            )}
          </>
        )}

        {/* Botões */}
        <div className="flex gap-3 pt-2">
          {step > 1 && (
            <button
              type="button"
              onClick={() => setStep(s => s - 1)}
              className="flex-1 py-3 rounded-xl border border-white/10 text-white/60 text-sm font-medium hover:border-white/20 transition-colors"
            >
              Voltar
            </button>
          )}
          {step < 3 ? (
            <button
              type="button"
              onClick={() => setStep(s => s + 1)}
              disabled={step === 1 && !form.name}
              className="flex-1 py-3 rounded-xl bg-violet-600 hover:bg-violet-500 disabled:bg-violet-900 disabled:cursor-not-allowed text-white text-sm font-semibold transition-colors"
            >
              Continuar →
            </button>
          ) : (
            <button
              type="button"
              onClick={handleSubmit}
              disabled={loading || form.platforms.length === 0}
              className="flex-1 py-3 rounded-xl bg-violet-600 hover:bg-violet-500 disabled:bg-violet-900 disabled:cursor-not-allowed text-white text-sm font-semibold transition-colors"
            >
              {loading ? "Criando..." : "Criar Escritório 🚀"}
            </button>
          )}
        </div>
      </div>
  