"""tipo de mudanca na tarefa

Revisão: 0b48819ef0cb
Revisão anterior: a3aad06be56e
Criada em: 2026-09-23 02:40:20.660198+00:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = '0b48819ef0cb'
down_revision: str | None = 'a3aad06be56e'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Acrescenta o tipo da mudança, com `feature` para o que já existe.

    `server_default` não é detalhe: a coluna é NOT NULL e a tabela já tem linhas.
    Sem um valor para as existentes, a migração falha no banco de quem já estava
    rodando - que é justamente o caso que o Alembic veio resolver.
    """
    op.add_column(
        "tasks",
        sa.Column(
            "change_type",
            sa.String(length=16),
            nullable=False,
            server_default="feature",
        ),
    )


def downgrade() -> None:
    op.drop_column("tasks", "change_type")
