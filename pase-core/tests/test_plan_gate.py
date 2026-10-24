"""Aprovação do plano: o gate entre planejar e gastar uma execução."""

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text

from app.execution import planning
from app.orchestration import chain, redo, states
from app.orchestration.models import PlanningDocument
from app.task_layer.models import Task
from tests.conftest import requires_db

TABELAS = ("task_state_history", "execution_runs", "planning_documents", "tasks", "proposals")


def _zerar(session):
    for tabela in TABELAS:
        session.execute(text(f"DELETE FROM {tabela}"))
    session.commit()


@pytest.fixture
def limpo(session):
    _zerar(session)
    yield session
    _zerar(session)


@pytest.fixture
def client(limpo, monkeypatch):
    from app.main import app

    # as cadeias de fundo rodam o Executor de verdade: aqui só interessa quem é chamado
    chamadas = []
    monkeypatch.setattr(chain, "rodar_cadeia", lambda tid: chamadas.append(("cadeia", tid)))
    monkeypatch.setattr(
        chain, "rodar_replanejamento", lambda tid: chamadas.append(("replan", tid))
    )
    monkeypatch.setattr(
        chain, "rodar_apos_aprovacao_do_plano", lambda tid: chamadas.append(("plano", tid))
    )
    with TestClient(app) as c:
        c.chamadas = chamadas
        yield c


def _task(session, **campos) -> Task:
    padrao = {
        "title": "Exportar CSV", "description": "d", "module": "transacoes", "impact": 3,
        "complexity": 2, "risk_tier": "baixo", "status": "candidata",
    }
    t = Task(**{**padrao, **campos})
    session.add(t)
    session.commit()
    return t


def _com_plano(session, task):
    session.add(
        PlanningDocument(
            task_id=task.id,
            acceptance_criteria=[{"id": "C1", "criterio": "O botão aparece", "como_verificar": "t"}],
            affected_files=["client-frontend/app/transacoes/page.tsx"],
            roadmap="Acrescentar o botão.",
            tokens_estimated=1000,
        )
    )
    session.commit()


@requires_db
@pytest.mark.parametrize(
    "risco, pedido, esperado",
    [
        ("baixo", None, False),
        ("medio", None, True),
        ("alto", None, True),
        ("baixo", True, True),  # a pessoa quer ver o plano mesmo sendo baixo risco
        ("alto", False, False),  # e pode dispensar mesmo sendo alto
    ],
)
def test_aprovar_candidata_decide_se_o_plano_para(client, limpo, risco, pedido, esperado):
    task = _task(limpo, risk_tier=risco)

    corpo = {"review_plan": pedido} if pedido is not None else None
    r = client.post(f"/api/tasks/{task.id}/approve", json=corpo)

    assert r.status_code == 200
    assert r.json()["plan_approval_required"] is esperado
    limpo.refresh(task)
    assert task.plan_approval_required is esperado


@requires_db
def test_aprovar_sem_corpo_continua_funcionando(client, limpo):
    task = _task(limpo)
    assert client.post(f"/api/tasks/{task.id}/approve").status_code == 200


@requires_db
def test_planejamento_para_antes_de_despachar_quando_exige_aprovacao(limpo, monkeypatch):
    task = _task(limpo, status="aprovada_fake")
    task.status = states.EM_PLANEJAMENTO
    task.plan_approval_required = True
    limpo.commit()

    def planejar_falso(session, t, historico=""):
        doc = PlanningDocument(
            task_id=t.id, acceptance_criteria=[{"id": "C1", "criterio": "x"}],
            affected_files=["a.py"], roadmap="r", tokens_estimated=1,
        )
        session.add(doc)
        session.flush()
        return doc

    monkeypatch.setattr(planning, "planejar", planejar_falso)
    executou = []
    monkeypatch.setattr(chain, "rodar_execucao", lambda *a, **k: executou.append(1))

    chain._planejar_e_despachar(task.id, ja_em_planejamento=True)

    limpo.expire_all()
    assert limpo.get(Task, task.id).status == states.AGUARDANDO_PLANO
    assert executou == []  # nenhum token de execução foi gasto


@requires_db
def test_sem_exigencia_o_plano_segue_direto(limpo, monkeypatch):
    task = _task(limpo)
    task.status = states.EM_PLANEJAMENTO
    limpo.commit()

    def planejar_falso(session, t, historico=""):
        doc = PlanningDocument(
            task_id=t.id, acceptance_criteria=[], affected_files=["a.py"],
            roadmap="r", tokens_estimated=1,
        )
        session.add(doc)
        session.flush()
        return doc

    monkeypatch.setattr(planning, "planejar", planejar_falso)
    executou = []
    monkeypatch.setattr(chain, "rodar_execucao", lambda *a, **k: executou.append(1))

    chain._planejar_e_despachar(task.id, ja_em_planejamento=True)

    assert executou == [1]


@requires_db
def test_aprovar_plano_libera_a_execucao(client, limpo):
    task = _task(limpo, status=states.AGUARDANDO_PLANO, plan_approval_required=True)
    _com_plano(limpo, task)

    r = client.post(f"/api/tasks/{task.id}/plan/approve", json={"comment": "ok, pode ir"})

    assert r.status_code == 200
    assert ("plano", task.id) in client.chamadas
    limpo.refresh(task)
    assert task.status == states.PRONTA_PARA_DESPACHO
    assert task.plan_approved is True


@requires_db
def test_devolver_plano_leva_o_feedback_ao_proximo_planejamento(client, limpo):
    task = _task(limpo, status=states.AGUARDANDO_PLANO, plan_approval_required=True)
    _com_plano(limpo, task)

    r = client.post(
        f"/api/tasks/{task.id}/plan/revise",
        json={"feedback": "o backend já tem o endpoint, só falta a tela"},
    )

    assert r.status_code == 200
    assert ("replan", task.id) in client.chamadas
    limpo.refresh(task)
    assert task.status == states.EM_PLANEJAMENTO
    texto = redo.historico_de(limpo, task)
    assert "o backend já tem o endpoint, só falta a tela" in texto
    assert "Acrescentar o botão." in texto  # o plano devolvido também vai


@requires_db
def test_editar_plano_valida_e_registra(client, limpo):
    task = _task(limpo, status=states.AGUARDANDO_PLANO)
    _com_plano(limpo, task)

    r = client.patch(
        f"/api/tasks/{task.id}/plan",
        json={
            "affected_files": ["client-frontend/app/transacoes/page.tsx", "  "],
            "acceptance_criteria": [{"criterio": "Aparece com a lista vazia"}],
        },
    )

    assert r.status_code == 200
    detalhe = client.get(f"/api/tasks/{task.id}").json()
    assert detalhe["planning"]["affected_files"] == ["client-frontend/app/transacoes/page.tsx"]
    assert detalhe["planning"]["acceptance_criteria"][0]["id"] == "C1"
    assert any("plano editado" in (h["note"] or "") for h in detalhe["history"])


@requires_db
def test_plano_sem_criterios_e_recusado(client, limpo):
    task = _task(limpo, status=states.AGUARDANDO_PLANO)
    _com_plano(limpo, task)

    r = client.patch(f"/api/tasks/{task.id}/plan", json={"acceptance_criteria": [{"criterio": " "}]})

    assert r.status_code == 422


@requires_db
@pytest.mark.parametrize("rota", ["plan/approve", "plan/revise"])
def test_so_vale_em_aguardando_plano(client, limpo, rota):
    task = _task(limpo, status=states.EM_EXECUCAO)
    corpo = {"feedback": "x"} if rota.endswith("revise") else None

    assert client.post(f"/api/tasks/{task.id}/{rota}", json=corpo).status_code == 409
