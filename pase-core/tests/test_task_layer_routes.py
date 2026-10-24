"""Endpoints de ingestão e o formato do envelope (SPEC-03 §1)."""

import json

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text

from app.task_layer.models import Proposal
from tests.conftest import requires_db

P1 = json.dumps({"title": "Exportar CSV", "description": "Baixar transações.", "module": "transacoes"})
P1B_NAO = json.dumps({"requires_zone": False, "reasoning": "homogênea"})
P2A_OK = json.dumps({"coherent": True, "reason": "ok", "needs_adjustment": False})
P2B = json.dumps({"impact": 4, "complexity": 2, "confidence": 0.8, "risk_tier": "medio"})

FUNIL_COMPLETO = [P1, P1B_NAO, P2A_OK, P2B]


@pytest.fixture
def client(session):
    from app.main import app

    def zerar():
        for tabela in ("task_state_history", "tasks", "discarded_proposals", "proposals"):
            session.execute(text(f"DELETE FROM {tabela}"))
        session.commit()

    zerar()
    with TestClient(app) as test_client:
        yield test_client
    zerar()


@requires_db
def test_captacao_ativa_devolve_o_envelope_completo(client, mock_providers, session):
    mock_providers.responses = list(FUNIL_COMPLETO)

    response = client.post(
        "/api/proposals/external",
        json={"user_id": 1, "text": "queria baixar minhas transações em csv"},
    )

    assert response.status_code == 200
    corpo = response.json()
    assert corpo["outcome"] == "candidata"
    assert corpo["task_id"] is not None
    assert corpo["detail"]  # é o texto que o modal do FinTrack exibe
    assert corpo["module"] == "transacoes"
    assert corpo["risk_tier"] == "medio"

    proposal = session.get(Proposal, corpo["proposal_id"])
    assert proposal.origin == "external"
    assert proposal.user_id == 1


@requires_db
def test_sugestao_interna_funcional_passa_pelo_funil_inteiro(client, mock_providers):
    mock_providers.responses = list(FUNIL_COMPLETO)

    response = client.post(
        "/api/proposals/internal",
        json={"type": "funcional", "author": "Atharv", "text": "exportar transações em CSV"},
    )

    assert response.status_code == 200
    assert response.json()["outcome"] == "candidata"
    assert len(mock_providers.calls) == 4  # P1, P1b, P2a, P2b


@requires_db
def test_engenharia_com_autor_autorizado_entra(client, mock_providers, monkeypatch):
    from app.common.config import settings

    monkeypatch.setattr(settings, "engineering_authors", "PASE Audit,Atharv")
    mock_providers.responses = [P1, P2B]

    response = client.post(
        "/api/proposals/internal",
        json={
            "type": "engenharia",
            "author": "Atharv",
            "text": "atualizar dependências do client-backend",
        },
    )

    assert response.status_code == 200
    assert response.json()["outcome"] == "candidata"


@requires_db
def test_engenharia_com_autor_nao_autorizado_da_403(client, monkeypatch):
    from app.common.config import settings

    monkeypatch.setattr(settings, "engineering_authors", "PASE Audit")

    response = client.post(
        "/api/proposals/internal",
        json={"type": "engenharia", "author": "Estagiário", "text": "trocar o banco de dados"},
    )

    assert response.status_code == 403
    assert "não tem papel" in response.json()["detail"]


@requires_db
def test_ai_generate_exploratoria_gera_e_processa(client, mock_providers):
    mock_providers.responses = [
        json.dumps({"text": "queria baixar minhas transações em csv"}),
        *FUNIL_COMPLETO,
    ]

    response = client.post("/api/proposals/ai-generate", json={"mode": "exploratoria"})

    assert response.status_code == 200
    assert response.json()["outcome"] == "candidata"


@requires_db
def test_lacunas_sem_achado_responde_sem_proposta(client, mock_providers):
    """P3b devolver null é resposta legítima, não erro."""
    mock_providers.responses = [json.dumps({"text": None})]

    response = client.post("/api/proposals/ai-generate", json={"mode": "lacunas"})

    assert response.status_code == 200
    corpo = response.json()
    assert corpo["outcome"] == "sem_proposta"
    assert corpo["proposal_id"] is None


@requires_db
def test_texto_vazio_e_recusado_antes_de_gastar_llm(client, mock_providers):
    response = client.post("/api/proposals/external", json={"user_id": 1, "text": "oi"})

    assert response.status_code == 422
    assert mock_providers.calls == []
