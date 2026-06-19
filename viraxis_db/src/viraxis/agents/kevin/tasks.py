"""Tasks do agente Kevin — análise e especificação técnica."""

from crewai import Agent, Task


def create_architecture_review_task(agent: Agent, dev_task: str) -> Task:
    """
    Kevin analisa o codebase e cria uma spec técnica para a tarefa solicitada.

    Args:
        agent: O agente Kevin.
        dev_task: Descrição da tarefa de desenvolvimento em linguagem natural.
    """
    return Task(
        description=f"""
Você recebeu a seguinte tarefa de desenvolvimento para o sistema VIRAXIS:

=== TAREFA ===
{dev_task}
==============

Siga este processo rigoroso:

**PASSO 1 — Explorar a estrutura do projeto**
Use list_directory para mapear:
- viraxis_db/src/viraxis/api/routers/ (quais routers existem)
- viraxis_db/src/viraxis/domain/models/ (quais models existem)
- viraxis_db/src/viraxis/agents/ (estrutura de agentes)
- viraxis_web/src/app/ (estrutura do frontend)

**PASSO 2 — Ler arquivos relevantes**
Use read_file nos arquivos que serão afetados ou que fornecem contexto.
Leia pelo menos:
- O router mais próximo da tarefa (ex: offices.py se a tarefa é sobre offices)
- O model SQLAlchemy relevante
- main.py para entender os routers registrados

**PASSO 3 — Identificar padrões e convenções**
Use search_code para encontrar:
- Como outros endpoints similares são implementados
- Padrões de importação, nomenclatura de funções e schemas
- Como `Depends(get_current_user)` e `Depends(get_session)` são usados

**PASSO 4 — Criar a especificação técnica**
Com base no que você leu, crie uma spec DETALHADA que inclua:
- Arquivo(s) a criar ou modificar (caminhos relativos exatos)
- Imports necessários
- Esquema Pydantic de entrada/saída (se for endpoint)
- Lógica de negócio passo a passo
- Casos de borda a tratar
- Testes a cobrir

Seja específico. Davi vai implementar exatamente o que você especificar.
""".strip(),
        expected_output=(
            "Uma especificação técnica estruturada em Markdown com seções: "
            "## Contexto (o que foi lido), "
            "## Arquivos a modificar/criar, "
            "## Implementação (código Python/TypeScript a escrever), "
            "## Casos de borda, "
            "## Como testar. "
            "A spec deve ser completa e não ambígua."
        ),
        agent=agent,
    )


def create_review_task(agent: Agent, implementation_summary: str) -> Task:
    """
    Kevin revisa o que Davi implementou, valida sintaxe e coerência arquitetural.
    """
    return Task(
        description=f"""
Davi acabou de implementar a seguinte solução:

{implementation_summary}

Faça uma revisão técnica:
1. Use read_file para ler os arquivos que Davi criou/modificou
2. Use validate_python em todo código Python novo
3. Use search_code para verificar se não há imports quebrados ou duplicações
4. Verifique se os padrões do projeto foram seguidos (nomes, estrutura, auth guards)
5. Identifique vulnerabilidades óbvias (falta de auth, injection, etc.)

Produza um relatório de revisão com: ✅ aprovados, ⚠️ avisos, ❌ problemas.
""".strip(),
        expected_output=(
            "Relatório de revisão com: status geral (APROVADO/REPROVADO), "
            "lista de verificações ✅/⚠️/❌, "
            "problemas encontrados com localização exata, "
            "e recomendações de melhoria."
        ),
        agent=agent,
    )
