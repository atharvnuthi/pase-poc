"""Camada de Tarefas: ocorrências e citação conferida

Revisão: f1a0c0de0001
Revisão anterior: 0d2ceda8c205

- `proposals.occurrences`: quantos pedidos a proposta representa (peso do P0a e
  das duplicatas que bateram nela).
- `proposals.feedback`: a resposta dada a quem pediu, mostrada de volta no FinTrack.
- `discarded_proposals.cited_excerpt`: o trecho do contexto que o P2a citou como
  violado, conferido por código.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "f1a0c0de0001"
down_revision: str | None = "0d2ceda8c205"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "proposals",
        sa.Column("occurrences", sa.Integer(), nullable=False, server_default="1"),
    )
    op.add_column("proposals", sa.Column("feedback", sa.Text(), nullable=True))
    op.add_column(
        "discarded_proposals", sa.Column("cited_excerpt", sa.Text(), nullable=True)
    )


def downgrade() -> None:
    op.drop_column("discarded_proposals", "cited_excerpt")
    op.drop_column("proposals", "feedback")
    op.drop_column("proposals", "occurrences")
