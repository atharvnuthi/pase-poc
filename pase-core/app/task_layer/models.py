"""Tabelas do Task Layer (SPEC-03 §6) e a tabela `tasks` (SPEC-04 §1).

Sobre `tasks`: ela é especificada no SPEC-04, mas nasce aqui - é o Task Layer
que cria a Tarefa Candidata. O esquema completo da tabela mora aqui, e as
migrações Alembic (`alembic/versions/`) o evoluem; o Task Layer preenche apenas
os campos que lhe cabem.
"""

from datetime import datetime

from sqlalchemy import JSON, Boolean, DateTime, Float, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.common.db import Base
from app.common.models import utcnow
from app.common.vector_store import EmbeddingVector

# --------------------------------------------------------------------------- #
# Vocabulário canônico (SPEC-00 §8) - nunca usar sinônimos destes valores
# --------------------------------------------------------------------------- #

ORIGENS = ("external", "internal", "passiva", "ai", "auditoria", "reavaliacao")
MODULOS = ("dashboard", "transacoes", "relatorios", "orcamentos", "metas", "suporte", "geral")
OUTPUT_TYPES = ("codigo_permanente", "zona_dinamica")
RISK_TIERS = ("baixo", "medio", "alto")

OUTCOME_CANDIDATA = "candidata"
OUTCOME_DUPLICATA = "descartada_duplicata"
OUTCOME_INCOERENTE = "descartada_incoerente"
OUTCOME_REDIRECIONADA = "redirecionada_zona"

#: Desfechos terminais da proposta, gravados quando a tarefa que ela originou
#: acaba. Existem porque a Memória Histórica indexa `candidata` como
#: "proposals WHERE outcome = 'candidata'": sem fechar a proposta, tudo que
#: já foi decidido continua sendo lembrado como "aguardando avaliação".
OUTCOME_IMPLEMENTADA = "implementada"
OUTCOME_RECUSADA = "recusada_pelo_humano"
OUTCOME_REVERTIDA = "revertida"

REASON_DUPLICATA = "duplicata"
REASON_INCOERENTE = "incoerente"
REASON_RECUSA_HUMANA = "recusa_humana"


class Proposal(Base):
    """Ideia bruta captada, de qualquer origem (SPEC-00 §2)."""

    __tablename__ = "proposals"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    origin: Mapped[str] = mapped_column(String(16), index=True)
    type: Mapped[str | None] = mapped_column(String(16), nullable=True)
    raw_text: Mapped[str] = mapped_column(Text)
    user_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    author: Mapped[str | None] = mapped_column(String(128), nullable=True)

    title: Mapped[str | None] = mapped_column(String(200), nullable=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    module: Mapped[str | None] = mapped_column(String(32), nullable=True, index=True)
    output_type: Mapped[str | None] = mapped_column(String(32), nullable=True)

    embedding: Mapped[list[float] | None] = mapped_column(EmbeddingVector, nullable=True)
    outcome: Mapped[str | None] = mapped_column(String(32), nullable=True, index=True)
    #: Quantos pedidos esta proposta representa. Nasce com o tamanho do grupo do
    #: P0a (três tickets sobre a mesma dor são uma proposta com peso três) e cresce
    #: quando uma duplicata bate nela enquanto é candidata ou está em andamento.
    occurrences: Mapped[int] = mapped_column(Integer, default=1, server_default="1")
    #: A resposta dada a quem pediu, na hora em que o funil decidiu. É o que o
    #: FinTrack mostra de volta ao usuário (`GET /api/proposals/mine`).
    feedback: Mapped[str | None] = mapped_column(Text, nullable=True)

    # rastreabilidade: a proposta reaberta pela Reavaliação Cíclica aponta para o descarte
    source_discard_id: Mapped[int | None] = mapped_column(Integer, nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class DiscardedProposal(Base):
    """Histórico de Descartes - memória do que o sistema já recusou e por quê.

    Duplicatas não entram na memória: somam o peso delas (`Proposal.occurrences`)
    ao `duplicate_count` da linha que casou. A duplicata ganha só uma linha de
    auditoria, sem embedding. Esse contador é o sinal de recorrência que o
    Avaliador de Zonas lê.
    """

    __tablename__ = "discarded_proposals"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    proposal_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    task_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    reason_type: Mapped[str] = mapped_column(String(24), index=True)
    reason_text: Mapped[str] = mapped_column(Text)
    #: Trecho literal do contexto que o P2a disse ter sido violado, já conferido
    #: por código contra os documentos que ele recebeu. Só existe em incoerência.
    cited_excerpt: Mapped[str | None] = mapped_column(Text, nullable=True)
    matched_ref: Mapped[str | None] = mapped_column(String(128), nullable=True)
    duplicate_count: Mapped[int] = mapped_column(Integer, default=1)
    duplicate_refs: Mapped[list] = mapped_column(JSON, default=list)
    embedding: Mapped[list[float] | None] = mapped_column(EmbeddingVector, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class ImplementedItem(Base):
    """O que o produto já faz. É contra isto que a Memória Histórica compara."""

    __tablename__ = "implemented_items"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    title: Mapped[str] = mapped_column(String(200))
    description: Mapped[str] = mapped_column(Text)
    embedding: Mapped[list[float] | None] = mapped_column(EmbeddingVector, nullable=True)
    task_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    duplicate_count: Mapped[int] = mapped_column(Integer, default=1)
    duplicate_refs: Mapped[list] = mapped_column(JSON, default=list)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class Task(Base):
    """Tarefa Candidata e seu ciclo de vida (schema completo do SPEC-04 §1)."""

    __tablename__ = "tasks"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    proposal_id: Mapped[int | None] = mapped_column(ForeignKey("proposals.id"), nullable=True)

    title: Mapped[str] = mapped_column(String(200))
    description: Mapped[str] = mapped_column(Text)
    module: Mapped[str] = mapped_column(String(32), index=True)
    output_type: Mapped[str] = mapped_column(String(32), default="codigo_permanente")
    #: Tipo da mudança, no vocabulário de `engineering-guidelines` §3 do contexto.
    #: Decide o prefixo da branch e da mensagem de commit do Executor.
    change_type: Mapped[str] = mapped_column(String(16), default="feature")

    impact: Mapped[int] = mapped_column(Integer, default=1)
    complexity: Mapped[int] = mapped_column(Integer, default=1)
    confidence: Mapped[float] = mapped_column(Float, default=0.0)
    uncertainty: Mapped[bool] = mapped_column(Boolean, default=False)
    risk_tier: Mapped[str] = mapped_column(String(16), default="baixo")

    status: Mapped[str] = mapped_column(String(32), default="candidata", index=True)
    final_outcome: Mapped[str | None] = mapped_column(String(16), nullable=True)

    # Campos consumidos pela Orquestração e pela Execução (SPEC-04)
    branch_name: Mapped[str | None] = mapped_column(String(128), nullable=True)
    #: SHA do merge da tarefa na develop. Guardado, e não procurado no `git log` pela
    #: mensagem - foi assim que a reversão teve de ser feita antes de existirem
    #: migrações, e era frágil por depender do formato do texto.
    merge_commit: Mapped[str | None] = mapped_column(String(40), nullable=True)
    pr_url: Mapped[str | None] = mapped_column(String(512), nullable=True)
    pr_number: Mapped[int | None] = mapped_column(Integer, nullable=True)
    waiting_on_task_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    alert: Mapped[str] = mapped_column(String(24), default="none")
    urgency_score: Mapped[float] = mapped_column(Float, default=0.0)
    #: Teto de tokens definido por uma pessoa, sobrepondo o cálculo automático.
    #: Existe porque a estimativa do P4 erra por ordem de grandeza e uma tarefa
    #: legítima pode estourar o piso: sem isto, ela fica suspensa sem recurso.
    budget_cap_tokens: Mapped[int | None] = mapped_column(Integer, nullable=True)
    #: Tarefa da qual esta é uma nova tentativa. Refazer não reabre a anterior -
    #: `finalizada` é terminal - e sim abre outra que sabe por que a primeira falhou.
    parent_task_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    #: O que a pessoa pediu para mudar em relação à tentativa anterior.
    redo_feedback: Mapped[str | None] = mapped_column(Text, nullable=True)
    #: Esta tarefa para depois do planejamento até uma pessoa aprovar o plano.
    #: Decidido na aprovação da candidata: pelo risco, ou à mão.
    plan_approval_required: Mapped[bool] = mapped_column(Boolean, default=False)
    plan_approved: Mapped[bool] = mapped_column(Boolean, default=False)
    #: O que a pessoa pediu para mudar no plano. Vai ao P4 na próxima rodada.
    plan_feedback: Mapped[str | None] = mapped_column(Text, nullable=True)
    #: Onde a entrega está no fluxo de branches: `develop` (em testes), `release`
    #: (numa release ainda não publicada) ou `producao`. `None` antes de a
    #: homologação integrar, e nas tarefas anteriores ao fluxo de releases.
    stage: Mapped[str | None] = mapped_column(String(16), nullable=True, index=True)
    #: Aprovação funcional no ambiente de testes - exigida para entrar numa release.
    tested_ok: Mapped[bool] = mapped_column(Boolean, default=False)
    tested_note: Mapped[str | None] = mapped_column(Text, nullable=True)
    release_id: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)
    release_commit: Mapped[str | None] = mapped_column(String(40), nullable=True)
    #: Arquivada some das listas e do grafo, mas **nada é apagado**: histórico,
    #: execuções, pareceres e artefatos continuam. Apagar de verdade destruiria o
    #: rastro de uma decisão, e o gate humano é um registro (SPEC-00 §3).
    archived_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True, index=True
    )
    archive_note: Mapped[str | None] = mapped_column(Text, nullable=True)
    demo_force_fail_runs: Mapped[int | None] = mapped_column(Integer, nullable=True)
    demo_budget_cap_tokens: Mapped[int | None] = mapped_column(Integer, nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow
    )


class TaskStateHistory(Base):
    """Toda transição de estado vira linha - gate humano é registro (SPEC-00 §3)."""

    __tablename__ = "task_state_history"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    task_id: Mapped[int] = mapped_column(ForeignKey("tasks.id"), index=True)
    from_status: Mapped[str | None] = mapped_column(String(32), nullable=True)
    to_status: Mapped[str] = mapped_column(String(32))
    note: Mapped[str | None] = mapped_column(Text, nullable=True)
    at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
