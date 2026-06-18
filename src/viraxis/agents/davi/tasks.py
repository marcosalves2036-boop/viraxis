"""Tasks do agente Davi — implementação de código."""

from crewai import Agent, Task


def create_implementation_task(agent: Agent, spec: str) -> Task:
    """
    Davi implementa o código conforme a spec do Kevin.

    Args:
        agent: O agente Davi.
        spec: Especificação técnica detalhada criada pelo Kevin.
    """
    return Task(
        description=f"""
Você recebeu a seguinte especificação técnica do Kevin para implementar:

{spec}

Siga este processo sem pular nenhuma etapa:

**PASSO 1 — Entender o contexto**
Leia os arquivos mencionados na spec com read_file.
Se a spec mencionar um padrão a seguir, use search_code para encontrá-lo.

**PASSO 2 — Para cada arquivo Python a criar/modificar:**
a) Escreva o código completo na sua cabeça
b) Use validate_python passando o código como string
c) Se houver erro de sintaxe, corrija e valide novamente
d) Só após validação bem-sucedida, chame write_file

**PASSO 3 — Para arquivos TypeScript/TSX:**
Escreva o arquivo completo e use write_file diretamente.
(Não temos validador TS — escreva com cuidado, seguindo padrões existentes)

**PASSO 4 — Relatório final**
Liste cada arquivo criado/modificado com:
- Caminho relativo exato
- O que foi implementado
- Qualquer limitação ou próximo passo necessário

IMPORTANTE:
- Nunca escreva código parcial ou com TODO comments não resolvidos
- Sempre importe de caminhos que existem no projeto
- Siga as convenções: router.get/post com Depends(get_current_user), schemas Pydantic, etc.
""".strip(),
        expected_output=(
            "Relatório de implementação com: "
            "lista de arquivos criados/modificados (caminhos exatos), "
            "descrição do que cada um faz, "
            "confirmação de que validate_python passou em cada .py, "
            "instruções de como testar o que foi implementado."
        ),
        agent=agent,
    )


def create_fix_task(agent: Agent, issue: str, file_path: str) -> Task:
    """
    Davi corrige um problema específico apontado pelo Kevin na revisão.
    """
    return Task(
        description=f"""
Kevin identificou o seguinte problema que precisa ser corrigido:

PROBLEMA: {issue}
ARQUIVO: {file_path}

Processo:
1. Leia o arquivo atual com read_file
2. Identifique exatamente a linha/trecho problemático
3. Escreva a versão corrigida do arquivo completo
4. Valide com validate_python (se for .py)
5. Escreva com write_file
6. Confirme a correção
""".strip(),
        expected_output=(
            "Confirmação da correção com: arquivo modificado, "
            "descrição exata do que foi mudado, "
            "confirmação de validação de sintaxe."
        ),
        agent=agent,
    )
