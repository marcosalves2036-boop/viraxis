"use client";

import RetryAnalysisButton, { errorTypeLabel } from "@/components/biblioteca/RetryAnalysisButton";
import {
  RawVideo,
  STATUS_LABEL,
  STATUS_CLASS,
  highlightsCount,
  analysisErrorMessage,
  fmtDuration,
} from "@/components/biblioteca/types";

/**
 * Card de vídeo no grid da Biblioteca — extraído de `dashboard/biblioteca/page.tsx`
 * (item P2 do BACKLOG, `fonte: arthur`). Comportamento 100% preservado:
 *
 *  - Thumbnail 16:9 (gerada via canvas pelo pai, passada como prop) com
 *    fallback 🎬 quando ainda não existe.
 *  - Overlays automáticos de status (pending = enviando, processing =
 *    analisando) — nunca exige clique manual em "Analisar".
 *  - Badge de erro (❌) com o motivo (error_type) via `title` no hover.
 *  - Chips de status/duração/destaques detectados.
 *  - `RetryAnalysisButton` inline (variant="card") quando `status=failed`,
 *    permitindo tentar de novo sem abrir o modal de detalhe.
 *
 * Continua sendo um `<div role="button">`, não um `<button>` real — o card
 * precisa hospedar o `RetryAnalysisButton` (que é um `<button>`), e
 * `<button>` dentro de `<button>` é HTML inválido. role/tabIndex/onKeyDown
 * preservam a acessibilidade (Enter/Espaço abrem o modal).
 */

interface VideoCardProps {
  video: RawVideo;
  /** Thumbnail já gerada (data URL) pelo componente pai, se disponível. */
  thumbnail?: string;
  onSelect: (video: RawVideo) => void;
  onReanalyzeSuccess: (videoId: string, patch: { status: string; error_type: string | null }) => void;
}

export default function VideoCard({ video, thumbnail, onSelect, onReanalyzeSuccess }: VideoCardProps) {
  return (
    <div
      role="button"
      tabIndex={0}
      onClick={() => onSelect(video)}
      onKeyDown={e => {
        if (e.key === "Enter" || e.key === " ") {
          e.preventDefault();
          onSelect(video);
        }
      }}
      className="card-glass rounded-2xl overflow-hidden text-left group hover:border-violet-500/30 border border-white/[0.06] transition-all cursor-pointer"
    >
      {/* Thumbnail 16:9 */}
      <div className="relative aspect-video bg-black flex items-center justify-center">
        {thumbnail ? (
          // eslint-disable-next-line @next/next/no-img-element
          <img src={thumbnail} alt={video.title || video.original_filename} className="w-full h-full object-cover" />
        ) : (
          <span className="text-3xl opacity-30">🎬</span>
        )}
        {/* Overlays de status — badge/spinner automático, sem botão manual */}
        {video.status === "pending" && (
          <div className="absolute inset-0 bg-black/55 flex flex-col items-center justify-center gap-1.5">
            <span className="animate-pulse text-lg">📤</span>
            <span className="text-white/70 text-[11px] font-semibold">Enviando...</span>
          </div>
        )}
        {video.status === "processing" && (
          <div className="absolute inset-0 bg-black/55 flex flex-col items-center justify-center gap-1.5">
            <span className="animate-spin text-lg">⚙️</span>
            <span className="text-violet-300 text-[11px] font-semibold">Analisando...</span>
          </div>
        )}
        {video.status === "ready" && (
          <span className="absolute top-1.5 right-1.5 text-xs bg-black/60 rounded-full px-1.5 py-0.5">✅</span>
        )}
        {video.status === "failed" && (
          <span
            className="absolute top-1.5 right-1.5 text-xs bg-black/60 rounded-full px-1.5 py-0.5"
            title={analysisErrorMessage(video) || errorTypeLabel(video.error_type)}
          >
            ❌
          </span>
        )}
        {/* Duração */}
        <span className="absolute bottom-1.5 left-1.5 text-[11px] font-semibold text-white bg-black/70 rounded px-1.5 py-0.5">
          ▶ {fmtDuration(video.duration_seconds)}
        </span>
      </div>
      {/* Título */}
      <div className="p-2.5">
        <p className="text-white/80 text-xs font-medium truncate group-hover:text-white transition-colors">
          {video.title || video.original_filename}
        </p>
        {/* Chips: status, duração e destaques detectados */}
        <div className="flex flex-wrap items-center gap-1 mt-1.5">
          <span className={`inline-block text-[10px] font-semibold px-1.5 py-0.5 rounded-full border ${STATUS_CLASS[video.status] || STATUS_CLASS.pending}`}>
            {STATUS_LABEL[video.status] || video.status}
          </span>
          <span className="inline-flex items-center gap-0.5 text-[10px] text-white/40 bg-white/[0.05] rounded-full px-1.5 py-0.5">
            ⏱ {fmtDuration(video.duration_seconds)}
          </span>
          {video.status === "ready" && (
            <span className="inline-flex items-center gap-0.5 text-[10px] text-violet-300/80 bg-violet-500/[0.08] rounded-full px-1.5 py-0.5">
              ✨ {highlightsCount(video)} {highlightsCount(video) === 1 ? "destaque" : "destaques"}
            </span>
          )}
        </div>
        <p className="text-white/25 text-[10px] mt-1">
          {new Date(video.created_at).toLocaleDateString("pt-BR")}
        </p>
        {/* Retry inline no card — evita ter que abrir o modal só para
            tentar de novo. stopPropagation dentro do componente
            impede que o clique também abra o modal de detalhe. */}
        {video.status === "failed" && (
          <div className="mt-2">
            <RetryAnalysisButton
              videoId={video.id}
              errorType={video.error_type as "download_failed" | "timeout" | "analysis_failed" | null}
              variant="card"
              showReason={false}
              onSuccess={patch => onReanalyzeSuccess(video.id, patch)}
            />
          </div>
        )}
      </div>
    </div>
  );
}
