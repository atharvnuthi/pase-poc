"""API do FinTrack - o produto-alvo que o PASE evolui (SPEC-02).

A superfície desta API é contrato congelado desde a primeira versão: o Executor do PASE a
edita de forma autônoma e depende de `tests/test_api.py` como rede de regressão.
"""

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.budgets import router as budgets_router
from app.db import init_db
from app.goals import router as goals_router
from app.insights import router as insights_router
from app.routes import router


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    yield


app = FastAPI(title="FinTrack API", version="1.0.0", lifespan=lifespan)

# PoC local, sem autenticação (README.md).
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://localhost:3001"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(router)
app.include_router(budgets_router)
app.include_router(goals_router)
app.include_router(insights_router)


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok", "service": "client-backend"}
