"""Tabelas que pertencem à infraestrutura comum (SPEC-01).

As tabelas de domínio (proposals, tasks, discarded_proposals, implemented_items,
incidents, zone_payloads...) são definidas pelos SPECs que as introduzem.
"""

from datetime import UTC, datetime

from sqlalchemy import JSON, DateTime, Float, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.common.db import Base


def utcnow() -> datetime:
    return datetime.now(UTC)


class LLMCall(Base):
    """Registro de toda chamada ao LLM - rastreabilidade integral (SPEC-00 §2).

    O trace_id permite religar qualquer decisão do sistema à conversa exata
    que a produziu (SPEC-08 §1).
    """

    __tablename__ = "llm_calls"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    trace_id: Mapped[str] = mapped_column(String(36), index=True)
    kind: Mapped[str] = mapped_column(String(16))  # chat | embed
    provider: Mapped[str] = mapped_column(String(32))
    model: Mapped[str] = mapped_column(String(128))
    temperature: Mapped[float | None] = mapped_column(nullable=True)
    tokens_in: Mapped[int] = mapped_column(Integer, default=0)
    tokens_out: Mapped[int] = mapped_column(Integer, default=0)
    duration_ms: Mapped[int] = mapped_column(Integer, default=0)
    attempts: Mapped[int] = mapped_column(Integer, default=1)
    #: Custo em dólares, calculado na hora da chamada a partir do preço do
    #: modelo. Tokens não são comparáveis entre modelos; dinheiro é - e é o
    #: número que entra no capítulo de validação.
    cost_usd: Mapped[float] = mapped_column(Float, default=0.0)
    tags: Mapped[dict] = mapped_column(JSON, default=dict)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class ContextDocument(Base):
    """Um documento do contexto do produto: escopo, requisitos, guia de engenharia...

    Mora no banco, não no repositório, por três motivos: muda em tempo real sem
    commit nem reinício, cada agente lê só o que precisa em cada etapa do ciclo, e um
    agente futuro pode ser treinado sobre um conjunto versionado e consultável.

    `slug` é o caminho lógico (`scope-and-constraints`, `adrs/0001-...`) e `folder` é o
    primeiro segmento quando há pasta (`adrs`, `design-systems`).
    """

    __tablename__ = "context_documents"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    slug: Mapped[str] = mapped_column(String(160), unique=True, index=True)
    folder: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    title: Mapped[str] = mapped_column(String(200))
    content: Mapped[str] = mapped_column(Text)
    version: Mapped[int] = mapped_column(Integer, default=1)
    updated_by: Mapped[str] = mapped_column(String(64), default="sistema")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow
    )


class ContextDocumentVersion(Base):
    """Toda versão que um documento já teve.

    O sistema decide com base nestes textos (o que cabe no produto, como se escreve
    código). Saber quem mudou o quê, e poder voltar, é parte de poder confiar neles.
    """

    __tablename__ = "context_document_versions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    document_id: Mapped[int] = mapped_column(ForeignKey("context_documents.id"), index=True)
    version: Mapped[int] = mapped_column(Integer)
    content: Mapped[str] = mapped_column(Text)
    note: Mapped[str] = mapped_column(String(300), default="")
    author: Mapped[str] = mapped_column(String(64), default="sistema")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class ContextSuggestion(Base):
    """Uma mudança que a IA sugere num documento de contexto, esperando uma pessoa.

    Nasce quando uma tarefa é aprovada: o que passou a existir pode ter deixado um
    documento desatualizado. A sugestão guarda a versão do documento sobre a qual foi
    feita (`base_version`); se o documento mudou desde então, aceitar seria sobrescrever
    uma edição, e a aceitação é recusada.
    """

    __tablename__ = "context_suggestions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    task_id: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)
    slug: Mapped[str] = mapped_column(String(160), index=True)
    base_version: Mapped[int] = mapped_column(Integer)
    summary: Mapped[str] = mapped_column(String(300), default="")
    reasoning: Mapped[str] = mapped_column(Text, default="")
    content: Mapped[str] = mapped_column(Text)
    diff: Mapped[str] = mapped_column(Text, default="")
    #: pendente | aceita | dispensada | obsoleta
    status: Mapped[str] = mapped_column(String(16), default="pendente", index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    decided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
