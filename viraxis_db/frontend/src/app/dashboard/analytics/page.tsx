"use client";

import { useEffect, useState, useCallback } from "react";
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

const PLATFORM_ICONS: Record<string, string> = {
  tiktok: "🎵",
  instagram: "📸",
  youtube: "▶️",
  twitter: "🐦",
  kwai: "📱",
  facebook: "👥",
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

// ── Componente principal ─────────────────────────────────────────────────────

export default function AnalyticsPage() {
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
    <div className="max-w-5xl mx-auto space-y-6">
      <div className="flex items-center justify-between flex-wrap gap-3">
        <div>
          <h1 className="text-2xl font-black text-white">Analytics</h1>
          <p className="text-white/40 text-sm mt-1">
            Desempenho do pipeline de conteúdo — vídeos, aprovações e publicações.
          </p>
        </div>
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
