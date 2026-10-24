"""grafo de dependencias, metadados de PR e custo

Revisão: 5a31fd6d2084
Revisão anterior: 0b48819ef0cb
Criada em: 2026-09-28 15:58:48.643049+00:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "5a31fd6d2084"
down_revision: str | None = "0b48819ef0cb"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


#: Onde há embedding. HNSW e não ivfflat: o ivfflat precisa de dados para treinar
#: as listas e, criado sobre tabela quase vazia, fica pior que a varredura. O
#: HNSW é construído incrementalmente e funciona desde a primeira linha.
TABELAS_COM_EMBEDDING = ("proposals", "discarded_proposals", "implemented_items")


def upgrade() -> None:
    op.create_table(
        "task_dependencies",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("task_id", sa.Integer(), nullable=False),
        sa.Column("depends_on_task_id", sa.Integer(), nullable=False),
        sa.Column("kind", sa.String(length=16), nullable=False, server_default="arquivo"),
        sa.Column("reason", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.ForeignKeyConstraint(["depends_on_task_id"], ["tasks.id"]),
        sa.ForeignKeyConstraint(["task_id"], ["tasks.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("task_id", "depends_on_task_id", name="uq_dependencia"),
    )
    op.create_index(
        op.f("ix_task_dependencies_depends_on_task_id"),
        "task_dependencies",
        ["depends_on_task_id"],
    )
    op.create_index(op.f("ix_task_dependencies_kind"), "task_dependencies", ["kind"])
    op.create_index(op.f("ix_task_dependencies_task_id"), "task_dependencies", ["task_id"])

    # `server_default` porque as colunas são NOT NULL e as tabelas já têm linhas.
    op.add_column(
        "llm_calls",
        sa.Column("cost_usd", sa.Float(), nullable=False, server_default="0"),
    )
    op.add_column("tasks", sa.Column("merge_commit", sa.String(length=40), nullable=True))
    op.add_column("tasks", sa.Column("pr_url", sa.String(length=512), nullable=True))
    op.add_column("tasks", sa.Column("pr_number", sa.Integer(), nullable=True))

    # Busca vetorial deixa de ser varredura sequencial.
    for tabela in TABELAS_COM_EMBEDDING:
        op.execute(
            f"CREATE INDEX IF NOT EXISTS ix_{tabela}_embedding_hnsw "
            f"ON {tabela} USING hnsw (embedding vector_cosine_ops)"
        )

    # --- correção de dados ---------------------------------------------------
    # A Memória Histórica indexa `candidata` como `proposals WHERE outcome =
    # 'candidata'`, e nada nunca fechava a proposta quando a tarefa acabava.
    # Resultado: toda demanda já decidida continuava sendo lembrada como
    # "aguardando avaliação", e reenviá-la voltava barrada com um motivo falso.
    # As duas tarefas finalizadas do banco estavam assim - inclusive a que havia
    # sido revertida justamente para liberar o pedido.
    op.execute(
        """
        UPDATE proposals p
           SET outcome = CASE t.final_outcome
                             WHEN 'aprovada'  THEN 'implementada'
                             WHEN 'recusada'  THEN 'recusada_pelo_humano'
                             WHEN 'revertida' THEN 'revertida'
                             ELSE p.outcome
                         END
          FROM tasks t
         WHERE t.proposal_id = p.id
           AND t.status = 'finalizada'
           AND p.outcome = 'candidata'
        """
    )


def downgrade() -> None:
    for tabela in TABELAS_COM_EMBEDDING:
        op.execute(f"DROP INDEX IF EXISTS ix_{tabela}_embedding_hnsw")

    op.drop_column("tasks", "pr_number")
    op.drop_column("tasks", "pr_url")
    op.drop_column("tasks", "merge_commit")
    op.drop_column("llm_calls", "cost_usd")
    op.drop_index(op.f("ix_task_dependencies_task_id"), table_name="task_dependencies")
    op.drop_index(op.f("ix_task_dependencies_kind"), table_name="task_dependencies")
    op.drop_index(
        op.f("ix_task_dependencies_depends_on_task_id"), table_name="task_dependencies"
    )
    op.drop_table("task_dependencies")
