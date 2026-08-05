"use client";

import Link from "next/link";
import { useCallback, useEffect, useRef, useState } from "react";
import {
  fetchOnboardingStatus,
  getStepConfig,
  isPathAllowedForStep,
  ONBOARDING_STEPS,
  type OnboardingStatus,
} from "@/lib/onboarding";

const POLL_INTERVAL_MS = 6000;

interface UseOnboardingStatusResult {
  status: OnboardingStatus | null;
  loading: boolean;
  error: string | null;
  refetch: () => void;
}

/**
 * Busca e mantém o progresso do onboarding atualizado.
 *
 * Faz polling enquanto o onboarding não estiver completo — o progresso é
 * derivado no backend de eventos assíncronos (análise de IA em background,
 * BRAIN, RENDERER + FFmpeg), então a UI precisa refletir mudanças sem exigir
 * um F5 manual do usuário. Para de sondar assim que `completed=true`, já que
 * o backend trava essa conclusão permanentemente.
 */
function useOnboardingStatus(token: string | null): UseOnboardingStatusResult {
  const [status, setStatus] = useState<OnboardingStatus | null>(null);
  const [loading, setLoading] = useState<boolean>(true);
  const [error, setError] = useState<string | null>(null);
  const mountedRef = useRef(true);
  const intervalRef = useRef<ReturnType<typeof setInterval> | null>(null);

  const load = useCallback(async () => {
    if (!token) {
      setLoading(false);
      return;
    }
    try {
      const data = await fetchOnboardingStatus(token);
      if (!mountedRef.current) return;
      setStatus(data);
      setError(null);
    } catch (e) {
      if (!mountedRef.current) return;
      setError(e instanceof Error ? e.message : "Erro desconhecido ao consultar onboarding.");
    } finally {
      if (mountedRef.current) setLoading(false);
    }
  }, [token]);

  useEffect(() => {
    mountedRef.current = true;
    load();
    return () => {
      mountedRef.current = false;
      if (intervalRef.current) clearInterval(intervalRef.current);
    };
  }, [load]);

  useEffect(() => {
    if (intervalRef.current) {
      clearInterval(intervalRef.current);
      intervalRef.current = null;
    }
    if (!status || status.completed) return;
    intervalRef.current = setInterval(load, POLL_INTERVAL_MS);
    return () => {
      if (intervalRef.current) clearInterval(intervalRef.current);
    };
  }, [status, load]);

  return { status, loading, error, refetch: load };
}

function StepTracker({ status }: { status: OnboardingStatus }) {
  const doneMap = [status.has_uploaded_video, status.has_brain_decision, status.has_ready_content];
  return (
    <div className="flex items-center gap-2 w-full max-w-md mx-auto">
      {ONBOARDING_STEPS.map((s, i) => {
        const done = doneMap[i];
        const current = status.current_step === s.step;
        return (
          <div key={s.step} className="flex items-center flex-1 last:flex-none">
            <div
              className={`w-9 h-9 rounded-full border flex items-center justify-center text-sm font-bold shrink-0 transition-all
                ${
                  done
                    ? "bg-emerald-500 border-emerald-500 text-white"
                    : current
                    ? "border-violet-400 text-violet-300 bg-violet-500/10 animate-pulse"
                    : "border-white/15 text-white/25"
                }`}
              aria-current={current ? "step" : undefined}
            >
              {done ? "✓" : s.step}
            </div>
            {i < ONBOARDING_STEPS.length - 1 && (
              <div
                className={`h-0.5 flex-1 mx-1 rounded transition-all ${
                  doneMap[i] ? "bg-emerald-500" : "bg-white/10"
                }`}
              />
            )}
          </div>
        );
      })}
    </div>
  );
}

/** Banner fino exibido no topo das páginas liberadas durante o onboarding — mantém o usuário orientado sem bloquear a ação que ele veio fazer. */
export function OnboardingProgressBanner({ status }: { status: OnboardingStatus }) {
  const config = getStepConfig(status.current_step);
  if (!config) return null;
  return (
    <div className="mb-6 card-glass rounded-2xl p-4 border-violet-500/20">
      <div className="flex items-center justify-between gap-4 flex-wrap">
        <div className="flex items-center gap-3">
          <span className="text-xl">{config.icon}</span>
          <div>
            <p className="text-xs text-white/40 uppercase tracking-widest">
              Onboarding · Passo {status.current_step} de {status.total_steps}
            </p>
            <p className="text-sm font-semibold text-white">{config.title}</p>
          </div>
        </div>
        <div className="w-40">
          <StepTracker status={status} />
        </div>
      </div>
    </div>
  );
}

function GateLoading() {
  return (
    <div className="min-h-[70vh] flex items-center justify-center">
      <div className="flex flex-col items-center gap-3">
        <div className="w-10 h-10 rounded-full border-2 border-violet-500/30 border-t-violet-400 animate-spin" />
        <p className="text-white/40 text-sm">Carregando seu progresso de onboarding...</p>
      </div>
    </div>
  );
}

function GateError({ message, onRetry }: { message: string; onRetry: () => void }) {
  return (
    <div className="min-h-[70vh] flex items-center justify-center px-6">
      <div className="card-glass rounded-2xl p-8 max-w-md text-center space-y-4">
        <div className="text-3xl">⚠️</div>
        <h2 className="text-lg font-bold text-white">Não foi possível carregar seu onboarding</h2>
        <p className="text-white/50 text-sm">{message}</p>
        <button
          onClick={onRetry}
          className="px-5 py-2.5 bg-violet-600 hover:bg-violet-500 text-white text-sm font-semibold rounded-xl transition-colors"
        >
          Tentar novamente
        </button>
      </div>
    </div>
  );
}

/** Tela de bloqueio em tela cheia — substitui o conteúdo do dashboard enquanto o onboarding não está completo e a rota atual não é uma das liberadas para o step corrente. Sem botão "pular". */
function GateScreen({ status }: { status: OnboardingStatus }) {
  const doneMap = [status.has_uploaded_video, status.has_brain_decision, status.has_ready_content];
  return (
    <div className="min-h-[75vh] flex items-center justify-center px-4">
      <div className="w-full max-w-2xl space-y-8">
        <div className="text-center space-y-2">
          <p className="text-xs font-semibold text-violet-400 uppercase tracking-widest">
            Configuração inicial obrigatória
          </p>
          <h1 className="text-2xl md:text-3xl font-black text-white">
            Vamos até seu <span className="gradient-text">primeiro vídeo pronto</span>
          </h1>
          <p className="text-white/40 text-sm max-w-md mx-auto">
            Complete os 3 passos abaixo para liberar o restante do painel. Isso garante que você
            veja a VIRAXIS decidindo e produzindo conteúdo de verdade antes de configurar o resto.
          </p>
        </div>

        <StepTracker status={status} />

        <div className="space-y-3">
          {ONBOARDING_STEPS.map((s, i) => {
            const done = doneMap[i];
            const current = status.current_step === s.step;
            const locked = !done && !current;
            return (
              <div
                key={s.step}
                className={`card-glass rounded-2xl p-5 flex items-start gap-4 transition-all
                  ${current ? "border-violet-500/40" : ""} ${locked ? "opacity-45" : ""}`}
              >
                <div className="text-2xl shrink-0">{done ? "✅" : s.icon}</div>
                <div className="flex-1 min-w-0">
                  <p className="font-semibold text-white text-sm">
                    Passo {s.step} — {s.title}
                  </p>
                  <p className="text-white/40 text-xs mt-1">{s.description}</p>
                </div>
                {current && (
                  <Link
                    href={s.ctaHref}
                    className="shrink-0 px-4 py-2 bg-violet-600 hover:bg-violet-500 text-white text-xs font-semibold rounded-xl transition-colors whitespace-nowrap"
                  >
                    {s.ctaLabel} →
                  </Link>
                )}
                {done && (
                  <span className="shrink-0 text-[10px] font-bold px-2 py-1 rounded-full bg-emerald-500/15 text-emerald-400 border border-emerald-500/30">
                    Concluído
                  </span>
                )}
              </div>
            );
          })}
        </div>

        <p className="text-center text-white/25 text-xs">
          Este passo a passo não pode ser pulado — assim que o pipeline confirmar o vídeo pronto,
          seu painel completo é liberado automaticamente.
        </p>
      </div>
    </div>
  );
}

interface OnboardingGateViewProps {
  token: string | null;
  pathname: string;
  status: OnboardingStatus | null;
  loading: boolean;
  error: string | null;
  onRetry: () => void;
  /** Bypassa o gate — usado para contas admin internas (não fazem parte do funil B2C de chargeback). */
  bypass?: boolean;
  children: React.ReactNode;
}

/**
 * Versão "pura" do gate — recebe o estado já resolvido (útil quando o layout
 * pai precisa do mesmo `status` para outra finalidade, como desabilitar links
 * da sidebar, e não queremos dois pollings independentes rodando).
 *
 * Regras:
 * - Sem token: não decide nada, deixa o layout pai lidar com redirect de login.
 * - Bypass (admin): renderiza os filhos direto, sem gate.
 * - Loading: spinner full-screen.
 * - Erro ao consultar backend: tela de erro com "tentar novamente" — nunca libera o dashboard.
 * - Completo: renderiza os filhos normalmente (nenhum overhead visual).
 * - Incompleto: se a rota atual está liberada para o step corrente, renderiza os
 *   filhos com um banner de progresso; senão, substitui os filhos pela tela de bloqueio.
 */
export function OnboardingGateView({
  token,
  pathname,
  status,
  loading,
  error,
  onRetry,
  bypass,
  children,
}: OnboardingGateViewProps) {
  if (!token || bypass) return <>{children}</>;
  if (loading) return <GateLoading />;
  if (error) return <GateError message={error} onRetry={onRetry} />;
  if (!status) return <GateLoading />;
  if (status.completed) return <>{children}</>;

  const allowed = isPathAllowedForStep(pathname, status.current_step);
  if (allowed) {
    return (
      <>
        <OnboardingProgressBanner status={status} />
        {children}
      </>
    );
  }
  return <GateScreen status={status} />;
}

interface OnboardingGateProps {
  token: string | null;
  pathname: string;
  bypass?: boolean;
  children: React.ReactNode;
}

/** Wrapper autossuficiente (busca e sonda o status internamente) para uso fora do dashboard layout. */
export function OnboardingGate({ token, pathname, bypass, children }: OnboardingGateProps) {
  const { status, loading, error, refetch } = useOnboardingStatus(token);
  return (
    <OnboardingGateView
      token={token}
      pathname={pathname}
      status={status}
      loading={loading}
      error={error}
      onRetry={refetch}
      bypass={bypass}
    >
      {children}
    </OnboardingGateView>
  );
}

export { useOnboardingStatus };
