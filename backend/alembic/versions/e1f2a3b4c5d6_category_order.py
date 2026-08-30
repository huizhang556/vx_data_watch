"""Persist AI chat category ordering."""
from collections.abc import Sequence
import sqlalchemy as sa
from alembic import op

revision: str = "e1f2a3b4c5d6"
down_revision: str | None = "d0e1f2a3b4c5"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

def upgrade() -> None:
    with op.batch_alter_table("ai_chat_categories") as batch:
        batch.add_column(sa.Column("sort_order", sa.Integer(), nullable=False, server_default="0"))

def downgrade() -> None:
    with op.batch_alter_table("ai_chat_categories") as batch:
        batch.drop_column("sort_order")
