"""Convenções de branch e commit (`engineering-guidelines` §3 do contexto).

Geração e conferência são testadas juntas porque é o par que importa: o que o
Executor produz tem de ser aceito pelo que confere, sempre.
"""

import pytest

from app.common import conventions


@pytest.mark.parametrize(
    "entrada,esperado",
    [
        ("Exportar transações em CSV", "exportar-transacoes-em-csv"),
        ("Edição de data - na lista!", "edicao-de-data-na-lista"),
        ("  ", "sem-titulo"),
        ("ÁÉÍÓÚ ção", "aeiou-cao"),
    ],
)
def test_slug_remove_acento_e_pontuacao(entrada, esperado):
    assert conventions.slug(entrada) == esperado


def test_slug_nao_passa_do_limite():
    gerado = conventions.slug("palavra " * 50)
    assert len(gerado) <= conventions.TAMANHO_DO_SLUG
    assert not gerado.endswith("-")


def test_branch_liga_a_tarefa_e_marca_o_executor():
    branch = conventions.branch_de(12, "Exportar transações em CSV", "feature")

    assert branch == "feature/pase-12-exportar-transacoes-em-csv"
    assert conventions.e_do_executor(branch)
    assert conventions.conferir_branch(branch)[0]


def test_tipo_desconhecido_cai_em_feature():
    """Tipo inválido não pode derrubar uma run - só perde a precisão."""
    assert conventions.branch_de(1, "x", "inventado").startswith("feature/")


@pytest.mark.parametrize("tipo", conventions.TIPOS)
def test_todo_tipo_valido_gera_branch_e_commit_conformes(tipo):
    branch = conventions.branch_de(3, "Alguma coisa", tipo)
    commit = conventions.commit_de(3, "Alguma coisa", "transacoes", tipo)

    assert conventions.conferir_branch(branch)[0], branch
    assert conventions.conferir_commit(commit)[0], commit


def test_commit_leva_escopo_e_numero_da_tarefa():
    assert conventions.commit_de(7, "Editar data", "transacoes", "feature") == (
        "feature(transacoes): Editar data (task #7)"
    )


def test_commit_sem_modulo_nao_inventa_escopo():
    assert conventions.commit_de(7, "Editar data", None, "fix") == (
        "fix: Editar data (task #7)"
    )


def test_merge_tem_formato_proprio_e_conforme():
    mensagem = conventions.merge_de(7, "Editar data", "transacoes", "feature")

    assert mensagem.startswith("feature(transacoes): integra ")
    assert conventions.conferir_commit(mensagem)[0]


@pytest.mark.parametrize(
    "mensagem",
    [
        "pase: faz alguma coisa",          # o formato antigo
        "feat(login): adiciona validação",  # `feat` não está no padrão da equipe
        "adiciona coisa",                   # sem tipo
        "feature adiciona coisa",           # sem dois-pontos
        "",
    ],
)
def test_mensagem_fora_do_padrao_e_recusada(mensagem):
    conforme, aviso = conventions.conferir_commit(mensagem)

    assert conforme is False
    assert "padrão" in aviso


@pytest.mark.parametrize(
    "branch",
    ["pase/task-1", "minha-branch", "Feature/coisa", "feature/"],
)
def test_branch_fora_do_padrao_e_recusada(branch):
    assert conventions.conferir_branch(branch)[0] is False


def test_conferencia_aceita_mensagem_de_varias_linhas():
    """Só a primeira linha é o assunto; o corpo é livre."""
    mensagem = "fix(execution): corrige o gate\n\nCorpo explicando o porquê."

    assert conventions.conferir_commit(mensagem)[0]
