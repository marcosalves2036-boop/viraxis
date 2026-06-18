"""Definição do agente BRAIN — estrategista de conteúdo viral."""

import os

from crewai import Agent, LLM

from viraxis.config import settings

# Temperature padrão do BRAIN; pode ser sobrescrita via NicheProfile.brain_params
_DEFAULT_BRAIN_TEMPERATURE = 0.7


def create_llm(temperature: float = _DEFAULT_BRAIN_TEMPERATURE) -> LLM:
    """
    Instancia o LLM via CrewAI/LiteLLM.
    Provider detectado automaticamente pelo prefixo de llm_model.
    Troque provider alterando LLM_MODEL e LLM_API_KEY no .env — sem tocar no código.

    IMPORTANTE: CrewAI exige OPENAI_API_KEY no ambiente (mesmo quando não usa OpenAI).
    Definimos um valor dummy se não estiver presente para contornar a validação.
    """
    # CrewAI valida OPENAI_API_KEY no import — garantir valor antes de qualquer instância
    if not os.environ.get("OPENAI_API_KEY"):
        os.environ["OPENAI_API_KEY"] = "fake-not-used-crewai-bypass"

    model = settings.llm_model
    # llm_api_key tem prioridade; fallback para google_api_key (legado)
    api_key = settings.llm_api_key or settings.google_api_key

    if model.startswith("gemini/"):
        os.environ["GEMINI_API_KEY"] = api_key
        os.environ["GOOGLE_API_KEY"] = api_key
    elif model.startswith("groq/"):
        os.environ["GROQ_API_KEY"] = api_key
    elif model.startswith("gpt") or model.startswith("openai/"):
        os.environ["OPENAI_API_KEY"] = api_key
    elif model.startswith("anthropic/") or model.startswith("claude"):
        os.environ["ANTHROPIC_API_KEY"] = api_key
    # else: LiteLLM resolve pelo modelo; OPENAI_API_KEY=fake já está setado

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
            "Você opera com a disciplina de um analista quantitativo e a criatividade de um "
            "produtor de conteúdo de elite. Cada decisão sua vira um ContentDecision no banco — "
            "um registro auditável que o usuário pode revisar, aprovar ou rejeitar."
        ),
        llm=llm,
        verbose=False,
        allow_delegation=False,
    )
