#!/usr/bin/env bash
# ─────────────────────────────────────────────────────────────────────────────
# post-create.sh — Roda uma vez ao criar o Codespace
# ─────────────────────────────────────────────────────────────────────────────
set -e

echo ""
echo "╔══════════════════════════════════════════╗"
echo "║     VIRAXIS — configurando ambiente       ║"
echo "╚══════════════════════════════════════════╝"
echo ""

# ── 1. Instalar dependencias Python ──────────────────────────────────────────
echo "▸ Instalando dependencias..."
cd /workspaces/viraxis_db
pip install --quiet -e ".[dev]" 2>/dev/null || pip install --quiet -e .

# ── 2. Criar .env se nao existir ─────────────────────────────────────────────
if [ ! -f .env ]; then
  cp .env.example .env

  # Gerar SECRET_KEY automaticamente
  SECRET=$(python3 -c "import secrets; print(secrets.token_hex(32))")
  sed -i "s/TROQUE_AQUI_string_aleatoria_64_chars/$SECRET/" .env

  # No Codespace a API roda diretamente (fora do docker), entao Postgres e localhost
  sed -i "s/^POSTGRES_HOST=postgres/POSTGRES_HOST=localhost/" .env
  sed -i "s/^POSTGRES_PASSWORD=TROQUE_AQUI_senha_forte_32_chars/POSTGRES_PASSWORD=viraxis_dev/" .env

  echo "▸ .env criado com SECRET_KEY gerado automaticamente"
  echo "  ⚠ Edite .env e adicione suas chaves de API (LLM, Stripe, etc.)"
else
  echo "▸ .env ja existe — mantendo"
fi

# ── 3. Subir infraestrutura (Postgres + Redis) via Docker Compose ─────────────
echo "▸ Subindo Postgres e Redis..."
docker compose up -d postgres redis

# Aguardar Postgres ficar saudavel
echo "▸ Aguardando Postgres..."
for i in $(seq 1 30); do
  if docker compose exec -T postgres pg_isready -U viraxis -q 2>/dev/null; then
    echo "  ✓ Postgres pronto!"
    break
  fi
  sleep 2
done

# ── 4. Rodar migrations Alembic ───────────────────────────────────────────────
echo "▸ Rodando migrations..."
DATABASE_URL=$(grep "^DATABASE_URL=" .env | cut -d= -f2-)
if [ -z "$DATABASE_URL" ]; then
  # Montar URL a partir das variaveis separadas
  PGUSER=$(grep "^POSTGRES_USER=" .env | cut -d= -f2-)
  PGPASS=$(grep "^POSTGRES_PASSWORD=" .env | cut -d= -f2-)
  PGDB=$(grep "^POSTGRES_DB=" .env | cut -d= -f2-)
  DATABASE_URL="postgresql+asyncpg://${PGUSER}:${PGPASS}@localhost:5432/${PGDB}"
fi

export PYTHONPATH=/workspaces/viraxis_db/src
alembic upgrade head && echo "  ✓ Migrations aplicadas!" || echo "  ⚠ Erro nas migrations — verifique o .env"

# ── 5. Aliases uteis ──────────────────────────────────────────────────────────
cat >> ~/.bashrc << 'ALIASES'

# VIRAXIS aliases
alias vx-up='docker compose up -d && uvicorn viraxis.api.main:app --reload --host 0.0.0.0 --port 8000'
alias vx-api='cd /workspaces/viraxis_db && PYTHONPATH=src uvicorn viraxis.api.main:app --reload --host 0.0.0.0 --port 8000'
alias vx-worker='cd /workspaces/viraxis_db && PYTHONPATH=src celery -A viraxis.worker.celery_app worker -Q viraxis -l info -c 2'
alias vx-logs='docker compose logs -f'
alias vx-db='docker compose exec postgres psql -U viraxis viraxis'
alias vx-migrate='cd /workspaces/viraxis_db && PYTHONPATH=src alembic upgrade head'
ALIASES

echo ""
echo "╔══════════════════════════════════════════╗"
echo "║            Setup concluido!              ║"
echo "╠══════════════════════════════════════════╣"
echo "║  Comandos rapidos:                        ║"
echo "║   vx-api     → inicia o servidor API     ║"
echo "║   vx-worker  → inicia o Celery worker    ║"
echo "║   vx-db      → abre o psql               ║"
echo "║   vx-migrate → roda as migrations        ║"
echo "╠══════════════════════════════════════════╣"
echo "║  Docs: http://localhost:8000/docs         ║"
echo "╚══════════════════════════════════════════╝"
echo ""
echo "  ⚠ Proximos passos:"
echo "     1. Edite .env e cole sua chave LLM (Groq ou OpenAI)"
echo "     2. Execute: vx-api"
echo "     3. Acesse: http://localhost:8000/docs"
echo ""
