"""Despacho em paralelo, arestas semânticas e a ordem depois da aprovação.

Monografia §4.4.2: "tarefas totalmente independentes são despachadas em
paralelo", e as arestas do grafo têm três origens - sobreposição de arquivos,
proximidade semântica e decisão manual. §4.4.4: o que fala da entrega aprovada
(CI da develop, sugestão de contexto) não espera a execução de quem dependia dela.
"""

import threading

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text

from app.common import context_suggestions
from app.common.config import settings
from app.orchestration import chain, delivery, dependencies, homologation, states
from app.orchestration.models import (
    DEP_ARQUIVO,
    DEP_MANUAL,
    DEP_SEMANTICA,
    PlanningDocument,
)
from app.task_layer.models import Proposal, Task
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


def _tarefa(session, status, arquivos, *, proposta: Proposal | None = None) -> Task:
    t = Task(
        title=f"Tarefa {status}", description="d", module="geral", impact=3, complexity=1,
        status=status, proposal_id=proposta.id if proposta else None,
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


def _vetor(*componentes: float) -> list[float]:
    v = [0.0] * settings.embedding_dim
    for i, c in enumerate(componentes):
        v[i] = c
    return v


def _proposta(session, vetor: list[float], outcome: str = "candidata") -> Proposal:
    p = Proposal(origin="manual", raw_text="x", title="x", embedding=vetor, outcome=outcome)
    session.add(p)
    session.commit()
    return p


def _status(session, task) -> str:
    session.expire_all()
    return session.get(Task, task.id).status


# --------------------------------------------------------------------------- #
# Despacho em paralelo
# --------------------------------------------------------------------------- #


@requires_db
def test_liberadas_independentes_executam_ao_mesmo_tempo(limpo, monkeypatch):
    """Cada uma espera a outra começar: em série, a primeira esperaria para sempre."""
    a = _tarefa(limpo, states.FINALIZADA, ["a.py"])
    b = _tarefa(limpo, states.PRONTA_PARA_DESPACHO, ["b.py"])
    c = _tarefa(limpo, states.PRONTA_PARA_DESPACHO, ["c.py"])
    for t in (b, c):
        dependencies.ligar(limpo, t.id, a.id, kind=DEP_MANUAL)
    limpo.commit()

    encontro = threading.Barrier(2, timeout=5)
    juntas = []

    def executar(tid, **kw):
        encontro.wait()  # BrokenBarrierError se a outra não estiver rodando junto
        juntas.append(tid)

    monkeypatch.setattr(chain, "rodar_execucao", executar)

    threads = chain.liberar_quem_esperava(a.id)
    for t in threads:
        t.join(timeout=10)

    assert sorted(juntas) == [b.id, c.id]
    assert _status(limpo, b) == _status(limpo, c) == states.EM_EXECUCAO


@requires_db
def test_liberadas_que_disputam_arquivos_nao_rodam_juntas(limpo, monkeypatch):
    """A decisão é sequencial: a segunda já vê a primeira ocupando o arquivo."""
    a = _tarefa(limpo, states.FINALIZADA, ["a.py"])
    b = _tarefa(limpo, states.PRONTA_PARA_DESPACHO, ["comum.py"])
    c = _tarefa(limpo, states.PRONTA_PARA_DESPACHO, ["comum.py"])
    for t in (b, c):
        dependencies.ligar(limpo, t.id, a.id, kind=DEP_MANUAL)
    limpo.commit()
    monkeypatch.setattr(chain, "rodar_execucao", lambda tid, **kw: None)

    threads = chain.liberar_quem_esperava(a.id)
    for t in threads:
        t.join(timeout=10)

    assert len(threads) == 1
    assert _status(limpo, b) == states.EM_EXECUCAO
    assert _status(limpo, c) == states.PRONTA_PARA_DESPACHO
    arestas = {(e.depends_on_task_id, e.kind) for e in dependencies.arestas_de(limpo, c.id)}
    assert (b.id, DEP_ARQUIVO) in arestas


@requires_db
def test_liberacao_nao_despacha_duas_vezes(limpo, monkeypatch):
    """Duas predecessoras terminando juntas liberam a mesma tarefa uma vez só."""
    a = _tarefa(limpo, states.FINALIZADA, ["a.py"])
    x = _tarefa(limpo, states.FINALIZADA, ["x.py"])
    b = _tarefa(limpo, states.PRONTA_PARA_DESPACHO, ["b.py"])
    dependencies.ligar(limpo, b.id, a.id, kind=DEP_MANUAL)
    dependencies.ligar(limpo, b.id, x.id, kind=DEP_MANUAL)
    limpo.commit()
    rodadas = []
    monkeypatch.setattr(chain, "rodar_execucao", lambda tid, **kw: rodadas.append(tid))

    threads = chain.liberar_quem_esperava(a.id) + chain.liberar_quem_esperava(x.id)
    for t in threads:
        t.join(timeout=10)

    assert rodadas == [b.id]


# --------------------------------------------------------------------------- #
# Arestas semânticas
# --------------------------------------------------------------------------- #


@requires_db
def test_aresta_semantica_nao_segura_o_despacho(limpo):
    a = _tarefa(limpo, states.EM_EXECUCAO, ["a.py"])
    b = _tarefa(limpo, states.PRONTA_PARA_DESPACHO, ["b.py"])
    dependencies.ligar(limpo, b.id, a.id, kind=DEP_SEMANTICA)
    limpo.commit()

    assert dependencies.bloqueadoras(limpo, b.id) == []
    assert chain.tentar_despacho(b.id) is True


@requires_db
def test_liga_por_semantica_so_tarefas_abertas_e_parecidas(limpo, monkeypatch):
    monkeypatch.setattr(settings, "semantic_dependency_threshold", 0.6)
    parecida = _tarefa(limpo, states.EM_EXECUCAO, ["a.py"], proposta=_proposta(limpo, _vetor(1.0)))
    distante = _tarefa(limpo, states.EM_EXECUCAO, ["c.py"], proposta=_proposta(limpo, _vetor(0, 1.0)))
    # candidata: ninguém decidiu fazê-la ainda
    _tarefa(limpo, states.CANDIDATA, ["d.py"], proposta=_proposta(limpo, _vetor(1.0)))
    nova = _tarefa(
        limpo, states.PRONTA_PARA_DESPACHO, ["b.py"], proposta=_proposta(limpo, _vetor(0.9, 0.4359))
    )

    ligadas = dependencies.ligar_por_semantica(limpo, nova)

    assert ligadas == [parecida.id]
    aresta = dependencies.arestas_de(limpo, nova.id)[0]
    assert aresta.kind == DEP_SEMANTICA
    assert "0.90" in aresta.reason
    assert distante.id not in ligadas


@requires_db
def test_semantica_recusa_ciclo(limpo):
    """A já depende de B: a aresta B → A fecharia o ciclo e não é criada."""
    a = _tarefa(limpo, states.EM_EXECUCAO, ["a.py"], proposta=_proposta(limpo, _vetor(1.0)))
    b = _tarefa(limpo, states.PRONTA_PARA_DESPACHO, ["b.py"], proposta=_proposta(limpo, _vetor(1.0)))
    dependencies.ligar(limpo, a.id, b.id, kind=DEP_MANUAL)

    assert dependencies.ligar_por_semantica(limpo, b) == []
    assert dependencies.arestas_de(limpo, b.id) == []


@requires_db
def test_semantica_cede_lugar_a_aresta_de_arquivo(limpo):
    """Senão, duas tarefas no mesmo arquivo rodariam juntas por terem tema parecido."""
    a = _tarefa(limpo, states.PRONTA_PARA_DESPACHO, ["a.py"])
    b = _tarefa(limpo, states.EM_EXECUCAO, ["a.py"])
    dependencies.ligar(limpo, b.id, a.id, kind=DEP_SEMANTICA)

    criada = dependencies.ligar(limpo, a.id, b.id, kind=DEP_ARQUIVO, reason="a.py")

    assert criada is not None
    assert dependencies.arestas_de(limpo, b.id) == []


@requires_db
def test_ciclo_entre_arestas_que_bloqueiam_continua_recusado(limpo):
    a = _tarefa(limpo, states.PRONTA_PARA_DESPACHO, ["a.py"])
    b = _tarefa(limpo, states.EM_EXECUCAO, ["b.py"])
    dependencies.ligar(limpo, b.id, a.id, kind=DEP_MANUAL)

    with pytest.raises(dependencies.DependenciaInvalidaError, match="ciclo"):
        dependencies.ligar(limpo, a.id, b.id, kind=DEP_ARQUIVO)


@requires_db
def test_ligacao_manual_sobre_semantica_passa_a_bloquear(limpo):
    a = _tarefa(limpo, states.EM_EXECUCAO, ["a.py"])
    b = _tarefa(limpo, states.PRONTA_PARA_DESPACHO, ["b.py"])
    dependencies.ligar(limpo, b.id, a.id, kind=DEP_SEMANTICA)

    dependencies.ligar(limpo, b.id, a.id, kind=DEP_MANUAL, reason="precisa da API")

    assert [e.kind for e in dependencies.arestas_de(limpo, b.id)] == [DEP_MANUAL]
    assert [t.id for t in dependencies.bloqueadoras(limpo, b.id)] == [a.id]


@requires_db
def test_aprovar_o_plano_liga_por_semantica_e_despacha(limpo, monkeypatch):
    a = _tarefa(limpo, states.EM_EXECUCAO, ["a.py"], proposta=_proposta(limpo, _vetor(1.0)))
    b = _tarefa(limpo, states.PRONTA_PARA_DESPACHO, ["b.py"], proposta=_proposta(limpo, _vetor(1.0)))
    rodadas = []
    monkeypatch.setattr(chain, "rodar_execucao", lambda tid, **kw: rodadas.append(tid))

    chain.rodar_apos_aprovacao_do_plano(b.id)

    assert [(e.depends_on_task_id, e.kind) for e in dependencies.arestas_de(limpo, b.id)] == [
        (a.id, DEP_SEMANTICA)
    ]
    assert rodadas == [b.id]  # a semântica não segurou
    grafo = dependencies.grafo(limpo)
    assert {"from": b.id, "to": a.id, "blocking": False}.items() <= next(
        e for e in grafo["edges"] if e["from"] == b.id
    ).items()


# --------------------------------------------------------------------------- #
# Ordem depois da aprovação (§4.4.4)
# --------------------------------------------------------------------------- #


@requires_db
def test_ci_e_contexto_vem_antes_de_liberar_dependentes(limpo, monkeypatch):
    t = _tarefa(limpo, states.EM_HOMOLOGACAO, ["a.py"])

    def aprovar(session, task, decisao, comentario):
        states.transicionar(session, task, states.FINALIZADA, final_outcome="aprovada")
        return {"merged": True}

    ordem = []
    monkeypatch.setattr(homologation, "decidir", aprovar)
    monkeypatch.setattr(delivery, "rodar_ci_da_develop", lambda tid: ordem.append("ci"))
    monkeypatch.setattr(
        context_suggestions, "gerar_para_tarefa", lambda tid: ordem.append("contexto")
    )
    monkeypatch.setattr(chain, "liberar_quem_esperava", lambda tid: ordem.append("liberar"))

    from app.main import app

    with TestClient(app) as client:
        r = client.post(f"/api/tasks/{t.id}/homologation", json={"decision": "aprovar"})

    assert r.status_code == 200
    assert ordem == ["ci", "contexto", "liberar"]
