"use client";

import Link from "next/link";
import { useEffect, useState } from "react";

function StatCard({ label, value, sub, color = "violet" }: {
  label: string; value: string | number; sub?: string; color?: "violet" | "cyan" | "emerald" | "rose";
}) {
  const colors = {
    violet: "from-violet-500 to-violet-700",
    cyan: "from-cyan-500 to-cyan-700",
    emerald: "from-emerald-500 to-emerald-700",
    rose: "from-rose-500 to-rose-700",
  };
  return (
    <div className="card-glass rounded-2xl p-5">
      <p className="text-white/40 text-xs uppercase tracking-widest mb-3">{label}</p>
      <p className={`text-3xl font-black bg-gradient-to-r ${colors[color]} bg-clip-text text-transparent`}>{value}</p>
      {sub && <p className="text-white/25 text-xs mt-1">{sub}</p>}
    </div>
  );
}

function QuickAction({ icon, label, href, desc }: { icon: string; label: string; href: string; desc: string }) {
  return (
    <Link href={href} className="card-glass rounded-2xl p-5 flex gap-4 items-start hover:border-violet-500/30 transition-all group">
      <div className="text-2xl shrink-0">{icon}</div>
      <div>
        <p className="font-semibold text-white group-hover:text-violet-300 transition-colors">{label}</p>
        <p className="text-white/40 text-sm mt-0.5">{desc}</p>
      </div>
    </Link>
  );
}

interface Office {
  id: string;
  content_count: number;
  published_count: number;
  viral_count: number;
}

export default function DashboardPage() {
  const [offices, setOffices] = useState<Office[]>([]);
  const [user, setUser] = useState<{ full_name: string } | null>(null);

  useEffect(() => {
    const token = localStorage.getItem("viraxis_token");
    if (!token) return;
    const h = { Authorization: `Bearer ${token}` };
    fetch("/api/offices", { headers: h }).then(r => r.json()).then(d => { if (Array.isArray(d)) setOffices(d); }).catch(() => {});
    fetch("/api/users/me", { headers: h }).then(r => r.json()).then(d => setUser(d)).catch(() => {});
  }, []);

  const totalContent = offices.reduce((s, o) => s + (o.content_count ?? 0), 0);
  const totalPublished = offices.reduce((s, o) => s + (o.published_count ?? 0), 0);
  const totalViral = offices.reduce((s, o) => s + (o.viral_count ?? 0), 0);
  const hasOffice = offices.length > 0;

  return (
    <div className="max-w-5xl mx-auto space-y-8">
      {/* Header */}
      <div>
        <h1 className="text-2xl font-black text-white">
          {user ? `Olá, ${user.full_name.split(" ")[0]} 👋` : "Visão Geral"}
        </h1>
        <p className="text-white/40 text-sm mt-1">Bem-vindo ao seu painel VIRAXIS.</p>
      </div>

      {/* Stats */}
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
        <StatCard label="Escritórios" value={offices.length} sub="Máx. 1 no plano Free" color="violet" />
        <StatCard label="Conteúdos" value={totalContent} sub="Total gerado" color="cyan" />
        <StatCard label="Publicados" value={totalPublished} sub="Prontos para ir ao ar" color="emerald" />
        <StatCard label="Virais" value={totalViral} sub="> 100k views" color="rose" />
      </div>

      {/* Quick actions */}
      <div>
        <h2 className="text-sm font-semibold text-white/50 uppercase tracking-widest mb-4">Ações rápidas</h2>
        <div className="grid md:grid-cols-2 gap-4">
          {hasOffice ? (
            <QuickAction icon="🏢" label="Meus Escritórios" href="/dashboard/escritorios" desc="Gerencie e execute seus agentes BRAIN" />
          ) : (
            <QuickAction icon="🏢" label="Criar Escritório Viral" href="/dashboard/escritorios/novo" desc="Configure um novo escritório autônomo de conteúdo" />
          )}
          <QuickAction icon="📹" label="Ver Conteúdos Gerados" href="/dashboard/conteudo" desc="Revise e publique o conteúdo criado pelos agentes" />
          <QuickAction icon="📊" label="Analíticos" href="/dashboard/analiticos" desc="Acompanhe o desempenho dos seus conteúdos" />
          <QuickAction icon="⚙️" label="Configurações" href="/dashboard/configuracoes" desc="Gerencie sua conta e integrações" />
        </div>
      </div>

      {/* Onboarding checklist */}
      <div className="card-glass rounded-2xl p-6">
        <h2 className="font-bold text-white mb-4">🚀 Primeiros passos</h2>
        <div className="space-y-3">
          {[
            { done: true, label: "Criar sua conta VIRAXIS" },
            { done: hasOffice, label: "Criar seu primeiro Escritório Viral" },
            { done: hasOffice, label: "Configurar nicho e plataformas alvo" },
            { done: totalContent > 0, label: "Ativar o agente BRAIN para análise" },
            { done: totalPublished > 0, label: "Publicar seu primeiro conteúdo viral" },
          ].map((step, i) => (
            <div key={i} className="flex items-center gap-3">
              <div className={`w-5 h-5 rounded-full border flex items-center justify-center text-xs shrink-0
                ${step.done ? "bg-emerald-500 border-emerald-500 text-white" : "border-white/20 text-white/0"}`}>
                {step.done ? "✓" : ""}
              </div>
              <span className={`text-sm ${step.done ? "text-white/40 line-through" : "text-white/70"}`}>
                {step.label}
              </span>
            </div>
          ))}
        </div>
        {!hasOffice && (
          <div className="mt-5">
            <Link
              href="/dashboard/escritorios/novo"
              className="inline-block px-5 py-2.5 bg-violet-600 hover:bg-violet-500 text-white text-sm font-semibold rounded-xl transition-colors"
            >
              Criar meu primeiro escritório →
            </Link>
          </div>
        )}
      </div>
    </div>
  );
}
