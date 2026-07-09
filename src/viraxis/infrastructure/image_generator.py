"""Image Generator — uma imagem por cena via Pollinations.ai (FLUX).

Fluxo por cena:
  1. LLM (litellm/Groq, mesmo provider do RENDERER) traduz/otimiza a
     ``visual_description`` em PT-BR para um prompt de text-to-image em inglês.
  2. ``GET https://image.pollinations.ai/prompt/{prompt}?width=1080&height=1920&model=flux&nologo=true``
  3. timeout 30s + retry (3 tentativas no total), retorna os bytes da imagem.

Pollinations é público (sem API key). Opcionalmente, se ``POLLINATIONS_API_KEY``
estiver no ambiente, é enviado como ``Authorization: Bearer`` (chaves ``sk_``
removem rate limit — ver docs.pollinations.ai).

Nota de robustez: a geração ao vivo depende da origem do Pollinations estar no ar.
Se a chamada falhar após os retries, esta função levanta ``ImageGenerationError`` —
cabe ao compositor decidir o fallback (fundo sólido da marca) para não derrubar
o vídeo inteiro por causa de uma cena.
"""

from __future__ import annotations

import asyncio
import logging
import os
from urllib.parse import quote, urlencode

import httpx

from viraxis.config import get_settings

logger = logging.getLogger(__name__)

_POLLINATIONS_BASE = "https://image.pollinations.ai/prompt/"
_IMG_TIMEOUT = 30.0
_MAX_ATTEMPTS = 3          # 1 tentativa + 2 retries
_PROMPT_MAX_CHARS = 1200   # limite defensivo para o path da URL
_MODEL = "flux"

# assinaturas de imagem aceitas (PNG, JPEG, WEBP)
_IMAGE_SIGNATURES = (b"\x89PNG\r\n\x1a\n", b"\xff\xd8\xff", b"RIFF")

_PROMPT_SYSTEM = (
    "You are a visual prompt engineer for a text-to-image model (FLUX). "
    "Given a short scene description in Portuguese, write ONE concise English "
    "prompt (max 55 words) describing a single vertical 9:16 cinematic image "
    "for a social media short. Focus on concrete visual subject, setting, "
    "lighting, mood and art style. Do NOT include any on-image text, captions, "
    "watermarks, logos, or real people's names. "
    "Return ONLY the prompt text — no quotes, no preamble, no explanation."
)

_STYLE_SUFFIX = (
    ", cinematic, highly detailed, dramatic lighting, vertical 9:16 composition, "
    "vibrant colors, sharp focus, no text, no watermark"
)


class ImageGenerationError(RuntimeError):
    """Falha ao gerar/baixar a imagem da cena após todos os retries."""


async def _optimize_prompt(visual_description: str) -> str:
    """Traduz/otimiza a descrição PT-BR em um prompt EN para o modelo de imagem.

    Fallback seguro: se o LLM falhar, usa a própria descrição (limpa) como prompt.
    """
    description = " ".join((visual_description or "").split())
    if not description:
        return "abstract cinematic vertical background, dark moody neon lighting"

    settings = get_settings()
    try:
        import litellm  # import lazy — dependência só usada aqui

        litellm.set_verbose = False
        response = await litellm.acompletion(
            model=settings.llm_model,
            api_key=settings.llm_api_key,
            messages=[
                {"role": "system", "content": _PROMPT_SYSTEM},
                {"role": "user", "content": description[:1000]},
            ],
            max_tokens=180,
            temperature=0.7,
        )
        prompt = (response.choices[0].message.content or "").strip().strip('"').strip("`")
        prompt = " ".join(prompt.split())
        if prompt:
            logger.info("image_generator: prompt otimizado (%d chars)", len(prompt))
            return prompt[:_PROMPT_MAX_CHARS]
    except Exception as e:  # noqa: BLE001 — qualquer erro do LLM cai no fallback
        logger.warning("image_generator: otimização de prompt falhou (%s) — usando descrição crua", e)

    return description[:_PROMPT_MAX_CHARS]


def _looks_like_image(content: bytes, content_type: str) -> bool:
    if not content or len(content) < 1000:
        return False
    if content_type.startswith("image/"):
        return True
    return content.startswith(_IMAGE_SIGNATURES)


async def generate_scene_image(
    visual_description: str,
    *,
    width: int = 1080,
    height: int = 1920,
    seed: int | None = None,
) -> bytes:
    """Gera 1 imagem para a cena e retorna os bytes.

    Args:
        seed: semente distinta por cena → garante imagens variadas e reproduzíveis.

    Raises:
        ImageGenerationError: se todas as tentativas falharem.
    """
    prompt = await _optimize_prompt(visual_description)
    full_prompt = f"{prompt}{_STYLE_SUFFIX}"[:_PROMPT_MAX_CHARS]

    params = {"width": width, "height": height, "model": _MODEL, "nologo": "true"}
    if seed is not None:
        params["seed"] = int(seed) % 2_147_483_647
    query = urlencode(params)
    url = f"{_POLLINATIONS_BASE}{quote(full_prompt, safe='')}?{query}"

    headers = {"User-Agent": "viraxis/1.0"}
    api_key = os.environ.get("POLLINATIONS_API_KEY", "").strip()
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"

    last_error: Exception | str | None = None
    for attempt in range(1, _MAX_ATTEMPTS + 1):
        try:
            async with httpx.AsyncClient(timeout=_IMG_TIMEOUT, follow_redirects=True) as client:
                resp = await client.get(url, headers=headers)
            ctype = resp.headers.get("content-type", "")
            if resp.status_code == 200 and _looks_like_image(resp.content, ctype):
                logger.info(
                    "image_generator OK | tentativa=%d | bytes=%d | ctype=%s",
                    attempt, len(resp.content), ctype,
                )
                return resp.content
            last_error = f"HTTP {resp.status_code} ctype={ctype!r} bytes={len(resp.content or b'')}"
        except Exception as e:  # noqa: BLE001
            last_error = e

        logger.warning(
            "image_generator tentativa %d/%d falhou: %s", attempt, _MAX_ATTEMPTS, last_error
        )
        if attempt < _MAX_ATTEMPTS:
            await asyncio.sleep(2 * attempt)  # backoff simples: 2s, 4s

    raise ImageGenerationError(
        f"Pollinations não retornou imagem após {_MAX_ATTEMPTS} tentativas: {last_error}"
    )
