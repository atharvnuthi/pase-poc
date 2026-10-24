"""Endpoints de ingestão do Task Layer (SPEC-03 §1).

Três das quatro origens têm endpoint. A quarta - Captação Passiva - roda em
background, lendo tickets do FinTrack (`app/jobs/passive_capture.py`).

O funil roda na própria requisição: são segundos, aceitável nesta PoC, e mantém
a resposta síncrona que o modal do FinTrack exibe ao usuário.
"""

import logging

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.common.config import settings
from app.common.db import get_session
from app.task_layer import generation, pipeline, retorno
from app.task_layer.models import Proposal, Task
from app.task_layer.schemas import (
    AIGenerateIn,
    ExternalProposalIn,
    InternalProposalIn,
    ProposalEnvelope,
)

logger = logging.getLogger("pase.task_layer")

router = APIRouter(prefix="/api/proposals", tags=["proposals"])


def _registrar(session: Session, **campos) -> Proposal:
    """Primeiro artefato da cadeia: a ideia bruta vira linha antes de qualquer juízo."""
    proposal = Proposal(**campos)
    session.add(proposal)
    session.flush()
    return proposal


@router.post("/external", response_model=ProposalEnvelope)
def captacao_ativa(
    payload: ExternalProposalIn,
    session: Session = Depends(get_session),
) -> ProposalEnvelope:
    """Agente Externo - Captação Ativa (modal do FinTrack)."""
    proposal = _registrar(
        session, origin="external", raw_text=payload.text, user_id=payload.user_id
    )
    return pipeline.run(session, proposal)


@router.post("/internal", response_model=ProposalEnvelope)
def sugestao_interna(
    payload: InternalProposalIn,
    session: Session = Depends(get_session),
) -> ProposalEnvelope:
    """Agente Interno - Sugestão Funcional ou de Engenharia.

    Engenharia exige autor com papel autorizado: a autorização é o que transfere
    a responsabilidade de julgamento para um humano qualificado e justifica o
    bypass da Memória e da Coerência (SPEC-03 §4).
    """
    if payload.type == "engenharia" and payload.author not in settings.authorized_authors:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=(
                f"'{payload.author}' não tem papel para abrir Sugestão de Engenharia. "
                "Autores autorizados são definidos em ENGINEERING_AUTHORS."
            ),
        )

    proposal = _registrar(
        session,
        origin="internal",
        type=payload.type,
        author=payload.author,
        raw_text=payload.text,
    )
    return pipeline.run(session, proposal)


@router.post("/ai-generate", response_model=ProposalEnvelope)
def geracao_por_ia(
    payload: AIGenerateIn,
    session: Session = Depends(get_session),
) -> ProposalEnvelope:
    """IA - Geração Exploratória (temperatura alta) ou Análise de Lacunas."""
    if payload.mode == "exploratoria":
        texto = generation.gerar_exploratoria(session)
    else:
        texto = generation.gerar_lacunas(session)

    if not texto:
        # P3b devolve null quando não encontra lacuna relevante: é uma resposta
        # legítima, não um erro.
        return ProposalEnvelope(
            proposal_id=None,
            outcome="sem_proposta",
            detail="A análise não encontrou nada relevante para propor agora.",
        )

    proposal = _registrar(
        session, origin="ai", type="funcional", author=f"PASE {payload.mode}", raw_text=texto
    )
    return pipeline.run(session, proposal)


@router.get("/mine")
def minhas_propostas(
    user_id: int = Query(...),
    session: Session = Depends(get_session),
) -> list[dict]:
    """O que aconteceu com cada sugestão do usuário (retorno ao FinTrack).

    Cada item: `id`, `texto`, `titulo`, `criada_em`, `situacao` e `detalhe`. As
    situações possíveis estão em `retorno.SITUACOES`.
    """
    return retorno.minhas_propostas(session, user_id)


@router.get("/occurrences")
def ocorrencias_por_tarefa(session: Session = Depends(get_session)) -> dict[str, int]:
    """`{task_id: pedidos}` das tarefas cuja proposta reúne mais de um pedido.

    O painel mostra "N pedidos" na lista de candidatas. A lista de tarefas vem de
    outro módulo; o peso mora na proposta, e é daqui que ele sai.
    """
    linhas = session.execute(
        select(Task.id, Proposal.occurrences)
        .join(Proposal, Proposal.id == Task.proposal_id)
        .where(Proposal.occurrences > 1)
    ).all()
    return {str(task_id): ocorrencias for task_id, ocorrencias in linhas}
