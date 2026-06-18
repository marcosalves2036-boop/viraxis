#!/bin/bash
# ============================================================
# setup_vm.sh — Setup do servidor VIRAXIS (Ubuntu 22.04 ARM)
# Oracle Cloud Free Tier | Ampere A1 Flex
#
# Uso:
#   curl -sSL https://raw.githubusercontent.com/SEU_USER/viraxis_db/main/setup_vm.sh | bash
#
# O que faz:
#   1. Instala Docker + Docker Compose
#   2. Adiciona usuario atual ao grupo docker
#   3. Clona o repositorio
#   4. Configura .env a partir do .env.example
#   5. Sobe os servicos
# ============================================================

set -euo pipefail

REPO_URL="${REPO_URL:-https://github.com/SEU_USER/viraxis_db.git}"
APP_DIR="/opt/viraxis"
DEPLOY_USER="${DEPLOY_USER:-ubuntu}"

echo "======================================================"
echo "  VIRAXIS — Setup do Servidor"
echo "======================================================"

# ── 1. Atualizar sistema ──────────────────────────────────
echo "[1/6] Atualizando sistema..."
sudo apt-get update -qq
sudo apt-get upgrade -y -qq
sudo apt-get install -y -qq git curl ufw

# ── 2. Instalar Docker ────────────────────────────────────
echo "[2/6] Instalando Docker..."
if ! command -v docker &>/dev/null; then
    curl -fsSL https://get.docker.com | sudo sh
fi
sudo usermod -aG docker "$DEPLOY_USER"

# Docker Compose v2
if ! docker compose version &>/dev/null; then
    sudo apt-get install -y -qq docker-compose-plugin
fi

echo "Docker: $(docker --version)"
echo "Docker Compose: $(docker compose version)"

# ── 3. Firewall ───────────────────────────────────────────
echo "[3/6] Configurando firewall..."
sudo ufw default deny incoming
sudo ufw default allow outgoing
sudo ufw allow ssh
sudo ufw allow 8000/tcp   # API
sudo ufw allow 80/tcp     # HTTP (para nginx futuro)
sudo ufw allow 443/tcp    # HTTPS
sudo ufw --force enable
echo "Firewall configurado."

# ── 4. Clonar repositório ─────────────────────────────────
echo "[4/6] Clonando repositorio..."
sudo mkdir -p "$APP_DIR"
sudo chown "$DEPLOY_USER:$DEPLOY_USER" "$APP_DIR"

if [ -d "$APP_DIR/.git" ]; then
    echo "Repositorio ja existe. Fazendo pull..."
    cd "$APP_DIR" && git pull
else
    git clone "$REPO_URL" "$APP_DIR"
    cd "$APP_DIR"
fi

# ── 5. Configurar .env ────────────────────────────────────
echo "[5/6] Configurando .env..."
if [ ! -f "$APP_DIR/.env" ]; then
    cp "$APP_DIR/.env.example" "$APP_DIR/.env"
    # Gerar SECRET_KEY automaticamente
    SECRET=$(python3 -c "import secrets; print(secrets.token_hex(32))")
    sed -i "s/TROQUE_AQUI_string_aleatoria_64_chars/$SECRET/" "$APP_DIR/.env"
    echo ""
    echo "======================================================="
    echo "  ATENCAO: Edite o .env antes de subir os servicos!"
    echo "  nano $APP_DIR/.env"
    echo "  Campos obrigatorios:"
    echo "  - POSTGRES_PASSWORD"
    echo "  - LLM_API_KEY"
    echo "======================================================="
    echo ""
else
    echo ".env ja existe, mantendo."
fi

# ── 6. Build e start ──────────────────────────────────────
echo "[6/6] Fazendo build dos servicos..."
cd "$APP_DIR"
# Build sem subir (usuario precisa configurar .env primeiro)
docker compose build

echo ""
echo "======================================================"
echo "  Setup concluido!"
echo ""
echo "  Proximos passos:"
echo "  1. cd $APP_DIR"
echo "  2. nano .env          # preencha as variaveis"
echo "  3. docker compose up -d"
echo "  4. docker compose logs -f api"
echo ""
echo "  API estara em: http://IP_DA_VM:8000"
echo "  Docs:          http://IP_DA_VM:8000/docs"
echo "======================================================"
