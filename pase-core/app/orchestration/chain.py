"""Cadeia pós-aprovação (SPEC-04 §4) e política de falhas (§7).

Roda em `BackgroundTasks`: a aprovação responde na hora e o trabalho segue
atrás. O painel acompanha por SSE, lendo os eventos que cada transição publica.

Nenhuma etapa aqui espera input humano. Gate humano é estado registrado na
tabela (`candidata`, `em_homologacao`, `suspensa`), nunca processo bloqueado -
o sistema continua tocando outras tarefas enquanto uma espera (SPEC-00 §3).

Tarefas liberadas juntas rodam juntas (monografia §4.4.2): cada uma numa thread
própria, com a sua sessão de banco. O que impede duas de mexerem nos mesmos
arquivos é a decisão de despacho, tomada uma de cada vez e já gravada como
`em_execucao` antes da próxima ser decidida.
"""

from __future__ import annotations

import logging
import threading

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.common.config import settings
from app.common.db import session_scope
from app.execution import budget, executor, planning
from app.orchestration import dependencies, redo, states, suspensao
from app.orchestration.models import ExecutionRun, PlanningDocument
from app.task_layer.models import Task, TaskStateHistory

logger = logging.getLogger("pase.orchestration")

#: Estados em que uma tarefa segura os arquivos que está mexendo.
OCUPANDO_ARQUIVOS = (states.EM_EXECUCAO, states.EM_HOMOLOGACAO)

#: Uma decisão de despacho por vez, no processo inteiro. Duas tarefas liberadas
#: juntas e disputando os mesmos arquivos só se enxergam se a primeira já constar
#: como `em_execucao` quando a segunda for decidida - e duas transações paralelas
#: não veem o que a outra ainda não commitou. O pase-core roda num processo só,
#: então uma trava de thread basta. Segura apenas a decisão, nunca a execução.
_DESPACHO = threading.Lock()


def _plano_de(session: Session, task_id: int) -> PlanningDocument | None:
    return session.execute(
        select(PlanningDocument)
        .where(PlanningDocument.task_id == task_id)
        .order_by(PlanningDocument.id.desc())
        .limit(1)
    ).scalar_one_or_none()


def _proxima_tentativa(session: Session, task_id: int) -> int:
    runs = session.execute(
        select(ExecutionRun).where(ExecutionRun.task_id == task_id)
    ).scalars().all()
    return len(runs) + 1


def conflito_de_arquivos(session: Session, task: Task, plano: PlanningDocument) -> Task | None:
    """Alguma tarefa em andamento já está mexendo nos mesmos arquivos?

    Sem sub-DAG nem replanejamento (fora do escopo da PoC): a segunda tarefa simplesmente
    espera a primeira sair de cena.
    """
    previstos = set(plano.affected_files or [])
    if not previstos:
        return None

    em_andamento = session.execute(
        select(Task).where(Task.status.in_(OCUPANDO_ARQUIVOS)).where(Task.id != task.id)
    ).scalars().all()

    for outra in em_andamento:
        outro_plano = _plano_de(session, outra.id)
        if outro_plano and previstos & set(outro_plano.affected_files or []):
            return outra
    return None


def despachar(session: Session, task: Task, plano: PlanningDocument) -> bool:
    """Tenta mandar a tarefa para execução. False se ficou esperando outra.

    As arestas de origem `arquivo` são refeitas aqui, a cada despacho: os planos
    das outras tarefas mudam, e uma dependência por sobreposição de arquivos só
    faz sentido enquanto a sobreposição existe. As arestas manuais e semânticas
    não são tocadas.

    `waiting_on_task_id` continua sendo preenchido para o painel antigo e para as
    métricas, mas agora é **derivado** do grafo, não a fonte da verdade.
    """
    dependencies.recalcular_por_arquivo(session, task, plano)
    pendentes = dependencies.bloqueadoras(session, task.id)

    task.waiting_on_task_id = pendentes[0].id if pendentes else None
    session.add(task)
    session.flush()

    if pendentes:
        logger.info(
            "task #%s aguarda %s",
            task.id,
            ", ".join(f"#{t.id}" for t in pendentes),
        )
        return False

    return True


def tentar_despacho(task_id: int, trigger: str = "inicial") -> bool:
    """Decide se a tarefa vai para execução e, se vai, já a marca `em_execucao`.

    Decisão e marcação na mesma transação, sob `_DESPACHO`, commitadas antes de
    devolver: é o que faz a próxima decisão enxergar esta tarefa ocupando os
    arquivos dela. Só decide quem está em `pronta_para_despacho` - quem já saiu
    desse estado por outro caminho (cancelada, suspensa, despachada por outra
    liberação simultânea) não é despachada de novo.

    Se quem ela espera está suspensa, a tarefa é suspensa junto (§4.4.3).
    """
    with _DESPACHO, session_scope() as session:
        task = session.get(Task, task_id)
        plano = _plano_de(session, task_id)
        if task is None or plano is None or task.status != states.PRONTA_PARA_DESPACHO:
            return False

        if not despachar(session, task, plano):
            suspensa = suspensao.predecessora_suspensa(session, task_id)
            if suspensa is not None:
                suspensao.suspender_por_predecessora(session, task, suspensa.id)
            return False

        states.transicionar(session, task, states.EM_EXECUCAO, note=f"run {trigger}")
        return True


def _ligar_por_semantica(session: Session, task: Task) -> None:
    """Arestas semânticas da tarefa que acabou de ficar pronta (§4.4.2).

    Num savepoint: a aresta é informativa, e uma falha ao calculá-la não pode
    desfazer a transição para `pronta_para_despacho` que vem junto.
    """
    try:
        with session.begin_nested():
            ligadas = dependencies.ligar_por_semantica(session, task)
        if ligadas:
            logger.info(
                "task #%s ligada por semântica a %s",
                task.id,
                ", ".join(f"#{i}" for i in ligadas),
            )
    except Exception as exc:  # pragma: no cover - rede de segurança
        logger.warning("arestas semânticas da task #%s falharam: %s", task.id, exc)


def rodar_cadeia(task_id: int) -> None:
    """Planejamento → despacho → execução. Entrada do BackgroundTasks."""
    try:
        _planejar_e_despachar(task_id)
    except Exception:  # pragma: no cover - rede de segurança do background
        logger.exception("cadeia falhou para a task #%s", task_id)


def rodar_replanejamento(task_id: int) -> None:
    """Refaz plano e workspace de uma tarefa devolvida ao planejamento."""
    try:
        _planejar_e_despachar(task_id, ja_em_planejamento=True)
    except Exception:  # pragma: no cover - rede de segurança do background
        logger.exception("replanejamento falhou para a task #%s", task_id)


def _planejar_e_despachar(task_id: int, *, ja_em_planejamento: bool = False) -> None:
    if not ja_em_planejamento:
        with session_scope() as session:
            task = session.get(Task, task_id)
            nota = (
                f"refazendo a task #{task.parent_task_id}"
                if task.parent_task_id
                else "aprovada pelo gestor"
            )
            states.transicionar(session, task, states.EM_PLANEJAMENTO, note=nota)

    # Falha no planejamento segue a mesma política da execução (§4.4.3): uma
    # retentativa, depois suspensão para decisão humana.
    tentativas = settings.max_retries + 1
    for tentativa in range(1, tentativas + 1):
        desfecho = _planejar(task_id, tentativa, ultima=tentativa == tentativas)
        if desfecho != "refazer":
            break

    if desfecho != states.PRONTA_PARA_DESPACHO:
        return

    trigger = "replanejamento" if ja_em_planejamento else "inicial"
    if tentar_despacho(task_id, trigger):
        rodar_execucao(task_id, trigger=trigger)


def _planejar(task_id: int, tentativa: int, *, ultima: bool) -> str:
    """Uma tentativa de planejamento. Devolve o estado em que a tarefa ficou,
    ou `refazer` quando falhou e ainda cabe outra tentativa."""
    with session_scope() as session:
        task = session.get(Task, task_id)
        try:
            plano = planning.planejar(session, task, historico=redo.historico_de(session, task))
            task.plan_feedback = None  # já foi ouvido; a próxima rodada começa limpa
        except Exception as exc:
            logger.warning(
                "planejamento falhou para a task #%s (tentativa %s): %s", task_id, tentativa, exc
            )
            # Descarta o que a tentativa deixou pela metade antes de registrar.
            session.rollback()
            task = session.get(Task, task_id)
            if task.status != states.EM_PLANEJAMENTO:
                return task.status  # cancelada enquanto planejava
            if not ultima:
                session.add(
                    TaskStateHistory(
                        task_id=task.id,
                        from_status=task.status,
                        to_status=task.status,
                        note=f"planejamento falhou na tentativa {tentativa}, refazendo: {exc}",
                    )
                )
                return "refazer"
            suspensao.suspender(
                session,
                task,
                note=f"planejamento falhou após {tentativa} tentativa(s): {exc}",
                alert="retries",
            )
            return states.SUSPENSA

        # O planejamento pode demorar o bastante para a tarefa ser cancelada em
        # outra requisição. O plano permanece como artefato, mas não a ressuscita.
        session.refresh(task)
        if task.status == states.FINALIZADA:
            logger.info("task #%s cancelada durante o planejamento", task_id)
            return states.FINALIZADA

        # O plano é o ponto mais barato para discordar: ainda não custou
        # execução. Tarefa que exige aprovação para aqui, com o plano à vista.
        if task.plan_approval_required and not task.plan_approved:
            states.transicionar(
                session,
                task,
                states.AGUARDANDO_PLANO,
                note=f"plano pronto ({len(plano.affected_files)} arquivo(s), "
                f"{len(plano.acceptance_criteria)} critério(s)): aguarda aprovação",
            )
            return states.AGUARDANDO_PLANO

        states.transicionar(
            session,
            task,
            states.PRONTA_PARA_DESPACHO,
            note=f"{len(plano.affected_files)} arquivo(s) previstos, "
            f"{plano.tokens_estimated} tokens estimados",
        )
        _ligar_por_semantica(session, task)
        return states.PRONTA_PARA_DESPACHO


def rodar_apos_aprovacao_do_plano(task_id: int) -> None:
    """O plano foi aprovado por uma pessoa: liga por semântica, despacha e executa."""
    try:
        with session_scope() as session:
            task = session.get(Task, task_id)
            if task is not None and task.status == states.PRONTA_PARA_DESPACHO:
                _ligar_por_semantica(session, task)
        if tentar_despacho(task_id, "inicial"):
            rodar_execucao(task_id, trigger="inicial")
    except Exception:  # pragma: no cover - rede de segurança do background
        logger.exception("execução pós-aprovação do plano falhou para a task #%s", task_id)


def rodar_execucao(
    task_id: int, *, trigger: str = "inicial", comentario: str | None = None
) -> None:
    """Uma tentativa do Executor, com a política de falhas do §7 aplicada ao fim."""
    # Transação curta só para marcar `em_execucao`, **commitada antes** do trabalho
    # começar. Se a marcação viajasse junto da run, ela só ficaria visível a outras
    # transações quando a execução terminasse - minutos depois - e a checagem de
    # conflito de arquivos nunca enxergaria uma tarefa em andamento. Foi exatamente
    # o que aconteceu na primeira verificação: duas tarefas mexendo no mesmo
    # `routes.py` rodaram lado a lado.
    with session_scope() as session:
        task = session.get(Task, task_id)
        if _plano_de(session, task_id) is None:
            logger.error("task #%s sem planejamento - execução abortada", task_id)
            return
        if task.status != states.EM_EXECUCAO:
            states.transicionar(session, task, states.EM_EXECUCAO, note=f"run {trigger}")

    with session_scope() as session:
        task = session.get(Task, task_id)
        plano = _plano_de(session, task_id)
        tentativa = _proxima_tentativa(session, task_id)
        # Diz ao guardrail de quem é esta execução: o custo previsto de cada
        # chamada passa a levar em conta as chamadas anteriores da tarefa.
        with budget.tarefa_em_execucao(task_id):
            run = executor.executar(
                session, task, plano, attempt=tentativa, trigger=trigger, comentario=comentario
            )
        status_da_run = run.status
        desvios = list(run.deviation_files or [])
        sem_criterios = run.failure_reason == executor.SEM_CRITERIOS

    _apos_a_run(task_id, status_da_run, desvios, tentativa, sem_criterios=sem_criterios)


def _apos_a_run(
    task_id: int,
    status_run: str,
    desvios: list[str],
    tentativa: int,
    *,
    sem_criterios: bool = False,
) -> None:
    """Política de falhas (SPEC-04 §7)."""
    # A run em curso ainda registra seu resultado após um cancelamento
    # cooperativo, mas não pode reabrir a tarefa nem disparar retry.
    with session_scope() as session:
        task = session.get(Task, task_id)
        if task.status == states.FINALIZADA:
            logger.info("task #%s terminou a run depois de cancelada; resultado ignorado", task_id)
            return

    if status_run == "sucesso":
        with session_scope() as session:
            task = session.get(Task, task_id)
            nota = "pronta para homologação"
            if desvios:
                nota += f" - {len(desvios)} arquivo(s) fora do planejado"
            states.transicionar(session, task, states.EM_HOMOLOGACAO, note=nota, alert="none")
        return

    if status_run == "interrompida_budget":
        with session_scope() as session:
            task = session.get(Task, task_id)
            suspensao.suspender(session, task, note="teto de tokens atingido", alert="budget")
        return

    # Plano sem critério de aceite não melhora com outra tentativa: quem resolve é uma
    # pessoa, replanejando ou editando o plano. Suspende já, sem gastar a retentativa.
    if sem_criterios:
        with session_scope() as session:
            task = session.get(Task, task_id)
            suspensao.suspender(
                session, task, note="plano sem critérios de aceite", alert="retries"
            )
        return

    # falha comum: uma retentativa, depois suspende para decisão humana
    if tentativa <= settings.max_retries:
        logger.info("task #%s: falha na tentativa %s, refazendo", task_id, tentativa)
        rodar_execucao(task_id, trigger="retry")
        return

    with session_scope() as session:
        task = session.get(Task, task_id)
        suspensao.suspender(
            session, task, note=f"falhou após {tentativa} tentativa(s)", alert="retries"
        )


def liberar_quem_esperava(task_id: int) -> list[threading.Thread]:
    """Uma tarefa saiu de cena: quem estava esperando por ela pode andar (§4.2)."""
    with session_scope() as session:
        # Quem tem aresta apontando para esta tarefa - no grafo, não no escalar.
        ids = [t.id for t in dependencies.dependentes(session, task_id)]

    threads = despachar_em_paralelo(ids)
    for t in threads:
        logger.info("%s liberada pela conclusão da #%s", t.name, task_id)
    return threads


def despachar_em_paralelo(ids: list[int]) -> list[threading.Thread]:
    """Despacha cada tarefa liberada e a executa numa thread própria (§4.4.2).

    As decisões são sequenciais (`tentar_despacho`), as execuções não: cada
    tarefa liberada começa sem esperar a anterior terminar. Antes, a segunda
    esperava a execução inteira da primeira - minutos - mesmo sem nada em comum
    com ela.

    Devolve as threads para quem precisar esperar por elas (os testes). Quem
    chama pelo BackgroundTasks não espera: a requisição seguinte não fica presa
    atrás da execução de outra tarefa.
    """
    threads = []
    for outro_id in ids:
        if not tentar_despacho(outro_id, "inicial"):
            continue
        thread = threading.Thread(
            target=_executar_em_segundo_plano,
            args=(outro_id,),
            name=f"task #{outro_id}",
            # Não segura o desligamento do processo: uma execução cortada fica
            # registrada como estava, como já acontecia antes desta mudança.
            daemon=True,
        )
        thread.start()
        threads.append(thread)
    return threads


def _executar_em_segundo_plano(task_id: int) -> None:
    try:
        rodar_execucao(task_id, trigger="inicial")
    except Exception:  # pragma: no cover - rede de segurança da thread
        logger.exception("execução em paralelo falhou para a task #%s", task_id)
