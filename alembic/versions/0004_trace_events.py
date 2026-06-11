"""trace events

Revision ID: 0004_trace_events
Revises: 0003_user_preferences
Create Date: 2026-06-11 00:00:03.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB


revision: str = "0004_trace_events"
down_revision: Union[str, None] = "0003_user_preferences"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "trace_events",
        sa.Column("id", sa.Integer(), primary_key=True, nullable=False),
        sa.Column(
            "session_id",
            sa.Integer(),
            sa.ForeignKey("chat_sessions.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("event_type", sa.String(length=64), nullable=False),
        sa.Column("payload", JSONB(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )
    op.create_index("ix_trace_events_session_id", "trace_events", ["session_id"])


def downgrade() -> None:
    op.drop_index("ix_trace_events_session_id", table_name="trace_events")
    op.drop_table("trace_events")
