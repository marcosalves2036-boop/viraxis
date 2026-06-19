"""Schemas Pydantic de entrada e saída do agente BRAIN."""

from typing import Literal

from pydantic import BaseModel, Field

from viraxis.domain.models.niche_profile import NicheProfile


# ------------------------------------------------------------------ #
# Input — contexto do nicho que o BRAIN recebe                       #
# ------------------------------------------------------------------ #

class BrainDecisionInput(BaseModel):
    """Contexto serializado do NicheProfile para o agente processar."""

    niche_name: str
    target_platforms: list[str]
    viral_archetypes: dict
    content_style: dict
    top_keywords: list[str]
    brain_params: dict
    raw_notes: str | None = None

    @classmethod
    def from_niche_profile(cls, profile: NicheProfile) -> "BrainDecisionInput":
        """Constrói o input a partir de um NicheProfile ORM."""
        return cls(
            niche_name=profile.niche_name,
            target_platforms=profile.target_platforms or [],
            viral_archetypes=profile.viral_archetypes or {},
            content_style=profile.content_style or {},
            top_keywords=profile.top_keywords or [],
            brain_params=profile.brain_params or {},
            raw_notes=profile.raw_notes,
        )

    def to_context_string(self) -> str:
        """Formata o contexto como texto estruturado para o prompt do agente."""
        archetypes_str = (
            ", ".join(
                f"{k} ({v:.0%})" for k, v in self.viral_archetypes.items()
            )
            if self.viral_archetypes
            else "nenhum mapeado ainda"
        )
        keywords_str = (
            ", ".join(self.top_keywords[:15]) if self.top_keywords else "nenhuma mapeada"
        )
        platforms_str = (
            ", ".join(self.target_platforms) if self.target_platforms else "não definidas"
        )
        style_str = (
            str(self.content_style) if self.content_style else "não definido"
        )
        notes_str = self.raw_notes or "nenhuma nota adicional"

        return f"""
NICHO: {self.niche_name}

PLATAFORMAS ALVO: {platforms_str}

ARCHETYPES VIRAIS COM PESOS HISTÓRICOS:
{archetypes_str}

KEYWORDS DE ALTA PERFORMANCE:
{keywords_str}

ESTILO EDITORIAL:
{style_str}

NOTAS DO OPERADOR:
{notes_str}
""".strip()


# ------------------------------------------------------------------ #
# Output — decisão estruturada que o BRAIN devolve                   #
# ------------------------------------------------------------------ #

class BrainDecisionOutput(BaseModel):
    """
    Output estruturado do agente BRAIN.
    Mapeado diretamente para os campos de ContentDecision.
    """

    decision_type: Literal[
        "content_topic",
        "archetype_selection",
        "platform_targeting",
        "repost_strategy",
        "pause_office",
    ] = Field(
        description="Tipo da decisão tomada pelo BRAIN."
    )

    hypothesis: str = Field(
        description=(
            "Hipótese principal: por que este conteúdo vai performar? "
            "Seja específico — cite o archetype, a plataforma e o sinal de tendência."
        ),
        min_length=20,
        max_length=1000,
    )

    reasoning: dict = Field(
        description=(
            "Chain-of-thought estruturado. Deve conter as chaves: "
            "'sinais_identificados' (list[str]), "
            "'alternativas_descartadas' (list[str]), "
            "'justificativa_final' (str)."
        )
    )

    selected_topic: str | None = Field(
        default=None,
        description="Tema/tópico escolhido para o conteúdo (se decision_type = content_topic).",
        max_length=512,
    )

    selected_archetype: str | None = Field(
        default=None,
        description="Archetype viral selecionado (ex: 'transformação', 'revelação', 'humor').",
        max_length=128,
    )

    selected_platform: str | None = Field(
        default=None,
        description="Plataforma alvo escolhida (tiktok, instagram, youtube, kwai).",
        max_length=64,
    )

    confidence_score: float = Field(
        description="Nível de confiança na decisão, de 0.0 a 1.0.",
        ge=0.0,
        le=1.0,
    )
