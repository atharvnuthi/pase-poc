"""Guardrail de custo (SPEC-04 §6.2, SPEC-00 §4).

Isto é um **hook determinístico, não uma recomendação ao modelo**: é código que
impede a chamada de acontecer. A diferença importa - um prompt pedindo economia
ao modelo não é um teto, é um pedido.

O teto é verificado **antes de cada chamada**, nunca depois: descobrir o estouro
com a resposta na mão já significa ter pago por ela.

O consumo é acumulado **por tarefa**, somando todas as runs. Um teto que
reiniciasse a cada tentativa deixaria um retry dobrar o custo, o que anula o
propósito de existir um teto.
"""

from __future__ import annotations

import logging
from collections.abc import Iterator
from contextlib import contextmanager
from contextvars import ContextVar

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.common.config import settings
from app.common.db import session_scope
from app.common.models import LLMCall
from app.orchestration.models import ExecutionRun
from app.task_layer.models import Task

logger = logging.getLogger("pase.execution")

#: A tarefa cuja execução está em curso nesta thread. A Orquestração a declara em
#: volta da chamada ao Executor, e o `BudgetGuard` a lê para medir as chamadas
#: anteriores da mesma tarefa sem que o Executor precise passá-la.
_TAREFA_EM_EXECUCAO: ContextVar[int | None] = ContextVar("pase_tarefa_em_execucao", default=None)


@contextmanager
def tarefa_em_execucao(task_id: int) -> Iterator[None]:
    marca = _TAREFA_EM_EXECUCAO.set(task_id)
    try:
        yield
    finally:
        _TAREFA_EM_EXECUCAO.reset(marca)


class BudgetExcedidoError(RuntimeError):
    """Teto de tokens atingido. A run termina como `interrompida_budget`."""

    def __init__(self, gasto: int, teto: int) -> None:
        super().__init__(f"budget excedido: {gasto} de {teto} tokens")
        self.gasto = gasto
        self.teto = teto


def teto_de(task: Task, plano_tokens_estimated: int) -> int:
    """Teto em tokens para a tarefa inteira.

    `demo_budget_cap_tokens` sobrepõe tudo, inclusive o piso - é o instrumento do
    D5(b), que precisa forçar a interrupção. Em seguida vem `budget_cap_tokens`,
    que é a decisão de uma pessoa no painel.

    Fora do modo demo, o teto tem um piso. A estimativa do P4 é um palpite do
    modelo e erra por ordem de grandeza: na primeira execução real ele estimou
    1200 tokens para uma tarefa cujo prompt de geração sozinho ocupa 8800.
    Sem piso, o guardrail deixaria de proteger contra loop desgovernado e passaria
    a barrar toda tarefa honesta - que é o oposto do que o SPEC-00 §4 pede.

    A estimativa continua sendo registrada em `planning_documents` e exibida ao
    humano: ela é um artefato de planejamento útil, só não serve como teto sozinha.
    """
    if task.demo_budget_cap_tokens is not None:
        return task.demo_budget_cap_tokens

    # Teto posto por uma pessoa vence o cálculo automático, para cima ou para
    # baixo. É o recurso de quem olha uma tarefa suspensa por budget e conclui
    # que ela merece mais - ou menos.
    if task.budget_cap_tokens is not None:
        return task.budget_cap_tokens

    calculado = int(plano_tokens_estimated * (1 + settings.budget_tolerance))
    return max(calculado, settings.budget_min_tokens)


def gasto_da_task(session: Session, task_id: int) -> int:
    total = session.execute(
        select(func.coalesce(func.sum(ExecutionRun.tokens_real), 0)).where(
            ExecutionRun.task_id == task_id
        )
    ).scalar_one()
    return int(total or 0)


class BudgetGuard:
    """Acompanha o consumo de uma run contra o teto da tarefa.

    O custo previsto de cada chamada é o **maior** entre duas estimativas
    (monografia §4.4.3): o tamanho do prompt prestes a ser enviado e o custo da
    chamada mais cara que esta tarefa já fez. O prompt sozinho subestima - não
    conta a saída, nem o raciocínio cobrado como saída, que numa geração de
    código passa da metade do custo. A medição das chamadas anteriores é o que a
    tarefa de fato custa por chamada.

    `maior_chamada` vem, nesta ordem: do argumento; das chamadas já registradas
    da tarefa em `task_id` ou na declarada por `tarefa_em_execucao`; e é
    atualizada a cada `registrar`, para que a própria run alimente a estimativa.
    """

    def __init__(
        self,
        teto: int,
        ja_gasto: int,
        *,
        task_id: int | None = None,
        maior_chamada: int | None = None,
    ) -> None:
        self.teto = teto
        self.ja_gasto = ja_gasto
        self.gasto_na_run = 0
        if maior_chamada is None:
            alvo = task_id if task_id is not None else _TAREFA_EM_EXECUCAO.get()
            maior_chamada = _medir_maior_chamada(alvo) if alvo is not None else 0
        self.maior_chamada = maior_chamada

    @property
    def total(self) -> int:
        return self.ja_gasto + self.gasto_na_run

    def previsto(self, custo_do_prompt: int = 0) -> int:
        """O custo que a próxima chamada deve ter, pelo maior dos dois palpites."""
        return max(custo_do_prompt, self.maior_chamada)

    def checar(self, custo_previsto: int = 0) -> None:
        """Chamado imediatamente antes de cada chamada ao LLM.

        `custo_previsto` é o tamanho estimado do prompt que está para ser
        enviado; o guardrail o compara com o custo das chamadas anteriores da
        tarefa e fica com o maior. A verificação é **preditiva**: pergunta se a
        chamada cabe no que resta, não se o que já foi gasto estourou. A
        diferença é o que faz o guardrail funcionar na primeira chamada - com um
        teto de 100 tokens e nada gasto ainda, olhar só para o passado deixaria
        passar justamente a chamada que não cabe.
        """
        previsto = self.previsto(custo_previsto)
        projetado = self.total + previsto
        if projetado > self.teto:
            logger.warning(
                "budget: %s (gasto) + %s (previsto; prompt %s, maior chamada %s) "
                "excede o teto de %s tokens",
                self.total,
                previsto,
                custo_previsto,
                self.maior_chamada,
                self.teto,
            )
            raise BudgetExcedidoError(projetado, self.teto)

    def registrar(self, usage: dict) -> None:
        custo = int(usage.get("tokens_in", 0)) + int(usage.get("tokens_out", 0))
        self.gasto_na_run += custo
        self.maior_chamada = max(self.maior_chamada, custo)


def _medir_maior_chamada(task_id: int) -> int:
    """`custo_da_maior_chamada` numa sessão própria, que só lê.

    Sem banco, a estimativa volta a ser só o tamanho do prompt: o guardrail
    perde precisão, mas não deixa de existir.
    """
    try:
        with session_scope() as session:
            return custo_da_maior_chamada(session, task_id)
    except Exception as exc:
        logger.warning("não consegui medir as chamadas da task #%s: %s", task_id, exc)
        return 0


def custo_da_maior_chamada(session: Session, task_id: int) -> int:
    """Quanto custou a chamada mais cara já feita por esta tarefa.

    Medição, não palpite: o contexto de uma tarefa é o que é, e a próxima chamada
    vai custar aproximadamente o mesmo que a anterior. É a base para decidir se
    ainda cabe uma.

    Zero quando a tarefa nunca chamou o modelo - não há o que medir, e quem
    pergunta cai no piso.
    """
    maior = session.execute(
        select(func.coalesce(func.max(LLMCall.tokens_in + LLMCall.tokens_out), 0)).where(
            LLMCall.tags["task_id"].as_integer() == task_id
        )
    ).scalar()
    return int(maior or 0)


def cabe_mais_uma_chamada(session: Session, task: Task, teto: int) -> tuple[bool, str]:
    """Sobra folga para pelo menos mais uma chamada ao modelo?

    Existe porque "o gasto ainda não passou do teto" **não** significa que a
    execução consegue começar. Medido: uma tarefa com 35.592 tokens de folga e
    chamadas de ~37.000 produziu duas execuções que morreram em sete segundos,
    com zero tokens gastos - o guardrail do Executor é preditivo e barrava antes
    da primeira chamada, mas nada avisava quem apertou "Retomar".

    Retomar sem folga não é inofensivo: cria uma execução, um registro de falha e
    ruído no histórico, sem chance nenhuma de terminar.
    """
    gasto = gasto_da_task(session, task.id)
    folga = teto - gasto
    precisa = custo_da_maior_chamada(session, task.id) or settings.budget_min_tokens // 4

    if folga >= precisa:
        return True, ""

    return False, (
        f"a tarefa já gastou {gasto:,} de um teto de {teto:,} tokens, e sobram {max(folga, 0):,}. "
        f"A chamada mais cara desta tarefa custou {precisa:,} - retomar agora criaria uma "
        "execução que para antes da primeira chamada. Aumente o teto ou replaneje."
    ).replace(",", ".")
