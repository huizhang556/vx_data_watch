"""Store the model list returned by each provider."""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op


revision: str = "g0a1b2c3d4e5f"
down_revision: tuple[str, str] = ("b2c3d4e5f6a7", "f9a2b3c4d5e6")
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("ai_provider_configs", sa.Column("models_json", sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column("ai_provider_configs", "models_json")
