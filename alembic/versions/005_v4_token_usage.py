"""v4 token usage: add token_usage JSON column to queries

Revision ID: 005
Revises: 004
Create Date: 2026-03-16
"""

from alembic import op
import sqlalchemy as sa

revision = "005"
down_revision = "004"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "queries",
        sa.Column("token_usage", sa.JSON(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("queries", "token_usage")
