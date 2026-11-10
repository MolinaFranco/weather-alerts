"""rename data_status to operational_status

Revision ID: 7d3e1c5a9b42
Revises: 59355eae80db
Create Date: 2026-11-10 14:05:00.000000
"""

from alembic import op

revision = "7d3e1c5a9b42"
down_revision = "59355eae80db"
branch_labels = None
depends_on = None

# PL/pgSQL looks types up by name when the function runs, so the trigger function has to
# be recreated with the new name or it breaks on the next write.
SYNC_SAMPLE_STATUS_FUNCTION = """
CREATE OR REPLACE FUNCTION sync_sample_status() RETURNS trigger AS $$
DECLARE
    point_status {status_type};
BEGIN
    SELECT status INTO point_status FROM measurement_points WHERE id = NEW.point_id;
    IF NOT FOUND THEN
        RETURN NEW;  -- let the foreign key report the missing point
    END IF;

    IF TG_OP = 'UPDATE' THEN
        NEW.updated_at := now();
    END IF;

    IF point_status <> 'active' THEN
        NEW.status := point_status;
    ELSIF TG_OP = 'INSERT' OR NEW.probability IS DISTINCT FROM OLD.probability THEN
        NEW.status := 'active';
    END IF;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql
"""


def upgrade() -> None:
    op.execute("ALTER TYPE data_status RENAME TO operational_status")
    op.execute(SYNC_SAMPLE_STATUS_FUNCTION.format(status_type="operational_status"))


def downgrade() -> None:
    op.execute("ALTER TYPE operational_status RENAME TO data_status")
    op.execute(SYNC_SAMPLE_STATUS_FUNCTION.format(status_type="data_status"))
