-- Executado uma única vez pelo entrypoint do Postgres, na criação do volume pgdata.
-- O restante do schema é criado pelas migrações Alembic, aplicadas no boot do pase-core.
CREATE EXTENSION IF NOT EXISTS vector;
