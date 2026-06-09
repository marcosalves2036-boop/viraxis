.PHONY: help install up down logs test lint fmt db-upgrade db-downgrade db-reset

# Detecta o Python correto no Windows/Unix
PYTHON := python
PIP := pip

help: ## Mostra esta ajuda
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | sort | awk 'BEGIN {FS = ":.*?## "}; {printf "\033[36m%-20s\033[0m %s\n", $$1, $$2}'

# ── Setup ──────────────────────────────────────────────────────────
install: ## Instala dependências e o projeto em modo editable
	$(PIP) install -e ".[dev]"

env: ## Cria o .env a partir do .env.example (não sobrescreve)
	@if not exist .env (copy .env.example .env && echo .env criado. Edite e preencha as variaveis.) else (echo .env ja existe.)

# ── Docker ─────────────────────────────────────────────────────────
up: ## Sobe Postgres + Redis em background
	docker compose up -d
	@echo Aguardando servicos...
	docker compose ps

down: ## Para e remove os containers (dados persistem nos volumes)
	docker compose down

down-v: ## Para containers E remove volumes (reseta o banco)
	docker compose down -v

logs: ## Mostra logs dos containers
	docker compose logs -f

# ── Banco de dados ──────────────────────────────────────────────────
db-upgrade: ## Aplica todas as migrations pendentes
	alembic upgrade head

db-downgrade: ## Reverte a última migration
	alembic downgrade -1

db-reset: down-v up ## Reseta o banco completamente e reaplica migrations
	@echo Aguardando Postgres subir...
	docker compose exec postgres pg_isready -U viraxis
	alembic upgrade head

db-history: ## Mostra histórico de migrations
	alembic history --verbose

# ── Testes ──────────────────────────────────────────────────────────
test: ## Roda todos os testes
	pytest tests/ -v

test-unit: ## Roda apenas testes unitários
	pytest tests/unit/ -v

test-cov: ## Roda testes com cobertura
	pytest tests/ -v --cov=src/viraxis --cov-report=term-missing

# ── Qualidade de código ─────────────────────────────────────────────
lint: ## Verifica estilo com ruff
	ruff check src/ tests/

fmt: ## Formata código com ruff
	ruff format src/ tests/
	ruff check --fix src/ tests/

# ── CLI ─────────────────────────────────────────────────────────────
info: ## Mostra info do projeto via CLI
	viraxis info

db-check: ## Verifica conexão com o banco via CLI
	viraxis db check
