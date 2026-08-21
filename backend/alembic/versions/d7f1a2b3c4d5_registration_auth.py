"""Add email registration and verification codes."""

from collections.abc import Sequence
import sqlalchemy as sa
from alembic import op

revision: str = "d7f1a2b3c4d5"
down_revision: str | None = "a1c9d2e4f6b8"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

def upgrade() -> None:
    op.add_column("users", sa.Column("email", sa.String(length=254), nullable=True))
    op.add_column("users", sa.Column("email_verified", sa.Boolean(), nullable=False, server_default=sa.false()))
    op.create_index("ix_users_email", "users", ["email"], unique=True)
    op.create_table(
        "verification_codes",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("email", sa.String(length=254), nullable=False),
        sa.Column("purpose", sa.String(length=30), nullable=False),
        sa.Column("code_hash", sa.String(length=64), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("consumed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_verification_codes_email", "verification_codes", ["email"])
    op.create_index("ix_verification_codes_purpose", "verification_codes", ["purpose"])
    op.create_index("ix_verification_codes_expires_at", "verification_codes", ["expires_at"])

def downgrade() -> None:
    op.drop_table("verification_codes")
    op.drop_index("ix_users_email", table_name="users")
    op.drop_column("users", "email_verified")
    op.drop_column("users", "email")
