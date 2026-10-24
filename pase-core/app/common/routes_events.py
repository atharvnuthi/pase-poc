"""Stream de eventos para o painel (SPEC-06 §1).

O painel **reage a eventos reais do sistema**, em vez de perguntar em loop. Isso
não é só economia de requisição: um painel que faz polling mostra um retrato
atrasado, e as decisões que ele apresenta - aprovar, homologar, retomar - são
sobre coisas que mudam de estado sozinhas, em background.

Construído sobre o `events.listen()` do SPEC-01, que já devolve tiques de
keep-alive entre eventos: é exatamente o que uma conexão SSE precisa para
sobreviver a proxies e a períodos de silêncio.
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import AsyncIterator

from fastapi import APIRouter, Request
from fastapi.responses import StreamingResponse

from app.common import events

logger = logging.getLogger("pase.events")

router = APIRouter(prefix="/api/events", tags=["events"])

#: Janela de espera do LISTEN. Vencida sem evento, sai um comentário SSE.
KEEPALIVE_SEGUNDOS = 15


def _sse(dados: str, *, evento: str | None = None) -> str:
    prefixo = f"event: {evento}\n" if evento else ""
    return f"{prefixo}data: {dados}\n\n"


async def _fluxo(request: Request) -> AsyncIterator[str]:
    """Ponte entre o LISTEN bloqueante do Postgres e o loop assíncrono do FastAPI."""
    fila: asyncio.Queue[str | None] = asyncio.Queue()
    loop = asyncio.get_running_loop()
    parar = False

    def escutar() -> None:
        # roda numa thread: psycopg LISTEN é bloqueante por natureza
        for evento in events.listen(timeout=KEEPALIVE_SEGUNDOS):
            if parar:
                return
            loop.call_soon_threadsafe(fila.put_nowait, evento.to_json() if evento else None)

    tarefa = loop.run_in_executor(None, escutar)
    yield _sse('{"type": "stream.open"}')

    try:
        while True:
            if await request.is_disconnected():
                break
            try:
                item = await asyncio.wait_for(fila.get(), timeout=KEEPALIVE_SEGUNDOS + 5)
            except TimeoutError:
                yield ": keep-alive\n\n"
                continue

            yield ": keep-alive\n\n" if item is None else _sse(item, evento="pase")
    finally:
        parar = True
        tarefa.cancel()


@router.get("/stream")
async def stream(request: Request) -> StreamingResponse:
    """Eventos do sistema, em Server-Sent Events."""
    return StreamingResponse(
        _fluxo(request),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )
