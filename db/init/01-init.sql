-- Executado uma única vez pelo entrypoint do Postgres, na criação do volume pgdata.
-- O restante do schema é criado por SQLAlchemy create_all no boot do pase-core
-- (sem Alembic nesta fase, ver SPEC-01 §6 e SPEC-10).
CREATE EXTENSION IF NOT EXISTS vector;
