"""Entrega: o caminho de uma tarefa homologada até a produção.

Segue o guia de fluxo de ramos (documento `git-guide` do contexto):

    feature/* ──merge──▶ develop ──(aprovada nos testes)──▶ release/x.x.x ──PR──▶ main ──▶ tag

A Homologação deixou de ser o ponto em que o código chega à principal. Aprovar
integra na `develop`, que é o ambiente de testes; uma pessoa aprova funcionalmente
ali; a tarefa entra numa release; e só a release inteira chega à principal, por um
Pull Request que outra decisão humana libera.

Três escolhas que merecem registro:

1. **As regras vivem em `pipeline_rules`, não aqui.** Este módulo decide *quando*;
   quem diz *o que é permitido* é um módulo sem efeito colateral, testável sozinho.
2. **O CI roda depois do merge, em segundo plano.** Rodar lint, tipos, testes e
   `next build` custa minutos; segurar a requisição da Homologação por isso faria a
   tela parecer travada. Se o CI reprova, a integração é desfeita - o guia permite
   "correção ou reversão", e reverter é o que mantém a develop sempre utilizável.
3. **Sem GitHub configurado, o PASE é o Pull Request.** A aprovação humana, o CI
   verde e o texto do PR são exigidos do mesmo jeito; só o merge na principal é
   local. Com `GITHUB_TOKEN`, o PR é aberto e mergeado de verdade.
"""

from __future__ import annotations

import logging
import shutil
from pathlib import Path

from git import GitCommandError, Repo
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.common import conventions, git_service, github, pipeline_rules
from app.common.config import settings
from app.common.db import session_scope
from app.common.git_service import MergeConflictError
from app.common.pipeline_rules import PipelineError
from app.orchestration import states
from app.orchestration.models import PipelineEvent, PlanningDocument, Release
from app.task_layer.models import (
    OUTCOME_REVERTIDA,
    ImplementedItem,
    Task,
)

logger = logging.getLogger("pase.delivery")

ESTAGIO_DEVELOP = "develop"
ESTAGIO_RELEASE = "release"
ESTAGIO_PRODUCAO = "producao"

#: Nada além disto muda numa release que já abriu o PR.
EDITAVEL = ("aberta", "validada")


class EntregaError(RuntimeError):
    """A operação não é permitida no estado atual da entrega."""


# --------------------------------------------------------------------------- #
# Registro
# --------------------------------------------------------------------------- #


def registrar(
    session: Session,
    branch: str,
    kind: str,
    *,
    ok: bool = True,
    task_id: int | None = None,
    release_id: int | None = None,
    commit: str | None = None,
    detail: str = "",
    log_path: str | None = None,
) -> PipelineEvent:
    evento = PipelineEvent(
        branch=branch,
        kind=kind,
        ok=ok,
        task_id=task_id,
        release_id=release_id,
        commit=commit,
        detail=detail,
        log_path=log_path,
    )
    session.add(evento)
    session.flush()
    logger.info("pipeline %s %s %s: %s", branch, kind, "ok" if ok else "FALHOU", detail)
    return evento


def _pasta_de_logs() -> Path:
    pasta = Path(settings.artifacts_path) / "pipeline"
    pasta.mkdir(parents=True, exist_ok=True)
    return pasta


# --------------------------------------------------------------------------- #
# CI
# --------------------------------------------------------------------------- #


def _rodar_ci(branch: str, nome_do_log: str) -> tuple[bool, str, str]:
    """Lint, tipos, testes e build de `branch`, num clone próprio.

    Devolve `(passou, log, caminho_do_log)`. Clone novo e descartável: o CI não
    pode herdar nada de quem o chamou, senão "passou aqui" não diz nada sobre a
    branch.
    """
    # Importado aqui: o executor importa meio sistema, e a entrega só precisa dele
    # quando de fato roda o gate.
    from app.execution import executor

    destino = git_service.WORKSPACE_ROOT / f"ci-{nome_do_log}"
    shutil.rmtree(destino, ignore_errors=True)
    try:
        repo = Repo.clone_from(settings.repo_path, destino, branch=branch)
        git_service.configurar_autor(repo)
        passou, log = executor.verificar(destino)
    finally:
        shutil.rmtree(destino, ignore_errors=True)

    caminho = _pasta_de_logs() / f"{nome_do_log}.log"
    caminho.write_text(log, encoding="utf-8")
    return passou, log, str(caminho)


# --------------------------------------------------------------------------- #
# Tarefa → develop
# --------------------------------------------------------------------------- #


def integrar_na_develop(session: Session, task: Task, mensagem: str) -> dict:
    """Merge direto da branch da tarefa na `develop`. O CI roda depois, em segundo plano."""
    if not task.branch_name:
        raise EntregaError(f"a task #{task.id} não tem branch")

    try:
        with git_service.clone_de_entrega() as repo:
            git_service.garantir_develop(repo)
            sha = git_service.integrar(repo, task.branch_name, pipeline_rules.DEVELOP, mensagem)
    except MergeConflictError as exc:
        task.alert = "merge_conflict"
        session.add(task)
        registrar(
            session, pipeline_rules.DEVELOP, "integracao", ok=False, task_id=task.id,
            detail=str(exc),
        )
        return {"merged": False, "alert": "merge_conflict", "detail": str(exc)}
    except PipelineError as exc:
        registrar(
            session, pipeline_rules.DEVELOP, "integracao", ok=False, task_id=task.id,
            detail=str(exc),
        )
        return {"merged": False, "alert": "none", "detail": str(exc)}

    task.merge_commit = sha
    task.stage = ESTAGIO_DEVELOP
    session.add(task)
    registrar(
        session, pipeline_rules.DEVELOP, "integracao", task_id=task.id, commit=sha,
        detail=f"{task.branch_name} → develop",
    )
    return {"merged": True, "commit": sha, "stage": ESTAGIO_DEVELOP}


def rodar_ci_da_develop(task_id: int) -> None:
    """CI da develop depois de uma integração. Reprovou, desfaz a integração.

    O guia diz que falha no pipeline bloqueia novas integrações até correção ou
    reversão. Reverter na hora é a opção que não deixa a develop quebrada à espera
    de alguém: o próximo merge de outra tarefa não herda o defeito desta.
    """
    if not settings.delivery_ci_enabled:
        return
    try:
        with session_scope() as session:
            task = session.get(Task, task_id)
            if task is None or task.stage != ESTAGIO_DEVELOP:
                return
            sha = task.merge_commit
            passou, log, caminho = _rodar_ci(pipeline_rules.DEVELOP, f"develop-task-{task_id}")
            registrar(
                session, pipeline_rules.DEVELOP, "ci", ok=passou, task_id=task_id, commit=sha,
                detail="CI da develop " + ("passou" if passou else "reprovou"), log_path=caminho,
            )
            if passou:
                return

            # CI reprovado: a integração sai da develop e a tarefa volta a ser
            # tratada como não entregue.
            with git_service.clone_de_entrega() as repo:
                revert = git_service.reverter_integracao(
                    repo,
                    pipeline_rules.DEVELOP,
                    sha,
                    f"revert: desfaz {task.title} da develop (CI reprovado, task #{task_id})",
                )
            registrar(
                session, pipeline_rules.DEVELOP, "reversao", task_id=task_id, commit=revert,
                detail="integração desfeita porque o CI da develop reprovou",
            )
            _dar_baixa(session, task, OUTCOME_REVERTIDA)
            task.stage = None
            task.alert = "ci_develop"
            states.registrar_desfecho(
                session, task, "revertida",
                note="o CI da develop reprovou depois do merge; a integração foi desfeita. "
                f"Log: {caminho}",
            )
    except Exception:  # pragma: no cover - rede de segurança do background
        logger.exception("CI da develop falhou para a task #%s", task_id)


def _dar_baixa(session: Session, task: Task, desfecho: str) -> None:
    """Tira a tarefa da memória: pedir de novo volta a ser um pedido legítimo."""
    from app.orchestration import homologation

    session.query(ImplementedItem).filter(ImplementedItem.task_id == task.id).delete()
    homologation.encerrar_proposta(session, task, desfecho)


def aprovar_nos_testes(session: Session, task: Task, nota: str) -> None:
    """Aprovação funcional no ambiente de testes - a porta de entrada de uma release."""
    if task.stage != ESTAGIO_DEVELOP:
        raise EntregaError(
            f"a task #{task.id} não está na develop (estágio: {task.stage or 'nenhum'})"
        )
    if not nota.strip():
        raise EntregaError("a aprovação nos testes exige uma nota: o que foi conferido")
    task.tested_ok = True
    task.tested_note = nota.strip()
    session.add(task)
    registrar(
        session, pipeline_rules.DEVELOP, "aprovacao", task_id=task.id,
        detail=f"aprovada nos testes: {nota.strip()}",
    )


# --------------------------------------------------------------------------- #
# Releases
# --------------------------------------------------------------------------- #


def versao_sugerida(nivel: str = "minor") -> str:
    ultima = git_service.tags()
    return pipeline_rules.proxima_versao(ultima[0] if ultima else None, nivel)


def criar_release(session: Session, versao: str) -> Release:
    """`release/x.x.x` a partir da principal."""
    pipeline_rules.validar_versao(versao)
    if session.execute(select(Release).where(Release.version == versao)).scalar_one_or_none():
        raise EntregaError(f"a release {versao} já existe")

    with git_service.clone_de_entrega() as repo:
        branch = git_service.criar_release(repo, versao)

    release = Release(version=versao, branch=branch, status="aberta")
    session.add(release)
    session.flush()
    registrar(
        session, branch, "release", release_id=release.id,
        detail=f"release {versao} criada a partir da principal",
    )
    return release


def _tarefas_da(session: Session, release: Release) -> list[Task]:
    return list(
        session.execute(
            select(Task).where(Task.release_id == release.id).order_by(Task.id)
        ).scalars()
    )


def _exige_editavel(release: Release) -> None:
    if release.status not in EDITAVEL:
        raise EntregaError(
            f"a release {release.version} está '{release.status}': só se altera a "
            "composição antes do Pull Request."
        )


def incluir_na_release(session: Session, release: Release, task: Task) -> dict:
    """Merge direto da tarefa na release. Só entra o que foi aprovado nos testes."""
    _exige_editavel(release)
    if task.stage != ESTAGIO_DEVELOP:
        raise EntregaError(
            f"a task #{task.id} precisa estar na develop para entrar numa release "
            f"(estágio: {task.stage or 'nenhum'})"
        )
    if not task.tested_ok:
        raise EntregaError(
            f"a task #{task.id} ainda não foi aprovada nos testes: o guia só deixa entrar "
            "numa release o que passou pelo ambiente de testes."
        )

    mensagem = conventions.merge_de(task.id, task.title, task.module, task.change_type)
    try:
        with git_service.clone_de_entrega() as repo:
            sha = git_service.integrar(repo, task.branch_name, release.branch, mensagem)
    except MergeConflictError as exc:
        registrar(
            session, release.branch, "integracao", ok=False, task_id=task.id,
            release_id=release.id, detail=str(exc),
        )
        return {"incluida": False, "detail": str(exc)}

    task.stage = ESTAGIO_RELEASE
    task.release_id = release.id
    task.release_commit = sha
    session.add(task)

    linha = f"- {task.title} (task #{task.id})"
    if f"(task #{task.id})" not in release.changelog:
        release.changelog = (release.changelog.rstrip() + "\n" + linha).strip()
    # A composição mudou: a validação anterior não vale mais.
    release.status = "aberta"
    release.validation_ok = None
    session.add(release)
    registrar(
        session, release.branch, "integracao", task_id=task.id, release_id=release.id,
        commit=sha, detail=f"{task.branch_name} → {release.branch}",
    )
    return {"incluida": True, "commit": sha}


def remover_da_release(session: Session, release: Release, task: Task) -> None:
    """Desfaz a integração da tarefa na release; ela volta à develop."""
    _exige_editavel(release)
    if task.release_id != release.id or task.stage != ESTAGIO_RELEASE:
        raise EntregaError(f"a task #{task.id} não está na release {release.version}")

    with git_service.clone_de_entrega() as repo:
        revert = git_service.reverter_integracao(
            repo, release.branch, task.release_commit,
            f"revert: tira {task.title} da release {release.version} (task #{task.id})",
        )
    task.stage = ESTAGIO_DEVELOP
    task.release_id = None
    task.release_commit = None
    release.changelog = "\n".join(
        linha
        for linha in release.changelog.splitlines()
        if f"(task #{task.id})" not in linha
    )
    release.status = "aberta"
    release.validation_ok = None
    session.add_all([task, release])
    registrar(
        session, release.branch, "reversao", task_id=task.id, release_id=release.id,
        commit=revert, detail="tarefa retirada da release",
    )


def iniciar_validacao(session: Session, release: Release) -> None:
    _exige_editavel(release)
    if not _tarefas_da(session, release):
        raise EntregaError("a release está vazia: inclua ao menos uma tarefa aprovada nos testes")
    release.status = "validando"
    session.add(release)


def rodar_validacao_da_release(release_id: int) -> None:
    """Validação final: as suítes completas, na branch da release, com tudo integrado."""
    try:
        with session_scope() as session:
            release = session.get(Release, release_id)
            if release is None or release.status != "validando":
                return
            if settings.delivery_ci_enabled:
                passou, _, caminho = _rodar_ci(release.branch, f"release-{release.version}")
            else:
                passou, caminho = True, None
            release.validation_ok = passou
            release.validation_log_path = caminho
            release.status = "validada" if passou else "aberta"
            session.add(release)
            registrar(
                session, release.branch, "ci", ok=passou, release_id=release.id,
                detail="validação final " + ("passou" if passou else "reprovou"),
                log_path=caminho,
            )
    except Exception:  # pragma: no cover - rede de segurança do background
        logger.exception("validação da release %s falhou", release_id)
        with session_scope() as session:
            release = session.get(Release, release_id)
            if release is not None and release.status == "validando":
                release.status = "aberta"
                release.validation_ok = False
                session.add(release)


def _risco_maximo(tarefas: list[Task]) -> str:
    ordem = {"baixo": 0, "medio": 1, "alto": 2}
    return max((t.risk_tier for t in tarefas), key=lambda r: ordem.get(r, 0), default="baixo")


def corpo_do_pr(session: Session, release: Release) -> str:
    """O texto do PR: o que o guia §7 pede que todo PR para a principal diga."""
    tarefas = _tarefas_da(session, release)
    anterior = git_service.tags()
    rollback = (
        f"reverter o merge da release na principal (`git revert -m 1`) ou refazer o deploy "
        f"da tag `{anterior[0]}`"
        if anterior
        else "reverter o merge da release na principal (`git revert -m 1`); primeira versão"
    )
    linhas = [
        f"## Release {release.version}",
        "",
        "### Objetivo e escopo",
        release.changelog.strip(),
        "",
        "### Branches incluídas",
    ]
    for t in tarefas:
        planos = session.execute(
            select(PlanningDocument)
            .where(PlanningDocument.task_id == t.id)
            .order_by(PlanningDocument.id.desc())
            .limit(1)
        ).scalar_one_or_none()
        arquivos = len(planos.affected_files) if planos else 0
        linhas.append(
            f"- `{t.branch_name}` - {t.title} (task #{t.id}, risco {t.risk_tier}, "
            f"{arquivos} arquivo(s) previstos)"
        )
    linhas += [
        "",
        "### Testes executados",
        "- lint, checagem de tipos, testes unitários e `next build` na branch da release, "
        "com todas as tarefas integradas: "
        + ("passaram." if release.validation_ok else "NÃO validado."),
        "- cada tarefa passou antes pela revisão independente e pela homologação humana, e "
        "foi aprovada no ambiente de testes (develop).",
        "",
        "### Riscos conhecidos",
        f"- risco máximo entre as tarefas: **{_risco_maximo(tarefas)}**.",
        "",
        "### Rollback",
        f"- {rollback}.",
    ]
    return "\n".join(linhas)


def abrir_pr(session: Session, release: Release) -> Release:
    if release.status != "validada":
        raise EntregaError(
            f"a release {release.version} está '{release.status}': o PR só abre depois "
            "de a validação final passar."
        )
    if not release.changelog.strip():
        raise EntregaError("o changelog está vazio: o guia exige que a release o atualize")

    corpo = corpo_do_pr(session, release)
    base = git_service.main_branch()
    # O PR só enxerga o que está no GitHub, e todo o trabalho do PASE fica no repositório
    # local: a principal e a branch da release sobem antes de o PR abrir.
    github.enviar(str(git_service.main_repo().working_dir), base, release.branch)
    pr = github.abrir_pr(
        release.branch, base, f"release: {release.version}", corpo
    )
    if pr:
        release.pr_number = pr["number"]
        release.pr_url = pr["url"]
    release.pr_body = corpo
    release.status = "pr_aberto"
    session.add(release)
    registrar(
        session, release.branch, "release", release_id=release.id,
        detail=f"PR {release.branch} → {base} aberto" + (f" ({pr['url']})" if pr else " (local)"),
    )
    return release


def publicar(session: Session, release: Release, nota: str) -> dict:
    """Release → principal, tag e publicação. Exige a aprovação humana por escrito."""
    if release.status != "pr_aberto":
        raise EntregaError(
            f"a release {release.version} está '{release.status}': só se publica com o PR aberto."
        )
    if not nota.strip():
        raise EntregaError("publicar exige a aprovação registrada por escrito")

    mensagem = f"release: {release.version}\n\n{release.changelog.strip()}"
    try:
        if release.pr_number and github.ativo():
            sha = github.mergear_pr(release.pr_number, f"release: {release.version}")
            repo = git_service.main_repo()
            base = git_service.main_branch(repo)
            # O merge aconteceu no GitHub: traz para a principal local (as próximas
            # tarefas clonam dela), cria a tag aqui e publica a tag.
            github.buscar(str(repo.working_dir), base)
            repo.git.checkout(base)
            repo.git.merge("--ff-only", sha)
            repo.create_tag(release.version, ref=sha, message=f"Release {release.version}")
            github.enviar(str(repo.working_dir), f"refs/tags/{release.version}")
        else:
            sha = git_service.publicar_release(release.branch, mensagem, release.version)
    except (MergeConflictError, GitCommandError, github.GitHubError) as exc:
        registrar(
            session, git_service.main_branch(), "publicacao", ok=False, release_id=release.id,
            detail=str(exc),
        )
        return {"publicada": False, "detail": str(exc)}

    release.status = "publicada"
    release.publish_commit = sha
    release.tag = release.version
    release.approval_note = nota.strip()
    from app.common.models import utcnow

    release.published_at = utcnow()
    session.add(release)

    for t in _tarefas_da(session, release):
        t.stage = ESTAGIO_PRODUCAO
        session.add(t)

    base = git_service.main_branch()
    registrar(
        session, base, "publicacao", release_id=release.id, commit=sha,
        detail=f"release {release.version} publicada; tag {release.version}",
    )
    return {"publicada": True, "commit": sha, "tag": release.version}


def cancelar_release(session: Session, release: Release, motivo: str) -> None:
    """Descarta a release. As tarefas voltam à develop; a branch fica para auditoria."""
    if release.status in ("publicada", "cancelada"):
        raise EntregaError(f"a release {release.version} já está '{release.status}'")
    for t in _tarefas_da(session, release):
        t.stage = ESTAGIO_DEVELOP
        t.release_id = None
        t.release_commit = None
        session.add(t)
    release.status = "cancelada"
    session.add(release)
    registrar(
        session, release.branch, "release", ok=False, release_id=release.id,
        detail=f"release cancelada: {motivo}",
    )


# --------------------------------------------------------------------------- #
# Reversão por estágio
# --------------------------------------------------------------------------- #


def desfazer_na_entrega(session: Session, task: Task, motivo: str) -> str | None:
    """Tira da develop (e da release, se estiver nela) o que a tarefa integrou.

    Devolve o sha do revert na develop, ou `None` para tarefa anterior ao fluxo
    (que entrou direto na principal e é revertida lá, pelo caminho antigo).
    """
    if task.stage == ESTAGIO_PRODUCAO:
        raise EntregaError(
            "esta tarefa já foi publicada: a principal só muda por release. Corrija com "
            "um hotfix - Refazer cria um."
        )
    if task.stage is None:
        return None

    if task.stage == ESTAGIO_RELEASE and task.release_id:
        release = session.get(Release, task.release_id)
        if release is not None:
            remover_da_release(session, release, task)

    with git_service.clone_de_entrega() as repo:
        revert = git_service.reverter_integracao(
            repo, pipeline_rules.DEVELOP, task.merge_commit,
            f"revert: desfaz {task.title} da develop (task #{task.id})\n\n{motivo}",
        )
    registrar(
        session, pipeline_rules.DEVELOP, "reversao", task_id=task.id, commit=revert,
        detail=f"integração desfeita: {motivo}",
    )
    task.stage = None
    task.tested_ok = False
    session.add(task)
    return revert
