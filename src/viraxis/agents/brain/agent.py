"""Definição do agente BRAIN — estrategista de conteúdo viral."""

import os

from crewai import Agent, LLM

from viraxis.config import settings

# Temperature padrão do BRAIN; pode ser sobrescrita via NicheProfile.brain_params
_DEFAULT_BRAIN_TEMPERATURE = 0.7


def create_llm(temperature: float = _DEFAULT_BRAIN_TEMPERATURE) -> LLM:
    """
    Instancia o LLM via CrewAI.
    Provider detectado automaticamente pelo prefixo de llm_model.
    Troque provider alterando LLM_MODEL e LLM_API_KEY no .env — sem tocar no codigo.
    """
    model = settings.llm_model
    # llm_api_key tem prioridade; fallback para google_api_key (legado)
    api_key = settings.llm_api_key or settings.google_api_key

    if model.startswith("gemini/"):
        # CrewAI native Gemini usa GEMINI_API_KEY; LiteLLM usa GOOGLE_API_KEY
        os.environ["GEMINI_API_KEY"] = api_key
        os.environ["GOOGLE_API_KEY"] = api_key
    elif model.startswith("groq/"):
        os.environ["GROQ_API_KEY"] = api_key
    elif model.startswith("gpt") or model.startswith("openai/"):
        os.environ["OPENAI_API_KEY"] = api_key
    elif model.startswith("anthropic/") or model.startswith("claude"):
        os.environ["ANTHROPIC_API_KEY"] = api_key
    else:
        # Fallback: LiteLLM vai tentar resolver pelo modelo
        os.environ["OPENAI_API_KEY"] = api_key

    return LLM(
        model=model,
        temperature=temperature,
        max_tokens=4096,
    )


def create_brain_agent(
    llm: LLM | None = None,
    temperature: float = _DEFAULT_BRAIN_TEMPERATURE,
) -> Agent:
    """
    Cria o agente BRAIN — analista de tendências e estrategista de conteúdo viral.

    O BRAIN é o diferencial intelectual do produto: ele não só escolhe temas,
    ele documenta *por que* escolheu e qual hipótese está testando.

    Args:
        llm: LLM pré-configurado (opcional; cria um Gemini padrão se None).
        temperature: Criatividade do agente. Pode ser extraída de NicheProfile.brain_params.
    """
    if llm is None:
        llm = create_llm(temperature=temperature)

    return Agent(
        role="Estrategista de Conteúdo Viral",
        goal=(
            "Analisar o perfil de nicho fornecido e tomar UMA decisão de conteúdo "
            "precisa e bem fundamentada. A decisão deve maximizar a probabilidade de "
            "viralização com base nos archetypes e plataformas de melhor desempenho. "
            "Toda decisão precisa de hipótese clara e chain-of-thought documentado."
        ),
        backstory=(
            "Você é o BRAIN — o núcleo estratégico dos Escritórios Virais Autônomos da VIRAXIS. "
            "Sua função é processar dados de nicho (archetypes de maior performance histórica, "
            "keywords em alta, estilo editorial validado) e transformá-los em decisões de conteúdo "
            "acionáveis e auditáveis.\n\n"
            "Você opera com a disciplina de um analista de dados e a criatividade de um diretor "
            "de conteúdo. Cada decisão sua é um experimento documentado: você formula uma hipótese, "
            "justifica com evidências do nicho e define um nível de confiança honesto.\n\n"
            "Você NUNCA decide por instinto — sempre por dados. Se os dados são insuficientes, "
            "você aponta isso explicitamente e reduz o confidence_score."
        ),
        llm=llm,
        verbose=True,
        allow_delegation=False,  # o BRAIN é autônomo, não delega
        max_iter=3,              # máximo de iterações de auto-reflexão interna
    )
