"""index notices by date and activate samples with their point

Revision ID: 239870af035d
Revises: 10b95aff9951
Create Date: 2026-11-09 00:31:03.607778
"""

from alembic import op

# When a point goes live, the forecasts it got while in testing become real, even if the
# ingestion never sends a different probability for them. Only upcoming days are touched
# (from yesterday, to cover the gap between UTC and local time), so past test data stays
# marked as such. Samples a technician marked differently keep their mark.
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

revision = "239870af035d"
down_revision = "10b95aff9951"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_index(
        op.f("ix_notifications_forecast_date"), "notifications", ["forecast_date"], unique=False
    )
    op.execute(ACTIVATE_POINT_SAMPLES_FUNCTION)
    op.execute(ACTIVATE_POINT_SAMPLES_TRIGGER)


def downgrade() -> None:
    op.execute("DROP TRIGGER measurement_points_activate_samples ON measurement_points")
    op.execute("DROP FUNCTION activate_point_samples")
    op.drop_index(op.f("ix_notifications_forecast_date"), table_name="notifications")
