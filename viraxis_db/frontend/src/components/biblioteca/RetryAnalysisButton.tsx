"use client";

import { useEffect, useRef, useState } from "react";

/**
 * Botão "Tentar novamente" para RawVideo com status=failed.
 *
 * Reaproveita o endpoint `POST /raw-videos/{id}/reanalyze` (DAVI) via proxy
 * Next.js `/api/raw-videos/[id]/reanalyze` — re-dispara a análise de IA sem
 * exigir novo upload, usando o arquivo já presente no Supabase Storage.
 *
 * Estados cobertos:
 *  - idle:     botão pronto, mostra o motivo do erro anterior (error_type)
 *  - loading:  chamada em andamento — botão desabilitado + spinner
 *  - cooldown: 429 (rate limit 10/min) — contagem regressiva via Retry-After,
 *              botão reabilita sozinho quando o cooldown zera
 *  - error:    falha na própria chamada de retry (404/422/502/503/rede) —
 *              mensagem inline, botão permanece clicável para nova tentativa
 *
 * Ao ter sucesso, chama `onSuccess` com o novo status/error_type do vídeo
 * para que o componente pai atualize a UI imediatamente (status: processing)
 * sem esperar o próximo ciclo do polling já existente na Biblioteca.
 */

export type RawVideoErrorType = "download_failed" | "timeout" | "analysis_failed" | null;

interface ReanalyzeSuccessPatch {
  status: string;
  error_type: string | null;
}

interface RetryAnalysisButtonProps {
  videoId: string;
  errorType: RawVideoErrorType;
  onSuccess: (patch: ReanalyzeSuccessPatch) => void;
  /** "card" = botão compacto para overlay do grid; "modal" = botão full-width */
  variant?: "card" | "modal";
  /** Mostra o motivo do erro anterior (error_type) acima/ao lado do botão */
  showReason?: boolean;
  className?: string;
}

type Phase = "idle" | "loading" | "cooldown" | "error";

interface ReanalyzeErrorBody {
  detail?: string;
  type?: string;
  retry_after_seconds?: number;
}

const ERROR_TYPE_LABELS: Record<string, string> = {
  download_failed: "Falha ao baixar o vídeo do armazenamento",
  timeout: "Tempo esgotado durante a análise",
  analysis_failed: "Falha na análise de IA",
};

export function errorTypeLabel(errorType: string | null | undefined): string {
  if (!errorType) return "Erro na análise";
  return ERROR_TYPE_LABELS[errorType] ?? "Erro na análise";
}

function statusFallbackMessage(status: number): string {
  switch (status) {
    case 404:
      return "Vídeo não encontrado — pode ter sido excluído.";
    case 422:
      return "Este vídeo não está mais elegível para nova tentativa.";
    case 502:
      return "Erro ao acessar o armazenamento. Tente novamente em instantes.";
    case 503:
      return "Armazenamento indisponível no momento. Tente novamente em instantes.";
    default:
      return "Não foi possível tentar novamente agora.";
  }
}

export default function RetryAnalysisButton({
  videoId,
  errorType,
  onSuccess,
  variant = "card",
  showReason = true,
  className = "",
}: RetryAnalysisButtonProps) {
  const [phase, setPhase] = useState<Phase>("idle");
  const [errorMessage, setErrorMessage] = useState<string | null>(null);
  const [cooldownSeconds, setCooldownSeconds] = useState(0);
  const intervalRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const mountedRef = useRef(true);

  useEffect(() => {
    mountedRef.current = true;
    return () => {
      mountedRef.current = false;
      if (intervalRef.current) clearInterval(intervalRef.current);
    };
  }, []);

  // Contagem regressiva do cooldown de rate limit — reabilita o botão sozinho
  // quando chega a zero, sem exigir ação do usuário.
  useEffect(() => {
    if (phase !== "cooldown") return;
    if (cooldownSeconds <= 0) {
      setPhase("idle");
      return;
    }
    intervalRef.current = setInterval(() => {
      setCooldownSeconds(prev => {
        if (prev <= 1) {
          if (intervalRef.current) clearInterval(intervalRef.current);
          return 0;
        }
        return prev - 1;
      });
    }, 1000);
    return () => {
      if (intervalRef.current) clearInterval(intervalRef.current);
    };
  }, [phase, cooldownSeconds]);

  function startCooldown(seconds: number) {
    setCooldownSeconds(Math.max(1, seconds));
    setErrorMessage(null);
    setPhase("cooldown");
  }

  async function handleRetry(e: React.MouseEvent<HTMLButtonElement>) {
    // O botão pode estar aninhado dentro de um card clicável (abre o modal) —
    // impede que o clique de retry também dispare a abertura do modal.
    e.preventDefault();
    e.stopPropagation();

    if (phase === "loading" || phase === "cooldown") return;

    const token = typeof window !== "undefined" ? localStorage.getItem("viraxis_token") : null;
    if (!token) {
      setErrorMessage("Sessão expirada — recarregue a página e faça login novamente.");
      setPhase("error");
      return;
    }

    setPhase("loading");
    setErrorMessage(null);

    try {
      const res = await fetch(`/api/raw-videos/${videoId}/reanalyze`, {
        method: "POST",
        headers: { Authorization: `Bearer ${token}`, "Content-Type": "application/json" },
      });

      if (res.status === 429) {
        const body: ReanalyzeErrorBody = await res.json().catch(() => ({}));
        const headerRetryAfter = Number(res.headers.get("Retry-After"));
        const seconds = body.retry_after_seconds
          ?? (Number.isFinite(headerRetryAfter) && headerRetryAfter > 0 ? headerRetryAfter : 60);
        if (!mountedRef.current) return;
        startCooldown(seconds);
        return;
      }

      if (!res.ok) {
        const body: ReanalyzeErrorBody = await res.json().catch(() => ({}));
        if (!mountedRef.current) return;
        setErrorMessage(body.detail || statusFallbackMessage(res.status));
        setPhase("error");
        return;
      }

      const data = await res.json();
      if (!mountedRef.current) return;
      setPhase("idle");
      onSuccess({
        status: typeof data.status === "string" ? data.status : "processing",
        error_type: typeof data.error_type === "string" ? data.error_type : null,
      });
    } catch {
      if (!mountedRef.current) return;
      setErrorMessage("Erro de rede — verifique sua conexão e tente novamente.");
      setPhase("error");
    }
  }

  const isCompact = variant === "card";
  const disabled = phase === "loading" || phase === "cooldown";

  const buttonLabel =
    phase === "loading" ? "Reenviando..." :
    phase === "cooldown" ? `Aguarde ${cooldownSeconds}s` :
    "Tentar novamente";

  const baseButtonClass = isCompact
    ? "inline-flex items-center justify-center gap-1.5 px-2.5 py-1.5 rounded-lg text-[11px] font-semibold transition-colors"
    : "w-full inline-flex items-center justify-center gap-2 px-4 py-2.5 rounded-xl text-sm font-semibold transition-colors";

  const stateButtonClass = disabled
    ? "bg-white/[0.06] text-white/30 cursor-not-allowed border border-white/10"
    : "bg-amber-500/15 hover:bg-amber-500/25 text-amber-300 border border-amber-500/30";

  return (
    <div className={`space-y-1.5 ${className}`} onClick={e => e.stopPropagation()}>
      {showReason && (
        <p className={isCompact ? "text-[10px] text-white/40 leading-snug" : "text-xs text-white/40 leading-snug"}>
          {errorTypeLabel(errorType)}
        </p>
      )}

      <button
        type="button"
        onClick={handleRetry}
        disabled={disabled}
        aria-busy={phase === "loading"}
        className={`${baseButtonClass} ${stateButtonClass}`}
      >
        {phase === "loading" && (
          <span className="animate-spin inline-block h-3 w-3 rounded-full border-2 border-amber-300/30 border-t-amber-300" />
        )}
        {phase !== "loading" && <span aria-hidden="true">↻</span>}
        {buttonLabel}
      </button>

      {phase === "error" && errorMessage && (
        <p className={isCompact ? "text-[10px] text-red-400 leading-snug" : "text-xs text-red-400 leading-relaxed"}>
          {errorMessage}
        </p>
      )}
      {phase === "cooldown" && (
        <p className={isCompact ? "text-[10px] text-white/30 leading-snug" : "text-xs text-white/30 leading-relaxed"}>
          Limite de tentativas atingido. Nova tentativa liberada em {cooldownSeconds}s.
        </p>
      )}
    </div>
  );
}
