"""Sugestões de atualização do contexto, nascidas de uma tarefa aprovada.

O modelo PASE fecha o laço: uma tarefa aprovada vai para o histórico **e** pode mudar o
contexto geral do projeto. Aqui isso acontece sem que o sistema reescreva a própria régua:

1. aprovada uma tarefa, o P11 é consultado sobre os documentos que descrevem **o que
   existe** (o contexto do produto e as funcionalidades): ficou algo desatualizado?
2. só quando o P11 diz que se aplica nasce uma **sugestão**, com o diff, pendente;
3. uma pessoa aceita (e o documento ganha uma versão nova) ou dispensa.

A sugestão guarda a versão do documento sobre a qual foi feita. Se alguém editou o
documento no meio tempo, aceitá-la sobrescreveria essa edição, e por isso é recusado.
"""

from __future__ import annotations

import logging

from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.common import context_ai, context_store
from app.common.config import settings
from app.common.db import session_scope
from app.common.models import ContextSuggestion, utcnow

logger = logging.getLogger("pase.contexto")

#: Documentos que descrevem o que o produto É hoje. Os demais (guia de engenharia,
#: segurança...) não mudam porque uma funcionalidade foi entregue.
DOCUMENTOS = ("project-context", "features")

PENDENTE, ACEITA, DISPENSADA, OBSOLETA = "pendente", "aceita", "dispensada", "obsoleta"


def pedido_da_tarefa(titulo: str, descricao: str, roadmap: str, criterios: list[dict]) -> str:
    linhas = [
        f"A tarefa \"{titulo}\" foi aprovada e integrada ao produto.",
        f"Descrição: {descricao}",
    ]
    if roadmap:
        linhas.append(f"O que foi feito (plano seguido):\n{roadmap}")
    if criterios:
        linhas.append(
            "O que a pessoa passou a poder fazer:\n"
            + "\n".join(f"- {c['criterio']}" for c in criterios)
        )
    linhas.append(
        "Registre neste documento o que passou a existir, se algo aqui ficou desatualizado "
        "(um módulo, uma funcionalidade, uma zona ativa, uma regra). Se o documento já "
        "descreve o que foi entregue, ou a entrega não muda o que ele diz, responda "
        "aplicavel=false. Não altere nada que não tenha relação com esta entrega."
    )
    return "\n\n".join(linhas)


def gerar_para_tarefa(task_id: int) -> int:
    """Consulta o P11 para cada documento e grava as sugestões que se aplicam.

    Roda em segundo plano depois da aprovação. Falhar aqui não afeta a tarefa: é uma
    conveniência, e uma pessoa pode sempre editar o contexto à mão.
    """
    if not settings.context_suggestions_enabled:
        return 0

    from app.orchestration.models import PlanningDocument
    from app.task_layer.models import Task

    criadas = 0
    try:
        with session_scope() as session:
            task = session.get(Task, task_id)
            if task is None:
                return 0
            plano = session.execute(
                select(PlanningDocument)
                .where(PlanningDocument.task_id == task_id)
                .order_by(PlanningDocument.id.desc())
                .limit(1)
            ).scalar_one_or_none()
            pedido = pedido_da_tarefa(
                task.title,
                task.description,
                plano.roadmap if plano else "",
                (plano.acceptance_criteria if plano else None) or [],
            )

            for slug in DOCUMENTOS:
                ja_existe = session.execute(
                    select(ContextSuggestion.id).where(
                        ContextSuggestion.task_id == task_id,
                        ContextSuggestion.slug == slug,
                        ContextSuggestion.status == PENDENTE,
                    )
                ).first()
                if ja_existe:
                    continue
                try:
                    doc = context_store.obter(session, slug)
                    proposta = context_ai.propor(slug, doc.content, pedido, task_id=task_id)
                except Exception:
                    logger.exception("sugestão de contexto falhou: task #%s, %s", task_id, slug)
                    continue
                if not proposta["aplicavel"]:
                    continue
                session.add(
                    ContextSuggestion(
                        task_id=task_id,
                        slug=slug,
                        base_version=doc.version,
                        summary=proposta["summary"][:300],
                        reasoning=proposta["reasoning"],
                        content=proposta["content"],
                        diff=proposta["diff"],
                    )
                )
                criadas += 1
    except Exception:  # pragma: no cover - rede de segurança do background
        logger.exception("sugestões de contexto falharam para a task #%s", task_id)
    return criadas


def pendentes(session: Session) -> list[ContextSuggestion]:
    return list(
        session.execute(
            select(ContextSuggestion)
            .where(ContextSuggestion.status == PENDENTE)
            .order_by(ContextSuggestion.id.desc())
        ).scalars()
    )


def _obter(session: Session, suggestion_id: int) -> ContextSuggestion:
    s = session.get(ContextSuggestion, suggestion_id)
    if s is None:
        raise context_store.ContextoError("sugestão não encontrada")
    if s.status != PENDENTE:
        raise context_store.ContextoError(f"a sugestão já está '{s.status}'")
    return s


def aceitar(session: Session, suggestion_id: int):
    """Grava a sugestão como versão nova do documento. Recusa se o documento mudou."""
    s = _obter(session, suggestion_id)
    doc = context_store.obter(session, s.slug)
    if doc.version != s.base_version:
        raise context_store.ContextoError(
            f"o documento {s.slug} mudou desde a sugestão (v{s.base_version} para "
            f"v{doc.version}). Aceitá-la sobrescreveria essa edição: dispense e, se ainda "
            "valer, edite à mão."
        )
    doc, _ = context_store.salvar(
        session,
        s.slug,
        s.content,
        note=f"sugestão da tarefa #{s.task_id}: {s.summary}"[:300],
        author="ia (aceita por humano)",
    )
    s.status = ACEITA
    s.decided_at = utcnow()
    session.add(s)
    return doc


def dispensar(session: Session, suggestion_id: int) -> None:
    s = _obter(session, suggestion_id)
    s.status = DISPENSADA
    s.decided_at = utcnow()
    session.add(s)


def obsoletar_da_tarefa(session: Session, task_id: int) -> int:
    """A tarefa foi revertida: o que ela mudaria no contexto deixou de ser verdade."""
    resultado = session.execute(
        update(ContextSuggestion)
        .where(ContextSuggestion.task_id == task_id, ContextSuggestion.status == PENDENTE)
        .values(status=OBSOLETA, decided_at=utcnow())
    )
    return resultado.rowcount or 0
