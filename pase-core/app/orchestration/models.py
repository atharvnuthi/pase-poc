"""Tabelas da Orquestração e da Execução.

`tasks` e `task_state_history` moram em `task_layer/models.py`, onde nasceram.
Mudanças de esquema são migrações Alembic (ver `alembic/versions/`).
"""

from datetime import datetime

from sqlalchemy import (
    JSON,
    Boolean,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.common.db import Base
from app.common.models import utcnow

TRIGGERS = ("inicial", "retry", "ajuste", "replanejamento")
RUN_STATUS = ("sucesso", "falha", "interrompida_budget")
SEVERIDADES = ("baixo", "medio", "alto")


class PlanningDocument(Base):
    """Documento de Planejamento Técnico - o artefato do estágio de Design.

    Fica separado da execução de propósito: é o "plan mode antes de código"
    (SPEC-08 §3). Nunca se escreve código sem um plano registrado e revisável.
    """

    __tablename__ = "planning_documents"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    task_id: Mapped[int] = mapped_column(ForeignKey("tasks.id"), index=True)
    #: Como uma pessoa usando o produto percebe que a tarefa funciona. Definidos
    #: **antes** do código e conferidos por um revisor independente depois - o
    #: que faltou na tarefa #4, cujos testes provavam o mecanismo e não o efeito.
    acceptance_criteria: Mapped[list] = mapped_column(JSON, default=list)
    #: Caminhos previstos. Continua uma lista simples porque dependências por
    #: arquivo, conflito de execução e desvio do plano comparam conjuntos dela.
    affected_files: Mapped[list] = mapped_column(JSON, default=list)
    #: Mapeamento de impacto: caminho → `modificar` | `criar` | `excluir`.
    #: Caminho previsto sem entrada aqui vale como `modificar`.
    file_actions: Mapped[dict] = mapped_column(JSON, default=dict)
    roadmap: Mapped[str] = mapped_column(Text)
    tokens_estimated: Mapped[int] = mapped_column(Integer, default=0)
    #: Estimativa de tempo de execução, em minutos. Artefato de planejamento,
    #: como a de tokens - nunca teto.
    minutes_estimated: Mapped[int | None] = mapped_column(Integer, nullable=True)
    #: Risco técnico da mudança (`baixo` | `medio` | `alto`) e o porquê em uma frase.
    technical_risk: Mapped[str | None] = mapped_column(String(8), nullable=True)
    technical_risk_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    #: Troca com o modelo que produziu o plano (P4), em JSONL. Entra no
    #: transcript de cada execução, para o pacote de homologação ter tudo.
    transcript_path: Mapped[str | None] = mapped_column(String(512), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class ExecutionRun(Base):
    """Uma tentativa do Executor, com tudo que ela produziu.

    `deviation_files` guarda os arquivos tocados fora do que o planejamento
    previa. Não bloqueiam a execução - o SPEC-00 §7 dá essa liberdade ao
    Executor -, mas aparecem destacados na Homologação para o humano comparar
    o planejado com o executado.
    """

    __tablename__ = "execution_runs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    task_id: Mapped[int] = mapped_column(ForeignKey("tasks.id"), index=True)
    attempt: Mapped[int] = mapped_column(Integer, default=1)
    trigger: Mapped[str] = mapped_column(String(16), default="inicial")
    status: Mapped[str] = mapped_column(String(24), index=True)
    failure_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    deviation_files: Mapped[list] = mapped_column(JSON, default=list)
    tokens_real: Mapped[int] = mapped_column(Integer, default=0)
    duration_ms: Mapped[int] = mapped_column(Integer, default=0)
    diff_path: Mapped[str | None] = mapped_column(String(512), nullable=True)
    log_path: Mapped[str | None] = mapped_column(String(512), nullable=True)
    transcript_path: Mapped[str | None] = mapped_column(String(512), nullable=True)
    #: Parecer da revisão independente (P12), com evidência por critério.
    review_path: Mapped[str | None] = mapped_column(String(512), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class Incident(Base):
    """Incidente operacional - dá ao Fator de Urgência algo real para ler (SPEC-04 §2).

    `source=sentry_stub` marca que nesta PoC a inserção é manual pelo painel; em
    produção viria de uma integração real.
    """

    __tablename__ = "incidents"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    title: Mapped[str] = mapped_column(String(200))
    description: Mapped[str] = mapped_column(Text, default="")
    severity: Mapped[str] = mapped_column(String(16), index=True)
    module: Mapped[str | None] = mapped_column(String(32), nullable=True, index=True)
    source: Mapped[str] = mapped_column(String(16), default="manual")
    resolved: Mapped[bool] = mapped_column(Boolean, default=False)
    task_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


#: Origem de uma aresta do grafo de dependências.
DEP_ARQUIVO = "arquivo"       # detectada por sobreposição de affected_files
DEP_SEMANTICA = "semantica"   # propostas parecidas (embedding); não bloqueia
DEP_MANUAL = "manual"         # criada por uma pessoa no painel

ORIGENS_DE_DEPENDENCIA = (DEP_ARQUIVO, DEP_SEMANTICA, DEP_MANUAL)


class TaskDependency(Base):
    """Uma aresta do grafo: `task_id` depende de `depends_on_task_id`.

    Substitui o `waiting_on_task_id` - um escalar que só guardava o último
    bloqueio detectado e era recalculado a cada despacho. Um escalar não é um
    grafo: não dá para ter duas dependências, nem saber de onde cada uma veio,
    nem desenhar arestas.

    `kind` guarda a **origem** da aresta, e isso importa na hora de decidir o que
    pode ser apagado automaticamente: as de `arquivo` são recalculadas pelo
    sistema a cada despacho, enquanto as `manual` são decisão de uma pessoa e
    nenhum recálculo tem o direito de remover.
    """

    __tablename__ = "task_dependencies"
    __table_args__ = (
        UniqueConstraint("task_id", "depends_on_task_id", name="uq_dependencia"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    task_id: Mapped[int] = mapped_column(ForeignKey("tasks.id"), index=True)
    depends_on_task_id: Mapped[int] = mapped_column(ForeignKey("tasks.id"), index=True)
    kind: Mapped[str] = mapped_column(String(16), default=DEP_ARQUIVO, index=True)
    reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


RELEASE_STATUS = ("aberta", "validando", "validada", "pr_aberto", "publicada", "cancelada")


class Release(Base):
    """Uma `release/x.x.x`: a composição de uma versão a publicar.

    É o único caminho para a branch principal. Tarefa aprovada nos testes entra
    aqui por merge direto; a release inteira entra na principal por um PR que uma
    pessoa aprova (`engineering-guidelines` §3 do contexto, guia de fluxo de ramos).
    """

    __tablename__ = "releases"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    version: Mapped[str] = mapped_column(String(16), unique=True)
    branch: Mapped[str] = mapped_column(String(32))
    status: Mapped[str] = mapped_column(String(16), default="aberta", index=True)
    changelog: Mapped[str] = mapped_column(Text, default="")
    #: Resultado da última validação final (suítes completas na branch da release).
    validation_ok: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    validation_log_path: Mapped[str | None] = mapped_column(String(512), nullable=True)
    pr_number: Mapped[int | None] = mapped_column(Integer, nullable=True)
    pr_url: Mapped[str | None] = mapped_column(String(512), nullable=True)
    pr_body: Mapped[str | None] = mapped_column(Text, nullable=True)
    approval_note: Mapped[str | None] = mapped_column(Text, nullable=True)
    publish_commit: Mapped[str | None] = mapped_column(String(40), nullable=True)
    tag: Mapped[str | None] = mapped_column(String(16), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class PipelineEvent(Base):
    """Rastro do fluxo de branches: o que entrou onde, quando, e se o CI passou.

    O guia exige rastreabilidade das integrações e que falha de pipeline bloqueie
    novas integrações. Sem um registro, "o último CI da develop passou?" só teria
    resposta olhando o git.
    """

    __tablename__ = "pipeline_events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    #: `develop`, `release/x.x.x` ou `main`.
    branch: Mapped[str] = mapped_column(String(48), index=True)
    #: integracao | ci | reversao | release | publicacao | tag
    kind: Mapped[str] = mapped_column(String(16), index=True)
    ok: Mapped[bool] = mapped_column(Boolean, default=True)
    task_id: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)
    release_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    commit: Mapped[str | None] = mapped_column(String(40), nullable=True)
    detail: Mapped[str] = mapped_column(Text, default="")
    log_path: Mapped[str | None] = mapped_column(String(512), nullable=True)
    at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
