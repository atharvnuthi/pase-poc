"""Regras do fluxo de branches, em código (documento `git-guide` do contexto).

O guia é lido por humanos, por agentes e pelo CI. Este módulo é a parte que o
**sistema** não pode esquecer: quais integrações existem, de onde cada branch
nasce, e o que nunca acontece. É a mesma lição do resto do projeto - uma regra que
só vive em texto é um pedido, e a única versão que se sustenta é a que o código
confere antes de tocar o repositório.

Nada aqui chama `git`. As funções recebem nomes e respondem se a operação é
permitida; quem executa é `git_service`, que pergunta antes.
"""

from __future__ import annotations

import re

MAIN = "main"
DEVELOP = "develop"

RELEASE = re.compile(r"^release/(\d+)\.(\d+)\.(\d+)$")
VERSAO = re.compile(r"^(\d+)\.(\d+)\.(\d+)$")


class PipelineError(RuntimeError):
    """A operação viola o fluxo de branches."""


def tipo_de(nome: str, base: str = MAIN) -> str:
    """`main` | `develop` | `feature` | `hotfix` | `release` | `outra`.

    `base` é o nome real da branch de produção do repositório (`main` ou
    `master`): o guia fala em `main`, e o repositório pode ainda se chamar `master`.
    """
    if nome in (MAIN, "master", base):
        return "main"
    if nome == DEVELOP:
        return "develop"
    if RELEASE.match(nome):
        return "release"
    prefixo = nome.partition("/")[0]
    return prefixo if prefixo in ("feature", "hotfix") else "outra"


#: Matriz mínima do guia §16 - o que pode entrar em quê, e por qual método.
INTEGRACOES_PERMITIDAS = {
    ("feature", "develop"): "merge direto com --no-ff",
    ("hotfix", "develop"): "merge direto com --no-ff",
    ("feature", "release"): "merge direto com --no-ff",
    ("hotfix", "release"): "merge direto com --no-ff",
    ("release", "main"): "Pull Request obrigatório",
}


def validar_integracao(origem: str, destino: str, base: str = MAIN) -> str:
    """Devolve o método permitido, ou levanta `PipelineError` com a regra violada."""
    t_origem, t_destino = tipo_de(origem, base), tipo_de(destino, base)

    if t_origem == "develop":
        raise PipelineError(
            f"`develop` nunca entra em outra branch ({origem} → {destino}): ela é "
            "o ambiente de testes, não uma versão pronta para produção."
        )
    if t_destino == "main" and t_origem != "release":
        raise PipelineError(
            f"`{origem}` não pode entrar na principal: só `release/x.x.x`, por Pull Request."
        )
    if t_destino == "feature" or t_destino == "hotfix":
        raise PipelineError(f"nada é integrado em `{destino}`: ela só recebe a principal.")

    metodo = INTEGRACOES_PERMITIDAS.get((t_origem, t_destino))
    if metodo is None:
        raise PipelineError(f"integração fora do fluxo: {origem} → {destino}.")
    return metodo


def validar_origem_da_criacao(nome: str, origem: str, base: str = MAIN) -> None:
    """`feature/*`, `hotfix/*` e `release/*` nascem sempre da principal."""
    if tipo_de(nome, base) in ("feature", "hotfix", "release") and tipo_de(origem, base) != "main":
        raise PipelineError(
            f"`{nome}` nasce da principal, nunca de `{origem}`"
            + (" (a develop é só ambiente de testes)." if origem == DEVELOP else ".")
        )


def validar_versao(versao: str) -> tuple[int, int, int]:
    achou = VERSAO.match(versao or "")
    if not achou:
        raise PipelineError(f"versão inválida: {versao!r}. O formato é MAJOR.MINOR.PATCH.")
    return tuple(int(g) for g in achou.groups())  # type: ignore[return-value]


def proxima_versao(ultima: str | None, nivel: str = "minor") -> str:
    """Próxima versão semântica a partir da última tag; `1.0.0` se não há tag."""
    if not ultima:
        return "1.0.0"
    major, minor, patch = validar_versao(ultima)
    if nivel == "major":
        return f"{major + 1}.0.0"
    if nivel == "patch":
        return f"{major}.{minor}.{patch + 1}"
    return f"{major}.{minor + 1}.0"


def branch_da_release(versao: str) -> str:
    validar_versao(versao)
    return f"release/{versao}"
