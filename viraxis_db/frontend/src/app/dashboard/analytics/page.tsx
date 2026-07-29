"use client";

import { useEffect, useState, useCallback, Suspense } from "react";
import { useSearchParams } from "next/navigation";
import { auth } from "@/lib/api";
import {
  ResponsiveContainer,
  LineChart,
  Line,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
} from "recharts";

// ── Types ─────────────────────────────────────────────────────────────────────

interface PlatformCount {
  platform: string;
  count: number;
}

interface AnalyticsSummary {
  total_videos: number;
  ready_count: number;
  approval_rate: number;
  total_publications: number;
  platforms_active: PlatformCount[];
}

interface TimelinePoint {
  date: string;
  count: number;
}

interface PublicationRow {
  content_item_id: string;
  office_id: string;
  title: string;
  platform: string | null;
  external_id: string | null;
  url: string | null;
  published_at: string | null;
  content_status: string;
}

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

const PLATFORM_ICONS: Record<string, string> = {
  tiktok: "🎵",
  instagram: "📸",
  youtube: "▶️",
  twitter: "🐦",
  kwai: "📱",
  facebook: "👥",
};

const PLATFORM_COLORS: Record<string, string> = {
  tiktok: "from-pink-500 to-red-500",
  instagram: "from-purple-500 to-pink-500",
  youtube: "from-red-500 to-orange-500",
  twitter: "from-sky-500 to-blue-500",
  kwai: "from-orange-500 to-yellow-500",
};

const STATUS_LABELS: Record<string, string> = {
  draft: "Rascunho",
  rendering: "Renderizando",
  review: "Em revisão",
  ready: "Pronto",
  published: "Publicado",
  failed: "Falhou",
};

const STATUS_COLORS: Record<string, string> = {
  draft: "bg-white/10 text-white/50 border-white/10",
  rendering: "bg-amber-500/15 text-amber-300 border-amber-500/25",
  review: "bg-sky-500/15 text-sky-300 border-sky-500/25",
  ready: "bg-emerald-500/15 text-emerald-300 border-emerald-500/25",
  published: "bg-violet-500/15 text-violet-300 border-violet-500/25",
  failed: "bg-red-500/15 text-red-300 border-red-500/25",
};

const PERIODS = ["7 dias", "30 dias", "3 meses", "Tudo"];

function fmtDateShort(iso: string): string {
  // iso = "YYYY-MM-DD"
  const [, m, d] = iso.split("-");
  return `${d}/${m}`;
}

function fmtDateTime(iso: string | null): string {
  if (!iso) return "—";
  try {
    return new Date(iso).toLocaleString("pt-BR", {
      day: "2-digit",
      month: "2-digit",
      year: "2-digit",
      hour: "2-digit",
      minute: "2-digit",
    });
  } catch {
    return iso;
  }
}

type TabKey = "performance" | "decisoes";

const TABS: { key: TabKey; label: string; icon: string }[] = [
  { key: "performance", label: "Performance", icon: "📈" },
  { key: "decisoes", label: "Decisões Editoriais", icon: "🧠" },
];

// ── Aba: Performance (ex /dashboard/analytics) ───────────────────────────────

function PerformanceTab() {
  const [summary, setSummary] = useState<AnalyticsSummary | null>(null);
  const [timeline, setTimeline] = useState<TimelinePoint[]>([]);
  const [publications, setPublications] = useState<PublicationRow[]>([]);
  const [loadingSummary, setLoadingSummary] = useState(true);
  const [loadingTimeline, setLoadingTimeline] = useState(true);
  const [loadingPublications, setLoadingPublications] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [days, setDays] = useState(30);

  const loadData = useCallback(async (selectedDays: number) => {
    const token = auth.getToken();
    if (!token) {
      setError("Sessão expirada. Faça login novamente.");
      setLoadingSummary(false);
      setLoadingTimeline(false);
      setLoadingPublications(false);
      return;
    }
    const headers = { Authorization: `Bearer ${token}` };
    setError(null);

    setLoadingSummary(true);
    fetch("/api/analytics/summary", { headers })
      .then(async (r) => {
        if (!r.ok) throw new Error((await r.json().catch(() => ({}))).detail ?? "Erro ao carregar resumo");
        return r.json();
      })
      .then((data: AnalyticsSummary) => setSummary(data))
      .catch((e: Error) => setError((prev) => prev ?? e.message))
      .finally(() => setLoadingSummary(false));

    setLoadingTimeline(true);
    fetch(`/api/analytics/timeline?days=${selectedDays}`, { headers })
      .then(async (r) => {
        if (!r.ok) throw new Error((await r.json().catch(() => ({}))).detail ?? "Erro ao carregar série temporal");
        return r.json();
      })
      .then((data: TimelinePoint[]) => setTimeline(Array.isArray(data) ? data : []))
      .catch((e: Error) => setError((prev) => prev ?? e.message))
      .finally(() => setLoadingTimeline(false));

    setLoadingPublications(true);
    fetch("/api/analytics/publications?limit=20", { headers })
      .then(async (r) => {
        if (!r.ok) throw new Error((await r.json().catch(() => ({}))).detail ?? "Erro ao carregar publicações");
        return r.json();
      })
      .then((data: PublicationRow[]) => setPublications(Array.isArray(data) ? data : []))
      .catch((e: Error) => setError((prev) => prev ?? e.message))
      .finally(() => setLoadingPublications(false));
  }, []);

  useEffect(() => {
    loadData(days);
  }, [loadData, days]);

  const chartData = timeline.map((p) => ({ ...p, label: fmtDateShort(p.date) }));

  const kpis = [
    {
      label: "Vídeos gerados",
      value: summary ? summary.total_videos : "—",
      icon: "🎬",
      color: "from-violet-500 to-violet-700",
    },
    {
      label: "Taxa de aprovação",
      value: summary ? `${summary.approval_rate}%` : "—",
      icon: "✅",
      color: "from-emerald-500 to-emerald-700",
    },
    {
      label: "Publicações totais",
      value: summary ? summary.total_publications : "—",
      icon: "📤",
      color: "from-cyan-500 to-cyan-700",
    },
    {
      label: "Plataformas ativas",
      value: summary ? summary.platforms_active.length : "—",
      icon: "📡",
      color: "from-rose-500 to-rose-700",
    },
  ];

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-end flex-wrap gap-3">
        <div className="flex gap-2 flex-wrap">
          {[7, 30, 90].map((d) => (
            <button
              key={d}
              onClick={() => setDays(d)}
              className={`px-3 py-1.5 rounded-xl text-sm font-medium border transition-all
                ${
                  days === d
                    ? "bg-violet-600/20 border-violet-500/30 text-violet-300"
                    : "bg-white/[0.04] border-white/10 text-white/50 hover:border-white/20"
                }`}
            >
              {d} dias
            </button>
          ))}
        </div>
      </div>

      {error && (
        <div className="card-glass rounded-2xl p-4 border border-red-500/30 bg-red-500/5">
          <p className="text-red-300 text-sm">{error}</p>
        </div>
      )}

      {/* KPI Cards */}
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
        {kpis.map((k) => (
          <div key={k.label} className="card-glass rounded-2xl p-5">
            <span className="text-xl block mb-3">{k.icon}</span>
            {loadingSummary ? (
              <div className="h-9 w-16 rounded bg-white/[0.06] animate-pulse" />
            ) : (
              <p
                className={`text-3xl font-black bg-gradient-to-r ${k.color} bg-clip-text text-transparent`}
              >
                {k.value}
              </p>
            )}
            <p className="text-white/40 text-xs mt-1">{k.label}</p>
          </div>
        ))}
      </div>

      {/* Plataformas ativas — detalhamento */}
      {!loadingSummary && summary && summary.platforms_active.length > 0 && (
        <div className="card-glass rounded-2xl p-5">
          <h2 className="font-bold text-white mb-3 text-sm">Contas ativas por plataforma</h2>
          <div className="flex gap-3 flex-wrap">
            {summary.platforms_active.map((p) => (
              <div
                key={p.platform}
                className="flex items-center gap-2 px-3 py-1.5 rounded-xl bg-white/[0.04] border border-white/10"
              >
                <span>{PLATFORM_ICONS[p.platform] ?? "🌐"}</span>
                <span className="text-white/70 text-sm capitalize">{p.platform}</span>
                <span className="text-white/40 text-xs">({p.count})</span>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Gráfico de linha — vídeos por dia */}
      <div className="card-glass rounded-2xl p-6">
        <h2 className="font-bold text-white mb-5">
          Vídeos gerados por dia — últimos {days} dias
        </h2>
        {loadingTimeline ? (
          <div className="h-64 rounded-xl bg-white/[0.03] animate-pulse" />
        ) : chartData.every((p) => p.count === 0) ? (
          <div className="h-64 flex items-center justify-center text-white/25 text-sm">
            Nenhum vídeo gerado no período selecionado.
          </div>
        ) : (
          <ResponsiveContainer width="100%" height={280}>
            <LineChart data={chartData} margin={{ top: 8, right: 16, left: -16, bottom: 0 }}>
              <CartesianGrid strokeDasharray="3 3" stroke="rgba(255,255,255,0.06)" />
              <XAxis
                dataKey="label"
                stroke="rgba(255,255,255,0.3)"
                fontSize={11}
                tickLine={false}
                axisLine={false}
                interval={days > 30 ? Math.floor(days / 15) : "preserveStartEnd"}
              />
              <YAxis
                allowDecimals={false}
                stroke="rgba(255,255,255,0.3)"
                fontSize={11}
                tickLine={false}
                axisLine={false}
                width={28}
              />
              <Tooltip
                contentStyle={{
                  background: "rgba(10,10,14,0.95)",
                  border: "1px solid rgba(255,255,255,0.1)",
                  borderRadius: "12px",
                  fontSize: "12px",
                  color: "#fff",
                }}
                labelStyle={{ color: "rgba(255,255,255,0.6)" }}
                formatter={(value: number) => [value, "vídeos"]}
              />
              <Line
                type="monotone"
                dataKey="count"
                stroke="#a855f7"
                strokeWidth={2.5}
                dot={{ r: 2, fill: "#a855f7" }}
                activeDot={{ r: 5 }}
              />
            </LineChart>
          </ResponsiveContainer>
        )}
      </div>

      {/* Tabela de publicações recentes */}
      <div className="card-glass rounded-2xl p-6">
        <h2 className="font-bold text-white mb-5">Últimas publicações</h2>
        {loadingPublications ? (
          <div className="space-y-2">
            {[...Array(4)].map((_, i) => (
              <div key={i} className="h-10 rounded-lg bg-white/[0.03] animate-pulse" />
            ))}
          </div>
        ) : publications.length === 0 ? (
          <div className="text-center py-10">
            <div className="text-4xl mb-3">📤</div>
            <p className="text-white/40 text-sm">
              Nenhuma publicação registrada ainda. Publique um ContentItem para ver o
              histórico aqui.
            </p>
          </div>
        ) : (
          <div className="overflow-x-auto -mx-2">
            <table className="w-full text-sm">
              <thead>
                <tr className="text-left text-white/30 text-xs uppercase tracking-wide">
                  <th className="px-2 py-2 font-medium">Título</th>
                  <th className="px-2 py-2 font-medium">Plataforma</th>
                  <th className="px-2 py-2 font-medium">Status</th>
                  <th className="px-2 py-2 font-medium">Publicado em</th>
                  <th className="px-2 py-2 font-medium">Link</th>
                </tr>
              </thead>
              <tbody>
                {publications.map((p, i) => (
                  <tr
                    key={`${p.content_item_id}-${p.platform}-${i}`}
                    className="border-t"
                    style={{ borderColor: "var(--border)" }}
                  >
                    <td className="px-2 py-2.5 text-white/80 max-w-[220px] truncate">
                      {p.title}
                    </td>
                    <td className="px-2 py-2.5 text-white/60">
                      {PLATFORM_ICONS[p.platform ?? ""] ?? "🌐"}{" "}
                      <span className="capitalize">{p.platform ?? "—"}</span>
                    </td>
                    <td className="px-2 py-2.5">
                      <span
                        className={`px-2 py-0.5 rounded-full text-xs border ${
                          STATUS_COLORS[p.content_status] ?? "bg-white/10 text-white/50 border-white/10"
                        }`}
                      >
                        {STATUS_LABELS[p.content_status] ?? p.content_status}
                      </span>
                    </td>
                    <td className="px-2 py-2.5 text-white/50 text-xs whitespace-nowrap">
                      {fmtDateTime(p.published_at)}
                    </td>
                    <td className="px-2 py-2.5">
                      {p.url ? (
                        <a
                          href={p.url}
                          target="_blank"
                          rel="noopener noreferrer"
                          className="text-violet-400 hover:text-violet-300 text-xs"
                        >
                          Abrir ↗
                        </a>
                      ) : (
                        <span className="text-white/20 text-xs">—</span>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </div>
  );
}

// ── Aba: Decisões Editoriais (ex /dashboard/analiticos) ─────────────────────

function DecisoesTab() {
  const [period, setPeriod] = useState("30 dias");
  const [offices, setOffices] = useState<Office[]>([]);
  const [decisions, setDecisions] = useState<Decision[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    const token = localStorage.getItem("viraxis_token");
    if (!token) {
      setLoading(false);
      return;
    }
    const h = { Authorization: `Bearer ${token}` };

    fetch("/api/offices", { headers: h })
      .then((r) => r.json())
      .then(async (offs: Office[]) => {
        if (!Array.isArray(offs)) return;
        setOffices(offs);
        const all: Decision[] = [];
        for (const o of offs) {
          try {
            const r = await fetch(`/api/offices/${o.id}/decisions`, { headers: h });
            if (r.ok) {
              const decs: Decision[] = await r.json();
              decs.forEach((d) => {
                d.office_id = o.id;
                d.office_name = o.name;
              });
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
  const filtered = decisions.filter((d) => {
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
    const count = decisions.filter((dec) => dec.created_at?.slice(0, 10) === key).length;
    return { day: d.toLocaleDateString("pt-BR", { day: "2-digit", month: "2-digit" }), count };
  });
  const maxBar = Math.max(...last14.map((d) => d.count), 1);

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
    <div className="space-y-6">
      <div className="flex items-center justify-end flex-wrap gap-3">
        <div className="flex gap-2 flex-wrap">
          {PERIODS.map((p) => (
            <button
              key={p}
              onClick={() => setPeriod(p)}
              className={`px-3 py-1.5 rounded-xl text-sm font-medium border transition-all
                ${
                  period === p
                    ? "bg-violet-600/20 border-violet-500/30 text-violet-300"
                    : "bg-white/[0.04] border-white/10 text-white/50 hover:border-white/20"
                }`}
            >
              {p}
            </button>
          ))}
        </div>
      </div>

      <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
        {metrics.map((m) => (
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
                  {Object.entries(platformCounts).sort(([, a], [, b]) => b - a).map(([platform, count]) => {
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
                      <span className="text-white/20 text-sm font-bold w-5 shrink-0">#{i + 1}</span>
                      <div className="flex-1 min-w-0">
                        <p className="text-white/80 text-sm truncate">{d.content_topic || "—"}</p>
                        <p className="text-white/30 text-xs">{PLATFORM_ICONS[d.target_platform] ?? "🌐"} {d.target_platform}{d.office_name ? ` · ${d.office_name}` : ""}</p>
                      </div>
                      <span className="text-violet-400 font-bold text-sm shrink-0">{Math.round((d.confidence_score || 0) * 100)}%</span>
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

// ── Página consolidada ───────────────────────────────────────────────────────

function AnalyticsInner() {
  const searchParams = useSearchParams();
  const initialTab: TabKey = searchParams.get("tab") === "decisoes" ? "decisoes" : "performance";
  const [tab, setTab] = useState<TabKey>(initialTab);

  return (
    <div className="max-w-5xl mx-auto space-y-6">
      <div className="flex items-center justify-between flex-wrap gap-3">
        <div>
          <h1 className="text-2xl font-black text-white">Analytics</h1>
          <p className="text-white/40 text-sm mt-1">
            Desempenho do pipeline de conteúdo e decisões editoriais do agente BRAIN.
          </p>
        </div>
      </div>

      <div className="flex gap-2 border-b" style={{ borderColor: "var(--border)" }}>
        {TABS.map((t) => (
          <button
            key={t.key}
            onClick={() => setTab(t.key)}
            className={`px-4 py-2.5 text-sm font-medium border-b-2 -mb-px transition-all flex items-center gap-2
              ${
                tab === t.key
                  ? "border-violet-500 text-violet-300"
                  : "border-transparent text-white/40 hover:text-white/70"
              }`}
          >
            <span>{t.icon}</span>
            {t.label}
          </button>
        ))}
      </div>

      {tab === "performance" ? <PerformanceTab /> : <DecisoesTab />}
    </div>
  );
}

export default function AnalyticsPage() {
  return (
    <Suspense
      fallback={
        <div className="flex items-center justify-center min-h-[60vh]">
          <div className="text-white/30 animate-pulse text-sm">Carregando…</div>
        </div>
      }
    >
      <AnalyticsInner />
    </Suspense>
  );
}
