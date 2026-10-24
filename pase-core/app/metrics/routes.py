"""Métricas em CSV (SPEC-06 §5).

São anexo do capítulo de validação do TCC. As três medidas citadas na conclusão
da monografia saem todas de `tasks.csv`:

- **taxa de intervenção humana** = proporção de `ajustar`/`recusar` sobre o total
  que chegou à Homologação;
- **densidade de retrabalho** = média de `runs` por tarefa finalizada;
- **incidência de regressões** = tarefas cujos testes falharam numa run depois de
  terem passado numa run anterior da mesma tarefa.

O endpoint devolve linhas, não conclusões: o cálculo fica na monografia, onde
pode ser explicado.
"""

from __future__ import annotations

import csv
import io

from fastapi import APIRouter, Depends
from fastapi.responses import PlainTextResponse
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.common.db import get_session
from app.orchestration.models import ExecutionRun, PlanningDocument
from app.task_layer.models import DiscardedProposal, Proposal, Task
from app.upa.models import ZoneViolation

router = APIRouter(prefix="/api/metrics", tags=["metrics"])

COLUNAS_TASKS = [
    "task_id", "title", "origin", "output_type", "status", "final_outcome",
    "impact", "complexity", "confidence", "uncertainty", "risk_tier", "urgency_score",
    "tokens_estimated", "tokens_real_total", "runs", "retries", "deviation_count",
    "duration_ms_total", "created_at", "finished_at",
]

COLUNAS_DISCARDS = [
    "id", "reason_type", "reason_text", "matched_ref", "duplicate_count", "origin", "created_at",
]

COLUNAS_VIOLATIONS = ["id", "user_id", "slot", "origem", "reason", "created_at"]


def _csv(colunas: list[str], linhas: list[dict]) -> str:
    buffer = io.StringIO()
    escritor = csv.DictWriter(buffer, fieldnames=colunas, extrasaction="ignore")
    escritor.writeheader()
    escritor.writerows(linhas)
    return buffer.getvalue()


@router.get("/tasks.csv", response_class=PlainTextResponse)
def tasks_csv(session: Session = Depends(get_session)) -> str:
    """Uma linha por tarefa, com o agregado das suas execuções."""
    tarefas = session.execute(select(Task).order_by(Task.id)).scalars().all()

    agregados = {
        task_id: (total, soma_tokens or 0, soma_duracao or 0)
        for task_id, total, soma_tokens, soma_duracao in session.execute(
            select(
                ExecutionRun.task_id,
                func.count(ExecutionRun.id),
                func.sum(ExecutionRun.tokens_real),
                func.sum(ExecutionRun.duration_ms),
            ).group_by(ExecutionRun.task_id)
        ).all()
    }

    runs_por_task: dict[int, list[ExecutionRun]] = {}
    for run in session.execute(select(ExecutionRun).order_by(ExecutionRun.attempt)).scalars().all():
        runs_por_task.setdefault(run.task_id, []).append(run)

    planos = dict(
        session.execute(
            select(PlanningDocument.task_id, PlanningDocument.tokens_estimated)
        ).all()
    )

    origens = {
        p.id: p.origin for p in session.execute(select(Proposal)).scalars().all()
    }

    linhas = []
    for task in tarefas:
        runs = runs_por_task.get(task.id, [])
        total, tokens, duracao = agregados.get(task.id, (0, 0, 0))
        linhas.append(
            {
                "task_id": task.id,
                "title": task.title,
                "origin": origens.get(task.proposal_id, ""),
                "output_type": task.output_type,
                "status": task.status,
                "final_outcome": task.final_outcome or "",
                "impact": task.impact,
                "complexity": task.complexity,
                "confidence": task.confidence,
                "uncertainty": int(bool(task.uncertainty)),
                "risk_tier": task.risk_tier,
                "urgency_score": task.urgency_score,
                "tokens_estimated": planos.get(task.id, 0),
                "tokens_real_total": tokens,
                "runs": total,
                "retries": sum(1 for r in runs if r.trigger == "retry"),
                "deviation_count": sum(len(r.deviation_files or []) for r in runs),
                "duration_ms_total": duracao,
                "created_at": task.created_at.isoformat() if task.created_at else "",
                "finished_at": (
                    task.updated_at.isoformat()
                    if task.status == "finalizada" and task.updated_at
                    else ""
                ),
            }
        )

    return _csv(COLUNAS_TASKS, linhas)


@router.get("/discards.csv", response_class=PlainTextResponse)
def discards_csv(session: Session = Depends(get_session)) -> str:
    """Uma linha por descarte - a matéria-prima da análise do funil."""
    descartes = session.execute(
        select(DiscardedProposal).order_by(DiscardedProposal.id)
    ).scalars().all()
    origens = {p.id: p.origin for p in session.execute(select(Proposal)).scalars().all()}

    linhas = [
        {
            "id": d.id,
            "reason_type": d.reason_type,
            "reason_text": d.reason_text,
            "matched_ref": d.matched_ref or "",
            "duplicate_count": d.duplicate_count,
            "origin": origens.get(d.proposal_id, ""),
            "created_at": d.created_at.isoformat() if d.created_at else "",
        }
        for d in descartes
    ]
    return _csv(COLUNAS_DISCARDS, linhas)


@router.get("/violations.csv", response_class=PlainTextResponse)
def violations_csv(session: Session = Depends(get_session)) -> str:
    """Uma linha por payload recusado, no servidor ou no cliente (`origem`)."""
    violacoes = session.execute(select(ZoneViolation).order_by(ZoneViolation.id)).scalars().all()

    linhas = [
        {
            "id": v.id,
            "user_id": v.user_id,
            "slot": v.slot,
            "origem": v.origem,
            "reason": v.reason,
            "created_at": v.at.isoformat() if v.at else "",
        }
        for v in violacoes
    ]
    return _csv(COLUNAS_VIOLATIONS, linhas)
