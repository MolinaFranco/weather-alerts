"""retry failed sends and skip stale notices

Revision ID: 59355eae80db
Revises: 239870af035d
Create Date: 2026-11-09 01:20:11.402118
"""

import sqlalchemy as sa
from alembic import op

revision = "59355eae80db"
down_revision = "239870af035d"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Postgres can't drop a value from an enum, so the downgrade leaves it in place.
    op.execute("ALTER TYPE notification_status ADD VALUE IF NOT EXISTS 'skipped'")
    op.add_column(
        "notifications",
        sa.Column("attempts", sa.SmallInteger(), server_default="0", nullable=False),
    )
    op.add_column(
        "notifications",
        sa.Column(
            "next_attempt_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
    )
    op.drop_index("ix_notifications_pending", table_name="notifications")
    op.create_index(
        "ix_notifications_pending",
        "notifications",
        ["next_attempt_at"],
        postgresql_where=sa.text("status = 'pending'"),
    )


def downgrade() -> None:
    op.drop_index("ix_notifications_pending", table_name="notifications")
    op.create_index(
        "ix_notifications_pending",
        "notifications",
        ["id"],
        postgresql_where=sa.text("status = 'pending'"),
    )
    op.drop_column("notifications", "next_attempt_at")
    op.drop_column("notifications", "attempts")
