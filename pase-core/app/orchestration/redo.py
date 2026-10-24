"""Refazer: uma tentativa nova da mesma demanda, com o porquê da anterior.

Reverter constata que a entrega estava errada; até aqui, tentar de novo
significava reenviar a demanda pelo funil, que a barrava como "aguardando
avaliação" ou a deixava passar sem lembrar de nada. O resultado era pedir o
mesmo erro duas vezes.

Refazer cria uma tarefa **nova**, ligada à anterior por `parent_task_id`:

- a anterior continua como está, com o seu desfecho - o histórico conta as duas;
- a nova pula o funil, porque uma pessoa já decidiu que a demanda vale;
- o planejamento recebe o que deu errado (plano, parecer da revisão, motivo da
  reversão) e o executor recebe o pedido de quem homologou.

Tarefa aprovada é revertida antes, no mesmo gesto: refazer por cima de código
que continua na principal faria o Executor partir de uma base que já contém a
entrega errada.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.orchestration import homologation, states
from app.orchestration.models import ExecutionRun, PlanningDocument
from app.task_layer.models import OUTCOME_CANDIDATA, Proposal, Task, TaskStateHistory

logger = logging.getLogger("pase.orchestration")

#: Desfechos a partir dos quais refazer faz sentido. `aprovada` passa por uma
#: reversão antes; as demais já não deixaram código na principal.
DESFECHOS_REFAZIVEIS = ("aprovada", "revertida", "recusada", "cancelada")

#: Quantas tentativas anteriores entram no histórico do planejamento. Mais que
#: isso é ruído - e a mais recente já carrega o que importa das outras.
MAX_ANTERIORES = 3


class RefazerError(RuntimeError):
    pass


def refazer(session: Session, task: Task, feedback: str) -> Task:
    """Cria a tentativa nova, já em `candidata`. Quem chama dispara a cadeia."""
    feedback = (feedback or "").strip()
    if not feedback:
        raise RefazerError("refazer exige dizer o que estava errado")
    if task.status != states.FINALIZADA or task.final_outcome not in DESFECHOS_REFAZIVEIS:
        raise RefazerError(
            f"só dá para refazer tarefa finalizada; a task #{task.id} está em "
            f"'{task.status}' ({task.final_outcome})"
        )

    publicada = task.stage == "producao"
    if task.final_outcome == "aprovada" and not publicada:
        resultado = homologation.reverter(session, task, feedback)
        if not resultado.get("revertida"):
            raise RefazerError(
                f"não consegui reverter a task #{task.id} antes de refazer: "
                f"{resultado.get('detail')}"
            )

    nova = Task(
        proposal_id=task.proposal_id,
        title=task.title,
        description=task.description,
        module=task.module,
        output_type=task.output_type,
        # O que já está em produção só se corrige com um hotfix: nasce da principal
        # e entra por uma release nova. O resto refaz do mesmo tipo.
        change_type="fix" if publicada else task.change_type,
        impact=task.impact,
        complexity=task.complexity,
        confidence=task.confidence,
        uncertainty=task.uncertainty,
        risk_tier=task.risk_tier,
        urgency_score=task.urgency_score,
        # O teto manual não passa adiante: foi ajustado para a tentativa anterior, e
        # a nova começa do cálculo automático.
        parent_task_id=task.id,
        redo_feedback=feedback,
        # Refazer é exatamente o caso em que alguém quer ver o plano antes de gastar
        # outra execução: a primeira tentativa já mostrou que o entendimento falhou.
        plan_approval_required=True,
        status=states.CANDIDATA,
    )
    session.add(nova)
    session.flush()
    session.add(
        TaskStateHistory(
            task_id=nova.id,
            from_status=None,
            to_status=states.CANDIDATA,
            note=f"refazendo a task #{task.id}: {feedback}",
        )
    )

    # A demanda volta a estar em andamento. Reenviá-la agora **deve** ser barrado
    # como "aguardando avaliação" - e isso volta a ser verdade.
    if task.proposal_id is not None:
        proposta = session.get(Proposal, task.proposal_id)
        if proposta is not None:
            proposta.outcome = OUTCOME_CANDIDATA
            session.add(proposta)

    session.flush()
    logger.info("task #%s refaz a task #%s", nova.id, task.id)
    return nova


def _ultima_nota(session: Session, task_id: int) -> str:
    nota = session.execute(
        select(TaskStateHistory.note)
        .where(TaskStateHistory.task_id == task_id)
        .order_by(TaskStateHistory.id.desc())
        .limit(1)
    ).scalar_one_or_none()
    return nota or ""


def _parecer_da_ultima_run(session: Session, task_id: int) -> dict | None:
    caminho = session.execute(
        select(ExecutionRun.review_path)
        .where(ExecutionRun.task_id == task_id, ExecutionRun.review_path.is_not(None))
        .order_by(ExecutionRun.id.desc())
        .limit(1)
    ).scalar_one_or_none()
    if not caminho or not Path(caminho).exists():
        return None
    try:
        return json.loads(Path(caminho).read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return None


def _bloco_de(session: Session, anterior: Task) -> str:
    linhas = [f"### Task #{anterior.id} - desfecho: {anterior.final_outcome or anterior.status}"]

    plano = session.execute(
        select(PlanningDocument)
        .where(PlanningDocument.task_id == anterior.id)
        .order_by(PlanningDocument.id.desc())
        .limit(1)
    ).scalar_one_or_none()
    if plano is not None:
        linhas.append(f"Plano seguido:\n{plano.roadmap.strip()}")
        if plano.acceptance_criteria:
            linhas.append(
                "Critérios que ela tinha:\n"
                + "\n".join(f"- {c['criterio']}" for c in plano.acceptance_criteria)
            )

    parecer = _parecer_da_ultima_run(session, anterior.id)
    if parecer is not None:
        pendentes = [c for c in parecer.get("criterios", []) if not c.get("atendido")]
        if parecer.get("resumo"):
            linhas.append(f"Revisão independente: {parecer['resumo']}")
        for c in pendentes:
            linhas.append(f"- não cumpriu: {c.get('criterio')} ({c.get('anulado_por') or ''})")

    nota = _ultima_nota(session, anterior.id)
    if nota:
        linhas.append(f"Por que foi encerrada: {nota}")
    return "\n\n".join(linhas)


def _historico_de_revisao_do_plano(session: Session, task: Task) -> str:
    """O plano que uma pessoa devolveu, e por quê."""
    if not task.plan_feedback:
        return ""
    plano = session.execute(
        select(PlanningDocument)
        .where(PlanningDocument.task_id == task.id)
        .order_by(PlanningDocument.id.desc())
        .limit(1)
    ).scalar_one_or_none()
    partes = [
        "## Uma pessoa devolveu o plano anterior desta tarefa",
        f"> {task.plan_feedback}",
    ]
    if plano is not None:
        partes.append("Plano devolvido:\n" + plano.roadmap.strip())
        partes.append("Arquivos previstos: " + ", ".join(plano.affected_files))
        if plano.acceptance_criteria:
            partes.append(
                "Critérios que ele tinha:\n"
                + "\n".join(f"- {c['criterio']}" for c in plano.acceptance_criteria)
            )
    partes.append("Faça um plano novo que resolva o que foi apontado. Não repita o anterior.")
    return "\n\n".join(partes)


def historico_de(session: Session, task: Task) -> str:
    """O bloco `{{historico}}` do P4: tentativas anteriores e planos devolvidos."""
    revisao = _historico_de_revisao_do_plano(session, task)
    refazer = _historico_de_tentativas(session, task)
    return "\n\n".join(b for b in (refazer, revisao) if b)


def _historico_de_tentativas(session: Session, task: Task) -> str:
    """Vazio para uma tarefa que não refaz outra."""
    if task.parent_task_id is None:
        return ""

    blocos = []
    atual: Task | None = task
    while atual is not None and atual.parent_task_id is not None and len(blocos) < MAX_ANTERIORES:
        anterior = session.get(Task, atual.parent_task_id)
        if anterior is None:
            break
        blocos.append(_bloco_de(session, anterior))
        atual = anterior

    return (
        "## Tentativas anteriores desta mesma demanda\n\n"
        "Esta tarefa refaz uma entrega que não serviu. Quem a usou pediu:\n\n"
        f"> {task.redo_feedback}\n\n"
        "Leia o que foi tentado antes e por que falhou. Os critérios de aceite desta vez "
        "precisam cobrir exatamente o que faltou.\n\n" + "\n\n".join(blocos)
    )
