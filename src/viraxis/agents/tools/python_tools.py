"""Ferramentas Python para validação e execução segura de código."""

import ast
import subprocess
import sys
from typing import Type

from crewai.tools import BaseTool
from pydantic import BaseModel, Field


class ValidatePythonInput(BaseModel):
    code: str = Field(description="Código Python a validar sintaticamente.")
    filename: str = Field(default="<code>", description="Nome do arquivo (para mensagens de erro).")


class ValidatePythonTool(BaseTool):
    name: str = "validate_python"
    description: str = (
        "Valida a sintaxe de um trecho de código Python via ast.parse. "
        "Use SEMPRE antes de escrever um arquivo .py para garantir que não há erros de sintaxe. "
        "Retorna 'OK' se válido, ou a mensagem de erro com linha/coluna."
    )
    args_schema: Type[BaseModel] = ValidatePythonInput

    def _run(self, code: str, filename: str = "<code>") -> str:
        # Remove null bytes que corrompem arquivos
        code = code.replace("\x00", "")
        try:
            ast.parse(code, filename=filename)
            lines = code.count("\n") + 1
            return f"[OK] Sintaxe válida — {lines} linhas, sem erros."
        except SyntaxError as e:
            return (
                f"[ERRO DE SINTAXE] {e.msg}\n"
                f"  Arquivo : {filename}\n"
                f"  Linha   : {e.lineno}\n"
                f"  Coluna  : {e.offset}\n"
                f"  Trecho  : {e.text!r}"
            )
        except Exception as e:
            return f"[ERRO] {type(e).__name__}: {e}"
