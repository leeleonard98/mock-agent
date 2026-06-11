"""itinerary feedback

Revision ID: 0005_itinerary_feedback
Revises: 0004_trace_events
Create Date: 2026-06-11 00:00:04.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "0005_itinerary_feedback"
down_revision: Union[str, None] = "0004_trace_events"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "itinerary_feedback",
        sa.Column("id", sa.Integer(), primary_key=True, nullable=False),
        sa.Column(
            "session_id",
            sa.Integer(),
            sa.ForeignKey("chat_sessions.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("rating", sa.Integer(), nullable=False),
        sa.Column("comment", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )
    op.create_index(
        "ix_itinerary_feedback_session_id", "itinerary_feedback", ["session_id"]
    )


def downgrade() -> None:
    op.drop_index(
        "ix_itinerary_feedback_session_id", table_name="itinerary_feedback"
    )
    op.drop_table("itinerary_feedback")
