"""Os três CSVs de métricas (SPEC-06 §5).

São anexo do capítulo de validação: as colunas são contrato com a monografia, e
mudar uma delas invalida a planilha que o texto cita.
"""

import csv
import io

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text

from app.metrics.routes import COLUNAS_DISCARDS, COLUNAS_TASKS, COLUNAS_VIOLATIONS
from app.orchestration.models import ExecutionRun, PlanningDocument
from app.task_layer.models import DiscardedProposal, Proposal, Task
from app.upa.models import ZoneViolation
from tests.conftest import requires_db


def _linhas(texto: str) -> list[dict]:
    return list(csv.DictReader(io.StringIO(texto)))


@pytest.fixture
def client(session):
    from app.main import app

    def zerar():
        for tabela in (
            "task_state_history",
            "execution_runs",
            "planning_documents",
            "zone_violations",
            "discarded_proposals",
            "tasks",
            "proposals",
        ):
            session.execute(text(f"DELETE FROM {tabela}"))
        session.commit()

    zerar()
    with TestClient(app) as test_client:
        yield test_client
    zerar()


@requires_db
def test_colunas_de_tasks_sao_exatamente_as_do_spec(client):
    corpo = client.get("/api/metrics/tasks.csv").text

    assert corpo.splitlines()[0].split(",") == COLUNAS_TASKS


@requires_db
def test_colunas_de_discards_e_violations(client):
    assert client.get("/api/metrics/discards.csv").text.splitlines()[0].split(",") == COLUNAS_DISCARDS
    assert (
        client.get("/api/metrics/violations.csv").text.splitlines()[0].split(",")
        == COLUNAS_VIOLATIONS
    )


@requires_db
def test_tasks_csv_agrega_as_execucoes_da_tarefa(client, session):
    proposta = Proposal(origin="internal", raw_text="x", title="T", description="d")
    session.add(proposta)
    session.flush()

    task = Task(
        proposal_id=proposta.id,
        title="Exportar CSV",
        description="d",
        module="transacoes",
        impact=4,
        complexity=2,
        confidence=0.3,
        uncertainty=True,
        risk_tier="medio",
        status="finalizada",
        final_outcome="aprovada",
    )
    session.add(task)
    session.flush()

    session.add(
        PlanningDocument(task_id=task.id, affected_files=["a.py"], roadmap="r", tokens_estimated=1200)
    )
    session.add(
        ExecutionRun(
            task_id=task.id, attempt=1, trigger="inicial", status="falha",
            tokens_real=1000, duration_ms=5000, deviation_files=[],
        )
    )
    session.add(
        ExecutionRun(
            task_id=task.id, attempt=2, trigger="retry", status="sucesso",
            tokens_real=2000, duration_ms=7000, deviation_files=["extra.py"],
        )
    )
    session.commit()

    linha = _linhas(client.get("/api/metrics/tasks.csv").text)[0]

    assert linha["task_id"] == str(task.id)
    assert linha["origin"] == "internal"
    assert linha["runs"] == "2"
    assert linha["retries"] == "1"  # densidade de retrabalho sai daqui
    assert linha["tokens_estimated"] == "1200"
    assert linha["tokens_real_total"] == "3000"
    assert linha["duration_ms_total"] == "12000"
    assert linha["deviation_count"] == "1"
    assert linha["uncertainty"] == "1"
    assert linha["final_outcome"] == "aprovada"
    assert linha["finished_at"]


@requires_db
def test_discards_csv_traz_o_motivo_e_o_contador(client, session):
    proposta = Proposal(origin="external", raw_text="x", title="Minigame")
    session.add(proposta)
    session.flush()
    session.add(
        DiscardedProposal(
            proposal_id=proposta.id,
            reason_type="duplicata",
            reason_text="Já coberto por: Relatórios mensais",
            matched_ref="implemented#5",
            duplicate_count=3,
        )
    )
    session.commit()

    linha = _linhas(client.get("/api/metrics/discards.csv").text)[0]

    assert linha["reason_type"] == "duplicata"
    assert linha["matched_ref"] == "implemented#5"
    assert linha["duplicate_count"] == "3"
    assert linha["origin"] == "external"


@requires_db
def test_violations_csv(client, session):
    session.add(
        ZoneViolation(user_id=1, slot="resumo_financeiro", reason="href externo", raw_payload={})
    )
    session.commit()

    linha = _linhas(client.get("/api/metrics/violations.csv").text)[0]

    assert linha["user_id"] == "1"
    assert linha["reason"] == "href externo"


@requires_db
def test_csv_vazio_ainda_traz_o_cabecalho(client):
    """Planilha sem linhas é resultado legítimo; sem cabeçalho é arquivo quebrado."""
    corpo = client.get("/api/metrics/tasks.csv").text

    assert corpo.strip() == ",".join(COLUNAS_TASKS)
