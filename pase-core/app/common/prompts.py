"""Carregamento dos prompts versionados (`app/prompts/`).

Convenção do README.md: um arquivo `.md` por prompt, nunca texto inline no
código Python. Assim o prompt entra no `git log` como qualquer outro artefato -
é possível ligar uma decisão do sistema à versão exata do prompt que a produziu.

Interpolação usa `{{variavel}}`, e não `str.format`: os prompts contêm exemplos
de JSON com chaves `{}`, que quebrariam o format.
"""

from __future__ import annotations

import logging
import re
from functools import cache
from pathlib import Path
from typing import Any

logger = logging.getLogger("pase.prompts")

PROMPTS_DIR = Path(__file__).resolve().parent.parent / "prompts"

PLACEHOLDER = re.compile(r"\{\{\s*(\w+)\s*\}\}")


class PromptError(RuntimeError):
    pass


@cache
def _read(prompt_id: str) -> str:
    path = PROMPTS_DIR / f"{prompt_id}.md"
    if not path.exists():
        raise PromptError(f"prompt não encontrado: {path}")
    return path.read_text(encoding="utf-8")


def available() -> list[str]:
    return sorted(p.stem for p in PROMPTS_DIR.glob("*.md"))


def render(prompt_id: str, **variables: Any) -> str:
    """Devolve o prompt com as variáveis substituídas.

    Levanta se sobrar algum `{{placeholder}}` sem valor - um prompt incompleto
    chegando ao modelo é bug silencioso caro.
    """
    text = _read(prompt_id)

    def substituir(match: re.Match[str]) -> str:
        nome = match.group(1)
        if nome not in variables:
            raise PromptError(f"{prompt_id}: falta a variável '{nome}'")
        valor = variables[nome]
        return "" if valor is None else str(valor)

    rendered = PLACEHOLDER.sub(substituir, text)

    sobrando = PLACEHOLDER.findall(rendered)
    if sobrando:
        raise PromptError(f"{prompt_id}: placeholders não resolvidos: {sobrando}")
    return rendered


def system_message(prompt_id: str, **variables: Any) -> dict[str, str]:
    return {"role": "system", "content": render(prompt_id, **variables)}


def load_documentacao(etapa: str) -> str:
    """Os documentos de contexto que esta etapa do ciclo lê (`context_store.LEITURAS`).

    Vêm do banco, não de arquivo: editar no painel vale na próxima chamada.
    """
    from app.common import context_store

    try:
        return context_store.contexto(etapa)
    except context_store.ContextoError as exc:
        raise PromptError(str(exc)) from exc


def load_project_context() -> str:
    """O contexto que a etapa de filtragem do funil lê: escopo, requisitos, funcionalidades.

    É insumo obrigatório da Coerência Sistêmica (SPEC-03 P2a): sem o documento do
    produto não há contra o que julgar, e seguir sem ele aprovaria qualquer coisa.
    """
    return load_documentacao("funil")
