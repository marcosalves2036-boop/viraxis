// Onboarding travado (gate de primeiro uso) — tipos, config de steps e fetcher.
//
// O progresso vem de GET /users/me/onboarding (proxy Next → backend), que
// deriva o estado real do pipeline (upload concluído, decisão do BRAIN,
// vídeo pronto) a cada consulta. Este módulo só descreve como a UI mapeia
// esse estado em telas/CTAs — nenhuma lógica de "completo" é decidida aqui.

export interface OnboardingStatus {
  has_uploaded_video: boolean;
  has_brain_decision: boolean;
  has_ready_content: boolean;
  completed: boolean;
  completed_at: string | null;
  current_step: number; // 1..4 — 4 significa concluído
  total_steps: number;
}

export interface OnboardingStepConfig {
  step: 1 | 2 | 3;
  title: string;
  description: string;
  icon: string;
  ctaLabel: string;
  ctaHref: string;
  /** Prefixos de rota liberados enquanto este é o step corrente. */
  allowedPathPrefixes: string[];
}

export const ONBOARDING_STEPS: OnboardingStepConfig[] = [
  {
    step: 1,
    title: "Faça o primeiro upload",
    description:
      "Envie um vídeo bruto para a Biblioteca. Se ainda não tem um Escritório, crie um primeiro — é rápido.",
    icon: "🎬",
    ctaLabel: "Ir para a Biblioteca",
    ctaHref: "/dashboard/biblioteca",
    allowedPathPrefixes: ["/dashboard/biblioteca", "/dashboard/escritorios"],
  },
  {
    step: 2,
    title: "Aguarde a decisão do BRAIN",
    description:
      "O agente BRAIN analisa o vídeo enviado e decide o próximo conteúdo a produzir. Execute o BRAIN no seu Escritório.",
    icon: "🧠",
    ctaLabel: "Ir para o Escritório",
    ctaHref: "/dashboard/escritorios",
    allowedPathPrefixes: ["/dashboard/escritorios", "/dashboard/biblioteca"],
  },
  {
    step: 3,
    title: "Veja seu primeiro vídeo pronto",
    description:
      "Aprove a decisão do BRAIN para o RENDERER escrever o roteiro e o pipeline cortar o vídeo. Revise e aprove o resultado em Conteúdo.",
    icon: "✅",
    ctaLabel: "Ir para Conteúdo",
    ctaHref: "/dashboard/conteudo",
    allowedPathPrefixes: ["/dashboard/conteudo", "/dashboard/escritorios"],
  },
];

export function getStepConfig(step: number): OnboardingStepConfig | null {
  return ONBOARDING_STEPS.find((s) => s.step === step) ?? null;
}

/** Verdadeiro se a rota atual é uma das liberadas para o step corrente do onboarding. */
export function isPathAllowedForStep(pathname: string, step: number): boolean {
  const config = getStepConfig(step);
  if (!config) return false;
  return config.allowedPathPrefixes.some(
    (prefix) => pathname === prefix || pathname.startsWith(`${prefix}/`)
  );
}

export async function fetchOnboardingStatus(token: string): Promise<OnboardingStatus> {
  const res = await fetch("/api/users/me/onboarding", {
    headers: { Authorization: `Bearer ${token}` },
  });
  if (!res.ok) {
    let detail = `Erro ${res.status} ao consultar o onboarding.`;
    try {
      const body = await res.json();
      if (body?.detail) detail = String(body.detail);
    } catch {
      // resposta não-JSON — mantém a mensagem genérica
    }
    throw new Error(detail);
  }
  return res.json();
}
