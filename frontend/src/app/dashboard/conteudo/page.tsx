"use client";

import Link from "next/link";
import { useEffect, useState } from "react";

interface Decision {
  id: string;
  content_topic: string;
  content_format: string;
  target_platform: string;
  confidence_score: number;
  created_at: string;
  office_name?: string;
  office_id?: string;
}

interface Office {
  id: string;
  name: string;
}

const PLATFORM_ICONS: Record<string, string> = {
  tiktok: "🎵", instagram: "📸", youtube: "▶️", twitter: "🐦", kwai: "📱",
};

const STATUS_FILTERS = ["Todos", "Pendente", "Aprovado", "Publicado"];

export default function ConteudoPage() {
  const [decisions, setDecisions] = useState<Decision[]>([]);
  const [loading, setLoading] = useState(true);
  const [filter, setFilter] = useState("Todos");

  useEffect(() => {
    const token = localStorage.getItem("viraxis_token");
    if (!token) return;
    const h = { Authorization: `Bearer ${token}` };

    // Fetch offices then fetch decisions per office
    fetch("/api/offices", { headers: h })
      .then(r => r.json())
      .then(async (offices: Office[]) => {
        if (!Array.isArray(offices) || offices.length === 0) return;
        const all: Decision[] = [];
        for (const office of offices) {
          try {
            const r = await fetch(`/api/offices/${office.id}/decisions`, { headers: h });
            if (r.ok) {
              const decs: Decision[] = await r.json();
              decs.forEach(d => { d.office_name = office.name; d.office_id = office.id; });
              all.push(...decs);
            }
          } catch {}
        }
        // Sort by most recent
        all.sort((a, b) => b.created_at.localeCompare(a.created_at));
        setDecisions(all);
      })
      .catch(() => {})
      .finally(() => setLoading(false));
  }, []);

  const filtered = decisions; // status filtering would require backend support

  return (
    <div className="max-w-5xl mx-auto space-y-6">
      <div>
        <h1 className="text-2xl font-black text-white">Conteúdo</h1>
        <p className="text-white/40 text-sm mt-1">Revise e publique os conteúdos gerados pelos agentes.</p>
      </div>

      {/* Filters */}
      <div className="flex flex-wrap gap-2">
        {STATUS_FILTERS.map(f => (
          <button
            key={f}
            onClick={() => setFilter(f)}
            className={`px-4 py-2 rounded-xl text-sm font-medium border transition-all
              ${filter === f
                ? "bg-violet-600/20 border-violet-500/30 text-violet-300"
                : "bg-white/[0.04] border-white/10 text-white/50 hover:border-white/20"}`}
          >
            {f}
          </button>
        ))}
      </div>

      {loading ? (
        <div className="card-glass rounded-2xl p-12 text-center text-white/30 text-sm">Carregando...</div>
      ) : filtered.length === 0 ? (
        <div className="card-glass rounded-2xl p-16 text-center">
          <div className="text-5xl mb-4">📹</div>
          <h3 className="text-xl font-bold text-white mb-2">Nenhum conteúdo ainda</h3>
          <p className="text-white/40 text-sm max-w-sm mx-auto mb-6">
            Crie um escritório e ative o agente BRAIN para começar a gerar conteúdo viral automaticamente.
          </p>
          <Link
            href="/dashboard/escritorios"
            className="inline-block px-6 py-3 bg-violet-600 hover:bg-violet-500 text-white font-semibold rounded-xl transition-colors"
          >
            Ir para Escritórios →
          </Link>
        </div>
      ) : (
        <div className="space-y-3">
          {filtered.map(d => (
            <div key={d.id} className="card-glass rounded-2xl p-5 flex items-center gap-4">
              <div className="text-2xl shrink-0">
                {PLATFORM_ICONS[d.target_platform] ?? "📄"}
              </div>
              <div className="flex-1 min-w-0">
                <p className="text-white font-semibold text-sm truncate">{d.content_topic || "Tópico a definir"}</p>
                <p className="text-white/40 text-xs mt-0.5">
                  {d.content_format.replace("_", " ")}
                  {d.office_name && ` · ${d.office_name}`}
                  {d.created_at && ` · ${new Date(d.created_at).toLocaleDateString("pt-BR")}`}
                </p>
              </div>
              <div className="text-right shrink-0">
                <p className="text-violet-400 font-bold text-sm">{Math.round((d.confidence_score ?? 0) * 100)}%</p>
                <p className="text-white/30 text-xs">confiança</p>
              </div>
              {d.office_id && (
                <Link
                  href={`/dashboard/escritorios/${d.office_id}`}
                  className="shrink-0 px-3 py-1.5 rounded-lg bg-white/[0.04] border border-white/10 text-white/50 text-xs hover:text-white/70 hover:border-white/20 transition-colors"
                >
                  Ver →
                </Link>
              )}
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
