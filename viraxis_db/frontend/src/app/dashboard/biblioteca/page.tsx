"use client";

import { useEffect, useState, useCallback, useRef } from "react";
import { useSearchParams } from "next/navigation";
import { Suspense } from "react";
import { offices as officesApi } from "@/lib/api";

interface Office { id: string; name: string; }

interface AiAnalysis {
  overall_summary?: string;
  detected_topics?: string[];
  predominant_tone?: string;
  transcription_text?: string;
  scenes?: Array<{ start: number; end: number; description: string }>;
  editorial_highlights?: Array<{ start: number; end: number; reason: string }>;
}

interface RawVideo {
  id: string; office_id: string; title: string | null;
  original_filename: string; status: string;
  duration_seconds: number | null; tags: string[];
  description: string | null; r2_url: string | null;
  ai_analysis: AiAnalysis | null;
  created_at: string;
}

interface GeneratedItem {
  id: string; title: string; status: string; created_at: string;
  production_meta?: { raw_video?: { id?: string }; raw_video_id?: string; video_url?: string };
}

const STATUS_LABEL: Record<string, string> = {
  pending: "Aguardando", ready: "Pronto", processing: "Analisando...", failed: "Falhou",
};
const STATUS_CLASS: Record<string, string> = {
  pending:    "bg-white/10 text-white/50 border-white/10",
  ready:      "bg-green-500/10 text-green-400 border-green-500/20",
  processing: "bg-violet-500/10 text-violet-400 border-violet-500/20",
  failed:     "bg-red-500/10 text-red-400 border-red-500/20",
};

function fmtDuration(s: number | null) {
  if (!s) return "—";
  return `${Math.floor(s / 60)}:${String(Math.floor(s % 60)).padStart(2, "0")}`;
}

// ── Modal de detalhe do vídeo ─────────────────────────────────────────────────

function VideoModal({
  video, officeId, onClose, onDelete, onSaved,
}: {
  video: RawVideo;
  officeId: string;
  onClose: () => void;
  onDelete: (id: string) => Promise<void>;
  onSaved: () => void;
}) {
  const [editing, setEditing] = useState(false);
  const [editTitle, setEditTitle] = useState(video.title || "");
  const [editTags, setEditTags] = useState((video.tags || []).join(", "));
  const [generated, setGenerated] = useState<GeneratedItem[]>([]);
  const [loadingGen, setLoadingGen] = useState(true);
  const [brainRunning, setBrainRunning] = useState(false);
  const [brainMsg, setBrainMsg] = useState<string | null>(null);
  const [showBrainModal, setShowBrainModal] = useState(false);
  const [nVideos, setNVideos] = useState(0);
  const [batchLoading, setBatchLoading] = useState(false);
  const [batchResult, setBatchResult] = useState<number | null>(null);

  const token = typeof window !== "undefined" ? localStorage.getItem("viraxis_token") : null;

  useEffect(() => {
    (async () => {
      setLoadingGen(true);
      try {
        const r = await fetch(`/api/offices/${officeId}/content`, {
          headers: { Authorization: `Bearer ${token}` },
        });
        if (r.ok) {
          const items: GeneratedItem[] = await r.json();
          setGenerated(items.filter(i =>
            i.production_meta?.raw_video?.id === video.id ||
            i.production_meta?.raw_video_id === video.id
          ));
        }
      } finally { setLoadingGen(false); }
    })();
  }, [video.id, officeId]);

  async function handleSave() {
    await fetch(`/api/raw-videos/${video.id}`, {
      method: "PATCH",
      headers: { "Content-Type": "application/json", Authorization: `Bearer ${token}` },
      body: JSON.stringify({
        title: editTitle || null,
        tags: editTags ? editTags.split(",").map(t => t.trim()).filter(Boolean) : [],
      }),
    });
    setEditing(false);
    onSaved();
  }

  async function handleUseBrain() {
    setBrainRunning(true); setBrainMsg(null);
    try {
      await officesApi.runBrainWithVideo(officeId, video.id);
      setBrainMsg("✅ Decisão criada! Veja no escritório → decisões.");
    } catch (e) {
      setBrainMsg(`❌ ${e instanceof Error ? e.message : "Erro ao rodar BRAIN"}`);
    } finally { setBrainRunning(false); }
  }

  async function handleBatchBrain() {
    if (!video || !officeId) return;
    setBatchLoading(true);
    setBatchResult(null);
    try {
      const res = await fetch("/api/brain/batch-run", {
        method: "POST",
        headers: { "Content-Type": "application/json", Authorization: `Bearer ${token}` },
        body: JSON.stringify({
          office_id: officeId,
          raw_video_id: video.id,
          n_videos: nVideos,
        }),
      });
      if (!res.ok) throw new Error(await res.text());
      const data = await res.json();
      setBatchResult(data.total);
    } catch (err) {
      console.error("batch-brain error:", err);
    } finally {
      setBatchLoading(false);
    }
  }

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4" onClick={onClose}>
      <div className="absolute inset-0 bg-black/75 backdrop-blur-sm" />
      <div
        className="relative w-full max-w-2xl max-h-[92vh] overflow-y-auto rounded-2xl border border-white/[0.08] p-6 space-y-4"
        style={{ background: "rgba(8,9,16,0.99)" }}
        onClick={e => e.stopPropagation()}
      >
        <div className="flex items-start justify-between gap-3">
          <div className="min-w-0">
            <span className={`inline-block text-xs font-semibold px-2 py-0.5 rounded-full border mb-2 ${STATUS_CLASS[video.status] || STATUS_CLASS.pending}`}>
              {STATUS_LABEL[video.status] || video.status}
            </span>
            <h2 className="text-base font-bold text-white leading-snug truncate">
              {video.title || video.original_filename}
            </h2>
            <p className="text-white/30 text-xs mt-1">
              ⏱ {fmtDuration(video.duration_seconds)} • 📅 {new Date(video.created_at).toLocaleDateString("pt-BR")}
              {video.tags?.length > 0 && <> • 🏷 {video.tags.slice(0, 5).join(", ")}</>}
            </p>
          </div>
          <button onClick={onClose} className="text-white/30 hover:text-white/60 text-xl shrink-0">✕</button>
        </div>

        {/* Player */}
        {video.r2_url ? (
          <video src={video.r2_url} controls className="w-full rounded-xl bg-black aspect-video" />
        ) : (
          <div className="w-full rounded-xl bg-black/60 aspect-video flex items-center justify-center text-white/20 text-4xl">🎬</div>
        )}

        {/* Resumo da IA */}
        {video.ai_analysis?.overall_summary && (
          <div className="bg-white/[0.04] border border-white/10 rounded-xl p-4">
            <p className="text-xs font-semibold text-white/40 uppercase tracking-wider mb-1.5">🧠 Análise de IA</p>
            <p className="text-white/70 text-sm leading-relaxed">{video.ai_analysis.overall_summary}</p>
            {video.ai_analysis.detected_topics && video.ai_analysis.detected_topics.length > 0 && (
              <p className="text-white/40 text-xs mt-2">
                Tópicos: {video.ai_analysis.detected_topics.slice(0, 6).join(", ")}
                {video.ai_analysis.predominant_tone && <> • Tom: {video.ai_analysis.predominant_tone}</>}
              </p>
            )}
          </div>
        )}

        {/* Edição de metadados */}
        {editing && (
          <div className="space-y-3">
            <input
              value={editTitle} onChange={e => setEditTitle(e.target.value)} placeholder="Título (opcional)"
              className="w-full bg-white/[0.06] border border-white/10 rounded-xl px-4 py-2.5 text-sm text-white placeholder-white/20 focus:outline-none focus:border-violet-500/60 transition-colors"
            />
            <input
              value={editTags} onChange={e => setEditTags(e.target.value)} placeholder="Tags separadas por vírgula"
              className="w-full bg-white/[0.06] border border-white/10 rounded-xl px-4 py-2.5 text-sm text-white placeholder-white/20 focus:outline-none focus:border-violet-500/60 transition-colors"
            />
            <div className="flex gap-2">
              <button onClick={handleSave} className="px-4 py-2 bg-green-600 hover:bg-green-500 text-white rounded-xl text-sm font-semibold transition-colors">Salvar</button>
              <button onClick={() => setEditing(false)} className="px-4 py-2 bg-white/[0.06] hover:bg-white/10 text-white/60 rounded-xl text-sm transition-colors">Cancelar</button>
            </div>
          </div>
        )}

        {/* Conteúdos gerados a partir deste vídeo */}
        <div>
          <p className="text-xs font-semibold text-white/40 uppercase tracking-wider mb-2">📦 Conteúdos gerados deste vídeo</p>
          {loadingGen ? (
            <p className="text-white/25 text-xs animate-pulse">Carregando…</p>
          ) : generated.length === 0 ? (
            <p className="text-white/25 text-xs">Nenhum conteúdo gerado ainda. Use o BRAIN para criar uma decisão com este vídeo.</p>
          ) : (
            <div className="space-y-2">
              {generated.map(g => (
                <a key={g.id} href={`/dashboard/conteudo/${g.id}`}
                  className="block bg-white/[0.03] hover:bg-white/[0.06] rounded-xl p-3 transition-colors">
                  <div className="flex items-center justify-between gap-2">
                    <span className="text-white/75 text-sm truncate">{g.title}</span>
                    <span className="text-white/30 text-xs shrink-0">{g.status}</span>
                  </div>
                  <p className="text-white/25 text-[11px] mt-1">👁 0 · ❤️ 0 · 💬 0 · {new Date(g.created_at).toLocaleDateString("pt-BR")}</p>
                </a>
              ))}
            </div>
          )}
        </div>

        {brainMsg && <p className="text-xs text-white/60">{brainMsg}</p>}

        {/* Ações */}
        <div className="flex gap-2 flex-wrap pt-1">
          <button onClick={() => setEditing(!editing)}
            className="px-3 py-2 bg-white/[0.06] hover:bg-white/10 border border-white/10 text-white/60 rounded-xl text-xs transition-colors">
            ✏️ Editar metadados
          </button>
          <button
            onClick={() => {
              const highlights = video?.ai_analysis?.editorial_highlights ?? [];
              if (highlights.length >= 2) {
                setNVideos(0);
                setBatchResult(null);
                setShowBrainModal(true);
              } else {
                handleUseBrain();
              }
            }}
            disabled={brainRunning || video.status !== "ready"}
            className="px-3 py-2 bg-violet-600 hover:bg-violet-500 disabled:opacity-50 disabled:cursor-not-allowed text-white rounded-xl text-xs font-semibold transition-colors">
            {brainRunning ? "⚙️ Rodando BRAIN…" : "🧠 Usar no BRAIN"}
          </button>
          <button onClick={() => onDelete(video.id)}
            className="px-3 py-2 bg-red-500/10 hover:bg-red-500/20 border border-red-500/20 text-red-400 rounded-xl text-xs transition-colors ml-auto">
            🗑 Excluir
          </button>
        </div>

        {showBrainModal && (() => {
          const highlights = video.ai_analysis?.editorial_highlights ?? [];
          return (
            <div className="fixed inset-0 z-[60] bg-black/70 flex items-center justify-center p-4">
              <div className="bg-[#0f0f17] border border-white/10 rounded-2xl p-6 w-full max-w-md space-y-5">
                <h3 className="text-white font-semibold">🤖 Quantos vídeos gerar?</h3>
                <div className="space-y-2">
                  {[
                    { label: `Auto — ${Math.min(highlights.length, 5)} destaques detectados`, value: 0 },
                    { label: "1 vídeo", value: 1 },
                    { label: "2 vídeos", value: 2 },
                    { label: "3 vídeos", value: 3 },
                  ].map(opt => (
                    <label key={opt.value} className="flex items-center gap-3 p-3 rounded-xl bg-white/[0.04] cursor-pointer hover:bg-white/[0.07]">
                      <input type="radio" name="n_videos" value={opt.value}
                        checked={nVideos === opt.value}
                        onChange={() => setNVideos(opt.value)}
                        className="accent-violet-500" />
                      <span className="text-white/80 text-sm">{opt.label}</span>
                    </label>
                  ))}
                </div>
                {highlights.length > 0 && (
                  <div className="space-y-2">
                    <p className="text-xs text-white/40 uppercase tracking-wider">Destaques detectados</p>
                    {highlights.slice(0, 5).map((hl: {start: number; end: number; reason: string}, i: number) => (
                      <div key={i} className="flex gap-2 text-xs bg-white/[0.03] rounded-lg p-2">
                        <span className="text-violet-400 font-mono shrink-0">
                          {Math.floor(hl.start/60)}:{String(Math.floor(hl.start%60)).padStart(2,"0")}–
                          {Math.floor(hl.end/60)}:{String(Math.floor(hl.end%60)).padStart(2,"0")}
                        </span>
                        <span className="text-white/60">{hl.reason}</span>
                      </div>
                    ))}
                  </div>
                )}
                {batchResult !== null && (
                  <p className="text-center text-xs text-emerald-400">
                    ✅ {batchResult} decisões criadas — acesse Gerenciar Escritório para aprovar.
                  </p>
                )}
                <div className="flex gap-3 pt-2">
                  <button onClick={() => setShowBrainModal(false)}
                    className="flex-1 py-2.5 rounded-xl border border-white/10 text-white/50 text-sm hover:bg-white/[0.04]">
                    Cancelar
                  </button>
                  <button onClick={handleBatchBrain} disabled={batchLoading}
                    className="flex-1 py-2.5 rounded-xl bg-violet-600 hover:bg-violet-500 text-white text-sm font-medium disabled:opacity-50">
                    {batchLoading ? "Gerando..." : "Gerar com o BRAIN →"}
                  </button>
                </div>
              </div>
            </div>
          );
        })()}
      </div>
    </div>
  );
}

// ── Página principal ──────────────────────────────────────────────────────────

function BibliotecaContent() {
  const searchParams = useSearchParams();
  const [offices, setOffices] = useState<Office[]>([]);
  const [selectedOfficeId, setSelectedOfficeId] = useState<string>(searchParams.get("office_id") || "");
  const [videos, setVideos] = useState<RawVideo[]>([]);
  const [loading, setLoading] = useState(false);
  const [uploading, setUploading] = useState(false);
  const [uploadError, setUploadError] = useState<string | null>(null);
  const [uploadProgress, setUploadProgress] = useState<number | null>(null);
  const [uploadLabel, setUploadLabel] = useState<string | null>(null);
  const [thumbnails, setThumbnails] = useState<Record<string, string>>({});
  const [selectedVideo, setSelectedVideo] = useState<RawVideo | null>(null);
  const fileInputRef = useRef<HTMLInputElement | null>(null);

  useEffect(() => {
    const token = localStorage.getItem("viraxis_token");
    if (!token) return;
    fetch("/api/offices", { headers: { Authorization: `Bearer ${token}` } })
      .then(r => r.json())
      .then(data => {
        if (Array.isArray(data)) {
          setOffices(data);
          if (!selectedOfficeId && data.length > 0) setSelectedOfficeId(data[0].id);
        }
      }).catch(() => {});
  }, []);

  const loadVideos = useCallback(() => {
    if (!selectedOfficeId) return;
    const token = localStorage.getItem("viraxis_token");
    if (!token) return;
    setLoading(true);
    fetch(`/api/raw-videos?office_id=${selectedOfficeId}`, { headers: { Authorization: `Bearer ${token}` } })
      .then(r => r.json())
      .then(data => { if (Array.isArray(data)) setVideos(data); })
      .catch(() => {}).finally(() => setLoading(false));
  }, [selectedOfficeId]);

  useEffect(() => { loadVideos(); }, [loadVideos]);

  // Polling a cada 8s enquanto houver vídeos processando
  useEffect(() => {
    const processing = videos.some(v => v.status === "processing" || v.status === "pending");
    if (!processing) return;
    const id = setInterval(() => loadVideos(), 8000);
    return () => clearInterval(id);
  }, [videos, loadVideos]);

  // Thumbnails via canvas (frame ~3s) para vídeos prontos
  useEffect(() => {
    videos
      .filter(v => v.status === "ready" && v.r2_url && !thumbnails[v.id])
      .forEach(v => {
        const vid = document.createElement("video");
        vid.crossOrigin = "anonymous";
        vid.muted = true;
        vid.preload = "metadata";
        vid.src = v.r2_url!;
        vid.onloadedmetadata = () => {
          try { vid.currentTime = Math.min(3, (vid.duration || 6) / 2); } catch {}
        };
        vid.onseeked = () => {
          try {
            const canvas = document.createElement("canvas");
            canvas.width = 320; canvas.height = 180;
            canvas.getContext("2d")!.drawImage(vid, 0, 0, 320, 180);
            setThumbnails(prev => ({ ...prev, [v.id]: canvas.toDataURL("image/jpeg", 0.75) }));
          } catch {
            // CORS/canvas tainted — mantém fallback 🎬
          }
          vid.src = "";
        };
        vid.onerror = () => { /* fallback 🎬 */ };
      });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [videos]);

  // Upload multi-arquivo: upload-url → PUT direto Supabase → confirm-upload
  async function handleMultiUpload(e: React.ChangeEvent<HTMLInputElement>) {
    const files = Array.from(e.target.files ?? []);
    if (!files.length || !selectedOfficeId) return;
    const token = localStorage.getItem("viraxis_token");
    if (!token) return;
    setUploading(true); setUploadError(null);
    try {
      for (let i = 0; i < files.length; i++) {
        const file = files[i];
        setUploadLabel(files.length > 1 ? `Enviando ${i + 1}/${files.length} — ${file.name}` : `Enviando ${file.name}`);
        setUploadProgress(0);

        // 1. Pedir signed upload URL ao backend
        const r1 = await fetch("/api/raw-videos/upload-url", {
          method: "POST",
          headers: { "Content-Type": "application/json", Authorization: `Bearer ${token}` },
          body: JSON.stringify({
            office_id: selectedOfficeId,
            filename: file.name,
            mime_type: file.type || "video/mp4",
            file_size_bytes: file.size,
          }),
        });
        if (!r1.ok) {
          const d = await r1.json().catch(() => ({}));
          throw new Error((d as { detail?: string }).detail || `Erro ao preparar upload de ${file.name}`);
        }
        const { video_id, upload_url } = await r1.json();

        // 2. PUT direto browser → Supabase (não passa pelo Render)
        await new Promise<void>((resolve, reject) => {
          const xhr = new XMLHttpRequest();
          xhr.open("PUT", upload_url);
          xhr.setRequestHeader("Content-Type", file.type || "video/mp4");
          xhr.upload.onprogress = ev => {
            if (ev.lengthComputable) setUploadProgress(Math.round((ev.loaded / ev.total) * 100));
          };
          xhr.onload = () => (xhr.status >= 200 && xhr.status < 300)
            ? resolve()
            : reject(new Error(`Upload de ${file.name} falhou (${xhr.status})`));
          xhr.onerror = () => reject(new Error(`Erro de rede enviando ${file.name}`));
          xhr.send(file);
        });

        // 3. Confirmar — extrai duração + dispara análise de IA
        const r3 = await fetch(`/api/raw-videos/${video_id}/confirm-upload`, {
          method: "POST",
          headers: { "Content-Type": "application/json", Authorization: `Bearer ${token}` },
          body: JSON.stringify({ file_size_bytes: file.size }),
        });
        if (!r3.ok) {
          const d = await r3.json().catch(() => ({}));
          throw new Error((d as { detail?: string }).detail || `Erro ao confirmar upload de ${file.name}`);
        }
      }
      loadVideos();
    } catch (err: unknown) {
      setUploadError(err instanceof Error ? err.message : "Erro desconhecido");
      loadVideos();
    } finally {
      setUploading(false); setUploadProgress(null); setUploadLabel(null);
      if (e.target) e.target.value = "";
    }
  }

  async function handleDelete(id: string) {
    if (!confirm("Excluir este vídeo da biblioteca?")) return;
    const token = localStorage.getItem("viraxis_token");
    if (!token) return;
    await fetch(`/api/raw-videos/${id}`, { method: "DELETE", headers: { Authorization: `Bearer ${token}` } });
    setSelectedVideo(null);
    loadVideos();
  }

  return (
    <div className="space-y-6">
      {selectedVideo && (
        <VideoModal
          video={selectedVideo}
          officeId={selectedOfficeId}
          onClose={() => setSelectedVideo(null)}
          onDelete={handleDelete}
          onSaved={() => { setSelectedVideo(null); loadVideos(); }}
        />
      )}

      <div>
        <h1 className="text-2xl font-black text-white">Biblioteca</h1>
        <p className="text-white/40 text-sm mt-1">
          Vídeos brutos que serão editados e publicados pelo pipeline.
        </p>
      </div>

      <div className="flex flex-wrap gap-3 items-center">
        <select
          value={selectedOfficeId}
          onChange={e => setSelectedOfficeId(e.target.value)}
          className="bg-white/[0.06] border border-white/10 rounded-xl px-3 py-2 text-sm text-white focus:outline-none focus:border-violet-500/60 transition-colors"
        >
          {offices.length === 0 && <option value="">Carregando escritórios...</option>}
          {offices.map(o => <option key={o.id} value={o.id}>{o.name}</option>)}
        </select>

        <label className={`px-4 py-2 rounded-xl text-sm font-semibold transition-colors cursor-pointer select-none ${uploading || !selectedOfficeId ? "bg-violet-900 text-white/40 cursor-not-allowed" : "bg-violet-600 hover:bg-violet-500 text-white"}`}>
          {uploading ? "Enviando..." : "Upload ▲"}
          <input ref={fileInputRef} type="file" accept="video/*" multiple onChange={handleMultiUpload} className="hidden" disabled={uploading || !selectedOfficeId} />
        </label>
      </div>

      {uploadProgress !== null && uploading && (
        <div className="card-glass rounded-xl p-4 space-y-2">
          <div className="flex justify-between text-xs text-white/50">
            <span>{uploadLabel ?? "Enviando vídeo..."}</span>
            <span>{uploadProgress}%</span>
          </div>
          <div className="bg-white/10 rounded-full h-1.5">
            <div className="bg-violet-500 rounded-full h-1.5 transition-all duration-200" style={{ width: `${uploadProgress}%` }} />
          </div>
        </div>
      )}

      {uploadError && (
        <div className="bg-red-500/10 border border-red-500/30 rounded-xl px-4 py-3 text-sm text-red-300">
          {uploadError}
        </div>
      )}

      {loading && videos.length === 0 ? (
        <div className="text-white/40 text-sm py-8 text-center">Carregando...</div>
      ) : videos.length === 0 ? (
        <div className="card-glass rounded-2xl p-12 text-center space-y-3">
          <div className="text-5xl">🎬</div>
          <p className="text-white/60 text-base">Nenhum vídeo na biblioteca ainda.</p>
          <p className="text-white/30 text-sm">Adicione vídeos brutos para o pipeline usar como base de publicação.</p>
        </div>
      ) : (
        <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-4 gap-4">
          {videos.map(v => (
            <button
              key={v.id}
              onClick={() => setSelectedVideo(v)}
              className="card-glass rounded-2xl overflow-hidden text-left group hover:border-violet-500/30 border border-white/[0.06] transition-all"
            >
              {/* Thumbnail 16:9 */}
              <div className="relative aspect-video bg-black flex items-center justify-center">
                {thumbnails[v.id] ? (
                  // eslint-disable-next-line @next/next/no-img-element
                  <img src={thumbnails[v.id]} alt={v.title || v.original_filename} className="w-full h-full object-cover" />
                ) : (
                  <span className="text-3xl opacity-30">🎬</span>
                )}
                {/* Overlays de status */}
                {v.status === "processing" && (
                  <div className="absolute inset-0 bg-black/55 flex flex-col items-center justify-center gap-1.5">
                    <span className="animate-spin text-lg">⚙️</span>
                    <span className="text-violet-300 text-[11px] font-semibold">Analisando...</span>
                  </div>
                )}
                {v.status === "ready" && (
                  <span className="absolute top-1.5 right-1.5 text-xs bg-black/60 rounded-full px-1.5 py-0.5">✅</span>
                )}
                {v.status === "failed" && (
                  <span className="absolute top-1.5 right-1.5 text-xs bg-black/60 rounded-full px-1.5 py-0.5">❌</span>
                )}
                {/* Duração */}
                <span className="absolute bottom-1.5 left-1.5 text-[11px] font-semibold text-white bg-black/70 rounded px-1.5 py-0.5">
                  ▶ {fmtDuration(v.duration_seconds)}
                </span>
              </div>
              {/* Título */}
              <div className="p-2.5">
                <p className="text-white/80 text-xs font-medium truncate group-hover:text-white transition-colors">
                  {v.title || v.original_filename}
                </p>
                <p className="text-white/25 text-[10px] mt-0.5">
                  {new Date(v.created_at).toLocaleDateString("pt-BR")}
                </p>
              </div>
            </button>
          ))}

          {/* Card "+" para upload */}
          <button
            onClick={() => fileInputRef.current?.click()}
            disabled={uploading || !selectedOfficeId}
            className="rounded-2xl border-2 border-dashed border-white/10 hover:border-violet-500/40 aspect-auto min-h-[140px] flex flex-col items-center justify-center gap-2 text-white/25 hover:text-violet-300 transition-colors disabled:opacity-40 disabled:cursor-not-allowed"
          >
            <span className="text-3xl">+</span>
            <span className="text-xs font-semibold">Upload ▲</span>
          </button>
        </div>
      )}
    </div>
  );
}

export default function BibliotecaPage() {
  return (
    <Suspense fallback={<div className="text-white/40 text-sm p-8">Carregando biblioteca...</div>}>
      <BibliotecaContent />
    </Suspense>
  );
}
