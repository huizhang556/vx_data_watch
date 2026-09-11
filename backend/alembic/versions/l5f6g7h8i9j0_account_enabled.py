"""Track whether a video account can be used."""
import sqlalchemy as sa
from alembic import op

revision = "l5f6g7h8i9j0"
down_revision = "k4e5f6g7h8i9"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("channels_accounts", sa.Column("is_enabled", sa.Boolean(), nullable=False, server_default=sa.true()))
    op.create_index("ix_channels_accounts_is_enabled", "channels_accounts", ["is_enabled"])


def downgrade() -> None:
    op.drop_index("ix_channels_accounts_is_enabled", table_name="channels_accounts")
    op.drop_column("channels_accounts", "is_enabled")
