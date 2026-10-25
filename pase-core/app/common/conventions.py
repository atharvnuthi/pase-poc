"""Convenções de branch e de mensagem de commit (`engineering-guidelines` §3 do contexto).

Este módulo faz as duas pontas: **gera** o nome da branch e a mensagem que o
Executor usa, e **confere** se estão conformes antes do commit.

As duas pontas moram juntas de propósito. Uma convenção que só existe no prompt é
um pedido - e este projeto já mediu cinco vezes o que acontece com garantias que
dependem da boa vontade do modelo. Aqui o formato é construído por código e
validado por código; o modelo não participa da decisão.
"""

from __future__ import annotations

import re
import unicodedata

#: Tipos aceitos, conforme o padrão da equipe.
TIPOS = ("feature", "fix", "refactor", "docs", "test", "chore")

#: `<tipo>(<escopo opcional>): <descrição>` - o escopo é opcional por escolha da
#: equipe, e o exemplo do padrão traz as duas formas.
MENSAGEM_DE_COMMIT = re.compile(
    rf"^(?:{'|'.join(TIPOS)})(?:\([a-z0-9][a-z0-9._-]*\))?: .+",
)

#: Branches de trabalho: `feature/*` ou `hotfix/*` (guia de fluxo de ramos §2); as do
#: Executor são `<tipo>/pase-<id>-<slug>`. `release/x.x.x` é de outra natureza e é
#: criada pelo fluxo de releases, nunca por uma tarefa.
BRANCHES_DE_TRABALHO = ("feature", "hotfix")
NOME_DE_BRANCH = re.compile(
    rf"^(?:{'|'.join(BRANCHES_DE_TRABALHO)})/[A-Za-z0-9][A-Za-z0-9._/-]*$|^release/\d+\.\d+\.\d+$",
)

#: Marca a branch como território do Executor - nunca editada à mão (README.md).
PREFIXO_DO_EXECUTOR = "pase-"

TAMANHO_DO_SLUG = 40


def slug(texto: str) -> str:
    """Trecho legível e seguro para nome de branch.

    Sem acento e sem caixa alta: `git` aceita os dois, mas um nome de branch com
    `ç` vira dor de cabeça na primeira vez que alguém o digita no terminal.
    """
    sem_acento = (
        unicodedata.normalize("NFKD", texto).encode("ascii", "ignore").decode("ascii")
    )
    limpo = re.sub(r"[^a-zA-Z0-9]+", "-", sem_acento).strip("-").lower()
    return limpo[:TAMANHO_DO_SLUG].strip("-") or "sem-titulo"


def tipo_valido(tipo: str | None) -> str:
    """Cai em `feature` quando o tipo é desconhecido, em vez de quebrar a run."""
    return tipo if tipo in TIPOS else "feature"


def prefixo_da_branch(tipo: str | None) -> str:
    """`hotfix` para correção (`fix`), `feature` para todo o resto.

    O guia só conhece duas branches de trabalho. Um refactor ou uma doc é "alteração
    planejada" - `feature`; só a correção vira `hotfix`. O **tipo do commit**
    continua sendo o da tarefa (`fix`, `refactor`, ...): são duas convenções
    diferentes, e a mensagem diz o que a mudança é mesmo quando a branch não diz.
    """
    return "hotfix" if tipo_valido(tipo) == "fix" else "feature"


def branch_de(task_id: int, titulo: str, tipo: str | None = "feature") -> str:
    """`<feature|hotfix>/pase-<id>-<slug>` - conforma com o padrão e continua rastreável.

    O `<id>` liga a branch à tarefa sem precisar consultar nada, e o `pase-`
    sinaliza que ela é do Executor: quem vê `feature/pase-12-exportar-csv` sabe
    de imediato que aquilo não é trabalho humano e não deve ser editado na mão.
    """
    return f"{prefixo_da_branch(tipo)}/{PREFIXO_DO_EXECUTOR}{task_id}-{slug(titulo)}"


def e_do_executor(branch: str) -> bool:
    _, _, nome = branch.partition("/")
    return nome.startswith(PREFIXO_DO_EXECUTOR)


def commit_de(task_id: int, titulo: str, modulo: str | None, tipo: str | None) -> str:
    """Mensagem do commit da run, com o escopo sendo o módulo da tarefa."""
    escopo = f"({slug(modulo)})" if modulo else ""
    return f"{tipo_valido(tipo)}{escopo}: {titulo.strip().rstrip('.')} (task #{task_id})"


def merge_de(task_id: int, titulo: str, modulo: str | None, tipo: str | None) -> str:
    """Mensagem do merge na principal."""
    escopo = f"({slug(modulo)})" if modulo else ""
    return (
        f"{tipo_valido(tipo)}{escopo}: integra {titulo.strip().rstrip('.')} "
        f"(task #{task_id})"
    )


def conferir_commit(mensagem: str) -> tuple[bool, str]:
    """A mensagem segue `<tipo>(<escopo>): <descrição>`?"""
    primeira = (mensagem or "").strip().splitlines()[0] if (mensagem or "").strip() else ""
    if MENSAGEM_DE_COMMIT.match(primeira):
        return True, ""
    return False, (
        f"mensagem de commit fora do padrão: {primeira!r}. "
        f"O formato é `<tipo>(<escopo opcional>): <descrição>`, "
        f"com tipo em {', '.join(TIPOS)}."
    )


def conferir_branch(nome: str) -> tuple[bool, str]:
    """O nome da branch segue `<tipo>/<nome>`?"""
    if NOME_DE_BRANCH.match(nome or ""):
        return True, ""
    return False, (
        f"nome de branch fora do padrão: {nome!r}. "
        "O formato é `feature/<nome>`, `hotfix/<nome>` ou `release/x.x.x`."
    )
