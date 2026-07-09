"""Scene Extractor — quebra o roteiro estruturado do RENDERER em cenas.

Cada cena tem DOIS textos independentes:
  - ``narration``: o que o TTS fala e o que vira legenda (o conteúdo do vídeo).
  - ``visual_description``: o que deve aparecer na imagem gerada por IA — NUNCA é
    falado. Usado apenas pelo ``image_generator``.

Formatos aceitos no ``production_meta['roteiro']``:
  - NOVO (recomendado): cada parte é um objeto
    ``{"narracao": "...", "descricao_visual": "..."}``.
  - LEGADO: cada parte é uma string única (usada tanto para fala quanto imagem).

A cena final (CTA) é falada mas não gera imagem — usa fundo sólido (preto/roxo).
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

logger = logging.getLogger(__name__)

# ~15 caracteres por segundo de fala em PT-BR (heurística conservadora para TTS neural)
_CHARS_PER_SECOND = 15.0
_MIN_DURATION_HINT = 2
_MAX_DURATION_HINT = 12


@dataclass
class Scene:
    index: int
    narration: str  # texto que o TTS vai narrar (e que vira legenda)
    visual_description: str  # descrição PT-BR só para gerar a imagem (não é falada)
    duration_hint: int  # segundos estimados (calculado pela narração)
    has_image: bool = True  # False apenas para a cena de CTA (fundo sólido da marca)


def _duration_hint(text: str) -> int:
    if not text:
        return _MIN_DURATION_HINT
    estimated = round(len(text) / _CHARS_PER_SECOND)
    return max(_MIN_DURATION_HINT, min(_MAX_DURATION_HINT, estimated))


def split_scene_part(part) -> tuple[str, str]:
    """Normaliza uma parte do roteiro em ``(narracao, descricao_visual)``.

    - dict novo → usa ``narracao`` e ``descricao_visual`` (visual cai p/ narração
      se vier vazio).
    - string legada → mesmo texto para os dois (comportamento antigo).
    """
    if isinstance(part, dict):
        narr = str(part.get("narracao") or part.get("narração") or "").strip()
        vis = str(
            part.get("descricao_visual")
            or part.get("descrição_visual")
            or part.get("visual")
            or ""
        ).strip()
        return narr, (vis or narr)
    text = str(part or "").strip()
    return text, text


def extract_scenes(production_meta: dict) -> list[Scene]:
    """Lê ``production_meta['roteiro']`` e retorna a lista de cenas.

    Regras:
      - hook -> 1 cena
      - cada item de desenvolvimento[] -> 1 cena
      - climax -> 1 cena
      - cta -> 1 cena, falada mas sem imagem (has_image=False; fundo sólido)
    """
    roteiro = (production_meta or {}).get("roteiro") or {}
    scenes: list[Scene] = []

    def _add(part, *, has_image: bool = True) -> None:
        narration, visual = split_scene_part(part)
        if not narration:
            return
        scenes.append(
            Scene(
                index=len(scenes),
                narration=narration,
                visual_description=visual if has_image else "",
                duration_hint=_duration_hint(narration),
                has_image=has_image,
            )
        )

    _add(roteiro.get("hook"))

    desenvolvimento = roteiro.get("desenvolvimento") or []
    if isinstance(desenvolvimento, (str, dict)):
        desenvolvimento = [desenvolvimento]
    for cena in desenvolvimento:
        _add(cena)

    _add(roteiro.get("climax"))
    _add(roteiro.get("cta"), has_image=False)

    if not scenes:
        raise ValueError(
            "production_meta['roteiro'] vazio ou em formato inesperado — sem cenas para extrair."
        )

    logger.info(
        "scene_extractor: %d cena(s) extraída(s) (%d com imagem)",
        len(scenes), sum(s.has_image for s in scenes),
    )
    return scenes
