"""Máquina de estados da tarefa (SPEC-04 §1)."""

import pytest
from sqlalchemy import text

from app.orchestration import states
from app.task_layer.models import Task, TaskStateHistory
from tests.conftest import requires_db


@pytest.fixture
def task(session):
    def zerar():
        for tabela in ("task_state_history", "execution_runs", "planning_documents", "tasks"):
            session.execute(text(f"DELETE FROM {tabela}"))
        session.commit()

    zerar()
    nova = Task(
        title="Tarefa de teste",
        description="x",
        module="transacoes",
        impact=4,
        complexity=2,
        confidence=0.8,
        risk_tier="medio",
        status="candidata",
    )
    session.add(nova)
    session.commit()
    yield nova
    zerar()


@requires_db
def test_caminho_feliz_completo(session, task):
    caminho = [
        states.EM_PLANEJAMENTO,
        states.PRONTA_PARA_DESPACHO,
        states.EM_EXECUCAO,
        states.EM_HOMOLOGACAO,
        states.FINALIZADA,
    ]
    for destino in caminho:
        states.transicionar(session, task, destino)
    session.commit()

    assert task.status == states.FINALIZADA

    historico = (
        session.query(TaskStateHistory)
        .filter(TaskStateHistory.task_id == task.id)
        .order_by(TaskStateHistory.id)
        .all()
    )
    assert [h.to_status for h in historico] == caminho
    assert historico[0].from_status == states.CANDIDATA


@requires_db
def test_transicao_fora_do_mapa_e_recusada(session, task):
    """Pular o planejamento e ir direto executar não é um caminho do modelo."""
    with pytest.raises(states.TransicaoInvalidaError, match="candidata → em_execucao"):
        states.transicionar(session, task, states.EM_EXECUCAO)

    assert task.status == states.CANDIDATA


@requires_db
def test_finalizada_e_terminal(session, task):
    states.transicionar(session, task, states.FINALIZADA, final_outcome="recusada")
    session.commit()

    with pytest.raises(states.TransicaoInvalidaError):
        states.transicionar(session, task, states.EM_PLANEJAMENTO)


@requires_db
def test_suspensa_e_retomada(session, task):
    for destino in (states.EM_PLANEJAMENTO, states.PRONTA_PARA_DESPACHO, states.EM_EXECUCAO):
        states.transicionar(session, task, destino)

    states.transicionar(session, task, states.SUSPENSA, note="falhou", alert="retries")
    assert task.alert == "retries"

    states.transicionar(session, task, states.EM_EXECUCAO, note="retomada", alert="none")
    session.commit()

    assert task.status == states.EM_EXECUCAO
    assert task.alert == "none"


@requires_db
def test_homologacao_pode_voltar_para_execucao_no_ajuste(session, task):
    for destino in (
        states.EM_PLANEJAMENTO,
        states.PRONTA_PARA_DESPACHO,
        states.EM_EXECUCAO,
        states.EM_HOMOLOGACAO,
    ):
        states.transicionar(session, task, destino)

    states.transicionar(session, task, states.EM_EXECUCAO, note="ajuste pedido")
    session.commit()

    assert task.status == states.EM_EXECUCAO


@requires_db
def test_suspensa_e_homologacao_podem_voltar_ao_planejamento(session, task):
    for destino in (states.EM_PLANEJAMENTO, states.PRONTA_PARA_DESPACHO, states.EM_EXECUCAO):
        states.transicionar(session, task, destino)
    states.transicionar(session, task, states.SUSPENSA)
    states.transicionar(session, task, states.EM_PLANEJAMENTO)
    session.commit()

    assert task.status == states.EM_PLANEJAMENTO


def test_score_de_prioridade():
    t = Task(title="x", description="y", module="geral", impact=5, complexity=2, urgency_score=3.0)
    assert states.score_de_prioridade(t) == 6.0

    sem_urgencia = Task(title="x", description="y", module="geral", impact=2, complexity=4)
    assert states.score_de_prioridade(sem_urgencia) == -2.0
