"""criterios de aceite revisao e refazer

Revisão: a6304ceae190
Revisão anterior: 9717e9b6a002
Criada em: 2026-10-08 02:07:44.178898+00:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = 'a6304ceae190'
down_revision: str | None = '9717e9b6a002'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column('execution_runs', sa.Column('review_path', sa.String(length=512), nullable=True))
    # Planos antigos nasceram sem critérios: lista vazia, e não nulo, para que o
    # revisor e o painel tratem "sem critério" sem um caso especial.
    op.add_column(
        'planning_documents',
        sa.Column('acceptance_criteria', sa.JSON(), nullable=False, server_default='[]'),
    )
    op.add_column('tasks', sa.Column('parent_task_id', sa.Integer(), nullable=True))
    op.add_column('tasks', sa.Column('redo_feedback', sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column('tasks', 'redo_feedback')
    op.drop_column('tasks', 'parent_task_id')
    op.drop_column('planning_documents', 'acceptance_criteria')
    op.drop_column('execution_runs', 'review_path')
