"""O grafo de dependências entre tarefas.

Substitui o `waiting_on_task_id` - um escalar recalculado a cada despacho, que
só sabia guardar o último bloqueio. Um escalar não é um grafo: não comporta duas
dependências, não diz de onde cada uma veio, e não tem arestas para desenhar.

Três origens de aresta, com regras diferentes de quem pode apagar:

- **arquivo** - detectada por sobreposição de `affected_files`. O sistema a
  recalcula a cada despacho e pode removê-la sozinho.
- **semantica** - detectada por proximidade entre os embeddings das propostas,
  quando a tarefa fica pronta para despacho. **Não bloqueia**: bloquear por peso
  e limiar está fora do escopo da monografia (§4.4.2). Fica registrada e
  desenhada no grafo, para quem decide ver que duas tarefas mexem no mesmo tema.
- **manual** - criada por uma pessoa no painel. **Nenhum recálculo a remove**:
  uma decisão humana não é desfeita por rotina automática.

Só `arquivo` e `manual` seguram o despacho e propagam a suspensão.
"""

from __future__ import annotations

import logging

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.common.config import settings
from app.common.vector_store import search
from app.orchestration.models import (
    DEP_ARQUIVO,
    DEP_MANUAL,
    DEP_SEMANTICA,
    ORIGENS_DE_DEPENDENCIA,
    PlanningDocument,
    TaskDependency,
)
from app.orchestration.states import CANDIDATA, EM_EXECUCAO, EM_HOMOLOGACAO, FINALIZADA
from app.task_layer.models import Proposal, Task

logger = logging.getLogger("pase.orchestration")

#: Estados em que uma tarefa ainda segura os arquivos que está mexendo.
OCUPANDO_ARQUIVOS = (EM_EXECUCAO, EM_HOMOLOGACAO)

#: Origens que seguram o despacho. A semântica é informativa.
BLOQUEANTES = (DEP_ARQUIVO, DEP_MANUAL)

#: Quantas propostas parecidas a busca devolve antes de filtrar as tarefas abertas.
VIZINHOS_SEMANTICOS = 20


class DependenciaInvalidaError(RuntimeError):
    """Aresta que criaria um ciclo, ou apontaria para a própria tarefa."""


def arestas_de(session: Session, task_id: int) -> list[TaskDependency]:
    return list(
        session.execute(
            select(TaskDependency).where(TaskDependency.task_id == task_id)
        ).scalars()
    )


def bloqueadoras(session: Session, task_id: int) -> list[Task]:
    """Tarefas de que esta depende e que **ainda não acabaram**.

    Lista vazia significa caminho livre. Dependência de tarefa já finalizada não
    bloqueia nada: ela cumpriu o seu papel e continua no grafo como histórico.
    Aresta semântica não entra: ela informa, não segura.
    """
    linhas = session.execute(
        select(Task)
        .join(TaskDependency, TaskDependency.depends_on_task_id == Task.id)
        .where(TaskDependency.task_id == task_id)
        .where(TaskDependency.kind.in_(BLOQUEANTES))
        .where(Task.status != FINALIZADA)
    ).scalars()
    return list(linhas)


def dependentes(session: Session, task_id: int) -> list[Task]:
    """Quem espera por esta tarefa por uma aresta que bloqueia."""
    return list(
        session.execute(
            select(Task)
            .join(TaskDependency, TaskDependency.task_id == Task.id)
            .where(TaskDependency.depends_on_task_id == task_id)
            .where(TaskDependency.kind.in_(BLOQUEANTES))
            .order_by(Task.id)
        ).scalars()
    )


def _vizinhos(session: Session, origens: set[int], *, para_frente: bool, so_bloqueantes: bool):
    """Fecho transitivo seguindo as arestas num sentido (ou no contrário)."""
    de, para = (
        (TaskDependency.task_id, TaskDependency.depends_on_task_id)
        if para_frente
        else (TaskDependency.depends_on_task_id, TaskDependency.task_id)
    )
    pilha = list(origens)
    vistos: set[int] = set()
    while pilha:
        atual = pilha.pop()
        if atual in vistos:
            continue
        vistos.add(atual)
        consulta = select(para).where(de == atual)
        if so_bloqueantes:
            consulta = consulta.where(TaskDependency.kind.in_(BLOQUEANTES))
        pilha.extend(session.execute(consulta).scalars())
    return vistos


def _criaria_ciclo(
    session: Session, task_id: int, depende_de: int, *, so_bloqueantes: bool = False
) -> bool:
    """Seguir as arestas a partir de `depende_de` chega de volta em `task_id`?

    Busca em profundidade com marcação de visitados: sem isso, um ciclo que já
    exista no grafo faria esta própria checagem rodar para sempre.
    """
    return task_id in _vizinhos(
        session, {depende_de}, para_frente=True, so_bloqueantes=so_bloqueantes
    )


def _ceder_semanticas(session: Session, task_id: int, depende_de: int) -> int:
    """Apaga as arestas semânticas que fechariam ciclo com uma aresta que bloqueia.

    Uma aresta semântica não pode impedir uma de arquivo: se impedisse, duas
    tarefas mexendo nos mesmos arquivos rodariam lado a lado só porque o tema
    delas é parecido. Chamada só quando o ciclo **não** existe entre as arestas
    que bloqueiam - então todo caminho de volta passa por alguma semântica, e
    tirar as semânticas desses caminhos desfaz o ciclo.

    Uma aresta u → v está num caminho de `depende_de` até `task_id` quando u é
    alcançável a partir de `depende_de` e v alcança `task_id`.
    """
    alcancaveis = _vizinhos(session, {depende_de}, para_frente=True, so_bloqueantes=False)
    alcancam = _vizinhos(session, {task_id}, para_frente=False, so_bloqueantes=False)
    removidas = 0
    for aresta in session.execute(
        select(TaskDependency).where(TaskDependency.kind == DEP_SEMANTICA)
    ).scalars():
        if aresta.task_id in alcancaveis and aresta.depends_on_task_id in alcancam:
            logger.info(
                "aresta semântica #%s → #%s cede lugar a #%s → #%s",
                aresta.task_id,
                aresta.depends_on_task_id,
                task_id,
                depende_de,
            )
            session.delete(aresta)
            removidas += 1
    session.flush()
    return removidas


def ligar(
    session: Session,
    task_id: int,
    depende_de: int,
    *,
    kind: str = DEP_ARQUIVO,
    reason: str | None = None,
) -> TaskDependency | None:
    """Cria a aresta, se ela for válida e ainda não existir.

    Devolve `None` quando a aresta já existia - repetir a ligação é idempotente
    de propósito, porque a detecção por arquivo roda a cada despacho.
    """
    if kind not in ORIGENS_DE_DEPENDENCIA:
        raise DependenciaInvalidaError(f"origem de dependência desconhecida: {kind}")
    if task_id == depende_de:
        raise DependenciaInvalidaError("uma tarefa não pode depender de si mesma")

    existente = session.execute(
        select(TaskDependency)
        .where(TaskDependency.task_id == task_id)
        .where(TaskDependency.depends_on_task_id == depende_de)
    ).scalar_one_or_none()
    if existente is not None:
        # Semântica não segura nada: quando arquivo ou pessoa pedem a mesma
        # ligação, ela passa a bloquear. O contrário nunca acontece.
        if existente.kind == DEP_SEMANTICA and kind in BLOQUEANTES:
            existente.kind = kind
            existente.reason = reason
            session.add(existente)
            session.flush()
            return existente
        return None

    # Aresta que bloqueia só é recusada por ciclo entre arestas que bloqueiam; as
    # semânticas no caminho cedem. A semântica é recusada por qualquer ciclo.
    if (
        kind in BLOQUEANTES
        and not _criaria_ciclo(session, task_id, depende_de, so_bloqueantes=True)
        and _criaria_ciclo(session, task_id, depende_de)
    ):
        _ceder_semanticas(session, task_id, depende_de)

    if _criaria_ciclo(session, task_id, depende_de):
        raise DependenciaInvalidaError(
            f"a tarefa #{depende_de} já depende, direta ou indiretamente, da #{task_id}: "
            "a aresta fecharia um ciclo e nenhuma das duas poderia começar"
        )

    aresta = TaskDependency(
        task_id=task_id, depends_on_task_id=depende_de, kind=kind, reason=reason
    )
    session.add(aresta)
    session.flush()
    logger.info("task #%s passa a depender da #%s (%s)", task_id, depende_de, kind)
    return aresta


def desligar(session: Session, task_id: int, depende_de: int) -> bool:
    aresta = session.execute(
        select(TaskDependency)
        .where(TaskDependency.task_id == task_id)
        .where(TaskDependency.depends_on_task_id == depende_de)
    ).scalar_one_or_none()
    if aresta is None:
        return False
    session.delete(aresta)
    # Sem o flush, uma consulta seguinte na mesma sessão ainda encontra a linha.
    session.flush()
    return True


def recalcular_por_arquivo(
    session: Session, task: Task, plano: PlanningDocument
) -> list[int]:
    """Refaz as arestas de origem `arquivo` desta tarefa.

    Só as de `arquivo`: as `manual` e as `semantica` sobrevivem ao recálculo,
    porque não foram o sistema que as criou e não cabe ao sistema removê-las.
    """
    for aresta in arestas_de(session, task.id):
        if aresta.kind == DEP_ARQUIVO:
            session.delete(aresta)
    session.flush()

    previstos = set(plano.affected_files or [])
    if not previstos:
        return []

    ligadas = []
    em_andamento = session.execute(
        select(Task).where(Task.status.in_(OCUPANDO_ARQUIVOS)).where(Task.id != task.id)
    ).scalars()

    for outra in em_andamento:
        outro_plano = session.execute(
            select(PlanningDocument)
            .where(PlanningDocument.task_id == outra.id)
            .order_by(PlanningDocument.id.desc())
            .limit(1)
        ).scalar_one_or_none()
        if not outro_plano:
            continue

        comuns = previstos & set(outro_plano.affected_files or [])
        if not comuns:
            continue

        try:
            criada = ligar(
                session,
                task.id,
                outra.id,
                kind=DEP_ARQUIVO,
                reason="arquivos em comum: " + ", ".join(sorted(comuns)),
            )
        except DependenciaInvalidaError as exc:
            # Ciclo por sobreposição de arquivos é possível quando dois planos se
            # cruzam. Registrar e seguir é melhor que travar o despacho: a
            # detecção por arquivo é uma otimização, não uma regra de negócio.
            logger.warning("não liguei #%s → #%s: %s", task.id, outra.id, exc)
            continue
        if criada is not None:
            ligadas.append(outra.id)

    return ligadas


def ligar_por_semantica(session: Session, task: Task) -> list[int]:
    """Liga a tarefa às tarefas abertas cujas propostas falam do mesmo assunto.

    Roda quando a tarefa fica pronta para despacho. A tarefa que chega depende
    das que já estavam no fluxo (aprovadas, ainda não finalizadas): quem chegou
    antes define o terreno. Candidata fica de fora - ninguém decidiu fazê-la -,
    e liga-se a ela quando ela própria ficar pronta.

    Usa o embedding que a proposta já tem: nenhuma chamada nova ao provider.
    O limiar fica abaixo do de duplicata de propósito - parecida o bastante para
    ser o mesmo tema, não para ser a mesma demanda (essa o funil já barrou).
    """
    if task.proposal_id is None:
        return []
    proposta = session.get(Proposal, task.proposal_id)
    if proposta is None or proposta.embedding is None:
        return []

    hits = search(
        "",
        ["candidata"],
        top_k=VIZINHOS_SEMANTICOS,
        session=session,
        vector=[float(x) for x in proposta.embedding],
    )
    parecidas = {
        h.ref_id: h.similarity
        for h in hits
        if h.ref_id != task.proposal_id
        and h.similarity >= settings.semantic_dependency_threshold
    }
    if not parecidas:
        return []

    abertas = session.execute(
        select(Task)
        .where(Task.proposal_id.in_(parecidas))
        .where(Task.id != task.id)
        .where(Task.status.not_in((CANDIDATA, FINALIZADA)))
        .where(Task.archived_at.is_(None))
        .order_by(Task.id)
    ).scalars()

    ligadas = []
    for outra in abertas:
        similaridade = parecidas[outra.proposal_id]
        try:
            criada = ligar(
                session,
                task.id,
                outra.id,
                kind=DEP_SEMANTICA,
                reason=f"propostas parecidas (similaridade {similaridade:.2f})",
            )
        except DependenciaInvalidaError as exc:
            # A outra já depende desta, direta ou indiretamente: a ligação no
            # sentido inverso já conta a mesma história.
            logger.info("não liguei #%s → #%s por semântica: %s", task.id, outra.id, exc)
            continue
        if criada is not None:
            ligadas.append(outra.id)
    return ligadas


def grafo(session: Session) -> dict:
    """Nós e arestas para o painel desenhar.

    Devolve dados crus, sem layout: onde cada nó aparece na tela é decisão da
    interface, não do servidor.
    """
    tarefas = (
        session.execute(select(Task).where(Task.archived_at.is_(None)).order_by(Task.id))
        .scalars()
        .all()
    )
    visiveis = {t.id for t in tarefas}
    arestas = [
        a
        for a in session.execute(select(TaskDependency)).scalars().all()
        if a.task_id in visiveis and a.depends_on_task_id in visiveis
    ]

    return {
        "nodes": [
            {
                "id": t.id,
                "title": t.title,
                "status": t.status,
                "final_outcome": t.final_outcome,
                "module": t.module,
                "risk_tier": t.risk_tier,
                "change_type": t.change_type,
                "alert": t.alert,
                "uncertainty": t.uncertainty,
                "priority_score": float(t.impact - t.complexity + (t.urgency_score or 0)),
            }
            for t in tarefas
        ],
        "edges": [
            {
                "from": a.task_id,
                "to": a.depends_on_task_id,
                "kind": a.kind,
                "reason": a.reason,
                "blocking": a.kind in BLOQUEANTES,
            }
            for a in arestas
        ],
    }
