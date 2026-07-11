"""
Upload Analyzer — análise automática de vídeos brutos após upload.

Roda como background task após confirm-upload. Extrai:
  1. Metadados técnicos via ffprobe (duração, resolução, fps, qualidade de áudio)
  2. Transcrição completa com timestamps via Groq Whisper
  3. Análise visual frame-a-frame com timestamps início-fim via Gemini 1.5 Flash

O resultado é salvo em raw_videos.ai_analysis (JSONB) e raw_videos.duration_seconds.
O status muda: pending/ready → processing → ready (com ai_analysis preenchido).

Dependências já instaladas:
  - google-generativeai (via crewai[google-genai])
  - httpx (download do vídeo)
  - ffmpeg + ffprobe (no Render via render.yaml)

Env vars necessárias:
  - GOOGLE_API_KEY   → Gemini 1.5 Flash (análise visual de vídeo)
  - LLM_API_KEY      → Groq Whisper (transcrição — mesma chave do LLM)
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import subprocess
import tempfile
from pathlib import Path

import httpx

from viraxis.config import get_settings
from viraxis.infrastructure.database.session import AsyncSessionLocal
from viraxis.domain.models.raw_video import RawVideo, RawVideoStatus

logger = logging.getLogger(__name__)

# ── Configurações ─────────────────────────────────────────────────────────────

_GEMINI_MODEL = "gemini-flash-latest"  # alias estável — modelos fixos (1.5/2.5) rejeitam contas novas
_GEMINI_TIMEOUT = 300.0        # vídeos longos levam tempo
_WHISPER_MODEL = "whisper-large-v3"
_WHISPER_TIMEOUT = 180.0
_DOWNLOAD_TIMEOUT = 600.0      # 10min para vídeos grandes
_FFPROBE_TIMEOUT = 30
_AUDIO_SAMPLE_RATE = 16000     # Hz — ideal para Whisper
_MAX_VIDEO_BYTES = 500 * 1024 * 1024  # 500MB — limite Gemini File API


# ── Prompt Gemini ─────────────────────────────────────────────────────────────

_GEMINI_SYSTEM = """Você é um analisador especializado de vídeos para criação de conteúdo.
Sua tarefa é analisar o vídeo fornecido e retornar um JSON estruturado com análise detalhada
de cada cena. Responda APENAS com JSON válido, sem markdown, sem texto extra."""

_GEMINI_PROMPT = """Analise este vídeo completo e retorne um JSON com a estrutura abaixo.

INSTRUÇÕES OBRIGATÓRIAS:
1. Identifique cada cena/segmento com timestamps REAIS do vídeo (início e fim em segundos com 1 decimal)
2. Para cada cena, classifique o tipo e descreva com MÁXIMO NÍVEL DE DETALHE:

   SE HOUVER HUMANO(S):
   - Idade aproximada e gênero
   - Tom de pele e características faciais marcantes (formato do rosto, nariz, olhos, sobrancelhas, lábios)
   - Cabelo: cor, comprimento, estilo (liso, ondulado, cacheado, crespo), corte
   - Barba/bigode (se houver): estilo, comprimento
   - Vestuário: peça, cor, estampa, fit
   - Expressão facial: detalhada (sorriso, olhos arregalados, cenho franzido, olhar para baixo, etc.)
   - Postura e gesticulação (se relevante)
   - Posição na cena (centro, lateral, enquadramento: rosto fechado / meio-corpo / corpo inteiro)
   - Contato visual com a câmera (sim/não/intermitente)
   - Maquiagem ou acessórios visíveis

   SE FOR CENA SEM HUMANO (captura de tela, produto, lugar, objeto):
   - Descreva o conteúdo exato mostrado (textos visíveis, números, gráficos, marcas)
   - Cores dominantes e paleta
   - Composição e layout
   - Iluminação e qualidade visual
   - Contexto e ambiente inferido

   SE HOUVER ANIMAL:
   - Espécie e raça provável
   - Cor, padrão da pelagem/plumagem/escama
   - Tamanho estimado
   - Comportamento exato no momento (correndo, dormindo, olhando para câmera, etc.)
   - Expressão ou estado emocional aparente
   - Ambiente ao redor

3. Para TODAS as cenas, inclua também:
   - Qualidade técnica: iluminação (boa/ruim/artificial/natural), foco (nítido/suave/desfocado), estabilidade
   - Tom/energia: (animado, calmo, didático, urgente, emocional, humorístico, etc.)
   - Ambiente de fundo: detalhes do cenário visível

4. Ao final, gere um resumo geral do vídeo com os pontos de maior impacto editorial.

FORMATO JSON DE RESPOSTA (todos os campos obrigatórios):
{
  "duration_seconds": 312.5,
  "total_scenes": 8,
  "scenes": [
    {
      "index": 1,
      "start": 0.0,
      "end": 7.3,
      "type": "human",
      "description": "Descrição completa conforme instruções acima",
      "technical": {
        "lighting": "natural suave frontal",
        "focus": "nítido",
        "stability": "estável",
        "framing": "meio-corpo"
      },
      "tone": "confiante e direto",
      "background": "parede bege com quadro desfocado à direita"
    }
  ],
  "editorial_highlights": [
    {
      "start": 42.0,
      "end": 58.5,
      "reason": "Momento de maior impacto — revelação de resultado com prova visual na tela"
    }
  ],
  "overall_summary": "Resumo do vídeo inteiro em 3-5 frases para uso no pipeline de edição",
  "detected_topics": ["finanças", "investimento", "renda"],
  "predominant_tone": "educativo e motivacional",
  "has_face": true,
  "has_screen_capture": false,
  "audio_quality": "boa",
  "video_quality": "boa"
}"""


# ── Helpers FFprobe / FFmpeg ──────────────────────────────────────────────────

def _run_ffprobe(video_path: str) -> dict:
    """Extrai metadados técnicos do vídeo via ffprobe."""
    cmd = [
        "ffprobe", "-v", "quiet",
        "-print_format", "json",
        "-show_format", "-show_streams",
        video_path,
    ]
    try:
        result = subprocess.run(
            cmd, capture_output=True, text=True, timeout=_FFPROBE_TIMEOUT
        )
        data = json.loads(result.stdout)
        fmt = data.get("format", {})
        streams = data.get("streams", [])

        video_stream = next((s for s in streams if s.get("codec_type") == "video"), {})
        audio_stream = next((s for s in streams if s.get("codec_type") == "audio"), {})

        duration = float(fmt.get("duration") or video_stream.get("duration") or 0)
        width = int(video_stream.get("width") or 0)
        height = int(video_stream.get("height") or 0)

        # fps: "30000/1001" ou "30"
        fps_raw = video_stream.get("r_frame_rate", "0/1")
        try:
            num, den = fps_raw.split("/")
            fps = round(int(num) / int(den), 2)
        except Exception:
            fps = 0.0

        return {
            "duration_seconds": round(duration, 2),
            "resolution": f"{width}x{height}" if width else "desconhecida",
            "fps": fps,
            "video_codec": video_stream.get("codec_name", "desconhecido"),
            "audio_codec": audio_stream.get("codec_name", "desconhecido"),
            "audio_sample_rate": audio_stream.get("sample_rate", "?"),
            "has_audio": bool(audio_stream),
            "file_size_bytes": int(fmt.get("size") or 0),
        }
    except Exception as e:
        logger.warning("ffprobe falhou: %s", e)
        return {"duration_seconds": 0.0, "resolution": "desconhecida"}


async def _extract_audio_for_whisper(video_path: str, out_path: str) -> bool:
    """Extrai áudio mono 16kHz MP3 para o Whisper. Retorna True se OK."""
    cmd = [
        "ffmpeg", "-y",
        "-i", video_path,
        "-vn",                        # sem vídeo
        "-acodec", "mp3",
        "-ac", "1",                   # mono
        "-ar", str(_AUDIO_SAMPLE_RATE),
        "-b:a", "64k",               # qualidade suficiente para STT
        out_path,
    ]
    try:
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.DEVNULL,
            stderr=asyncio.subprocess.DEVNULL,
        )
        await asyncio.wait_for(proc.wait(), timeout=120)
        return proc.returncode == 0 and Path(out_path).exists()
    except Exception as e:
        logger.warning("extração de áudio falhou: %s", e)
        return False


# ── Transcrição via Groq Whisper ──────────────────────────────────────────────

async def _transcribe_with_whisper(audio_path: str) -> dict:
    """
    Transcreve via Groq Whisper com timestamps por segmento.
    Retorna: { "text": "...", "segments": [{"start": 0.0, "end": 3.2, "text": "..."}] }
    """
    settings = get_settings()
    api_key = settings.llm_api_key

    if not api_key:
        logger.warning("LLM_API_KEY não configurada — transcrição ignorada")
        return {"text": "", "segments": []}

    try:
        async with httpx.AsyncClient(timeout=_WHISPER_TIMEOUT) as client:
            with open(audio_path, "rb") as f:
                audio_bytes = f.read()

            resp = await client.post(
                "https://api.groq.com/openai/v1/audio/transcriptions",
                headers={"Authorization": f"Bearer {api_key}"},
                files={"file": ("audio.mp3", audio_bytes, "audio/mpeg")},
                data={
                    "model": _WHISPER_MODEL,
                    "language": "pt",
                    "response_format": "verbose_json",
                    "timestamp_granularities[]": "segment",
                },
            )

        if resp.status_code != 200:
            logger.warning("Whisper retornou %d: %s", resp.status_code, resp.text[:200])
            return {"text": "", "segments": []}

        data = resp.json()
        segments = [
            {
                "start": round(float(s.get("start", 0)), 2),
                "end": round(float(s.get("end", 0)), 2),
                "text": s.get("text", "").strip(),
            }
            for s in (data.get("segments") or [])
            if s.get("text", "").strip()
        ]
        return {"text": data.get("text", "").strip(), "segments": segments}

    except Exception as e:
        logger.warning("Whisper falhou: %s", e)
        return {"text": "", "segments": []}


# ── Análise Visual via Gemini 1.5 Flash ──────────────────────────────────────

async def _analyze_video_with_gemini(video_path: str, duration: float) -> dict:
    """
    Envia o vídeo para o Gemini 1.5 Flash e obtém análise cena-a-cena
    com timestamps precisos e descrições detalhadas.
    """
    settings = get_settings()
    api_key = settings.google_api_key

    if not api_key:
        logger.warning("GOOGLE_API_KEY não configurada — análise visual ignorada")
        return {}

    try:
        from google import genai  # google-genai (SDK novo) — instalado via crewai[google-genai]
        from google.genai import types as genai_types

        client = genai.Client(api_key=api_key)

        file_size = Path(video_path).stat().st_size
        if file_size > _MAX_VIDEO_BYTES:
            logger.warning(
                "Vídeo muito grande para Gemini File API (%dMB > %dMB) — "
                "análise visual ignorada",
                file_size // 1024 // 1024,
                _MAX_VIDEO_BYTES // 1024 // 1024,
            )
            return {}

        # Upload do vídeo para a File API do Gemini
        logger.info("Fazendo upload do vídeo para Gemini File API (%dMB)...", file_size // 1024 // 1024)

        video_file = await asyncio.to_thread(
            client.files.upload,
            file=video_path,
            config=genai_types.UploadFileConfig(
                display_name=f"viraxis_analysis_{Path(video_path).stem}",
                # arquivo temporário não tem extensão — mime explícito obrigatório
                mime_type="video/mp4",
            ),
        )

        # Aguardar processamento pelo Gemini
        for attempt in range(30):  # até 5min
            video_file = await asyncio.to_thread(client.files.get, name=video_file.name)
            state = getattr(video_file.state, "name", str(video_file.state))
            if state == "ACTIVE":
                break
            if state == "FAILED":
                logger.warning("Gemini File API: processamento falhou")
                return {}
            await asyncio.sleep(10)
        else:
            logger.warning("Gemini File API: timeout aguardando processamento")
            return {}

        logger.info("Vídeo ativo no Gemini — iniciando análise de cenas...")

        response = await asyncio.to_thread(
            client.models.generate_content,
            model=_GEMINI_MODEL,
            contents=[video_file, _GEMINI_PROMPT],
            config=genai_types.GenerateContentConfig(
                system_instruction=_GEMINI_SYSTEM,
                temperature=0.2,         # baixo para análise factual precisa
                max_output_tokens=8192,
                http_options=genai_types.HttpOptions(timeout=int(_GEMINI_TIMEOUT * 1000)),
            ),
        )

        raw = response.text.strip()

        # Strip markdown se presente
        if "```" in raw:
            parts = raw.split("```")
            raw = parts[1]
            if raw.startswith("json"):
                raw = raw[4:].lstrip("\n")

        start = raw.find("{")
        if start > 0:
            raw = raw[start:]

        result = json.loads(raw)
        logger.info(
            "Gemini análise OK | cenas=%d | destaques=%d",
            result.get("total_scenes", 0),
            len(result.get("editorial_highlights", [])),
        )

        # Limpar arquivo do Gemini após uso
        try:
            await asyncio.to_thread(client.files.delete, name=video_file.name)
        except Exception:
            pass

        return result

    except Exception as e:
        logger.warning("Análise Gemini falhou: %s", e)
        return {}


# ── Função principal ──────────────────────────────────────────────────────────

async def analyze_uploaded_video(video_id: str, signed_url: str) -> None:
    """
    Entry point: chamado como background task após confirm-upload.

    Fluxo:
      1. Marca status = processing
      2. Baixa o vídeo via signed URL
      3. ffprobe → metadados técnicos
      4. Gemini → análise visual cena-a-cena com timestamps
      5. Groq Whisper → transcrição com timestamps por segmento
      6. Mescla tudo em ai_analysis JSONB
      7. Atualiza raw_videos: duration_seconds + ai_analysis + status = ready

    Em caso de falha parcial (ex: Gemini falha mas Whisper ok), salva o que tiver.
    Nunca deixa o vídeo em status 'processing' em caso de erro — sempre volta a 'ready'.
    """
    logger.info("upload_analyzer iniciando | video_id=%s", video_id)

    from uuid import UUID
    from sqlalchemy import select, update as sa_update

    # 1. Marcar como processing
    async with AsyncSessionLocal() as session:
        await session.execute(
            sa_update(RawVideo)
            .where(RawVideo.id == UUID(video_id))
            .values(status=RawVideoStatus.processing)
        )
        await session.commit()

    with tempfile.TemporaryDirectory() as tmpdir:
        tmp = Path(tmpdir)
        video_path = str(tmp / "video_input")
        audio_path = str(tmp / "audio.mp3")

        technical_meta: dict = {}
        gemini_analysis: dict = {}
        transcription: dict = {"text": "", "segments": []}

        try:
            # 2. Download do vídeo
            logger.info("Baixando vídeo | video_id=%s | url=%.60s...", video_id, signed_url)
            async with httpx.AsyncClient(timeout=_DOWNLOAD_TIMEOUT) as client:
                async with client.stream("GET", signed_url) as resp:
                    resp.raise_for_status()
                    with open(video_path, "wb") as f:
                        async for chunk in resp.aiter_bytes(chunk_size=1024 * 1024):
                            f.write(chunk)
            logger.info("Download OK | video_id=%s | size=%dMB", video_id,
                        Path(video_path).stat().st_size // 1024 // 1024)

            # 3. Metadados técnicos (ffprobe — síncrono, rápido)
            technical_meta = await asyncio.to_thread(_run_ffprobe, video_path)
            duration = technical_meta.get("duration_seconds", 0.0)
            logger.info("ffprobe OK | video_id=%s | duration=%.1fs | res=%s",
                        video_id, duration, technical_meta.get("resolution"))

            # 4. Análise visual (Gemini) e Transcrição (Whisper) em paralelo
            audio_ok = await _extract_audio_for_whisper(video_path, audio_path)

            async def _sem_audio() -> dict:
                return {"text": "", "segments": []}

            gemini_task = asyncio.create_task(
                _analyze_video_with_gemini(video_path, duration)
            )
            whisper_task = asyncio.create_task(
                _transcribe_with_whisper(audio_path) if audio_ok else _sem_audio()
            )

            gemini_analysis, transcription = await asyncio.gather(
                gemini_task, whisper_task, return_exceptions=False
            )

        except Exception as e:
            logger.error("upload_analyzer erro crítico | video_id=%s | erro=%s", video_id, e)
            # Mesmo em erro, salva o que tiver e volta a 'ready'

    # 5. Montar ai_analysis final
    ai_analysis = {
        "status": "complete" if (gemini_analysis or transcription.get("text")) else "partial",
        "technical": technical_meta,
        "transcription": transcription,
        "visual_analysis": gemini_analysis,  # contém scenes[], editorial_highlights, etc.
    }

    # Campos de conveniência no topo (para o BRAIN acessar facilmente)
    if gemini_analysis:
        ai_analysis["overall_summary"] = gemini_analysis.get("overall_summary", "")
        ai_analysis["detected_topics"] = gemini_analysis.get("detected_topics", [])
        ai_analysis["predominant_tone"] = gemini_analysis.get("predominant_tone", "")
        ai_analysis["has_face"] = gemini_analysis.get("has_face", False)
        ai_analysis["scenes"] = gemini_analysis.get("scenes", [])
        ai_analysis["editorial_highlights"] = gemini_analysis.get("editorial_highlights", [])

    if transcription.get("text"):
        ai_analysis["transcription_text"] = transcription["text"]

    duration_seconds = technical_meta.get("duration_seconds") or (
        gemini_analysis.get("duration_seconds") if gemini_analysis else None
    )

    # 6. Salvar no banco
    async with AsyncSessionLocal() as session:
        from sqlalchemy import update as sa_update
        from uuid import UUID as _UUID

        values: dict = {
            "status": RawVideoStatus.ready,
            "ai_analysis": ai_analysis,
        }
        if duration_seconds:
            values["duration_seconds"] = duration_seconds

        await session.execute(
            sa_update(RawVideo)
            .where(RawVideo.id == _UUID(video_id))
            .values(**values)
        )
        await session.commit()

    logger.info(
        "upload_analyzer concluído | video_id=%s | duration=%.1fs | "
        "scenes=%d | transcription_chars=%d",
        video_id,
        duration_seconds or 0,
        len(ai_analysis.get("scenes", [])),
        len(ai_analysis.get("transcription_text", "")),
    )
