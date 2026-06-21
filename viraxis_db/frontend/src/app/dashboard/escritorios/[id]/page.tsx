"use client";

import { useEffect, useState, useCallback } from "react";
import { useParams, useRouter } from "next/navigation";
import { auth } from "@/lib/api";

// ── Types ─────────────────────────────────────────────────────────────────────

interface Office {
  id: string; name: string; niche: string; status: string;
  platforms: string[]; target_audience: string; content_style: string;
  content_count: number; published_count: number; viral_count: number;
  pending_decisions: number;
}

interface Decision {
  id: string; decision_type: string; status: string;
  content_topic: string; content_format: string;
  target_platform: string; selected_archetype: string;
  confidence_score: number; hypothesis: string;
  reasoning: Record<string, unknown>; input_signals: Record<string, unknown>;
  created_at: string; updated_at: string;
}

// ── Constants ─────────────────────────────────────────────────────────────────

const PLATFORM_ICONS: Record<string, string> = {
  tiktok: "🎵", instagram: "📸", youtube: "▶️", twitter: "🐦",
  linkedin: "💼", facebook: "👥", pinterest: "📌", default: "🌐",
};

const STATUS_STYLES: Record<string, string> = {
  pending:   "bg-yellow-500/15 text-yellow-400 border-yellow-500/30",
  approved:  "bg-emerald-500/15 text-emerald-400 border-emerald-500/30",
  executing: "bg-blue-500/15 text-blue-400 border-blue-500/30",
  done:      "bg-violet-500/15 text-violet-400 border-violet-500/30",
  rejected:  "bg-red-500/15 text-red-400 border-red-500/30",
  failed:    "bg-red-700/15 text-red-500 border-red-700/30",
};

const STATUS_LABELS: Record<string, string> = {
  pending: "⏳ Pendente", approved: "✅ Aprovada", executing: "⚙️ Executando",
  done: "🎯 Concluída", rejected: "❌ Rejeitada", failed: "💥 Falhou",
};

const STATUS_FILTERS = ["todos", "pending", "approved", "done", "rejected"];

function ConfidenceGauge({ score }: { score: number }) {
  const pct = Math.round(score * 100);
  const color = pct >= 75 ? "#10b981" : pct >= 50 ? "#f59e0b" : "#ef4444";
  const r = 28, circ = 2 * Math.PI * r;
  const dash = (pct / 100) * circ;
  return (
    <div className="flex flex-col items-center gap-1">
      <svg width="72" height="72" viewBox="0 0 72 72">
        <circle cx="36" cy="36" r={r} fill="none" stroke="rgba(255,255,255,0.06)" strokeWidth="6" />
        <circle cx="36" cy="36" r={r} fill="none" stroke={color} strokeWidth="6"
          strokeDasharray={`${dash} ${circ}`} strokeLinecap="round"
          transform="rotate(-90 36 36)" style={{ transition: "stroke-dasharray 0.6s ease" }}
        />
        <text x="36" y="41" textAnchor="middle" fill="white" fontSize="14" fontWeight="bold">{pct}%</text>
      </svg>
      <span className="text-white/30 text-[10px]">confiança</span>
    </div>
  );
}

// ── Decision Detail Modal ─────────────────────────────────────────────────────

function DecisionModal({
  decision, officeId, onClose, onStatusChange,
}: {
  decision: Decision; officeId: string;
  onClose: () => void; onStatusChange: (d: Decision) => void;
}) {
  const [loading, setLoading] = useState<string | null>(null);
  const token = typeof window !== "undefined" ? localStorage.getItem("viraxis_token") : null;

  async function patchStatus(newStatus: string) {
    setLoading(newStatus);
    try {
      const r = await fetch(`/api/offices/${officeId}/decisions/${decision.id}`, {
        method: "PATCH",
        headers: { Authorization: `Bearer ${token}`, "Content-Type": "application/json" },
        body: JSON.stringify({ status: newStatus }),
      });
      if (r.ok) { onStatusChange(await r.json()); onClose(); }
    } finally { setLoading(null); }
  }

  const signals = decision.input_signals as Record<string, unknown>;
  const reasoning = decision.reasoning as Record<string, unknown>;

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4" onClick={onClose}>
      <div className="absolute inset-0 bg-black/70 backdrop-blur-sm" />
      <div
        className="relative w-full max-w-2xl max-h-[90vh] overflow-y-auto rounded-2xl border"
        style={{ background: "rgba(10,11,18,0.98)", borderColor: "var(--border)" }}
        onClick={e => e.stopPropagation()}
      >
        {/* Header */}
        <div className="flex items-start justify-between p-6 border-b" style={{ borderColor: "var(--border)" }}>
          <div className="flex-1 min-w-0 pr-4">
            <div className="flex items-center gap-2 mb-1 flex-wrap">
              <span className={`text-xs font-semibold px-2.5 py-1 rounded-full border ${STATUS_STYLES[decision.status] ?? ""}`}>
                {STATUS_LABELS[decision.status] ?? decision.status}
              </span>
              <span className="text-xs text-white/30">
                {PLATFORM_ICONS[decision.target_platform] ?? "🌐"} {decision.target_platform}
              </span>
            </div>
            <h2 className="text-lg font-bold text-white">{decision.content_topic || "Sem tópico"}</h2>
            <p className="text-white/30 text-xs mt-0.5">
              {new Date(decision.created_at).toLocaleString("pt-BR")}
            </p>
          </div>
          <ConfidenceGauge score={decision.confidence_score} />
        </div>

        {/* Body */}
        <div className="p-6 space-y-5">
          {/* Archetype */}
          {decision.selected_archetype && (
            <div>
              <p className="text-xs font-semibold text-white/40 uppercase tracking-wider mb-1.5">Archetype Viral</p>
              <span className="inline-block px-3 py-1.5 rounded-lg bg-violet-500/15 border border-violet-500/30 text-violet-300 text-sm font-medium">
                🎭 {decision.selected_archetype}
              </span>
            </div>
          )}

          {/* Hypothesis */}
          <div>
            <p className="text-xs font-semibold text-white/40 uppercase tracking-wider mb-2">💡 Hipótese do BRAIN</p>
            <div className="bg-white/[0.03] border border-white/[0.06] rounded-xl p-4">
              <p className="text-white/80 text-sm leading-relaxed">{decision.hypothesis}</p>
            </div>
          </div>

          {/* Reasoning */}
          {Object.keys(reasoning).length > 0 && (
            <div>
              <p className="text-xs font-semibold text-white/40 uppercase tracking-wider mb-2">🔍 Chain-of-Thought</p>
              <div className="bg-black/40 rounded-xl p-4 max-h-48 overflow-y-auto">
                <pre className="text-white/60 text-xs whitespace-pre-wrap font-mono leading-relaxed">
                  {JSON.stringify(reasoning, null, 2)}
                </pre>
              </div>
            </div>
          )}

          {/* Input Signals */}
          {Object.keys(signals).length > 0 && (
            <div>
              <p className="text-xs font-semibold text-white/40 uppercase tracking-wider mb-2">📡 Sinais de Input</p>
              <div className="grid grid-cols-2 gap-2">
                {signals.niche_name && (
                  <div className="bg-white/[0.03] rounded-lg p-3">
                    <p className="text-white/30 text-[10px] uppercase mb-1">Nicho</p>
                    <p className="text-white/70 text-xs">{String(signals.niche_name)}</p>
                  </div>
                )}
                {Array.isArray(signals.target_platforms) && (
                  <div className="bg-white/[0.03] rounded-lg p-3">
                    <p className="text-white/30 text-[10px] uppercase mb-1">Plataformas</p>
                    <p className="text-white/70 text-xs">{(signals.target_platforms as string[]).join(", ")}</p>
                  </div>
                )}
                {Array.isArray(signals.top_keywords) && (
                  <div className="bg-white/[0.03] rounded-lg p-3 col-span-2">
                    <p className="text-white/30 text-[10px] uppercase mb-1">Keywords em Alta</p>
                    <div className="flex flex-wrap gap-1 mt-1">
                      {(signals.top_keywords as string[]).slice(0, 6).map((k: string) => (
                        <span key={k} className="text-[10px] px-2 py-0.5 rounded bg-white/[0.06] text-white/50">{k}</span>
                      ))}
                    </div>
                  </div>
                )}
              </div>
            </div>
          )}
        </div>

        {/* Actions */}
        <div className="px-6 pb-6 flex flex-wrap gap-3">
          {decision.status === "pending" && (
            <>
              <button
                onClick={() => patchStatus("approved")}
                disabled={loading !== null}
                className="flex-1 py-2.5 bg-emerald-600 hover:bg-emerald-500 disabled:opacity-50 text-white text-sm font-bold rounded-xl transition-colors"
              >
                {loading === "approved" ? "..." : "✅ Aprovar"}
              </button>
              <button
                onClick={() => patchStatus("rejected")}
                disabled={loading !== null}
                className="flex-1 py-2.5 bg-red-600/30 hover:bg-red-600/50 border border-red-500/40 disabled:opacity-50 text-red-300 text-sm font-bold rounded-xl transition-colors"
              >
                {loading === "rejected" ? "..." : "❌ Rejeitar"}
              </button>
            </>
          )}
          {decision.status === "approved" && (
            <button
              onClick={() => patchStatus("executing")}
              disabled={loading !== null}
              className="flex-1 py-2.5 bg-blue-600 hover:bg-blue-500 disabled:opacity-50 text-white text-sm font-bold rounded-xl transition-colors"
            >
              {loading === "executing" ? "..." : "⚙️ Iniciar Execução"}
            </button>
          )}
          <button
            onClick={onClose}
            className="px-5 py-2.5 bg-white/[0.06] hover:bg-white/[0.10] text-white/60 text-sm rounded-xl transition-colors"
          >
            Fechar
          </button>
        </div>
      </div>
    </div>
  );
}

// ── Main Page ─────────────────────────────────────────────────────────────────

export default function OfficeDetailPage() {
  const { id } = useParams<{ id: string }>();
  const router = useRouter();

  const [office, setOffice] = useState<Office | null>(null);
  const [decisions, setDecisions] = useState<Decision[]>([]);
  const [statusFilter, setStatusFilter] = useState("todos");
  const [selectedDecision, setSelectedDecision] = useState<Decision | null>(null);
  const [brainLoading, setBrainLoading] = useState(false);
  const [brainMsg, setBrainMsg] = useState<{ ok: boolean; text: string } | null>(null);
  const [loading, setLoading] = useState(true);

  const token = typeof window !== "undefined" ? localStorage.getItem("viraxis_token") : null;
  const headers = { Authorization: `Bearer ${token}` };

  const loadDecisions = useCallback(async (filter: string) => {
    const qs = filter !== "todos" ? `?status=${filter}` : "";
    const r = await fetch(`/api/offices/${id}/decisions${qs}`, { headers });
    if (r.ok) setDecisions(await r.json());
  }, [id, token]);

  useEffect(() => {
    if (!auth.getToken()) { router.replace("/login"); return; }
    (async () => {
      setLoading(true);
      try {
        const r = await fetch("/api/offices", { headers });
        if (r.ok) {
          const list: Office[] = await r.json();
          const found = list.find(o => o.id === id);
          if (found) setOffice(found);
          else router.replace("/dashboard/escritorios");
        }
        await loadDecisions("todos");
      } finally { setLoading(false); }
    })();
  }, [id]);

  useEffect(() => { loadDecisions(statusFilter); }, [statusFilter]);

  async function runBrain() {
    setBrainLoading(true); setBrainMsg(null);
    try {
      const r = await fetch(`/api/offices/${id}/brain/run`, {
        method: "POST", headers: { ...headers, "Content-Type": "application/json" },
      });
      const data = await r.json();
      if (r.ok) {
        setBrainMsg({ ok: true, text: `✅ BRAIN concluiu — decisão: "${data.content_topic}" via ${data.target_platform}` });
        await loadDecisions(statusFilter);
      } else {
        setBrainMsg({ ok: false, text: `❌ Erro: ${data.detail}` });
      }
    } catch (e) {
      setBrainMsg({ ok: false, text: `❌ Erro de conexão: ${e}` });
    } finally { setBrainLoading(false); }
  }

  async function toggleOfficeStatus() {
    if (!office) return;
    const next = office.status === "active" ? "paused" : "active";
    const r = await fetch(`/api/offices/${id}/status`, {
      method: "PATCH", headers: { ...headers, "Content-Type": "application/json" },
      body: JSON.stringify({ status: next }),
    });
    if (r.ok) {
      const updated = await r.json();
      setOffice(prev => prev ? { ...prev, status: updated.status } : prev);
    }
  }

  function handleStatusChange(updated: Decision) {
    setDecisions(prev => prev.map(d => d.id === updated.id ? updated : d));
  }

  const pendingCount = decisions.filter(d => d.status === "pending").length;
  const approvedCount = decisions.filter(d => d.status === "approved").length;
  const doneCount = decisions.filter(d => d.status === "done").length;

  if (loading) {
    return (
      <div className="flex items-center justify-center min-h-[60vh]">
        <div className="text-white/30 animate-pulse text-sm">Carregando escritório...</div>
      </div>
    );
  }

  if (!office) return null;

  const isActive = office.status === "active";

  return (
    <>
      {selectedDecision && (
        <DecisionModal
          decision={selectedDecision} officeId={id}
          onClose={() => setSelectedDecision(null)}
          onStatusChange={d => { handleStatusChange(d); setSelectedDecision(null); }}
        />
      )}

      <div className="max-w-5xl mx-auto space-y-6">
        {/* Header */}
        <div className="flex items-start justify-between gap-4 flex-wrap">
          <div>
            <div className="flex items-center gap-2 mb-1">
              <button onClick={() => router.back()} className="text-white/30 hover:text-white/60 text-sm transition-colors">
                ← Voltar
              </button>
            </div>
            <div className="flex items-center gap-3 flex-wrap">
              <h1 className="text-2xl font-black text-white">{office.name}</h1>
              <span className={`text-xs font-semibold px-2.5 py-1 rounded-full border ${isActive ? "bg-emerald-500/15 text-emerald-400 border-emerald-500/30" : "bg-yellow-500/15 text-yellow-400 border-yellow-500/30"}`}>
                {isActive ? "● Ativo" : "⏸ Pausado"}
              </span>
            </div>
            <p className="text-white/40 text-sm mt-1">{office.niche}</p>
          </div>
          <div className="flex gap-2 flex-wrap">
            <button
              onClick={toggleOfficeStatus}
              className={`px-4 py-2 text-sm rounded-xl border transition-colors font-medium ${isActive ? "border-yellow-500/40 text-yellow-400 hover:bg-yellow-500/10" : "border-emerald-500/40 text-emerald-400 hover:bg-emerald-500/10"}`}
            >
              {isActive ? "⏸ Pausar" : "▶ Ativar"}
            </button>
          </div>
        </div>

        {/* Stats */}
        <div className="grid grid-cols-2 sm:grid-cols-4 gap-4">
          {[
            { label: "Decisões Totais", value: decisions.length, color: "text-white" },
            { label: "Pendentes", value: pendingCount, color: "text-yellow-400" },
            { label: "Aprovadas", value: approvedCount, color: "text-emerald-400" },
            { label: "Concluídas", value: doneCount, color: "text-violet-400" },
          ].map(s => (
            <div key={s.label} className="card-glass rounded-2xl p-4 text-center">
              <p className={`text-3xl font-black ${s.color}`}>{s.value}</p>
              <p className="text-white/40 text-xs mt-1">{s.label}</p>
            </div>
          ))}
        </div>

        {/* BRAIN Panel */}
        <div className="card-glass rounded-2xl p-6">
          <div className="flex items-center justify-between flex-wrap gap-4">
            <div>
              <div className="flex items-center gap-2 mb-1">
                <span className="text-lg">🧠</span>
                <h2 className="font-bold text-white">Agente BRAIN</h2>
              </div>
              <p className="text-white/40 text-sm">Analisa tendências e decide o próximo conteúdo a criar.</p>
            </div>
            <button
              onClick={runBrain}
              disabled={brainLoading || !isActive}
              className="px-5 py-2.5 bg-violet-600 hover:bg-violet-500 disabled:bg-violet-900 disabled:cursor-not-allowed text-white text-sm font-bold rounded-xl transition-colors flex items-center gap-2"
            >
              {brainLoading ? <><span className="animate-spin">⚙️</span> Pensando...</> : "▶ Executar BRAIN"}
            </button>
          </div>
          {brainMsg && (
            <div className={`mt-4 px-4 py-3 rounded-xl text-sm border ${brainMsg.ok ? "bg-emerald-500/10 border-emerald-500/30 text-emerald-300" : "bg-red-500/10 border-red-500/30 text-red-300"}`}>
              {brainMsg.text}
            </div>
          )}
          {!isActive && (
            <p className="mt-3 text-yellow-400/70 text-xs">⚠️ Ative o escritório para executar o BRAIN.</p>
          )}
        </div>

        {/* Platforms + Style */}
        <div className="grid md:grid-cols-2 gap-4">
          <div className="card-glass rounded-2xl p-5">
            <p className="text-xs font-semibold text-white/40 uppercase tracking-wider mb-3">Plataformas</p>
            {office.platforms.length > 0 ? (
              <div className="flex flex-wrap gap-2">
                {office.platforms.map(p => (
                  <span key={p} className="px-3 py-1.5 rounded-lg bg-white/[0.06] border border-white/[0.08] text-white/70 text-sm">
                    {PLATFORM_ICONS[p] ?? "🌐"} {p}
                  </span>
                ))}
              </div>
            ) : <p className="text-white/25 text-sm">Nenhuma plataforma configurada</p>}
          </div>
          <div className="card-glass rounded-2xl p-5">
            <p className="text-xs font-semibold text-white/40 uppercase tracking-wider mb-3">Estilo de Conteúdo</p>
            <p className="text-white/70 text-sm capitalize">{office.content_style}</p>
            {office.target_audience && (
              <>
                <p className="text-xs font-semibold text-white/40 uppercase tracking-wider mb-1 mt-3">Público-alvo</p>
                <p className="text-white/50 text-sm">{office.target_audience}</p>
              </>
            )}
          </div>
        </div>

        {/* Decisions List */}
        <div className="card-glass rounded-2xl p-6">
          <div className="flex items-center justify-between flex-wrap gap-4 mb-5">
            <div className="flex items-center gap-2">
              <h2 className="font-bold text-white">📋 Decisões do BRAIN</h2>
              {pendingCount > 0 && (
                <span className="text-xs font-bold px-2 py-0.5 rounded-full bg-yellow-500/20 text-yellow-400 border border-yellow-500/30">
                  {pendingCount} pendente{pendingCount > 1 ? "s" : ""}
                </span>
              )}
            </div>
            {/* Status filter */}
            <div className="flex gap-1 flex-wrap">
              {STATUS_FILTERS.map(f => (
                <button
                  key={f}
                  onClick={() => setStatusFilter(f)}
                  className={`px-3 py-1.5 text-xs rounded-lg transition-colors font-medium capitalize ${statusFilter === f ? "bg-violet-600/30 text-violet-300 border border-violet-500/40" : "text-white/40 hover:text-white/60 bg-white/[0.03] border border-transparent"}`}
                >
                  {f === "todos" ? "Todos" : STATUS_LABELS[f]?.replace(/^[^\s]+ /, "") ?? f}
                </button>
              ))}
            </div>
          </div>

          {decisions.length === 0 ? (
            <div className="text-center py-12">
              <p className="text-white/20 text-4xl mb-3">🧠</p>
              <p className="text-white/30 text-sm">
                {statusFilter === "todos" ? "Nenhuma decisão ainda. Execute o BRAIN!" : `Nenhuma decisão com status "${statusFilter}".`}
              </p>
            </div>
          ) : (
            <div className="space-y-3">
              {decisions.map(d => (
                <button
                  key={d.id}
                  onClick={() => setSelectedDecision(d)}
                  className="w-full text-left p-4 rounded-xl bg-white/[0.03] border border-white/[0.06] hover:border-violet-500/30 hover:bg-white/[0.05] transition-all group"
                >
                  <div className="flex items-center gap-4">
                    {/* Confidence mini gauge */}
                    <div className="shrink-0">
                      <div className="w-12 h-12 rounded-full flex items-center justify-center border-2 text-sm font-bold"
                        style={{
                          borderColor: d.confidence_score >= 0.75 ? "#10b981" : d.confidence_score >= 0.5 ? "#f59e0b" : "#ef4444",
                          color: d.confidence_score >= 0.75 ? "#10b981" : d.confidence_score >= 0.5 ? "#f59e0b" : "#ef4444",
                        }}
                      >
                        {Math.round(d.confidence_score * 100)}%
                      </div>
                    </div>

                    {/* Content */}
                    <div className="flex-1 min-w-0">
                      <div className="flex items-center gap-2 mb-1 flex-wrap">
                        <p className="text-white font-semibold text-sm truncate">
                          {d.content_topic || "Sem tópico"}
                        </p>
                        <span className={`text-[10px] font-semibold px-2 py-0.5 rounded-full border shrink-0 ${STATUS_STYLES[d.status] ?? ""}`}>
                          {STATUS_LABELS[d.status] ?? d.status}
                        </span>
                      </div>
                      <div className="flex items-center gap-3 text-xs text-white/30">
                        <span>{PLATFORM_ICONS[d.target_platform] ?? "🌐"} {d.target_platform}</span>
                        {d.selected_archetype && <span>🎭 {d.selected_archetype}</span>}
                        <span>{new Date(d.created_at).toLocaleDateString("pt-BR")}</span>
                      </div>
                    </div>

                    <span className="text-white/20 group-hover:text-white/50 transition-colors shrink-0">→</span>
                  </div>

                  {/* Hypothesis preview */}
                  <p className="mt-2 text-white/30 text-xs line-clamp-2 pl-16 leading-relaxed">
                    {d.hypothesis}
                  </p>
                </button>
              ))}
            </div>
          )}
        </div>
      </div>
    </>
  );
}
