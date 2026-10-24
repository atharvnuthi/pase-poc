"""Eventos internos via Postgres LISTEN/NOTIFY (SPEC-01 §6, SPEC-06 §1).

O painel consome isto por SSE - ele reage a eventos reais do sistema em vez de
perguntar em loop. Não há broker externo: o banco que já é a fonte da verdade
também é o canal.

    publish("task.updated", {"task_id": 7, "status": "em_execucao"})
    for event in listen(timeout=15):
        ...
"""

from __future__ import annotations

import json
import logging
from collections.abc import Callable, Iterator
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

import psycopg
from sqlalchemy import text as sql_text
from sqlalchemy.orm import Session

from app.common.config import settings

logger = logging.getLogger("pase.events")

#: Canal único do sistema. O roteamento fino acontece no campo `type` do payload.
CHANNEL = "pase_events"

#: pg_notify trunca acima de ~8000 bytes; eventos carregam referências, não objetos.
MAX_PAYLOAD_BYTES = 7000


@dataclass
class Event:
    type: str
    payload: dict[str, Any] = field(default_factory=dict)
    at: str = ""

    def to_json(self) -> str:
        return json.dumps(
            {"type": self.type, "payload": self.payload, "at": self.at},
            ensure_ascii=False,
            default=str,
        )

    @classmethod
    def from_json(cls, raw: str) -> Event:
        data = json.loads(raw)
        return cls(type=data["type"], payload=data.get("payload", {}), at=data.get("at", ""))


def raw_dsn() -> str:
    """DATABASE_URL no formato aceito pelo psycopg (sem o driver do SQLAlchemy)."""
    return settings.database_url.replace("postgresql+psycopg://", "postgresql://")


def publish(
    event_type: str,
    payload: dict[str, Any] | None = None,
    *,
    session: Session | None = None,
) -> Event:
    """Publica um evento. Com `session`, só chega aos ouvintes após o commit dela."""
    event = Event(
        type=event_type,
        payload=payload or {},
        at=datetime.now(UTC).isoformat(),
    )
    body = event.to_json()
    if len(body.encode("utf-8")) > MAX_PAYLOAD_BYTES:
        raise ValueError(
            f"payload de evento grande demais ({event_type}): "
            "envie referências (ids) e deixe o painel buscar o detalhe"
        )

    statement = sql_text("SELECT pg_notify(:channel, :body)")
    params = {"channel": CHANNEL, "body": body}

    if session is not None:
        session.execute(statement, params)
    else:
        from app.common.db import session_scope

        with session_scope() as own:
            own.execute(statement, params)

    logger.info("evento publicado: %s", event_type)
    return event


def listen(
    *,
    timeout: float | None = None,
    stop_after: int | None = None,
    on_ready: Callable[[], None] | None = None,
) -> Iterator[Event | None]:
    """Gerador bloqueante de eventos, em conexão própria (LISTEN dedicado).

    - `timeout`: a cada janela sem evento o gerador devolve `None`, um tique de
      keep-alive que o SSE usa para manter a conexão viva. Sem `timeout`, bloqueia
      indefinidamente e nunca devolve `None`.
    - `stop_after`: encerra depois de N eventos (usado nos testes).
    - `on_ready`: chamado uma vez, logo após o LISTEN estar ativo - evita corrida
      entre assinar e publicar.
    """
    received = 0
    with psycopg.connect(
        raw_dsn(), autocommit=True, connect_timeout=settings.db_connect_timeout
    ) as conn:
        conn.execute(f'LISTEN "{CHANNEL}"')
        if on_ready is not None:
            on_ready()

        while True:
            for notify in conn.notifies(timeout=timeout):
                try:
                    event = Event.from_json(notify.payload)
                except (json.JSONDecodeError, KeyError):
                    logger.warning("notificação ignorada, payload inválido: %r", notify.payload)
                    continue
                yield event
                received += 1
                if stop_after is not None and received >= stop_after:
                    return

            if timeout is None:
                return  # sem timeout, o gerador só termina se a conexão cair
            yield None  # janela vencida sem evento
