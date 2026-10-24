"""Endpoints da Orquestração (SPEC-04 §3).

Toda decisão crítica passa por aqui e nenhuma acontece sozinha: aprovar,
homologar, recusar e retomar são ações de uma pessoa no painel.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Literal

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query, status
from fastapi.responses import PlainTextResponse
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.common import context_suggestions
from app.common.config import settings
from app.common.db import get_session
from app.common.models import utcnow
from app.common.vector_store import save_embedding
from app.execution.budget import cabe_mais_uma_chamada, gasto_da_task, teto_de
from app.execution.planning import criterios_validos as _criterios_validos
from app.orchestration import (
    chain,
    delivery,
    dependencies,
    homologation,
    redo,
    states,
    suspensao,
)
from app.orchestration.chain import _plano_de
from app.orchestration.models import ExecutionRun, Incident, PlanningDocument
from app.task_layer.models import (
    OUTCOME_RECUSADA,
    DiscardedProposal,
    Proposal,
    Task,
    TaskStateHistory,
)
from app.task_layer.uncertainty import incerteza

logger = logging.getLogger("pase.orchestration")

router = APIRouter(prefix="/api", tags=["orchestration"])


# --------------------------------------------------------------------------- #
# Schemas
# --------------------------------------------------------------------------- #


class RejectIn(BaseModel):
    reason: str = Field(min_length=1)
    #: Só vale ao cancelar: `True` registra a demanda como descartada, para a memória
    #: barrá-la depois; `False` cancela só esta tentativa (ex.: vai refazer).
    remember: bool = True


class ArchiveIn(BaseModel):
    reason: str | None = None


@router.post("/tasks/{task_id}/archive")
def arquivar(
    task_id: int,
    payload: ArchiveIn | None = None,
    session: Session = Depends(get_session),
) -> dict:
    """Tira a tarefa das listas **sem apagar nada**.

    Só tarefa finalizada: as demais ainda têm trabalho ou decisão pendente, e
    arquivá-las as esconderia de quem precisa agir (cancele antes, se for o caso).
    E só se não estiver mais no fluxo de entrega: arquivar o que está na develop ou
    numa release deixaria uma release com uma tarefa invisível.

    O histórico, as execuções, os pareceres e os artefatos permanecem; é o
    registro que o gate humano exige. A tarefa continua abrindo pela URL dela.
    """
    task = session.get(Task, task_id)
    if task is None:
        raise HTTPException(status_code=404, detail="tarefa não encontrada")
    if task.archived_at is not None:
        raise HTTPException(status_code=409, detail="a tarefa já está arquivada")
    if task.status != states.FINALIZADA:
        raise HTTPException(
            status_code=409,
            detail=(
                f"só se arquiva tarefa finalizada; a task #{task_id} está em '{task.status}'. "
                "Cancele ou conclua antes."
            ),
        )
    if task.stage in ("develop", "release"):
        onde = "na develop" if task.stage == "develop" else "numa release"
        raise HTTPException(
            status_code=409,
            detail=f"a task #{task_id} ainda está {onde}: publique ou reverta antes de arquivar.",
        )

    nota = (payload.reason if payload else None) or "arquivada"
    task.archived_at = utcnow()
    task.archive_note = nota.strip()
    session.add(task)
    session.add(
        TaskStateHistory(
            task_id=task.id,
            from_status=task.status,
            to_status=task.status,
            note=f"arquivada: {task.archive_note}",
        )
    )
    session.commit()
    return {"task_id": task_id, "archived": True}


@router.post("/tasks/{task_id}/unarchive")
def desarquivar(task_id: int, session: Session = Depends(get_session)) -> dict:
    """Devolve a tarefa às listas."""
    task = session.get(Task, task_id)
    if task is None:
        raise HTTPException(status_code=404, detail="tarefa não encontrada")
    if task.archived_at is None:
        raise HTTPException(status_code=409, detail="a tarefa não está arquivada")

    task.archived_at = None
    task.archive_note = None
    session.add(task)
    session.add(
        TaskStateHistory(
            task_id=task.id,
            from_status=task.status,
            to_status=task.status,
            note="desarquivada",
        )
    )
    session.commit()
    return {"task_id": task_id, "archived": False}


class RevertIn(BaseModel):
    reason: str = Field(min_length=1)


class HomologationIn(BaseModel):
    decision: Literal["aprovar", "ajustar", "recusar"]
    comment: str | None = None


class IncidentIn(BaseModel):
    title: str = Field(min_length=1)
    description: str = ""
    severity: Literal["baixo", "medio", "alto"]
    module: str | None = None


class DemoIn(BaseModel):
    force_fail_runs: int | None = None
    budget_cap_tokens: int | None = None


# --------------------------------------------------------------------------- #
# Leitura
# --------------------------------------------------------------------------- #


def _resumo(task: Task) -> dict:
    return {
        "id": task.id,
        "title": task.title,
        "status": task.status,
        "module": task.module,
        "output_type": task.output_type,
        "impact": task.impact,
        "complexity": task.complexity,
        "confidence": task.confidence,
        "uncertainty": task.uncertainty,
        "risk_tier": task.risk_tier,
        "urgency_score": task.urgency_score,
        "alert": task.alert,
        "waiting_on_task_id": task.waiting_on_task_id,
        "final_outcome": task.final_outcome,
        "priority_score": states.score_de_prioridade(task),
        "change_type": task.change_type,
        "branch_name": task.branch_name,
        "merge_commit": task.merge_commit,
        "pr_url": task.pr_url,
        "budget_cap_tokens": task.budget_cap_tokens,
        "parent_task_id": task.parent_task_id,
        "stage": task.stage,
        "release_id": task.release_id,
        "tested_ok": task.tested_ok,
        "plan_approval_required": task.plan_approval_required,
        "archived_at": task.archived_at,
        "updated_at": task.updated_at,
    }


@router.get("/tasks")
def listar_tasks(
    task_status: str | None = Query(default=None, alias="status"),
    archived: bool = Query(default=False),
    session: Session = Depends(get_session),
) -> list[dict]:
    """Lista tarefas, ordenadas por `impact - complexity + urgency_score` (§2).

    As arquivadas ficam de fora, a menos que se peça `archived=true`: aí só elas.
    """
    consulta = select(Task).where(
        Task.archived_at.is_not(None) if archived else Task.archived_at.is_(None)
    )
    if task_status:
        consulta = consulta.where(Task.status == task_status)

    tarefas = session.execute(consulta).scalars().all()
    return sorted(
        (_resumo(t) for t in tarefas),
        key=lambda item: (-item["priority_score"], item["id"]),
    )


def _ler_parecer(caminho: str | None) -> dict | None:
    """O parecer da revisão independente, se a run chegou a ser revisada.

    Vai inteiro no detalhe da tarefa, não como artefato de texto: é o que a
    Homologação mostra critério a critério, com a evidência ao lado.
    """
    if not caminho or not Path(caminho).exists():
        return None
    try:
        return json.loads(Path(caminho).read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        logger.warning("parecer ilegível em %s", caminho)
        return None


@router.get("/tasks/{task_id}")
def detalhar_task(task_id: int, session: Session = Depends(get_session)) -> dict:
    """Agregado que a tela Tarefa[id] consome: task + histórico + plano + runs."""
    task = session.get(Task, task_id)
    if task is None:
        raise HTTPException(status_code=404, detail="tarefa não encontrada")

    historico = session.execute(
        select(TaskStateHistory)
        .where(TaskStateHistory.task_id == task_id)
        .order_by(TaskStateHistory.id)
    ).scalars().all()

    plano = session.execute(
        select(PlanningDocument)
        .where(PlanningDocument.task_id == task_id)
        .order_by(PlanningDocument.id.desc())
        .limit(1)
    ).scalar_one_or_none()

    runs = session.execute(
        select(ExecutionRun).where(ExecutionRun.task_id == task_id).order_by(ExecutionRun.attempt)
    ).scalars().all()

    # O orçamento é o que decide se "Retomar" tem chance de fazer alguma coisa.
    # Sem isto à vista, a única forma de saber era ler a mensagem de erro de uma
    # execução que já falhou.
    teto = teto_de(task, plano.tokens_estimated if plano else 0)
    gasto = gasto_da_task(session, task_id)

    return {
        "task": _resumo(task),
        "description": task.description,
        "branch_name": task.branch_name,
        "parent_task_id": task.parent_task_id,
        "redo_feedback": task.redo_feedback,
        "plan_approval_required": task.plan_approval_required,
        "plan_approved": task.plan_approved,
        "tested_note": task.tested_note,
        "archive_note": task.archive_note,
        "orcamento": {
            "teto": teto,
            "gasto": gasto,
            "restante": max(teto - gasto, 0),
            "manual": task.budget_cap_tokens is not None,
        },
        "history": [
            {"from": h.from_status, "to": h.to_status, "note": h.note, "at": h.at}
            for h in historico
        ],
        "planning": None
        if plano is None
        else {
            "acceptance_criteria": plano.acceptance_criteria or [],
            "affected_files": plano.affected_files,
            "roadmap": plano.roadmap,
            "tokens_estimated": plano.tokens_estimated,
            "file_actions": plano.file_actions or {},
            "minutes_estimated": plano.minutes_estimated,
            "technical_risk": plano.technical_risk,
            "technical_risk_reason": plano.technical_risk_reason,
        },
        "runs": [
            {
                "id": r.id,
                "attempt": r.attempt,
                "trigger": r.trigger,
                "status": r.status,
                "failure_reason": r.failure_reason,
                "deviation_files": r.deviation_files,
                "tokens_real": r.tokens_real,
                "duration_ms": r.duration_ms,
                "created_at": r.created_at,
                "review": _ler_parecer(r.review_path),
            }
            for r in runs
        ],
    }


# --------------------------------------------------------------------------- #
# Gates humanos
# --------------------------------------------------------------------------- #


class ApproveIn(BaseModel):
    #: `True` para parar no plano, `False` para seguir direto, `None` para decidir
    #: pelo risco da tarefa (`PLAN_APPROVAL_TIERS`).
    review_plan: bool | None = None


@router.post("/tasks/{task_id}/approve")
def aprovar_candidata(
    task_id: int,
    background: BackgroundTasks,
    payload: ApproveIn | None = None,
    session: Session = Depends(get_session),
) -> dict:
    """Libera a tarefa para a cadeia autônoma (§4). Responde na hora.

    Aprovar a demanda não é aprovar o plano. Para tarefa de risco médio ou alto -
    ou quando a pessoa pede -, a cadeia para depois do planejamento, antes de
    gastar uma única chamada de execução, e espera `/plan/approve`.
    """
    task = session.get(Task, task_id)
    if task is None:
        raise HTTPException(status_code=404, detail="tarefa não encontrada")
    if task.status != states.CANDIDATA:
        raise HTTPException(
            status_code=409, detail=f"a tarefa está em '{task.status}', não em 'candidata'"
        )

    pedido = payload.review_plan if payload else None
    task.plan_approval_required = (
        pedido if pedido is not None else task.risk_tier in settings.planos_que_exigem_aprovacao
    )
    task.plan_approved = False
    session.add(task)

    session.commit()
    background.add_task(chain.rodar_cadeia, task_id)
    return {
        "task_id": task_id,
        "status": "aprovada",
        "detail": "planejamento iniciado",
        "plan_approval_required": task.plan_approval_required,
    }


@router.post("/tasks/{task_id}/reject")
def recusar_candidata(
    task_id: int,
    payload: RejectIn,
    session: Session = Depends(get_session),
) -> dict:
    """Recusa antes de qualquer execução. Entra na memória de descartes."""
    task = session.get(Task, task_id)
    if task is None:
        raise HTTPException(status_code=404, detail="tarefa não encontrada")
    if task.status != states.CANDIDATA:
        raise HTTPException(status_code=409, detail=f"a tarefa está em '{task.status}'")

    descarte = DiscardedProposal(
        proposal_id=task.proposal_id,
        task_id=task.id,
        reason_type="recusa_humana",
        reason_text=payload.reason,
        duplicate_count=1,
    )
    session.add(descarte)
    session.flush()
    save_embedding(
        "discarded", descarte.id, f"{task.title}\n{task.description}", session=session
    )

    homologation.encerrar_proposta(session, task, OUTCOME_RECUSADA)
    states.transicionar(
        session,
        task,
        states.FINALIZADA,
        note=f"recusada na triagem: {payload.reason}",
        final_outcome="recusada",
    )
    session.commit()
    return {"task_id": task_id, "status": "finalizada", "final_outcome": "recusada"}


class ResumeIn(BaseModel):
    #: O que o Executor deve mudar. Vazio retoma como antes: mesmo plano, mesma ordem.
    instruction: str | None = None
    #: Com instrução, `True` (padrão) reescreve o plano incluindo-a e segue o plano novo;
    #: `False` mantém o plano e entrega a instrução ao Executor como pedido.
    update_plan: bool = True


@router.post("/tasks/{task_id}/resume")
def retomar(
    task_id: int,
    background: BackgroundTasks,
    payload: ResumeIn | None = None,
    session: Session = Depends(get_session),
) -> dict:
    """Retoma uma tarefa suspensa, zerando a contagem de retry (§3).

    O modelo prevê que, da Suspensa, o humano "solicita ajustes". Aqui a pessoa diz o
    que mudar: por padrão o plano é reescrito com a instrução (o problema que suspendeu
    a tarefa costuma estar no plano, e repetir o mesmo plano repete a falha); ela pode
    preferir manter o plano e só orientar a execução.
    """
    instrucao = ((payload.instruction if payload else None) or "").strip() or None
    atualizar_plano = payload.update_plan if payload else True
    task = session.get(Task, task_id)
    if task is None:
        raise HTTPException(status_code=404, detail="tarefa não encontrada")
    if task.status != states.SUSPENSA:
        raise HTTPException(status_code=409, detail=f"a tarefa está em '{task.status}'")

    # Suspensa em cascata não falhou: espera a predecessora. Retomá-la direto a
    # mandaria executar antes de quem ela depende - e pularia o gate do plano,
    # se ela estava esperando aprovação. Ela volta sozinha quando a outra voltar.
    predecessora = suspensao.suspensa_por(session, task)
    if predecessora is not None:
        raise HTTPException(
            status_code=409,
            detail=(
                f"a task #{task_id} está suspensa porque a #{predecessora} está; "
                f"retome, replaneje ou cancele a #{predecessora} e esta volta junto"
            ),
        )

    # Retomar sem teto novo quando o gasto já o ultrapassou produz uma run que
    # morre em sete segundos sem gastar um token - foi o que aconteceu duas vezes
    # na primeira execução real. Melhor recusar dizendo os números do que fingir
    # que tentou.
    plano = _plano_de(session, task_id)
    teto = teto_de(task, plano.tokens_estimated if plano else 0)
    gasto = gasto_da_task(session, task_id)

    # Preditivo, não retrospectivo: "ainda não passou do teto" não significa que
    # a execução consegue começar. O guardrail do Executor confere o custo da
    # chamada **antes** de enviá-la, e uma retomada sem folga para uma chamada
    # inteira morre antes de gastar um token.
    cabe, aviso = cabe_mais_uma_chamada(session, task, teto)
    if not cabe:
        raise HTTPException(status_code=409, detail=aviso)

    if instrucao and atualizar_plano:
        # O plano muda, então a pessoa volta a vê-lo quando a tarefa exige aprovação.
        task.plan_feedback = instrucao
        if task.plan_approval_required:
            task.plan_approved = False
        session.add(task)
        states.transicionar(
            session,
            task,
            states.EM_PLANEJAMENTO,
            note=f"retomada com ajuste, plano reescrito: {instrucao}",
            alert="none",
        )
        suspensao.restaurar_dependentes(session, task_id)
        session.commit()
        background.add_task(chain.rodar_replanejamento, task_id)
        return {"task_id": task_id, "status": states.EM_PLANEJAMENTO, "teto": teto, "gasto": gasto}

    nota = "retomada pelo gestor"
    if instrucao:
        nota = f"retomada com ajuste, mesmo plano: {instrucao}"
    states.transicionar(session, task, states.EM_EXECUCAO, note=nota, alert="none")
    # O ramo que parou junto volta ao que era; segue esperando esta terminar.
    suspensao.restaurar_dependentes(session, task_id)
    session.commit()
    background.add_task(chain.rodar_execucao, task_id, trigger="retry", comentario=instrucao)
    return {"task_id": task_id, "status": states.EM_EXECUCAO, "teto": teto, "gasto": gasto}


def _task_aguardando_plano(session: Session, task_id: int) -> Task:
    task = session.get(Task, task_id)
    if task is None:
        raise HTTPException(status_code=404, detail="tarefa não encontrada")
    if task.status != states.AGUARDANDO_PLANO:
        raise HTTPException(
            status_code=409,
            detail=f"a tarefa está em '{task.status}', não em 'aguardando_plano'",
        )
    return task


class PlanApproveIn(BaseModel):
    comment: str | None = None


@router.post("/tasks/{task_id}/plan/approve")
def aprovar_plano(
    task_id: int,
    background: BackgroundTasks,
    payload: PlanApproveIn | None = None,
    session: Session = Depends(get_session),
) -> dict:
    """Libera o plano: só agora o Executor começa a escrever código."""
    task = _task_aguardando_plano(session, task_id)
    nota = (payload.comment if payload else None) or "plano aprovado"
    task.plan_approved = True
    session.add(task)
    states.transicionar(session, task, states.PRONTA_PARA_DESPACHO, note=nota)
    session.commit()
    background.add_task(chain.rodar_apos_aprovacao_do_plano, task_id)
    return {"task_id": task_id, "status": states.PRONTA_PARA_DESPACHO}


class PlanReviseIn(BaseModel):
    feedback: str = Field(min_length=1)


@router.post("/tasks/{task_id}/plan/revise")
def devolver_plano(
    task_id: int,
    payload: PlanReviseIn,
    background: BackgroundTasks,
    session: Session = Depends(get_session),
) -> dict:
    """Devolve o plano com o que está errado. O planejamento recomeça lendo o motivo.

    O plano devolvido e o feedback vão ao P4: refazer o plano sem saber o que foi
    apontado seria pedir o mesmo plano de novo.
    """
    task = _task_aguardando_plano(session, task_id)
    task.plan_feedback = payload.feedback.strip()
    task.plan_approved = False
    session.add(task)
    states.transicionar(
        session,
        task,
        states.EM_PLANEJAMENTO,
        note=f"plano devolvido: {task.plan_feedback}",
    )
    session.commit()
    background.add_task(chain.rodar_replanejamento, task_id)
    return {"task_id": task_id, "status": states.EM_PLANEJAMENTO}


class PlanoIn(BaseModel):
    acceptance_criteria: list[dict] | None = None
    affected_files: list[str] | None = None
    roadmap: str | None = Field(default=None, min_length=1)


@router.patch("/tasks/{task_id}/plan")
def editar_plano(
    task_id: int,
    payload: PlanoIn,
    session: Session = Depends(get_session),
) -> dict:
    """Edita o plano à mão antes de aprová-lo.

    Quando a pessoa sabe exatamente o que quer - tirar um arquivo, apertar um
    critério -, dizer isso direto custa menos do que pedir ao modelo para
    adivinhar. A edição fica no histórico: quem decidiu o quê precisa constar.
    """
    task = _task_aguardando_plano(session, task_id)
    plano = _plano_de(session, task_id)
    if plano is None:
        raise HTTPException(status_code=404, detail="esta tarefa não tem plano")

    mudancas = payload.model_dump(exclude_none=True)
    if not mudancas:
        raise HTTPException(status_code=422, detail="nada para mudar")

    if "acceptance_criteria" in mudancas:
        criterios = _criterios_validos(mudancas["acceptance_criteria"])
        if not criterios:
            raise HTTPException(
                status_code=422,
                detail=(
                    "o plano precisa de ao menos um critério de aceite: "
                    "é o que a revisão confere"
                ),
            )
        plano.acceptance_criteria = criterios
    if "affected_files" in mudancas:
        plano.affected_files = [f.strip() for f in mudancas["affected_files"] if f.strip()]
    if "roadmap" in mudancas:
        plano.roadmap = mudancas["roadmap"].strip()

    session.add(plano)
    session.add(
        TaskStateHistory(
            task_id=task.id,
            from_status=task.status,
            to_status=task.status,
            note="plano editado por uma pessoa - " + ", ".join(sorted(mudancas)),
        )
    )
    session.commit()
    return {"task_id": task_id, "editado": sorted(mudancas)}


@router.post("/tasks/{task_id}/replan")
def replanejar(
    task_id: int,
    background: BackgroundTasks,
    session: Session = Depends(get_session),
) -> dict:
    """Refaz o planejamento do zero e recomeça.

    Diferente de retomar: aquilo tenta de novo com o mesmo plano, isto joga o
    plano fora. Serve para quando o problema não foi a execução e sim o
    planejamento - arquivos errados, escopo mal entendido, estimativa absurda.

    O gasto anterior **não** é apagado: ele aconteceu e continua contando contra
    o teto. Quem quiser recomeçar o orçamento também, sobe o teto explicitamente.
    """
    task = session.get(Task, task_id)
    if task is None:
        raise HTTPException(status_code=404, detail="tarefa não encontrada")
    replanejaveis = {states.SUSPENSA, states.EM_HOMOLOGACAO}
    if task.status not in replanejaveis:
        raise HTTPException(
            status_code=409,
            detail=(
                f"não dá para replanejar uma tarefa em '{task.status}'; "
                "ela precisa estar suspensa ou em homologação"
            ),
        )

    estava_suspensa = task.status == states.SUSPENSA
    states.transicionar(
        session,
        task,
        states.EM_PLANEJAMENTO,
        note="replanejamento pedido pelo gestor",
        alert="none",
    )
    if estava_suspensa:
        suspensao.restaurar_dependentes(session, task_id)
    session.commit()
    background.add_task(chain.rodar_replanejamento, task_id)
    return {"task_id": task_id, "status": states.EM_PLANEJAMENTO}


@router.post("/tasks/{task_id}/homologation")
def homologar(
    task_id: int,
    payload: HomologationIn,
    background: BackgroundTasks,
    session: Session = Depends(get_session),
) -> dict:
    """Aprovar, ajustar ou recusar o que o Executor produziu (§5)."""
    task = session.get(Task, task_id)
    if task is None:
        raise HTTPException(status_code=404, detail="tarefa não encontrada")

    try:
        resultado = homologation.decidir(session, task, payload.decision, payload.comment)
    except homologation.ComentarioObrigatorioError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except homologation.HomologacaoError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc

    session.commit()

    if payload.decision == homologation.AJUSTAR:
        background.add_task(
            chain.rodar_execucao, task_id, trigger="ajuste", comentario=payload.comment
        )
    elif task.status == states.FINALIZADA:
        # Ordem importa (§4.4.4): as tarefas de fundo rodam uma depois da outra.
        # O CI da develop e a sugestão de contexto falam da entrega que acabou de
        # ser aprovada e vêm primeiro; liberar quem esperava só dispara as
        # execuções em threads próprias e devolve na hora.
        if resultado.get("merged"):
            # O CI da develop leva minutos: roda depois de responder.
            background.add_task(delivery.rodar_ci_da_develop, task_id)
            # O que foi aprovado pode ter deixado o contexto desatualizado.
            background.add_task(context_suggestions.gerar_para_tarefa, task_id)
        background.add_task(chain.liberar_quem_esperava, task_id)

    return {"task_id": task_id, "decision": payload.decision, **resultado}


@router.post("/tasks/{task_id}/revert")
def reverter(
    task_id: int,
    payload: RevertIn,
    session: Session = Depends(get_session),
) -> dict:
    """Desfaz o merge de uma tarefa já integrada.

    A verificação automática pode passar e o resultado ainda estar errado. Sem
    este caminho, o humano que descobre o problema depois do merge só tem `git`
    na unha - e uma decisão tomada fora do sistema não vira registro.
    """
    task = session.get(Task, task_id)
    if task is None:
        raise HTTPException(status_code=404, detail="tarefa não encontrada")

    try:
        resultado = homologation.reverter(session, task, payload.reason)
    except homologation.ReversaoError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc

    session.commit()
    return {"task_id": task_id, **resultado}


class RedoIn(BaseModel):
    feedback: str = Field(min_length=1)


@router.post("/tasks/{task_id}/redo", status_code=status.HTTP_201_CREATED)
def refazer(
    task_id: int,
    payload: RedoIn,
    background: BackgroundTasks,
    session: Session = Depends(get_session),
) -> dict:
    """Tentativa nova da mesma demanda, com o que estava errado na anterior.

    Tarefa aprovada é revertida no mesmo gesto. A nova vai direto para o
    planejamento - o funil já foi feito, e uma pessoa acabou de decidir de novo.
    """
    task = session.get(Task, task_id)
    if task is None:
        raise HTTPException(status_code=404, detail="tarefa não encontrada")

    try:
        nova = redo.refazer(session, task, payload.feedback)
    except (redo.RefazerError, homologation.ReversaoError) as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc

    session.commit()
    background.add_task(chain.rodar_cadeia, nova.id)
    return {"task_id": nova.id, "parent_task_id": task_id, "status": nova.status}


# --------------------------------------------------------------------------- #
# Incidentes e urgência
# --------------------------------------------------------------------------- #

#: Peso de cada severidade no Fator de Urgência (§2). Soma simples nesta fase;
#: SLA e decaimento temporal estão no SPEC-10.
PESO_URGENCIA = {"alto": 3.0, "medio": 1.0, "baixo": 0.0}


@router.post("/incidents", status_code=status.HTTP_201_CREATED)
def criar_incidente(payload: IncidentIn, session: Session = Depends(get_session)) -> dict:
    """Cria o incidente e recalcula a urgência das candidatas do módulo afetado."""
    incidente = Incident(
        title=payload.title,
        description=payload.description,
        severity=payload.severity,
        module=payload.module,
        source="manual",
    )
    session.add(incidente)
    session.flush()

    peso = PESO_URGENCIA[payload.severity]
    afetadas: list[int] = []
    if peso and payload.module:
        candidatas = session.execute(
            select(Task)
            .where(Task.status == states.CANDIDATA)
            .where(Task.module == payload.module)
        ).scalars().all()
        for task in candidatas:
            task.urgency_score = (task.urgency_score or 0.0) + peso
            session.add(task)
            afetadas.append(task.id)

    session.commit()
    logger.info(
        "incidente #%s (%s/%s) elevou a urgência de %d tarefa(s)",
        incidente.id,
        payload.severity,
        payload.module,
        len(afetadas),
    )
    return {"incident_id": incidente.id, "urgency_applied": peso, "tasks_affected": afetadas}


@router.get("/discards")
def listar_descartes(session: Session = Depends(get_session)) -> list[dict]:
    """Histórico de Descartes, para a aba Descartadas do painel (SPEC-06 §2).

    Duplicata mostra contra o que bateu e quantas vezes; incoerência e recusa
    humana mostram o texto do motivo. Nenhum SPEC previu este endpoint, mas a
    tela depende dele.
    """
    descartes = session.execute(
        select(DiscardedProposal).order_by(DiscardedProposal.id.desc())
    ).scalars().all()
    propostas = {p.id: p for p in session.execute(select(Proposal)).scalars().all()}

    return [
        {
            "id": d.id,
            "reason_type": d.reason_type,
            "reason_text": d.reason_text,
            "matched_ref": d.matched_ref,
            "duplicate_count": d.duplicate_count,
            "task_id": d.task_id,
            "title": (
                propostas[d.proposal_id].title
                if d.proposal_id in propostas
                else None
            ),
            "origin": (
                propostas[d.proposal_id].origin if d.proposal_id in propostas else None
            ),
            "created_at": d.created_at,
        }
        for d in descartes
    ]


@router.get("/incidents")
def listar_incidentes(session: Session = Depends(get_session)) -> list[dict]:
    incidentes = session.execute(select(Incident).order_by(Incident.id.desc())).scalars().all()
    return [
        {
            "id": i.id,
            "title": i.title,
            "description": i.description,
            "severity": i.severity,
            "module": i.module,
            "source": i.source,
            "resolved": i.resolved,
            "created_at": i.created_at,
        }
        for i in incidentes
    ]


# --------------------------------------------------------------------------- #
# Instrumentos de demonstração e artefatos
# --------------------------------------------------------------------------- #


@router.patch("/tasks/{task_id}/demo")
def configurar_demo(
    task_id: int,
    payload: DemoIn,
    session: Session = Depends(get_session),
) -> dict:
    """Injeta falha controlada ou teto de tokens - só com DEMO_MODE=true (§3)."""
    if not settings.demo_mode:
        raise HTTPException(status_code=403, detail="DEMO_MODE está desligado")

    task = session.get(Task, task_id)
    if task is None:
        raise HTTPException(status_code=404, detail="tarefa não encontrada")

    if payload.force_fail_runs is not None:
        task.demo_force_fail_runs = payload.force_fail_runs
    if payload.budget_cap_tokens is not None:
        task.demo_budget_cap_tokens = payload.budget_cap_tokens

    session.add(task)
    session.commit()
    return {
        "task_id": task_id,
        "demo_force_fail_runs": task.demo_force_fail_runs,
        "demo_budget_cap_tokens": task.demo_budget_cap_tokens,
    }


ARTEFATOS = {
    "diff": "diff_path",
    "logs": "log_path",
    "transcript": "transcript_path",
    "review": "review_path",
}


@router.get("/runs/{run_id}/artifact/{tipo}", response_class=PlainTextResponse)
def servir_artefato(
    run_id: int,
    tipo: str,
    session: Session = Depends(get_session),
) -> str:
    """Serve diff, log de lint/teste ou transcript de uma run (§3)."""
    if tipo not in ARTEFATOS:
        raise HTTPException(status_code=404, detail=f"artefato desconhecido: {tipo}")

    run = session.get(ExecutionRun, run_id)
    if run is None:
        raise HTTPException(status_code=404, detail="run não encontrada")

    caminho = getattr(run, ARTEFATOS[tipo])
    if not caminho or not Path(caminho).exists():
        raise HTTPException(status_code=404, detail=f"esta run não produziu '{tipo}'")

    return Path(caminho).read_text(encoding="utf-8")


# --------------------------------------------------------------------------- #
# Grafo de dependências e edição da tarefa (Fase 2 do roadmap)
# --------------------------------------------------------------------------- #


class DependenciaIn(BaseModel):
    depends_on: int
    reason: str | None = None


class TarefaIn(BaseModel):
    """Campos editáveis de uma tarefa.

    Só metadados de julgamento. Estado, desfecho e branch não entram: eles são
    consequência do que aconteceu e mudá-los na mão apagaria o rastro.
    """

    title: str | None = Field(default=None, min_length=1, max_length=200)
    description: str | None = None
    module: str | None = None
    risk_tier: Literal["baixo", "medio", "alto"] | None = None
    change_type: Literal["feature", "fix", "refactor", "docs", "test", "chore"] | None = None
    impact: int | None = Field(default=None, ge=1, le=5)
    complexity: int | None = Field(default=None, ge=1, le=5)
    #: Quanto as estimativas merecem crédito. Quem corrige uma estimativa à mão
    #: pode dizer que agora confia nela.
    confidence: float | None = Field(default=None, ge=0, le=1)
    #: Teto de tokens. `0` remove o teto manual e devolve o cálculo automático.
    budget_cap_tokens: int | None = Field(default=None, ge=0)
    #: Exigir aprovação do plano antes de qualquer código. Só vale até o plano sair.
    plan_approval_required: bool | None = None


@router.get("/graph")
def ver_grafo(session: Session = Depends(get_session)) -> dict:
    """Nós e arestas para o painel desenhar o pipeline."""
    return dependencies.grafo(session)


@router.post("/tasks/{task_id}/dependencies")
def criar_dependencia(
    task_id: int,
    payload: DependenciaIn,
    session: Session = Depends(get_session),
) -> dict:
    """Liga duas tarefas à mão. Aresta manual não é desfeita por recálculo."""
    if session.get(Task, task_id) is None:
        raise HTTPException(status_code=404, detail="tarefa não encontrada")
    if session.get(Task, payload.depends_on) is None:
        raise HTTPException(status_code=404, detail="tarefa de destino não encontrada")

    try:
        aresta = dependencies.ligar(
            session,
            task_id,
            payload.depends_on,
            kind=dependencies.DEP_MANUAL,
            reason=payload.reason,
        )
    except dependencies.DependenciaInvalidaError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc

    session.commit()
    return {
        "task_id": task_id,
        "depends_on": payload.depends_on,
        "criada": aresta is not None,
    }


@router.delete("/tasks/{task_id}/dependencies/{depends_on}")
def remover_dependencia(
    task_id: int,
    depends_on: int,
    session: Session = Depends(get_session),
) -> dict:
    removida = dependencies.desligar(session, task_id, depends_on)
    if not removida:
        raise HTTPException(status_code=404, detail="essa dependência não existe")
    session.commit()
    return {"task_id": task_id, "depends_on": depends_on, "removida": True}


@router.patch("/tasks/{task_id}")
def editar_tarefa(
    task_id: int,
    payload: TarefaIn,
    session: Session = Depends(get_session),
) -> dict:
    """Corrige os metadados de julgamento de uma tarefa.

    A edição fica registrada em `task_state_history`: mudar a prioridade ou o
    risco de uma tarefa é uma decisão, e decisão sem registro não é rastreável.
    """
    task = session.get(Task, task_id)
    if task is None:
        raise HTTPException(status_code=404, detail="tarefa não encontrada")
    if task.status == states.FINALIZADA:
        raise HTTPException(status_code=409, detail="tarefa finalizada não é editável")

    mudancas = payload.model_dump(exclude_none=True)
    if not mudancas:
        raise HTTPException(status_code=422, detail="nada para mudar")

    # Zero é o comando explícito da API para voltar ao cálculo automático.
    # Persisti-lo criaria um teto manual no qual chamada nenhuma cabe.
    if mudancas.get("budget_cap_tokens") == 0:
        mudancas["budget_cap_tokens"] = None

    aplicadas = []
    for campo, valor in mudancas.items():
        anterior = getattr(task, campo)
        if anterior == valor:
            continue
        setattr(task, campo, valor)
        aplicadas.append(f"{campo}: {anterior!r} → {valor!r}")

    if not aplicadas:
        return {"task_id": task_id, "alterado": []}

    # Confiança e incerteza andam juntas; mexer numa sem a outra mentiria no selo.
    # O marcador é regra fixa (§4.4.1), recalculada aqui como na Qualificação.
    if {"impact", "complexity", "confidence"} & set(mudancas):
        if "impact" in mudancas or "complexity" in mudancas:
            aplicadas.append("prioridade recalculada")
        marcador = incerteza(task.impact, task.complexity, task.confidence or 0.0)
        if marcador != task.uncertainty:
            aplicadas.append(f"incerteza: {task.uncertainty!r} → {marcador!r}")
            task.uncertainty = marcador

    session.add(task)
    session.add(
        TaskStateHistory(
            task_id=task.id,
            from_status=task.status,
            to_status=task.status,
            note="editada no painel - " + "; ".join(aplicadas),
        )
    )
    session.commit()
    return {"task_id": task_id, "alterado": aplicadas}


@router.post("/tasks/{task_id}/cancel")
def cancelar(
    task_id: int,
    payload: RejectIn,
    background: BackgroundTasks,
    session: Session = Depends(get_session),
) -> dict:
    """Interrompe uma tarefa antes do fim.

    Em execução, o cancelamento é **cooperativo**: a tarefa vai para `suspensa`
    e o Executor percebe no próximo ponto de checagem, antes da chamada seguinte
    ao modelo. Matar o processo no meio deixaria o clone pela metade e um custo
    de LLM já gasto sem registro - e o gate humano é estado registrado, nunca
    processo morto à força.
    """
    task = session.get(Task, task_id)
    if task is None:
        raise HTTPException(status_code=404, detail="tarefa não encontrada")
    if task.status == states.FINALIZADA:
        raise HTTPException(status_code=409, detail="tarefa já finalizada")

    era_execucao = task.status == states.EM_EXECUCAO
    descarte = None
    if payload.remember:
        # Cancelar é rejeitar mais tarde: o modelo manda a rejeição humana para o
        # Histórico de Descartadas, e é ele que impede a mesma demanda de voltar.
        descarte = homologation.registrar_descarte(session, task, payload.reason)
    homologation.encerrar_proposta(session, task, OUTCOME_RECUSADA)
    states.transicionar(
        session,
        task,
        states.FINALIZADA,
        note=f"cancelada: {payload.reason}"
        + ("" if payload.remember else " (sem registro de descarte)"),
        alert="none",
        final_outcome="cancelada",
    )
    # Quem foi suspensa por causa desta deixa de esperá-la: a aresta cai e a
    # tarefa volta ao estado em que estava, podendo ser despachada.
    restauradas = suspensao.restaurar_dependentes(session, task_id, remover_aresta=True)
    session.commit()
    background.add_task(chain.liberar_quem_esperava, task_id)
    if restauradas:
        background.add_task(chain.despachar_em_paralelo, restauradas)
    return {
        "task_id": task_id,
        "status": task.status,
        "final_outcome": "cancelada",
        "cooperativo": era_execucao,
        "discard_id": descarte.id if descarte else None,
    }
