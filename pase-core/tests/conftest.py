"""Fixtures da suíte do pase-core.

A suíte roda contra um **banco separado** (`<database>_test`), criado sob demanda.
Isso não é preciosismo: vários testes limpam tabelas para se isolar, e apontar
para o banco da aplicação significaria apagar tarefas e propostas reais a cada
`make test-core` - inclusive no meio de uma demonstração.
"""

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

from app.common import db as db_module
from app.common import llm_client
from app.common.config import settings


def _url_de_teste() -> str:
    base, _, nome = settings.database_url.rpartition("/")
    return f"{base}/{nome}_test"


def _garantir_banco_de_teste() -> str:
    """Recria o banco de teste do zero a cada sessão.

    Recriar, e não reaproveitar: `create_all` só cria tabela que falta, **nunca
    altera** uma existente. Um banco de teste reaproveitado guarda o esquema do
    dia em que foi criado, e uma coluna nova passa a existir nos modelos, na
    migração e em produção - mas não nele. Já aconteceu: a suíte inteira quebrou
    com `column "change_type" does not exist` enquanto a aplicação rodava bem.

    Um banco vazio com doze tabelas nasce em cerca de um segundo. É barato o
    bastante para não valer a pena guardar.

    **A suíte não roda duas vezes ao mesmo tempo.** Este `DROP` derruba as
    conexões de quem já estivesse usando o banco, e a outra execução morre com
    `AdminShutdown` no meio - dezenas de erros sem causa aparente no código.
    """
    url = _url_de_teste()
    nome = url.rpartition("/")[2]

    administrativo = create_engine(
        settings.database_url.rpartition("/")[0] + "/postgres",
        isolation_level="AUTOCOMMIT",
        connect_args={"connect_timeout": settings.db_connect_timeout},
    )
    with administrativo.connect() as conn:
        # Conexão pendurada de uma execução anterior impediria o DROP.
        conn.execute(
            text(
                "SELECT pg_terminate_backend(pid) FROM pg_stat_activity "
                "WHERE datname = :nome AND pid <> pg_backend_pid()"
            ),
            {"nome": nome},
        )
        conn.execute(text(f'DROP DATABASE IF EXISTS "{nome}"'))
        conn.execute(text(f'CREATE DATABASE "{nome}"'))
    administrativo.dispose()

    return url


def _postgres_disponivel() -> bool:
    try:
        with db_module.engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        return True
    except Exception:
        return False


POSTGRES_UP = _postgres_disponivel()

requires_db = pytest.mark.skipif(
    not POSTGRES_UP,
    reason="precisa do Postgres com pgvector (rode via `make test-core`)",
)


@pytest.fixture(scope="session", autouse=True)
def banco_de_teste():
    """Redireciona todo o acesso a banco da aplicação para o banco de teste."""
    if not POSTGRES_UP:
        yield None
        return

    url = _garantir_banco_de_teste()
    engine = create_engine(
        url,
        pool_pre_ping=True,
        future=True,
        connect_args={"connect_timeout": settings.db_connect_timeout},
    )

    with engine.begin() as conn:
        conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))

    engine_original = db_module.engine
    session_original = db_module.SessionLocal
    url_original = settings.database_url

    db_module.engine = engine
    db_module.SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
    # events.listen() abre conexão própria a partir do DATABASE_URL
    settings.database_url = url

    db_module.init_db()

    yield engine

    engine.dispose()
    db_module.engine = engine_original
    db_module.SessionLocal = session_original
    settings.database_url = url_original


@pytest.fixture(autouse=True)
def github_desligado(monkeypatch):
    """Nenhum teste fala com o GitHub real.

    O container herda o `GITHUB_TOKEN` do `.env`, e o fluxo de entrega sobe a
    principal e a release antes do PR. Sem isto, `test_delivery` empurrou o
    repositório de teste para o remoto de verdade, abriu e mergeou um PR lá.
    Teste que precisa do GitHub liga um token falso e dubla o transporte.
    """
    monkeypatch.setattr(settings, "github_token", "")
    monkeypatch.setattr(settings, "github_repo", "")


@pytest.fixture(autouse=True)
def mock_providers(monkeypatch):
    """Nenhum teste fala com um provider real: chat e embed são determinísticos.

    Sem Postgres, o registro em `llm_calls` é desligado: o llm_client tolera o
    banco fora do ar por design, mas cada tentativa custaria o connect_timeout.
    """
    provider = llm_client.MockProvider()
    llm_client.set_providers(chat=provider, embed=provider)

    if not POSTGRES_UP:
        monkeypatch.setattr(
            llm_client,
            "_record",
            lambda kind, usage, temperature, error: None,
        )

    yield provider
    llm_client.reset_providers()


@pytest.fixture
def session(banco_de_teste):
    sess = db_module.SessionLocal()
    try:
        yield sess
        sess.rollback()
    finally:
        sess.close()
