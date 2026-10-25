"""Guardrail de custo (SPEC-04 §6.2, SPEC-00 §4)."""

import pytest
from sqlalchemy import text

from app.common.config import settings
from app.common.models import LLMCall
from app.execution import budget
from app.execution.budget import BudgetExcedidoError, BudgetGuard, teto_de
from app.orchestration.models import ExecutionRun
from app.task_layer.models import Task
from tests.conftest import requires_db


def _task(**campos) -> Task:
    return Task(title="x", description="y", module="geral", **campos)


def test_teto_usa_a_estimativa_mais_a_tolerancia_acima_do_piso():
    estimativa = settings.budget_min_tokens * 2
    esperado = int(estimativa * (1 + settings.budget_tolerance))

    assert teto_de(_task(), estimativa) == esperado


def test_estimativa_irrealista_cai_no_piso():
    """Medido: o P4 estimou 1200 tokens para uma execução de ~8800 por chamada.

    Sem piso, o guardrail passaria a barrar tarefa honesta em vez de loop
    desgovernado - o oposto do que o SPEC-00 §4 pede dele.
    """
    assert teto_de(_task(), 1_200) == settings.budget_min_tokens


def test_cap_de_demo_sobrepoe_a_estimativa_e_o_piso():
    """É o instrumento do D5(b): forçar a interrupção por budget."""
    assert teto_de(_task(demo_budget_cap_tokens=100), 999_999) == 100


def test_teto_manual_sobrepoe_o_calculo_automatico():
    assert teto_de(_task(budget_cap_tokens=250_000), 1_200) == 250_000


def test_corta_antes_da_chamada_e_nao_depois():
    """Descobrir o estouro com a resposta na mão já significa ter pago por ela."""
    guard = BudgetGuard(teto=1000, ja_gasto=0)

    guard.checar(custo_previsto=400)  # ainda cabe
    guard.registrar({"tokens_in": 600, "tokens_out": 500})

    with pytest.raises(BudgetExcedidoError) as excecao:
        guard.checar(custo_previsto=10)

    assert excecao.value.teto == 1000


def test_verificacao_e_preditiva_ja_na_primeira_chamada():
    """Teto de 100 com nada gasto: a chamada que não cabe é barrada de saída.

    Olhar só para o passado (`gasto >= teto`) deixaria passar exatamente a
    primeira chamada - e é ela que o D5(b) precisa ver interrompida.
    """
    guard = BudgetGuard(teto=100, ja_gasto=0)

    with pytest.raises(BudgetExcedidoError):
        guard.checar(custo_previsto=9_000)


def test_gasto_e_acumulado_entre_runs_da_mesma_task():
    """Um retry não pode reiniciar o teto - isso dobraria o custo permitido."""
    guard = BudgetGuard(teto=1000, ja_gasto=900)

    guard.registrar({"tokens_in": 50, "tokens_out": 60})

    assert guard.total == 1010
    with pytest.raises(BudgetExcedidoError):
        guard.checar()


def test_teto_ja_estourado_corta_mesmo_sem_custo_previsto():
    guard = BudgetGuard(teto=100, ja_gasto=150)

    with pytest.raises(BudgetExcedidoError):
        guard.checar()


@requires_db
def test_folga_menor_que_uma_chamada_impede_retomar(session):
    """Retrospectivo não basta: "não passou do teto" ≠ "consegue começar".

    Medido numa execução real: 35.592 tokens de folga contra chamadas de ~37.000
    produziram duas runs que morreram em sete segundos, com zero tokens gastos.
    """
    task = Task(title="t", description="d", module="geral", status="suspensa")
    session.add(task)
    session.flush()

    session.add(
        ExecutionRun(task_id=task.id, attempt=1, trigger="inicial", status="falha", tokens_real=114_408)
    )
    session.add(
        LLMCall(
            trace_id="x",
            kind="chat",
            provider="mock",
            model="m",
            tokens_in=36_000,
            tokens_out=1_000,
            tags={"task_id": task.id},
        )
    )
    session.flush()

    cabe, aviso = budget.cabe_mais_uma_chamada(session, task, teto=150_000)

    assert cabe is False
    assert "37.000" in aviso

    # Com teto maior, a mesma tarefa passa a caber.
    cabe, _ = budget.cabe_mais_uma_chamada(session, task, teto=400_000)
    assert cabe is True


@requires_db
def test_sem_chamada_anterior_usa_um_piso(session):
    """Tarefa que nunca chamou o modelo não tem o que medir."""
    task = Task(title="t", description="d", module="geral", status="suspensa")
    session.add(task)
    session.flush()

    cabe, _ = budget.cabe_mais_uma_chamada(session, task, teto=10)

    assert cabe is False


# --------------------------------------------------------------------------- #
# Custo previsto pelas chamadas anteriores (monografia §4.4.3)
# --------------------------------------------------------------------------- #


def test_a_propria_run_alimenta_a_estimativa():
    """O prompt sozinho não conta a saída: a chamada anterior conta."""
    guard = BudgetGuard(teto=9_000, ja_gasto=0, maior_chamada=0)
    guard.registrar({"tokens_in": 1_000, "tokens_out": 4_000})

    # Pelo tamanho do prompt (100), caberia: 5.000 + 100 < 9.000. Pela chamada
    # anterior (5.000), não cabe: 5.000 + 5.000 > 9.000.
    with pytest.raises(BudgetExcedidoError):
        guard.checar(custo_previsto=100)


def test_prompt_maior_que_as_chamadas_anteriores_ainda_conta():
    guard = BudgetGuard(teto=10_000, ja_gasto=0, maior_chamada=2_000)

    assert guard.previsto(500) == 2_000
    assert guard.previsto(8_000) == 8_000
    with pytest.raises(BudgetExcedidoError):
        guard.checar(custo_previsto=12_000)


@pytest.fixture
def chamada_registrada(session):
    """Uma tarefa com uma chamada de 37 mil tokens, **commitada**: o guardrail
    mede numa sessão própria, como faz durante a execução."""
    task = Task(title="t", description="d", module="geral", status="em_execucao")
    session.add(task)
    session.flush()
    session.add(
        LLMCall(
            trace_id="budget-previsto",
            kind="chat",
            provider="mock",
            model="m",
            tokens_in=36_000,
            tokens_out=1_000,
            tags={"task_id": task.id},
        )
    )
    session.commit()
    yield task
    session.execute(text("DELETE FROM llm_calls WHERE trace_id = 'budget-previsto'"))
    session.execute(text("DELETE FROM tasks WHERE id = :id"), {"id": task.id})
    session.commit()


@requires_db
def test_guard_mede_as_chamadas_anteriores_da_tarefa(chamada_registrada):
    task = chamada_registrada
    guard = BudgetGuard(teto=50_000, ja_gasto=20_000, task_id=task.id)

    assert guard.maior_chamada == 37_000
    # O prompt diz 1.000 e caberia; a medição diz 37.000 e não cabe.
    with pytest.raises(BudgetExcedidoError):
        guard.checar(custo_previsto=1_000)


@requires_db
def test_a_orquestracao_declara_a_tarefa_sem_mudar_a_chamada_do_executor(chamada_registrada):
    """O Executor constrói `BudgetGuard(teto=..., ja_gasto=...)`, sem task_id."""
    task = chamada_registrada

    with budget.tarefa_em_execucao(task.id):
        guard = BudgetGuard(teto=50_000, ja_gasto=0)
    fora = BudgetGuard(teto=50_000, ja_gasto=0)

    assert guard.maior_chamada == 37_000
    assert fora.maior_chamada == 0
