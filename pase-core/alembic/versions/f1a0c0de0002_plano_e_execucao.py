"""Execução: ação por arquivo, tempo e risco técnico no plano

Revisão: f1a0c0de0002
Revisão anterior: f1a0c0de0001
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "f1a0c0de0002"
down_revision: str | None = "f1a0c0de0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Planos antigos não têm ação por arquivo: dicionário vazio, e não nulo, para
    # que quem lê trate "sem ação declarada" como "modificar" sem caso especial.
    op.add_column(
        "planning_documents",
        sa.Column("file_actions", sa.JSON(), nullable=False, server_default="{}"),
    )
    op.add_column(
        "planning_documents", sa.Column("minutes_estimated", sa.Integer(), nullable=True)
    )
    op.add_column(
        "planning_documents", sa.Column("technical_risk", sa.String(length=8), nullable=True)
    )
    op.add_column(
        "planning_documents", sa.Column("technical_risk_reason", sa.Text(), nullable=True)
    )
    op.add_column(
        "planning_documents",
        sa.Column("transcript_path", sa.String(length=512), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("planning_documents", "transcript_path")
    op.drop_column("planning_documents", "technical_risk_reason")
    op.drop_column("planning_documents", "technical_risk")
    op.drop_column("planning_documents", "minutes_estimated")
    op.drop_column("planning_documents", "file_actions")
