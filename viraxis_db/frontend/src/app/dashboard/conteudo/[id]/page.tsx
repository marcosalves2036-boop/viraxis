"use client";

import { useEffect, useState } from "react";
import { useParams, useRouter } from "next/navigation";
import { auth, content } from "@/lib/api";

function toText(val: unknown): string {
  if (!val) return "";
  if (typeof val === "string") return val;
  if (typeof val === "object") {
    const o = val as Record<string, unknown>;
    return String(o.narracao ?? o["narração"] ?? o.content ?? Object.values(o).join(" "));
  }
  return String(val);
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
  thumbnails?: { descricao: string; cores_principais: string[]; elementos: string[]; texto_overlay: string; composicao: string }[];
  seo?: { titulo_otimizado: string; descricao: string; tags: string[]; hashtags: string[]; categoria: string };
  plano_postagem?: { melhor_dia: string; melhor_horario: string; frequencia_ideal: string; estrategia_reposts: string; notas: string };
  checklist_producao?: string[];
  error?: string;
}

interface ContentItem {
  id: string; decision_id: string | null; title: string; status: string;
  duration_seconds: number | null; production_meta: ProductionMeta; script: string;
  created_at: string;
}

export default function ContentDetailPage() {
  const { id } = useParams<{ id: string }>();
  const router = useRouter();
  const [item, setItem] = useState<ContentItem | null>(null);
  const [loading, setLoading] = useState(true);
  const [activeTab, setActiveTab] = useState<"roteiro" | "thumbnails" | "seo" | "plano" | "checklist">("roteiro");
  const [selectedThumb, setSelectedThumb] = useState(0);
  const [officeId, setOfficeId] = useState<string | null>(null);
  const [videoUrl, setVideoUrl] = useState<string | null>(null);
  const [generating, setGenerating] = useState(false);
  const [genError, setGenError] = useState<string | null>(null);

  const token = typeof window !== "undefined" ? localStorage.getItem("viraxis_token") : null;

  useEffect(() => {
    if (!auth.getToken()) { router.replace("/login"); return; }
    // We need to search all offices for this content item
    (async () => {
      setLoading(true);
      try {
        const r = await fetch("/api/offices", { headers: { Authorization: `Bearer ${token}` } });
        if (!r.ok) return;
        const offices = await r.json();
        for (const o of offices) {
          const cr = await fetch(`/api/offices/${o.id}/content`, { headers: { Authorization: `Bearer ${token}` } });
          if (cr.ok) {
            const items: ContentItem[] = await cr.json();
            const found = items.find(i => i.id === id);
            if (found) {
              setItem(found);
              setOfficeId(o.id);
              if (found.production_meta?.video_url) setVideoUrl(found.production_meta.video_url);
              break;
            }
          }
        }
      } finally { setLoading(false); }
    })();
  }, [id]);

  if (loading) return (
    <div className="flex items-center justify-center min-h-[60vh]">
      <div className="text-white/30 animate-pulse text-sm">Carregando conteúdo…</div>
    </div>
  );
  if (!item) return (
    <div className="text-center py-16">
      <p className="text-white/30 text-sm">Conteúdo não encontrado.</p>
      <button onClick={() => router.back()} className="mt-4 text-violet-400 text-sm hover:underline">← Voltar</button>
    </div>
  );

  const meta = item.production_meta;

  // Polling do modo 100% IA: atualiza o item até o vídeo ficar pronto/falhar.
  async function pollDetailUntilDone(oid: string, itemId: string) {
    const started = Date.now();
    const TIMEOUT_MS = 8 * 60 * 1000;
    while (Date.now() - started < TIMEOUT_MS) {
      await new Promise(res => setTimeout(res, 3000));
      try {
        const r = await fetch(`/api/offices/${oid}/content`, { headers: { Authorization: `Bearer ${token}` } });
        if (!r.ok) continue;
        const data: ContentItem[] = await r.json();
        const it = data.find(i => i.id === itemId);
        if (!it) continue;
        setItem(it);
        if (it.production_meta?.video_url) setVideoUrl(it.production_meta.video_url);
        if (["ready", "published", "failed", "review"].includes(it.status)) return;
      } catch { /* tenta de novo no próximo ciclo */ }
    }
  }

  async function handleGenerateVideo() {
    if (!officeId || generating) return;
    setGenerating(true);
    setGenError(null);
    try {
      if (item!.status === "review") {
        const ar = await fetch(`/api/offices/${officeId}/content/${item!.id}/approve`, {
          method: "PATCH",
          headers: { Authorization: `Bearer ${token}` },
        });
        if (!ar.ok) throw new Error("Falha ao aprovar o roteiro");
      }
      await content.processVideo(officeId, item!.id);
      setItem(prev => prev ? { ...prev, status: "rendering" } : prev);
      await pollDetailUntilDone(officeId, item!.id);
    } catch (e) {
      setGenError(e instanceof Error ? e.message : "Erro ao gerar vídeo");
    } finally {
      setGenerating(false);
    }
  }

  const canGenerate = officeId && item.status !== "rendering";

  const tabs = [
    { id: "roteiro" as const, label: meta.plano_edicao ? "✂️ Edição" : "📝 Roteiro" },
    { id: "thumbnails" as const, label: "🖼 Thumbnails" },
    { id: "seo" as const, label: "📊 SEO" },
    { id: "plano" as const, label: "📅 Plano" },
    { id: "checklist" as const, label: "✅ Checklist" },
  ];

  return (
    <div className="max-w-3xl mx-auto space-y-6">
      <div>
        <button onClick={() => router.back()} className="text-white/30 hover:text-white/60 text-sm transition-colors mb-3 block">← Voltar</button>
        <h1 className="text-xl font-black text-white leading-snug">{item.title}</h1>
        {item.duration_seconds && (
          <p className="text-white/40 text-sm mt-1">⏱ {Math.round(item.duration_seconds)}s</p>
        )}
      </div>

      {/* Video generation */}
      <div className="card-glass rounded-2xl p-5">
        <div className="flex items-center justify-between gap-4 flex-wrap">
          <div>
            <p className="text-xs font-semibold text-white/40 uppercase tracking-wider">🎬 Vídeo</p>
            <p className="text-white/30 text-xs mt-1">
              {meta.plano_edicao
                ? "Aplica os cortes do plano de edição no vídeo bruto e gera o .mp4 final."
                : "Gera narração em PT-BR do roteiro e compõe o .mp4 vertical (9:16)."}
            </p>
          </div>
          {canGenerate && (
            <button
              onClick={handleGenerateVideo}
              disabled={generating}
              className="bg-violet-600 hover:bg-violet-500 disabled:opacity-50 disabled:cursor-not-allowed text-white rounded-xl text-sm font-semibold px-4 py-2 transition-colors shrink-0"
            >
              {generating ? "⚙️ Gerando vídeo…" : videoUrl ? "🔄 Gerar novamente" : item.status === "review" ? "✅ Aprovar e gerar vídeo" : "🎬 Gerar Vídeo"}
            </button>
          )}
        </div>
        {generating && (
          <p className="text-violet-300/60 text-xs mt-3 animate-pulse">
            Processando com FFmpeg — pode levar 1-2 minutos…
          </p>
        )}
        {genError && (
          <p className="text-red-400 text-xs mt-3">❌ {genError}</p>
        )}
        {videoUrl && !generating && (
          <div className="mt-4">
            <video
              src={videoUrl}
              controls
              className="w-full max-w-xs mx-auto rounded-xl border border-white/10 bg-black"
              style={{ aspectRatio: "9/16" }}
            />
            <p className="text-center mt-2">
              <a href={videoUrl} target="_blank" rel="noopener noreferrer" className="text-violet-400 text-xs hover:underline">
                ⬇ Abrir/baixar .mp4
              </a>
            </p>
          </div>
        )}
      </div>

      {/* Title variations */}
      {meta.titulos && meta.titulos.length > 1 && (
        <div className="card-glass rounded-2xl p-5">
          <p className="text-xs font-semibold text-white/40 uppercase tracking-wider mb-3">Variações de Título</p>
          <div className="space-y-2">
            {meta.titulos.map((t, i) => (
              <div key={i} className="flex items-start gap-2">
                <span className="text-violet-400 font-bold text-xs shrink-0 mt-0.5">#{i+1}</span>
                <p className="text-white/70 text-sm">{t}</p>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Rendering progress bar */}
      {item.status === "rendering" && (
        <div className="card-glass rounded-2xl p-5 space-y-3">
          <p className="text-sm text-white/60 font-medium">
            {meta.mode === "editing_plan" ? "✂️ Editando vídeo..." : "🤖 Gerando vídeo..."}
          </p>
          <div className="space-y-1.5">
            <div className="flex justify-between text-xs text-white/40">
              <span>{meta.render_stage || "processando..."}</span>
              <span>{meta.render_progress ?? 0}%</span>
            </div>
            <div className="h-1.5 rounded-full bg-white/[0.08] overflow-hidden">
              <div
                className="h-full rounded-full bg-gradient-to-r from-violet-500 to-cyan-400 transition-all duration-700"
                style={{ width: `${meta.render_progress ?? 5}%` }}
              />
            </div>
          </div>
          <p className="text-xs text-white/30 text-center">
            {meta.mode === "editing_plan"
              ? "FFmpeg está cortando os trechos. Leva de 30s a alguns minutos."
              : "Isso leva 2–5 minutos. Pode fechar esta aba."}
          </p>
        </div>
      )}

      {/* Tabs */}
      <div className="card-glass rounded-2xl overflow-hidden">
        <div className="flex border-b border-white/[0.06] overflow-x-auto">
          {tabs.map(t => (
            <button key={t.id} onClick={() => setActiveTab(t.id)}
              className={`px-4 py-3 text-xs font-medium whitespace-nowrap transition-colors border-b-2 ${activeTab === t.id ? "border-violet-500 text-violet-300" : "border-transparent text-white/30 hover:text-white/55"}`}>
              {t.label}
            </button>
          ))}
        </div>

        <div className="p-6">
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
                    <p className="text-xs font-semibold text-yellow-400 uppercase tracking-wider mb-2">🎣 Hook</p>
                    <p className="text-white/75 text-sm leading-relaxed">{toText(meta.roteiro.hook)}</p>
                  </div>
                  <div>
                    <p className="text-xs font-semibold text-white/40 uppercase tracking-wider mb-2">🎬 Desenvolvimento</p>
                    <div className="space-y-2">
                      {meta.roteiro.desenvolvimento.map((cena, i) => (
                        <div key={i} className="flex gap-3 bg-white/[0.03] rounded-xl p-3">
                          <span className="text-violet-400 font-bold text-sm shrink-0">{i+1}</span>
                          <p className="text-white/65 text-sm leading-relaxed">{toText(cena)}</p>
                        </div>
                      ))}
                    </div>
                  </div>
                  <div className="bg-emerald-500/10 border border-emerald-500/20 rounded-xl p-4">
                    <p className="text-xs font-semibold text-emerald-400 uppercase tracking-wider mb-2">⚡ Clímax</p>
                    <p className="text-white/75 text-sm leading-relaxed">{toText(meta.roteiro.climax)}</p>
                  </div>
                  <div className="bg-violet-500/10 border border-violet-500/20 rounded-xl p-4">
                    <p className="text-xs font-semibold text-violet-400 uppercase tracking-wider mb-2">📣 CTA</p>
                    <p className="text-white/75 text-sm leading-relaxed">{toText(meta.roteiro.cta)}</p>
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
                  <div className="flex gap-2">
                    {meta.thumbnails.map((_, i) => (
                      <button key={i} onClick={() => setSelectedThumb(i)}
                        className={`px-3 py-1.5 text-xs rounded-lg font-medium transition-colors ${selectedThumb === i ? "bg-violet-600/30 text-violet-300 border border-violet-500/40" : "bg-white/[0.05] text-white/40 border border-transparent"}`}>
                        Opção {i + 1}
                      </button>
                    ))}
                  </div>
                  {(() => {
                    const th = meta.thumbnails![selectedThumb];
                    return (
                      <div className="space-y-3">
                        <div className="flex items-center gap-3 bg-white/[0.03] rounded-xl p-4">
                          <div className="flex gap-1.5">
                            {th.cores_principais.map((c, i) => (
                              <div key={i} className="w-8 h-8 rounded-lg border border-white/10" style={{ background: c }} title={c} />
                            ))}
                          </div>
                          <p className="text-white/50 text-xs">{th.cores_principais.join(" · ")}</p>
                        </div>
                        <div className="bg-white/[0.03] rounded-xl p-4">
                          <p className="text-xs text-white/40 font-semibold mb-1">Texto overlay</p>
                          <p className="text-white font-bold text-lg">{th.texto_overlay}</p>
                        </div>
                        <div className="bg-white/[0.03] rounded-xl p-4">
                          <p className="text-xs text-white/40 font-semibold mb-1">Conceito visual</p>
                          <p className="text-white/65 text-sm leading-relaxed">{th.descricao}</p>
                        </div>
                        <div className="bg-white/[0.03] rounded-xl p-4">
                          <p className="text-xs text-white/40 font-semibold mb-1">Composição</p>
                          <p className="text-white/65 text-sm leading-relaxed">{th.composicao}</p>
                        </div>
                        <div>
                          <p className="text-xs text-white/40 font-semibold mb-2">Elementos</p>
                          <div className="flex flex-wrap gap-1.5">
                            {th.elementos.map((e, i) => (
                              <span key={i} className="text-xs px-2.5 py-1 rounded-lg bg-white/[0.06] text-white/55">{e}</span>
                            ))}
                          </div>
                        </div>
                      </div>
                    );
                  })()}
                </>
              ) : <p className="text-white/25 text-sm">Thumbnails não disponíveis.</p>}
            </div>
          )}

          {/* SEO */}
          {activeTab === "seo" && meta.seo && (
            <div className="space-y-3">
              <div className="bg-white/[0.03] rounded-xl p-4">
                <p className="text-xs text-white/40 font-semibold mb-1.5">Título otimizado</p>
                <p className="text-white font-semibold text-sm">{meta.seo.titulo_otimizado}</p>
              </div>
              <div className="bg-white/[0.03] rounded-xl p-4">
                <p className="text-xs text-white/40 font-semibold mb-1.5">Descrição</p>
                <p className="text-white/65 text-sm leading-relaxed whitespace-pre-line">{meta.seo.descricao}</p>
              </div>
              <div className="grid grid-cols-2 gap-3">
                <div>
                  <p className="text-xs text-white/40 font-semibold mb-2">Tags</p>
                  <div className="flex flex-wrap gap-1.5">
                    {meta.seo.tags?.map((t, i) => (
                      <span key={i} className="text-xs px-2 py-0.5 rounded-md bg-blue-500/10 text-blue-300 border border-blue-500/20">{t}</span>
                    ))}
                  </div>
                </div>
                <div>
                  <p className="text-xs text-white/40 font-semibold mb-2">Hashtags</p>
                  <div className="flex flex-wrap gap-1.5">
                    {meta.seo.hashtags?.map((h, i) => (
                      <span key={i} className="text-xs px-2 py-0.5 rounded-md bg-violet-500/10 text-violet-300 border border-violet-500/20">{h}</span>
                    ))}
                  </div>
                </div>
              </div>
              {meta.seo.categoria && (
                <div className="bg-white/[0.03] rounded-xl p-4">
                  <p className="text-xs text-white/40 font-semibold mb-1">Categoria</p>
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
                  <p className="text-xs text-white/40 font-semibold mb-1.5">{label}</p>
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
      </div>
    </div>
  );
}
