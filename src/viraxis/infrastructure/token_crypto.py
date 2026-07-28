"""Criptografia simetrica (Fernet) para tokens OAuth de SocialAccount.

A chave e derivada de `settings.secret_key` via SHA-256 -> base64 urlsafe
(32 bytes), o mesmo esquema historicamente usado em `api/routers/oauth.py`
para gerar `access_token_enc`/`refresh_token_enc`.

Este modulo existe para centralizar essa derivacao de chave. Antes dele,
`oauth.py` (`_get_fernet`) e `agents/publisher/runner.py` (`_decrypt_token`)
implementavam a derivacao de formas DIFERENTES:

  - oauth.py:  Fernet(base64.urlsafe_b64encode(sha256(secret_key).digest()))
  - runner.py: Fernet(secret_key.encode())   # <- normalmente NAO e uma chave
                                              #    Fernet valida (nao tem 32
                                              #    bytes base64-urlsafe), entao
                                              #    Fernet() levantava
                                              #    ValueError e o runner caia
                                              #    num fallback de "dev" que
                                              #    devolvia o proprio texto
                                              #    cifrado como se fosse
                                              #    plaintext.

Ou seja: tokens reais gravados pelo fluxo OAuth NUNCA eram descriptografados
corretamente no Publisher — qualquer chamada real a uma API de plataforma
social receberia lixo no lugar do access_token. Esse modulo corrige isso:
todo encrypt/decrypt de token na aplicacao deve passar por aqui.
"""

from __future__ import annotations

import base64
import hashlib
import logging

from cryptography.fernet import Fernet, InvalidToken

from viraxis.config import settings

logger = logging.getLogger(__name__)


def get_fernet() -> Fernet:
    """Deriva a chave Fernet (32 bytes urlsafe-base64) a partir de SECRET_KEY."""
    key_bytes = hashlib.sha256(settings.secret_key.encode()).digest()
    return Fernet(base64.urlsafe_b64encode(key_bytes))


def encrypt_token(token: str) -> str:
    """Criptografa um token em texto plano. Retorna um Fernet token (str)."""
    if not token:
        raise ValueError("encrypt_token: token vazio")
    return get_fernet().encrypt(token.encode()).decode()


def decrypt_token(token_enc: str | None) -> str | None:
    """Descriptografa um token Fernet armazenado em SocialAccount.

    Retorna None se `token_enc` for None/vazio ou se a descriptografia
    falhar (chave incorreta, token corrompido, SECRET_KEY divergente entre
    ambientes, etc). Diferente da implementacao antiga do runner, NAO cai
    em um fallback que trata o texto cifrado como plaintext — um token que
    nao descriptografa corretamente jamais deve ser usado para autenticar
    contra uma API externa.
    """
    if not token_enc:
        return None
    try:
        return get_fernet().decrypt(token_enc.encode()).decode()
    except (InvalidToken, ValueError, TypeError) as exc:
        logger.error("token_crypto: falha ao descriptografar token Fernet: %s", exc)
        return None
