"""Retorno ao usuário do FinTrack: o que aconteceu com cada sugestão dele.

Monografia §4.3.1: quem sugere pela Captação Ativa "recebe de volta a decisão
tomada sobre a sugestão". O modal mostra a resposta do funil e fecha; isto é o que
continua respondendo depois, quando a sugestão virou tarefa e a tarefa andou.

A situação é derivada, não guardada: vem do desfecho da proposta e, quando ela virou
tarefa, do estado da tarefa mais recente (refazer abre outra tarefa com a mesma
proposta) e de onde a entrega está no fluxo de branches.

O contrato é consumido pela interface do FinTrack - mudar um nome aqui quebra a tela.
"""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.orchestration.models import Release
from app.task_layer.models import (
    OUTCOME_DUPLICATA,
    OUTCOME_INCOERENTE,
    OUTCOME_REDIRECIONADA,
    OUTCOME_REVERTIDA,
    REASON_INCOERENTE,
    DiscardedProposal,
    Proposal,
    Task,
)

SITUACOES = (
    "em_analise",
    "descartada",
    "ja_existe",
    "personalizada",
    "aguardando_decisao",
    "em_desenvolvimento",
    "recusada",
    "aprovada",
    "publicada",
)

TEXTO_MAX_CHARS = 140
DETALHE_MAX_CHARS = 220
LIMITE_PADRAO = 50


def _encurtar(texto: str, limite: int) -> str:
    texto = " ".join((texto or "").split())
    return texto if len(texto) <= limite else texto[: limite - 1].rstrip() + "…"


def _detalhe_do_descarte(session: Session, proposal: Proposal) -> str:
    """O motivo do descarte, curto e em linguagem de quem usa o app."""
    descarte = session.execute(
        select(DiscardedProposal)
        .where(DiscardedProposal.proposal_id == proposal.id)
        .where(DiscardedProposal.reason_type == REASON_INCOERENTE)
        .order_by(DiscardedProposal.id.desc())
        .limit(1)
    ).scalar_one_or_none()
    if descarte is not None and descarte.reason_text.startswith("falha técnica"):
        return "Não conseguimos avaliar sua sugestão agora. Ela ficou registrada para revisão."
    if descarte is not None and descarte.cited_excerpt:
        return _encurtar(
            "Fica fora do que o FinTrack se propõe a fazer. A regra do produto diz: "
            f"“{descarte.cited_excerpt.strip()}”",
            DETALHE_MAX_CHARS,
        )
    motivo = descarte.reason_text if descarte is not None else proposal.feedback
    if motivo:
        return _encurtar(f"Fica fora do escopo do FinTrack: {motivo}", DETALHE_MAX_CHARS)
    return "Fica fora do escopo do FinTrack."


def _da_tarefa(session: Session, proposal: Proposal, task: Task) -> tuple[str, str]:
    if task.status == "candidata":
        if task.archived_at is not None:
            return "recusada", "A equipe avaliou a sugestão e decidiu não seguir com ela agora."
        return "aguardando_decisao", "Sua sugestão virou uma tarefa e aguarda a decisão da equipe."

    if task.status != "finalizada":
        return "em_desenvolvimento", "A equipe aprovou a sugestão e ela está sendo desenvolvida."

    if task.final_outcome == "aprovada" and proposal.outcome != OUTCOME_REVERTIDA:
        versao = None
        if task.release_id is not None:
            release = session.get(Release, task.release_id)
            versao = release.version if release is not None else None
        if task.stage == "producao":
            if versao:
                return "publicada", f"Já está no FinTrack, desde a versão {versao}."
            return "publicada", "Já está no FinTrack."
        if task.stage == "release" and versao:
            return "aprovada", f"Aprovada. Vai chegar ao FinTrack na versão {versao}."
        return "aprovada", "Aprovada. Está em testes antes de entrar numa nova versão do FinTrack."

    if task.final_outcome == "revertida" or proposal.outcome == OUTCOME_REVERTIDA:
        return "recusada", "A mudança chegou a ser feita, mas foi desfeita pela equipe."
    if task.final_outcome == "cancelada":
        return "recusada", "O desenvolvimento foi cancelado pela equipe."
    return "recusada", "A equipe avaliou a sugestão e decidiu não seguir com ela."


def situacao(session: Session, proposal: Proposal) -> tuple[str, str]:
    """`(situacao, detalhe)` de uma proposta, para quem a enviou."""
    if proposal.outcome is None:
        return "em_analise", "Sua sugestão está sendo avaliada."
    if proposal.outcome == OUTCOME_INCOERENTE:
        return "descartada", _detalhe_do_descarte(session, proposal)
    if proposal.outcome == OUTCOME_DUPLICATA:
        return "ja_existe", _encurtar(
            proposal.feedback or "Já existe uma sugestão ou funcionalidade equivalente.",
            DETALHE_MAX_CHARS,
        )
    if proposal.outcome == OUTCOME_REDIRECIONADA:
        return "personalizada", _encurtar(
            proposal.feedback or "Sua tela foi ajustada para você.", DETALHE_MAX_CHARS
        )

    # candidata e os desfechos terminais da tarefa: o destino é o da tarefa
    task = session.execute(
        select(Task).where(Task.proposal_id == proposal.id).order_by(Task.id.desc()).limit(1)
    ).scalar_one_or_none()
    if task is None:
        return "em_analise", "Sua sugestão está sendo avaliada."
    return _da_tarefa(session, proposal, task)


def minhas_propostas(
    session: Session, user_id: int, limite: int = LIMITE_PADRAO
) -> list[dict]:
    """As sugestões de um usuário, da mais recente para a mais antiga."""
    propostas = session.execute(
        select(Proposal)
        .where(Proposal.user_id == user_id)
        .order_by(Proposal.created_at.desc(), Proposal.id.desc())
        .limit(limite)
    ).scalars().all()

    itens = []
    for proposal in propostas:
        estado, detalhe = situacao(session, proposal)
        itens.append(
            {
                "id": proposal.id,
                "texto": _encurtar(proposal.raw_text, TEXTO_MAX_CHARS),
                "titulo": proposal.title,
                "criada_em": proposal.created_at.isoformat() if proposal.created_at else None,
                "situacao": estado,
                "detalhe": detalhe,
            }
        )
    return itens
