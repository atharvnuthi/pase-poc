"""Retomar com ajuste: a pessoa diz o que mudar, e escolhe se o plano muda junto."""

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text

from app.orchestration import chain, redo, states
from app.orchestration.models import PlanningDocument
from app.task_layer.models import Task
from tests.conftest import requires_db

TABELAS = ("task_state_history", "execution_runs", "planning_documents", "tasks", "proposals")


@pytest.fixture
def limpo(session):
    def zerar():
        for t in TABELAS:
            session.execute(text(f"DELETE FROM {t}"))
        session.commit()

    zerar()
    yield session
    zerar()


@pytest.fixture
def client(limpo, monkeypatch):
    from app.main import app

    chamadas = []
    monkeypatch.setattr(
        chain, "rodar_execucao", lambda tid, **kw: chamadas.append(("execucao", tid, kw))
    )
    monkeypatch.setattr(chain, "rodar_replanejamento", lambda tid: chamadas.append(("replan", tid)))
    with TestClient(app) as c:
        c.chamadas = chamadas
        yield c


def _suspensa(session, **campos) -> Task:
    t = Task(
        title="Exportar CSV", description="d", module="transacoes", impact=3, complexity=1,
        status=states.SUSPENSA, alert="retries", **campos,
    )
    session.add(t)
    session.flush()
    session.add(
        PlanningDocument(
            task_id=t.id, acceptance_criteria=[{"id": "C1", "criterio": "x"}],
            affected_files=["client-backend/app/routes.py"], roadmap="Plano antigo.",
            tokens_estimated=1000,
        )
    )
    session.commit()
    return t


@requires_db
def test_retomar_sem_instrucao_continua_igual(client, limpo):
    t = _suspensa(limpo)

    r = client.post(f"/api/tasks/{t.id}/resume")

    assert r.status_code == 200 and r.json()["status"] == states.EM_EXECUCAO
    assert client.chamadas == [("execucao", t.id, {"trigger": "retry", "comentario": None})]


@requires_db
def test_com_instrucao_o_plano_e_reescrito_por_padrao(client, limpo):
    t = _suspensa(limpo)

    r = client.post(f"/api/tasks/{t.id}/resume", json={"instruction": "o endpoint já existe"})

    assert r.status_code == 200 and r.json()["status"] == states.EM_PLANEJAMENTO
    assert client.chamadas == [("replan", t.id)]
    limpo.refresh(t)
    assert t.status == states.EM_PLANEJAMENTO
    historico = redo.historico_de(limpo, t)
    assert "o endpoint já existe" in historico and "Plano antigo." in historico


@requires_db
def test_plano_reescrito_volta_ao_gate_quando_a_tarefa_exige_aprovacao(client, limpo):
    t = _suspensa(limpo, plan_approval_required=True, plan_approved=True)

    client.post(f"/api/tasks/{t.id}/resume", json={"instruction": "mude o escopo"})

    limpo.refresh(t)
    assert t.plan_approved is False  # o plano mudou: a pessoa o vê de novo


@requires_db
def test_sem_atualizar_o_plano_a_instrucao_vai_ao_executor(client, limpo):
    t = _suspensa(limpo)

    r = client.post(
        f"/api/tasks/{t.id}/resume",
        json={"instruction": "use o helper formatMoney", "update_plan": False},
    )

    assert r.status_code == 200 and r.json()["status"] == states.EM_EXECUCAO
    assert client.chamadas == [
        ("execucao", t.id, {"trigger": "retry", "comentario": "use o helper formatMoney"})
    ]
    limpo.refresh(t)
    assert t.plan_feedback is None  # o plano ficou como estava


@requires_db
def test_instrucao_em_branco_vale_como_sem_instrucao(client, limpo):
    t = _suspensa(limpo)

    client.post(f"/api/tasks/{t.id}/resume", json={"instruction": "   "})

    assert client.chamadas[0][0] == "execucao"


@requires_db
def test_so_retoma_tarefa_suspensa(client, limpo):
    t = _suspensa(limpo)
    t.status = states.EM_EXECUCAO
    limpo.commit()

    assert client.post(f"/api/tasks/{t.id}/resume", json={"instruction": "x"}).status_code == 409
