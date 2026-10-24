"""Pull Request de verdade no GitHub (Fase 5 do roadmap).

**Desligado por padrão.** Sem `GITHUB_TOKEN` o sistema segue exatamente como
antes: a Homologação faz merge local e nada aqui é chamado. Não é meia
implementação - é uma escolha. Abrir PR muda o modelo de confiança do projeto
(passa a existir segredo e escrita num serviço externo), e uma PoC local que
guarda um token por padrão convida ao acidente.

Ligar exige duas coisas: `GITHUB_TOKEN` no ambiente e `GITHUB_REPO` no formato
`dono/repositorio`. Com as duas, o Executor abre PR ao terminar a run e a
Homologação passa a fazer merge pelo PR em vez de localmente.

O `pase-core` chama esta API - **nunca o sandbox do Executor**, que continua sem
rede além do provedor de LLM (CLAUDE.md).
"""

from __future__ import annotations

import base64
import logging
import os
import subprocess

import httpx

from app.common.config import settings

logger = logging.getLogger("pase.github")

API = "https://api.github.com"
TIMEOUT = 20.0


class GitHubError(RuntimeError):
    """A API do GitHub recusou a operação."""


def ativo() -> bool:
    """Há token e repositório configurados?"""
    return bool(settings.github_token and settings.github_repo)


def _git(repo_path: str, *args: str) -> str:
    """Roda `git` contra o GitHub sem deixar o token em argv, em config ou em erro.

    O token vai por variável de ambiente (`GIT_CONFIG_*`), então não aparece na
    linha de comando que o GitPython e o `ps` mostram, nem no `.git/config`. A
    saída é limpa antes de virar mensagem de erro.
    """
    credencial = base64.b64encode(f"x-access-token:{settings.github_token}".encode()).decode()
    env = {
        **os.environ,
        "GIT_TERMINAL_PROMPT": "0",
        "GIT_CONFIG_COUNT": "1",
        "GIT_CONFIG_KEY_0": "http.extraheader",
        "GIT_CONFIG_VALUE_0": f"Authorization: Basic {credencial}",
    }
    resultado = subprocess.run(
        ["git", "-C", repo_path, *args],
        env=env, capture_output=True, text=True, timeout=120, check=False,
    )
    saida = (resultado.stdout + resultado.stderr).replace(settings.github_token, "***")
    saida = saida.replace(credencial, "***")
    if resultado.returncode != 0:
        raise GitHubError(f"git {args[0]} falhou: {saida.strip()}")
    return saida


def _url() -> str:
    return f"https://github.com/{settings.github_repo}.git"


def enviar(repo_path: str, *refs: str) -> None:
    """Publica branches ou tags do repositório local no GitHub."""
    if not ativo():
        return
    _git(repo_path, "push", _url(), *refs)


def buscar(repo_path: str, ref: str) -> None:
    """Traz `ref` do GitHub para o repositório local (fica em FETCH_HEAD)."""
    _git(repo_path, "fetch", _url(), ref)


def _cabecalhos() -> dict[str, str]:
    return {
        "Authorization": f"Bearer {settings.github_token}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
    }


def abrir_pr(branch: str, base: str, titulo: str, corpo: str) -> dict | None:
    """Abre o PR da branch da tarefa. `None` quando a integração está desligada.

    Um PR que já exista para a mesma branch não é erro: o GitHub responde 422 e
    nós devolvemos o que já está lá. Reexecutar uma tarefa empurra commits novos
    para a mesma branch, e o PR aberto continua valendo.
    """
    if not ativo():
        return None

    with httpx.Client(timeout=TIMEOUT) as cliente:
        resposta = cliente.post(
            f"{API}/repos/{settings.github_repo}/pulls",
            headers=_cabecalhos(),
            json={"title": titulo, "head": branch, "base": base, "body": corpo},
        )

        if resposta.status_code == 201:
            dados = resposta.json()
            logger.info("PR #%s aberto para %s", dados["number"], branch)
            return {"number": dados["number"], "url": dados["html_url"]}

        if resposta.status_code == 422:
            existente = _pr_da_branch(cliente, branch)
            if existente:
                logger.info("PR #%s já existia para %s", existente["number"], branch)
                return existente

        raise GitHubError(f"não consegui abrir o PR ({resposta.status_code}): {resposta.text}")


def _pr_da_branch(cliente: httpx.Client, branch: str) -> dict | None:
    dono = settings.github_repo.split("/")[0]
    resposta = cliente.get(
        f"{API}/repos/{settings.github_repo}/pulls",
        headers=_cabecalhos(),
        params={"head": f"{dono}:{branch}", "state": "open"},
    )
    if resposta.status_code != 200 or not resposta.json():
        return None
    dados = resposta.json()[0]
    return {"number": dados["number"], "url": dados["html_url"]}


def estado_do_pr(numero: int) -> dict | None:
    """Estado do PR e o resultado dos checks, para o painel mostrar."""
    if not ativo():
        return None

    with httpx.Client(timeout=TIMEOUT) as cliente:
        pr = cliente.get(
            f"{API}/repos/{settings.github_repo}/pulls/{numero}", headers=_cabecalhos()
        )
        if pr.status_code != 200:
            raise GitHubError(f"não consegui ler o PR #{numero}: {pr.status_code}")
        dados = pr.json()

        checks = cliente.get(
            f"{API}/repos/{settings.github_repo}/commits/{dados['head']['sha']}/check-runs",
            headers=_cabecalhos(),
        )
        corridas = checks.json().get("check_runs", []) if checks.status_code == 200 else []

    return {
        "number": numero,
        "url": dados["html_url"],
        "state": dados["state"],
        "merged": dados.get("merged", False),
        "mergeable": dados.get("mergeable"),
        "checks": [
            {"name": c["name"], "status": c["status"], "conclusion": c["conclusion"]}
            for c in corridas
        ],
    }


def mergear_pr(numero: int, titulo: str) -> str:
    """Faz o merge pelo PR. Devolve o SHA do commit de merge."""
    if not ativo():
        raise GitHubError("integração com o GitHub desligada")

    with httpx.Client(timeout=TIMEOUT) as cliente:
        resposta = cliente.put(
            f"{API}/repos/{settings.github_repo}/pulls/{numero}/merge",
            headers=_cabecalhos(),
            json={"commit_title": titulo, "merge_method": "merge"},
        )

    if resposta.status_code != 200:
        raise GitHubError(
            f"o merge do PR #{numero} falhou ({resposta.status_code}): {resposta.text}"
        )

    return resposta.json()["sha"]
