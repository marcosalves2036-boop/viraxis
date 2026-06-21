"use client";

import { useEffect, useState } from "react";

interface Decision {
  id: string;
  content_topic: string;
  content_format: string;
  target_platform: string;
  confidence_score: number;
  created_at: string;
  office_id?: string;
  office_name?: string;
}

interface Office {
  id: string;
  name: string;
  niche: string;
  platforms: string[];
  content_count: number;
}

const PLATFORM_COLORS: Record<string, string> = {
  tiktok: "from-pink-500 to-red-500",
  instagram: "from-purple-500 to-pink-500",
  youtube: "from-red-500 to-orange-500",
  twitter: "from-sky-500 to-blue-500",
  kwai: "from-orange-500 to-yellow-500",
};

const PLATFORM_ICONS: Record<string, string> = {
  tiktok: "🎵", instagram: "📸", youtube: "▶️", twitter: "🐦", kwai: "📱",
};

const PERIODS = ["7 dias", "30 dias", "3 meses", "Tudo"];

export default function AnaliticosPage() {
  const [period, setPeriod] = useState("30 dias");
  const [offices, setOffices] = useState<Office[]>([]);
  const [decisions, setDecisions] = useState<Decision[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    const token = localStorage.getItem("viraxis_token");
    if (!token) return;
    const h = { Authorization: `Bearer ${token}` };

    fetch("/api/offices", { headers: h })
      .then(r => r.json())
      .then(async (offs: Office[]) => {
        if (!Array.isArray(offs)) return;
        setOffices(offs);
        const all: Decision[] = [];
        for (const o of offs) {
          try {
            const r = await fetch(`/api/offices/${o.id}/decisions`, { headers: h });
            if (r.ok) {
              const decs: Decision[] = await r.json();
              decs.forEach(d => { d.office_id = o.id; d.office_name = o.name; });
              all.push(...decs);
            }
          } catch {}
        }
        all.sort((a, b) => b.created_at.localeCompare(a.created_at));
        setDecisions(all);
      })
      .catch(() => {})
      .finally(() => setLoading(false));
  }, []);

  const now = new Date();
  const filtered = decisions.filter(d => {
    if (period === "Tudo" || !d.created_at) return true;
    const days = period === "7 dias" ? 7 : period === "30 dias" ? 30 : 90;
    const diff = (now.getTime() - new Date(d.created_at).getTime()) / 86400000;
    return diff <= days;
  });

  const platformCounts = filtered.reduce<Record<string, number>>((acc, d) => {
    if (d.target_platform) acc[d.target_platform] = (acc[d.target_platform] || 0) + 1;
    return acc;
  }, {});

  const avgConf = filtered.length
    ? filtered.reduce((s, d) => s + (d.confidence_score || 0), 0) / filtered.length
    : 0;

  const last14 = Array.from({ length: 14 }, (_, i) => {
    const d = new Date();
    d.setDate(d.getDate() - (13 - i));
    const key = d.toISOString().slice(0, 10);
    const count = decisions.filter(dec => dec.created_at?.slice(0, 10) === key).length;
    return { day: d.toLocaleDateString("pt-BR", { day: "2-digit", month: "2-digit" }), count };
  });
  const maxBar = Math.max(...last14.map(d => d.count), 1);

  const topTopics = [...filtered]
    .sort((a, b) => (b.confidence_score || 0) - (a.confidence_score || 0))
    .slice(0, 5);

  const metrics = [
    { label: "Escritórios ativos", value: offices.length, icon: "🏢", color: "from-violet-500 to-violet-700" },
    { label: "Decisões do BRAIN", value: filtered.length, icon: "🧠", color: "from-cyan-500 to-cyan-700" },
    { label: "Confiança média", value: `${Math.round(avgConf * 100)}%`, icon: "🎯", color: "from-emerald-500 to-emerald-700" },
    { label: "Plataformas ativas", value: Object.keys(platformCounts).length, icon: "📡", color: "from-rose-500 to-rose-700" },
  ];

  return (
    <div className="max-w-5xl mx-auto space-y-6">
      <div className="flex items-center justify-between flex-wrap gap-3">
        <div>
          <h1 className="text-2xl font-black text-white">Analíticos</h1>
          <p className="text-white/40 text-sm mt-1">Acompanhe o desempenho do seu sistema VIRAXIS.</p>
        </div>
        <div className="flex gap-2 flex-wrap">
          {PERIODS.map(p => (
            <button key={p} onClick={() => setPeriod(p)}
              className={`px-3 py-1.5 rounded-xl text-sm font-medium border transition-all
                ${period === p ? "bg-violet-600/20 border-violet-500/30 text-violet-300"
                  : "bg-white/[0.04] border-white/10 text-white/50 hover:border-white/20"}`}>
              {p}
            </button>
          ))}
        </div>
      </div>

      <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
        {metrics.map(m => (
          <div key={m.label} className="card-glass rounded-2xl p-5">
            <span className="text-xl block mb-3">{m.icon}</span>
            <p className={`text-3xl font-black bg-gradient-to-r ${m.color} bg-clip-text text-transparent`}>{m.value}</p>
            <p className="text-white/40 text-xs mt-1">{m.label}</p>
          </div>
        ))}
      </div>

      {loading ? (
        <div className="card-glass rounded-2xl p-12 text-center text-white/30 text-sm">Carregando dados...</div>
      ) : decisions.length === 0 ? (
        <div className="card-glass rounded-2xl p-16 text-center">
          <div className="text-5xl mb-4">📊</div>
          <h3 className="text-xl font-bold text-white mb-2">Sem dados ainda</h3>
          <p className="text-white/40 text-sm max-w-sm mx-auto">
            Crie um escritório e execute o agente BRAIN para gerar decisões de conteúdo.
          </p>
        </div>
      ) : (
        <>
          <div className="card-glass rounded-2xl p-6">
            <h2 className="font-bold text-white mb-5">Atividade do BRAIN — últimos 14 dias</h2>
            <div className="flex items-end gap-1 h-32">
              {last14.map(({ day, count }) => (
                <div key={day} className="flex-1 flex flex-col items-center gap-1 group">
                  <div className="relative w-full flex flex-col justify-end" style={{ height: "112px" }}>
                    {count > 0 && (
                      <div className="absolute -top-5 left-1/2 -translate-x-1/2 text-[10px] text-white/60 opacity-0 group-hover:opacity-100 transition-opacity whitespace-nowrap">{count}</div>
                    )}
                    <div
                      className="w-full rounded-sm transition-all"
                      style={{
                        height: `${Math.max((count / maxBar) * 112, count > 0 ? 6 : 2)}px`,
                        background: count > 0 ? "linear-gradient(to top, #7c3aed, #a855f7)" : "rgba(255,255,255,0.05)",
                      }}
                    />
                  </div>
                  <p className="text-white/20 text-[9px] whitespace-nowrap">{day}</p>
                </div>
              ))}
            </div>
          </div>

          <div className="grid md:grid-cols-2 gap-4">
            <div className="card-glass rounded-2xl p-6">
              <h2 className="font-bold text-white mb-4">Distribuição por plataforma</h2>
              {Object.keys(platformCounts).length === 0 ? (
                <p className="text-white/25 text-sm text-center py-6">Nenhuma plataforma</p>
              ) : (
                <div className="space-y-3">
                  {Object.entries(platformCounts).sort(([,a],[,b]) => b-a).map(([platform, count]) => {
                    const pct = Math.round((count / filtered.length) * 100);
                    return (
                      <div key={platform}>
                        <div className="flex items-center justify-between mb-1">
                          <span className="text-white/70 text-sm">{PLATFORM_ICONS[platform] ?? "🌐"} {platform}</span>
                          <span className="text-white/40 text-xs">{count} ({pct}%)</span>
                        </div>
                        <div className="h-2 bg-white/[0.06] rounded-full overflow-hidden">
                          <div className={`h-full rounded-full bg-gradient-to-r ${PLATFORM_COLORS[platform] ?? "from-violet-500 to-violet-700"}`}
                            style={{ width: `${pct}%` }} />
                        </div>
                      </div>
                    );
                  })}
                </div>
              )}
            </div>

            <div className="card-glass rounded-2xl p-6">
              <h2 className="font-bold text-white mb-4">Top decisões por confiança</h2>
              {topTopics.length === 0 ? (
                <p className="text-white/25 text-sm text-center py-6">Nenhuma decisão</p>
              ) : (
                <div className="space-y-3">
                  {topTopics.map((d, i) => (
                    <div key={d.id} className="flex items-center gap-3">
                      <span className="text-white/20 text-sm font-bold w-5 shrink-0">#{i+1}</span>
                      <div className="flex-1 min-w-0">
                        <p className="text-white/80 text-sm truncate">{d.content_topic || "—"}</p>
                        <p className="text-white/30 text-xs">{PLATFORM_ICONS[d.target_platform] ?? "🌐"} {d.target_platform}{d.office_name ? ` · ${d.office_name}` : ""}</p>
                      </div>
                      <span className="text-violet-400 font-bold text-sm shrink-0">{Math.round((d.confidence_score||0)*100)}%</span>
                    </div>
                  ))}
                </div>
              )}
            </div>
          </div>
        </>
      )}
    </div>
  );
}
