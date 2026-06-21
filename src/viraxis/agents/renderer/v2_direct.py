"""Renderer v2 — chamada direta à API Anthropic, output JSON estruturado.

Gera em UMA chamada todos os artefatos:
  - Roteiro completo (hook / desenvolvimento / clímax / CTA)
  - 3 variações de título
  - 3 conceitos de thumbnail
  - SEO / metadata
  - Plano de postagem
  - Checklist de produção

Davi: single call, retry logic, progress via production_meta.
Kevin: variações, voz do canal, checklist acionável.
"""

import json
import logging
from uuid import UUID

from sqlalchemy import desc, select

from viraxis.config import get_settings
from viraxis.domain.models.content_decision import ContentDecision, DecisionStatus
from viraxis.domain.models.content_item import ContentItem, ContentStatus
from viraxis.domain.models.trend_snapshot import TrendSnapshot
from viraxis.infrastructure.database.session import AsyncSessionLocal
from viraxis.infrastructure.repositories.niche_profile import NicheProfileRepository

logger = logging.getLogger(__name__)

MAX_RETRIES = 3

SYSTEM_PROMPT = """Você é o RENDERER da Viraxis — especialista em criação de conteúdo viral.
Responda APENAS com JSON válido, sem markdown, sem texto extra."""

USER_PROMPT = """Crie um pacote completo de produção para este conteúdo:

ESCRITÓRIO
- Nicho: {niche_name}
- Plataforma: {platform}
- Público-alvo: {target_audience}
- Voz do canal: {voice_style}
- Estilo: {content_style}

DECISÃO DO BRAIN
- Tópico: {selected_topic}
- Archetype viral: {selected_archetype}
- Hipótese: {hypothesis}
- Confiança: {confidence_score}%

TENDÊNCIAS RECENTES
{trend_context}

Retorne este JSON (todos os campos obrigatórios):
{{
  "roteiro": {{
    "hook": "primeiros 3-5 segundos que capturam atenção imediata",
    "desenvolvimento": ["Cena 1 — ação + narração exata", "Cena 2", "Cena 3"],
    "climax": "momento de maior impacto/revelação do vídeo",
    "cta": "call-to-action final específico para {platform}"
  }},
  "titulos": [
    "Título 1 — mais viral/clickbait com emoji",
    "Título 2 — otimizado para busca",
    "Título 3 — criativo/alternativo"
  ],
  "thumbnails": [
    {{
      "descricao": "conceito visual principal",
      "cores_principais": ["#hex1", "#hex2"],
      "elementos": ["elemento 1", "elemento 2"],
      "texto_overlay": "texto em destaque (curto)",
      "composicao": "descrição do layout"
    }},
    {{
      "descricao": "variação 2",
      "cores_principais": ["#hex1", "#hex2"],
      "elementos": ["elem1", "elem2"],
      "texto_overlay": "texto alternativo",
      "composicao": "layout alternativo"
    }},
    {{
      "descricao": "variação 3 — minimalista",
      "cores_principais": ["#hex1"],
      "elementos": ["elem principal"],
      "texto_overlay": "texto mínimo",
      "composicao": "composição simples"
    }}
  ],
  "seo": {{
    "titulo_otimizado": "título com keyword no início (max 60 chars)",
    "descricao": "2-3 parágrafos com keywords naturais",
    "tags": ["tag1", "tag2", "tag3", "tag4", "tag5"],
    "hashtags": ["#hashtag1", "#hashtag2", "#hashtag3"],
    "categoria": "categoria da plataforma"
  }},
  "plano_postagem": {{
    "melhor_dia": "ex: Sábado",
    "melhor_horario": "ex: 19h-21h",
    "frequencia_ideal": "ex: 3x por semana",
    "estrategia_reposts": "como adaptar para outras plataformas",
    "notas": "dica para maximizar alcance neste nicho"
  }},
  "checklist_producao": [
    "Item acionável 1",
    "Item 2",
    "Item 3",
    "Item 4",
    "Item 5"
  ],
  "duracao_estimada_segundos": 60
}}"""


async def _update_progress(item_id: UUID, progress: int, stage: str) -> None:
    from sqlalchemy import update as sa_update
    async with AsyncSessionLocal() as s:
        await s.execute(
            sa_update(ContentItem)
            .where(ContentItem.id == item_id)
            .values(production_meta={"render_progress": progress, "render_stage": stage})
        )
        await s.commit()


async def _mark_failed(item_id: UUID, decision_id: UUID, error: str) -> None:
    from sqlalchemy import update as sa_update
    async with AsyncSessionLocal() as s:
        await s.execute(
            sa_update(ContentItem)
            .where(ContentItem.id == item_id)
            .values(
                status=ContentStatus.failed,
                production_meta={"render_progress": 0, "render_stage": "falhou", "error": error},
            )
        )
        await s.execute(
            sa_update(ContentDecision)
            .where(ContentDecision.id == decision_id)
            .values(status=DecisionStatus.failed)
        )
        await s.commit()


async def run_renderer_v2(
    office_id: UUID,
    user_id: UUID,
    decision_id: UUID,
) -> ContentItem:
    """Renderer v2: Anthropic direto, todos os artefatos em 1 chamada."""
    import anthropic

    settings = get_settings()
    client = anthropic.AsyncAnthropic(api_key=settings.anthropic_api_key)

    # 1. Carregar decisão + contexto
    async with AsyncSessionLocal() as session:
        dec_result = await session.execute(
            select(ContentDecision).where(
                ContentDecision.id == decision_id,
                ContentDecision.office_id == office_id,
            )
        )
        decision = dec_result.scalar_one_or_none()
        if not decision:
            raise ValueError(f"Decisão {decision_id} não encontrada")

        niche_repo = NicheProfileRepository(session)
        niche = await niche_repo.get_by_office_or_raise(office_id)

        trend_result = await session.execute(
            select(TrendSnapshot)
            .where(TrendSnapshot.office_id == office_id)
            .order_by(desc(TrendSnapshot.captured_at))
            .limit(1)
        )
        latest_trend = trend_result.scalar_one_or_none()
        trend_signals = latest_trend.processed_signals if latest_trend else {}

        voice_style = (niche.content_style or {}).get("voice_style", "natural e envolvente")
        content_style_label = (niche.content_style or {}).get("style", "entertainment")

    # 2. Criar ContentItem placeholder + marcar decisão como executing
    async with AsyncSessionLocal() as session:
        item = ContentItem(
            office_id=office_id,
            user_id=user_id,
            decision_id=decision_id,
            title=f"Gerando: {decision.selected_topic or 'conteúdo'}…",
            script="",
            status=ContentStatus.rendering,
            production_meta={"render_progress": 10, "render_stage": "iniciando"},
        )
        session.add(item)
        dec_up = await session.execute(
            select(ContentDecision).where(ContentDecision.id == decision_id)
        )
        dec = dec_up.scalar_one()
        dec.status = DecisionStatus.executing
        await session.commit()
        await session.refresh(item)
        item_id = item.id

    logger.info("RENDERER v2 | office=%s decision=%s item=%s", office_id, decision_id, item_id)

    # 3. Contexto de tendências
    if trend_signals:
        kw = ", ".join(str(k) for k in trend_signals.get("keywords", [])[:6])
        trend_context = f"Keywords em alta: {kw}\nArchetype: {trend_signals.get('archetype', '')}"
    else:
        trend_context = "Sem tendências recentes — usar criatividade baseada no nicho."

    prompt = USER_PROMPT.format(
        niche_name=niche.niche_name,
        platform=decision.selected_platform or "youtube",
        target_audience=niche.raw_notes or "público geral",
        voice_style=voice_style,
        content_style=content_style_label,
        selected_topic=decision.selected_topic or "",
        selected_archetype=decision.selected_archetype or "viral_hook",
        hypothesis=decision.hypothesis,
        confidence_score=int((decision.confidence_score or 0.75) * 100),
        trend_context=trend_context,
    )

    # 4. Chamar Claude com retry
    await _update_progress(item_id, 30, "gerando com Claude AI…")

    last_error: Exception | None = None
    data: dict | None = None

    for attempt in range(1, MAX_RETRIES + 1):
        try:
            msg = await client.messages.create(
                model="claude-3-5-haiku-20241022",
                max_tokens=4096,
                system=SYSTEM_PROMPT,
                messages=[{"role": "user", "content": prompt}],
            )
            raw = msg.content[0].text.strip()
            if "```" in raw:
                parts = raw.split("```")
                raw = parts[1]
                if raw.startswith("json"):
                    raw = raw[4:].lstrip("\n")
            data = json.loads(raw)
            break
        except Exception as e:
            last_error = e
            logger.warning("RENDERER v2 tentativa %d/%d falhou: %s", attempt, MAX_RETRIES, e)
            if attempt < MAX_RETRIES:
                import asyncio
                await asyncio.sleep(2 ** attempt)

    if data is None:
        await _mark_failed(item_id, decision_id, str(last_error))
        raise RuntimeError(f"RENDERER v2 falhou após {MAX_RETRIES} tentativas: {last_error}")

    await _update_progress(item_id, 80, "salvando artefatos…")

    # 5. Montar script texto
    rot = data.get("roteiro", {})
    titulos = data.get("titulos", [decision.selected_topic or "Conteúdo"])
    titulo_principal = titulos[0] if titulos else (decision.selected_topic or "Conteúdo")

    dev_lines = "\n".join(
        f"  {i+1}. {c}" for i, c in enumerate(rot.get("desenvolvimento", []))
    )
    script_text = (
        f"# {titulo_principal}\n\n"
        f"## 🎣 HOOK\n{rot.get('hook', '')}\n\n"
        f"## 🎬 DESENVOLVIMENTO\n{dev_lines}\n\n"
        f"## ⚡ CLÍMAX\n{rot.get('climax', '')}\n\n"
        f"## 📣 CALL TO ACTION\n{rot.get('cta', '')}\n"
    )

    # 6. Salvar resultado
    async with AsyncSessionLocal() as session:
        item_r = await session.execute(select(ContentItem).where(ContentItem.id == item_id))
        item = item_r.scalar_one()
        dec_r = await session.execute(select(ContentDecision).where(ContentDecision.id == decision_id))
        dec = dec_r.scalar_one()

        item.title = titulo_principal
        item.script = script_text
        item.duration_seconds = float(data.get("duracao_estimada_segundos", 60))
        item.status = ContentStatus.ready
        item.production_meta = {
            "render_progress": 100,
            "render_stage": "concluído",
            "roteiro": rot,
            "titulos": titulos,
            "thumbnails": data.get("thumbnails", []),
            "seo": data.get("seo", {}),
            "plano_postagem": data.get("plano_postagem", {}),
            "checklist_producao": data.get("checklist_producao", []),
        }
        dec.status = DecisionStatus.done
        await session.commit()
        await session.refresh(item)

    logger.info("RENDERER v2 concluído | item=%s title=%.50s", item_id, titulo_principal)
    return item
