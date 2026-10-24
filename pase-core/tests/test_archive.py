"""Arquivar tarefa: some das listas, nada é apagado."""

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text

from app.orchestration.models import ExecutionRun
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
def client(limpo):
    from app.main import app

    with TestClient(app) as c:
        yield c


def _task(session, **campos) -> Task:
    padrao = {
        "title": "Exportar CSV", "description": "d", "module": "transacoes", "impact": 3,
        "complexity": 1, "status": "finalizada", "final_outcome": "aprovada",
    }
    t = Task(**{**padrao, **campos})
    session.add(t)
    session.commit()
    return t


def _ids(client, **params) -> list[int]:
    return [t["id"] for t in client.get("/api/tasks", params=params).json()]


@requires_db
def test_arquivada_sai_da_lista_e_aparece_no_arquivo(client, limpo):
    t = _task(limpo)

    assert client.post(f"/api/tasks/{t.id}/archive", json={"reason": "limpeza"}).status_code == 200

    assert t.id not in _ids(client)
    assert t.id in _ids(client, archived="true")


@requires_db
def test_nada_e_apagado_ao_arquivar(client, limpo):
    t = _task(limpo)
    limpo.add(ExecutionRun(task_id=t.id, attempt=1, trigger="inicial", status="sucesso"))
    limpo.commit()

    client.post(f"/api/tasks/{t.id}/archive", json={"reason": "limpeza"})

    detalhe = client.get(f"/api/tasks/{t.id}").json()
    assert len(detalhe["runs"]) == 1  # a execução continua
    assert detalhe["archive_note"] == "limpeza"
    assert any("arquivada: limpeza" in (h["note"] or "") for h in detalhe["history"])


@requires_db
def test_desarquivar_devolve_a_tarefa_as_listas(client, limpo):
    t = _task(limpo)
    client.post(f"/api/tasks/{t.id}/archive")

    assert client.post(f"/api/tasks/{t.id}/unarchive").status_code == 200

    assert t.id in _ids(client)
    assert t.id not in _ids(client, archived="true")


@requires_db
@pytest.mark.parametrize("status", ["candidata", "em_execucao", "em_homologacao", "suspensa"])
def test_so_se_arquiva_o_que_esta_finalizado(client, limpo, status):
    t = _task(limpo, status=status, final_outcome=None)

    r = client.post(f"/api/tasks/{t.id}/archive")

    assert r.status_code == 409
    assert "finalizada" in r.json()["detail"]


@requires_db
@pytest.mark.parametrize("stage", ["develop", "release"])
def test_tarefa_ainda_no_fluxo_de_entrega_nao_se_arquiva(client, limpo, stage):
    t = _task(limpo, stage=stage)

    r = client.post(f"/api/tasks/{t.id}/archive")

    assert r.status_code == 409


@requires_db
def test_em_producao_pode_ser_arquivada(client, limpo):
    t = _task(limpo, stage="producao")
    assert client.post(f"/api/tasks/{t.id}/archive").status_code == 200


@requires_db
def test_arquivar_duas_vezes_e_desarquivar_o_que_nao_esta_arquivado(client, limpo):
    t = _task(limpo)
    client.post(f"/api/tasks/{t.id}/archive")

    assert client.post(f"/api/tasks/{t.id}/archive").status_code == 409
    client.post(f"/api/tasks/{t.id}/unarchive")
    assert client.post(f"/api/tasks/{t.id}/unarchive").status_code == 409


@requires_db
def test_arquivada_sai_do_grafo_mas_continua_nas_metricas(client, limpo):
    t = _task(limpo)
    client.post(f"/api/tasks/{t.id}/archive")

    assert t.id not in [n["id"] for n in client.get("/api/graph").json()["nodes"]]
    # o log: as métricas leem a tabela inteira
    assert limpo.query(Task).filter_by(id=t.id).count() == 1
