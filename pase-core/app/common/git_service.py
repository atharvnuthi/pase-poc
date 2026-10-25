"""Operações de Git sobre o REPO_PATH (SPEC-01 §6).

É a única porta de entrada do PASE para o repositório. O isolamento exigido pelo
SPEC-00 §7 acontece aqui: o Executor trabalha num clone em /tmp, numa branch
`feature/pase-{id}-{slug}` (ou `hotfix/...`), e nada entra na branch principal
fora de `publicar_release()`, que só uma release aprovada por uma pessoa aciona.
"""

from __future__ import annotations

import re
import shutil
import threading
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path

from git import GitCommandError, Repo

from app.common import conventions, pipeline_rules
from app.common.config import settings

WORKSPACE_ROOT = Path("/tmp/pase")


class GitServiceError(RuntimeError):
    pass


class ConvencaoError(RuntimeError):
    """Nome de branch ou mensagem de commit fora do padrão da equipe."""


class MergeConflictError(GitServiceError):
    """Merge abortado por conflito - a task permanece em homologação."""


@dataclass
class Workspace:
    task_id: int
    path: Path
    branch: str
    repo: Repo


def branch_name(task_id: int, titulo: str = "", tipo: str | None = "feature") -> str:
    """Branch da tarefa, no padrão da equipe (`engineering-guidelines` §3 do contexto).

    Branches de tarefa são exclusivas do Executor e nunca editadas à mão.
    """
    return conventions.branch_de(task_id, titulo or f"task-{task_id}", tipo)


def main_repo() -> Repo:
    return Repo(settings.repo_path)


def main_branch(repo: Repo | None = None) -> str:
    """Nome da branch principal deste repositório (`main` ou `master`)."""
    repo = repo or main_repo()
    for candidate in ("main", "master"):
        if candidate in repo.heads:
            return candidate
    return repo.active_branch.name


def prepare_workspace(
    task_id: int, *, nova: bool = False, titulo: str = "", tipo: str | None = "feature"
) -> Workspace:
    """Clona o REPO_PATH num workspace isolado e posiciona na branch da task.

    `nova=True` descarta qualquer branch anterior com este nome e recomeça da
    branch principal. É o caso da primeira execução de uma tarefa.

    Isso importa porque `make reset` zera o banco - e os ids das tarefas voltam a
    começar do 1 - mas não apaga as branches que o Executor deixou no repositório.
    Sem este cuidado, a tarefa #1 de hoje herdaria a branch da tarefa #1 de ontem,
    já com código dentro: o diff sairia quase vazio e o merge entraria em conflito
    com a branch principal.

    Com `nova=False` (retry e ajuste), a branch existente é reaproveitada de
    propósito: é a mesma tarefa continuando de onde parou.
    """
    path = WORKSPACE_ROOT / f"task-{task_id}"
    branch = branch_name(task_id, titulo, tipo)

    if nova:
        shutil.rmtree(path, ignore_errors=True)

    if path.exists():
        repo = Repo(path)
        repo.remotes.origin.fetch(prune=True)
    else:
        path.parent.mkdir(parents=True, exist_ok=True)
        repo = Repo.clone_from(settings.repo_path, path)

    base = main_branch(repo)

    if nova:
        repo.git.checkout("-B", branch, f"origin/{base}")
        return Workspace(task_id=task_id, path=path, branch=branch, repo=repo)

    # Reaproveitar a branch é continuar a tarefa, não herdar a sujeira: arquivos
    # escritos por uma tentativa que falhou ficam no disco, não no commit.
    repo.git.reset("--hard")
    repo.git.clean("-fd")

    if branch in repo.heads:
        repo.git.checkout(branch)
    elif f"origin/{branch}" in [ref.name for ref in repo.refs]:
        repo.git.checkout("-b", branch, f"origin/{branch}")
    else:
        repo.git.checkout("-b", branch, f"origin/{base}")

    return Workspace(task_id=task_id, path=path, branch=branch, repo=repo)


def discard_workspace(task_id: int) -> None:
    shutil.rmtree(WORKSPACE_ROOT / f"task-{task_id}", ignore_errors=True)


def _dentro_do_clone(workspace: Workspace, relativo: str) -> Path:
    """Caminho absoluto de `relativo` no clone - ou erro, se ele sair do clone.

    A fronteira de verdade (quais pastas o Executor pode tocar) é conferida antes,
    em `executor.fronteira_respeitada`. Isto é a última trava, no ponto da
    escrita: nenhum caminho absoluto, `..` ou symlink leva a escrita para fora do
    clone, mesmo que alguém chame esta função sem passar pela fronteira.
    """
    raiz = workspace.path.resolve()
    alvo = (workspace.path / relativo).resolve()
    if Path(relativo).is_absolute() or not alvo.is_relative_to(raiz) or alvo == raiz:
        raise GitServiceError(f"caminho fora do clone recusado: {relativo!r}")
    return alvo


def write_files(workspace: Workspace, files: list[dict[str, str]]) -> list[str]:
    """Escreve `[{path, content}]` no workspace. Devolve os caminhos tocados."""
    alvos = [(_dentro_do_clone(workspace, item["path"]), item) for item in files]
    written: list[str] = []
    for target, item in alvos:
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(item["content"], encoding="utf-8")
        written.append(item["path"])
    return written


def delete_files(workspace: Workspace, paths: list[str]) -> list[str]:
    """Apaga arquivos do workspace. Devolve só os que existiam e foram apagados.

    Pastas não: o plano exclui arquivos, e apagar uma pasta inteira por um
    caminho mal escrito levaria junto o que ninguém pediu.
    """
    alvos = [(_dentro_do_clone(workspace, relativo), relativo) for relativo in paths]
    removed: list[str] = []
    for target, relativo in alvos:
        if target.is_file():
            target.unlink()
            removed.append(relativo)
    return removed


def commit_all(workspace: Workspace, message: str) -> str | None:
    """Comita tudo que mudou. Devolve o sha, ou None se não havia mudança.

    A mensagem é conferida contra a convenção antes de virar commit. Um histórico
    só é útil se for legível de forma uniforme, e a única maneira de garantir isso
    é recusar o que está fora do formato - não pedir que esteja dentro.
    """
    conforme, aviso = conventions.conferir_commit(message)
    if not conforme:
        raise ConvencaoError(aviso)

    workspace.repo.git.add("--all")
    if not workspace.repo.is_dirty(index=True, working_tree=True, untracked_files=True):
        return None
    workspace.repo.index.commit(message)
    return workspace.repo.head.commit.hexsha


def push(workspace: Workspace, *, forcar: bool = False) -> None:
    """Publica a branch da task no REPO_PATH.

    `forcar` na primeira execução: a branch remota pode ser restolho de um ciclo
    anterior com o mesmo id de tarefa.
    """
    args = ["--set-upstream", "origin", workspace.branch]
    if forcar:
        args.insert(0, "--force")
    _push(workspace.repo, *args)


#: URL de remoto de rede: `https://…`, `ssh://…`, `git@host:…`.
_REMOTO_DE_REDE = re.compile(r"^(?:[a-z][a-z0-9+.-]*://|[\w.-]+@[\w.-]+:)", re.IGNORECASE)


def _push(repo: Repo, *args: str) -> None:
    """`git push` para o `origin` - que tem de ser o REPO_PATH local.

    Todo clone deste módulo nasce de `settings.repo_path`, então o `origin` é um
    caminho no disco. Publicar no GitHub é papel de `app.common.github`, só
    quando ele está ativo; daqui nenhum push sai para a rede. Conferido por
    código: uma suíte de testes chegou a publicar no remoto de verdade porque o
    container herda o `GITHUB_TOKEN`.
    """
    url = repo.remotes.origin.url
    if _REMOTO_DE_REDE.match(url):
        raise GitServiceError(f"push recusado: o origin deste clone é um remoto de rede ({url})")
    repo.git.push(*args)


def diff_against_main(workspace: Workspace) -> str:
    """`git diff main...HEAD` - o diff que o humano revisa na Homologação."""
    base = main_branch(workspace.repo)
    return workspace.repo.git.diff(f"origin/{base}...HEAD")


def diff_em_andamento(workspace: Workspace) -> str:
    """Diff do que já está escrito no clone e ainda não foi commitado.

    A revisão roda **antes** do commit, para que uma reprovação volte ao ciclo de
    correção sem deixar um commit ruim na branch. `intent-to-add` faz os arquivos
    novos aparecerem no diff sem colocá-los no índice de verdade.
    """
    base = main_branch(workspace.repo)
    workspace.repo.git.add("--intent-to-add", "--all")
    return workspace.repo.git.diff(f"origin/{base}")


def changed_files(workspace: Workspace) -> list[str]:
    base = main_branch(workspace.repo)
    output = workspace.repo.git.diff("--name-only", f"origin/{base}...HEAD")
    return [line for line in output.splitlines() if line.strip()]


def merge_branch(branch: str, message: str) -> str:
    """Traz uma branch para a principal com --no-ff. Hoje só `publicar_release` a usa.

    Levanta MergeConflictError sem deixar o repositório em estado de conflito.
    """
    repo = main_repo()
    base = main_branch(repo)
    repo.git.checkout(base)
    try:
        repo.git.merge("--no-ff", branch, "-m", message)
    except GitCommandError as exc:
        repo.git.merge("--abort")
        raise MergeConflictError(f"conflito ao integrar {branch} em {base}: {exc}") from exc
    return repo.head.commit.hexsha


def merge_commit_da_task(task_id: int) -> str | None:
    """SHA do merge que integrou esta tarefa na principal, ou None.

    Alternativa para tarefas sem `merge_commit` gravado: procura pela mensagem do
    merge, escrita pelo próprio `aprovar()` num formato fixo, e `-F` garante que
    `(task #1)` não case com `(task #11)`.
    """
    repo = main_repo()
    saida = repo.git.log(
        "--merges", "-F", f"--grep=(task #{task_id})", "--format=%H", "-1"
    )
    return saida.strip() or None


def reverter_merge(sha: str, message: str) -> str:
    """Desfaz um merge na principal com um commit novo (SPEC-00 §2).

    `git revert`, nunca `reset`: desfazer apagando histórico destruiria o rastro
    da decisão que trouxe o código, e o registro de que ela foi tomada é parte
    do que torna o sistema auditável. Depois disto o histórico conta as duas
    coisas - que entrou e que foi desfeito.
    """
    repo = main_repo()
    base = main_branch(repo)
    repo.git.checkout(base)
    try:
        repo.git.revert("-m", "1", "--no-commit", sha)
        repo.git.commit("-m", message)
    except GitCommandError as exc:
        # Não deixa o repositório em estado de conflito pela metade.
        repo.git.revert("--quit")
        repo.git.reset("--hard", "HEAD")
        raise MergeConflictError(f"conflito ao reverter {sha[:8]}: {exc}") from exc
    return repo.head.commit.hexsha


# --------------------------------------------------------------------------- #
# Fluxo de entrega: develop → release/x.x.x → principal
#
# Tudo aqui acontece num clone próprio (`/tmp/pase/delivery`), publicando por
# `push` na origem. A árvore de trabalho do `REPO_PATH` - onde uma pessoa pode
# estar com mudanças não commitadas - nunca é tocada, exceto pela publicação na
# principal, que é por definição a única operação que a altera.
# --------------------------------------------------------------------------- #

#: Duas operações no clone de entrega ao mesmo tempo corromperiam o índice dele.
_trava_de_entrega = threading.RLock()


@contextmanager
def clone_de_entrega() -> Iterator[Repo]:
    """O clone de entrega, atualizado e limpo, com exclusividade enquanto durar o bloco."""
    with _trava_de_entrega:
        caminho = WORKSPACE_ROOT / "delivery"
        if caminho.exists():
            repo = Repo(caminho)
            repo.git.reset("--hard")
            repo.git.clean("-fd")
            repo.remotes.origin.fetch(prune=True, tags=True, force=True)
        else:
            caminho.parent.mkdir(parents=True, exist_ok=True)
            repo = Repo.clone_from(settings.repo_path, caminho)
            repo.remotes.origin.fetch(tags=True, force=True)
        configurar_autor(repo)
        yield repo


def configurar_autor(repo: Repo) -> None:
    """Merge precisa de autor. O ambiente do container pode não ter um configurado."""
    with repo.config_writer() as cfg:
        if not cfg.has_option("user", "name"):
            cfg.set_value("user", "name", "PASE")
        if not cfg.has_option("user", "email"):
            cfg.set_value("user", "email", "pase@localhost")


def _existe_na_origem(repo: Repo, branch: str) -> bool:
    return f"origin/{branch}" in [ref.name for ref in repo.refs]


def garantir_develop(repo: Repo) -> None:
    """Cria `develop` a partir da principal, na primeira vez.

    O guia a trata como existente. Num repositório que ainda não a tem, criá-la é
    parte de adotar o fluxo - e é a única criação de branch que não nasce de uma
    tarefa.
    """
    if _existe_na_origem(repo, pipeline_rules.DEVELOP):
        return
    base = main_branch(repo)
    repo.git.checkout("-B", pipeline_rules.DEVELOP, f"origin/{base}")
    _push(repo, "--set-upstream", "origin", pipeline_rules.DEVELOP)


def _posicionar(repo: Repo, branch: str) -> None:
    """Põe o clone em `branch`, igual à da origem."""
    if _existe_na_origem(repo, branch):
        repo.git.checkout("-B", branch, f"origin/{branch}")
    else:
        raise GitServiceError(f"a branch {branch} não existe na origem")


def incorpora_develop(repo: Repo, branch: str) -> bool:
    """A branch trouxe a `develop` para dentro de si?

    O guia proíbe `develop → feature/hotfix/release` porque a develop carrega
    mudanças de outras entregas, ainda em teste. Quem a incorpora passa a levar
    consigo trabalho não aprovado para a release.

    A conta: a linha principal (`--first-parent`) da develop é feita dos merges de
    entrega e dos commits diretos nela. Uma branch de trabalho legítima nunca
    contém nenhum deles - só os próprios commits, que chegam à develop como
    segundo pai. Se contém, ela absorveu a develop.
    """
    if not _existe_na_origem(repo, pipeline_rules.DEVELOP):
        return False
    base = main_branch(repo)
    da_develop = set(
        repo.git.rev_list(
            "--first-parent", f"origin/{pipeline_rules.DEVELOP}", f"^origin/{base}"
        ).split()
    )
    da_branch = set(repo.git.rev_list(f"origin/{branch}", f"^origin/{base}").split())
    return bool(da_develop & da_branch)


def integrar(repo: Repo, origem: str, destino: str, mensagem: str) -> str:
    """Merge direto `--no-ff` de `origem` em `destino`, publicado na origem.

    A permissão vem de `pipeline_rules`, não de quem chama. Em conflito, aborta e
    deixa o clone limpo: o guia manda parar e pedir uma pessoa, não resolver sozinho.
    """
    base = main_branch(repo)
    pipeline_rules.validar_integracao(origem, destino, base)

    if not _existe_na_origem(repo, origem):
        raise GitServiceError(f"a branch {origem} não existe na origem")
    if incorpora_develop(repo, origem):
        raise pipeline_rules.PipelineError(
            f"`{origem}` incorporou a develop. Refaça a branch a partir da principal: "
            "a develop carrega trabalho de outras entregas ainda em teste."
        )

    _posicionar(repo, destino)
    try:
        repo.git.merge("--no-ff", f"origin/{origem}", "-m", mensagem)
    except GitCommandError as exc:
        repo.git.merge("--abort")
        raise MergeConflictError(f"conflito ao integrar {origem} em {destino}: {exc}") from exc

    _push(repo, "origin", destino)
    return repo.head.commit.hexsha


def reverter_integracao(repo: Repo, branch: str, sha: str, mensagem: str) -> str:
    """`git revert -m 1` de um merge numa branch de entrega, publicado na origem."""
    _posicionar(repo, branch)
    try:
        repo.git.revert("-m", "1", "--no-commit", sha)
        repo.git.commit("-m", mensagem)
    except GitCommandError as exc:
        repo.git.revert("--quit")
        repo.git.reset("--hard", "HEAD")
        raise MergeConflictError(f"conflito ao reverter {sha[:8]} em {branch}: {exc}") from exc
    _push(repo, "origin", branch)
    return repo.head.commit.hexsha


def criar_release(repo: Repo, versao: str) -> str:
    """`release/x.x.x` a partir da principal, publicada. Devolve o nome da branch."""
    nome = pipeline_rules.branch_da_release(versao)
    base = main_branch(repo)
    pipeline_rules.validar_origem_da_criacao(nome, base, base)

    if _existe_na_origem(repo, nome):
        raise pipeline_rules.PipelineError(f"a {nome} já existe.")
    if versao in tags(repo):
        raise pipeline_rules.PipelineError(f"a versão {versao} já foi publicada (tag existente).")

    repo.git.checkout("-B", nome, f"origin/{base}")
    _push(repo, "--set-upstream", "origin", nome)
    return nome


def tags(repo: Repo | None = None) -> list[str]:
    """Tags de versão, da mais nova para a mais velha."""
    repo = repo or main_repo()
    achadas = [t.name for t in repo.tags if pipeline_rules.VERSAO.match(t.name)]
    return sorted(achadas, key=pipeline_rules.validar_versao, reverse=True)


def publicar_release(branch: str, mensagem: str, versao: str) -> str:
    """Release → principal, mais a tag. Única operação que altera a principal.

    Quem chama já verificou o que o guia exige - PR aberto, validação verde,
    aprovação humana registrada. Aqui o `pipeline_rules` confere só o destino.
    """
    base = main_branch()
    pipeline_rules.validar_integracao(branch, base, base)
    sha = merge_branch(branch, mensagem)
    main_repo().create_tag(versao, ref=sha, message=f"Release {versao}")
    return sha
