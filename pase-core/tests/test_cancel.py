"""Cancelar uma tarefa: com a caixa "lembrar", a demanda entra nas descartadas."""

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text

from app.task_layer.models import DiscardedProposal, Proposal, Task
from tests.conftest import requires_db

TABELAS = (
    "task_state_history", "execution_runs", "planning_documents", "discarded_proposals",
    "tasks", "proposals",
)


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
def client(limpo, mock_providers):
    from app.main import app

    with TestClient(app) as c:
        yield c


def _tarefa(session, status="suspensa") -> Task:
    proposta = Proposal(origin="internal", raw_text="exportar em PDF", outcome="candidata")
    session.add(proposta)
    session.flush()
    t = Task(
        proposal_id=proposta.id, title="Exportar em PDF", description="Gerar PDF das transações",
        module="transacoes", impact=3, complexity=2, status=status,
    )
    session.add(t)
    session.commit()
    return t


@requires_db
def test_cancelar_registra_o_descarte_por_padrao(client, limpo):
    t = _tarefa(limpo)

    r = client.post(f"/api/tasks/{t.id}/cancel", json={"reason": "não queremos PDF"})

    assert r.status_code == 200 and r.json()["discard_id"]
    d = limpo.get(DiscardedProposal, r.json()["discard_id"])
    assert d.reason_type == "recusa_humana"
    assert d.reason_text == "não queremos PDF"
    assert d.task_id == t.id
    assert d.embedding is not None  # é o que permite a memória barrar o pedido de novo


@requires_db
def test_cancelar_sem_lembrar_nao_cria_descarte(client, limpo):
    t = _tarefa(limpo)

    r = client.post(
        f"/api/tasks/{t.id}/cancel", json={"reason": "vou refazer", "remember": False}
    )

    assert r.status_code == 200 and r.json()["discard_id"] is None
    assert limpo.query(DiscardedProposal).count() == 0
    limpo.expire_all()
    assert limpo.get(Task, t.id).final_outcome == "cancelada"


@requires_db
def test_o_descarte_do_cancelamento_aparece_na_lista_de_descartadas(client, limpo):
    t = _tarefa(limpo)
    client.post(f"/api/tasks/{t.id}/cancel", json={"reason": "fora de escopo"})

    descartes = client.get("/api/discards").json()

    assert any(d["task_id"] == t.id and d["reason_type"] == "recusa_humana" for d in descartes)


@requires_db
def test_recusar_na_homologacao_continua_registrando(client, limpo):
    t = _tarefa(limpo, status="em_homologacao")

    r = client.post(
        f"/api/tasks/{t.id}/homologation", json={"decision": "recusar", "comment": "não serve"}
    )

    assert r.status_code == 200
    assert limpo.query(DiscardedProposal).filter_by(task_id=t.id).count() == 1
