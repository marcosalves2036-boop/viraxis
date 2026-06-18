FROM python:3.11-slim

# Sistema
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    libpq-dev \
    ffmpeg \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Copia tudo que o pip precisa ANTES de instalar
COPY pyproject.toml ./
COPY src/ ./src/

# Instala dependências
RUN pip install --no-cache-dir -e .

# Resto dos arquivos
COPY alembic/ ./alembic/
COPY alembic.ini ./

ENV PYTHONPATH=/app/src \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

EXPOSE 8000

# Render injeta $PORT — usamos ele ou 8000 como fallback
CMD ["sh", "-c", "alembic upgrade head && uvicorn viraxis.api.main:app --host 0.0.0.0 --port ${PORT:-8000}"]
