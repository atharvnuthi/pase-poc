"""Integração com o GitHub (Fase 5) - desligada por padrão.

O que mais importa aqui é o caminho **desligado**: sem token, nada muda no
comportamento do sistema. Uma integração opcional que altera o fluxo mesmo
inativa seria pior que não ter integração nenhuma.
"""

import httpx
import pytest

from app.common import github

#: A classe real, guardada antes de qualquer monkeypatch. Sem isto, substituir
#: `github.httpx.Client` substitui `httpx.Client` no módulo inteiro - e o
#: dublê passa a chamar a si mesmo até estourar a pilha.
CLIENTE_REAL = httpx.Client


def usar_transporte(monkeypatch, responder):
    """Faz o `github` falar com um transporte de mentira, sem tocar a rede."""
    monkeypatch.setattr(
        github.httpx,
        "Client",
        lambda **kw: CLIENTE_REAL(transport=httpx.MockTransport(responder)),
    )


@pytest.fixture
def desligado(monkeypatch):
    monkeypatch.setattr(github.settings, "github_token", "")
    monkeypatch.setattr(github.settings, "github_repo", "")


@pytest.fixture
def ligado(monkeypatch):
    monkeypatch.setattr(github.settings, "github_token", "token-de-teste")
    monkeypatch.setattr(github.settings, "github_repo", "dono/repo")


def test_sem_token_a_integracao_esta_desligada(desligado):
    assert github.ativo() is False


def test_so_o_token_nao_basta(monkeypatch):
    """Token sem repositório não sabe onde abrir PR."""
    monkeypatch.setattr(github.settings, "github_token", "token")
    monkeypatch.setattr(github.settings, "github_repo", "")

    assert github.ativo() is False


def test_desligado_abrir_pr_nao_faz_nada(desligado):
    """Devolve None em vez de levantar: o fluxo local segue intacto."""
    assert github.abrir_pr("feature/pase-1-x", "main", "t", "c") is None
    assert github.estado_do_pr(1) is None


def test_desligado_o_merge_por_pr_e_recusado(desligado):
    with pytest.raises(github.GitHubError, match="desligada"):
        github.mergear_pr(1, "t")


def test_abrir_pr_devolve_numero_e_url(ligado, monkeypatch):
    def transporte(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/repos/dono/repo/pulls"
        assert b"feature/pase-7-algo" in request.content
        return httpx.Response(
            201, json={"number": 42, "html_url": "https://github.com/dono/repo/pull/42"}
        )

    usar_transporte(monkeypatch, transporte)

    pr = github.abrir_pr("feature/pase-7-algo", "main", "feature: algo (task #7)", "corpo")

    assert pr == {"number": 42, "url": "https://github.com/dono/repo/pull/42"}


def test_pr_ja_existente_e_reaproveitado(ligado, monkeypatch):
    """Reexecutar uma tarefa empurra commits na mesma branch; o PR continua valendo."""
    def transporte(request: httpx.Request) -> httpx.Response:
        if request.method == "POST":
            return httpx.Response(422, json={"message": "A pull request already exists"})
        return httpx.Response(
            200, json=[{"number": 9, "html_url": "https://github.com/dono/repo/pull/9"}]
        )

    usar_transporte(monkeypatch, transporte)

    pr = github.abrir_pr("feature/pase-9-x", "main", "t", "c")

    assert pr == {"number": 9, "url": "https://github.com/dono/repo/pull/9"}


def test_erro_de_verdade_levanta(ligado, monkeypatch):
    def transporte(request: httpx.Request) -> httpx.Response:
        return httpx.Response(401, json={"message": "Bad credentials"})

    usar_transporte(monkeypatch, transporte)

    with pytest.raises(github.GitHubError, match="401"):
        github.abrir_pr("feature/pase-1-x", "main", "t", "c")


def test_merge_por_pr_devolve_o_sha(ligado, monkeypatch):
    def transporte(request: httpx.Request) -> httpx.Response:
        assert request.method == "PUT"
        return httpx.Response(200, json={"sha": "abc123", "merged": True})

    usar_transporte(monkeypatch, transporte)

    assert github.mergear_pr(42, "feature: integra algo (task #7)") == "abc123"


def test_desligado_enviar_nao_roda_git(desligado, monkeypatch):
    chamadas = []
    monkeypatch.setattr(github, "_git", lambda *a: chamadas.append(a))
    github.enviar("/qualquer", "master")
    assert chamadas == []


def test_git_nao_deixa_o_token_na_linha_de_comando_nem_no_erro(ligado, monkeypatch, tmp_path):
    visto = {}

    class Resultado:
        returncode = 1
        stdout = ""
        stderr = "fatal: token-de-teste recusado"

    def falso_run(argv, env, **kw):
        visto["argv"] = argv
        visto["env"] = env
        return Resultado()

    monkeypatch.setattr(github.subprocess, "run", falso_run)
    with pytest.raises(github.GitHubError) as erro:
        github.enviar(str(tmp_path), "master")

    assert "token-de-teste" not in " ".join(visto["argv"])
    assert "token-de-teste" not in str(erro.value)
    assert visto["env"]["GIT_CONFIG_KEY_0"] == "http.extraheader"
