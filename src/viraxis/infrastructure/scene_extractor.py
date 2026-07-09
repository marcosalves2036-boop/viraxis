"""Scene Extractor — quebra o roteiro estruturado do RENDERER em cenas.

Cada cena vira uma imagem + trecho de narração no video_composer_v2.
A cena final (CTA) não gera imagem — usa fundo sólido (preto/roxo da marca).
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
    narration: str  # texto que o TTS vai narrar
    visual_description: str  # descrição em português do que deve aparecer na tela
    duration_hint: int  # segundos estimados (calculado por caracteres)
    has_image: bool = True  # False apenas para a cena de CTA (fundo sólido da marca)


def _duration_hint(text: str) -> int:
    if not text:
        return _MIN_DURATION_HINT
    estimated = round(len(text) / _CHARS_PER_SECOND)
    return max(_MIN_DURATION_HINT, min(_MAX_DURATION_HINT, estimated))


def extract_scenes(production_meta: dict) -> list[Scene]:
    """Lê production_meta['roteiro'] e retorna a lista de cenas.

    Regras:
      - hook -> 1 cena
      - cada item de desenvolvimento[] -> 1 cena
      - climax -> 1 cena
      - cta -> 1 cena, sem imagem (has_image=False; usa fundo sólido no compositor)
    """
    roteiro = (production_meta or {}).get("roteiro") or {}
    scenes: list[Scene] = []
    idx = 0

    hook = (roteiro.get("hook") or "").strip()
    if hook:
        scenes.append(
            Scene(
                index=idx,
                narration=hook,
                visual_description=hook,
                duration_hint=_duration_hint(hook),
            )
        )
        idx += 1

    desenvolvimento = roteiro.get("desenvolvimento") or []
    if isinstance(desenvolvimento, str):
        desenvolvimento = [desenvolvimento]
    for cena_texto in desenvolvimento:
        texto = str(cena_texto).strip()
        if not texto:
            continue
        scenes.append(
            Scene(
                index=idx,
                narration=texto,
                visual_description=texto,
                duration_hint=_duration_hint(texto),
            )
        )
        idx += 1

    climax = (roteiro.get("climax") or "").strip()
    if climax:
        scenes.append(
            Scene(
                index=idx,
                narration=climax,
                visual_description=climax,
                duration_hint=_duration_hint(climax),
            )
        )
        idx += 1

    cta = (roteiro.get("cta") or "").strip()
    if cta:
        scenes.append(
            Scene(
                index=idx,
                narration=cta,
                visual_description="",
                duration_hint=_duration_hint(cta),
                has_image=False,
            )
        )
        idx += 1

    if not scenes:
        raise ValueError("production_meta['roteiro'] vazio ou em formato inesperado — sem cenas para extrair.")

    logger.info("scene_extractor: %d cena(s) extraída(s) (%d com imagem)", len(scenes), sum(s.has_image for s in scenes))
    return scenes
