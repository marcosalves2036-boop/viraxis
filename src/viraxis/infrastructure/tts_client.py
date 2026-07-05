"""Cliente TTS PT-BR — vozes neurais via edge-tts.

Nota: o plano original usava Groq PlayAI TTS, mas o modelo `playai-tts` foi
descontinuado pelo Groq (verificado em 2026-07-05; o catálogo atual só tem
TTS Orpheus em inglês/árabe). edge-tts oferece vozes neurais PT-BR
(pt-BR-AntonioNeural, pt-BR-FranciscaNeural) sem necessidade de API key.
"""

import logging
import tempfile
from pathlib import Path

logger = logging.getLogger(__name__)

DEFAULT_VOICE = "pt-BR-AntonioNeural"
VOICES_PT_BR = ["pt-BR-AntonioNeural", "pt-BR-FranciscaNeural", "pt-BR-ThalitaMultilingualNeural"]

# limite defensivo: scripts de shorts têm <2k chars; corta textos anômalos
MAX_TTS_CHARS = 8000


async def synthesize_pt(text: str, voice: str = DEFAULT_VOICE) -> bytes:
    """Converte texto em áudio MP3 (voz neural PT-BR). Retorna os bytes do MP3."""
    import edge_tts  # import lazy — dependência só usada aqui

    clean = " ".join(text.split())[:MAX_TTS_CHARS]
    if not clean:
        raise ValueError("Texto vazio para síntese TTS.")

    with tempfile.TemporaryDirectory() as tmpdir:
        out = Path(tmpdir) / "tts.mp3"
        communicate = edge_tts.Communicate(clean, voice)
        await communicate.save(str(out))
        audio = out.read_bytes()

    if len(audio) < 1000:
        raise RuntimeError(f"TTS retornou áudio suspeito ({len(audio)} bytes).")
    logger.info("TTS OK | voice=%s | chars=%d | bytes=%d", voice, len(clean), len(audio))
    return audio
