"""Máquina de estados da tarefa (SPEC-04 §1).

As transições são estritas e toda mudança grava `task_state_history` - o gate
humano é sempre um registro, nunca um processo travado esperando input
(SPEC-00 §3). O sistema segue rodando outras tarefas enquanto uma espera.

    candidata → em_planejamento → pronta_para_despacho → em_execucao
              → em_homologacao → finalizada

    em_planejamento → aguardando_plano  (tarefa que exige aprovação do plano)
    aguardando_plano → pronta_para_despacho  (plano aprovado)
    aguardando_plano → em_planejamento       (plano devolvido com feedback)

    em_execucao   → suspensa       (falha ou budget)
    suspensa      → em_execucao    (resume)
    em_homologacao → em_execucao   (ajuste)

    pronta_para_despacho | aguardando_plano → suspensa  (predecessora suspensa)
    suspensa → pronta_para_despacho | aguardando_plano  (predecessora voltou)
"""

from __future__ import annotations

import logging

from sqlalchemy.orm import Session

from app.common.events import publish
from app.task_layer.models import Task, TaskStateHistory

logger = logging.getLogger("pase.orchestration")

CANDIDATA = "candidata"
EM_PLANEJAMENTO = "em_planejamento"
AGUARDANDO_PLANO = "aguardando_plano"
PRONTA_PARA_DESPACHO = "pronta_para_despacho"
EM_EXECUCAO = "em_execucao"
EM_HOMOLOGACAO = "em_homologacao"
SUSPENSA = "suspensa"
FINALIZADA = "finalizada"

#: Único mapa de transições permitidas. Qualquer caminho fora daqui é bug.
TRANSICOES: dict[str, set[str]] = {
    CANDIDATA: {EM_PLANEJAMENTO, FINALIZADA},
    EM_PLANEJAMENTO: {PRONTA_PARA_DESPACHO, AGUARDANDO_PLANO, SUSPENSA, FINALIZADA},
    AGUARDANDO_PLANO: {PRONTA_PARA_DESPACHO, EM_PLANEJAMENTO, SUSPENSA, FINALIZADA},
    PRONTA_PARA_DESPACHO: {EM_EXECUCAO, SUSPENSA, FINALIZADA},
    EM_EXECUCAO: {EM_HOMOLOGACAO, SUSPENSA, FINALIZADA},
    EM_HOMOLOGACAO: {FINALIZADA, EM_EXECUCAO, EM_PLANEJAMENTO},
    # Volta a `pronta_para_despacho` ou `aguardando_plano` só a suspensão em
    # cascata: a tarefa não falhou, esperava uma predecessora que falhou.
    SUSPENSA: {EM_EXECUCAO, EM_PLANEJAMENTO, PRONTA_PARA_DESPACHO, AGUARDANDO_PLANO, FINALIZADA},
    FINALIZADA: set(),
}

ALERTAS = ("none", "retries", "budget", "merge_conflict", "ci_develop", "predecessora")


class TransicaoInvalidaError(RuntimeError):
    """Tentativa de mover a tarefa por um caminho que o modelo não prevê."""


def pode_transicionar(de: str, para: str) -> bool:
    return para in TRANSICOES.get(de, set())


def transicionar(
    session: Session,
    task: Task,
    para: str,
    *,
    note: str | None = None,
    alert: str | None = None,
    final_outcome: str | None = None,
) -> Task:
    """Move a tarefa, registra o histórico e publica o evento.

    É o único caminho para mudar `task.status`. Escrever o campo direto pularia
    o histórico, e uma decisão sem registro não é rastreável (SPEC-00 §2).
    """
    de = task.status
    if not pode_transicionar(de, para):
        raise TransicaoInvalidaError(f"transição inválida para a task #{task.id}: {de} → {para}")

    task.status = para
    if alert is not None:
        task.alert = alert
    if final_outcome is not None:
        task.final_outcome = final_outcome

    session.add(task)
    session.add(
        TaskStateHistory(task_id=task.id, from_status=de, to_status=para, note=note)
    )
    session.flush()

    logger.info("task #%s: %s → %s%s", task.id, de, para, f" ({note})" if note else "")
    publish(
        "task.updated",
        {
            "task_id": task.id,
            "from": de,
            "to": para,
            "alert": task.alert,
            "note": note,
        },
        session=session,
    )
    return task


def score_de_prioridade(task: Task) -> float:
    """`impact − complexity + urgency_score` (SPEC-04 §2).

    Deliberadamente simples nesta fase; SLA e decaimento temporal estão no SPEC-10.
    """
    return (task.impact or 0) - (task.complexity or 0) + (task.urgency_score or 0.0)


def registrar_desfecho(
    session: Session, task: Task, final_outcome: str, *, note: str
) -> Task:
    """Muda o desfecho de uma tarefa **sem** mover o estado.

    `finalizada` é terminal e continua sendo: a reversão de um merge não é uma
    transição de estado, é a constatação de que o desfecho registrado deixou de
    ser verdade. Abrir um laço `finalizada → finalizada` no mapa só para caber
    este caso enfraqueceria o invariante para todo o resto.

    O que importa - o registro em `task_state_history` e o evento para o painel -
    acontece igual.
    """
    task.final_outcome = final_outcome
    session.add(task)
    session.add(
        TaskStateHistory(
            task_id=task.id, from_status=task.status, to_status=task.status, note=note
        )
    )
    session.flush()

    logger.info("task #%s: desfecho → %s (%s)", task.id, final_outcome, note)
    publish(
        "task.updated",
        {
            "task_id": task.id,
            "from": task.status,
            "to": task.status,
            "alert": task.alert,
            "note": note,
        },
        session=session,
    )
    return task
