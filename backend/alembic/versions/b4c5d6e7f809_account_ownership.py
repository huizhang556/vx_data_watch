"""Allow video accounts to be owned by an individual user."""
from collections.abc import Sequence
import sqlalchemy as sa
from alembic import op

revision: str = "b4c5d6e7f809"
down_revision: str | None = "a3b4c5d6e7f8"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

def upgrade() -> None:
    with op.batch_alter_table("channels_accounts") as batch:
        batch.add_column(sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=True))
        batch.create_index("ix_channels_accounts_user_id", ["user_id"])

def downgrade() -> None:
    with op.batch_alter_table("channels_accounts") as batch:
        batch.drop_index("ix_channels_accounts_user_id")
        batch.drop_column("user_id")
