"""Image Generator — uma imagem por cena, com múltiplos provedores.

Ordem de provedores (fallback automático, na ordem de disponibilidade de key):
  1. Cloudflare Workers AI — FLUX.1 [schnell] (grátis, sem cartão). Usado se
     ``CLOUDFLARE_ACCOUNT_ID`` + ``CLOUDFLARE_API_TOKEN`` estiverem no ambiente.
  2. Together AI — FLUX.1 [schnell]. Usado se ``TOGETHER_API_KEY`` existir.
     (Obs: a Together passou a exigir depósito p/ liberar a API.)
  3. Pollinations.ai (FLUX) — público, sem key. Fallback (instável).

Fluxo por cena:
  1. LLM (litellm/Groq, mesmo provider do RENDERER) traduz/otimiza a
     ``visual_description`` (PT-BR) em um prompt de text-to-image em inglês.
  2. Tenta cada provedor na ordem; retorna os bytes da 1ª imagem válida.
  3. Se todos falharem, levanta ``ImageGenerationError`` — o compositor então
     usa fundo sólido da marca para aquela cena (não derruba o vídeo).

Config por ambiente:
  - ``CLOUDFLARE_ACCOUNT_ID`` + ``CLOUDFLARE_API_TOKEN`` → Cloudflare (primário).
  - ``TOGETHER_API_KEY``      → Together.
  - ``POLLINATIONS_API_KEY``  → opcional (bearer) para o Pollinations.
"""

from __future__ import annotations

import asyncio
import base64
import logging
import os
from urllib.parse import quote, urlencode

import httpx

from viraxis.config import get_settings

logger = logging.getLogger(__name__)

# ── Cloudflare Workers AI (FLUX.1 schnell — grátis) ──────────────────────────────
_CF_MODEL = "@cf/black-forest-labs/flux-1-schnell"
_CF_TIMEOUT = 60.0
_CF_ATTEMPTS = 2
_CF_STEPS = 4  # schnell: 1–8

# ── Together AI (FLUX.1 schnell) ─────────────────────────────────────────────────
_TOGETHER_URL = "https://api.together.xyz/v1/images/generations"
_TOGETHER_MODEL = "black-forest-labs/FLUX.1-schnell-Free"
_TOGETHER_TIMEOUT = 60.0
_TOGETHER_ATTEMPTS = 2
_TOGETHER_MAX_DIM = 1440
_TOGETHER_STEPS = 4

# ── Pollinations ─────────────────────────────────────────────────────────────────
_POLLINATIONS_BASE = "https://image.pollinations.ai/prompt/"
_POLLINATIONS_TIMEOUT = 30.0
_POLLINATIONS_ATTEMPTS = 3
_POLLINATIONS_MODEL = "flux"

_PROMPT_MAX_CHARS = 1200
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
    """Falha ao gerar/baixar a imagem da cena após todos os provedores/retries."""


async def _optimize_prompt(visual_description: str) -> str:
    """Traduz/otimiza a descrição PT-BR em um prompt EN para o modelo de imagem."""
    description = " ".join((visual_description or "").split())
    if not description:
        return "abstract cinematic vertical background, dark moody neon lighting"

    settings = get_settings()
    try:
        import litellm

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
    except Exception as e:  # noqa: BLE001
        logger.warning("image_generator: otimização de prompt falhou (%s) — usando descrição crua", e)

    return description[:_PROMPT_MAX_CHARS]


def _looks_like_image(content: bytes, content_type: str = "") -> bool:
    if not content or len(content) < 1000:
        return False
    if content_type.startswith("image/"):
        return True
    return content.startswith(_IMAGE_SIGNATURES)


# ── Provedor: Cloudflare Workers AI ──────────────────────────────────────────────

async def _generate_cloudflare(full_prompt: str, width: int, height: int, seed: int | None) -> bytes:
    account_id = os.environ.get("CLOUDFLARE_ACCOUNT_ID", "").strip()
    token = os.environ.get("CLOUDFLARE_API_TOKEN", "").strip()
    if not (account_id and token):
        raise ImageGenerationError("CLOUDFLARE_ACCOUNT_ID/CLOUDFLARE_API_TOKEN ausentes")

    url = f"https://api.cloudflare.com/client/v4/accounts/{account_id}/ai/run/{_CF_MODEL}"
    payload: dict = {"prompt": full_prompt, "steps": _CF_STEPS}
    if seed is not None:
        payload["seed"] = int(seed) % 2_147_483_647
    headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}

    last_error: object = None
    for attempt in range(1, _CF_ATTEMPTS + 1):
        try:
            async with httpx.AsyncClient(timeout=_CF_TIMEOUT) as client:
                resp = await client.post(url, json=payload, headers=headers)
            if resp.status_code == 200:
                body = resp.json() or {}
                b64 = (body.get("result") or {}).get("image")
                if b64:
                    raw = base64.b64decode(b64)
                    if _looks_like_image(raw):
                        logger.info("image_generator[cloudflare] OK | tentativa=%d | bytes=%d", attempt, len(raw))
                        return raw
                last_error = f"sem imagem no corpo (success={body.get('success')}, errors={body.get('errors')})"
            else:
                last_error = f"HTTP {resp.status_code}: {resp.text[:200]}"
        except Exception as e:  # noqa: BLE001
            last_error = e
        logger.warning("image_generator[cloudflare] tentativa %d/%d falhou: %s", attempt, _CF_ATTEMPTS, last_error)
        if attempt < _CF_ATTEMPTS:
            await asyncio.sleep(2 * attempt)
    raise ImageGenerationError(f"Cloudflare falhou: {last_error}")


# ── Provedor: Together AI ────────────────────────────────────────────────────────

def _clamp_together_dims(width: int, height: int) -> tuple[int, int]:
    scale = min(1.0, _TOGETHER_MAX_DIM / max(width, height))

    def _round16(v: float) -> int:
        return max(16, int(round(v * scale / 16)) * 16)

    return _round16(width), _round16(height)


async def _generate_together(full_prompt: str, width: int, height: int, seed: int | None) -> bytes:
    api_key = os.environ.get("TOGETHER_API_KEY", "").strip()
    if not api_key:
        raise ImageGenerationError("TOGETHER_API_KEY ausente")

    w, h = _clamp_together_dims(width, height)
    payload = {
        "model": _TOGETHER_MODEL,
        "prompt": full_prompt,
        "width": w,
        "height": h,
        "steps": _TOGETHER_STEPS,
        "n": 1,
        "response_format": "b64_json",
    }
    if seed is not None:
        payload["seed"] = int(seed) % 2_147_483_647
    headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}

    last_error: object = None
    for attempt in range(1, _TOGETHER_ATTEMPTS + 1):
        try:
            async with httpx.AsyncClient(timeout=_TOGETHER_TIMEOUT) as client:
                resp = await client.post(_TOGETHER_URL, json=payload, headers=headers)
            if resp.status_code == 200:
                data = (resp.json() or {}).get("data") or []
                if data:
                    item = data[0]
                    b64 = item.get("b64_json")
                    if b64:
                        raw = base64.b64decode(b64)
                        if _looks_like_image(raw):
                            logger.info("image_generator[together] OK | tentativa=%d | bytes=%d", attempt, len(raw))
                            return raw
                    url = item.get("url")
                    if url:
                        async with httpx.AsyncClient(timeout=_TOGETHER_TIMEOUT, follow_redirects=True) as c2:
                            img = await c2.get(url)
                        if img.status_code == 200 and _looks_like_image(img.content, img.headers.get("content-type", "")):
                            logger.info("image_generator[together] OK (url) | tentativa=%d | bytes=%d", attempt, len(img.content))
                            return img.content
                last_error = f"resposta sem imagem utilizável ({resp.status_code})"
            else:
                last_error = f"HTTP {resp.status_code}: {resp.text[:200]}"
        except Exception as e:  # noqa: BLE001
            last_error = e
        logger.warning("image_generator[together] tentativa %d/%d falhou: %s", attempt, _TOGETHER_ATTEMPTS, last_error)
        if attempt < _TOGETHER_ATTEMPTS:
            await asyncio.sleep(2 * attempt)
    raise ImageGenerationError(f"Together falhou: {last_error}")


# ── Provedor: Pollinations ───────────────────────────────────────────────────────

async def _generate_pollinations(full_prompt: str, width: int, height: int, seed: int | None) -> bytes:
    params = {"width": width, "height": height, "model": _POLLINATIONS_MODEL, "nologo": "true"}
    if seed is not None:
        params["seed"] = int(seed) % 2_147_483_647
    url = f"{_POLLINATIONS_BASE}{quote(full_prompt, safe='')}?{urlencode(params)}"

    headers = {"User-Agent": "viraxis/1.0"}
    api_key = os.environ.get("POLLINATIONS_API_KEY", "").strip()
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"

    last_error: object = None
    for attempt in range(1, _POLLINATIONS_ATTEMPTS + 1):
        try:
            async with httpx.AsyncClient(timeout=_POLLINATIONS_TIMEOUT, follow_redirects=True) as client:
                resp = await client.get(url, headers=headers)
            ctype = resp.headers.get("content-type", "")
            if resp.status_code == 200 and _looks_like_image(resp.content, ctype):
                logger.info("image_generator[pollinations] OK | tentativa=%d | bytes=%d", attempt, len(resp.content))
                return resp.content
            last_error = f"HTTP {resp.status_code} ctype={ctype!r} bytes={len(resp.content or b'')}"
        except Exception as e:  # noqa: BLE001
            last_error = e
        logger.warning("image_generator[pollinations] tentativa %d/%d falhou: %s", attempt, _POLLINATIONS_ATTEMPTS, last_error)
        if attempt < _POLLINATIONS_ATTEMPTS:
            await asyncio.sleep(2 * attempt)
    raise ImageGenerationError(f"Pollinations falhou: {last_error}")


# ── API pública ──────────────────────────────────────────────────────────────────

def _provider_chain():
    """Ordem dos provedores conforme as keys disponíveis (Pollinations sempre por último)."""
    chain = []
    if os.environ.get("CLOUDFLARE_ACCOUNT_ID", "").strip() and os.environ.get("CLOUDFLARE_API_TOKEN", "").strip():
        chain.append(("cloudflare", _generate_cloudflare))
    if os.environ.get("TOGETHER_API_KEY", "").strip():
        chain.append(("together", _generate_together))
    chain.append(("pollinations", _generate_pollinations))
    return chain


async def generate_scene_image(
    visual_description: str,
    *,
    width: int = 1080,
    height: int = 1920,
    seed: int | None = None,
) -> bytes:
    """Gera 1 imagem para a cena e retorna os bytes.

    Tenta os provedores em ordem (Cloudflare → Together → Pollinations). Se
    ``seed`` for dado, as imagens ficam variadas por cena e reproduzíveis.

    Raises:
        ImageGenerationError: se todos os provedores falharem.
    """
    prompt = await _optimize_prompt(visual_description)
    full_prompt = f"{prompt}{_STYLE_SUFFIX}"[:_PROMPT_MAX_CHARS]

    errors: list[str] = []
    for name, fn in _provider_chain():
        try:
            return await fn(full_prompt, width, height, seed)
        except ImageGenerationError as e:
            errors.append(f"{name}: {e}")
            logger.warning("image_generator: provedor '%s' falhou, tentando próximo", name)

    raise ImageGenerationError("todos os provedores falharam → " + " | ".join(errors))
