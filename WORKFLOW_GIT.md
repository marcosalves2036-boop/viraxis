# Workflow de Git — Viraxis (para Claude no Cowork)

## Contexto importante

O Claude no Cowork tem dois ambientes separados:

- **File tools (Read/Write/Edit)** → acessam arquivos na pasta local do computador
- **Bash** → roda em sandbox Linux isolado que **reseta a cada sessão**

Por isso, a cada sessão nova o processo começa do zero.

---

## Passo a passo completo a cada sessão

### 1. Clonar o repo no sandbox
```bash
cd /tmp && git clone https://[PAT]@github.com/marcosalves2036-boop/viraxis.git
cd /tmp/viraxis
```
> O PAT está no arquivo `reference_all_credentials.md` — pedir ao Marcos.

### 2. Fazer as alterações nos arquivos
O Claude edita diretamente em `/tmp/viraxis/` via bash.

### 3. Commitar
```bash
cd /tmp/viraxis
git add -A
git -c user.email="arthur100bigode@gmail.com" -c user.name="Arthur" commit -m "tipo: descrição"
```

Padrão de mensagens:
- `fix:` — correção de bug
- `feat:` — nova funcionalidade
- `refactor:` — refatoração sem mudança de comportamento
- `chore:` — manutenção, configs

### 4. Push
```bash
git push origin main
```

### 5. Deploy após push

**Backend** (`src/` alterado) — Render tem auto-deploy DESATIVADO, disparar manualmente:
```bash
curl -X POST https://api.render.com/v1/services/srv-d8q80vjeo5us73emavt0/deploys \
  -H "Authorization: Bearer [RENDER_API_KEY]" \
  -H "Content-Type: application/json" -d '{}'
```

**Frontend** (`viraxis_db/frontend/` alterado) — Vercel detecta o push e deploya automaticamente. Nada a fazer.

---

## Qual pasta editar — CRÍTICO

O repo tem código duplicado. Editar a pasta errada não tem efeito em produção:

| Em produção | Pasta correta |
|-------------|--------------|
| Backend (Render) | `src/viraxis/` |
| Frontend (Vercel) | `viraxis_db/frontend/` |
| ❌ Ignorar sempre | `viraxis_db/src/` e `frontend/` (raiz) |

---

## Resumo em uma linha

> A cada sessão: clone → edita em `/tmp/viraxis/` → commit → push → se mudou backend, dispara deploy no Render via curl.
