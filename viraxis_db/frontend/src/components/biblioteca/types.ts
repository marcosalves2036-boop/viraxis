// Tipos e helpers compartilhados entre a página da Biblioteca (`page.tsx`,
// incluindo o VideoModal de detalhe) e os componentes extraídos
// (`VideoCard`, `EmptyState`). Ponto único para não duplicar a shape de
// `RawVideo`/`AiAnalysis` nem os mapas de status entre os consumidores.

export interface AiAnalysis {
  overall_summary?: string;
  detected_topics?: string[];
  predominant_tone?: string;
  transcription_text?: string;
  scenes?: Array<{ start: number; end: number; description: string }>;
  editorial_highlights?: Array<{ start: number; end: number; reason: string }>;
  status?: string;
  error?: string;
}

export interface RawVideo {
  id: string;
  office_id: string;
  title: string | null;
  original_filename: string;
  status: string;
  duration_seconds: number | null;
  tags: string[];
  description: string | null;
  r2_url: string | null;
  ai_analysis: AiAnalysis | null;
  // download_failed | timeout | analysis_failed | null — diferencia o motivo
  // da falha de análise para a mensagem exibida ao usuário (RetryAnalysisButton).
  error_type: string | null;
  created_at: string;
}

// Indicador automático de progresso — o usuário nunca precisa clicar em
// "Analisar" manualmente: pending (enviando/aguardando) → processing
// (analisando com IA) → ready (analisado) ou failed (erro na análise).
export const STATUS_LABEL: Record<string, string> = {
  pending: "Enviando...",
  ready: "Analisado",
  processing: "Analisando...",
  failed: "Erro na análise",
};

export const STATUS_CLASS: Record<string, string> = {
  pending: "bg-white/10 text-white/50 border-white/10",
  ready: "bg-green-500/10 text-green-400 border-green-500/20",
  processing: "bg-violet-500/10 text-violet-400 border-violet-500/20",
  failed: "bg-red-500/10 text-red-400 border-red-500/20",
};

export function highlightsCount(v: RawVideo): number {
  return v.ai_analysis?.editorial_highlights?.length ?? 0;
}

export function analysisErrorMessage(v: RawVideo): string | null {
  return v.ai_analysis?.error ?? null;
}

export function fmtDuration(s: number | null) {
  if (!s) return "—";
  return `${Math.floor(s / 60)}:${String(Math.floor(s % 60)).padStart(2, "0")}`;
}
