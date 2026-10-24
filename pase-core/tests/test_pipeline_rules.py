"""As regras do guia de fluxo de ramos, como código (documento `git-guide` do contexto)."""

import pytest

from app.common import conventions
from app.common.pipeline_rules import (
    PipelineError,
    branch_da_release,
    proxima_versao,
    tipo_de,
    validar_integracao,
    validar_origem_da_criacao,
    validar_versao,
)


@pytest.mark.parametrize(
    "nome, tipo",
    [
        ("main", "main"),
        ("master", "main"),
        ("develop", "develop"),
        ("feature/pase-3-modo-escuro", "feature"),
        ("hotfix/pase-9-timeout", "hotfix"),
        ("release/1.4.0", "release"),
        ("release/1.4", "outra"),
        ("fix/coisa", "outra"),
    ],
)
def test_tipo_da_branch(nome, tipo):
    assert tipo_de(nome) == tipo


@pytest.mark.parametrize(
    "origem, destino",
    [
        ("feature/pase-1-x", "develop"),
        ("hotfix/pase-1-x", "develop"),
        ("feature/pase-1-x", "release/1.0.0"),
        ("hotfix/pase-1-x", "release/1.0.0"),
        ("release/1.0.0", "main"),
    ],
)
def test_integracoes_da_matriz_sao_permitidas(origem, destino):
    assert validar_integracao(origem, destino)


@pytest.mark.parametrize(
    "origem, destino",
    [
        ("feature/pase-1-x", "main"),  # nunca direto à principal
        ("hotfix/pase-1-x", "main"),
        ("develop", "main"),  # a develop não é versão
        ("develop", "feature/pase-1-x"),
        ("develop", "hotfix/pase-1-x"),
        ("develop", "release/1.0.0"),
        ("release/1.0.0", "develop"),
        ("feature/pase-1-x", "feature/pase-2-y"),
        ("feature/pase-1-x", "hotfix/pase-2-y"),
        ("main", "develop"),
    ],
)
def test_integracoes_proibidas_levantam(origem, destino):
    with pytest.raises(PipelineError):
        validar_integracao(origem, destino)


def test_master_vale_como_main():
    with pytest.raises(PipelineError):
        validar_integracao("feature/pase-1-x", "master", base="master")
    assert validar_integracao("release/1.0.0", "master", base="master")


def test_branches_de_trabalho_nao_nascem_da_develop():
    for nome in ("feature/pase-1-x", "hotfix/pase-1-x", "release/1.0.0"):
        with pytest.raises(PipelineError, match="develop"):
            validar_origem_da_criacao(nome, "develop")
        validar_origem_da_criacao(nome, "main")


@pytest.mark.parametrize("versao", ["1", "1.0", "v1.0.0", "1.0.0-rc1", "", "a.b.c"])
def test_versao_invalida(versao):
    with pytest.raises(PipelineError):
        validar_versao(versao)


def test_proxima_versao_semantica():
    assert proxima_versao(None) == "1.0.0"
    assert proxima_versao("1.4.2") == "1.5.0"
    assert proxima_versao("1.4.2", "patch") == "1.4.3"
    assert proxima_versao("1.4.2", "major") == "2.0.0"
    assert branch_da_release("1.5.0") == "release/1.5.0"


def test_correcao_vira_hotfix_e_o_resto_feature():
    assert conventions.branch_de(3, "Corrige saldo", "fix").startswith("hotfix/pase-3-")
    for tipo in ("feature", "refactor", "docs", "test", "chore"):
        assert conventions.branch_de(3, "algo", tipo).startswith("feature/pase-3-")


@pytest.mark.parametrize(
    "nome", ["feature/pase-1-x", "hotfix/pase-1-x", "release/1.4.0", "feature/JIRA-123-algo"]
)
def test_nomes_conformes_ao_guia(nome):
    assert conventions.conferir_branch(nome)[0], nome


@pytest.mark.parametrize("nome", ["fix/pase-1-x", "release/1.4", "develop", "feature/"])
def test_nomes_fora_do_guia(nome):
    assert not conventions.conferir_branch(nome)[0], nome
