"""Endpoints do fluxo de entrega: develop, releases e publicação.

O painel consome `GET /api/delivery` como uma foto do fluxo inteiro e age pelos
demais. Cada ação que o guia coloca sob decisão humana - aprovar nos testes,
abrir o PR, publicar - exige o texto de quem decidiu.
"""

from __future__ import annotations

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.common import git_service, github, pipeline_rules
from app.common.db import get_session
from app.orchestration import delivery
from app.orchestration.models import PipelineEvent, Release
from app.task_layer.models import Task

router = APIRouter(prefix="/api/delivery", tags=["delivery"])


def _tarefa(task: Task) -> dict:
    return {
        "id": task.id,
        "title": task.title,
        "module": task.module,
        "change_type": task.change_type,
        "risk_tier": task.risk_tier,
        "branch": task.branch_name,
        "stage": task.stage,
        "tested_ok": task.tested_ok,
        "tested_note": task.tested_note,
        "release_id": task.release_id,
        "merge_commit": task.merge_commit,
        "alert": task.alert,
        "updated_at": task.updated_at,
    }


def _release(release: Release, tarefas: list[Task]) -> dict:
    return {
        "id": release.id,
        "version": release.version,
        "branch": release.branch,
        "status": release.status,
        "changelog": release.changelog,
        "validation_ok": release.validation_ok,
        "pr_number": release.pr_number,
        "pr_url": release.pr_url,
        "pr_body": release.pr_body,
        "approval_note": release.approval_note,
        "tag": release.tag,
        "publish_commit": release.publish_commit,
        "created_at": release.created_at,
        "published_at": release.published_at,
        "tasks": [_tarefa(t) for t in tarefas],
    }


def _por_release(session: Session) -> dict[int, list[Task]]:
    agrupadas: dict[int, list[Task]] = {}
    for t in session.execute(
        select(Task).where(Task.release_id.is_not(None)).order_by(Task.id)
    ).scalars():
        agrupadas.setdefault(t.release_id, []).append(t)
    return agrupadas


@router.get("")
def ver_entrega(session: Session = Depends(get_session)) -> dict:
    """O fluxo inteiro: o que está na develop, as releases e o rastro."""
    na_develop = session.execute(
        select(Task).where(Task.stage == delivery.ESTAGIO_DEVELOP).order_by(Task.id)
    ).scalars().all()
    por_release = _por_release(session)
    releases = session.execute(select(Release).order_by(Release.id.desc())).scalars().all()
    eventos = session.execute(
        select(PipelineEvent).order_by(PipelineEvent.id.desc()).limit(40)
    ).scalars().all()

    ultimo_ci = next((e for e in eventos if e.branch == "develop" and e.kind == "ci"), None)
    tags = git_service.tags()

    return {
        "principal": git_service.main_branch(),
        "versao_atual": tags[0] if tags else None,
        "versao_sugerida": delivery.versao_sugerida(),
        "github": github.ativo(),
        "develop": {
            "tarefas": [_tarefa(t) for t in na_develop],
            "ultimo_ci": None
            if ultimo_ci is None
            else {"ok": ultimo_ci.ok, "at": ultimo_ci.at, "detail": ultimo_ci.detail},
        },
        "releases": [_release(r, por_release.get(r.id, [])) for r in releases],
        "eventos": [
            {
                "id": e.id,
                "branch": e.branch,
                "kind": e.kind,
                "ok": e.ok,
                "task_id": e.task_id,
                "release_id": e.release_id,
                "commit": e.commit,
                "detail": e.detail,
                "at": e.at,
            }
            for e in eventos
        ],
        "regras": [
            {"origem": o, "destino": d, "metodo": m}
            for (o, d), m in pipeline_rules.INTEGRACOES_PERMITIDAS.items()
        ],
    }


def _erro(exc: Exception) -> HTTPException:
    codigo = 409 if isinstance(exc, delivery.EntregaError) else 422
    return HTTPException(status_code=codigo, detail=str(exc))


def _task(session: Session, task_id: int) -> Task:
    task = session.get(Task, task_id)
    if task is None:
        raise HTTPException(status_code=404, detail="tarefa não encontrada")
    return task


def _release_por_id(session: Session, release_id: int) -> Release:
    release = session.get(Release, release_id)
    if release is None:
        raise HTTPException(status_code=404, detail="release não encontrada")
    return release


class NotaIn(BaseModel):
    note: str = Field(min_length=1)


@router.post("/tasks/{task_id}/test-approve")
def aprovar_nos_testes(
    task_id: int, payload: NotaIn, session: Session = Depends(get_session)
) -> dict:
    """Aprovação funcional no ambiente de testes (develop)."""
    task = _task(session, task_id)
    try:
        delivery.aprovar_nos_testes(session, task, payload.note)
    except delivery.EntregaError as exc:
        raise _erro(exc) from exc
    session.commit()
    return {"task_id": task_id, "tested_ok": True}


class ReleaseIn(BaseModel):
    version: str | None = None
    level: str = "minor"


@router.post("/releases", status_code=201)
def criar_release(payload: ReleaseIn, session: Session = Depends(get_session)) -> dict:
    """Abre `release/x.x.x` a partir da principal. Sem versão, sugere a próxima."""
    versao = payload.version or delivery.versao_sugerida(payload.level)
    try:
        release = delivery.criar_release(session, versao)
    except (delivery.EntregaError, pipeline_rules.PipelineError) as exc:
        raise _erro(exc) from exc
    session.commit()
    return _release(release, [])


class IncluirIn(BaseModel):
    task_id: int


@router.post("/releases/{release_id}/tasks")
def incluir(
    release_id: int, payload: IncluirIn, session: Session = Depends(get_session)
) -> dict:
    release = _release_por_id(session, release_id)
    task = _task(session, payload.task_id)
    try:
        resultado = delivery.incluir_na_release(session, release, task)
    except (delivery.EntregaError, pipeline_rules.PipelineError) as exc:
        raise _erro(exc) from exc
    session.commit()
    return resultado


@router.delete("/releases/{release_id}/tasks/{task_id}")
def retirar(release_id: int, task_id: int, session: Session = Depends(get_session)) -> dict:
    release = _release_por_id(session, release_id)
    task = _task(session, task_id)
    try:
        delivery.remover_da_release(session, release, task)
    except (delivery.EntregaError, git_service.MergeConflictError) as exc:
        raise _erro(exc) from exc
    session.commit()
    return {"retirada": True}


class ChangelogIn(BaseModel):
    changelog: str


@router.put("/releases/{release_id}/changelog")
def editar_changelog(
    release_id: int, payload: ChangelogIn, session: Session = Depends(get_session)
) -> dict:
    release = _release_por_id(session, release_id)
    if release.status not in delivery.EDITAVEL:
        raise HTTPException(
            status_code=409, detail="o changelog só se edita antes do Pull Request"
        )
    release.changelog = payload.changelog.strip()
    session.add(release)
    session.commit()
    return {"changelog": release.changelog}


@router.post("/releases/{release_id}/validate")
def validar(
    release_id: int, background: BackgroundTasks, session: Session = Depends(get_session)
) -> dict:
    """Validação final em segundo plano: as suítes inteiras, com tudo integrado."""
    release = _release_por_id(session, release_id)
    try:
        delivery.iniciar_validacao(session, release)
    except delivery.EntregaError as exc:
        raise _erro(exc) from exc
    session.commit()
    background.add_task(delivery.rodar_validacao_da_release, release_id)
    return {"release_id": release_id, "status": "validando"}


@router.post("/releases/{release_id}/pull-request")
def abrir_pr(release_id: int, session: Session = Depends(get_session)) -> dict:
    release = _release_por_id(session, release_id)
    try:
        delivery.abrir_pr(session, release)
    except (delivery.EntregaError, github.GitHubError) as exc:
        raise _erro(exc) from exc
    session.commit()
    return {"release_id": release_id, "status": release.status, "pr_url": release.pr_url}


@router.post("/releases/{release_id}/publish")
def publicar(
    release_id: int, payload: NotaIn, session: Session = Depends(get_session)
) -> dict:
    """Merge da release na principal, tag e publicação. Decisão humana por escrito."""
    release = _release_por_id(session, release_id)
    try:
        resultado = delivery.publicar(session, release, payload.note)
    except delivery.EntregaError as exc:
        raise _erro(exc) from exc
    session.commit()
    return resultado


@router.post("/releases/{release_id}/cancel")
def cancelar(
    release_id: int, payload: NotaIn, session: Session = Depends(get_session)
) -> dict:
    release = _release_por_id(session, release_id)
    try:
        delivery.cancelar_release(session, release, payload.note)
    except delivery.EntregaError as exc:
        raise _erro(exc) from exc
    session.commit()
    return {"release_id": release_id, "status": "cancelada"}
