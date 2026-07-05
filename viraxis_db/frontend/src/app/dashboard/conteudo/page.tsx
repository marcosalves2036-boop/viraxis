"use client";

import { useEffect, useState, useCallback, Suspense } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import { auth, content as contentApi } from "@/lib/api";

// ── Types ─────────────────────────────────────────────────────────────────────

interface ContentItem {
  id: string;
  decision_id: string | null;
  title: string;
  status: string;
  duration_seconds: number | null;
  production_meta: ProductionMeta;
  script: string;
  created_at: string;
  office_id?: string;
  office_name?: string;
}


interface CorteEdicao { inicio?: number; fim?: number; tipo: string; descricao: string; prioridade?: string }
interface TextoTela { inicio?: number; fim?: number; texto: string }
interface PlanoEdicao {
  hook_timestamp?: number;
  cortes?: CorteEdicao[];
  textos_tela?: TextoTela[];
  trilha_sonora?: string | null;
  duracao_final_segundos?: number;
  notas_producao?: string;
}

interface ProductionMeta {
  mode?: "editing_plan" | "new_script";
  plano_edicao?: PlanoEdicao;
  raw_video?: { id: string; title: string; duration_seconds?: number };
  video_url?: string;
  video_storage_path?: string;

  render_progress?: number;
  render_stage?: string;
  roteiro?: { hook: string; desenvolvimento: string[]; climax: string; cta: string };
  titulos?: string[];
  thumbnails?: ThumbnailConcept[];
  seo?: { titulo_otimizado: string; descricao: string; tags: string[]; hashtags: string[]; categoria: string };
  plano_postagem?: { melhor_dia: string; melhor_horario: string; frequencia_ideal: string; estrategia_reposts: string; notas: string };
  checklist_producao?: string[];
  error?: string;
}

interface ThumbnailConcept {
  descricao: string;
  cores_principais: string[];
  elementos: string[];
  texto_overlay: string;
  composicao: string;
}

interface Office { id: string; name: string; }

const STATUS_STYLES: Record<string, string> = {
  draft:     "bg-white/10 text-white/50",
  rendering: "bg-blue-500/15 text-blue-400",
  review:    "bg-amber-500/15 text-amber-400",
  ready:     "bg-emerald-500/15 text-emerald-400",
  published: "bg-violet-500/15 text-violet-400",
  failed:    "bg-red-500/15 text-red-400",
};

const STATUS_LABELS: Record<string, string> = {
  draft: "Rascunho", rendering: "⚙ Gerando…", review: "👁 Aguardando revisão",
  ready: "✅ Pronto", published: "🚀 Publicado", failed: "❌ Falhou",
};

// ── Content Detail Modal ──────────────────────────────────────────────────────

function ContentModal({
  item, onClose, onDelete, onApprove, isGenerating,
}: {
  item: ContentItem;
  onClose: () => void;
  onDelete: (id: string, officeId: string) => Promise<void>;
  onApprove?: (itemId: string, officeId: string) => Promise<void>;
  isGenerating?: boolean;
}) {
  const [activeTab, setActiveTab] = useState<"roteiro" | "thumbnails" | "seo" | "plano" | "checklist">("roteiro");
  const [selectedThumb, setSelectedThumb] = useState(0);
  const [deleting, setDeleting] = useState(false);
  const [confirmDel, setConfirmDel] = useState(false);
  const meta = item.production_meta;

  async function handleDelete() {
    if (!confirmDel) { setConfirmDel(true); return; }
    setDeleting(true);
    await onDelete(item.id, item.office_id ?? "");
    onClose();
  }

  const tabs = [
    { id: "roteiro" as const, label: meta.plano_edicao ? "✂️ Edição" : "📝 Roteiro" },
    { id: "thumbnails" as const, label: "🖼 Thumbnails" },
    { id: "seo" as const, label: "📊 SEO" },
    { id: "plano" as const, label: "📅 Plano" },
    { id: "checklist" as const, label: "✅ Checklist" },
  ];

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4" onClick={onClose}>
      <div className="absolute inset-0 bg-black/75 backdrop-blur-sm" />
      <div
        className="relative w-full max-w-3xl max-h-[92vh] flex flex-col rounded-2xl border overflow-hidden"
        style={{ background: "rgba(8,9,16,0.99)", borderColor: "rgba(255,255,255,0.08)" }}
        onClick={e => e.stopPropagation()}
      >
        {/* Header */}
        <div className="px-6 pt-6 pb-4 border-b border-white/[0.06] shrink-0">
          <div className="flex items-start justify-between gap-4">
            <div className="flex-1 min-w-0">
              <span className={`inline-block text-xs font-semibold px-2 py-0.5 rounded-full mb-2 ${STATUS_STYLES[item.status]}`}>
                {STATUS_LABELS[item.status]}
              </span>
              <h2 className="text-base font-bold text-white leading-snug">{item.title}</h2>
              {item.duration_seconds && (
                <p className="text-white/30 text-xs mt-1">⏱ {Math.round(item.duration_seconds)}s • {item.office_name}</p>
              )}
            </div>
            <button onClick={onClose} className="text-white/30 hover:text-white/60 text-xl shrink-0">✕</button>
          </div>

          {/* Title variations */}
          {meta.titulos && meta.titulos.length > 1 && (
            <div className="mt-3 space-y-1">
              <p className="text-xs text-white/30 font-semibold uppercase tracking-wider mb-1.5">Variações de Título</p>
              {meta.titulos.map((t, i) => (
                <div key={i} className="flex items-start gap-2">
                  <span className="text-[10px] text-white/25 shrink-0 mt-0.5">#{i+1}</span>
                  <p className="text-white/60 text-xs">{t}</p>
                </div>
              ))}
            </div>
          )}
        </div>

        {/* Ação: aprovar / progresso / player */}
        {item.status === "review" && onApprove && (
          <div className="mx-6 mt-4 mb-1 p-3 rounded-xl border border-amber-500/20 bg-amber-500/5 shrink-0">
            <p className="text-amber-400 text-xs font-semibold mb-2">👁 Roteiro aguardando aprovação</p>
            <button
              onClick={() => onApprove(item.id, item.office_id ?? "")}
              disabled={isGenerating}
              className="w-full py-2 bg-emerald-600/80 hover:bg-emerald-500 disabled:opacity-60 disabled:cursor-not-allowed text-white text-sm font-bold rounded-lg transition-colors"
            >
              {isGenerating ? "⚙️ Aprovando e gerando vídeo…" : "✅ Aprovar roteiro e gerar vídeo"}
            </button>
          </div>
        )}
        {item.status === "rendering" && (
          <div className="mx-6 mt-4 mb-1 p-3 rounded-xl border border-blue-500/20 bg-blue-500/5 shrink-0">
            <p className="text-blue-400 text-xs font-semibold">⚙️ Gerando vídeo… aguarde ~60s</p>
            <div className="mt-2 h-1.5 rounded-full bg-white/10 overflow-hidden">
              <div className="h-full rounded-full bg-gradient-to-r from-violet-500 to-cyan-400 animate-pulse w-1/2" />
            </div>
          </div>
        )}
        {(item.status === "ready" || item.status === "published") && item.production_meta?.video_url && (
          <div className="mx-6 mt-4 mb-1 shrink-0">
            <video
              src={item.production_meta.video_url}
              controls
              className="w-full rounded-xl aspect-[9/16] max-h-64 bg-black object-contain"
            />
            <a
              href={item.production_meta.video_url}
              target="_blank"
              rel="noopener noreferrer"
              className="mt-2 block text-center text-xs text-violet-400 hover:text-violet-300"
            >
              ⬇️ Baixar vídeo
            </a>
          </div>
        )}

        {/* Tabs */}
        <div className="flex gap-0 border-b border-white/[0.06] shrink-0 overflow-x-auto">
          {tabs.map(t => (
            <button key={t.id} onClick={() => setActiveTab(t.id)}
              className={`px-4 py-3 text-xs font-medium whitespace-nowrap transition-colors border-b-2 ${activeTab === t.id ? "border-violet-500 text-violet-300" : "border-transparent text-white/30 hover:text-white/55"}`}>
              {t.label}
            </button>
          ))}
        </div>

        {/* Content */}
        <div className="flex-1 overflow-y-auto p-6">

          {/* ROTEIRO */}
          {activeTab === "roteiro" && (
            <div className="space-y-4">
              {meta.plano_edicao ? (
                <>
                  {meta.raw_video && (
                    <div className="bg-white/[0.04] border border-white/10 rounded-xl p-3 flex items-center justify-between gap-2">
                      <p className="text-white/50 text-xs">🎞 Vídeo bruto: <span className="text-white/80">{meta.raw_video.title}</span></p>
                      {meta.raw_video.duration_seconds && <span className="text-white/30 text-xs">{Math.round(meta.raw_video.duration_seconds)}s brutos</span>}
                    </div>
                  )}
                  <div className="bg-yellow-500/10 border border-yellow-500/20 rounded-xl p-4">
                    <p className="text-xs font-semibold text-yellow-400 uppercase tracking-wider mb-1.5">🎣 Hook</p>
                    <p className="text-white/75 text-sm">Começa aos <strong>{meta.plano_edicao.hook_timestamp ?? "?"}s</strong> do vídeo bruto — usar como abertura do vídeo final.</p>
                  </div>
                  <div>
                    <p className="text-xs font-semibold text-white/40 uppercase tracking-wider mb-2">✂️ Cortes</p>
                    <div className="space-y-2">
                      {(meta.plano_edicao.cortes ?? []).map((c, i) => (
                        <div key={i} className="flex gap-3 bg-white/[0.03] rounded-xl p-3 items-start">
                          <span className="text-violet-400 font-mono text-xs shrink-0 mt-0.5">{c.inicio ?? "?"}s–{c.fim ?? "?"}s</span>
                          <div className="flex-1">
                            <p className="text-white/65 text-sm leading-relaxed">{c.descricao}</p>
                            <p className="text-[10px] mt-1">
                              <span className="text-white/30 uppercase">{c.tipo}</span>
                              {c.prioridade && <span className={`ml-2 px-1.5 py-0.5 rounded ${c.prioridade === "essencial" ? "bg-red-500/15 text-red-400" : c.prioridade === "recomendado" ? "bg-amber-500/15 text-amber-400" : "bg-white/10 text-white/40"}`}>{c.prioridade}</span>}
                            </p>
                          </div>
                        </div>
                      ))}
                    </div>
                  </div>
                  {(meta.plano_edicao.textos_tela ?? []).length > 0 && (
                    <div>
                      <p className="text-xs font-semibold text-white/40 uppercase tracking-wider mb-2">💬 Textos na tela</p>
                      <div className="space-y-2">
                        {(meta.plano_edicao.textos_tela ?? []).map((t, i) => (
                          <div key={i} className="flex gap-3 bg-white/[0.03] rounded-xl p-3">
                            <span className="text-cyan-400 font-mono text-xs shrink-0 mt-0.5">{t.inicio ?? "?"}s–{t.fim ?? "?"}s</span>
                            <p className="text-white/75 text-sm font-semibold">{t.texto}</p>
                          </div>
                        ))}
                      </div>
                    </div>
                  )}
                  <div className="bg-emerald-500/10 border border-emerald-500/20 rounded-xl p-4">
                    <p className="text-xs font-semibold text-emerald-400 uppercase tracking-wider mb-1.5">🎵 Trilha & duração final</p>
                    <p className="text-white/75 text-sm">{meta.plano_edicao.trilha_sonora || "Manter áudio original"} • final ~{meta.plano_edicao.duracao_final_segundos ?? "?"}s</p>
                  </div>
                  {meta.plano_edicao.notas_producao && (
                    <div className="bg-violet-500/10 border border-violet-500/20 rounded-xl p-4">
                      <p className="text-xs font-semibold text-violet-400 uppercase tracking-wider mb-1.5">📝 Notas de produção</p>
                      <p className="text-white/75 text-sm leading-relaxed">{meta.plano_edicao.notas_producao}</p>
                    </div>
                  )}
                </>
              ) : meta.roteiro ? (
                <>
                  <div className="bg-yellow-500/10 border border-yellow-500/20 rounded-xl p-4">
                    <p className="text-xs font-semibold text-yellow-400 uppercase tracking-wider mb-1.5">🎣 Hook (primeiros segundos)</p>
                    <p className="text-white/75 text-sm leading-relaxed">{meta.roteiro.hook}</p>
                  </div>
                  <div>
                    <p className="text-xs font-semibold text-white/40 uppercase tracking-wider mb-2">🎬 Desenvolvimento</p>
                    <div className="space-y-2">
                      {meta.roteiro.desenvolvimento.map((cena, i) => (
                        <div key={i} className="flex gap-3 bg-white/[0.03] rounded-xl p-3">
                          <span className="text-violet-400 font-bold text-sm shrink-0">{i+1}</span>
                          <p className="text-white/65 text-sm leading-relaxed">{cena}</p>
                        </div>
                      ))}
                    </div>
                  </div>
                  <div className="bg-emerald-500/10 border border-emerald-500/20 rounded-xl p-4">
                    <p className="text-xs font-semibold text-emerald-400 uppercase tracking-wider mb-1.5">⚡ Clímax</p>
                    <p className="text-white/75 text-sm leading-relaxed">{meta.roteiro.climax}</p>
                  </div>
                  <div className="bg-violet-500/10 border border-violet-500/20 rounded-xl p-4">
                    <p className="text-xs font-semibold text-violet-400 uppercase tracking-wider mb-1.5">📣 Call to Action</p>
                    <p className="text-white/75 text-sm leading-relaxed">{meta.roteiro.cta}</p>
                  </div>
                </>
              ) : (
                <pre className="text-white/50 text-xs whitespace-pre-wrap leading-relaxed font-mono">{item.script}</pre>
              )}
            </div>
          )}

          {/* THUMBNAILS */}
          {activeTab === "thumbnails" && (
            <div className="space-y-4">
              {meta.thumbnails && meta.thumbnails.length > 0 ? (
                <>
                  {/* Selector */}
                  <div className="flex gap-2">
                    {meta.thumbnails.map((_, i) => (
                      <button key={i} onClick={() => setSelectedThumb(i)}
                        className={`px-3 py-1.5 text-xs rounded-lg font-medium transition-colors ${selectedThumb === i ? "bg-violet-600/30 text-violet-300 border border-violet-500/40" : "bg-white/[0.05] text-white/40 border border-transparent"}`}>
                        Opção {i + 1}
                      </button>
                    ))}
                  </div>

                  {/* Selected thumbnail */}
                  {(() => {
                    const th = meta.thumbnails![selectedThumb];
                    return (
                      <div className="space-y-3">
                        {/* Color preview */}
                        <div className="flex items-center gap-3 bg-white/[0.03] rounded-xl p-4">
                          <div className="flex gap-1.5">
                            {th.cores_principais.map((c, i) => (
                              <div key={i} className="w-8 h-8 rounded-lg border border-white/10" style={{ background: c }} title={c} />
                            ))}
                          </div>
                          <div>
                            <p className="text-white/60 text-xs">{th.cores_principais.join(" · ")}</p>
                          </div>
                        </div>

                        <div className="grid gap-3">
                          <div className="bg-white/[0.03] rounded-xl p-4">
                            <p className="text-xs text-white/40 uppercase tracking-wider font-semibold mb-1.5">Texto em destaque</p>
                            <p className="text-white font-bold text-lg">{th.texto_overlay}</p>
                          </div>
                          <div className="bg-white/[0.03] rounded-xl p-4">
                            <p className="text-xs text-white/40 uppercase tracking-wider font-semibold mb-1.5">Conceito visual</p>
                            <p className="text-white/65 text-sm leading-relaxed">{th.descricao}</p>
                          </div>
                          <div className="bg-white/[0.03] rounded-xl p-4">
                            <p className="text-xs text-white/40 uppercase tracking-wider font-semibold mb-1.5">Composição</p>
                            <p className="text-white/65 text-sm leading-relaxed">{th.composicao}</p>
                          </div>
                          <div>
                            <p className="text-xs text-white/40 uppercase tracking-wider font-semibold mb-1.5">Elementos visuais</p>
                            <div className="flex flex-wrap gap-1.5">
                              {th.elementos.map((e, i) => (
                                <span key={i} className="text-xs px-2.5 py-1 rounded-lg bg-white/[0.06] text-white/55 border border-white/[0.08]">{e}</span>
                              ))}
                            </div>
                          </div>
                        </div>
                      </div>
                    );
                  })()}
                </>
              ) : <p className="text-white/25 text-sm">Conceitos de thumbnail não disponíveis.</p>}
            </div>
          )}

          {/* SEO */}
          {activeTab === "seo" && meta.seo && (
            <div className="space-y-4">
              <div className="bg-white/[0.03] rounded-xl p-4">
                <p className="text-xs text-white/40 uppercase tracking-wider font-semibold mb-1.5">Título otimizado</p>
                <p className="text-white font-semibold text-sm">{meta.seo.titulo_otimizado}</p>
              </div>
              <div className="bg-white/[0.03] rounded-xl p-4">
                <p className="text-xs text-white/40 uppercase tracking-wider font-semibold mb-1.5">Descrição</p>
                <p className="text-white/65 text-sm leading-relaxed whitespace-pre-line">{meta.seo.descricao}</p>
              </div>
              <div className="grid grid-cols-2 gap-3">
                <div>
                  <p className="text-xs text-white/40 uppercase tracking-wider font-semibold mb-1.5">Tags</p>
                  <div className="flex flex-wrap gap-1.5">
                    {meta.seo.tags?.map((t, i) => (
                      <span key={i} className="text-xs px-2 py-0.5 rounded-md bg-blue-500/10 text-blue-300 border border-blue-500/20">{t}</span>
                    ))}
                  </div>
                </div>
                <div>
                  <p className="text-xs text-white/40 uppercase tracking-wider font-semibold mb-1.5">Hashtags</p>
                  <div className="flex flex-wrap gap-1.5">
                    {meta.seo.hashtags?.map((h, i) => (
                      <span key={i} className="text-xs px-2 py-0.5 rounded-md bg-violet-500/10 text-violet-300 border border-violet-500/20">{h}</span>
                    ))}
                  </div>
                </div>
              </div>
              {meta.seo.categoria && (
                <div>
                  <p className="text-xs text-white/40 uppercase tracking-wider font-semibold mb-1">Categoria</p>
                  <p className="text-white/55 text-sm">{meta.seo.categoria}</p>
                </div>
              )}
            </div>
          )}

          {/* PLANO */}
          {activeTab === "plano" && meta.plano_postagem && (
            <div className="grid gap-3">
              {[
                { label: "📅 Melhor dia", value: meta.plano_postagem.melhor_dia },
                { label: "⏰ Melhor horário", value: meta.plano_postagem.melhor_horario },
                { label: "🔄 Frequência ideal", value: meta.plano_postagem.frequencia_ideal },
                { label: "♻️ Estratégia de reposts", value: meta.plano_postagem.estrategia_reposts },
                { label: "💡 Notas", value: meta.plano_postagem.notas },
              ].map(({ label, value }) => value && (
                <div key={label} className="bg-white/[0.03] rounded-xl p-4">
                  <p className="text-xs text-white/40 uppercase tracking-wider font-semibold mb-1.5">{label}</p>
                  <p className="text-white/70 text-sm leading-relaxed">{value}</p>
                </div>
              ))}
            </div>
          )}

          {/* CHECKLIST */}
          {activeTab === "checklist" && (
            <div className="space-y-2">
              {meta.checklist_producao && meta.checklist_producao.length > 0 ? (
                meta.checklist_producao.map((item, i) => (
                  <div key={i} className="flex items-start gap-3 bg-white/[0.03] rounded-xl p-3.5">
                    <span className="text-emerald-400 shrink-0 mt-0.5">☐</span>
                    <p className="text-white/65 text-sm leading-relaxed">{item}</p>
                  </div>
                ))
              ) : <p className="text-white/25 text-sm">Checklist não disponível.</p>}
            </div>
          )}
        </div>
        {/* Delete footer */}
        <div className="px-6 pb-5 flex justify-end border-t border-white/[0.05] pt-4">
          {confirmDel ? (
            <div className="flex items-center gap-3">
              <span className="text-white/40 text-xs">Confirmar exclusão?</span>
              <button onClick={() => setConfirmDel(false)} className="px-3 py-1.5 text-xs text-white/50 hover:text-white/70 transition-colors">Cancelar</button>
              <button onClick={handleDelete} disabled={deleting}
                className="px-3 py-1.5 text-xs bg-red-600 hover:bg-red-500 disabled:opacity-50 text-white rounded-lg transition-colors font-semibold">
                {deleting ? "Deletando…" : "Deletar mesmo assim"}
              </button>
            </div>
          ) : (
            <button onClick={handleDelete}
              className="px-3 py-1.5 text-xs text-red-400/60 hover:text-red-400 hover:bg-red-500/10 rounded-lg transition-colors">
              🗑 Deletar conteúdo
            </button>
          )}
        </div>
      </div>
    </div>
  );
}

// ── Main Page ─────────────────────────────────────────────────────────────────

function ConteudoInner() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const officeFilter = searchParams.get("office");

  const [items, setItems] = useState<ContentItem[]>([]);
  const [offices, setOffices] = useState<Office[]>([]);
  const [loading, setLoading] = useState(true);
  const [selectedItem, setSelectedItem] = useState<ContentItem | null>(null);
  const [generatingItems, setGeneratingItems] = useState<Set<string>>(new Set());
  const [officeId, setOfficeId] = useState(officeFilter ?? "all");

  const token = typeof window !== "undefined" ? localStorage.getItem("viraxis_token") : null;
  const headers = { Authorization: `Bearer ${token}` };

  const loadContent = useCallback(async (oid: string) => {
    setLoading(true);
    try {
      const officeList = oid === "all" ? offices : offices.filter(o => o.id === oid);
      const allItems: ContentItem[] = [];

      for (const o of officeList) {
        try {
          const r = await fetch(`/api/offices/${o.id}/content`, { headers });
          if (r.ok) {
            const data: ContentItem[] = await r.json();
            data.forEach(d => { d.office_id = o.id; d.office_name = o.name; });
            allItems.push(...data);
          }
        } catch {}
      }

      allItems.sort((a, b) => b.created_at.localeCompare(a.created_at));
      setItems(allItems);
    } finally { setLoading(false); }
  }, [offices, token]);

  useEffect(() => {
    if (!auth.getToken()) { router.replace("/login"); return; }
    (async () => {
      const r = await fetch("/api/offices", { headers });
      if (r.ok) setOffices(await r.json());
    })();
  }, []);

  useEffect(() => {
    if (offices.length > 0) loadContent(officeId);
  }, [offices, officeId]);

  async function deleteItem(itemId: string, officeId: string) {
    if (!officeId) return;
    await fetch(`/api/offices/${officeId}/content/${itemId}`, {
      method: "DELETE",
      headers,
    });
    setItems(prev => prev.filter(i => i.id !== itemId));
  }

  function updateItem(id: string, patch: Partial<ContentItem>) {
    setItems(prev => prev.map(i => i.id === id ? { ...i, ...patch } : i));
    setSelectedItem(prev => prev?.id === id ? { ...prev, ...patch } : prev);
  }

  async function approveItem(itemId: string, officeId: string) {
    if (!officeId) return;

    // 1. Aprovar roteiro (muda status no backend)
    const r = await fetch(`/api/offices/${officeId}/content/${itemId}/approve`, {
      method: "PATCH", headers,
    });
    if (!r.ok) return;

    // 2. Sinalizar geração (card + modal em sincronia)
    updateItem(itemId, { status: "rendering" });
    setGeneratingItems(prev => new Set(prev).add(itemId));

    // 3. Disparar process-video direto no Render (evita timeout 10s do proxy Vercel)
    try {
      const result = await contentApi.processVideo(officeId, itemId);
      const currentMeta = items.find(i => i.id === itemId)?.production_meta ?? ({} as ProductionMeta);
      updateItem(itemId, {
        status: "ready",
        production_meta: { ...currentMeta, video_url: result.video_url },
      });
    } catch (err) {
      console.error("Erro ao gerar vídeo:", err);
      // Rollback visual: voltar para review para o usuário tentar de novo
      updateItem(itemId, { status: "review" });
    } finally {
      setGeneratingItems(prev => { const s = new Set(prev); s.delete(itemId); return s; });
    }
  }

  async function rejectItem(itemId: string, officeId: string) {
    if (!officeId) return;
    const r = await fetch(`/api/offices/${officeId}/content/${itemId}/reject`, {
      method: "PATCH", headers,
    });
    if (r.ok) setItems(prev => prev.filter(i => i.id !== itemId));
  }

  const ready = items.filter(i => i.status === "ready" || i.status === "published");
  const review = items.filter(i => i.status === "review");
  const rendering = items.filter(i => i.status === "rendering");
  const failed = items.filter(i => i.status === "failed");

  return (
    <>
      {selectedItem && (
        <ContentModal
          item={selectedItem}
          onClose={() => setSelectedItem(null)}
          onDelete={deleteItem}
          onApprove={approveItem}
          isGenerating={generatingItems.has(selectedItem.id)}
        />
      )}

      <div className="max-w-5xl mx-auto space-y-6">
        <div className="flex items-start justify-between gap-4 flex-wrap">
          <div>
            <h1 className="text-2xl font-black text-white">Conteúdo</h1>
            <p className="text-white/40 text-sm mt-1">Pacotes completos gerados pelo RENDERER — roteiro, thumbnails, SEO e mais.</p>
          </div>
          {offices.length > 1 && (
            <select
              value={officeId}
              onChange={e => setOfficeId(e.target.value)}
              className="px-3 py-2 bg-white/[0.05] border border-white/10 rounded-xl text-white/70 text-sm focus:outline-none focus:border-violet-500/50"
            >
              <option value="all">Todos os escritórios</option>
              {offices.map(o => <option key={o.id} value={o.id}>{o.name}</option>)}
            </select>
          )}
        </div>

        {/* Stats */}
        <div className="grid grid-cols-3 gap-4">
          <div className="card-glass rounded-2xl p-4 text-center">
            <p className="text-3xl font-black text-emerald-400">{ready.length}</p>
            <p className="text-white/40 text-xs mt-1">Prontos</p>
          </div>
          <div className="card-glass rounded-2xl p-4 text-center">
            <p className="text-3xl font-black text-blue-400">{rendering.length}</p>
            <p className="text-white/40 text-xs mt-1">Gerando</p>
          </div>
          <div className="card-glass rounded-2xl p-4 text-center">
            <p className="text-3xl font-black text-white/50">{items.length}</p>
            <p className="text-white/40 text-xs mt-1">Total</p>
          </div>
        </div>

        {/* Generating alert */}
        {rendering.length > 0 && (
          <div className="bg-blue-500/10 border border-blue-500/20 rounded-2xl p-4 flex items-center gap-3">
            <span className="animate-spin text-lg">⚙️</span>
            <p className="text-blue-300 text-sm">
              <strong>{rendering.length}</strong> conteúdo(s) sendo gerado(s) pelo RENDERER…
            </p>
          </div>
        )}

        {/* Content grid */}
        {loading ? (
          <div className="text-center py-16 text-white/25 text-sm animate-pulse">Carregando conteúdos…</div>
        ) : items.length === 0 ? (
          <div className="text-center py-16 card-glass rounded-2xl">
            <p className="text-5xl mb-4">📝</p>
            <p className="text-white/30 text-sm">Nenhum conteúdo gerado ainda.</p>
            <p className="text-white/20 text-xs mt-2">Aprove uma decisão do BRAIN para gerar conteúdo automaticamente.</p>
            <button onClick={() => router.push("/dashboard/escritorios")}
              className="mt-4 px-4 py-2 bg-violet-600/30 border border-violet-500/30 text-violet-300 text-sm rounded-xl hover:bg-violet-600/40 transition-colors">
              Ir para Escritórios →
            </button>
          </div>
        ) : (
          <div className="grid gap-4 sm:grid-cols-2">
            {items.map(item => {
              const meta = item.production_meta;
              const isReady = item.status === "ready" || item.status === "published";
              const isReview = item.status === "review";
              const isRendering = item.status === "rendering";

              return (
                <div key={item.id}
                  className={`relative text-left p-5 rounded-2xl border transition-all ${isReady ? "card-glass hover:border-violet-500/30" : isReview ? "card-glass hover:border-amber-500/30" : "card-glass opacity-70"} border-white/[0.06]`}>

                  {/* Status + Office + Delete */}
                  <div className="flex items-center justify-between gap-2 mb-3">
                    <div className="flex items-center gap-2">
                      <span className={`text-[10px] font-bold px-2 py-0.5 rounded-full ${STATUS_STYLES[item.status]}`}>
                        {STATUS_LABELS[item.status]}
                      </span>
                      {meta.mode === "editing_plan" && (
                        <span className="text-[10px] font-bold px-2 py-0.5 rounded-full bg-cyan-500/10 text-cyan-400 border border-cyan-500/20">✂️ com referência</span>
                      )}
                      {item.office_name && (
                        <span className="text-[10px] text-white/25 truncate">{item.office_name}</span>
                      )}
                    </div>
                    <button
                      onClick={e => { e.stopPropagation(); deleteItem(item.id, item.office_id ?? ""); }}
                      className="text-white/20 hover:text-red-400 transition-colors text-xs px-1.5 py-0.5 rounded hover:bg-red-500/10"
                      title="Deletar conteúdo"
                    >🗑</button>
                  </div>

                  {/* Title */}
                  <p onClick={() => (isReady || isReview) && setSelectedItem(item)} className={`text-white font-semibold text-sm leading-snug mb-3 line-clamp-2 ${(isReady || isReview) ? "cursor-pointer hover:text-violet-200 transition-colors" : ""}`}>{item.title}</p>

                  {/* Rendering progress */}
                  {isRendering && (
                    <div className="mb-3">
                      <div className="flex justify-between text-xs text-white/30 mb-1">
                        <span>{meta.render_stage ?? "gerando…"}</span>
                        <span>{meta.render_progress ?? 0}%</span>
                      </div>
                      <div className="h-1 rounded-full bg-white/[0.08] overflow-hidden">
                        <div className="h-full rounded-full bg-gradient-to-r from-violet-500 to-cyan-400 transition-all duration-500"
                          style={{ width: `${meta.render_progress ?? 0}%` }} />
                      </div>
                    </div>
                  )}

                  {/* Review actions */}
                  {isReview && (
                    <div className="mb-3 p-3 rounded-xl border border-amber-500/20 bg-amber-500/5">
                      <p className="text-amber-400 text-xs font-semibold mb-2">👁 Roteiro aguardando sua aprovação</p>
                      <div className="flex gap-2">
                        <button
                          onClick={e => { e.stopPropagation(); approveItem(item.id, item.office_id ?? ""); }}
                          disabled={generatingItems.has(item.id)}
                          className="flex-1 py-1.5 bg-emerald-600/80 hover:bg-emerald-500 disabled:opacity-60 disabled:cursor-not-allowed text-white text-xs font-bold rounded-lg transition-colors"
                        >{generatingItems.has(item.id) ? "⚙️ Gerando vídeo…" : "✅ Aprovar roteiro"}</button>
                        <button
                          onClick={e => { e.stopPropagation(); rejectItem(item.id, item.office_id ?? ""); }}
                          className="flex-1 py-1.5 bg-red-900/60 hover:bg-red-800/60 text-white text-xs font-bold rounded-lg transition-colors"
                        >🔄 Rejeitar</button>
                      </div>
                    </div>
                  )}

                  {/* Artifacts preview */}
                  {isReady && (
                    <div className="flex flex-wrap gap-1.5 mb-3">
                      {meta.plano_edicao && <span className="text-[10px] px-2 py-0.5 rounded-md bg-cyan-500/10 text-cyan-400">✂️ Plano de edição</span>}
                      {meta.roteiro && <span className="text-[10px] px-2 py-0.5 rounded-md bg-white/[0.06] text-white/40">📝 Roteiro</span>}
                      {meta.thumbnails && meta.thumbnails.length > 0 && <span className="text-[10px] px-2 py-0.5 rounded-md bg-white/[0.06] text-white/40">🖼 {meta.thumbnails.length} thumbnails</span>}
                      {meta.seo && <span className="text-[10px] px-2 py-0.5 rounded-md bg-white/[0.06] text-white/40">📊 SEO</span>}
                      {meta.checklist_producao && <span className="text-[10px] px-2 py-0.5 rounded-md bg-white/[0.06] text-white/40">✅ {meta.checklist_producao.length} itens</span>}
                    </div>
                  )}

                  <div className="flex items-center justify-between text-xs text-white/25">
                    <span>{new Date(item.created_at).toLocaleDateString("pt-BR")}</span>
                    {item.duration_seconds && <span>⏱ {Math.round(item.duration_seconds)}s</span>}
                    {(isReady || isReview) && (
                      <button onClick={() => setSelectedItem(item)} className="text-violet-400/60 hover:text-violet-300 transition-colors">
                        {meta.plano_edicao ? "Ver plano →" : "Ver roteiro →"}
                      </button>
                    )}
                  </div>
                </div>
              );
            })}
          </div>
        )}
      </div>
    </>
  );
}

export default function ConteudoPage() {
  return (
    <Suspense fallback={<div className="flex items-center justify-center min-h-[60vh]"><div className="text-white/30 animate-pulse text-sm">Carregando…</div></div>}>
      <ConteudoInner />
    </Suspense>
  );
}
