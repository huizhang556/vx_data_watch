"""Allow video accounts to be owned by an individual user."""
from collections.abc import Sequence
import sqlalchemy as sa
from alembic import op

revision: str = "f3a4b5c6d7e8"
down_revision: str | None = "e1f2a3b4c5d6"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

def upgrade() -> None:
    with op.batch_alter_table("channels_accounts") as batch:
        batch.add_column(sa.Column("user_id", sa.Integer(), nullable=True))
        batch.create_foreign_key(
            "fk_channels_accounts_user_id_users",
            "users",
            ["user_id"],
            ["id"],
            ondelete="CASCADE",
        )
        batch.create_index("ix_channels_accounts_user_id", ["user_id"])

def downgrade() -> None:
    with op.batch_alter_table("channels_accounts") as batch:
        batch.drop_index("ix_channels_accounts_user_id")
        batch.drop_constraint("fk_channels_accounts_user_id_users", type_="foreignkey")
        batch.drop_column("user_id")
