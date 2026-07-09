"""Composição de vídeo — modo "100% IA" v2 (visual real por cena).

Evolui o ``video_composer.py`` (que só fazia TTS + fundo preto). Para cada cena
extraída do roteiro (``scene_extractor.extract_scenes``):

  1. Narração TTS PT-BR (edge-tts) — define a duração da cena.
  2. Imagem gerada por IA (Pollinations/FLUX via ``image_generator``) com efeito
     Ken Burns (zoom lento). Se a geração falhar, cai para fundo sólido da marca.
  3. Cena de CTA usa fundo sólido (preto/roxo Viraxis), sem imagem.

Depois: concatena as cenas, queima as legendas (SRT burn-in via libass) e sobe
o ``.mp4`` final (1080x1920, 30fps, libx264/yuv420p, aac 128k) para
``ai_generated/{item_id}.mp4`` no Supabase, retornando ``(dest_path, signed_url)``.

Não altera o fluxo ``mode=editing_plan`` (``video_processor.apply_editing_plan``).
"""

from __future__ import annotations

import asyncio
import logging
import os
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Awaitable, Callable

from viraxis.infrastructure.image_generator import ImageGenerationError, generate_scene_image
from viraxis.infrastructure.scene_extractor import Scene, extract_scenes
from viraxis.infrastructure.tts_client import DEFAULT_VOICE, synthesize_pt
from viraxis.infrastructure.video_processor import (
    _ffmpeg_bin,
    _run_ffmpeg,
    sign_storage_path,
    upload_to_storage,
)

logger = logging.getLogger(__name__)

# ── Constantes de composição ────────────────────────────────────────────────────
_W, _H, _FPS = 1080, 1920, 30
_MIN_SCENE_SEC = 1.2
_TAIL_PAD_SEC = 0.35          # silêncio no fim da cena p/ não cortar a narração
_MAX_SUBTITLE_CHARS = 90      # divide narração longa em blocos legíveis

# Cores da marca Viraxis (fundo sólido: CTA + fallback de cena sem imagem)
_BRAND_COLORS = ("0x000000", "0x1a0033")  # preto, roxo escuro

# Fonte das legendas: preferimos a fonte empacotada no repo (garante renderização
# mesmo que a imagem base do Render não traga DejaVu); fallback para a do sistema.
_BUNDLED_FONTS_DIR = os.path.join(os.path.dirname(__file__), "assets", "fonts")
_SYSTEM_FONTS_DIR = "/usr/share/fonts/truetype/dejavu"
_SUBTITLE_STYLE = (
    "FontName=DejaVu Sans,Fontsize=16,Bold=1,"
    "PrimaryColour=&H00FFFFFF,OutlineColour=&H00000000,BackColour=&H80000000,"
    "BorderStyle=1,Outline=2,Shadow=1,Alignment=2,MarginV=90"
)

ProgressCb = Callable[[int, str], Awaitable[None]] | Callable[[int, str], None] | None


# ── Helpers ──────────────────────────────────────────────────────────────────────

def _ffprobe_bin() -> str:
    ff = _ffmpeg_bin()
    cand = os.path.join(os.path.dirname(ff), "ffprobe") if os.path.dirname(ff) else "ffprobe"
    return cand if (os.path.dirname(ff) and os.path.exists(cand)) else (shutil.which("ffprobe") or "ffprobe")


async def _probe_duration(path: Path) -> float:
    """Duração (segundos) de um arquivo de mídia via ffprobe."""
    def _run() -> float:
        out = subprocess.run(
            [_ffprobe_bin(), "-v", "error", "-show_entries", "format=duration",
             "-of", "default=noprint_wrappers=1:nokey=1", str(path)],
            check=True, capture_output=True, timeout=60,
        )
        return float((out.stdout or b"0").decode().strip() or 0.0)
    try:
        return await asyncio.to_thread(_run)
    except Exception as e:  # noqa: BLE001
        logger.warning("ffprobe falhou para %s (%s) — assumindo %.1fs", path, e, _MIN_SCENE_SEC)
        return _MIN_SCENE_SEC


async def _emit(cb: ProgressCb, pct: int, stage: str) -> None:
    if cb is None:
        return
    try:
        result = cb(pct, stage)
        if asyncio.iscoroutine(result):
            await result
    except Exception as e:  # noqa: BLE001 — progresso nunca deve derrubar o job
        logger.warning("progress_cb falhou (%s)", e)


def _brand_color(index: int) -> str:
    return _BRAND_COLORS[index % len(_BRAND_COLORS)]


def _fonts_dir() -> str | None:
    """Diretório de fontes para o libass: empacotada > sistema > None (default do libass)."""
    for d in (_BUNDLED_FONTS_DIR, _SYSTEM_FONTS_DIR):
        try:
            if os.path.isdir(d) and any(f.lower().endswith(".ttf") for f in os.listdir(d)):
                return d
        except OSError:
            continue
    return None


async def _ken_burns_segment(img_path: Path, audio_path: Path, seg_dur: float,
                             out_path: Path, *, zoom_max: float) -> None:
    """Gera um segmento .mp4 com Ken Burns (zoom lento) sobre a imagem + áudio."""
    frames = max(1, int(round(seg_dur * _FPS)))
    inc = round((zoom_max - 1.0) / frames, 6)
    vf = (
        f"[0:v]scale=1620:2880:force_original_aspect_ratio=increase,"
        f"crop=1620:2880,"
        f"zoompan=z='min(zoom+{inc},{zoom_max})':d={frames}:"
        f"x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':fps={_FPS}:s={_W}x{_H},"
        f"trim=duration={seg_dur:.3f},setsar=1[v]"
    )
    await _run_ffmpeg([
        "-loop", "1", "-t", f"{seg_dur:.3f}", "-i", str(img_path),
        "-i", str(audio_path),
        "-filter_complex", vf,
        "-map", "[v]", "-map", "1:a",
        "-r", str(_FPS), "-c:v", "libx264", "-preset", "veryfast", "-pix_fmt", "yuv420p",
        "-c:a", "aac", "-b:a", "128k", "-ar", "44100",
        str(out_path),
    ])


async def _solid_segment(color: str, audio_path: Path, seg_dur: float, out_path: Path) -> None:
    """Gera um segmento .mp4 com fundo sólido + áudio (CTA ou fallback sem imagem)."""
    await _run_ffmpeg([
        "-f", "lavfi", "-t", f"{seg_dur:.3f}", "-i", f"color=c={color}:s={_W}x{_H}:r={_FPS}",
        "-i", str(audio_path),
        "-map", "0:v", "-map", "1:a",
        "-c:v", "libx264", "-preset", "veryfast", "-pix_fmt", "yuv420p",
        "-c:a", "aac", "-b:a", "128k", "-ar", "44100",
        str(out_path),
    ])


async def _concat_segments(segments: list[Path], tmp: Path, out_path: Path) -> None:
    """Concatena segmentos (mesmos parâmetros de codec) via demuxer concat + copy."""
    list_path = tmp / "concat_list.txt"
    list_path.write_text("\n".join(f"file '{p.name}'" for p in segments), encoding="utf-8")
    await _run_ffmpeg([
        "-f", "concat", "-safe", "0", "-i", str(list_path),
        "-c", "copy", str(out_path),
    ])


def _fmt_ts(seconds: float) -> str:
    if seconds < 0:
        seconds = 0.0
    ms = int(round(seconds * 1000))
    h, ms = divmod(ms, 3_600_000)
    m, ms = divmod(ms, 60_000)
    s, ms = divmod(ms, 1000)
    return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"


def _chunk_text(text: str, max_chars: int = _MAX_SUBTITLE_CHARS) -> list[str]:
    """Quebra o texto em blocos <= max_chars respeitando limites de palavra."""
    words = text.split()
    chunks: list[str] = []
    cur = ""
    for w in words:
        if cur and len(cur) + 1 + len(w) > max_chars:
            chunks.append(cur)
            cur = w
        else:
            cur = f"{cur} {w}".strip()
    if cur:
        chunks.append(cur)
    return chunks or [text.strip()]


def _scene_cues(narration: str, start: float, end: float) -> list[tuple[float, float, str]]:
    """Distribui a narração da cena em cues de legenda proporcionais ao tamanho."""
    text = " ".join((narration or "").split())
    if not text:
        return []
    chunks = _chunk_text(text)
    total_chars = sum(len(c) for c in chunks) or 1
    span = max(end - start, 0.1)
    cues: list[tuple[float, float, str]] = []
    cursor = start
    for c in chunks:
        share = span * (len(c) / total_chars)
        cues.append((cursor, cursor + share, c))
        cursor += share
    # garante que o último cue termina exatamente em `end`
    if cues:
        s, _, t = cues[-1]
        cues[-1] = (s, end, t)
    return cues


def _render_srt(cues: list[tuple[float, float, str]]) -> str:
    blocks = []
    for i, (s, e, text) in enumerate(cues, start=1):
        blocks.append(f"{i}\n{_fmt_ts(s)} --> {_fmt_ts(e)}\n{text}\n")
    return "\n".join(blocks)


def _escape_subtitles_path(path: str) -> str:
    # escapa caracteres especiais do filtergraph do FFmpeg
    return path.replace("\\", "\\\\").replace(":", "\\:").replace("'", "\\'")


async def _burn_subtitles(video_path: Path, srt_path: Path, out_path: Path) -> None:
    """Queima o SRT no vídeo via filtro subtitles (libass)."""
    filt = f"subtitles={_escape_subtitles_path(str(srt_path))}"
    fonts_dir = _fonts_dir()
    if fonts_dir:
        filt += f":fontsdir={_escape_subtitles_path(fonts_dir)}"
    filt += f":force_style='{_SUBTITLE_STYLE}'"
    await _run_ffmpeg([
        "-i", str(video_path),
        "-vf", filt,
        "-c:v", "libx264", "-preset", "veryfast", "-pix_fmt", "yuv420p",
        "-c:a", "copy",
        str(out_path),
    ])


def _resolve_scenes(production_meta: dict, script_text: str) -> list[Scene]:
    """Extrai cenas do roteiro; fallback para uma única cena com o script inteiro."""
    try:
        scenes = extract_scenes(production_meta)
        if scenes:
            return scenes
    except Exception as e:  # noqa: BLE001
        logger.warning("scene_extractor falhou (%s) — fallback para cena única", e)
    text = " ".join((script_text or "").split())
    if not text:
        raise ValueError("Sem roteiro/cenas e sem script_text para compor o vídeo.")
    return [Scene(index=0, narration=text, visual_description=text, duration_hint=8)]


# ── Pipeline principal ───────────────────────────────────────────────────────────

async def compose_ai_video_v2(
    production_meta: dict,
    script_text: str,
    item_id: str,
    voice: str = DEFAULT_VOICE,
    progress_cb: ProgressCb = None,
) -> tuple[str, str]:
    """Compõe o vídeo 100% IA v2 e sobe para o Supabase.

    Returns:
        (dest_path, signed_url) — caminho estável no bucket + URL assinada 7d.
    """
    dest_path = f"ai_generated/{item_id}.mp4"
    scenes = _resolve_scenes(production_meta, script_text)
    n = len(scenes)
    logger.info("video_composer_v2: iniciando | item=%s | %d cena(s)", item_id, n)

    with tempfile.TemporaryDirectory() as tmpdir:
        tmp = Path(tmpdir)
        segments: list[Path] = []
        cues: list[tuple[float, float, str]] = []
        cursor = 0.0

        for i, scene in enumerate(scenes):
            await _emit(progress_cb, 10 + int(70 * i / max(n, 1)), f"gerando cena {i + 1}/{n}")

            # 1. TTS — define a duração da cena
            audio_bytes = await synthesize_pt(scene.narration, voice)
            audio_path = tmp / f"audio_{i}.mp3"
            audio_path.write_bytes(audio_bytes)
            narration_dur = max(await _probe_duration(audio_path), _MIN_SCENE_SEC)
            seg_dur = narration_dur + _TAIL_PAD_SEC

            # 2. Visual — imagem IA (com fallback) ou fundo sólido (CTA)
            img_path: Path | None = None
            if scene.has_image:
                try:
                    img_bytes = await generate_scene_image(scene.visual_description or scene.narration)
                    img_path = tmp / f"img_{i}.bin"
                    img_path.write_bytes(img_bytes)
                except ImageGenerationError as e:
                    logger.warning("cena %d sem imagem IA (%s) — usando fundo sólido", i, e)

            # 3. Segmento
            seg = tmp / f"seg_{i}.mp4"
            if img_path is not None:
                zoom_max = 1.12 if i % 2 == 0 else 1.08
                await _ken_burns_segment(img_path, audio_path, seg_dur, seg, zoom_max=zoom_max)
            else:
                await _solid_segment(_brand_color(i), audio_path, seg_dur, seg)
            segments.append(seg)

            # 4. Legendas desta cena (cobrem só a narração, não o pad final)
            cues.extend(_scene_cues(scene.narration, cursor, cursor + narration_dur))
            cursor += seg_dur

        # 5. Concat
        await _emit(progress_cb, 85, "montando o vídeo")
        concat_path = tmp / "concat.mp4"
        await _concat_segments(segments, tmp, concat_path)

        # 6. Legendas (burn-in)
        await _emit(progress_cb, 92, "queimando legendas")
        final_path = concat_path
        if cues:
            srt_path = tmp / "subs.srt"
            srt_path.write_text(_render_srt(cues), encoding="utf-8")
            burned = tmp / "final.mp4"
            try:
                await _burn_subtitles(concat_path, srt_path, burned)
                final_path = burned
            except Exception as e:  # noqa: BLE001 — sem legenda é melhor que sem vídeo
                logger.warning("burn-in de legendas falhou (%s) — enviando sem legenda", e)

        # 7. Upload
        await _emit(progress_cb, 96, "enviando ao storage")
        await upload_to_storage(final_path.read_bytes(), dest_path)

    signed_url = await sign_storage_path(dest_path)
    await _emit(progress_cb, 100, "concluído")
    logger.info("video_composer_v2: concluído | item=%s | path=%s", item_id, dest_path)
    return dest_path, signed_url
