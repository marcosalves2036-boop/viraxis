"use client";

import Link from "next/link";
import { useEffect, useState } from "react";

interface Office {
  id: string; name: string; niche: string; status: string;
  platforms: string[]; content_count: number; published_count: number;
  viral_count: number; pending_decisions: number;
}

const PLATFORM_ICONS: Record<string, string> = {
  tiktok: "🎵", instagram: "📸", youtube: "▶️", twitter: "🐦",
  linkedin: "💼", facebook: "👥", pinterest: "📌",
};

export default function EscritoriosPage() {
  const [offices, setOffices] = useState<Office[]>([]);
  const [loading, setLoading] = useState(true);
  const [confirmDelete, setConfirmDelete] = useState<Office | null>(null);
  const [deleting, setDeleting] = useState(false);

  useEffect(() => {
    const token = localStorage.getItem("viraxis_token");
    if (!token) return;
    fetch("/api/offices", { headers: { Authorization: `Bearer ${token}` } })
      .then(r => r.json())
      .then(data => { if (Array.isArray(data)) setOffices(data); })
      .catch(() => {})
      .finally(() => setLoading(false));
  }, []);

  async function handleDelete(office: Office) {
    const token = localStorage.getItem("viraxis_token");
    if (!token) return;
    setDeleting(true);
    try {
      const res = await fetch(`/api/offices/${office.id}`, {
        method: "DELETE",
        headers: { Authorization: `Bearer ${token}` },
      });
      if (res.ok || res.status === 204) {
        setOffices(prev => prev.filter(o => o.id !== office.id));
        setConfirmDelete(null);
      }
    } finally {
      setDeleting(false);
    }
  }

  const totalPending = offices.reduce((s, o) => s + (o.pending_decisions ?? 0), 0);

  return (
    <div className="max-w-5xl mx-auto space-y-6">
      {/* Confirm Delete Modal */}
      {confirmDelete && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/70 backdrop-blur-sm px-4">
          <div className="card-glass rounded-2xl p-8 max-w-md w-full space-y-5 shadow-2xl border border-white/10">
            <div className="text-center">
              <div className="text-5xl mb-3">🗑️</div>
              <h2 className="text-xl font-black text-white">Apagar escritório?</h2>
              <p className="text-white/50 text-sm mt-2">
                Esta ação é <span className="text-red-400 font-semibold">permanente e irreversível</span>.
              </p>
            </div>

            <div className="bg-white/[0.04] rounded-xl px-4 py-3 border border-white/10 text-center">
              <p className="text-white font-bold">{confirmDelete.name}</p>
              <p className="text-white/40 text-sm">{confirmDelete.niche}</p>
            </div>

            <div className="bg-red-500/10 border border-red-500/20 rounded-xl px-4 py-3 text-sm text-red-300 space-y-1">
              <p className="font-semibold text-red-400">Tudo será apagado:</p>
              <p>• Perfil de nicho e configurações</p>
              <p>• Decisões e estratégias do BRAIN</p>
              <p>• Roteiros e conteúdos gerados</p>
              <p>• Análises de tendências (SCOUT)</p>
            </div>

            <div className="flex gap-3 pt-1">
              <button
                onClick={() => setConfirmDelete(null)}
                disabled={deleting}
                className="flex-1 py-2.5 rounded-xl text-sm font-semibold bg-white/[0.06] border border-white/10 text-white/60 hover:bg-white/10 transition-colors disabled:opacity-40"
              >
                Cancelar
              </button>
              <button
                onClick={() => handleDelete(confirmDelete)}
                disabled={deleting}
                className="flex-1 py-2.5 rounded-xl text-sm font-semibold bg-red-600 hover:bg-red-500 text-white transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
              >
                {deleting ? "Apagando..." : "Sim, apagar tudo"}
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <div className="flex items-center gap-3">
            <h1 className="text-2xl font-black text-white">Escritórios Virais</h1>
            {totalPending > 0 && (
              <span className="text-xs font-bold px-2.5 py-1 rounded-full bg-yellow-500/20 text-yellow-400 border border-yellow-500/30 animate-pulse">
                {totalPending} pendente{totalPending > 1 ? "s" : ""}
              </span>
            )}
          </div>
          <p className="text-white/40 text-sm mt-1">Gerencie seus escritórios autônomos de conteúdo.</p>
        </div>
        <Link
          href="/dashboard/escritorios/novo"
          className="px-4 py-2.5 bg-violet-600 hover:bg-violet-500 text-white text-sm font-semibold rounded-xl transition-colors"
        >
          + Novo Escritório
        </Link>
      </div>

      {/* Content */}
      {loading ? (
        <div className="card-glass rounded-2xl p-12 text-center text-white/30 text-sm animate-pulse">
          Carregando escritórios...
        </div>
      ) : offices.length === 0 ? (
        <div className="card-glass rounded-2xl p-16 text-center">
          <div className="text-5xl mb-4">🏢</div>
          <h3 className="text-xl font-bold text-white mb-2">Nenhum escritório ainda</h3>
          <p className="text-white/40 text-sm max-w-sm mx-auto mb-6">
            Crie seu primeiro escritório viral e deixe os agentes de IA trabalharem por você 24/7.
          </p>
          <Link
            href="/dashboard/escritorios/novo"
            className="inline-block px-6 py-3 bg-violet-600 hover:bg-violet-500 text-white font-semibold rounded-xl transition-colors"
          >
            Criar Escritório Agora
          </Link>
        </div>
      ) : (
        <div className="grid md:grid-cols-2 gap-4">
          {offices.map(o => (
            <div key={o.id} className="card-glass rounded-2xl p-6 flex flex-col gap-4 relative">
              {/* Pending badge */}
              {(o.pending_decisions ?? 0) > 0 && (
                <div className="absolute top-4 right-14">
                  <span className="text-[10px] font-bold px-2 py-0.5 rounded-full bg-yellow-500/20 text-yellow-400 border border-yellow-500/30 animate-pulse">
                    {o.pending_decisions} pendente{o.pending_decisions > 1 ? "s" : ""}
                  </span>
                </div>
              )}

              {/* Delete button */}
              <button
                onClick={() => setConfirmDelete(o)}
                className="absolute top-4 right-4 w-8 h-8 flex items-center justify-center rounded-lg text-white/20 hover:text-red-400 hover:bg-red-500/10 transition-all"
                title="Apagar escritório"
              >
                <svg xmlns="http://www.w3.org/2000/svg" width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                  <polyline points="3 6 5 6 21 6"/><path d="M19 6l-1 14a2 2 0 01-2 2H8a2 2 0 01-2-2L5 6"/><path d="M10 11v6"/><path d="M14 11v6"/><path d="M9 6V4a1 1 0 011-1h4a1 1 0 011 1v2"/>
                </svg>
              </button>

              {/* Office info */}
              <div className="flex items-start justify-between pr-10">
                <div className="flex-1 min-w-0">
                  <h3 className="font-bold text-white truncate">{o.name}</h3>
                  <p className="text-white/40 text-sm">{o.niche}</p>
                  {o.platforms?.length > 0 && (
                    <div className="flex gap-1.5 mt-2">
                      {o.platforms.slice(0, 5).map(p => (
                        <span key={p} className="text-sm" title={p}>{PLATFORM_ICONS[p] ?? "🌐"}</span>
                      ))}
                    </div>
                  )}
                </div>
              </div>

              {/* Status + stats */}
              <div className="flex items-center gap-2">
                <span className={`text-xs font-semibold px-2.5 py-1 rounded-full border
                  ${o.status === "active"
                    ? "bg-emerald-500/15 text-emerald-400 border-emerald-500/30"
                    : "bg-yellow-500/10 text-yellow-400/60 border-yellow-500/20"}`}
                >
                  {o.status === "active" ? "● Ativo" : "⏸ Pausado"}
                </span>
              </div>

              <div className="grid grid-cols-3 gap-2 text-center">
                {[
                  ["Conteúdos", o.content_count ?? 0, "text-white"],
                  ["Publicados", o.published_count ?? 0, "text-violet-400"],
                  ["Virais", o.viral_count ?? 0, "text-emerald-400"],
                ].map(([label, val, color]) => (
                  <div key={label as string} className="bg-white/[0.03] rounded-xl py-3">
                    <p className={`text-lg font-bold ${color}`}>{val}</p>
                    <p className="text-white/30 text-xs">{label}</p>
                  </div>
                ))}
              </div>

              <Link
                href={`/dashboard/escritorios/${o.id}`}
                className="w-full text-center py-2.5 rounded-xl text-sm font-semibold bg-violet-600/20 border border-violet-500/30 text-violet-300 hover:bg-violet-600/30 transition-colors"
              >
                Gerenciar →
              </Link>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
