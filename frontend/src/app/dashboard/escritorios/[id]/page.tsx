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

interface ScriptSection {
  section: "hook" | "development" | "climax" | "cta";
  content: string;
  duration_estimate_seconds: number;
  visual_notes?: string;
}

interface ContentItem {
  id: string;
  office_id: string;
  decision_id: string | null;
  title: string;
  script: string;
  status: string;
  duration_seconds: number | null;
  production_meta: {
    renderer_output?: {
      sections?: ScriptSection[];
      platform_adaptations?: string;
      confidence_score?: number;
      archetype_applied?: string;
    };
    confidence_score?: number;
  };
  publication_log: { platform: string; external_id: string; published_at: string; url?: string }[];
  created_at: string;
  updated_at: string;
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

const ITEM_STATUS_STYLES: Record<string, string> = {
  draft:      "bg-yellow-500/15 text-yellow-400 border-yellow-500/30",
  rendering:  "bg-blue-500/15 text-blue-400 border-blue-500/30",
  ready:      "bg-emerald-500/15 text-emerald-400 border-emerald-500/30",
  published:  "bg-violet-500/15 text-violet-400 border-violet-500/30",
  failed:     "bg-red-700/15 text-red-500 border-red-700/30",
};

const ITEM_STATUS_LABELS: Record<string, string> = {
  draft:     "📝 Aguardando revisão",
  rendering: "⚙️ Processando",
  ready:     "✅ Pronto para publicar",
  published: "🚀 Publicado",
  failed:    "💥 Falhou",
};

const SECTION_LABELS: Record<string, { label: string; emoji: string; timing: string }> = {
  hook:        { label: "Gancho",        emoji: "🎣", timing: "0–3s"   },
  development: { label: "Desenvolvimento", emoji: "📈", timing: "3–20s"  },
  climax:      { label: "Clímax",        emoji: "🔥", timing: "20–40s" },
  cta:         { label: "CTA",           emoji: "📣", timing: "40–60s" },
};

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
                {signals.niche_name != null && (
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

// ── ContentItem Modal ─────────────────────────────────────────────────────────

function ContentItemModal({
  item, officeId, onClose, onStatusChange,
}: {
  item: ContentItem; officeId: string;
  onClose: () => void; onStatusChange: (updated: ContentItem) => void;
}) {
  const [actionLoading, setActionLoading] = useState<string | null>(null);
  const [copyMsg, setCopyMsg] = useState(false);
  const token = typeof window !== "undefined" ? localStorage.getItem("viraxis_token") : null;

  const sections: ScriptSection[] = item.production_meta?.renderer_output?.sections ?? [];
  const confidence = item.production_meta?.renderer_output?.confidence_score ?? item.production_meta?.confidence_score ?? null;
  const platformAdaptations = item.production_meta?.renderer_output?.platform_adaptations;
  const durationMin = item.duration_seconds ? Math.round(item.duration_seconds / 60 * 10) / 10 : null;

  async function patchStatus(newStatus: string): Promise<ContentItem | null> {
    const r = await fetch(`/api/offices/${officeId}/content-items/${item.id}/status`, {
      method: "PATCH",
      headers: { Authorization: `Bearer ${token}`, "Content-Type": "application/json" },
      body: JSON.stringify({ status: newStatus }),
    });
    if (!r.ok) return null;
    return await r.json();
  }

  async function handleApprove() {
    setActionLoading("approve");
    try {
      // draft → rendering → ready (two transitions — no real video rendering yet)
      await patchStatus("rendering");
      const updated = await patchStatus("ready");
      if (updated) { onStatusChange(updated); onClose(); }
    } finally { setActionLoading(null); }
  }

  async function handleReject() {
    setActionLoading("reject");
    try {
      // ready → draft (re-queue for re-generation)
      const updated = await patchStatus("draft");
      if (updated) { onStatusChange(updated); onClose(); }
    } finally { setActionLoading(null); }
  }

  function copyScript() {
    navigator.clipboard.writeText(item.script).then(() => {
      setCopyMsg(true);
      setTimeout(() => setCopyMsg(false), 2000);
    });
  }

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4" onClick={onClose}>
      <div className="absolute inset-0 bg-black/70 backdrop-blur-sm" />
      <div
        className="relative w-full max-w-2xl max-h-[92vh] overflow-y-auto rounded-2xl border flex flex-col"
        style={{ background: "rgba(10,11,18,0.98)", borderColor: "var(--border)" }}
        onClick={e => e.stopPropagation()}
      >
        {/* Header */}
        <div className="flex items-start justify-between p-6 border-b shrink-0" style={{ borderColor: "var(--border)" }}>
          <div className="flex-1 min-w-0 pr-4">
            <div className="flex items-center gap-2 mb-1 flex-wrap">
              <span className={`text-xs font-semibold px-2.5 py-1 rounded-full border ${ITEM_STATUS_STYLES[item.status] ?? ""}`}>
                {ITEM_STATUS_LABELS[item.status] ?? item.status}
              </span>
              {durationMin && (
                <span className="text-xs text-white/30">⏱ ~{durationMin} min</span>
              )}
              {confidence && (
                <span className="text-xs text-white/30">
                  🎯 {Math.round(confidence * 100)}% confiança
                </span>
              )}
            </div>
            <h2 className="text-lg font-bold text-white leading-tight">{item.title}</h2>
            <p className="text-white/30 text-xs mt-0.5">
              {new Date(item.created_at).toLocaleString("pt-BR")}
            </p>
          </div>
          <button onClick={onClose} className="text-white/30 hover:text-white/60 text-xl shrink-0 transition-colors">✕</button>
        </div>

        {/* Script Sections */}
        <div className="p-6 space-y-4 flex-1 overflow-y-auto">
          {sections.length > 0 ? (
            <>
              <div className="flex items-center justify-between mb-1">
                <p className="text-xs font-semibold text-white/40 uppercase tracking-wider">📝 Roteiro por Seção</p>
                <button onClick={copyScript} className="text-xs text-violet-400 hover:text-violet-300 transition-colors">
                  {copyMsg ? "✓ Copiado!" : "⧉ Copiar roteiro completo"}
                </button>
              </div>
              {sections.map((sec) => {
                const meta = SECTION_LABELS[sec.section];
                return (
                  <div key={sec.section} className="rounded-xl border border-white/[0.08] overflow-hidden">
                    <div className="flex items-center justify-between px-4 py-2.5 bg-white/[0.04] border-b border-white/[0.06]">
                      <div className="flex items-center gap-2">
                        <span>{meta?.emoji}</span>
                        <span className="text-sm font-bold text-white">{meta?.label}</span>
                        <span className="text-xs text-white/30">{meta?.timing}</span>
                      </div>
                      <span className="text-xs text-white/30">~{sec.duration_estimate_seconds}s</span>
                    </div>
                    <div className="px-4 py-3">
                      <p className="text-white/80 text-sm leading-relaxed whitespace-pre-wrap">{sec.content}</p>
                      {sec.visual_notes && (
                        <p className="text-white/30 text-xs mt-2 italic border-t border-white/[0.05] pt-2">
                          🎬 {sec.visual_notes}
                        </p>
                      )}
                    </div>
                  </div>
                );
              })}
            </>
          ) : (
            // Fallback: show full script as plain text
            <div>
              <div className="flex items-center justify-between mb-2">
                <p className="text-xs font-semibold text-white/40 uppercase tracking-wider">📝 Roteiro</p>
                <button onClick={copyScript} className="text-xs text-violet-400 hover:text-violet-300 transition-colors">
                  {copyMsg ? "✓ Copiado!" : "⧉ Copiar"}
                </button>
              </div>
              <div className="bg-white/[0.03] border border-white/[0.06] rounded-xl p-4">
                <p className="text-white/80 text-sm leading-relaxed whitespace-pre-wrap">{item.script}</p>
              </div>
            </div>
          )}

          {/* Platform adaptations */}
          {platformAdaptations && (
            <div className="bg-white/[0.03] border border-white/[0.06] rounded-xl p-4">
              <p className="text-xs font-semibold text-white/40 uppercase tracking-wider mb-2">🎯 Adaptações da Plataforma</p>
              <p className="text-white/60 text-sm leading-relaxed">{platformAdaptations}</p>
            </div>
          )}

          {/* Publication log */}
          {item.publication_log.length > 0 && (
            <div>
              <p className="text-xs font-semibold text-white/40 uppercase tracking-wider mb-2">🚀 Publicações</p>
              <div className="space-y-2">
                {item.publication_log.map((pub, i) => (
                  <div key={i} className="flex items-center gap-3 text-sm">
                    <span>{PLATFORM_ICONS[pub.platform] ?? "🌐"}</span>
                    <span className="text-white/70 capitalize">{pub.platform}</span>
                    <span className="text-white/30 text-xs">{new Date(pub.published_at).toLocaleString("pt-BR")}</span>
                    {pub.url && (
                      <a href={pub.url} target="_blank" rel="noopener noreferrer"
                        className="text-xs text-violet-400 hover:text-violet-300 ml-auto">
                        Ver →
                      </a>
                    )}
                  </div>
                ))}
              </div>
            </div>
          )}
        </div>

        {/* Actions */}
        <div className="px-6 pb-6 pt-4 border-t flex flex-wrap gap-3 shrink-0" style={{ borderColor: "var(--border)" }}>
          {item.status === "draft" && (
            <>
              <button
                onClick={handleApprove}
                disabled={actionLoading !== null}
                className="flex-1 py-2.5 bg-emerald-600 hover:bg-emerald-500 disabled:opacity-50 text-white text-sm font-bold rounded-xl transition-colors"
              >
                {actionLoading === "approve" ? "⚙️ Aprovando..." : "✅ Aprovar Roteiro"}
              </button>
              <button
                onClick={onClose}
                className="px-5 py-2.5 bg-white/[0.06] hover:bg-white/[0.10] text-white/60 text-sm rounded-xl transition-colors"
              >
                Fechar
              </button>
            </>
          )}
          {item.status === "ready" && (
            <>
              <div className="flex-1 px-4 py-2.5 bg-emerald-500/10 border border-emerald-500/30 rounded-xl text-center">
                <p className="text-emerald-400 text-xs font-semibold">Roteiro aprovado — pronto para publicar</p>
                <p className="text-white/30 text-[10px] mt-0.5">Conecte um canal em Configurações → Canais para publicar</p>
              </div>
              <button
                onClick={handleReject}
                disabled={actionLoading !== null}
                className="px-5 py-2.5 bg-red-600/20 border border-red-500/30 hover:bg-red-600/30 disabled:opacity-50 text-red-400 text-sm font-medium rounded-xl transition-colors"
              >
                {actionLoading === "reject" ? "..." : "↩ Refazer"}
              </button>
            </>
          )}
          {item.status === "published" && (
            <div className="flex-1 px-4 py-2.5 bg-violet-500/10 border border-violet-500/30 rounded-xl text-center">
              <p className="text-violet-400 text-xs font-semibold">🚀 Publicado em {item.publication_log.length} plataforma(s)</p>
            </div>
          )}
          {(item.status !== "draft" && item.status !== "ready" && item.status !== "published") && (
            <button
              onClick={onClose}
              className="flex-1 py-2.5 bg-white/[0.06] hover:bg-white/[0.10] text-white/60 text-sm rounded-xl transition-colors"
            >
              Fechar
            </button>
          )}
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
  const [contentItems, setContentItems] = useState<ContentItem[]>([]);
  const [statusFilter, setStatusFilter] = useState("todos");
  const [selectedDecision, setSelectedDecision] = useState<Decision | null>(null);
  const [selectedItem, setSelectedItem] = useState<ContentItem | null>(null);
  const [brainLoading, setBrainLoading] = useState(false);
  const [brainMsg, setBrainMsg] = useState<{ ok: boolean; text: string } | null>(null);
  const [pageLoading, setPageLoading] = useState(true);

  const token = typeof window !== "undefined" ? localStorage.getItem("viraxis_token") : null;
  const headers = { Authorization: `Bearer ${token}` };

  const loadDecisions = useCallback(async (filter: string) => {
    const qs = filter !== "todos" ? `?status=${filter}` : "";
    const r = await fetch(`/api/offices/${id}/decisions${qs}`, { headers });
    if (r.ok) setDecisions(await r.json());
  }, [id, token]);

  const loadContentItems = useCallback(async () => {
    const r = await fetch(`/api/offices/${id}/content-items`, { headers });
    if (r.ok) setContentItems(await r.json());
  }, [id, token]);

  useEffect(() => {
    if (!auth.getToken()) { router.replace("/login"); return; }
    fetch(`/api/offices/${id}`, { headers })
      .then(r => r.json())
      .then(data => setOffice(data))
      .catch(() => {})
      .finally(() => setPageLoading(false));
    loadDecisions(statusFilter);
    loadContentItems();
  }, [id]);

  async function toggleOfficeStatus() {
    if (!office) return;
    const next = office.status === "active" ? "paused" : "active";
    const r = await fetch(`/api/offices/${id}`, {
      method: "PATCH",
      headers: { ...headers, "Content-Type": "application/json" },
      body: JSON.stringify({ status: next }),
    });
    if (r.ok) setOffice(await r.json());
  }

  async function runBrain() {
    setBrainLoading(true);
    setBrainMsg(null);
    try {
      const r = await fetch(`/api/offices/${id}/brain/run`, {
        method: "POST",
        headers,
      });
      const data = await r.json();
      if (r.ok) {
        setBrainMsg({ ok: true, text: `✅ BRAIN gerou ${data.decisions_created ?? 1} decisão(ões)!` });
        loadDecisions(statusFilter);
      } else {
        setBrainMsg({ ok: false, text: data.detail ?? "Erro ao rodar o BRAIN." });
      }
    } catch {
      setBrainMsg({ ok: false, text: "Erro de conexão." });
    } finally {
      setBrainLoading(false);
    }
  }

  function handleDecisionStatusChange(updated: Decision) {
    setDecisions(prev => prev.map(d => d.id === updated.id ? updated : d));
    setSelectedDecision(updated);
    loadDecisions(statusFilter);
    loadContentItems();
  }

  function handleItemStatusChange(updated: ContentItem) {
    setContentItems(prev => prev.map(i => i.id === updated.id ? updated : i));
  }

  function handleFilterChange(f: string) {
    setStatusFilter(f);
    loadDecisions(f);
  }

  const pendingCount   = decisions.filter(d => d.status === "pending").length;
  const approvedCount  = decisions.filter(d => d.status === "approved" || d.status === "executing").length;
  const doneCount      = decisions.filter(d => d.status === "done").length;

  const draftItems     = contentItems.filter(i => i.status === "draft");
  const readyItems     = contentItems.filter(i => i.status === "ready");
  const publishedItems = contentItems.filter(i => i.status === "published");

  if (pageLoading) {
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
          decision={selectedDecision}
          officeId={id}
          onClose={() => setSelectedDecision(null)}
          onStatusChange={handleDecisionStatusChange}
        />
      )}
      {selectedItem && (
        <ContentItemModal
          item={selectedItem}
          officeId={id}
          onClose={() => setSelectedItem(null)}
          onStatusChange={handleItemStatusChange}
        />
      )}

      <div className="max-w-5xl mx-auto space-y-6 pb-12">

        {/* ── Office Header ── */}
        <div className="flex items-start justify-between gap-4 flex-wrap">
          <div>
            <div className="flex items-center gap-3 mb-1">
              <h1 className="text-2xl font-bold text-white">{office.name}</h1>
              <span className={`text-xs font-semibold px-2.5 py-1 rounded-full border ${
                isActive
                  ? "bg-emerald-500/15 text-emerald-400 border-emerald-500/30"
                  : "bg-white/[0.06] text-white/40 border-white/10"
              }`}>
                {isActive ? "● Ativo" : "⏸ Pausado"}
              </span>
            </div>
            <p className="text-white/40 text-sm">{office.niche}</p>
          </div>
          <button
            onClick={toggleOfficeStatus}
            className="px-4 py-2 rounded-xl border border-white/10 bg-white/[0.04] hover:bg-white/[0.08] text-white/50 text-sm transition-colors"
          >
            {isActive ? "Pausar" : "Ativar"}
          </button>
        </div>

        {/* ── Stats ── */}
        <div className="grid grid-cols-2 lg:grid-cols-4 gap-3">
          {[
            { label: "Conteúdos Gerados", value: office.content_count, icon: "🎬" },
            { label: "Publicados",         value: office.published_count, icon: "🚀" },
            { label: "Viralizaram",         value: office.viral_count, icon: "🔥" },
            { label: "Decisões Pendentes",  value: pendingCount, icon: "⏳" },
          ].map(stat => (
            <div key={stat.label} className="rounded-2xl border border-white/[0.06] bg-white/[0.03] p-4">
              <p className="text-white/30 text-xs mb-1">{stat.icon} {stat.label}</p>
              <p className="text-2xl font-bold text-white">{stat.value ?? 0}</p>
            </div>
          ))}
        </div>

        {/* ── BRAIN Panel ── */}
        <div className="rounded-2xl border border-white/[0.06] bg-white/[0.02] p-5">
          <div className="flex items-center justify-between gap-4 flex-wrap">
            <div>
              <h3 className="text-sm font-bold text-white mb-0.5">🧠 BRAIN</h3>
              <p className="text-white/30 text-xs">
                Analisa tendências e gera decisões de conteúdo para este escritório.
              </p>
            </div>
            <button
              onClick={runBrain}
              disabled={brainLoading || !isActive}
              className="px-5 py-2.5 bg-violet-600 hover:bg-violet-500 disabled:opacity-40 text-white text-sm font-bold rounded-xl transition-colors"
            >
              {brainLoading ? "⚙️ Rodando..." : "▶ Rodar BRAIN"}
            </button>
          </div>
          {brainMsg && (
            <div className={`mt-3 px-4 py-2.5 rounded-xl text-sm border ${
              brainMsg.ok
                ? "bg-emerald-500/10 border-emerald-500/20 text-emerald-300"
                : "bg-red-500/10 border-red-500/20 text-red-300"
            }`}>
              {brainMsg.text}
            </div>
          )}
        </div>

        {/* ── Config row: Platforms + Style ── */}
        <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
          <div className="rounded-2xl border border-white/[0.06] bg-white/[0.02] p-4">
            <p className="text-xs text-white/30 uppercase tracking-wider mb-3">📡 Plataformas</p>
            <div className="flex flex-wrap gap-2">
              {(office.platforms ?? []).map((p: string) => (
                <span key={p} className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-white/[0.06] text-white/70 text-xs font-medium">
                  {PLATFORM_ICONS[p] ?? "🌐"} {p}
                </span>
              ))}
            </div>
          </div>
          <div className="rounded-2xl border border-white/[0.06] bg-white/[0.02] p-4">
            <p className="text-xs text-white/30 uppercase tracking-wider mb-1.5">🎨 Estilo de Conteúdo</p>
            <p className="text-white/70 text-sm">{office.content_style || "—"}</p>
            <p className="text-xs text-white/30 uppercase tracking-wider mb-1.5 mt-3">👥 Público-Alvo</p>
            <p className="text-white/70 text-sm">{office.target_audience || "—"}</p>
          </div>
        </div>

        {/* ── Decisions ── */}
        <div>
          <div className="flex items-center justify-between mb-4 flex-wrap gap-2">
            <div>
              <h2 className="text-base font-bold text-white">Decisões do BRAIN</h2>
              <p className="text-white/30 text-xs mt-0.5">
                {pendingCount} pendente(s) · {approvedCount} em andamento · {doneCount} concluída(s)
              </p>
            </div>
            <div className="flex gap-1.5 flex-wrap">
              {STATUS_FILTERS.map(f => (
                <button
                  key={f}
                  onClick={() => handleFilterChange(f)}
                  className={`px-3 py-1.5 rounded-lg text-xs font-medium capitalize transition-colors ${
                    statusFilter === f
                      ? "bg-violet-600 text-white"
                      : "bg-white/[0.04] text-white/40 hover:bg-white/[0.08] hover:text-white/60"
                  }`}
                >
                  {f === "todos" ? "Todos" : STATUS_LABELS[f]?.replace(/^.+?\s/, "") ?? f}
                </button>
              ))}
            </div>
          </div>

          {decisions.length === 0 ? (
            <div className="rounded-2xl border border-white/[0.06] bg-white/[0.02] p-10 text-center">
              <p className="text-white/20 text-sm">Nenhuma decisão{statusFilter !== "todos" ? ` com status "${statusFilter}"` : ""}.</p>
              {statusFilter === "todos" && (
                <p className="text-white/15 text-xs mt-1">Rode o BRAIN para gerar decisões de conteúdo.</p>
              )}
            </div>
          ) : (
            <div className="space-y-2">
              {decisions.map(d => (
                <button
                  key={d.id}
                  onClick={() => setSelectedDecision(d)}
                  className="w-full text-left rounded-2xl border border-white/[0.06] bg-white/[0.02] hover:bg-white/[0.04] p-4 transition-colors"
                >
                  <div className="flex items-center justify-between gap-3 flex-wrap">
                    <div className="flex-1 min-w-0">
                      <div className="flex items-center gap-2 mb-1 flex-wrap">
                        <span className={`text-[11px] font-semibold px-2 py-0.5 rounded-full border ${STATUS_STYLES[d.status] ?? ""}`}>
                          {STATUS_LABELS[d.status] ?? d.status}
                        </span>
                        <span className="text-white/30 text-xs">
                          {PLATFORM_ICONS[d.target_platform] ?? "🌐"} {d.target_platform}
                        </span>
                        {d.selected_archetype && (
                          <span className="text-violet-400/60 text-xs">🎭 {d.selected_archetype}</span>
                        )}
                      </div>
                      <p className="text-white/80 text-sm font-medium truncate">{d.content_topic || "Sem tópico"}</p>
                      <p className="text-white/30 text-xs mt-0.5">{new Date(d.created_at).toLocaleString("pt-BR")}</p>
                    </div>
                    <div className="text-right shrink-0">
                      <p className="text-white font-bold text-sm">{Math.round(d.confidence_score * 100)}%</p>
                      <p className="text-white/20 text-[10px]">confiança</p>
                    </div>
                  </div>
                </button>
              ))}
            </div>
          )}
        </div>

        {/* ── Roteiros Gerados ── */}
        <div>
          <div className="flex items-center justify-between mb-4">
            <div>
              <h2 className="text-base font-bold text-white">Roteiros Gerados</h2>
              <p className="text-white/30 text-xs mt-0.5">
                {draftItems.length} aguardando revisão · {readyItems.length} prontos · {publishedItems.length} publicados
              </p>
            </div>
          </div>

          {contentItems.length === 0 ? (
            <div className="rounded-2xl border border-white/[0.06] bg-white/[0.02] p-10 text-center">
              <p className="text-white/20 text-sm">Nenhum roteiro gerado ainda.</p>
              <p className="text-white/15 text-xs mt-1">Aprove uma decisão e inicie a execução para gerar roteiros.</p>
            </div>
          ) : (
            <div className="space-y-2">
              {contentItems.map(item => (
                <button
                  key={item.id}
                  onClick={() => setSelectedItem(item)}
                  className="w-full text-left rounded-2xl border border-white/[0.06] bg-white/[0.02] hover:bg-white/[0.04] p-4 transition-colors group"
                >
                  <div className="flex items-center justify-between gap-3 flex-wrap">
                    <div className="flex-1 min-w-0">
                      <div className="flex items-center gap-2 mb-1 flex-wrap">
                        <span className={`text-[11px] font-semibold px-2 py-0.5 rounded-full border ${ITEM_STATUS_STYLES[item.status] ?? ""}`}>
                          {ITEM_STATUS_LABELS[item.status] ?? item.status}
                        </span>
                        {item.duration_seconds && (
                          <span className="text-white/30 text-xs">⏱ ~{Math.round(item.duration_seconds / 60 * 10) / 10} min</span>
                        )}
                        {(() => {
                          const conf = item.production_meta?.renderer_output?.confidence_score ?? item.production_meta?.confidence_score;
                          return conf ? <span className="text-white/30 text-xs">🎯 {Math.round(conf * 100)}%</span> : null;
                        })()}
                      </div>
                      <p className="text-white/80 text-sm font-medium truncate">{item.title}</p>
                      <p className="text-white/30 text-xs mt-0.5">{new Date(item.created_at).toLocaleString("pt-BR")}</p>
                    </div>
                    <span className="text-white/20 group-hover:text-white/40 text-lg transition-colors">›</span>
                  </div>
                </button>
              ))}
            </div>
          )}
        </div>

      </div>
    </>
  );
}
