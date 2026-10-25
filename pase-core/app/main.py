"""Entrada do pase-core - o motor do PASE.

Cria a aplicação FastAPI: aplica as migrações do banco no boot, registra as rotas
do Task Layer, da Orquestração, da entrega, do UPA, das métricas, dos eventos, do
contexto, do sistema e dos jobs, e expõe `/health`.
"""

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.common import context_store
from app.common.config import settings
from app.common.db import migrar, session_scope
from app.common.routes_context import router as context_router
from app.common.routes_events import router as events_router
from app.common.routes_system import router as system_router
from app.jobs.routes import router as jobs_router
from app.metrics.routes import router as metrics_router
from app.orchestration.routes import router as orchestration_router
from app.orchestration.routes_delivery import router as delivery_router
from app.task_layer.routes import router as proposals_router
from app.upa.routes import router as upa_router

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s %(message)s",
)
logger = logging.getLogger("pase.core")


@asynccontextmanager
async def lifespan(app: FastAPI):
    migrar()  # leva o banco até a última revisão do Alembic
    with session_scope() as session:
        context_store.bootstrap(session)  # documentos de contexto que ainda faltam
    logger.info("pase-core pronto (provider=%s)", settings.llm_provider)
    yield


app = FastAPI(title="PASE Core", version="0.1.0", lifespan=lifespan)

# PoC local, sem autenticação: só os dois frontends do projeto (README.md).
app.add_middleware(
    CORSMiddleware,
    allow_origins=list(settings.cors_origins),
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)


app.include_router(proposals_router)
app.include_router(orchestration_router)
app.include_router(delivery_router)
app.include_router(upa_router)
app.include_router(metrics_router)
app.include_router(events_router)
app.include_router(context_router)
app.include_router(system_router)
app.include_router(jobs_router)


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok", "service": "pase-core"}
