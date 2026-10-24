"""Ambiente do Alembic.

A URL vem de `settings.database_url`, nunca do `alembic.ini`: a aplicação e as
migrações precisam apontar necessariamente para o mesmo banco, e manter a string
de conexão em dois lugares é como se migra o banco errado.
"""

from logging.config import fileConfig

from alembic import context
from sqlalchemy import engine_from_config, pool

# Importar os modelos registra as tabelas no metadata da Base. Sem isto o
# autogenerate acha que o esquema inteiro deve ser apagado.
from app.common import models  # noqa: F401,E402
from app.common.config import settings
from app.common.db import Base
from app.orchestration import models as _orchestration  # noqa: F401,E402
from app.task_layer import models as _task_layer  # noqa: F401,E402
from app.upa import models as _upa  # noqa: F401,E402

config = context.config
config.set_main_option("sqlalchemy.url", settings.database_url)

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata


def render_item(tipo: str, obj, autogen_context) -> str | bool:
    """Faz o autogenerate escrever `Vector(...)` com o import certo.

    Sem isto a migração sai referenciando um tipo que ela não importou, e quebra
    na hora de rodar.
    """
    if tipo == "type" and obj.__class__.__module__.startswith("pgvector"):
        autogen_context.imports.add("import pgvector.sqlalchemy")
        return f"pgvector.sqlalchemy.Vector(dim={obj.dim})"
    return False


def include_object(obj, nome, tipo, reflected, comparado_com) -> bool:
    """Deixa de fora do autogenerate o que é mantido à mão.

    Os índices HNSW das três tabelas com embedding são criados em SQL cru (não
    há como declará-los no modelo com o operador `vector_cosine_ops` de forma
    portável). Sem este filtro, **toda** migração gerada trazia três
    `drop_index` - e aceitar a sugestão às cegas destruiria a busca vetorial.
    Já aconteceu duas vezes, corrigido na mão nas duas.
    """
    if tipo == "index" and nome and nome.endswith("_embedding_hnsw"):
        return False
    return True


def run_migrations_offline() -> None:
    context.configure(
        url=settings.database_url,
        target_metadata=target_metadata,
        literal_binds=True,
        render_item=render_item,
        include_object=include_object,
        compare_type=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            render_item=render_item,
            include_object=include_object,
            compare_type=True,
        )
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
