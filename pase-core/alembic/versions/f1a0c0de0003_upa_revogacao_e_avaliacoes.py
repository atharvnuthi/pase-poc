"""UPA: revogação durável e avaliações registradas

Revisão: f1a0c0de0003
Revisão anterior: f1a0c0de0002
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "f1a0c0de0003"
down_revision: str | None = "f1a0c0de0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _colunas_da_avaliacao() -> list[sa.Column]:
    """O que a avaliação passa a registrar: sinais, decisão, motivo e o que saiu dela."""
    return [
        sa.Column("sinais", sa.Text(), nullable=True),
        sa.Column("pedido", sa.Text(), nullable=True),
        sa.Column("decisao", sa.Boolean(), nullable=True),
        sa.Column("motivo", sa.Text(), nullable=True),
        sa.Column("payload_id", sa.Integer(), nullable=True),
        sa.Column("violation_id", sa.Integer(), nullable=True),
        sa.Column("trace_id", sa.String(length=64), nullable=True),
    ]


def upgrade() -> None:
    # Quem revogou e quando: é o que permite a revogação pela pessoa ser durável.
    op.add_column("zone_payloads", sa.Column("revoked_by", sa.String(length=16), nullable=True))
    op.add_column(
        "zone_payloads", sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True)
    )
    # Toda violação registrada até aqui veio do cliente: o core só logava as dele.
    op.add_column(
        "zone_violations",
        sa.Column("origem", sa.String(length=16), nullable=False, server_default="cliente"),
    )
    for coluna in _colunas_da_avaliacao():
        op.add_column("zone_evaluations", coluna)


def downgrade() -> None:
    for coluna in reversed(_colunas_da_avaliacao()):
        op.drop_column("zone_evaluations", coluna.name)
    op.drop_column("zone_violations", "origem")
    op.drop_column("zone_payloads", "revoked_at")
    op.drop_column("zone_payloads", "revoked_by")
