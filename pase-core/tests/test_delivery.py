"""O fluxo de entrega, sobre um repositório git de verdade (documento `git-guide` do contexto).

Nada de dublê de git: o que se prova aqui é o que acontece nas branches. Os testes
que não precisam de banco ficam no topo; os que precisam, abaixo.
"""

import pytest
from git import Repo
from sqlalchemy import text

from app.common import git_service, pipeline_rules
from app.common.git_service import MergeConflictError
from app.orchestration import delivery
from app.orchestration.models import PipelineEvent, Release
from app.task_layer.models import ImplementedItem, Task
from tests.conftest import requires_db


@pytest.fixture
def origem(tmp_path, monkeypatch):
    """Repositório de origem com a principal `main` e um arquivo."""
    caminho = tmp_path / "repo"
    caminho.mkdir()
    repo = Repo.init(caminho, initial_branch="main")
    repo.config_writer().set_value("user", "name", "Teste").release()
    repo.config_writer().set_value("user", "email", "teste@local").release()
    (caminho / "app.py").write_text("valor = 1\n", encoding="utf-8")
    repo.git.add("--all")
    repo.index.commit("inicial")

    monkeypatch.setattr(git_service.settings, "repo_path", str(caminho))
    monkeypatch.setattr(git_service.settings, "artifacts_path", str(tmp_path / "artefatos"))
    monkeypatch.setattr(git_service, "WORKSPACE_ROOT", tmp_path / "workspaces")
    monkeypatch.setattr(delivery.settings, "artifacts_path", str(tmp_path / "artefatos"))
    monkeypatch.setattr(delivery.settings, "delivery_ci_enabled", False)
    return repo


def _feature(task_id: int, titulo: str, arquivo: str, conteudo: str) -> str:
    """Uma branch de tarefa, feita pelo mesmo caminho do Executor."""
    ws = git_service.prepare_workspace(task_id, nova=True, titulo=titulo)
    git_service.write_files(ws, [{"path": arquivo, "content": conteudo}])
    git_service.commit_all(ws, f"feature: {titulo} (task #{task_id})")
    git_service.push(ws, forcar=True)
    return ws.branch


def _arquivos(repo: Repo, branch: str) -> set[str]:
    return set(repo.git.ls_tree("-r", "--name-only", branch).split())


# --------------------------------------------------------------------------- #
# git: o que cada operação faz nas branches
# --------------------------------------------------------------------------- #


def test_feature_entra_na_develop_com_merge_commit_e_a_principal_nao_muda(origem):
    branch = _feature(1, "Exportar csv", "export.py", "x = 1\n")
    antes = origem.heads.main.commit.hexsha

    with git_service.clone_de_entrega() as repo:
        git_service.garantir_develop(repo)
        sha = git_service.integrar(repo, branch, "develop", "feature: integra (task #1)")

    assert "export.py" in _arquivos(origem, "develop")
    assert len(origem.commit(sha).parents) == 2  # --no-ff: a branch continua identificável
    assert origem.heads.main.commit.hexsha == antes
    assert "export.py" not in _arquivos(origem, "main")


@pytest.mark.parametrize("destino", ["main", "develop"])
def test_develop_nunca_nasce_nem_entra_onde_o_guia_proibe(origem, destino):
    branch = _feature(1, "Algo", "a.py", "a = 1\n")
    with git_service.clone_de_entrega() as repo:
        git_service.garantir_develop(repo)
        if destino == "main":
            with pytest.raises(pipeline_rules.PipelineError):
                git_service.integrar(repo, branch, "main", "feature: x (task #1)")
        else:
            with pytest.raises(pipeline_rules.PipelineError):
                git_service.integrar(repo, "develop", branch, "feature: x (task #1)")


def test_branch_que_incorporou_a_develop_e_recusada(origem):
    a = _feature(1, "Primeira", "a.py", "a = 1\n")
    b = _feature(2, "Segunda", "b.py", "b = 1\n")

    with git_service.clone_de_entrega() as repo:
        git_service.garantir_develop(repo)
        git_service.integrar(repo, a, "develop", "feature: a (task #1)")
        assert not git_service.incorpora_develop(repo, a)  # a própria entrega não conta

    # a segunda branch puxa a develop para dentro de si - o que o guia proíbe
    ws = git_service.prepare_workspace(2, nova=False, titulo="Segunda")
    ws.repo.git.merge("origin/develop", "-m", "chore: traz a develop")
    git_service.push(ws)

    with git_service.clone_de_entrega() as repo:
        assert git_service.incorpora_develop(repo, b)
        with pytest.raises(pipeline_rules.PipelineError, match="incorporou a develop"):
            git_service.integrar(repo, b, "develop", "feature: b (task #2)")


def test_conflito_aborta_e_deixa_o_clone_limpo(origem):
    a = _feature(1, "Muda valor", "app.py", "valor = 2\n")
    b = _feature(2, "Muda valor de outro jeito", "app.py", "valor = 3\n")

    with git_service.clone_de_entrega() as repo:
        git_service.garantir_develop(repo)
        git_service.integrar(repo, a, "develop", "feature: a (task #1)")
        with pytest.raises(MergeConflictError):
            git_service.integrar(repo, b, "develop", "feature: b (task #2)")
        assert not repo.is_dirty(untracked_files=True)


def test_release_nasce_da_principal_e_publica_com_tag(origem):
    branch = _feature(1, "Exportar csv", "export.py", "x = 1\n")

    with git_service.clone_de_entrega() as repo:
        nome = git_service.criar_release(repo, "1.0.0")
        git_service.integrar(repo, branch, nome, "feature: integra (task #1)")
        with pytest.raises(pipeline_rules.PipelineError, match="já existe"):
            git_service.criar_release(repo, "1.0.0")

    assert "export.py" not in _arquivos(origem, "main")  # ainda não foi publicada

    sha = git_service.publicar_release("release/1.0.0", "release: 1.0.0", "1.0.0")

    assert "export.py" in _arquivos(origem, "main")
    assert origem.heads.main.commit.hexsha == sha
    assert git_service.tags() == ["1.0.0"]


def test_versao_ja_publicada_nao_vira_release_de_novo(origem):
    origem.create_tag("1.0.0")
    with git_service.clone_de_entrega() as repo:
        with pytest.raises(pipeline_rules.PipelineError, match="tag"):
            git_service.criar_release(repo, "1.0.0")


def test_reverter_integracao_tira_a_entrega_da_develop(origem):
    branch = _feature(1, "Exportar csv", "export.py", "x = 1\n")
    with git_service.clone_de_entrega() as repo:
        git_service.garantir_develop(repo)
        sha = git_service.integrar(repo, branch, "develop", "feature: a (task #1)")
        git_service.reverter_integracao(repo, "develop", sha, "revert: desfaz (task #1)")

    assert "export.py" not in _arquivos(origem, "develop")


# --------------------------------------------------------------------------- #
# Orquestração: tarefas, releases, publicação
# --------------------------------------------------------------------------- #

TABELAS = (
    "pipeline_events", "task_state_history", "execution_runs", "planning_documents",
    "implemented_items", "tasks", "releases", "proposals",
)


@pytest.fixture
def limpo(session):
    def zerar():
        for t in TABELAS:
            session.execute(text(f"DELETE FROM {t}"))
        session.commit()

    zerar()
    yield session
    zerar()


def _tarefa(session, task_id_git: int, titulo: str, arquivo: str, **campos) -> Task:
    branch = _feature(task_id_git, titulo, arquivo, "x = 1\n")
    task = Task(
        title=titulo, description="d", module="geral", impact=3, complexity=1,
        status="finalizada", final_outcome="aprovada", branch_name=branch, **campos,
    )
    session.add(task)
    session.commit()
    return task


def _na_develop(session, origem, arquivo="export.py") -> Task:
    task = _tarefa(session, 1, "Exportar csv", arquivo)
    # o id real é o do banco; a branch usa 1 só para não depender do autoincremento
    resultado = delivery.integrar_na_develop(session, task, "feature: integra (task #1)")
    session.commit()
    assert resultado["merged"]
    return task


@requires_db
def test_integrar_registra_estagio_commit_e_evento(limpo, origem):
    task = _na_develop(limpo, origem)

    assert task.stage == "develop"
    assert task.merge_commit
    eventos = limpo.query(PipelineEvent).filter_by(kind="integracao").all()
    assert [e.branch for e in eventos] == ["develop"]


@requires_db
def test_so_entra_na_release_o_que_foi_aprovado_nos_testes(limpo, origem):
    task = _na_develop(limpo, origem)
    release = delivery.criar_release(limpo, "1.0.0")
    limpo.commit()

    with pytest.raises(delivery.EntregaError, match="aprovada nos testes"):
        delivery.incluir_na_release(limpo, release, task)

    with pytest.raises(delivery.EntregaError, match="nota"):
        delivery.aprovar_nos_testes(limpo, task, "  ")

    delivery.aprovar_nos_testes(limpo, task, "conferi o botão de exportar na develop")
    resultado = delivery.incluir_na_release(limpo, release, task)
    limpo.commit()

    assert resultado["incluida"]
    assert task.stage == "release" and task.release_id == release.id
    assert "(task #" in release.changelog
    assert "export.py" in _arquivos(origem, "release/1.0.0")


@requires_db
def test_fluxo_completo_da_tarefa_a_producao(limpo, origem):
    task = _na_develop(limpo, origem)
    delivery.aprovar_nos_testes(limpo, task, "ok nos testes")
    release = delivery.criar_release(limpo, "1.0.0")
    delivery.incluir_na_release(limpo, release, task)
    limpo.commit()

    # PR antes da validação não abre
    with pytest.raises(delivery.EntregaError, match="validação final"):
        delivery.abrir_pr(limpo, release)

    delivery.iniciar_validacao(limpo, release)
    limpo.commit()
    delivery.rodar_validacao_da_release(release.id)
    limpo.expire_all()
    release = limpo.get(Release, release.id)
    assert release.status == "validada"

    # publicar sem PR aberto não vale
    with pytest.raises(delivery.EntregaError, match="PR aberto"):
        delivery.publicar(limpo, release, "aprovado")

    delivery.abrir_pr(limpo, release)
    assert "Rollback" in release.pr_body and "Branches incluídas" in release.pr_body

    with pytest.raises(delivery.EntregaError, match="por escrito"):
        delivery.publicar(limpo, release, " ")

    resultado = delivery.publicar(limpo, release, "li o PR, aprovo")
    limpo.commit()

    assert resultado["publicada"]
    assert "export.py" in _arquivos(origem, "main")
    assert git_service.tags() == ["1.0.0"]
    limpo.refresh(task)
    assert task.stage == "producao"
    assert release.status == "publicada" and release.tag == "1.0.0"


@requires_db
def test_release_vazia_nao_valida(limpo, origem):
    release = delivery.criar_release(limpo, "1.0.0")
    with pytest.raises(delivery.EntregaError, match="vazia"):
        delivery.iniciar_validacao(limpo, release)


@requires_db
def test_release_com_pr_aberto_nao_aceita_mais_tarefas(limpo, origem):
    a = _na_develop(limpo, origem)
    delivery.aprovar_nos_testes(limpo, a, "ok")
    release = delivery.criar_release(limpo, "1.0.0")
    delivery.incluir_na_release(limpo, release, a)
    release.status = "pr_aberto"
    limpo.commit()

    b = _tarefa(limpo, 2, "Outra coisa", "outra.py")
    b.stage, b.tested_ok = "develop", True
    limpo.commit()
    with pytest.raises(delivery.EntregaError, match="antes do Pull Request"):
        delivery.incluir_na_release(limpo, release, b)


@requires_db
def test_ci_reprovado_desfaz_a_integracao_na_develop(limpo, origem, monkeypatch):
    task = _na_develop(limpo, origem)
    limpo.add(ImplementedItem(title=task.title, description="d", task_id=task.id))
    limpo.commit()
    monkeypatch.setattr(delivery.settings, "delivery_ci_enabled", True)
    monkeypatch.setattr(delivery, "_rodar_ci", lambda branch, nome: (False, "teste falhou", "/x"))

    delivery.rodar_ci_da_develop(task.id)

    limpo.expire_all()
    task = limpo.get(Task, task.id)
    assert "export.py" not in _arquivos(origem, "develop")
    assert task.final_outcome == "revertida" and task.alert == "ci_develop"
    assert task.stage is None
    assert limpo.query(ImplementedItem).count() == 0
    kinds = [e.kind for e in limpo.query(PipelineEvent).order_by(PipelineEvent.id)]
    assert kinds[-2:] == ["ci", "reversao"]


@requires_db
def test_ci_aprovado_deixa_a_develop_como_esta(limpo, origem, monkeypatch):
    task = _na_develop(limpo, origem)
    monkeypatch.setattr(delivery.settings, "delivery_ci_enabled", True)
    monkeypatch.setattr(delivery, "_rodar_ci", lambda branch, nome: (True, "ok", "/x"))

    delivery.rodar_ci_da_develop(task.id)

    limpo.expire_all()
    assert "export.py" in _arquivos(origem, "develop")
    assert limpo.get(Task, task.id).stage == "develop"


@requires_db
def test_desfazer_na_release_tira_da_release_e_da_develop(limpo, origem):
    task = _na_develop(limpo, origem)
    delivery.aprovar_nos_testes(limpo, task, "ok")
    release = delivery.criar_release(limpo, "1.0.0")
    delivery.incluir_na_release(limpo, release, task)
    limpo.commit()

    delivery.desfazer_na_entrega(limpo, task, "estava errado")
    limpo.commit()

    assert "export.py" not in _arquivos(origem, "develop")
    assert "export.py" not in _arquivos(origem, "release/1.0.0")
    assert task.stage is None and task.release_id is None and not task.tested_ok


@requires_db
def test_o_que_ja_esta_em_producao_nao_se_reverte_so_se_corrige_com_hotfix(limpo, origem):
    task = _na_develop(limpo, origem)
    task.stage = "producao"
    limpo.commit()

    with pytest.raises(delivery.EntregaError, match="hotfix"):
        delivery.desfazer_na_entrega(limpo, task, "quebrou")


@requires_db
def test_refazer_o_que_esta_em_producao_cria_um_hotfix_sem_reverter(limpo, origem):
    from app.orchestration import redo

    task = _na_develop(limpo, origem)
    task.stage = "producao"
    limpo.commit()

    nova = redo.refazer(limpo, task, "o saldo ficou errado em produção")

    assert nova.change_type == "fix"
    assert git_service.conventions.branch_de(nova.id, nova.title, nova.change_type).startswith(
        "hotfix/"
    )
    assert task.final_outcome == "aprovada"  # nada foi revertido na principal
    assert "export.py" in _arquivos(origem, "develop")


@requires_db
def test_versao_sugerida_segue_as_tags(limpo, origem):
    assert delivery.versao_sugerida() == "1.0.0"
    origem.create_tag("1.4.2")
    assert delivery.versao_sugerida() == "1.5.0"
    assert delivery.versao_sugerida("patch") == "1.4.3"
