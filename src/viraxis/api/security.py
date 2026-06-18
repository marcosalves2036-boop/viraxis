"""Utilitarios de seguranca: hash de senha + JWT."""

from datetime import datetime, timedelta, timezone

import bcrypt
from jose import JWTError, jwt

from viraxis.config import settings


def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def verify_password(plain: str, hashed: str) -> bool:
    return bcrypt.checkpw(plain.encode("utf-8"), hashed.encode("utf-8"))


def create_access_token(subject: str, expires_delta: timedelta | None = None) -> str:
    expire = datetime.now(timezone.utc) + (
        expires_delta or timedelta(minutes=settings.jwt_expire_minutes)
    )
    return jwt.encode(
        {"sub": subject, "exp": expire},
        settings.secret_key,
        algorithm=settings.jwt_algorithm,
    )


def decode_token(token: str) -> str:
    """Retorna o subject (user_id) ou lanca JWTError."""
    payload = jwt.decode(token, settings.secret_key, algorithms=[settings.jwt_algorithm])
    sub: str | None = payload.get("sub")
    if sub is None:
        raise JWTError("Token sem subject")
    return sub
