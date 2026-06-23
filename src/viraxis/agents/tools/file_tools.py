"""
Ferramentas de arquivo para os agentes Kevin e Davi.

Todas as ferramentas são sandboxed dentro do VIRAXIS_PROJECT_ROOT definido em .env.
Caminhos são sempre relativos à raiz do projeto — os agentes nunca precisam saber
o caminho absoluto do sistema operacional do usuário.
"""

import os
import re
from pathlib import Path
from typing import Optional, Type

from crewai.tools import BaseTool
from pydantic import BaseModel, Field

# ---------------------------------------------------------------------------
# Raiz do projeto — configurável via env para Windows / Linux / CI
# ---------------------------------------------------------------------------

def _project_root() -> Path:
    root = os.environ.get("VIRAXIS_PROJECT_ROOT")
    if root is None:
        # Fallback: sobe até a raiz do repo (5 níveis acima de file_tools.py)
        root = str(Path(__file__).resolve().parents[4])
    return Path(root)


def _safe_path(relative: str) -> Path:
    """
    Resolve um caminho relativo dentro do projeto.
    Bloqueia path traversal (../../etc).
    """
    root = _project_root()
    # Normaliza separadores do Windows
    relative = relative.replace("\\", "/").lstrip("/")
    resolved = (root / relative).resolve()
    if not str(resolved).startswith(str(root.resolve())):
        raise ValueError(f"Caminho fora do projeto: {relative}")
    return resolved


# ---------------------------------------------------------------------------
# ReadFileTool
# ---------------------------------------------------------------------------

class ReadFileInput(BaseModel):
    path: str = Field(
        description=(
            "Caminho relativo do arquivo dentro do projeto VIRAXIS. "
            "Exemplos: 'viraxis_db/src/viraxis/api/routers/offices.py' "
            "ou 'viraxis_web/src/app/dashboard/page.tsx'"
        )
    )
    start_line: Optional[int] = Field(default=None, description="Linha inicial (1-indexed). Lê tudo se None.")
    end_line: Optional[int] = Field(default=None, description="Linha final (inclusiva). Lê até o fim se None.")


class ReadFileTool(BaseTool):
    name: str = "read_file"
    description: str = (
        "Lê o conteúdo de qualquer arquivo do projeto VIRAXIS. "
        "Use para inspecionar routers, models, configs, páginas Next.js e qualquer outro arquivo. "
        "Suporta leitura parcial via start_line/end_line para arquivos grandes."
    )
    args_schema: Type[BaseModel] = ReadFileInput

    def _run(self, path: str, start_line: Optional[int] = None, end_line: Optional[int] = None) -> str:
        try:
            file_path = _safe_path(path)
            if not file_path.exists():
                return f"[ERRO] Arquivo não encontrado: {path}"
            if not file_path.is_file():
                return f"[ERRO] '{path}' não é um arquivo (é um diretório?)"

            content = file_path.read_text(encoding="utf-8", errors="replace")
            lines = content.splitlines()

            if start_line or end_line:
                s = (start_line or 1) - 1
                e = end_line or len(lines)
                lines = lines[s:e]
                content = "\n".join(f"{s+i+1:4d} | {ln}" for i, ln in enumerate(lines))
                return f"# {path} (linhas {s+1}–{s+len(lines)})\n\n{content}"

            # Mostra com números de linha
            numbered = "\n".join(f"{i+1:4d} | {ln}" for i, ln in enumerate(lines))
            return f"# {path} ({len(lines)} linhas)\n\n{numbered}"
        except ValueError as e:
            return f"[ERRO de segurança] {e}"
        except Exception as e:
            return f"[ERRO] {e}"


# ---------------------------------------------------------------------------
# WriteFileTool
# ---------------------------------------------------------------------------

class WriteFileInput(BaseModel):
    path: str = Field(
        description=(
            "Caminho relativo do arquivo a criar/sobrescrever dentro do projeto VIRAXIS. "
            "Exemplo: 'viraxis_db/src/viraxis/api/routers/scout.py'"
        )
    )
    content: str = Field(description="Conteúdo completo a escrever no arquivo.")
    create_dirs: bool = Field(default=True, description="Cria diretórios intermediários se não existirem.")


class WriteFileTool(BaseTool):
    name: str = "write_file"
    description: str = (
        "Cria ou sobrescreve um arquivo no projeto VIRAXIS. "
        "Use para implementar novos routers, models, agentes, páginas Next.js, testes, etc. "
        "Sempre escreve o conteúdo COMPLETO do arquivo — não faz append parcial."
    )
    args_schema: Type[BaseModel] = WriteFileInput

    def _run(self, path: str, content: str, create_dirs: bool = True) -> str:
        try:
            file_path = _safe_path(path)
            if create_dirs:
                file_path.parent.mkdir(parents=True, exist_ok=True)
            file_path.write_text(content, encoding="utf-8")
            lines = content.count("\n") + 1
            return f"[OK] Arquivo escrito: {path} ({lines} linhas)"
        except ValueError as e:
            return f"[ERRO de segurança] {e}"
        except Exception as e:
            return f"[ERRO] {e}"


# ---------------------------------------------------------------------------
# ListDirectoryTool
# ---------------------------------------------------------------------------

class ListDirInput(BaseModel):
    path: str = Field(
        default="",
        description=(
            "Caminho relativo do diretório a listar. "
            "String vazia lista a raiz do projeto. "
            "Exemplo: 'viraxis_db/src/viraxis/api'"
        )
    )
    recursive: bool = Field(default=False, description="Se True, lista recursivamente todos os arquivos.")
    extensions: Optional[list[str]] = Field(
        default=None,
        description="Filtrar por extensões. Ex: ['.py', '.ts']. None = todos."
    )


class ListDirectoryTool(BaseTool):
    name: str = "list_directory"
    description: str = (
        "Lista arquivos e diretórios do projeto VIRAXIS. "
        "Use para entender a estrutura do projeto antes de criar ou editar arquivos. "
        "Suporta filtro por extensão e listagem recursiva."
    )
    args_schema: Type[BaseModel] = ListDirInput

    def _run(
        self,
        path: str = "",
        recursive: bool = False,
        extensions: Optional[list[str]] = None,
    ) -> str:
        try:
            dir_path = _safe_path(path) if path else _project_root()
            if not dir_path.exists():
                return f"[ERRO] Diretório não encontrado: {path or '(raiz)'}"
            if not dir_path.is_dir():
                return f"[ERRO] '{path}' não é um diretório"

            if recursive:
                entries = sorted(dir_path.rglob("*"))
            else:
                entries = sorted(dir_path.iterdir())

            # Filtra __pycache__ e .git
            entries = [
                e for e in entries
                if "__pycache__" not in str(e) and ".git" not in str(e) and ".next" not in str(e)
            ]

            if extensions:
                ext_set = {ext.lower() if ext.startswith(".") else f".{ext.lower()}" for ext in extensions}
                entries = [e for e in entries if e.is_file() and e.suffix.lower() in ext_set]

            root = _project_root()
            lines = []
            for entry in entries:
                rel = entry.relative_to(root)
                marker = "📁 " if entry.is_dir() else "📄 "
                lines.append(f"{marker}{rel}")

            if not lines:
                return f"[VAZIO] Nenhum arquivo encontrado em: {path or '(raiz)'}"

            header = f"# Listagem: {path or '(raiz do projeto)'} ({len(lines)} entradas)\n\n"
            return header + "\n".join(lines)
        except ValueError as e:
            return f"[ERRO de segurança] {e}"
        except Exception as e:
            return f"[ERRO] {e}"


# ---------------------------------------------------------------------------
# SearchCodeTool
# ---------------------------------------------------------------------------

class SearchCodeInput(BaseModel):
    pattern: str = Field(description="Padrão de busca (string simples ou regex Python).")
    path: str = Field(
        default="",
        description="Diretório/arquivo onde buscar. String vazia = projeto inteiro."
    )
    extensions: Optional[list[str]] = Field(
        default=[".py", ".ts", ".tsx"],
        description="Extensões a incluir na busca."
    )
    max_results: int = Field(default=40, description="Número máximo de linhas de resultado.")


class SearchCodeTool(BaseTool):
    name: str = "search_code"
    description: str = (
        "Busca por um padrão (texto ou regex) em todos os arquivos do projeto. "
        "Use para encontrar onde uma função é definida, onde um model é importado, "
        "quais endpoints existem, qual padrão de código está sendo usado. "
        "Retorna arquivo + número de linha + trecho da linha."
    )
    args_schema: Type[BaseModel] = SearchCodeInput

    def _run(
        self,
        pattern: str,
        path: str = "",
        extensions: Optional[list[str]] = None,
        max_results: int = 40,
    ) -> str:
        try:
            base = _safe_path(path) if path else _project_root()
            ext_set = None
            if extensions:
                ext_set = {e.lower() if e.startswith(".") else f".{e.lower()}" for e in extensions}

            try:
                regex = re.compile(pattern, re.IGNORECASE)
            except re.error:
                regex = re.compile(re.escape(pattern), re.IGNORECASE)

            results = []
            files = base.rglob("*") if base.is_dir() else [base]
            root = _project_root()

            for file_path in sorted(files):
                if not file_path.is_file():
                    continue
                if "__pycache__" in str(file_path) or ".git" in str(file_path) or ".next" in str(file_path):
                    continue
                if ext_set and file_path.suffix.lower() not in ext_set:
                    continue
                try:
                    text = file_path.read_text(encoding="utf-8", errors="replace")
                    for i, line in enumerate(text.splitlines(), 1):
                        if regex.search(line):
                            rel = file_path.relative_to(root)
                            results.append(f"{rel}:{i}: {line.strip()}")
                            if len(results) >= max_results:
                                break
                except Exception:
                    continue
                if len(results) >= max_results:
                    break

            if not results:
                return f"[SEM RESULTADOS] Padrão '{pattern}' não encontrado."

            header = f"# Resultados para '{pattern}' ({len(results)} ocorrências)\n\n"
            return header + "\n".join(results)
        except ValueError as e:
            return f"[ERRO de segurança] {e}"
        except Exception as e:
            return f"[ERRO] {e}"
