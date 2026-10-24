"""Origem IA: Geração Exploratória (P3) e Análise de Lacunas (P3b) - SPEC-03 §3.1.

P3 é a **única** chamada do sistema com temperatura alta. É ali que a
imprevisibilidade é permitida, e ela é contida logo depois: o texto gerado entra
no mesmo funil de qualquer outra proposta e pode ser descartado por ele
(SPEC-00 §4).
"""

from __future__ import annotations

import logging

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.common import prompts
from app.common.config import settings
from app.common.llm_client import chat as llm_chat
from app.task_layer.models import (
    REASON_INCOERENTE,
    REASON_RECUSA_HUMANA,
    DiscardedProposal,
    ImplementedItem,
    Proposal,
)

logger = logging.getLogger("pase.task_layer")

TEMPERATURA_EXPLORATORIA = 0.9  # SPEC-01 §4: único ponto quente do sistema
TEMPERATURA_ANALITICA = 0.2  # lacunas é análise, não brainstorm

SCHEMA_TEXTO = {
    "type": "object",
    "properties": {"text": {"type": ["string", "null"]}},
    "required": ["text"],
}

GO = {"role": "user", "content": "Produza agora o objeto JSON pedido."}


#: Quantos itens de cada lista vão ao P3 e ao P3b. São as linhas **mais recentes**:
#: com o baseline primeiro, um teto pelos ids mais antigos deixaria de fora justamente
#: o que o sistema acabou de entregar ou recusar.
LIMITE_DE_ITENS = 40

#: Descartes que dizem algo sobre o escopo. Duplicata não entra: é repetição, não juízo.
TIPOS_DE_DESCARTE = (REASON_INCOERENTE, REASON_RECUSA_HUMANA)


def _implementadas(session: Session, limite: int = LIMITE_DE_ITENS) -> str:
    itens = session.execute(
        select(ImplementedItem).order_by(ImplementedItem.id.desc()).limit(limite)
    ).scalars().all()
    if not itens:
        return "(nada implementado ainda)"
    return "\n".join(f"- {item.title}: {item.description}" for item in itens)


def _descartadas(session: Session, limite: int = LIMITE_DE_ITENS) -> str:
    linhas = session.execute(
        select(DiscardedProposal, Proposal.title)
        .outerjoin(Proposal, Proposal.id == DiscardedProposal.proposal_id)
        .where(DiscardedProposal.reason_type.in_(TIPOS_DE_DESCARTE))
        .order_by(DiscardedProposal.id.desc())
        .limit(limite)
    ).all()
    if not linhas:
        return "(nada descartado ainda)"
    return "\n".join(
        f"- {titulo or '(sem título)'}: {descarte.reason_text}" for descarte, titulo in linhas
    )


def gerar_exploratoria(session: Session) -> str | None:
    """P3 - propõe uma melhoria nova, com temperatura alta."""
    content, usage = llm_chat(
        [
            prompts.system_message(
                "P3",
                project_context=prompts.load_project_context(),
                implemented=_implementadas(session),
                discarded=_descartadas(session),
            ),
            GO,
        ],
        json_schema=SCHEMA_TEXTO,
        temperature=TEMPERATURA_EXPLORATORIA,
        model=settings.llm_model_exploratory,
        tags={"prompt_id": "P3", "fase": "geracao_exploratoria"},
    )
    logger.info("P3 gerou proposta (trace=%s)", usage["trace_id"])
    return content.get("text")


def gerar_lacunas(session: Session) -> str | None:
    """P3b - cruza módulos implementados procurando uma integração ausente."""
    content, usage = llm_chat(
        [
            prompts.system_message(
                "P3b",
                project_context=prompts.load_project_context(),
                implemented=_implementadas(session),
                discarded=_descartadas(session),
            ),
            GO,
        ],
        json_schema=SCHEMA_TEXTO,
        temperature=TEMPERATURA_ANALITICA,
        tags={"prompt_id": "P3b", "fase": "analise_lacunas"},
    )
    logger.info("P3b analisou lacunas (trace=%s)", usage["trace_id"])
    return content.get("text")
