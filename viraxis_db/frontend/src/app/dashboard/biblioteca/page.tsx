"use client";

import { useEffect, useState, useCallback } from "react";
import { useSearchParams } from "next/navigation";
import { Suspense } from "react";

interface Office { id: string; name: string; }
interface RawVideo {
  id: string; office_id: string; title: string | null;
  original_filename: string; status: string;
  duration_seconds: number | null; tags: string[];
  description: string | null; r2_url: string | null; created_at: string;
}

const STATUS_LABEL: Record<string, string> = {
  pending: "Aguardando", ready: "Pronto", processing: "Processando", failed: "Falhou",
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

function BibliotecaContent() {
  const searchParams = useSearchParams();
  const [offices, setOffices] = useState<Office[]>([]);
  const [selectedOfficeId, setSelectedOfficeId] = useState<string>(searchParams.get("office_id") || "");
  const [videos, setVideos] = useState<RawVideo[]>([]);
  const [loading, setLoading] = useState(false);
  const [uploading, setUploading] = useState(false);
  const [uploadError, setUploadError] = useState<string | null>(null);
  const [uploadProgress, setUploadProgress] = useState<number | null>(null);
  const [editingId, setEditingId] = useState<string | null>(null);
  const [editTitle, setEditTitle] = useState("");
  const [editTags, setEditTags] = useState("");

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

  async function handleUpload(e: React.ChangeEvent<HTMLInputElement>) {
    const file = e.target.files?.[0];
    if (!file || !selectedOfficeId) return;
    const token = localStorage.getItem("viraxis_token");
    if (!token) return;
    setUploading(true); setUploadError(null); setUploadProgress(0);
    try {
      const formData = new FormData();
      formData.append("file", file);
      formData.append("office_id", selectedOfficeId);
      const result = await new Promise<Response>((resolve, reject) => {
        const xhr = new XMLHttpRequest();
        xhr.open("POST", "/api/raw-videos/upload");
        xhr.setRequestHeader("Authorization", `Bearer ${token}`);
        xhr.upload.onprogress = (ev) => {
          if (ev.lengthComputable) setUploadProgress(Math.round((ev.loaded / ev.total) * 100));
        };
        xhr.onload = () => resolve(new Response(xhr.responseText, { status: xhr.status, headers: { "Content-Type": "application/json" } }));
        xhr.onerror = () => reject(new Error("Erro de rede durante upload"));
        xhr.send(formData);
      });
      if (!result.ok) {
        const data = await result.json().catch(() => ({}));
        if (result.status === 503) throw new Error("Armazenamento não configurado. Contate o suporte.");
        throw new Error((data as { detail?: string }).detail || "Erro ao fazer upload");
      }
      loadVideos();
    } catch (err: unknown) {
      setUploadError(err instanceof Error ? err.message : "Erro desconhecido");
    } finally { setUploading(false); setUploadProgress(null); e.target.value = ""; }
  }

  async function handleDelete(id: string) {
    if (!confirm("Excluir este vídeo da biblioteca?")) return;
    const token = localStorage.getItem("viraxis_token");
    if (!token) return;
    await fetch(`/api/raw-videos/${id}`, { method: "DELETE", headers: { Authorization: `Bearer ${token}` } });
    loadVideos();
  }

  async function handleSaveEdit(id: string) {
    const token = localStorage.getItem("viraxis_token");
    if (!token) return;
    await fetch(`/api/raw-videos/${id}`, {
      method: "PATCH",
      headers: { "Content-Type": "application/json", Authorization: `Bearer ${token}` },
      body: JSON.stringify({ title: editTitle || null, tags: editTags ? editTags.split(",").map((t: string) => t.trim()).filter(Boolean) : [] }),
    });
    setEditingId(null); loadVideos();
  }

  function startEdit(v: RawVideo) {
    setEditingId(v.id);
    setEditTitle(v.title || "");
    setEditTags((v.tags || []).join(", "));
  }

  return (
    <div className="space-y-6">
      {/* Header */}
      <div>
        <h1 className="text-2xl font-black text-white">Biblioteca</h1>
        <p className="text-white/40 text-sm mt-1">
          Vídeos brutos que serão editados e publicados pelo pipeline.
        </p>
      </div>

      {/* Controles */}
      <div className="flex flex-wrap gap-3 items-center">
        <select
          value={selectedOfficeId}
          onChange={e => setSelectedOfficeId(e.target.value)}
          className="bg-white/[0.06] border border-white/10 rounded-xl px-3 py-2 text-sm text-white focus:outline-none focus:border-violet-500/60 transition-colors"
        >
          {offices.length === 0 && <option value="">Carregando escritórios...</option>}
          {offices.map(o => <option key={o.id} value={o.id}>{o.name}</option>)}
        </select>

        <label className={`px-4 py-2 rounded-xl text-sm font-semibold transition-colors cursor-pointer select-none
          ${uploading || !selectedOfficeId
            ? "bg-violet-900 text-white/40 cursor-not-allowed"
            : "bg-violet-600 hover:bg-violet-500 text-white"}`}>
          {uploading ? "Enviando..." : "+ Adicionar vídeo"}
          <input type="file" accept="video/*" onChange={handleUpload} className="hidden" disabled={uploading || !selectedOfficeId} />
        </label>
      </div>

      {/* Barra de progresso de upload */}
      {uploadProgress !== null && uploading && (
        <div className="card-glass rounded-xl p-4 space-y-2">
          <div className="flex justify-between text-xs text-white/50">
            <span>Enviando vídeo...</span>
            <span>{uploadProgress}%</span>
          </div>
          <div className="bg-white/10 rounded-full h-1.5">
            <div
              className="bg-violet-500 rounded-full h-1.5 transition-all duration-200"
              style={{ width: `${uploadProgress}%` }}
            />
          </div>
        </div>
      )}

      {/* Erro de upload */}
      {uploadError && (
        <div className="bg-red-500/10 border border-red-500/30 rounded-xl px-4 py-3 text-sm text-red-300">
          {uploadError}
        </div>
      )}

      {/* Lista de vídeos */}
      {loading ? (
        <div className="text-white/40 text-sm py-8 text-center">Carregando...</div>
      ) : videos.length === 0 ? (
        <div className="card-glass rounded-2xl p-12 text-center space-y-3">
          <div className="text-5xl">🎬</div>
          <p className="text-white/60 text-base">Nenhum vídeo na biblioteca ainda.</p>
          <p className="text-white/30 text-sm">Adicione um vídeo bruto para o pipeline usar como base de publicação.</p>
        </div>
      ) : (
        <div className="space-y-3">
          {videos.map(v => (
            <div key={v.id} className="card-glass rounded-2xl p-4">
              {editingId === v.id ? (
                /* Modo edição */
                <div className="space-y-3">
                  <input
                    value={editTitle}
                    onChange={e => setEditTitle(e.target.value)}
                    placeholder="Título (opcional)"
                    className="w-full bg-white/[0.06] border border-white/10 rounded-xl px-4 py-2.5 text-sm text-white placeholder-white/20 focus:outline-none focus:border-violet-500/60 transition-colors"
                  />
                  <input
                    value={editTags}
                    onChange={e => setEditTags(e.target.value)}
                    placeholder="Tags separadas por vírgula"
                    className="w-full bg-white/[0.06] border border-white/10 rounded-xl px-4 py-2.5 text-sm text-white placeholder-white/20 focus:outline-none focus:border-violet-500/60 transition-colors"
                  />
                  <div className="flex gap-2">
                    <button
                      onClick={() => handleSaveEdit(v.id)}
                      className="px-4 py-2 bg-green-600 hover:bg-green-500 text-white rounded-xl text-sm font-semibold transition-colors"
                    >
                      Salvar
                    </button>
                    <button
                      onClick={() => setEditingId(null)}
                      className="px-4 py-2 bg-white/[0.06] hover:bg-white/10 text-white/60 rounded-xl text-sm transition-colors"
                    >
                      Cancelar
                    </button>
                  </div>
                </div>
              ) : (
                /* Modo visualização */
                <div className="flex justify-between items-start gap-4 flex-wrap">
                  <div className="flex-1 min-w-0">
                    {/* Título + badge de status */}
                    <div className="flex items-center gap-2 mb-1.5 flex-wrap">
                      <span className="font-semibold text-white text-sm truncate">
                        {v.title || v.original_filename}
                      </span>
                      <span className={`text-xs font-semibold px-2 py-0.5 rounded-full border ${STATUS_CLASS[v.status] || STATUS_CLASS.pending}`}>
                        {STATUS_LABEL[v.status] || v.status}
                      </span>
                    </div>
                    {/* Metadados */}
                    <div className="flex gap-4 text-xs text-white/40 flex-wrap">
                      <span>⏱ {fmtDuration(v.duration_seconds)}</span>
                      <span>📅 {new Date(v.created_at).toLocaleDateString("pt-BR")}</span>
                      {v.tags?.length > 0 && (
                        <span>🏷 {v.tags.slice(0, 4).join(", ")}{v.tags.length > 4 ? "…" : ""}</span>
                      )}
                    </div>
                    {v.description && (
                      <p className="text-xs text-white/30 mt-2 truncate">
                        {v.description.slice(0, 120)}{v.description.length > 120 ? "…" : ""}
                      </p>
                    )}
                  </div>

                  {/* Ações */}
                  <div className="flex gap-2 flex-shrink-0">
                    {v.r2_url && (
                      <a
        