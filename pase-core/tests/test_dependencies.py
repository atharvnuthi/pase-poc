"""O grafo de dependências entre tarefas.

Substituiu o `waiting_on_task_id`, que era um escalar: guardava só o último
bloqueio, não dizia de onde ele vinha, e não tinha arestas para desenhar.
"""

import pytest
from sqlalchemy import text

from app.orchestration import dependencies
from app.orchestration.models import DEP_ARQUIVO, DEP_MANUAL, PlanningDocument
from app.task_layer.models import Task
from tests.conftest import requires_db


@pytest.fixture
def tarefas(session):
    def zerar():
        session.execute(text("DELETE FROM task_dependencies"))
        session.execute(text("DELETE FROM task_state_history"))
        session.execute(text("DELETE FROM planning_documents"))
        session.execute(text("DELETE FROM tasks"))
        session.commit()

    zerar()
    criadas = []
    for i in range(1, 4):
        t = Task(
            title=f"Tarefa {i}",
            description="...",
            module="geral",
            status="candidata",
            impact=3,
            complexity=1,
        )
        session.add(t)
        criadas.append(t)
    session.commit()
    yield criadas
    zerar()


@requires_db
def test_ligar_cria_a_aresta_uma_vez_so(session, tarefas):
    a, b, _ = tarefas

    primeira = dependencies.ligar(session, a.id, b.id, kind=DEP_MANUAL)
    repetida = dependencies.ligar(session, a.id, b.id, kind=DEP_MANUAL)

    assert primeira is not None
    assert repetida is None, "ligar duas vezes tem de ser idempotente"
    assert len(dependencies.arestas_de(session, a.id)) == 1


@requires_db
def test_tarefa_nao_depende_de_si_mesma(session, tarefas):
    a, _, _ = tarefas

    with pytest.raises(dependencies.DependenciaInvalidaError):
        dependencies.ligar(session, a.id, a.id)


@requires_db
def test_ciclo_e_recusado(session, tarefas):
    """A → B → C → A deixaria as três esperando para sempre."""
    a, b, c = tarefas
    dependencies.ligar(session, a.id, b.id, kind=DEP_MANUAL)
    dependencies.ligar(session, b.id, c.id, kind=DEP_MANUAL)

    with pytest.raises(dependencies.DependenciaInvalidaError, match="ciclo"):
        dependencies.ligar(session, c.id, a.id, kind=DEP_MANUAL)


@requires_db
def test_so_bloqueia_quem_ainda_nao_acabou(session, tarefas):
    a, b, c = tarefas
    dependencies.ligar(session, a.id, b.id, kind=DEP_MANUAL)
    dependencies.ligar(session, a.id, c.id, kind=DEP_MANUAL)

    assert len(dependencies.bloqueadoras(session, a.id)) == 2

    b.status = "finalizada"
    session.add(b)
    session.flush()

    pendentes = dependencies.bloqueadoras(session, a.id)
    assert [t.id for t in pendentes] == [c.id]


@requires_db
def test_recalculo_por_arquivo_preserva_a_aresta_manual(session, tarefas):
    """Decisão humana não é desfeita por rotina automática."""
    a, b, c = tarefas
    dependencies.ligar(session, a.id, b.id, kind=DEP_MANUAL, reason="eu quis")
    dependencies.ligar(session, a.id, c.id, kind=DEP_ARQUIVO, reason="arquivo x")
    session.flush()

    plano = PlanningDocument(task_id=a.id, affected_files=[], roadmap="", tokens_estimated=0)
    dependencies.recalcular_por_arquivo(session, a, plano)

    restantes = dependencies.arestas_de(session, a.id)
    assert [(e.depends_on_task_id, e.kind) for e in restantes] == [(b.id, DEP_MANUAL)]


@requires_db
def test_recalculo_liga_quem_disputa_os_mesmos_arquivos(session, tarefas):
    a, b, _ = tarefas
    b.status = "em_execucao"
    session.add(b)
    session.add(
        PlanningDocument(
            task_id=b.id,
            affected_files=["client-backend/app/routes.py"],
            roadmap="",
            tokens_estimated=0,
        )
    )
    session.flush()

    plano_a = PlanningDocument(
        task_id=a.id,
        affected_files=["client-backend/app/routes.py", "client-backend/app/models.py"],
        roadmap="",
        tokens_estimated=0,
    )
    session.add(plano_a)
    session.flush()

    ligadas = dependencies.recalcular_por_arquivo(session, a, plano_a)

    assert ligadas == [b.id]
    aresta = dependencies.arestas_de(session, a.id)[0]
    assert aresta.kind == DEP_ARQUIVO
    assert "routes.py" in aresta.reason


@requires_db
def test_desligar_remove(session, tarefas):
    a, b, _ = tarefas
    dependencies.ligar(session, a.id, b.id, kind=DEP_MANUAL)

    assert dependencies.desligar(session, a.id, b.id) is True
    assert dependencies.desligar(session, a.id, b.id) is False


@requires_db
def test_grafo_devolve_nos_e_arestas(session, tarefas):
    a, b, _ = tarefas
    dependencies.ligar(session, a.id, b.id, kind=DEP_MANUAL, reason="porque sim")

    g = dependencies.grafo(session)

    assert len(g["nodes"]) == 3
    assert {
        "from": a.id, "to": b.id, "kind": DEP_MANUAL, "reason": "porque sim", "blocking": True,
    } in g["edges"]
    no = next(n for n in g["nodes"] if n["id"] == a.id)
    assert no["status"] == "candidata"
    assert no["priority_score"] == 2.0  # impacto 3 − complexidade 1
