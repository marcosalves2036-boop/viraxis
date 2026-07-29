"""Utilitarios compartilhados entre routers da API.

Centraliza padroes usados em multiplos routers para evitar duplicacao de
logica (e o risco de um router receber o tratamento de erro e outro nao).
"""

import logging
from typing import Any
from uuid import UUID

from fastapi import HTTPException, status

logger = logging.getLogger(__name__)


def parse_uuid(value: Any, field_name: str = "id") -> UUID:
    """Converte `value` em UUID, retornando 422 legivel em vez de deixar um
    ValueError/TypeError nao tratado estourar como 500 generico.

    Historico: bug encontrado em auditoria (2026-07) — `UUID(str)` sem
    tratamento em varios routers (raw_videos.upload-url, content_items,
    oauth, social_accounts) derrubava a request com um 500 sem detalhe
    algum sempre que o cliente mandava um id malformado (ex: "" ou
    "undefined" vindo de um bug no frontend). Este helper e o ponto unico
    de conversao string->UUID na API; qualquer novo endpoint que precise
    validar um UUID vindo de path/query/body deve importar daqui em vez de
    chamar `UUID(...)` diretamente.

    Aceita `None` como invalido (levanta 422) — quem quiser tratar `None`
    como "ausente" deve checar antes de chamar esta funcao.
    """
    if value is None:
        logger.warning("UUID ausente (None) recebido para %s", field_name)
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"{field_name} invalido: deve ser um UUID valido.",
        )
    try:
        return UUID(str(value))
    except (ValueError, AttributeError, TypeError):
        logger.warning("UUID invalido recebido para %s: %r", field_name, value)
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"{field_name} invalido: deve ser um UUID valido.",
        )
