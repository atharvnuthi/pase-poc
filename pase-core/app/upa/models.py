"""Tabelas do UPA (SPEC-05 §2).

Quatro observações de naturezas diferentes:
- `telemetry_events`: o que o usuário faz na interface;
- `zone_payloads`: como a interface foi personalizada para ele, e quem desfez;
- `zone_violations`: o que o core ou o cliente recusou;
- `zone_evaluations`: o que o agente viu, o que decidiu e por quê.
"""

from datetime import datetime

from sqlalchemy import JSON, Boolean, DateTime, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.common.db import Base
from app.common.models import utcnow

#: Quem revogou um payload. Só a revogação pela própria pessoa é durável (ver `rule`).
REVOGADO_PELO_USUARIO = "usuario"
REVOGADO_PELO_PAINEL = "painel"
#: Um pedido novo da pessoa tomou o lugar do payload.
SUBSTITUIDO_POR_PEDIDO = "pedido"

#: Onde a violação foi detectada.
VIOLACAO_NO_CLIENTE = "cliente"
VIOLACAO_NO_SERVIDOR = "servidor"


class TelemetryEvent(Base):
    """Observação de uso da interface - alimenta só a personalização (SPEC-03 §2).

    Deliberadamente separada do Task Layer: telemetria nunca vira tarefa de
    código, e ticket de suporte nunca vira personalização. São dois canais.
    """

    __tablename__ = "telemetry_events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(Integer, index=True)
    event: Mapped[str] = mapped_column(String(64), index=True)
    path: Mapped[str] = mapped_column(String(256), index=True)
    at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, index=True)


class ZonePayload(Base):
    """Configuração ativa de uma Zona Dinâmica para um usuário (SPEC-05 §2).

    Guarda **propriedades**, nunca código. O `payload` é um objeto que já passou
    (ou, em `origin=injetado`, deliberadamente não passou) pela validação contra
    o contrato canônico - e que o cliente valida de novo antes de renderizar.
    """

    __tablename__ = "zone_payloads"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(Integer, index=True)
    slot: Mapped[str] = mapped_column(String(64), index=True)
    payload: Mapped[dict] = mapped_column(JSON)
    origin: Mapped[str] = mapped_column(String(16), default="autonoma")
    status: Mapped[str] = mapped_column(String(16), default="ativo", index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    #: usuario | painel | pedido. Nulo enquanto o payload está ativo.
    revoked_by: Mapped[str | None] = mapped_column(String(16), nullable=True)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class ZoneViolation(Base):
    """Payload recusado por uma das duas validações (SPEC-05 §5.4).

    A existência desta tabela é o que torna a defesa em profundidade auditável:
    sem ela, um payload malformado simplesmente sumiria no fallback e ninguém
    saberia que houve tentativa. `origem` diz qual das duas camadas o barrou: o
    core antes de persistir (`servidor`) ou o cliente antes de renderizar (`cliente`).
    """

    __tablename__ = "zone_violations"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(Integer, index=True)
    slot: Mapped[str] = mapped_column(String(64), index=True)
    reason: Mapped[str] = mapped_column(Text)
    raw_payload: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    origem: Mapped[str] = mapped_column(
        String(16), default=VIOLACAO_NO_CLIENTE, server_default=VIOLACAO_NO_CLIENTE
    )
    at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, index=True)


class ZoneEvaluation(Base):
    """Uma avaliação de zona para um usuário, qualquer que tenha sido o resultado.

    Duas funções. A primeira é de custo: impede que uma zona que o P6 recusa seja
    reavaliada a cada visita. A segunda é de auditoria (SPEC-05 §7): os sinais que o
    agente recebeu, o que ele decidiu, por quê, e o payload que saiu - sem depender
    do log, que some.
    """

    __tablename__ = "zone_evaluations"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(Integer, index=True)
    slot: Mapped[str] = mapped_column(String(64), index=True)
    #: personalizou | recusou | fora_do_contrato | pedido | pedido_recusado |
    #: pedido_fora_do_contrato
    resultado: Mapped[str] = mapped_column(String(24))
    #: O resumo de comportamento exatamente como foi ao P6.
    sinais: Mapped[str | None] = mapped_column(Text, nullable=True)
    #: O texto da pessoa, quando a avaliação veio de um pedido.
    pedido: Mapped[str | None] = mapped_column(Text, nullable=True)
    #: O que o modelo decidiu (`personalize`), antes da validação do contrato.
    decisao: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    #: O `motivo` do P6, ou os erros de contrato quando o core recusou o payload.
    motivo: Mapped[str | None] = mapped_column(Text, nullable=True)
    # Sem chave estrangeira, de propósito: a auditoria não pode impedir que um
    # payload ou uma violação sejam apagados (o reset das demos apaga).
    payload_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    violation_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    trace_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, index=True)
