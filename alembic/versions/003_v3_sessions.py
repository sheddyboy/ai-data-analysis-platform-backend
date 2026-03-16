"""v3 sessions: add sessions table and FK on queries.session_id

Revision ID: 003
Revises: 002
Create Date: 2026-03-16
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID

revision = "003"
down_revision = "002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Create sessions table
    op.create_table(
        "sessions",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "dataset_id",
            UUID(as_uuid=True),
            sa.ForeignKey("datasets.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("title", sa.String(255), nullable=False, server_default="New session"),
        sa.Column("user_id", UUID(as_uuid=True), nullable=True),  # reserved for v4 auth
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
    )
    op.create_index("ix_sessions_id", "sessions", ["id"])
    op.create_index("ix_sessions_dataset_id", "sessions", ["dataset_id"])

    # Drop the existing bare index on queries.session_id (added in 002)
    op.drop_index("ix_queries_session_id", table_name="queries")

    # Add FK constraint on queries.session_id → sessions.id
    op.create_foreign_key(
        "fk_queries_session_id",
        "queries",
        "sessions",
        ["session_id"],
        ["id"],
        ondelete="SET NULL",
    )

    # Re-create the index (now backed by FK)
    op.create_index("ix_queries_session_id", "queries", ["session_id"])


def downgrade() -> None:
    op.drop_index("ix_queries_session_id", table_name="queries")
    op.drop_constraint("fk_queries_session_id", "queries", type_="foreignkey")

    # Restore bare index from migration 002
    op.create_index("ix_queries_session_id", "queries", ["session_id"])

    op.drop_index("ix_sessions_dataset_id", table_name="sessions")
    op.drop_index("ix_sessions_id", table_name="sessions")
    op.drop_table("sessions")
