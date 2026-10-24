"""Refazer uma tarefa: tentativa nova, ligada à anterior, que lembra o que deu errado."""

import json

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text

from app.orchestration import chain, homologation, redo
from app.orchestration.models import ExecutionRun, PlanningDocument
from app.task_layer.models import Proposal, Task, TaskStateHistory
from tests.conftest import requires_db

TABELAS = (
    "task_state_history",
    "execution_runs",
    "planning_documents",
    "tasks",
    "proposals",
)


def _zerar(session):
    for tabela in TABELAS:
        session.execute(text(f"DELETE FROM {tabela}"))
    session.commit()


@pytest.fixture
def limpo(session):
    _zerar(session)
    yield session
    _zerar(session)


def _finalizada(session, desfecho: str = "revertida", **campos) -> Task:
    proposta = Proposal(origin="manual", raw_text="modo escuro", outcome="revertida")
    session.add(proposta)
    session.flush()
    task = Task(
        proposal_id=proposta.id,
        title="Modo escuro no FinTrack",
        description="Permitir alternar entre tema claro e escuro.",
        module="geral",
        impact=3,
        complexity=2,
        risk_tier="baixo",
        status="finalizada",
        final_outcome=desfecho,
        **campos,
    )
    session.add(task)
    session.flush()
    session.add(
        TaskStateHistory(
            task_id=task.id,
            from_status="finalizada",
            to_status="finalizada",
            note="revertida em abc12345: Não funcionou",
        )
    )
    session.commit()
    return task


@requires_db
def test_refazer_cria_tarefa_nova_ligada_a_anterior(limpo):
    anterior = _finalizada(limpo)

    nova = redo.refazer(limpo, anterior, "clicar no botão não mudava nenhuma cor")
    limpo.commit()

    assert nova.id != anterior.id
    assert nova.parent_task_id == anterior.id
    assert nova.redo_feedback == "clicar no botão não mudava nenhuma cor"
    assert nova.status == "candidata"
    assert nova.plan_approval_required is True  # refazer sempre para no plano
    assert (nova.title, nova.module, nova.impact) == (
        anterior.title,
        anterior.module,
        anterior.impact,
    )
    # a anterior continua registrada como estava
    limpo.refresh(anterior)
    assert anterior.final_outcome == "revertida"


@requires_db
def test_a_demanda_volta_a_estar_em_andamento(limpo):
    """Reenviar a mesma demanda agora deve ser barrado - e o motivo volta a ser verdade."""
    anterior = _finalizada(limpo)

    redo.refazer(limpo, anterior, "faltou a paleta escura")
    limpo.commit()

    assert limpo.get(Proposal, anterior.proposal_id).outcome == "candidata"


@requires_db
def test_refazer_exige_motivo(limpo):
    anterior = _finalizada(limpo)

    with pytest.raises(redo.RefazerError, match="o que estava errado"):
        redo.refazer(limpo, anterior, "   ")


@requires_db
def test_nao_refaz_tarefa_em_andamento(limpo):
    em_curso = Task(
        title="t", description="d", module="geral", status="em_execucao", impact=1, complexity=1
    )
    limpo.add(em_curso)
    limpo.commit()

    with pytest.raises(redo.RefazerError, match="finalizada"):
        redo.refazer(limpo, em_curso, "qualquer coisa")


@requires_db
def test_aprovada_e_revertida_antes_de_refazer(limpo, monkeypatch):
    anterior = _finalizada(limpo, desfecho="aprovada")
    revertidas = []

    def reverter_falso(session, task, motivo):
        revertidas.append((task.id, motivo))
        task.final_outcome = "revertida"
        return {"revertida": True}

    monkeypatch.setattr(homologation, "reverter", reverter_falso)

    nova = redo.refazer(limpo, anterior, "o saldo ficou errado")

    assert revertidas == [(anterior.id, "o saldo ficou errado")]
    assert nova.parent_task_id == anterior.id


@requires_db
def test_reversao_em_conflito_impede_refazer(limpo, monkeypatch):
    anterior = _finalizada(limpo, desfecho="aprovada")
    monkeypatch.setattr(
        homologation,
        "reverter",
        lambda session, task, motivo: {"revertida": False, "detail": "conflito"},
    )

    with pytest.raises(redo.RefazerError, match="conflito"):
        redo.refazer(limpo, anterior, "o saldo ficou errado")


@requires_db
def test_historico_leva_plano_revisao_e_motivo_ao_planejamento(limpo, tmp_path):
    anterior = _finalizada(limpo)
    limpo.add(
        PlanningDocument(
            task_id=anterior.id,
            acceptance_criteria=[{"id": "C1", "criterio": "O fundo fica escuro"}],
            affected_files=["client-frontend/app/layout.tsx"],
            roadmap="Pôr a classe dark no body.",
            tokens_estimated=1000,
        )
    )
    parecer = tmp_path / "review.json"
    parecer.write_text(
        json.dumps(
            {
                "aprovado": False,
                "resumo": "A classe é aplicada, mas nenhuma cor muda.",
                "criterios": [
                    {
                        "criterio": "O fundo fica escuro",
                        "atendido": False,
                        "anulado_por": "evidência não confere",
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    limpo.add(
        ExecutionRun(
            task_id=anterior.id, attempt=1, trigger="inicial", status="sucesso",
            review_path=str(parecer),
        )
    )
    limpo.commit()

    nova = redo.refazer(limpo, anterior, "nada mudava na tela")
    texto = redo.historico_de(limpo, nova)

    assert "nada mudava na tela" in texto
    assert "Pôr a classe dark no body." in texto
    assert "O fundo fica escuro" in texto
    assert "nenhuma cor muda" in texto
    assert "Não funcionou" in texto  # o motivo da reversão


@requires_db
def test_tarefa_original_nao_tem_historico(limpo):
    task = _finalizada(limpo)
    assert redo.historico_de(limpo, task) == ""


@requires_db
def test_endpoint_refazer_dispara_a_cadeia_da_nova(limpo, monkeypatch):
    from app.main import app

    anterior = _finalizada(limpo)
    disparadas = []
    monkeypatch.setattr(chain, "rodar_cadeia", lambda task_id: disparadas.append(task_id))

    with TestClient(app) as client:
        resposta = client.post(
            f"/api/tasks/{anterior.id}/redo", json={"feedback": "faltou a paleta"}
        )
        detalhe = client.get(f"/api/tasks/{resposta.json()['task_id']}").json()

    assert resposta.status_code == 201
    nova_id = resposta.json()["task_id"]
    assert disparadas == [nova_id]
    assert detalhe["parent_task_id"] == anterior.id
    assert detalhe["redo_feedback"] == "faltou a paleta"


@requires_db
def test_endpoint_recusa_tarefa_que_nao_pode_ser_refeita(limpo):
    from app.main import app

    em_curso = Task(
        title="t", description="d", module="geral", status="candidata", impact=1, complexity=1
    )
    limpo.add(em_curso)
    limpo.commit()

    with TestClient(app) as client:
        resposta = client.post(f"/api/tasks/{em_curso.id}/redo", json={"feedback": "x"})

    assert resposta.status_code == 409


@requires_db
def test_teto_manual_da_tentativa_anterior_nao_e_herdado(limpo):
    anterior = _finalizada(limpo, budget_cap_tokens=600_000)

    nova = redo.refazer(limpo, anterior, "faltou a paleta")

    assert nova.budget_cap_tokens is None
