"""Composição de vídeo — modo "100% IA".

Gera narração TTS PT-BR a partir do script do RENDERER e compõe um .mp4
vertical (9:16, 1080x1920, fundo preto) com o áudio. Sobe o resultado para
`ai_generated/{item_id}.mp4` no bucket Supabase.
"""

import logging
import tempfile
from pathlib import Path

from viraxis.infrastructure.tts_client import DEFAULT_VOICE, synthesize_pt
from viraxis.infrastructure.video_processor import (
    _run_ffmpeg,
    sign_storage_path,
    upload_to_storage,
)

logger = logging.getLogger(__name__)


async def compose_ai_video(
    script_text: str,
    item_id: str,
    voice: str = DEFAULT_VOICE,
) -> tuple[str, str]:
    """Gera áudio TTS + vídeo 9:16 com fundo preto.

    Returns:
        (dest_path, signed_url) — caminho estável no bucket + URL assinada 7d.
    """
    dest_path = f"ai_generated/{item_id}.mp4"

    with tempfile.TemporaryDirectory() as tmpdir:
        tmp = Path(tmpdir)
        audio_path = tmp / "audio.mp3"
        output_path = tmp / "output.mp4"

        # 1. TTS
        audio_bytes = await synthesize_pt(script_text, voice)
        audio_path.write_bytes(audio_bytes)

        # 2. Fundo preto 1080x1920 + áudio (duração = duração do áudio)
        await _run_ffmpeg([
            "-f", "lavfi", "-i", "color=c=black:s=1080x1920:r=30",
            "-i", str(audio_path),
            "-shortest",
            "-c:v", "libx264", "-preset", "ultrafast", "-tune", "stillimage",
            "-c:a", "aac", "-b:a", "128k",
            "-pix_fmt", "yuv420p",
            str(output_path),
        ])

        # 3. Upload + signed URL
        await upload_to_storage(output_path, dest_path)

    signed_url = await sign_storage_path(dest_path)
    logger.info("video_composer: concluído | item=%s | path=%s", item_id, dest_path)
    return dest_path, signed_url
