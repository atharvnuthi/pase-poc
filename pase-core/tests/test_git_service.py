"""git_service: isolamento do Executor (SPEC-00 §7) sobre um repositório de mentira."""

from pathlib import Path

import pytest
from git import Repo

from app.common import git_service
from app.common.git_service import (
    MergeConflictError,
    branch_name,
    changed_files,
    commit_all,
    diff_against_main,
    main_branch,
    merge_branch,
    prepare_workspace,
    push,
    write_files,
)


@pytest.fixture
def repo_alvo(tmp_path, monkeypatch):
    """Repositório com um commit inicial, fazendo as vezes do REPO_PATH."""
    origem = tmp_path / "repo"
    origem.mkdir()
    repo = Repo.init(origem, initial_branch="main")
    repo.config_writer().set_value("user", "name", "Teste").release()
    repo.config_writer().set_value("user", "email", "teste@local").release()
    (origem / "app.py").write_text("valor = 1\n", encoding="utf-8")
    repo.index.add(["app.py"])
    repo.index.commit("inicial")

    monkeypatch.setattr(git_service.settings, "repo_path", str(origem))
    monkeypatch.setattr(git_service, "WORKSPACE_ROOT", tmp_path / "workspaces")
    return repo


def test_branch_da_task_segue_a_convencao():
    """`<feature|hotfix>/pase-<id>-<slug>` (guia de fluxo de ramos §2)."""
    assert branch_name(7, "Exportar em CSV", "feature") == "feature/pase-7-exportar-em-csv"
    # o guia só conhece duas branches de trabalho: correção vira hotfix
    assert branch_name(7, "Corrige o saldo", "fix") == "hotfix/pase-7-corrige-o-saldo"
    assert branch_name(7, "Organiza docs", "docs") == "feature/pase-7-organiza-docs"


def test_main_branch_detecta_main_ou_master(repo_alvo):
    assert main_branch(repo_alvo) == "main"
    repo_alvo.git.branch("-m", "main", "master")
    assert main_branch(repo_alvo) == "master"


def test_ciclo_completo_clona_escreve_comita_e_integra(repo_alvo):
    workspace = prepare_workspace(7, titulo="Exportar em CSV")

    assert workspace.branch == "feature/pase-7-exportar-em-csv"
    assert workspace.path != Path(git_service.settings.repo_path)  # nunca na main local

    write_files(
        workspace,
        [
            {"path": "app.py", "content": "valor = 2\n"},
            {"path": "novo/util.py", "content": "def util():\n    return True\n"},
        ],
    )
    sha = commit_all(workspace, "feature: mudança de teste (task #7)")
    assert sha

    assert sorted(changed_files(workspace)) == ["app.py", "novo/util.py"]
    diff = diff_against_main(workspace)
    assert "-valor = 1" in diff and "+valor = 2" in diff

    # antes do merge, a branch principal continua intacta
    assert (Path(git_service.settings.repo_path) / "app.py").read_text() == "valor = 1\n"

    push(workspace)
    merge_branch("feature/pase-7-exportar-em-csv", "feature: integra task #7")

    assert (Path(git_service.settings.repo_path) / "app.py").read_text() == "valor = 2\n"


def test_commit_sem_mudanca_devolve_none(repo_alvo):
    workspace = prepare_workspace(8)
    assert commit_all(workspace, "chore: nada a fazer") is None


def test_conflito_de_merge_nao_deixa_o_repo_sujo(repo_alvo):
    workspace = prepare_workspace(9)
    write_files(workspace, [{"path": "app.py", "content": "valor = 99\n"}])
    commit_all(workspace, "feature: valor 99 (task #9)")
    push(workspace)

    # a branch principal muda o mesmo arquivo depois do clone
    alvo = Path(git_service.settings.repo_path) / "app.py"
    alvo.write_text("valor = 42\n", encoding="utf-8")
    repo_alvo.index.add(["app.py"])
    repo_alvo.index.commit("mudança concorrente na main")

    with pytest.raises(MergeConflictError):
        merge_branch(workspace.branch, "feature: integra task #9")

    assert not repo_alvo.is_dirty()  # merge --abort rodou
    assert alvo.read_text() == "valor = 42\n"


def test_commit_fora_da_convencao_e_recusado(repo_alvo):
    """A convenção é conferida por código, não pedida no prompt."""
    workspace = prepare_workspace(11, titulo="Qualquer coisa")
    write_files(workspace, [{"path": "app.py", "content": "valor = 3\n"}])

    with pytest.raises(git_service.ConvencaoError, match="padrão"):
        commit_all(workspace, "pase: formato antigo (task #11)")
