"""Persist chat category pinning and inherited provider preference."""
from collections.abc import Sequence
import sqlalchemy as sa
from alembic import op

revision: str = "f2a3b4c5d6e7"
down_revision: str | None = "e1f2a3b4c5d6"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("ai_chat_categories") as batch:
        batch.add_column(sa.Column("pinned", sa.Boolean(), nullable=False, server_default=sa.false()))
        batch.add_column(sa.Column("provider_id", sa.Integer(), sa.ForeignKey("ai_provider_configs.id", ondelete="SET NULL"), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("ai_chat_categories") as batch:
        batch.drop_column("provider_id")
        batch.drop_column("pinned")
