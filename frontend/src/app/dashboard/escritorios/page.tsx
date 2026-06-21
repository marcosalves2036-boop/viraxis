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

  useEffect(() => {
    const token = localStorage.getItem("viraxis_token");
    if (!token) return;
    fetch("/api/offices", { headers: { Authorization: `Bearer ${token}` } })
      .then(r => r.json())
      .then(data => { if (Array.isArray(data)) setOffices(data); })
      .catch(() => {})
      .finally(() => setLoading(false));
  }, []);

  const totalPending = offices.reduce((s, o) => s + (o.pending_decisions ?? 0), 0);

  return (
    <div className="max-w-5xl mx-auto space-y-6">
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
                <div className="absolute top-4 right-4">
                  <span className="text-[10px] font-bold px-2 py-0.5 rounded-full bg-yellow-500/20 text-yellow-400 border border-yellow-500/30 animate-pulse">
                    {o.pending_decisions} pendente{o.pending_decisions > 1 ? "s" : ""}
                  </span>
                </div>
              )}

              {/* Office info */}
              <div className="flex items-start justify-between pr-20">
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
