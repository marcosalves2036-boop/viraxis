"use client";

import { useEffect, useState, useCallback, useRef } from "react";
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

interface RenderProgress {
  item_id: string | null; progress: number; stage: string; status: string;
}

interface RawVideo {
  id: string; title: string | null; original_filename: string; status: string; duration_seconds: number | null;
}

// ── Constants ─────────────────────────────────────────────────────────────────

const PLATFORM_ICONS: Record<string, string> = {
  tiktok: "🎵", instagram: "📸", youtube: "▶️", twitter: "🐦",
  linkedin: "💼", facebook: "👥", kwai: "📱", default: "🌐",
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
  pending: "⏳ Pendente", approved: "✅ Aprovada", executing: "⚙ Executando",
  done: "🎯 Concluída", rejected: "❌ Rejeitada", failed: "💥 Falhou",
};

const STATUS_FILTERS = ["todos", "pending", "approved", "executing", "done", "rejected"];

// ── Render Progress Bar ───────────────────────────────────────────────────────

function RenderProgressBar({ progress, stage }: { progress: number; stage: string }) {
  return (
    <div className="mt-3 space-y-1.5">
      <div className="flex justify-between text-xs text-white/40">
        <span>🤖 {stage}</span>
        <span>{progress}%</span>
      </div>
      <div className="h-1.5 rounded-full bg-white/[0.08] overflow-hidden">
        <div
          className="h-full rounded-full bg-gradient-to-r from-violet-500 to-cyan-400 transition-all duration-700"
          style={{ width: `${progress}%` }}
        />
      </div>
    </div>
  );
}

// ── Decision Modal ────────────────────────────────────────────────────────────

function DecisionModal({
  decision, officeId, renderProgress, onClose, onStatusChange, onViewContent,
}: {
  decision: Decision; officeId: string;
  renderProgress: RenderProgress | null;
  onClose: () => void;
  onStatusChange: (d: Decision) => void;
  onViewContent: (itemId: string) => void;
}) {
  const [loading, setLoading] = useState<string | null>(null);
  const [extraInstructions, setExtraInstructions] = useState("");
  const token = typeof window !== "undefined" ? localStorage.getItem("viraxis_token") : null;

  async function patchStatus(newStatus: string) {
    setLoading(newStatus);
    try {
      const r = await fetch(`/api/offices/${officeId}/decisions/${decision.id}`, {
        method: "PATCH",
        headers: { Authorization: `Bearer ${token}`, "Content-Type": "application/json" },
        body: JSON.stringify({ status: newStatus, extra_instructions: extraInstructions || null }),
      });
      if (r.ok) { onStatusChange(await r.json()); onClose(); }
    } finally { setLoading(null); }
  }

  const signals = decision.input_signals as Record<string, unknown>;
  const reasoning = decision.reasoning as Record<string, unknown>;
  const isExecuting = decision.status === "executing";
  const isDone = decision.status === "done";
  const progress = renderProgress?.progress ?? 0;
  const stage = renderProgress?.stage ?? "processando";

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4" onClick={onClose}>
      <div className="absolute inset-0 bg-black/70 backdrop-blur-sm" />
      <div
        className="relative w-full max-w-2xl max-h-[90vh] overflow-y-auto rounded-2xl border"
        style={{ background: "rgba(10,11,18,0.98)", borderColor: "rgba(255,255,255,0.08)" }}
        onClick={e => e.stopPropagation()}
      >
        <div className="p-6 space-y-5">
          {/* Header */}
          <div className="flex items-start justify-between gap-4">
            <div className="flex-1 min-w-0">
              <div className="flex items-center gap-2 flex-wrap mb-2">
                <span className={`text-xs font-semibold px-2.5 py-1 rounded-full border ${STATUS_STYLES[decision.status]}`}>
                  {STATUS_LABELS[decision.status]}
                </span>
                <span className="text-xs text-white/30">
                  {PLATFORM_ICONS[decision.target_platform] ?? "🌐"} {decision.target_platform}
                </span>
              </div>
              <h2 className="text-lg font-bold text-white leading-tight">{decision.content_topic}</h2>
            </div>
            <div className="shrink-0">
              <div className="w-14 h-14 rounded-full flex items-center justify-center border-2 text-base font-black"
                style={{
                  borderColor: decision.confidence_score >= 0.75 ? "#10b981" : decision.confidence_score >= 0.5 ? "#f59e0b" : "#ef4444",
                  color: decision.confidence_score >= 0.75 ? "#10b981" : decision.confidence_score >= 0.5 ? "#f59e0b" : "#ef4444",
                }}
              >
                {Math.round(decision.confidence_score * 100)}%
              </div>
              <p className="text-[10px] text-white/25 text-center mt-1">confiança</p>
            </div>
          </div>

          {/* Render progress (when executing) */}
          {isExecuting && (
            <div className="bg-blue-500/10 border border-blue-500/20 rounded-xl p-4">
              <p className="text-blue-300 text-sm font-semibold mb-2">🤖 RENDERER em ação…</p>
              <RenderProgressBar progress={progress} stage={stage} />
              <p className="text-blue-300/50 text-xs mt-2">Gerando roteiro, thumbnails, SEO e plano de postagem</p>
            </div>
          )}

          {/* Done state — link to content */}
          {isDone && renderProgress?.item_id && (
            <div className="bg-violet-500/10 border border-violet-500/20 rounded-xl p-4 flex items-center justify-between gap-4">
              <div>
                <p className="text-violet-300 text-sm font-semibold">🎯 Conteúdo gerado com sucesso!</p>
                <p className="text-violet-300/50 text-xs mt-0.5">Roteiro, thumbnails, SEO e checklist prontos</p>
              </div>
              <button
                onClick={() => onViewContent(renderProgress.item_id!)}
                className="px-4 py-2 bg-violet-600 hover:bg-violet-500 text-white text-sm font-bold rounded-xl transition-colors shrink-0"
              >
                Ver conteúdo →
              </button>
            </div>
          )}

          {/* Hypothesis */}
          <div>
            <p className="text-xs font-semibold text-white/40 uppercase tracking-wider mb-2">Hipótese do BRAIN</p>
            <p className="text-white/70 text-sm leading-relaxed">{decision.hypothesis}</p>
          </div>

          {/* Archetype */}
          {decision.selected_archetype && (
            <div>
              <p className="text-xs font-semibold text-white/40 uppercase tracking-wider mb-1">Archetype viral</p>
              <span className="inline-block px-3 py-1 bg-violet-500/10 border border-violet-500/20 rounded-lg text-violet-300 text-sm">
                🎭 {decision.selected_archetype}
              </span>
            </div>
          )}

          {/* Reasoning */}
          {Object.keys(reasoning).length > 0 && (
            <div>
              <p className="text-xs font-semibold text-white/40 uppercase tracking-wider mb-2">Raciocínio</p>
              <div className="space-y-1.5">
                {Object.entries(reasoning).slice(0, 4).map(([k, v]) => (
                  <div key={k} className="flex gap-2 text-xs">
                    <span className="text-white/30 capitalize shrink-0">{k.replace(/_/g, " ")}:</span>
                    <span className="text-white/55">{String(v)}</span>
                  </div>
                ))}
              </div>
            </div>
          )}

          {/* Signals */}
          {Object.keys(signals).length > 0 && (
            <div>
              <p className="text-xs font-semibold text-white/40 uppercase tracking-wider mb-2">Sinais de entrada</p>
              <div className="flex flex-wrap gap-1.5">
                {Object.entries(signals).slice(0, 6).map(([k, v]) => (
                  <span key={k} className="text-xs px-2 py-1 rounded-md bg-white/[0.05] text-white/40">
                    {k}: {String(v).substring(0, 30)}
                  </span>
                ))}
              </div>
            </div>
          )}
        </div>

        {/* Extra instructions textarea (only when pending) */}
        {decision.status === "pending" && (
          <div className="px-6 pb-3">
            <p className="text-xs font-semibold text-white/40 uppercase tracking-wider mb-2">Instruções adicionais para o roteiro <span className="text-white/20 font-normal normal-case">(opcional)</span></p>
            <textarea
              value={extraInstructions}
              onChange={e => setExtraInstructions(e.target.value)}
              placeholder="Ex: foca em linguagem para crianças de 8 a 12 anos, tom divertido e use exemplos do cotidiano..."
              rows={3}
              className="w-full rounded-xl border px-3 py-2 text-sm text-white/80 placeholder-white/20 resize-none focus:outline-none focus:border-violet-500/50"
              style={{ background: "rgba(255,255,255,0.04)", borderColor: "rgba(255,255,255,0.08)" }}
            />
          </div>
        )}

        {/* Action buttons */}
        <div className="px-6 pb-6 flex gap-3 flex-wrap">
          {decision.status === "pending" && (
            <>
              <button onClick={() => patchStatus("approved")} disabled={loading !== null}
                className="flex-1 py-2.5 bg-emerald-600 hover:bg-emerald-500 disabled:opacity-50 text-white text-sm font-bold rounded-xl transition-colors">
                {loading === "approved" ? "..." : "✅ Aprovar"}
              </button>
              <button onClick={() => patchStatus("rejected")} disabled={loading !== null}
                className="flex-1 py-2.5 bg-red-900/60 hover:bg-red-800/60 disabled:opacity-50 text-white text-sm font-bold rounded-xl transition-colors">
                {loading === "rejected" ? "..." : "❌ Rejeitar"}
              </button>
            </>
          )}
          <button onClick={onClose}
            className="px-5 py-2.5 bg-white/[0.06] hover:bg-white/[0.10] text-white/60 text-sm rounded-xl transition-colors">
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
  const [renderProgresses, setRenderProgresses] = useState<Record<string, RenderProgress>>({});
  const [brainLoading, setBrainLoading] = useState(false);
  const [brainMsg, setBrainMsg] = useState<{ ok: boolean; text: string } | null>(null);
  const [brainMode, setBrainMode] = useState<"pure" | "reference">("pure");
  const [rawVideos, setRawVideos] = useState<RawVideo[]>([]);
  const [selectedVideoId, setSelectedVideoId] = useState<string>("");
  const [videosLoading, setVideosLoading] = useState(false);
  const [loading, setLoading] = useState(true);
  const pollingRef = useRef<NodeJS.Timeout | null>(null);

  const token = typeof window !== "undefined" ? localStorage.getItem("viraxis_token") : null;
  const headers = { Authorization: `Bearer ${token}` };

  const loadDecisions = useCallback(async (filter: string) => {
    const qs = filter !== "todos" ? `?status=${filter}` : "";
    const r = await fetch(`/api/offices/${id}/decisions${qs}`, { headers });
    if (r.ok) setDecisions(await r.json());
  }, [id, token]);

  // Poll render progress for executing decisions
  const pollProgress = useCallback(async (decisionIds: string[]) => {
    for (const did of decisionIds) {
      try {
        const r = await fetch(`/api/offices/${id}/decisions/${did}/render/progress`, { headers });
        if (r.ok) {
          const prog: RenderProgress = await r.json();
          setRenderProgresses(prev => ({ ...prev, [did]: prog }));
          // If done, refresh decisions list
          if (prog.status === "ready" || prog.status === "failed") {
            await loadDecisions(statusFilter);
          }
        }
      } catch {}
    }
  }, [id, token, statusFilter]);

  useEffect(() => {
    if (!auth.getToken()) { router.replace("/login"); return; }
    (async () => {
      setLoading(true);
      try {
        const r = await fetch("/api/offices", { headers });
        if (r.ok) {
          const list: Office[] = await r.json();
          const found = list.find(o => o.id === id);
          if (found) setOffice(found); else router.replace("/dashboard/escritorios");
        }
        await loadDecisions("todos");
      } finally { setLoading(false); }
    })();
  }, [id]);

  useEffect(() => { loadDecisions(statusFilter); }, [statusFilter]);

  // Auto-poll executing decisions
  useEffect(() => {
    const executing = decisions.filter(d => d.status === "executing").map(d => d.id);
    if (pollingRef.current) clearInterval(pollingRef.current);
    if (executing.length > 0) {
      pollProgress(executing); // immediate first poll
      pollingRef.current = setInterval(() => pollProgress(executing), 3000);
    }
    return () => { if (pollingRef.current) clearInterval(pollingRef.current); };
  }, [decisions]);

  async function loadRawVideos() {
    if (!id) return;
    setVideosLoading(true);
    try {
      const r = await fetch(`/api/raw-videos?office_id=${id}`, { headers });
      if (r.ok) {
        const data: RawVideo[] = await r.json();
        const ready = data.filter(v => v.status === "ready");
        setRawVideos(ready);
        if (ready.length > 0 && !selectedVideoId) setSelectedVideoId(ready[0].id);
      }
    } catch {} finally { setVideosLoading(false); }
  }

  async function handleBrainModeChange(mode: "pure" | "reference") {
    setBrainMode(mode);
    if (mode === "reference" && rawVideos.length === 0) await loadRawVideos();
  }

  async function runBrain() {
    setBrainLoading(true); setBrainMsg(null);
    try {
      const body: Record<string, string | null> = {};
      if (brainMode === "reference" && selectedVideoId) body.raw_video_id = selectedVideoId;

      const r = await fetch(`/api/offices/${id}/brain/run`, {
        method: "POST",
        headers: { ...headers, "Content-Type": "application/json" },
        body: JSON.stringify(body),
      });
      const data = await r.json();
      if (r.ok) {
        const refNote = brainMode === "reference" && selectedVideoId ? " (com referência de vídeo)" : "";
        setBrainMsg({ ok: true, text: `✅ BRAIN concluiu — "${data.content_topic}" via ${data.target_platform}${refNote}` });
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

  function handleViewContent(itemId: string) {
    router.push(`/dashboard/conteudo/${itemId}`);
  }

  const pendingCount = decisions.filter(d => d.status === "pending").length;
  const approvedCount = decisions.filter(d => d.status === "approved").length;
  const doneCount = decisions.filter(d => d.status === "done").length;
  const executingCount = decisions.filter(d => d.status === "executing").length;

  if (loading) return (
    <div className="flex items-center justify-center min-h-[60vh]">
      <div className="text-white/30 animate-pulse text-sm">Carregando escritório...</div>
    </div>
  );
  if (!office) return null;

  const isActive = office.status === "active";

  return (
    <>
      {selectedDecision && (
        <DecisionModal
          decision={selectedDecision} officeId={id}
          renderProgress={renderProgresses[selectedDecision.id] ?? null}
          onClose={() => setSelectedDecision(null)}
          onStatusChange={d => { handleStatusChange(d); setSelectedDecision(null); }}
          onViewContent={handleViewContent}
        />
      )}

      <div className="max-w-5xl mx-auto space-y-6">
        {/* Header */}
        <div className="flex items-start justify-between gap-4 flex-wrap">
          <div>
            <button onClick={() => router.back()} className="text-white/30 hover:text-white/60 text-sm transition-colors mb-2 block">
              ← Voltar
            </button>
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
              onClick={() => router.push(`/dashboard/conteudo?office=${id}`)}
              className="px-4 py-2 text-sm rounded-xl border border-violet-500/30 text-violet-300 hover:bg-violet-500/10 transition-colors font-medium"
            >
              📄 Ver Conteúdos
            </button>
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

        {/* Executing alert */}
        {executingCount > 0 && (
          <div className="bg-blue-500/10 border border-blue-500/20 rounded-2xl p-4 flex items-center gap-3">
            <span className="animate-spin text-xl">⚙️</span>
            <div>
              <p className="text-blue-300 font-semibold text-sm">RENDERER trabalhando…</p>
              <p className="text-blue-300/50 text-xs">{executingCount} decisão(ões) sendo processada(s). Atualizando automaticamente.</p>
            </div>
          </div>
        )}

        {/* BRAIN Panel */}
        <div className="card-glass rounded-2xl p-6">
          <div className="flex items-center justify-between flex-wrap gap-4 mb-4">
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

          {/* Mode selector */}
          <div className="flex gap-2 mb-3">
            <button
              onClick={() => handleBrainModeChange("pure")}
              className={`px-4 py-2 rounded-xl text-xs font-semibold border transition-all ${
                brainMode === "pure"
                  ? "bg-violet-600/30 border-violet-500/60 text-violet-200"
                  : "bg-white/[0.04] border-white/10 text-white/40 hover:text-white/70"
              }`}
            >
              🤖 IA pura
            </button>
            <button
              onClick={() => handleBrainModeChange("reference")}
              className={`px-4 py-2 rounded-xl text-xs font-semibold border transition-all ${
                brainMode === "reference"
                  ? "bg-violet-600/30 border-violet-500/60 text-violet-200"
                  : "bg-white/[0.04] border-white/10 text-white/40 hover:text-white/70"
              }`}
            >
              🎬 Com referência
            </button>
          </div>

          {/* Mode descriptions + video picker */}
          {brainMode === "pure" ? (
            <p className="text-xs text-white/30 mb-1">
              BRAIN decide o estilo livremente com base em tendências e nicho.
            </p>
          ) : (
            <div className="mt-2">
              <p className="text-xs text-white/30 mb-2">
                BRAIN usa o vídeo selecionado como referência de estilo para o RENDERER.
              </p>
              {videosLoading ? (
                <p className="text-xs text-white/30">Carregando biblioteca...</p>
              ) : rawVideos.length === 0 ? (
                <div className="flex items-center gap-2 px-3 py-2 rounded-xl bg-amber-500/10 border border-amber-500/20">
                  <span className="text-amber-400 text-xs">⚠️</span>
                  <span className="text-xs text-amber-300">
                    Nenhum vídeo pronto na biblioteca.{" "}
                    <a href="/dashboard/biblioteca" className="underline hover:text-amber-200">Adicionar vídeos →</a>
                  </span>
                </div>
              ) : (
                <select
                  value={selectedVideoId}
                  onChange={e => setSelectedVideoId(e.target.value)}
                  className="w-full text-sm rounded-xl px-3 py-2"
                  style={{ background: "#1e293b", color: "#e2e8f0", border: "1px solid #334155" }}
                >
                  {rawVideos.map(v => (
                    <option key={v.id} value={v.id}>
                      {v.title || v.original_filename}{v.duration_seconds ? ` (${Math.floor(v.duration_seconds / 60)}:${String(Math.floor(v.duration_seconds % 60)).padStart(2, "0")})` : ""}
                    </option>
                  ))}
                </select>
              )}
            </div>
          )}

          {brainMsg && (
            <div className={`mt-4 px-4 py-3 rounded-xl text-sm border ${brainMsg.ok ? "bg-emerald-500/10 border-emerald-500/30 text-emerald-300" : "bg-red-500/10 border-red-500/30 text-red-300"}`}>
              {brainMsg.text}
            </div>
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
            <p className="text-xs font-semibold text-white/40 uppercase tracking-wider mb-2">Estilo de Conteúdo</p>
            <p className="text-white/70 text-sm capitalize">{office.content_style}</p>
            {office.target_audience && (
              <>
                <p className="text-xs font-semibold text-white/40 uppercase tracking-wider mb-1 mt-3">Público-alvo</p>
                <p className="text-white/50 text-sm">{office.target_audience}</p>
              </>
            )}
          </div>
        </div>

        {/* Decisions */}
        <div className="card-glass rounded-2xl p-6">
          <div className="flex items-center justify-between flex-wrap gap-4 mb-5">
            <div className="flex items-center gap-2 flex-wrap">
              <h2 className="font-bold text-white">📋 Decisões do BRAIN</h2>
              {pendingCount > 0 && (
                <span className="text-xs font-bold px-2 py-0.5 rounded-full bg-yellow-500/20 text-yellow-400 border border-yellow-500/30">
                  {pendingCount} pendente{pendingCount > 1 ? "s" : ""}
                </span>
              )}
            </div>
            <div className="flex gap-1 flex-wrap">
              {STATUS_FILTERS.map(f => (
                <button key={f} onClick={() => setStatusFilter(f)}
                  className={`px-3 py-1.5 text-xs rounded-lg transition-colors font-medium capitalize ${statusFilter === f ? "bg-violet-600/30 text-violet-300 border border-violet-500/40" : "text-white/40 hover:text-white/60 bg-white/[0.03] border border-transparent"}`}>
                  {f === "todos" ? "Todos" : STATUS_LABELS[f]?.replace(/^.\s/, "") ?? f}
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
              {decisions.map(d => {
                const prog = renderProgresses[d.id];
                const isExec = d.status === "executing";
                return (
                  <button key={d.id} onClick={() => setSelectedDecision(d)}
                    className="w-full text-left p-4 rounded-xl bg-white/[0.03] border border-white/[0.06] hover:border-violet-500/30 hover:bg-white/[0.05] transition-all group">
                    <div className="flex items-center gap-4">
                      <div className="shrink-0 w-12 h-12 rounded-full flex items-center justify-center border-2 text-sm font-bold"
                        style={{
                          borderColor: d.confidence_score >= 0.75 ? "#10b981" : d.confidence_score >= 0.5 ? "#f59e0b" : "#ef4444",
                          color: d.confidence_score >= 0.75 ? "#10b981" : d.confidence_score >= 0.5 ? "#f59e0b" : "#ef4444",
                        }}>
                        {Math.round(d.confidence_score * 100)}%
                      </div>
                      <div className="flex-1 min-w-0">
                        <div className="flex items-center gap-2 mb-1 flex-wrap">
                          <p className="text-white font-semibold text-sm truncate">{d.content_topic || "Sem tópico"}</p>
                          <span className={`text-[10px] font-semibold px-2 py-0.5 rounded-full border shrink-0 ${STATUS_STYLES[d.status] ?? ""}`}>
                            {STATUS_LABELS[d.status] ?? d.status}
                          </span>
                        </div>
                        <div className="flex items-center gap-3 text-xs text-white/30">
                          <span>{PLATFORM_ICONS[d.target_platform] ?? "🌐"} {d.target_platform}</span>
                          {d.selected_archetype && <span>🎭 {d.selected_archetype}</span>}
                          <span>{new Date(d.created_at).toLocaleDateString("pt-BR")}</span>
                        </div>
                        {isExec && prog && (
                          <div className="mt-2">
                            <RenderProgressBar progress={prog.progress} stage={prog.stage} />
                          </div>
                        )}
                      </div>
                      <span className="text-white/20 group-hover:text-white/50 transition-colors shrink-0">→</span>
                    </div>
                    {!isExec && (
                      <p className="mt-2 text-white/30 text-xs line-clamp-1 pl-16">{d.hypothesis}</p>
                    )}
                  </button>
                );
              })}
            </div>
          )}
        </div>
      </div>
    </>
  );
}
