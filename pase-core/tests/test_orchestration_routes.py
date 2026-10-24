"""Endpoints da Orquestração e os gates humanos (SPEC-04 §3 e §5)."""

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text

from app.orchestration import states
from app.orchestration.models import PlanningDocument
from app.task_layer.models import DiscardedProposal, ImplementedItem, Task
from tests.conftest import requires_db


def _zerar(session):
    for tabela in (
        "task_state_history",
        "execution_runs",
        "planning_documents",
        "incidents",
        "discarded_proposals",
        "tasks",
        "implemented_items",
    ):
        session.execute(text(f"DELETE FROM {tabela}"))
    session.commit()


@pytest.fixture
def client(session):
    from app.main import app

    _zerar(session)
    with TestClient(app) as test_client:
        yield test_client
    _zerar(session)


def _nova_task(session, **campos) -> Task:
    padrao = {
        "title": "Tarefa",
        "description": "descrição",
        "module": "transacoes",
        "impact": 3,
        "complexity": 2,
        "confidence": 0.8,
        "risk_tier": "medio",
        "status": "candidata",
    }
    task = Task(**{**padrao, **campos})
    session.add(task)
    session.commit()
    session.refresh(task)
    return task


# --------------------------------------------------------------------------- #
# Priorização e urgência
# --------------------------------------------------------------------------- #


@requires_db
def test_listagem_ordena_por_impacto_menos_complexidade(client, session):
    _nova_task(session, title="Pouco impacto", impact=2, complexity=1)  # score 1
    _nova_task(session, title="Muito impacto", impact=5, complexity=1)  # score 4
    _nova_task(session, title="Cara e fraca", impact=2, complexity=4)  # score -2

    corpo = client.get("/api/tasks", params={"status": "candidata"}).json()

    assert [t["title"] for t in corpo] == ["Muito impacto", "Pouco impacto", "Cara e fraca"]
    assert corpo[0]["priority_score"] == 4


@requires_db
def test_incidente_alto_eleva_a_urgencia_do_modulo(client, session):
    baixa = _nova_task(session, title="De transações", impact=2, complexity=1, module="transacoes")
    _nova_task(session, title="De relatórios", impact=3, complexity=1, module="relatorios")

    antes = [t["title"] for t in client.get("/api/tasks", params={"status": "candidata"}).json()]
    assert antes[0] == "De relatórios"

    resposta = client.post(
        "/api/incidents",
        json={
            "title": "Erro ao salvar transação",
            "description": "500 intermitente",
            "severity": "alto",
            "module": "transacoes",
        },
    )

    assert resposta.status_code == 201
    assert resposta.json()["urgency_applied"] == 3.0
    assert baixa.id in resposta.json()["tasks_affected"]

    depois = client.get("/api/tasks", params={"status": "candidata"}).json()
    assert depois[0]["title"] == "De transações"  # subiu de posição
    assert depois[0]["urgency_score"] == 3.0


@requires_db
def test_incidente_medio_soma_menos_que_alto(client, session):
    _nova_task(session, module="relatorios")

    client.post(
        "/api/incidents",
        json={"title": "Lentidão", "severity": "medio", "module": "relatorios"},
    )

    corpo = client.get("/api/tasks").json()
    assert corpo[0]["urgency_score"] == 1.0


# --------------------------------------------------------------------------- #
# Gates
# --------------------------------------------------------------------------- #


@requires_db
def test_recusa_na_triagem_entra_na_memoria(client, session):
    task = _nova_task(session)

    resposta = client.post(
        f"/api/tasks/{task.id}/reject", json={"reason": "não é prioridade neste trimestre"}
    )

    assert resposta.status_code == 200
    assert resposta.json()["final_outcome"] == "recusada"

    session.expire_all()
    assert session.get(Task, task.id).status == states.FINALIZADA

    descarte = session.query(DiscardedProposal).filter_by(task_id=task.id).one()
    assert descarte.reason_type == "recusa_humana"
    assert descarte.embedding is not None  # recusa humana entra na memória


@requires_db
def test_aprovar_tarefa_que_nao_esta_candidata_da_conflito(client, session):
    task = _nova_task(session, status="em_execucao")

    resposta = client.post(f"/api/tasks/{task.id}/approve")

    assert resposta.status_code == 409


@requires_db
def test_homologar_fora_de_homologacao_da_conflito(client, session):
    task = _nova_task(session)

    resposta = client.post(
        f"/api/tasks/{task.id}/homologation", json={"decision": "aprovar", "comment": None}
    )

    assert resposta.status_code == 409


@requires_db
def test_risco_alto_exige_justificativa_mesmo_para_aprovar(client, session):
    """SPEC-04 §5: risco alto pede mais atenção humana, por escrito."""
    task = _nova_task(session, status="em_homologacao", risk_tier="alto", branch_name="pase/task-1")

    sem_comentario = client.post(
        f"/api/tasks/{task.id}/homologation", json={"decision": "aprovar"}
    )

    assert sem_comentario.status_code == 422
    assert "risco alto" in sem_comentario.json()["detail"]


@requires_db
def test_ajustar_exige_comentario(client, session):
    task = _nova_task(session, status="em_homologacao")

    resposta = client.post(f"/api/tasks/{task.id}/homologation", json={"decision": "ajustar"})

    assert resposta.status_code == 409
    assert "exige um comentário" in resposta.json()["detail"]


@requires_db
def test_recusar_na_homologacao_registra_descarte_com_embedding(client, session):
    task = _nova_task(session, status="em_homologacao")

    resposta = client.post(
        f"/api/tasks/{task.id}/homologation",
        json={"decision": "recusar", "comment": "a solução não resolve o problema relatado"},
    )

    assert resposta.status_code == 200
    descarte = session.query(DiscardedProposal).filter_by(task_id=task.id).one()
    assert descarte.reason_type == "recusa_humana"
    assert descarte.embedding is not None

    session.expire_all()
    task_final = session.get(Task, task.id)
    assert (task_final.status, task_final.final_outcome) == (states.FINALIZADA, "recusada")
    assert session.query(ImplementedItem).count() == 0  # recusa não vira implementada


@requires_db
def test_retomar_so_vale_para_suspensa(client, session):
    task = _nova_task(session, status="em_homologacao")

    assert client.post(f"/api/tasks/{task.id}/resume").status_code == 409


@requires_db
def test_teto_manual_pode_ser_definido_e_removido(client, session):
    task = _nova_task(session, status=states.SUSPENSA)

    definido = client.patch(
        f"/api/tasks/{task.id}", json={"budget_cap_tokens": 250_000}
    )
    assert definido.status_code == 200
    session.expire_all()
    assert session.get(Task, task.id).budget_cap_tokens == 250_000
    assert client.get(f"/api/tasks/{task.id}").json()["orcamento"]["manual"] is True

    removido = client.patch(f"/api/tasks/{task.id}", json={"budget_cap_tokens": 0})
    assert removido.status_code == 200
    session.expire_all()
    assert session.get(Task, task.id).budget_cap_tokens is None
    assert client.get(f"/api/tasks/{task.id}").json()["orcamento"]["manual"] is False


@requires_db
def test_replanejar_tarefa_suspensa_volta_ao_planejamento(
    client, session, monkeypatch
):
    from app.orchestration import chain

    chamadas = []
    monkeypatch.setattr(chain, "rodar_replanejamento", chamadas.append)
    task = _nova_task(session, status=states.SUSPENSA, alert="budget")

    resposta = client.post(f"/api/tasks/{task.id}/replan")

    assert resposta.status_code == 200
    session.expire_all()
    atual = session.get(Task, task.id)
    assert (atual.status, atual.alert) == (states.EM_PLANEJAMENTO, "none")
    assert chamadas == [task.id]


@requires_db
def test_replanejar_candidata_nao_fura_o_gate_humano(client, session):
    task = _nova_task(session, status=states.CANDIDATA)

    resposta = client.post(f"/api/tasks/{task.id}/replan")

    assert resposta.status_code == 409
    session.expire_all()
    assert session.get(Task, task.id).status == states.CANDIDATA


@requires_db
@pytest.mark.parametrize(
    "estado",
    [states.EM_PLANEJAMENTO, states.PRONTA_PARA_DESPACHO, states.EM_EXECUCAO],
)
def test_cancelar_finaliza_em_qualquer_fase_ativa(client, session, estado):
    task = _nova_task(session, status=estado)

    resposta = client.post(
        f"/api/tasks/{task.id}/cancel", json={"reason": "não faz mais sentido"}
    )

    assert resposta.status_code == 200
    assert resposta.json()["final_outcome"] == "cancelada"
    assert resposta.json()["cooperativo"] is (estado == states.EM_EXECUCAO)
    session.expire_all()
    atual = session.get(Task, task.id)
    assert (atual.status, atual.final_outcome) == (states.FINALIZADA, "cancelada")


# --------------------------------------------------------------------------- #
# Instrumentos de demo e detalhe
# --------------------------------------------------------------------------- #


@requires_db
def test_patch_demo_grava_os_instrumentos(client, session):
    task = _nova_task(session)

    resposta = client.patch(
        f"/api/tasks/{task.id}/demo", json={"force_fail_runs": 2, "budget_cap_tokens": 100}
    )

    assert resposta.status_code == 200
    assert resposta.json() == {
        "task_id": task.id,
        "demo_force_fail_runs": 2,
        "demo_budget_cap_tokens": 100,
    }


@requires_db
def test_patch_demo_bloqueado_com_demo_mode_desligado(client, session, monkeypatch):
    from app.orchestration import routes

    monkeypatch.setattr(routes.settings, "demo_mode", False)
    task = _nova_task(session)

    assert client.patch(f"/api/tasks/{task.id}/demo", json={"force_fail_runs": 1}).status_code == 403


@requires_db
def test_detalhe_agrega_historico_plano_e_runs(client, session):
    task = _nova_task(session)
    session.add(
        PlanningDocument(
            task_id=task.id,
            affected_files=["client-backend/app/routes.py"],
            roadmap="mudar a rota",
            tokens_estimated=1234,
        )
    )
    states.transicionar(session, task, states.EM_PLANEJAMENTO, note="aprovada")
    session.commit()

    corpo = client.get(f"/api/tasks/{task.id}").json()

    assert corpo["task"]["status"] == states.EM_PLANEJAMENTO
    assert corpo["planning"]["tokens_estimated"] == 1234
    assert corpo["planning"]["affected_files"] == ["client-backend/app/routes.py"]
    assert corpo["history"][-1]["to"] == states.EM_PLANEJAMENTO
    assert corpo["runs"] == []


@requires_db
def test_artefato_inexistente_devolve_404(client, session):
    assert client.get("/api/runs/999/artifact/diff").status_code == 404


@requires_db
def test_editar_estimativas_recalcula_o_marcador_de_incerteza(client, session):
    """§4.4.1: o marcador é regra fixa, recalculada também na edição humana."""
    task = _nova_task(session, impact=3, complexity=2, confidence=0.8, uncertainty=False)

    # pouco valor para muito esforço
    r = client.patch(f"/api/tasks/{task.id}", json={"impact": 1, "complexity": 5})
    assert r.status_code == 200
    assert any("incerteza" in a for a in r.json()["alterado"])
    session.expire_all()
    assert session.get(Task, task.id).uncertainty is True

    # a conta volta a fechar
    client.patch(f"/api/tasks/{task.id}", json={"impact": 4, "complexity": 2})
    session.expire_all()
    assert session.get(Task, task.id).uncertainty is False

    # o próprio modelo duvidaria das estimativas
    client.patch(f"/api/tasks/{task.id}", json={"confidence": 0.3})
    session.expire_all()
    assert session.get(Task, task.id).uncertainty is True

    client.patch(f"/api/tasks/{task.id}", json={"confidence": 0.9})
    session.expire_all()
    assert session.get(Task, task.id).uncertainty is False


@requires_db
def test_editar_campo_sem_relacao_nao_mexe_na_incerteza(client, session):
    task = _nova_task(session, impact=1, complexity=5, confidence=0.8, uncertainty=False)

    client.patch(f"/api/tasks/{task.id}", json={"title": "Outro título"})

    session.expire_all()
    assert session.get(Task, task.id).uncertainty is False
