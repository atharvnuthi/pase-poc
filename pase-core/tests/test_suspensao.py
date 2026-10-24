"""Suspensão em cascata e retentativa do planejamento (monografia §4.4.3).

"A tarefa é suspensa, junto com o ramo do grafo que depende dela, e o problema é
reportado a uma pessoa."
"""

import time

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text

from app.common.config import settings
from app.execution import planning
from app.orchestration import chain, dependencies, states, suspensao
from app.orchestration.models import DEP_MANUAL, DEP_SEMANTICA, PlanningDocument
from app.task_layer.models import Task, TaskStateHistory
from tests.conftest import requires_db

TABELAS = (
    "task_dependencies",
    "task_state_history",
    "execution_runs",
    "planning_documents",
    "discarded_proposals",
    "tasks",
    "proposals",
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
def execucoes(monkeypatch):
    """O Executor de verdade fica de fora: aqui só interessa quem foi mandado rodar."""
    chamadas = []
    monkeypatch.setattr(chain, "rodar_execucao", lambda tid, **kw: chamadas.append(tid))
    monkeypatch.setattr(chain, "rodar_replanejamento", lambda tid: chamadas.append(("replan", tid)))
    return chamadas


@pytest.fixture
def client(limpo, execucoes):
    from app.main import app

    with TestClient(app) as c:
        yield c


def _tarefa(session, status, *, arquivos=("a.py",), **campos) -> Task:
    t = Task(
        title=f"Tarefa {status}", description="d", module="geral", impact=3, complexity=1,
        status=status, **campos,
    )
    session.add(t)
    session.flush()
    session.add(
        PlanningDocument(
            task_id=t.id, acceptance_criteria=[{"id": "C1", "criterio": "x"}],
            affected_files=list(arquivos), roadmap="r", tokens_estimated=1000,
        )
    )
    session.commit()
    return t


def _ramo(session):
    """A executando; B espera A; C espera B; D só parece com A; E ainda planeja."""
    a = _tarefa(session, states.EM_EXECUCAO, arquivos=["a.py"])
    b = _tarefa(session, states.PRONTA_PARA_DESPACHO, arquivos=["b.py"])
    c = _tarefa(session, states.AGUARDANDO_PLANO, arquivos=["c.py"])
    d = _tarefa(session, states.PRONTA_PARA_DESPACHO, arquivos=["d.py"])
    e = _tarefa(session, states.EM_PLANEJAMENTO, arquivos=["e.py"])
    dependencies.ligar(session, b.id, a.id, kind=DEP_MANUAL)
    dependencies.ligar(session, c.id, b.id, kind=DEP_MANUAL)
    dependencies.ligar(session, d.id, a.id, kind=DEP_SEMANTICA)
    dependencies.ligar(session, e.id, a.id, kind=DEP_MANUAL)
    session.commit()
    return a, b, c, d, e


def _estado(session, task):
    session.expire_all()
    t = session.get(Task, task.id)
    return t.status, t.alert


def _notas(session, task) -> list[str]:
    return [
        h.note or ""
        for h in session.query(TaskStateHistory)
        .filter(TaskStateHistory.task_id == task.id)
        .order_by(TaskStateHistory.id)
    ]


@requires_db
def test_falha_esgotada_suspende_o_ramo_que_depende(limpo, monkeypatch):
    monkeypatch.setattr(settings, "max_retries", 1)
    a, b, c, d, e = _ramo(limpo)

    chain._apos_a_run(a.id, "falha", [], tentativa=2)

    assert _estado(limpo, a) == (states.SUSPENSA, "retries")
    assert _estado(limpo, b) == (states.SUSPENSA, suspensao.ALERTA)
    # transitivo: C espera B, que espera A
    assert _estado(limpo, c) == (states.SUSPENSA, suspensao.ALERTA)
    assert f"predecessora #{a.id} suspensa" in _notas(limpo, b)
    assert f"predecessora #{b.id} suspensa" in _notas(limpo, c)
    # aresta semântica não segura nem arrasta ninguém
    assert _estado(limpo, d)[0] == states.PRONTA_PARA_DESPACHO
    # quem já está trabalhando não é interrompido pela regra
    assert _estado(limpo, e)[0] == states.EM_PLANEJAMENTO


@requires_db
def test_budget_tambem_suspende_em_cascata(limpo):
    a, b, *_ = _ramo(limpo)

    chain._apos_a_run(a.id, "interrompida_budget", [], tentativa=1)

    assert _estado(limpo, a) == (states.SUSPENSA, "budget")
    assert _estado(limpo, b) == (states.SUSPENSA, suspensao.ALERTA)


@requires_db
def test_retomar_a_predecessora_devolve_o_ramo_ao_que_era(client, limpo, monkeypatch):
    monkeypatch.setattr(settings, "max_retries", 0)
    a, b, c, *_ = _ramo(limpo)
    chain._apos_a_run(a.id, "falha", [], tentativa=1)

    r = client.post(f"/api/tasks/{a.id}/resume")

    assert r.status_code == 200
    assert _estado(limpo, b) == (states.PRONTA_PARA_DESPACHO, "none")
    assert _estado(limpo, c) == (states.AGUARDANDO_PLANO, "none")
    assert f"predecessora #{a.id} retomada" in _notas(limpo, b)


@requires_db
def test_replanejar_a_predecessora_tambem_devolve_o_ramo(client, limpo):
    a, b, c, *_ = _ramo(limpo)
    chain._apos_a_run(a.id, "interrompida_budget", [], tentativa=1)

    assert client.post(f"/api/tasks/{a.id}/replan").status_code == 200

    assert _estado(limpo, b)[0] == states.PRONTA_PARA_DESPACHO
    assert _estado(limpo, c)[0] == states.AGUARDANDO_PLANO


@requires_db
def test_retomar_quem_foi_suspensa_em_cascata_e_recusado(client, limpo):
    """Executaria antes da predecessora e, se esperava o plano, pularia o gate."""
    a, b, *_ = _ramo(limpo)
    chain._apos_a_run(a.id, "interrompida_budget", [], tentativa=1)

    r = client.post(f"/api/tasks/{b.id}/resume")

    assert r.status_code == 409
    assert f"#{a.id}" in r.json()["detail"]


@requires_db
def test_cancelar_a_predecessora_solta_a_dependencia_e_despacha(client, limpo, execucoes):
    a, b, c, *_ = _ramo(limpo)
    chain._apos_a_run(a.id, "interrompida_budget", [], tentativa=1)

    r = client.post(f"/api/tasks/{a.id}/cancel", json={"reason": "não vale mais", "remember": False})

    assert r.status_code == 200
    assert [e.depends_on_task_id for e in dependencies.arestas_de(limpo, b.id)] == []
    # B não espera mais ninguém: foi despachada e mandada executar numa thread
    assert _estado(limpo, b) == (states.EM_EXECUCAO, "none")
    for _ in range(50):
        if b.id in execucoes:
            break
        time.sleep(0.05)
    assert b.id in execucoes
    # C continua esperando B, agora no estado em que estava
    assert _estado(limpo, c)[0] == states.AGUARDANDO_PLANO


@requires_db
def test_outra_predecessora_suspensa_mantem_a_suspensao(client, limpo):
    """B espera A e X. A volta, X não: B continua suspensa, agora por X."""
    a, b, *_ = _ramo(limpo)
    x = _tarefa(limpo, states.SUSPENSA, arquivos=["x.py"], alert="retries")
    dependencies.ligar(limpo, b.id, x.id, kind=DEP_MANUAL)
    limpo.commit()
    chain._apos_a_run(a.id, "interrompida_budget", [], tentativa=1)

    assert client.post(f"/api/tasks/{a.id}/resume").status_code == 200

    assert _estado(limpo, b) == (states.SUSPENSA, suspensao.ALERTA)
    assert suspensao.suspensa_por(limpo, limpo.get(Task, b.id)) == x.id

    assert client.post(f"/api/tasks/{x.id}/resume").status_code == 200
    assert _estado(limpo, b) == (states.PRONTA_PARA_DESPACHO, "none")


@requires_db
def test_quem_chega_ao_despacho_com_a_predecessora_suspensa_e_suspensa_junto(limpo):
    """Estava planejando quando A foi suspensa; chega ao despacho depois."""
    a = _tarefa(limpo, states.SUSPENSA, arquivos=["a.py"], alert="retries")
    b = _tarefa(limpo, states.PRONTA_PARA_DESPACHO, arquivos=["b.py"])
    dependencies.ligar(limpo, b.id, a.id, kind=DEP_MANUAL)
    limpo.commit()

    assert chain.tentar_despacho(b.id) is False
    assert _estado(limpo, b) == (states.SUSPENSA, suspensao.ALERTA)


# --------------------------------------------------------------------------- #
# Falha no planejamento: mesma política da execução
# --------------------------------------------------------------------------- #


def _planejar_que_falha(vezes: int, chamadas: list):
    def planejar(session, task, historico=""):
        chamadas.append(task.id)
        if len(chamadas) <= vezes:
            raise RuntimeError("o modelo devolveu JSON inválido")
        doc = PlanningDocument(
            task_id=task.id, acceptance_criteria=[{"id": "C1", "criterio": "x"}],
            affected_files=["p.py"], roadmap="r", tokens_estimated=1,
        )
        session.add(doc)
        session.flush()
        return doc

    return planejar


@requires_db
def test_planejamento_que_falha_uma_vez_e_refeito(limpo, monkeypatch, execucoes):
    monkeypatch.setattr(settings, "max_retries", 1)
    chamadas = []
    monkeypatch.setattr(planning, "planejar", _planejar_que_falha(1, chamadas))
    t = Task(
        title="t", description="d", module="geral", impact=3, complexity=1,
        status=states.EM_PLANEJAMENTO,
    )
    limpo.add(t)
    limpo.commit()

    chain._planejar_e_despachar(t.id, ja_em_planejamento=True)

    assert len(chamadas) == 2
    assert _estado(limpo, t)[0] == states.EM_EXECUCAO
    assert execucoes == [t.id]
    assert any("refazendo" in n for n in _notas(limpo, t))


@requires_db
def test_planejamento_que_falha_sempre_suspende_com_o_ramo(limpo, monkeypatch, execucoes):
    monkeypatch.setattr(settings, "max_retries", 1)
    chamadas = []
    monkeypatch.setattr(planning, "planejar", _planejar_que_falha(99, chamadas))
    a = Task(
        title="a", description="d", module="geral", impact=3, complexity=1,
        status=states.EM_PLANEJAMENTO,
    )
    limpo.add(a)
    limpo.commit()
    b = _tarefa(limpo, states.PRONTA_PARA_DESPACHO, arquivos=["b.py"])
    dependencies.ligar(limpo, b.id, a.id, kind=DEP_MANUAL)
    limpo.commit()

    chain._planejar_e_despachar(a.id, ja_em_planejamento=True)

    assert len(chamadas) == 2  # uma tentativa e uma retentativa
    assert _estado(limpo, a) == (states.SUSPENSA, "retries")
    assert any("após 2 tentativa(s)" in n for n in _notas(limpo, a))
    assert _estado(limpo, b) == (states.SUSPENSA, suspensao.ALERTA)
    assert execucoes == []


@requires_db
def test_plano_sem_criterios_suspende_sem_retentar(limpo, monkeypatch):
    monkeypatch.setattr(settings, "max_retries", 3)
    chamadas = []
    monkeypatch.setattr(chain, "rodar_execucao", lambda *a, **k: chamadas.append(a))
    a, *_ = _ramo(limpo)

    chain._apos_a_run(a.id, "falha", [], tentativa=1, sem_criterios=True)

    assert chamadas == []
    assert _estado(limpo, a) == (states.SUSPENSA, "retries")
    assert "plano sem critérios de aceite" in _notas(limpo, a)
