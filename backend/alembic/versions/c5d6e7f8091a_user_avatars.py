"""Add user avatars.

Revision ID: c5d6e7f8091a
Revises: b4c5d6e7f809
"""

from alembic import op
import sqlalchemy as sa

revision = "c5d6e7f8091a"
down_revision = "b4c5d6e7f809"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("users", sa.Column("avatar", sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column("users", "avatar")