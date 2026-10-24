"""Sugestões de atualização do contexto, nascidas de uma tarefa aprovada."""

import json

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text

from app.common import context_store, context_suggestions
from app.common.models import ContextSuggestion
from app.orchestration.models import PlanningDocument
from app.task_layer.models import Task
from tests.conftest import requires_db

TABELAS = (
    "context_suggestions", "context_document_versions", "context_documents",
    "planning_documents", "task_state_history", "tasks", "proposals",
)


@pytest.fixture
def limpo(session):
    def zerar():
        for t in TABELAS:
            session.execute(text(f"DELETE FROM {t}"))
        session.commit()

    zerar()
    context_store.bootstrap(session)
    session.commit()
    yield session
    zerar()


@pytest.fixture
def client(limpo):
    from app.main import app

    with TestClient(app) as c:
        yield c


def _tarefa(session) -> Task:
    t = Task(
        title="Exportar em CSV", description="Baixar as transações em CSV", module="transacoes",
        impact=3, complexity=1, status="finalizada", final_outcome="aprovada",
    )
    session.add(t)
    session.flush()
    session.add(
        PlanningDocument(
            task_id=t.id,
            acceptance_criteria=[{"id": "C1", "criterio": "A pessoa baixa um CSV"}],
            affected_files=["a.py"], roadmap="Botão de exportar.", tokens_estimated=1,
        )
    )
    session.commit()
    return t


def _resposta(aplicavel: bool, content: str = "# Doc\n\nnovo") -> str:
    return json.dumps(
        {"aplicavel": aplicavel, "reasoning": "r", "summary": "registra o CSV", "content": content}
    )


def test_o_pedido_leva_o_que_foi_entregue():
    texto = context_suggestions.pedido_da_tarefa(
        "Exportar em CSV", "Baixar em CSV", "Botão.", [{"criterio": "baixa um CSV"}]
    )
    assert "Exportar em CSV" in texto and "baixa um CSV" in texto
    assert "aplicavel=false" in texto  # o modelo pode dizer que nada mudou


@requires_db
def test_so_vira_sugestao_quando_o_modelo_diz_que_se_aplica(limpo, mock_providers, monkeypatch):
    t = _tarefa(limpo)
    # project-context: aplica; features: não aplica
    mock_providers.responses = [_resposta(True), _resposta(False, "")]

    criadas = context_suggestions.gerar_para_tarefa(t.id)

    assert criadas == 1
    limpo.expire_all()
    s = limpo.query(ContextSuggestion).one()
    assert s.slug == "project-context" and s.status == "pendente"
    assert s.base_version == 1 and s.task_id == t.id
    assert "novo" in s.diff


@requires_db
def test_nao_duplica_sugestao_pendente_da_mesma_tarefa(limpo, mock_providers):
    t = _tarefa(limpo)
    mock_providers.responses = [_resposta(True), _resposta(True)]
    context_suggestions.gerar_para_tarefa(t.id)
    mock_providers.responses = [_resposta(True), _resposta(True)]

    assert context_suggestions.gerar_para_tarefa(t.id) == 0


@requires_db
def test_desligada_nao_gasta_chamada(limpo, mock_providers, monkeypatch):
    t = _tarefa(limpo)
    monkeypatch.setattr(context_suggestions.settings, "context_suggestions_enabled", False)

    assert context_suggestions.gerar_para_tarefa(t.id) == 0
    assert mock_providers.calls == []


@requires_db
def test_aceitar_grava_versao_nova_com_a_origem_no_historico(client, limpo, mock_providers):
    t = _tarefa(limpo)
    mock_providers.responses = [_resposta(True, "# Contexto\n\nagora com CSV"), _resposta(False, "")]
    context_suggestions.gerar_para_tarefa(t.id)
    sugestao = client.get("/api/context/suggestions").json()[0]

    r = client.post(f"/api/context/suggestions/{sugestao['id']}/accept")

    assert r.status_code == 200 and r.json()["version"] == 2
    doc = client.get("/api/context/doc/project-context").json()
    assert doc["content"].endswith("agora com CSV") and doc["updated_by"].startswith("ia")
    historico = client.get("/api/context/doc/project-context/history").json()
    assert f"tarefa #{t.id}" in historico[0]["note"]
    assert client.get("/api/context/suggestions").json() == []


@requires_db
def test_aceitar_recusa_quando_o_documento_mudou_no_meio_tempo(client, limpo, mock_providers):
    t = _tarefa(limpo)
    mock_providers.responses = [_resposta(True), _resposta(False, "")]
    context_suggestions.gerar_para_tarefa(t.id)
    sugestao = client.get("/api/context/suggestions").json()[0]
    client.put(
        "/api/context/doc/project-context", json={"content": "# Editado\n\npor uma pessoa", "note": "n"}
    )

    r = client.post(f"/api/context/suggestions/{sugestao['id']}/accept")

    assert r.status_code == 409 and "mudou desde a sugestão" in r.json()["detail"]
    assert "por uma pessoa" in client.get("/api/context/doc/project-context").json()["content"]


@requires_db
def test_dispensar_e_so_uma_vez(client, limpo, mock_providers):
    t = _tarefa(limpo)
    mock_providers.responses = [_resposta(True), _resposta(False, "")]
    context_suggestions.gerar_para_tarefa(t.id)
    sugestao = client.get("/api/context/suggestions").json()[0]

    assert client.post(f"/api/context/suggestions/{sugestao['id']}/dismiss").status_code == 200
    assert client.post(f"/api/context/suggestions/{sugestao['id']}/dismiss").status_code == 409
    assert client.post("/api/context/suggestions/99999/accept").status_code == 404


@requires_db
def test_reverter_a_tarefa_torna_a_sugestao_obsoleta(limpo, mock_providers):
    t = _tarefa(limpo)
    mock_providers.responses = [_resposta(True), _resposta(False, "")]
    context_suggestions.gerar_para_tarefa(t.id)

    assert context_suggestions.obsoletar_da_tarefa(limpo, t.id) == 1
    limpo.commit()
    assert limpo.query(ContextSuggestion).one().status == "obsoleta"
    assert context_suggestions.pendentes(limpo) == []
