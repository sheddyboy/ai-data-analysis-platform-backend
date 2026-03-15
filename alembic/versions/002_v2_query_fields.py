"""v2 query fields: structured output, follow-ups, conversation threading

Revision ID: 002
Revises: 001
Create Date: 2026-03-15
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID, JSON

revision = "002"
down_revision = "001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Structured output fields
    op.add_column("queries", sa.Column("key_findings", JSON, nullable=True))
    op.add_column("queries", sa.Column("data_quality_notes", JSON, nullable=True))
    op.add_column("queries", sa.Column("confidence", sa.String(20), nullable=True))
    op.add_column("queries", sa.Column("analysis_plan", JSON, nullable=True))
    op.add_column("queries", sa.Column("follow_up_questions", JSON, nullable=True))

    # Conversation threading
    op.add_column(
        "queries",
        sa.Column("session_id", UUID(as_uuid=True), nullable=True),
    )
    op.add_column(
        "queries",
        sa.Column(
            "parent_query_id",
            UUID(as_uuid=True),
            sa.ForeignKey("queries.id", ondelete="SET NULL"),
            nullable=True,
        ),
    )
    op.create_index("ix_queries_session_id", "queries", ["session_id"])


def downgrade() -> None:
    op.drop_index("ix_queries_session_id", table_name="queries")
    op.drop_column("queries", "parent_query_id")
    op.drop_column("queries", "session_id")
    op.drop_column("queries", "follow_up_questions")
    op.drop_column("queries", "analysis_plan")
    op.drop_column("queries", "confidence")
    op.drop_column("queries", "data_quality_notes")
    op.drop_column("queries", "key_findings")
