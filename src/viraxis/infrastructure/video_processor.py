"""Processamento de vídeo — modo "com referência".

Baixa o vídeo bruto do Supabase Storage, aplica os cortes do plano de edição
via FFmpeg e sobe o resultado para `edited/{item_id}.mp4` no mesmo bucket.

Também expõe helpers de storage (upload/sign) reutilizados pelo
video_composer (modo 100% IA).

FFmpeg: binário estático baixado no build do Render (ver render.yaml).
Resolução via $FFMPEG_BIN > PATH.
"""

import asyncio
import logging
import os
import shutil
import subprocess
import tempfile
from pathlib import Path

import httpx

from viraxis.config import get_settings

logger = logging.getLogger(__name__)

# prioridades aceitas como "manter no corte final" (runner EN + v2_direct PT)
_KEEP_PRIORITIES = {"essential", "recommended", "essencial", "recomendado"}


def _ffmpeg_bin() -> str:
    return os.environ.get("FFMPEG_BIN") or shutil.which("ffmpeg") or "ffmpeg"


async def _run_ffmpeg(args: list[str]) -> None:
    """Roda FFmpeg em thread (não bloqueia o event loop). Levanta RuntimeError com stderr."""
    cmd = [_ffmpeg_bin(), "-y", "-hide_banner", "-loglevel", "error", *args]
    try:
        await asyncio.to_thread(
            subprocess.run, cmd, check=True, capture_output=True, timeout=300
        )
    except subprocess.CalledProcessError as e:
        stderr = (e.stderr or b"").decode(errors="ignore")[-800:]
        raise RuntimeError(f"FFmpeg falhou: {stderr}") from e
    except FileNotFoundError:
        raise RuntimeError(
            "FFmpeg não encontrado no container. Verifique o buildCommand do render.yaml."
        )


# ------------------------------------------------------------------ #
# Storage helpers (Supabase)                                          #
# ------------------------------------------------------------------ #

def _storage_headers() -> dict:
    settings = get_settings()
    key = settings.supabase_service_role_key
    return {"Authorization": f"Bearer {key}", "apikey": key}


async def upload_to_storage(data: bytes, dest_path: str, content_type: str = "video/mp4") -> str:
    """Sobe bytes para o bucket (upsert). Retorna o dest_path."""
    settings = get_settings()
    url = (
        f"{settings.supabase_url}/storage/v1/object/"
        f"{settings.supabase_bucket}/{dest_path}"
    )
    headers = {**_storage_headers(), "Content-Type": content_type, "x-upsert": "true"}
    async with httpx.AsyncClient(timeout=180.0) as client:
        resp = await client.post(url, content=data, headers=headers)
        if resp.status_code not in (200, 201):
            raise RuntimeError(
                f"Upload Supabase falhou ({resp.status_code}): {resp.text[:300]}"
            )
    return dest_path


async def sign_storage_path(path: str, expires_in: int = 604800) -> str:
    """Gera signed URL (padrão 7 dias) para um objeto do bucket."""
    settings = get_settings()
    url = (
        f"{settings.supabase_url}/storage/v1/object/sign/"
        f"{settings.supabase_bucket}/{path}"
    )
    async with httpx.AsyncClient(timeout=15.0) as client:
        resp = await client.post(url, json={"expiresIn": expires_in}, headers=_storage_headers())
        resp.raise_for_status()
        data = resp.json()
    signed = data.get("signedURL") or data.get("signedUrl") or ""
    if signed and not signed.startswith("http"):
        signed = f"{settings.supabase_url}/storage/v1{signed}"
    if not signed:
        raise RuntimeError(f"Supabase não retornou signed URL para {path}")
    return signed


# ------------------------------------------------------------------ #
# Normalização do plano de edição                                     #
# ------------------------------------------------------------------ #

def extract_keep_segments(production_meta: dict) -> list[tuple[float, float]]:
    """Extrai os segmentos a MANTER do production_meta, em qualquer formato.

    Suporta:
      - v2_direct (produção): meta["plano_edicao"]["cortes"] com chaves
        inicio/fim/tipo/prioridade (pt-BR)
      - runner CrewAI: meta["renderer_output"]["suggested_cuts"] com chaves
        timestamp_start/timestamp_end/instruction_type/priority (EN)

    Retorna lista ordenada de (start, end). Vazia => usar o vídeo inteiro.
    """
    raw_instructions: list[dict] = []
    plano = production_meta.get("plano_edicao") or {}
    if plano.get("cortes"):
        for c in plano["cortes"]:
            raw_instructions.append({
                "start": c.get("inicio"),
                "end": c.get("fim"),
                "type": (c.get("tipo") or "").lower(),
                "priority": (c.get("prioridade") or "recomendado").lower(),
            })
    else:
        ro = production_meta.get("renderer_output") or {}
        for c in ro.get("suggested_cuts", []):
            raw_instructions.append({
                "start": c.get("timestamp_start"),
                "end": c.get("timestamp_end"),
                "type": (c.get("instruction_type") or "").lower(),
                "priority": (c.get("priority") or "recommended").lower(),
            })

    segments: list[tuple[float, float]] = []
    for ins in raw_instructions:
        if ins["type"] != "keep" or ins["priority"] not in _KEEP_PRIORITIES:
            continue
        start, end = ins["start"], ins["end"]
        if start is None or end is None:
            continue
        try:
            start_f, end_f = float(start), float(end)
        except (TypeError, ValueError):
            continue
        if end_f > start_f >= 0:
            segments.append((start_f, end_f))

    segments.sort(key=lambda s: s[0])
    return segments


# ------------------------------------------------------------------ #
# Pipeline principal                                                  #
# ------------------------------------------------------------------ #

async def apply_editing_plan(
    raw_video_url: str,
    keep_segments: list[tuple[float, float]],
    item_id: str,
) -> tuple[str, str]:
    """Baixa o vídeo bruto, aplica os cortes e sobe o resultado.

    Returns:
        (dest_path, signed_url) — caminho estável no bucket + URL assinada 7d.
    """
    dest_path = f"edited/{item_id}.mp4"

    with tempfile.TemporaryDirectory() as tmpdir:
        tmp = Path(tmpdir)
        input_path = tmp / "input.mp4"
        output_path = tmp / "output.mp4"

        # 1. Download do vídeo bruto
        async with httpx.AsyncClient(timeout=300.0, follow_redirects=True) as client:
            resp = await client.get(raw_video_url)
            resp.raise_for_status()
            input_path.write_bytes(resp.content)
        logger.info(
            "video_processor: download OK | item=%s | %d bytes | %d segmento(s) keep",
            item_id, input_path.stat().st_size, len(keep_segments),
        )

        # 2. Cortes
        if not keep_segments:
            # fallback seguro: sem instruções keep válidas → vídeo inteiro
            output_path = input_path
        elif len(keep_segments) == 1:
            s, e = keep_segments[0]
            await _run_ffmpeg([
                "-i", str(input_path), "-ss", f"{s:.3f}", "-to", f"{e:.3f}",
                "-c:v", "libx264", "-preset", "ultrafast", "-crf", "23",
                "-c:a", "aac", "-pix_fmt", "yuv420p", str(output_path),
            ])
        else:
            # recodifica cada segmento (corte preciso) e concatena
            seg_paths: list[Path] = []
            for i, (s, e) in enumerate(keep_segments):
                seg_path = tmp / f"seg_{i}.mp4"
                await _run_ffmpeg([
                    "-i", str(input_path), "-ss", f"{s:.3f}", "-to", f"{e:.3f}",
                    "-c:v", "libx264", "-preset", "ultrafast", "-crf", "23",
                    "-c:a", "aac", "-pix_fmt", "yuv420p", str(seg_path),
                ])
                seg_paths.append(seg_path)

            list_path = tmp / "list.txt"
            list_path.write_text("\n".join(f"file '{p}'" for p in seg_paths))
            await _run_ffmpeg([
                "-f", "concat", "-safe", "0", "-i", str(list_path),
                "-c", "copy", str(output_path),
            ])

        # 3. Upload + signed URL
        await upload_to_storage(output_path.read_bytes(), dest_path)

    signed_url = await sign_storage_path(dest_path)
    logger.info("video_processor: concluído | item=%s | path=%s", item_id, dest_path)
    return dest_path, signed_url
