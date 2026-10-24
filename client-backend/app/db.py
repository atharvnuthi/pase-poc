"""Banco do FinTrack - SQLite (SPEC-02 §1).

O caminho vem de FINTRACK_DB_URL para que a suíte de testes (rede de regressão
do Executor) rode num arquivo temporário, sem tocar os dados do seed.
"""

import os
from collections.abc import Iterator
from pathlib import Path

from sqlmodel import Session, SQLModel, create_engine

DEFAULT_DB_PATH = Path(__file__).resolve().parent.parent / "data" / "fintrack.db"


def database_url() -> str:
    url = os.getenv("FINTRACK_DB_URL")
    if url:
        return url
    DEFAULT_DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    return f"sqlite:///{DEFAULT_DB_PATH}"


engine = create_engine(
    database_url(),
    echo=False,
    # o uvicorn atende requisições em threads diferentes da que abriu a conexão
    connect_args={"check_same_thread": False},
)


def init_db() -> None:
    from app import models  # noqa: F401  (registra as tabelas no metadata)

    SQLModel.metadata.create_all(engine)


def get_session() -> Iterator[Session]:
    with Session(engine) as session:
        yield session
