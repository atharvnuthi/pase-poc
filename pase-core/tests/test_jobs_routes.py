"""Auditoria e Reavaliação por acionamento humano (monografia §4.3.5 e §4.4.6)."""

import pytest
from fastapi.testclient import TestClient

from app.jobs import audit, reevaluation
from app.jobs import routes as jobs_routes
from tests.conftest import requires_db


@pytest.fixture
def client(monkeypatch):
    from app.main import app

    monkeypatch.setattr(jobs_routes, "_estado", {})
    with TestClient(app) as c:
        yield c


@requires_db
def test_auditoria_roda_em_segundo_plano_e_guarda_o_resultado(client, monkeypatch):
    monkeypatch.setattr(
        audit,
        "executar",
        lambda: {"propostas_geradas": 1, "proposta_id": 7, "resumo": "proposta #7 gerada"},
    )

    r = client.post("/api/jobs/auditoria")

    assert r.status_code == 202
    assert r.json()["status"] == "iniciado"
    # o TestClient roda as tarefas de fundo antes de devolver a resposta
    estado = client.get("/api/jobs").json()["auditoria"]
    assert estado["rodando"] is False
    assert estado["resultado"]["propostas_geradas"] == 1
    assert estado["erro"] is None
    assert estado["terminado_em"] is not None


@requires_db
def test_reavaliacao_devolve_quantas_voltaram_ao_funil(client, monkeypatch):
    monkeypatch.setattr(
        reevaluation,
        "executar",
        lambda: {"analisados": 3, "reinseridas": 2, "propostas": [], "resumo": "..."},
    )

    assert client.post("/api/jobs/reavaliacao").status_code == 202

    resultado = client.get("/api/jobs").json()["reavaliacao"]["resultado"]
    assert (resultado["analisados"], resultado["reinseridas"]) == (3, 2)


@requires_db
def test_segunda_rodada_simultanea_e_recusada(client, monkeypatch):
    rodou = []
    monkeypatch.setattr(reevaluation, "executar", lambda: rodou.append(1) or {})
    jobs_routes._estado["reavaliacao"] = {
        **jobs_routes._vazio("reavaliacao"),
        "rodando": True,
        "iniciado_em": jobs_routes.utcnow(),
    }

    r = client.post("/api/jobs/reavaliacao")

    assert r.status_code == 409
    assert "já está rodando" in r.json()["detail"]
    assert rodou == []
    # o outro job não é afetado
    monkeypatch.setattr(audit, "executar", lambda: {"propostas_geradas": 0})
    assert client.post("/api/jobs/auditoria").status_code == 202


@requires_db
def test_falha_do_job_fica_registrada_e_libera_nova_rodada(client, monkeypatch):
    def quebra():
        raise RuntimeError("provider fora do ar")

    monkeypatch.setattr(audit, "executar", quebra)

    assert client.post("/api/jobs/auditoria").status_code == 202

    estado = client.get("/api/jobs").json()["auditoria"]
    assert estado["rodando"] is False
    assert "provider fora do ar" in estado["erro"]
    assert client.post("/api/jobs/auditoria").status_code == 202


def test_linha_de_comando_continua_devolvendo_contagem(monkeypatch):
    monkeypatch.setattr(reevaluation, "executar", lambda: {"reinseridas": 4})
    monkeypatch.setattr(audit, "executar", lambda: {"propostas_geradas": 1})

    assert reevaluation.run() == 4
    assert audit.run() == 1
