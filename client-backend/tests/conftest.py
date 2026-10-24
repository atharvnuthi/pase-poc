"""Fixtures da suíte do FinTrack.

Cada teste roda contra um SQLite temporário e vazio - a rede de regressão do
Executor nunca pode depender do estado do seed nem sujá-lo.
"""

from datetime import date

import pytest
from fastapi.testclient import TestClient
from sqlmodel import Session, SQLModel, create_engine

from app import db as db_module
from app.models import Category, User


@pytest.fixture
def engine(tmp_path):
    engine = create_engine(
        f"sqlite:///{tmp_path / 'test.db'}",
        connect_args={"check_same_thread": False},
    )
    SQLModel.metadata.create_all(engine)
    yield engine
    engine.dispose()


@pytest.fixture
def client(engine, monkeypatch):
    from app.main import app

    monkeypatch.setattr(db_module, "engine", engine)

    def session_de_teste():
        with Session(engine) as session:
            yield session

    app.dependency_overrides[db_module.get_session] = session_de_teste
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()


def _cria(engine, record):
    with Session(engine) as session:
        session.add(record)
        session.commit()
        session.refresh(record)
        return record.id


@pytest.fixture
def ana(engine) -> int:
    return _cria(engine, User(name="Ana"))


@pytest.fixture
def clara(engine) -> int:
    return _cria(engine, User(name="Clara"))


@pytest.fixture
def categoria_alimentacao(engine) -> int:
    return _cria(engine, Category(name="Alimentação"))


@pytest.fixture
def categoria_transporte(engine) -> int:
    return _cria(engine, Category(name="Transporte"))


@pytest.fixture
def categoria_salario(engine) -> int:
    return _cria(engine, Category(name="Salário"))


@pytest.fixture
def nova_transacao(client):
    """Cria uma transação pela API e devolve o corpo da resposta."""

    def criar(user_id, category_id, amount, description, tipo="expense"):
        response = client.post(
            "/transactions",
            json={
                "user_id": user_id,
                "category_id": category_id,
                "type": tipo,
                "amount": amount,
                "date": date.today().isoformat(),
                "description": description,
            },
        )
        assert response.status_code == 201, response.text
        return response.json()

    return criar
