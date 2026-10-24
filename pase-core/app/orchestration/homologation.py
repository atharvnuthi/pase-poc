"""Homologação - o gate humano que libera código para a branch principal (SPEC-04 §5).

É o ponto do modelo onde a autonomia termina e a decisão volta a ser de uma
pessoa. O humano revisa o que **já passou pela máquina** (lint e testes verdes,
SPEC-00 §5); ele não é a primeira linha de defesa, é a última.

Três saídas: aprovar (merge na principal), ajustar (nova run com o comentário)
ou recusar (entra no Histórico de Descartes, com embedding).
"""

from __future__ import annotations

import logging

from sqlalchemy.orm import Session

from app.common import context_suggestions, conventions, git_service
from app.common.git_service import MergeConflictError
from app.common.vector_store import save_embedding
from app.orchestration import delivery, states
from app.task_layer.models import (
    OUTCOME_IMPLEMENTADA,
    OUTCOME_RECUSADA,
    OUTCOME_REVERTIDA,
    DiscardedProposal,
    ImplementedItem,
    Proposal,
    Task,
)

logger = logging.getLogger("pase.orchestration")

APROVAR = "aprovar"
AJUSTAR = "ajustar"
RECUSAR = "recusar"
DECISOES = (APROVAR, AJUSTAR, RECUSAR)


class HomologacaoError(RuntimeError):
    pass


class ComentarioObrigatorioError(HomologacaoError):
    """Risco alto exige justificativa escrita, mesmo para aprovar (SPEC-04 §5)."""


def _exige_comentario(task: Task, decisao: str, comentario: str | None) -> None:
    if decisao in (AJUSTAR, RECUSAR) and not (comentario or "").strip():
        raise HomologacaoError(f"a decisão '{decisao}' exige um comentário")

    # Risco alto pede mais atenção humana: não é RBAC, é obrigar a escrever o porquê.
    if decisao == APROVAR and task.risk_tier == "alto" and not (comentario or "").strip():
        raise ComentarioObrigatorioError(
            "tarefas de risco alto exigem justificativa por escrito mesmo na aprovação"
        )


def encerrar_proposta(session: Session, task: Task, desfecho: str) -> None:
    """Fecha a proposta que originou a tarefa, agora que ela tem desfecho.

    A Memória Histórica indexa o tipo `candidata` como
    `proposals WHERE outcome = 'candidata'`. Sem este fechamento, toda proposta
    já decidida - implementada, recusada ou revertida - continua sendo lembrada
    como "aguardando avaliação", e reenviar a mesma demanda volta barrada com um
    motivo que é factualmente falso.

    Medido: as duas tarefas finalizadas do banco estavam assim, inclusive a que
    havia sido revertida justamente para liberar o pedido.
    """
    if task.proposal_id is None:
        return
    proposta = session.get(Proposal, task.proposal_id)
    if proposta is None:
        return
    proposta.outcome = desfecho
    session.add(proposta)


def aprovar(session: Session, task: Task, comentario: str | None) -> dict:
    """Integra na `develop` e registra o que passou a existir.

    Aprovar na Homologação **não** leva o código à principal. Leva ao ambiente de
    testes; dali, só uma release chega à principal (`delivery`). Foi o que o guia
    de fluxo de ramos mudou: a decisão de revisar o diff e a de publicar são duas.
    """
    mensagem = conventions.merge_de(task.id, task.title, task.module, task.change_type)

    integracao = delivery.integrar_na_develop(session, task, mensagem)
    if not integracao["merged"]:
        # Não avança de estado: o humano precisa resolver e tentar de novo.
        logger.warning("integração da task #%s na develop: %s", task.id, integracao["detail"])
        return integracao
    sha = integracao["commit"]

    item = ImplementedItem(
        title=task.title,
        description=task.description,
        task_id=task.id,
    )
    session.add(item)
    session.flush()
    # Entra na Memória Histórica: a partir de agora, pedir isto de novo é duplicata.
    save_embedding(
        "implemented", item.id, f"{task.title}\n{task.description}", session=session
    )

    # Guardado agora que há coluna para ele: procurar o merge pela mensagem no
    # `git log` funcionava, mas dependia do formato do texto do commit.
    task.merge_commit = sha
    session.add(task)

    encerrar_proposta(session, task, OUTCOME_IMPLEMENTADA)

    states.transicionar(
        session,
        task,
        states.FINALIZADA,
        note=comentario or f"aprovada e integrada na develop em {sha[:8]}",
        alert="none",
        final_outcome="aprovada",
    )
    # Se era uma zona, ela passa a constar como homologada por consequência: o
    # `zona_homologada()` do Task Layer consulta exatamente tasks nesta situação.
    logger.info("task #%s integrada na principal (%s)", task.id, sha[:8])
    return {
        "merged": True,
        "commit": sha,
        "stage": delivery.ESTAGIO_DEVELOP,
        "implemented_item_id": item.id,
    }


def ajustar(session: Session, task: Task, comentario: str) -> dict:
    """Devolve para o Executor com o pedido do gestor, na mesma branch."""
    states.transicionar(
        session, task, states.EM_EXECUCAO, note=f"ajuste pedido: {comentario}", alert="none"
    )
    return {"ajuste": True}


def registrar_descarte(session: Session, task: Task, motivo: str) -> DiscardedProposal:
    """Grava o descarte humano, com embedding, no Histórico de Tarefas Descartadas.

    É o que faz a Memória Histórica barrar a mesma demanda depois. Usado ao recusar
    na Homologação e ao cancelar uma tarefa que o gestor não quer mais.
    """
    descarte = DiscardedProposal(
        proposal_id=task.proposal_id,
        task_id=task.id,
        reason_type="recusa_humana",
        reason_text=motivo,
        duplicate_count=1,
    )
    session.add(descarte)
    session.flush()
    save_embedding(
        "discarded", descarte.id, f"{task.title}\n{task.description}", session=session
    )
    return descarte


def recusar(session: Session, task: Task, comentario: str) -> dict:
    """Recusa humana entra no Histórico de Descartes, com embedding.

    A branch fica de pé para auditoria - o trabalho recusado continua
    inspecionável, o que é parte da rastreabilidade do modelo.
    """
    descarte = registrar_descarte(session, task, comentario)

    encerrar_proposta(session, task, OUTCOME_RECUSADA)

    states.transicionar(
        session,
        task,
        states.FINALIZADA,
        note=f"recusada: {comentario}",
        alert="none",
        final_outcome="recusada",
    )
    return {"recusada": True, "discard_id": descarte.id}


def decidir(session: Session, task: Task, decisao: str, comentario: str | None) -> dict:
    if decisao not in DECISOES:
        raise HomologacaoError(f"decisão desconhecida: {decisao}")
    if task.status != states.EM_HOMOLOGACAO:
        raise HomologacaoError(
            f"a task #{task.id} está em '{task.status}', não em homologação"
        )

    _exige_comentario(task, decisao, comentario)

    if decisao == APROVAR:
        return aprovar(session, task, comentario)
    if decisao == AJUSTAR:
        return ajustar(session, task, comentario)
    return recusar(session, task, comentario)


class ReversaoError(RuntimeError):
    """A tarefa não está num estado que permita reverter."""


def reverter(session: Session, task: Task, motivo: str) -> dict:
    """Desfaz o merge de uma tarefa já integrada.

    Existe porque a verificação automática pode passar e o resultado ainda estar
    errado - foi o que aconteceu com uma entrega que compilava, passava nos
    testes e quebrava o app na primeira tela aberta. Quando isso acontece, o
    humano precisa de um caminho de volta que não seja `git` na unha; e como o
    gate humano é um registro (SPEC-00 §3), desfazer também tem que ser.

    Três efeitos, nesta ordem:

    1. um commit de revert na principal - o histórico passa a contar que o
       código entrou **e** que foi desfeito, em vez de fingir que nunca entrou;
    2. a baixa em `implemented_items`, senão a Memória Histórica continuaria
       tratando como duplicata o pedido de algo que não existe mais;
    3. `final_outcome=revertida`, que é diferente de `recusada` - recusada nunca
       chegou a entrar.

    A tarefa **não** volta para a fila automaticamente. Reverter é constatar que
    a entrega estava errada; decidir tentar de novo é outra decisão, e ela
    continua sendo de uma pessoa.
    """
    if task.status != states.FINALIZADA or task.final_outcome != "aprovada":
        raise ReversaoError(
            f"só dá para reverter tarefa finalizada e aprovada; "
            f"a task #{task.id} está em '{task.status}' ({task.final_outcome})"
        )

    if not (motivo or "").strip():
        raise ReversaoError("reverter exige motivo por escrito")

    sha_merge = task.merge_commit or git_service.merge_commit_da_task(task.id)
    if not sha_merge:
        raise ReversaoError(
            f"não encontrei o commit de merge da task #{task.id} na branch principal"
        )

    try:
        if task.stage is None:
            # Anterior ao fluxo de releases: entrou direto na principal.
            sha_revert = git_service.reverter_merge(
                sha_merge, f"revert: desfaz {task.title} (task #{task.id})\n\n{motivo}"
            )
        else:
            # Entrou na develop (e talvez numa release): sai de lá, no estágio certo.
            try:
                sha_revert = delivery.desfazer_na_entrega(session, task, motivo)
            except delivery.EntregaError as exc:
                raise ReversaoError(str(exc)) from exc
    except MergeConflictError as exc:
        task.alert = "merge_conflict"
        session.add(task)
        logger.warning("revert da task #%s em conflito: %s", task.id, exc)
        return {"revertida": False, "alert": "merge_conflict", "detail": str(exc)}

    # Sai da memória: pedir de novo tem que voltar a ser um pedido legítimo.
    removidos = (
        session.query(ImplementedItem).filter(ImplementedItem.task_id == task.id).delete()
    )

    encerrar_proposta(session, task, OUTCOME_REVERTIDA)
    # O que a tarefa mudaria no contexto deixou de ser verdade.
    context_suggestions.obsoletar_da_tarefa(session, task.id)

    task.alert = "none"
    states.registrar_desfecho(
        session, task, "revertida", note=f"revertida em {sha_revert[:8]}: {motivo}"
    )

    logger.info(
        "task #%s revertida (merge %s desfeito em %s, %s item(ns) fora da memória)",
        task.id,
        sha_merge[:8],
        sha_revert[:8],
        removidos,
    )
    return {
        "revertida": True,
        "merge_revertido": sha_merge,
        "commit": sha_revert,
        "itens_removidos": removidos,
    }
