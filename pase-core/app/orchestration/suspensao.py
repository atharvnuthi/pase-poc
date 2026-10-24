"""Suspensão em cascata (monografia §4.4.3).

"A tarefa é suspensa, junto com o ramo do grafo que depende dela, e o problema é
reportado a uma pessoa." Sem a cascata, quem esperava por uma tarefa suspensa
ficava em `pronta_para_despacho` indefinidamente, parecendo saudável - e a
pessoa que olha o painel não tinha como saber que aquele ramo inteiro parou.

Só desce por arestas que bloqueiam (`arquivo` e `manual`); a semântica informa e
não segura ninguém. Só suspende quem ainda não começou: `pronta_para_despacho` e
`aguardando_plano`. Quem está planejando ou executando segue - interromper
trabalho em curso é decisão de uma pessoa, não de uma regra.

Nenhuma coluna nova guarda o estado anterior: ele está no histórico. A transição
para `suspensa` tem `from_status`, e a nota diz de qual predecessora a suspensão
veio. Restaurar é ler os dois de volta.
"""

from __future__ import annotations

import logging
import re

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.orchestration import dependencies, states
from app.task_layer.models import Task, TaskStateHistory

logger = logging.getLogger("pase.orchestration")

#: Alerta de quem foi suspensa porque uma predecessora foi.
ALERTA = "predecessora"

#: Estados de quem ainda não começou e pode ser suspensa junto.
ESPERANDO = (states.PRONTA_PARA_DESPACHO, states.AGUARDANDO_PLANO)

_MARCA = re.compile(r"^predecessora #(\d+) suspensa")


def nota_de_cascata(predecessora_id: int) -> str:
    return f"predecessora #{predecessora_id} suspensa"


def suspender(session: Session, task: Task, *, note: str, alert: str) -> list[int]:
    """Suspende a tarefa e, em cascata, quem depende dela. Devolve os ids arrastados."""
    states.transicionar(session, task, states.SUSPENSA, note=note, alert=alert)
    return suspender_dependentes(session, task.id)


def suspender_por_predecessora(session: Session, task: Task, predecessora_id: int) -> list[int]:
    """Chegou a vez da tarefa, mas quem ela espera está suspensa.

    Cobre quem não estava esperando no momento da suspensão - estava
    planejando, por exemplo - e só agora chegou ao despacho.
    """
    return suspender(session, task, note=nota_de_cascata(predecessora_id), alert=ALERTA)


def predecessora_suspensa(session: Session, task_id: int) -> Task | None:
    """A primeira tarefa suspensa entre as que seguram esta, se houver."""
    return next(
        (t for t in dependencies.bloqueadoras(session, task_id) if t.status == states.SUSPENSA),
        None,
    )


def suspender_dependentes(session: Session, task_id: int) -> list[int]:
    """Desce o grafo a partir da tarefa suspensa, suspendendo quem ainda esperava.

    Transitivo: a C que espera a B que espera a A é suspensa porque a B foi, e a
    nota de cada uma aponta a predecessora imediata - é por ela que a restauração
    sobe de volta.
    """
    arrastadas: list[int] = []
    fila = [task_id]
    vistos: set[int] = set()

    while fila:
        atual = fila.pop(0)
        if atual in vistos:
            continue
        vistos.add(atual)
        for dep in dependencies.dependentes(session, atual):
            if dep.status not in ESPERANDO:
                continue
            states.transicionar(
                session, dep, states.SUSPENSA, note=nota_de_cascata(atual), alert=ALERTA
            )
            logger.info("task #%s suspensa em cascata pela #%s", dep.id, atual)
            arrastadas.append(dep.id)
            fila.append(dep.id)

    return arrastadas


def suspensa_por(session: Session, task: Task) -> int | None:
    """De qual predecessora veio a suspensão desta tarefa, se veio de uma."""
    if task.status != states.SUSPENSA or task.alert != ALERTA:
        return None
    notas = session.execute(
        select(TaskStateHistory.note)
        .where(TaskStateHistory.task_id == task.id)
        .where(TaskStateHistory.note.like("predecessora #% suspensa%"))
        .order_by(TaskStateHistory.id.desc())
        .limit(1)
    ).scalar_one_or_none()
    marca = _MARCA.match(notas or "")
    return int(marca.group(1)) if marca else None


def _estado_antes_da_suspensao(session: Session, task_id: int) -> str:
    anterior = session.execute(
        select(TaskStateHistory.from_status)
        .where(TaskStateHistory.task_id == task_id)
        .where(TaskStateHistory.to_status == states.SUSPENSA)
        .where(TaskStateHistory.from_status != states.SUSPENSA)
        .order_by(TaskStateHistory.id.desc())
        .limit(1)
    ).scalar_one_or_none()
    return anterior if anterior in ESPERANDO else states.PRONTA_PARA_DESPACHO


def restaurar_dependentes(
    session: Session, task_id: int, *, remover_aresta: bool = False
) -> list[int]:
    """A predecessora saiu da suspensão: o ramo volta ao estado em que estava.

    `remover_aresta` vale para o cancelamento: a predecessora não vai mais
    existir, então a dependência dela perde o sentido e é desfeita - só a das
    tarefas que ela mesma arrastou.

    Se a dependente ainda espera **outra** predecessora suspensa, continua
    suspensa, agora por aquela - é dela que vai depender a próxima restauração.

    Devolve os ids restaurados para `pronta_para_despacho`, os únicos que podem
    precisar de despacho.
    """
    prontas: list[int] = []
    fila = [task_id]
    vistos: set[int] = set()

    while fila:
        atual = fila.pop(0)
        if atual in vistos:
            continue
        vistos.add(atual)

        for dep in dependencies.dependentes(session, atual):
            if suspensa_por(session, dep) != atual:
                continue
            if remover_aresta and atual == task_id:
                dependencies.desligar(session, dep.id, atual)

            outra = predecessora_suspensa(session, dep.id)
            if outra is not None:
                session.add(
                    TaskStateHistory(
                        task_id=dep.id,
                        from_status=dep.status,
                        to_status=dep.status,
                        note=f"{nota_de_cascata(outra.id)} (a #{atual} saiu da suspensão)",
                    )
                )
                session.flush()
                continue

            destino = _estado_antes_da_suspensao(session, dep.id)
            motivo = "cancelada" if remover_aresta and atual == task_id else "retomada"
            states.transicionar(
                session, dep, destino, note=f"predecessora #{atual} {motivo}", alert="none"
            )
            logger.info("task #%s volta a %s: predecessora #%s %s", dep.id, destino, atual, motivo)
            if destino == states.PRONTA_PARA_DESPACHO:
                prontas.append(dep.id)
            fila.append(dep.id)

    return prontas
