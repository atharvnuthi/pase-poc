"""teto de tokens editavel

Revisão: 9717e9b6a002
Revisão anterior: 5a31fd6d2084
Criada em: 2026-09-28 17:08:55.691464+00:00

O autogenerate quis **apagar os três índices HNSW** desta migração: eles foram
criados em SQL cru na revisão anterior e não existem no metadata dos modelos, o
que faz o Alembic concluir que sobraram no banco. As linhas de `drop_index`
foram removidas à mão. É o caso clássico de "please adjust": autogenerate não
sabe o que ele não modela, e aceitar a sugestão às cegas destruiria o índice a
cada migração nova.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "9717e9b6a002"
down_revision: str | None = "5a31fd6d2084"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Teto de tokens que uma pessoa pode ajustar.

    Nulo por padrão: sem valor, vale o cálculo automático com piso. Preenchido,
    vence - é o recurso de quem olha uma tarefa suspensa por budget e decide que
    ela merece mais.
    """
    op.add_column("tasks", sa.Column("budget_cap_tokens", sa.Integer(), nullable=True))


def downgrade() -> None:
    op.drop_column("tasks", "budget_cap_tokens")
