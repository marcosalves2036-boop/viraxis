"""Base declarativa SQLAlchemy com naming convention para Alembic estável."""

from sqlalchemy import MetaData
from sqlalchemy.orm import DeclarativeBase

# Naming convention: Alembic gera nomes determinísticos para FKs/UQs/IXs/CKs
# Evita `None` no downgrade e diffs instáveis entre ambientes
NAMING_CONVENTION: dict[str, str] = {
    "ix": "ix_%(table_name)s_%(column_0_label)s",
    "uq": "uq_%(table_name)s_%(column_0_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}


class Base(DeclarativeBase):
    metadata = MetaData(naming_convention=NAMING_CONVENTION)


# Importar todos os models aqui garante que Base.metadata os registre
# antes que o Alembic faça autogenerate
def _register_models() -> None:
    """Lazy import para evitar circular imports."""
    import viraxis.domain.models  # noqa: F401


_register_models()
