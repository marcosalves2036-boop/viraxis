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

const STATUS_LABEL: Record<string, string> = { pending: "Aguardando", ready: "Pronto", processing: "Processando", failed: "Falhou" };
const STATUS_COLOR: Record<string, string> = { pending: "#888", ready: "#22c55e", processing: "#a78bfa", failed: "#ef4444" };

function BibliotecaContent() {
  const searchParams = useSearchParams();
  const [offices, setOffices] = useState<Office[]>([]);
  const [selectedOfficeId, setSelectedOfficeId] = useState<string>(searchParams.get("office_id") || "");
  const [videos, setVideos] = useState<RawVideo[]>([]);
  const [loading, setLoading] = useState(false);
  const [uploading, setUploading] = useState(false);
  const [uploadError, setUploadError] = useState<string | null>(null);
  const [editingId, setEditingId] = useState<string | null>(null);
  const [editTitle, setEditTitle] = useState("");
  const [editTags, setEditTags] = useState("");
  const [r2Warning, setR2Warning] = useState(false);

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
    setUploading(true); setUploadError(null); setR2Warning(false);
    try {
      const presignRes = await fetch("/api/raw-videos/presign", {
        method: "POST",
        headers: { "Content-Type": "application/json", Authorization: `Bearer ${token}` },
        body: JSON.stringify({ office_id: selectedOfficeId, filename: file.name, content_type: file.type }),
      });
      const presignData = await presignRes.json();
      if (!presignRes.ok) {
        if (presignRes.status === 503 || JSON.stringify(presignData).includes("R2")) { setR2Warning(true); return; }
        throw new Error(presignData?.detail || "Erro ao gerar URL de upload");
      }
      const uploadRes = await fetch(presignData.upload_url, { method: "PUT", headers: { "Content-Type": file.type }, body: file });
      if (!uploadRes.ok) throw new Error("Falha no upload para armazenamento");
      const confirmRes = await fetch("/api/raw-videos", {
        method: "POST",
        headers: { "Content-Type": "application/json", Authorization: `Bearer ${token}` },
        body: JSON.stringify({ office_id: selectedOfficeId, r2_key: presignData.r2_key, original_filename: file.name }),
      });
      if (!confirmRes.ok) throw new Error("Erro ao registrar vídeo");
      loadVideos();
    } catch (err: unknown) {
      setUploadError(err instanceof Error ? err.message : "Erro desconhecido");
    } finally { setUploading(false); e.target.value = ""; }
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

  function startEdit(v: RawVideo) { setEditingId(v.id); setEditTitle(v.title || ""); setEditTags((v.tags || []).join(", ")); }
  function fmtDuration(s: number | null) { if (!s) return "—"; return `${Math.floor(s/60)}:${String(Math.floor(s%60)).padStart(2,"0")}`; }

  return (
    <div style={{ padding: "32px 24px", maxWidth: 900, margin: "0 auto", color: "#e2e8f0" }}>
      <h1 style={{ fontSize: 28, fontWeight: 700, marginBottom: 8 }}>📂 Biblioteca</h1>
      <p style={{ color: "#94a3b8", marginBottom: 24 }}>Vídeos brutos que o BRAIN pode usar como referência de estilo.</p>

      <div style={{ marginBottom: 24, display: "flex", gap: 12, alignItems: "center", flexWrap: "wrap" }}>
        <select value={selectedOfficeId} onChange={e => setSelectedOfficeId(e.target.value)}
          style={{ background: "#1e293b", color: "#e2e8f0", border: "1px solid #334155", borderRadius: 8, padding: "8px 12px", fontSize: 14 }}>
          {offices.map(o => <option key={o.id} value={o.id}>{o.name}</option>)}
        </select>
        <label style={{ background: "#7c3aed", color: "#fff", padding: "8px 16px", borderRadius: 8, cursor: uploading ? "not-allowed" : "pointer", fontSize: 14, fontWeight: 600, opacity: uploading ? 0.6 : 1 }}>
          {uploading ? "Enviando..." : "＋ Adicionar vídeo"}
          <input type="file" accept="video/*" onChange={handleUpload} style={{ display: "none" }} disabled={uploading || !selectedOfficeId} />
        </label>
      </div>

      {r2Warning && (
        <div style={{ background: "#431407", border: "1px solid #ea580c", borderRadius: 8, padding: 16, marginBottom: 20, color: "#fed7aa" }}>
          ⚠️ <strong>Armazenamento R2 não configurado.</strong> Configure <code>R2_ACCESS_KEY_ID</code>, <code>R2_SECRET_ACCESS_KEY</code> e <code>R2_ENDPOINT_URL</code> no Render para habilitar uploads.
        </div>
      )}
      {uploadError && (
        <div style={{ background: "#450a0a", border: "1px solid #ef4444", borderRadius: 8, padding: 12, marginBottom: 20, color: "#fca5a5" }}>❌ {uploadError}</div>
      )}

      {loading ? <p style={{ color: "#94a3b8" }}>Carregando...</p>
      : videos.length === 0 ? (
        <div style={{ textAlign: "center", padding: "48px 24px", color: "#64748b" }}>
          <div style={{ fontSize: 48, marginBottom: 12 }}>🎬</div>
          <p style={{ fontSize: 16 }}>Nenhum vídeo na biblioteca ainda.</p>
          <p style={{ fontSize: 13, marginTop: 4 }}>Adicione um vídeo bruto para o BRAIN usar como referência de estilo.</p>
        </div>
      ) : (
        <div style={{ display: "flex", flexDirection: "column", gap: 12 }}>
          {videos.map(v => (
            <div key={v.id} style={{ background: "#1e293b", border: "1px solid #334155", borderRadius: 10, padding: 16 }}>
              {editingId === v.id ? (
                <div style={{ display: "flex", flexDirection: "column", gap: 10 }}>
                  <input value={editTitle} onChange={e => setEditTitle(e.target.value)} placeholder="Título (opcional)"
                    style={{ background: "#0f172a", color: "#e2e8f0", border: "1px solid #475569", borderRadius: 6, padding: "6px 10px", fontSize: 14 }} />
                  <input value={editTags} onChange={e => setEditTags(e.target.value)} placeholder="Tags separadas por vírgula"
                    style={{ background: "#0f172a", color: "#e2e8f0", border: "1px solid #475569", borderRadius: 6, padding: "6px 10px", fontSize: 14 }} />
                  <div style={{ display: "flex", gap: 8 }}>
                    <button onClick={() => handleSaveEdit(v.id)} style={{ background: "#22c55e", color: "#fff", border: "none", borderRadius: 6, padding: "6px 14px", cursor: "pointer", fontSize: 13, fontWeight: 600 }}>Salvar</button>
                    <button onClick={() => setEditingId(null)} style={{ background: "#475569", color: "#e2e8f0", border: "none", borderRadius: 6, padding: "6px 14px", cursor: "pointer", fontSize: 13 }}>Cancelar</button>
                  </div>
                </div>
              ) : (
                <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", flexWrap: "wrap", gap: 8 }}>
                  <div style={{ flex: 1 }}>
                    <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 4 }}>
                      <span style={{ fontWeight: 600, fontSize: 15 }}>{v.title || v.original_filename}</span>
                      <span style={{ fontSize: 11, fontWeight: 600, padding: "2px 8px", borderRadius: 999, background: STATUS_COLOR[v.status] + "22", color: STATUS_COLOR[v.status], border: `1px solid ${STATUS_COLOR[v.status]}44` }}>
                        {STATUS_LABEL[v.status] || v.status}
                      </span>
                    </div>
                    <div style={{ display: "flex", gap: 16, fontSize: 12, color: "#94a3b8", flexWrap: "wrap" }}>
                      <span>⏱ {fmtDuration(v.duration_seconds)}</span>
                      <span>📅 {new Date(v.created_at).toLocaleDateString("pt-BR")}</span>
                      {v.tags?.length > 0 && <span>🏷 {v.tags.slice(0,4).join(", ")}{v.tags.length > 4 ? "…" : ""}</span>}
                    </div>
                    {v.description && <p style={{ fontSize: 12, color: "#64748b", marginTop: 6, marginBottom: 0 }}>{v.description.slice(0,120)}{v.description.length > 120 ? "…" : ""}</p>}
                  </div>
                  <div style={{ display: "flex", gap: 6, flexShrink: 0 }}>
                    {v.r2_url && <a href={v.r2_url} target="_blank" rel="noopener noreferrer" style={{ background: "#0f172a", color: "#94a3b8", border: "1px solid #334155", borderRadius: 6, padding: "5px 10px", fontSize: 12, textDecoration: "none" }}>▶ Ver</a>}
                    <button onClick={() => startEdit(v)} style={{ background: "#0f172a", color: "#94a3b8", border: "1px solid #334155", borderRadius: 6, padding: "5px 10px", fontSize: 12, cursor: "pointer" }}>✏️ Editar</button>
                    <button onClick={() => handleDelete(v.id)} style={{ background: "#0f172a", color: "#ef4444", border: "1px solid #991b1b", borderRadius: 6, padding: "5px 10px", fontSize: 12, cursor: "pointer" }}>🗑</button>
                  </div>
                </div>
              )}
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

export default function BibliotecaPage() {
  return (
    <Suspense fallback={<div style={{ padding: 32, color: "#94a3b8" }}>Carregando biblioteca...</div>}>
      <BibliotecaContent />
    </Suspense>
  );
}
