"""every new reading takes the point's status; activation no longer touches old data

Revision ID: c41f8e2d6a17
Revises: 7d3e1c5a9b42
Create Date: 2026-11-10 14:40:00.000000
"""

from alembic import op

revision = "c41f8e2d6a17"
down_revision = "7d3e1c5a9b42"
branch_labels = None
depends_on = None

# Activating a point used to activate what it had received while in testing, so a bogus
# reading from a faulty sensor could fire an alert the moment the point went live. Now
# data from the testing period stays as test data, and every new reading from the
# ingestion, even one repeating the same value, takes the point's current status.
# A write that changes the status is a technician marking that reading, and it is kept,
# except that it can't make active the data of a point that isn't.
SYNC_SAMPLE_STATUS_FUNCTION = """
CREATE OR REPLACE FUNCTION sync_sample_status() RETURNS trigger AS $$
DECLARE
    point_status operational_status;
BEGIN
    SELECT status INTO point_status FROM measurement_points WHERE id = NEW.point_id;
    IF NOT FOUND THEN
        RETURN NEW;  -- let the foreign key report the missing point
    END IF;

    IF TG_OP = 'UPDATE' THEN
        NEW.updated_at := now();
    END IF;

    IF TG_OP = 'UPDATE' AND NEW.status IS DISTINCT FROM OLD.status THEN
        IF NEW.status = 'active' AND point_status <> 'active' THEN
            NEW.status := point_status;
        END IF;
    ELSE
        NEW.status := point_status;
    END IF;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql
"""

PREVIOUS_SYNC_SAMPLE_STATUS_FUNCTION = """
CREATE OR REPLACE FUNCTION sync_sample_status() RETURNS trigger AS $$
DECLARE
    point_status operational_status;
BEGIN
    SELECT status INTO point_status FROM measurement_points WHERE id = NEW.point_id;
    IF NOT FOUND THEN
        RETURN NEW;
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

ACTIVATE_POINT_SAMPLES_FUNCTION = """
CREATE FUNCTION activate_point_samples() RETURNS trigger AS $$
BEGIN
    UPDATE weather_forecasts
    SET status = 'active'
    WHERE point_id = NEW.id
      AND status = OLD.status
      AND forecast_date >= current_date - 1;
    RETURN NULL;
END;
$$ LANGUAGE plpgsql
"""

ACTIVATE_POINT_SAMPLES_TRIGGER = """
CREATE TRIGGER measurement_points_activate_samples
AFTER UPDATE OF status ON measurement_points
FOR EACH ROW
WHEN (OLD.status <> 'active' AND NEW.status = 'active')
EXECUTE FUNCTION activate_point_samples()
"""


def upgrade() -> None:
    op.execute("DROP TRIGGER measurement_points_activate_samples ON measurement_points")
    op.execute("DROP FUNCTION activate_point_samples")
    op.execute(SYNC_SAMPLE_STATUS_FUNCTION)


def downgrade() -> None:
    op.execute(PREVIOUS_SYNC_SAMPLE_STATUS_FUNCTION)
    op.execute(ACTIVATE_POINT_SAMPLES_FUNCTION)
    op.execute(ACTIVATE_POINT_SAMPLES_TRIGGER)
