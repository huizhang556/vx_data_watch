"""Persist whether an AI provider uses an official or compatible interface."""
from alembic import op
import sqlalchemy as sa

revision = "a1b2c3d4e5f6"
down_revision = "f9a2b3c4d5e6"
branch_labels = None
depends_on = None

def upgrade() -> None:
    op.add_column("ai_provider_configs", sa.Column("interface_type", sa.String(length=20), nullable=False, server_default="compatible"))

def downgrade() -> None:
    op.drop_column("ai_provider_configs", "interface_type")
