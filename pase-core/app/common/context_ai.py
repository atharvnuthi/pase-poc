"""P11: a IA propõe uma versão nova de um documento de contexto. Nunca grava.

Usado pela tela Contexto (a pessoa pede uma mudança) e pelas sugestões que nascem de uma
tarefa aprovada. Nos dois casos a regra é a mesma: o modelo devolve um texto e um diff, e
**uma pessoa decide**. Deixar o modelo reescrever sozinho o documento que o julga criaria
um sistema validando as próprias decisões contra um texto que ele mesmo mudou.
"""

from __future__ import annotations

import difflib

from app.common import prompts
from app.common.llm_client import chat as llm_chat

SCHEMA_P11 = {
    "type": "object",
    "properties": {
        "aplicavel": {"type": "boolean"},
        "reasoning": {"type": "string"},
        "summary": {"type": "string"},
        "content": {"type": "string"},
    },
    "required": ["aplicavel", "reasoning", "summary", "content"],
}


def diff_de(slug: str, antes: str, depois: str) -> str:
    return "".join(
        difflib.unified_diff(
            antes.splitlines(keepends=True),
            depois.splitlines(keepends=True),
            fromfile=f"{slug} (atual)",
            tofile=f"{slug} (proposto)",
        )
    )


def propor(slug: str, atual: str, pedido: str, *, task_id: int | None = None) -> dict:
    """Uma versão do documento com a mudança aplicada, **sem gravar**."""
    tags = {"prompt_id": "P11", "fase": "contexto"}
    if task_id is not None:
        tags["task_id"] = task_id
    conteudo, _ = llm_chat(
        [
            prompts.system_message("P11", contexto_atual=atual, pedido=pedido),
            {"role": "user", "content": "Produza agora o objeto JSON pedido."},
        ],
        json_schema=SCHEMA_P11,
        temperature=0.1,
        tags=tags,
    )

    if not conteudo.get("aplicavel") or not conteudo.get("content", "").strip():
        return {
            "aplicavel": False,
            "reasoning": conteudo.get("reasoning", ""),
            "summary": "",
            "content": "",
            "diff": "",
        }
    proposto = conteudo["content"]
    return {
        "aplicavel": True,
        "reasoning": conteudo.get("reasoning", ""),
        "summary": conteudo.get("summary", ""),
        "content": proposto,
        "diff": diff_de(slug, atual, proposto),
    }
