"""Retorno ao usuário do FinTrack (`GET /api/proposals/mine`, monografia §4.3.1).

O contrato é lido pela interface do FinTrack: os nomes dos campos e das situações
são conferidos aqui um a um.
"""

import json

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text

from app.orchestration.models import Release
from app.task_layer.models import DiscardedProposal, Proposal, Task
from tests.conftest import requires_db

USUARIO = 7
CAMPOS = {"id", "texto", "titulo", "criada_em", "situacao", "detalhe"}
VERSAO = "9.9.1"


@pytest.fixture
def client(session):
    from app.main import app

    def zerar():
        for tabela in ("task_state_history", "tasks", "discarded_proposals", "proposals"):
            session.execute(text(f"DELETE FROM {tabela}"))
        session.execute(text("DELETE FROM releases WHERE version = :v"), {"v": VERSAO})
        session.commit()

    zerar()
    with TestClient(app) as test_client:
        yield test_client
    zerar()


def _proposta(session, outcome=None, user_id=USUARIO, **campos) -> Proposal:
    proposal = Proposal(
        origin="external",
        raw_text=campos.pop("raw_text", "quero uma coisa"),
        user_id=user_id,
        title=campos.pop("title", "Título normalizado"),
        module="transacoes",
        outcome=outcome,
        **campos,
    )
    session.add(proposal)
    session.flush()
    return proposal


def _tarefa(session, proposal, **campos) -> Task:
    task = Task(
        proposal_id=proposal.id, title="t", description="d", module="transacoes", **campos
    )
    session.add(task)
    session.flush()
    return task


def _por_id(corpo: list[dict]) -> dict[int, dict]:
    return {item["id"]: item for item in corpo}


@requires_db
def test_cada_desfecho_vira_uma_situacao_para_o_usuario(client, session):
    release = Release(version=VERSAO, branch=f"release/{VERSAO}", status="publicada")
    session.add(release)
    session.flush()

    em_analise = _proposta(session)
    descartada = _proposta(session, "descartada_incoerente")
    session.add(
        DiscardedProposal(
            proposal_id=descartada.id,
            reason_type="incoerente",
            reason_text="Mineração é investimento. Trecho do contexto violado: “Investimentos”",
            cited_excerpt="Investimentos, câmbio, múltiplas moedas.",
        )
    )
    ja_existe = _proposta(
        session, "descartada_duplicata", feedback="O FinTrack já faz isso: “Relatórios”."
    )
    personalizada = _proposta(
        session, "redirecionada_zona", feedback="Ajustamos a área personalizável da tela X."
    )
    aguardando = _proposta(session, "candidata")
    _tarefa(session, aguardando, status="candidata")
    desenvolvendo = _proposta(session, "candidata")
    _tarefa(session, desenvolvendo, status="em_execucao")
    recusada = _proposta(session, "recusada_pelo_humano")
    _tarefa(session, recusada, status="finalizada", final_outcome="recusada")
    aprovada = _proposta(session, "implementada")
    _tarefa(session, aprovada, status="finalizada", final_outcome="aprovada", stage="develop")
    publicada = _proposta(session, "implementada")
    _tarefa(
        session, publicada, status="finalizada", final_outcome="aprovada",
        stage="producao", release_id=release.id,
    )
    revertida = _proposta(session, "revertida")
    _tarefa(session, revertida, status="finalizada", final_outcome="revertida")
    _proposta(session, "candidata", user_id=USUARIO + 1)  # de outra pessoa
    session.commit()

    resposta = client.get("/api/proposals/mine", params={"user_id": USUARIO})

    assert resposta.status_code == 200
    corpo = resposta.json()
    assert len(corpo) == 10
    assert all(set(item) == CAMPOS for item in corpo)
    itens = _por_id(corpo)
    esperado = {
        em_analise.id: "em_analise",
        descartada.id: "descartada",
        ja_existe.id: "ja_existe",
        personalizada.id: "personalizada",
        aguardando.id: "aguardando_decisao",
        desenvolvendo.id: "em_desenvolvimento",
        recusada.id: "recusada",
        aprovada.id: "aprovada",
        publicada.id: "publicada",
        revertida.id: "recusada",
    }
    assert {i: itens[i]["situacao"] for i in esperado} == esperado

    assert "Investimentos, câmbio, múltiplas moedas." in itens[descartada.id]["detalhe"]
    assert itens[ja_existe.id]["detalhe"] == "O FinTrack já faz isso: “Relatórios”."
    assert itens[personalizada.id]["detalhe"].startswith("Ajustamos")
    assert VERSAO in itens[publicada.id]["detalhe"]
    assert all(item["detalhe"] for item in corpo)


@requires_db
def test_mais_recente_primeiro_e_texto_encurtado(client, session):
    antiga = _proposta(session, raw_text="x" * 300, title=None)
    nova = _proposta(session)
    session.commit()

    corpo = client.get("/api/proposals/mine", params={"user_id": USUARIO}).json()

    assert [item["id"] for item in corpo] == [nova.id, antiga.id]
    assert len(corpo[1]["texto"]) <= 140 and corpo[1]["texto"].endswith("…")
    assert corpo[1]["titulo"] is None
    assert corpo[0]["criada_em"]


@requires_db
def test_release_ainda_nao_publicada_diz_a_versao(client, session):
    release = Release(version=VERSAO, branch=f"release/{VERSAO}")
    session.add(release)
    session.flush()
    proposta = _proposta(session, "implementada")
    _tarefa(
        session, proposta, status="finalizada", final_outcome="aprovada",
        stage="release", release_id=release.id,
    )
    session.commit()

    item = client.get("/api/proposals/mine", params={"user_id": USUARIO}).json()[0]

    assert item["situacao"] == "aprovada"
    assert VERSAO in item["detalhe"]


@requires_db
def test_refazer_vale_a_tarefa_mais_recente(client, session):
    proposta = _proposta(session, "candidata")
    _tarefa(session, proposta, status="finalizada", final_outcome="recusada")
    _tarefa(session, proposta, status="em_planejamento")
    session.commit()

    item = client.get("/api/proposals/mine", params={"user_id": USUARIO}).json()[0]

    assert item["situacao"] == "em_desenvolvimento"


@requires_db
def test_ponta_a_ponta_a_resposta_do_modal_e_a_situacao_depois(client, mock_providers):
    mock_providers.responses = [
        json.dumps({"title": "Exportar CSV", "description": "Baixar.", "module": "transacoes"}),
        json.dumps({"requires_zone": False, "reasoning": "homogênea"}),
        json.dumps({"coherent": True, "reason": "ok", "needs_adjustment": False}),
        json.dumps({"impact": 4, "complexity": 2, "confidence": 0.8, "risk_tier": "medio"}),
    ]
    envelope = client.post(
        "/api/proposals/external", json={"user_id": USUARIO, "text": "baixar em csv"}
    ).json()

    corpo = client.get("/api/proposals/mine", params={"user_id": USUARIO}).json()

    assert corpo[0]["id"] == envelope["proposal_id"]
    assert corpo[0]["situacao"] == "aguardando_decisao"
    assert corpo[0]["titulo"] == "Exportar CSV"
    assert corpo[0]["texto"] == "baixar em csv"


@requires_db
def test_sem_user_id_e_erro_de_validacao(client):
    assert client.get("/api/proposals/mine").status_code == 422


@requires_db
def test_ocorrencias_por_tarefa_para_o_painel(client, session):
    pesada = _proposta(session, "candidata", occurrences=3)
    tarefa_pesada = _tarefa(session, pesada, status="candidata")
    avulsa = _proposta(session, "candidata")
    _tarefa(session, avulsa, status="candidata")
    session.commit()

    corpo = client.get("/api/proposals/occurrences").json()

    assert corpo == {str(tarefa_pesada.id): 3}
