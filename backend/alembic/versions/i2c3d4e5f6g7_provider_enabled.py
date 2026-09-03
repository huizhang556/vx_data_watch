"""Allow administrators to enable or disable individual AI providers."""
import sqlalchemy as sa
from alembic import op

revision = "i2c3d4e5f6g7"
down_revision = "h1b2c3d4e5f6"
branch_labels = None
depends_on = None

def upgrade() -> None:
    op.add_column("ai_provider_configs", sa.Column("is_enabled", sa.Boolean(), nullable=False, server_default=sa.true()))

def downgrade() -> None:
    op.drop_column("ai_provider_configs", "is_enabled")
