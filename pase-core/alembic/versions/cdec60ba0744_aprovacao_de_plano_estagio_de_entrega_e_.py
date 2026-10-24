"""aprovacao_de_plano_estagio_de_entrega_e_releases

Revisão: cdec60ba0744
Revisão anterior: a6304ceae190
Criada em: 2026-10-08 16:12:57.634846+00:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = 'cdec60ba0744'
down_revision: str | None = 'a6304ceae190'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table('pipeline_events',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('branch', sa.String(length=48), nullable=False),
    sa.Column('kind', sa.String(length=16), nullable=False),
    sa.Column('ok', sa.Boolean(), nullable=False),
    sa.Column('task_id', sa.Integer(), nullable=True),
    sa.Column('release_id', sa.Integer(), nullable=True),
    sa.Column('commit', sa.String(length=40), nullable=True),
    sa.Column('detail', sa.Text(), nullable=False),
    sa.Column('log_path', sa.String(length=512), nullable=True),
    sa.Column('at', sa.DateTime(timezone=True), nullable=False),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_pipeline_events_branch'), 'pipeline_events', ['branch'], unique=False)
    op.create_index(op.f('ix_pipeline_events_kind'), 'pipeline_events', ['kind'], unique=False)
    op.create_index(op.f('ix_pipeline_events_task_id'), 'pipeline_events', ['task_id'], unique=False)
    op.create_table('releases',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('version', sa.String(length=16), nullable=False),
    sa.Column('branch', sa.String(length=32), nullable=False),
    sa.Column('status', sa.String(length=16), nullable=False),
    sa.Column('changelog', sa.Text(), nullable=False),
    sa.Column('validation_ok', sa.Boolean(), nullable=True),
    sa.Column('validation_log_path', sa.String(length=512), nullable=True),
    sa.Column('pr_number', sa.Integer(), nullable=True),
    sa.Column('pr_url', sa.String(length=512), nullable=True),
    sa.Column('pr_body', sa.Text(), nullable=True),
    sa.Column('approval_note', sa.Text(), nullable=True),
    sa.Column('publish_commit', sa.String(length=40), nullable=True),
    sa.Column('tag', sa.String(length=16), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('published_at', sa.DateTime(timezone=True), nullable=True),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('version')
    )
    op.create_index(op.f('ix_releases_status'), 'releases', ['status'], unique=False)
    op.add_column(
        'tasks', sa.Column('plan_approval_required', sa.Boolean(), nullable=False, server_default=sa.false())
    )
    op.add_column(
        'tasks', sa.Column('plan_approved', sa.Boolean(), nullable=False, server_default=sa.false())
    )
    op.add_column('tasks', sa.Column('plan_feedback', sa.Text(), nullable=True))
    op.add_column('tasks', sa.Column('stage', sa.String(length=16), nullable=True))
    op.add_column(
        'tasks', sa.Column('tested_ok', sa.Boolean(), nullable=False, server_default=sa.false())
    )
    op.add_column('tasks', sa.Column('tested_note', sa.Text(), nullable=True))
    op.add_column('tasks', sa.Column('release_id', sa.Integer(), nullable=True))
    op.add_column('tasks', sa.Column('release_commit', sa.String(length=40), nullable=True))
    op.create_index(op.f('ix_tasks_release_id'), 'tasks', ['release_id'], unique=False)
    op.create_index(op.f('ix_tasks_stage'), 'tasks', ['stage'], unique=False)


def downgrade() -> None:
    op.drop_index(op.f('ix_tasks_stage'), table_name='tasks')
    op.drop_index(op.f('ix_tasks_release_id'), table_name='tasks')
    op.drop_column('tasks', 'release_commit')
    op.drop_column('tasks', 'release_id')
    op.drop_column('tasks', 'tested_note')
    op.drop_column('tasks', 'tested_ok')
    op.drop_column('tasks', 'stage')
    op.drop_column('tasks', 'plan_feedback')
    op.drop_column('tasks', 'plan_approved')
    op.drop_column('tasks', 'plan_approval_required')
    op.drop_index(op.f('ix_releases_status'), table_name='releases')
    op.drop_table('releases')
    op.drop_index(op.f('ix_pipeline_events_task_id'), table_name='pipeline_events')
    op.drop_index(op.f('ix_pipeline_events_kind'), table_name='pipeline_events')
    op.drop_index(op.f('ix_pipeline_events_branch'), table_name='pipeline_events')
    op.drop_table('pipeline_events')
