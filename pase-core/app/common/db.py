"""Engine, sessão e Base declarativa.

O esquema da aplicação é versionado em `alembic/versions/`. `create_all` sobrou
apenas para a suíte de testes - ver `init_db()` e `migrar()`.
"""

import logging
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

from sqlalchemy import create_engine, text
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from app.common.config import settings

logger = logging.getLogger("pase.db")

# connect_timeout: sem ele, um banco fora do ar deixa o processo pendurado
# indefinidamente em vez de falhar rápido (observado no Windows).
engine = create_engine(
    settings.database_url,
    pool_pre_ping=True,
    future=True,
    connect_args={"connect_timeout": settings.db_connect_timeout},
)
SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


class Base(DeclarativeBase):
    pass


@contextmanager
def session_scope() -> Iterator[Session]:
    """Sessão transacional: commit no sucesso, rollback em qualquer exceção."""
    session = SessionLocal()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def get_session() -> Iterator[Session]:
    """Dependência do FastAPI."""
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()


def _registrar_modelos() -> None:
    """Importar os módulos de modelos os registra no metadata da Base."""
    from app.common import models  # noqa: F401  (llm_calls)
    from app.orchestration import models as orch_models  # noqa: F401  (runs, incidents...)
    from app.task_layer import models as task_models  # noqa: F401  (proposals, tasks...)
    from app.upa import models as upa_models  # noqa: F401  (telemetry_events)


def _config_alembic():
    from alembic.config import Config

    raiz = Path(__file__).resolve().parents[2]
    config = Config(str(raiz / "alembic.ini"))
    config.set_main_option("script_location", str(raiz / "alembic"))
    return config


def init_db() -> None:
    """Cria o esquema a partir dos modelos, sem passar por migração.

    **Só para a suíte de testes.** Ela quer o esquema que os modelos descrevem
    agora, montado em um passo; reproduzir o histórico de migrações a cada
    execução seria mais lento e testaria a coisa errada. A aplicação usa
    `migrar()`.

    O banco é carimbado em `head` no fim, e isso importa: `create_all` produz o
    esquema **final**, então este banco já está na última revisão. Sem o carimbo,
    qualquer coisa que chame `migrar()` depois - um teste que sobe o app, por
    exemplo - encontraria um banco com tabelas e sem versão, concluiria que ele é
    anterior às migrações, e tentaria aplicar da primeira em diante numa
    estrutura que já está completa.
    """
    from alembic import command

    _registrar_modelos()

    with engine.begin() as conn:
        conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))

    Base.metadata.create_all(bind=engine)
    command.stamp(_config_alembic(), "head")


def migrar() -> None:
    """Leva o banco da aplicação até a última revisão do Alembic.

    Trata o banco que já existia antes de haver migrações: se há tabelas mas não
    há `alembic_version`, aplicar a revisão inicial tentaria criar o que já está
    lá e falharia. Nesse caso o banco é **carimbado** na revisão inicial - ele já
    tem aquele esquema - e dali em diante segue o caminho normal.
    """
    from alembic import command
    from alembic.runtime.migration import MigrationContext
    from sqlalchemy import inspect

    _registrar_modelos()

    with engine.begin() as conn:
        conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))

    config = _config_alembic()

    with engine.connect() as conn:
        versao_atual = MigrationContext.configure(conn).get_current_revision()
        ja_tem_tabelas = "tasks" in inspect(conn).get_table_names()

    if versao_atual is None and ja_tem_tabelas:
        from alembic.script import ScriptDirectory

        primeira = next(
            rev.revision
            for rev in ScriptDirectory.from_config(config).walk_revisions()
            if rev.down_revision is None
        )
        logger.warning(
            "banco anterior às migrações: carimbando na revisão inicial %s", primeira[:12]
        )
        command.stamp(config, primeira)

    command.upgrade(config, "head")
    logger.info("migrações aplicadas")
