"""create initial schema

Revision ID: 10b95aff9951
Revises:
Create Date: 2026-11-08 23:57:59.741586
"""

import sqlalchemy as sa
from alembic import op

# The ingestion job is an external system, so the status rules for samples have to live in
# the database. New data takes the point's current status; a technician's manual mark on a
# sample lasts until a new probability arrives for it.
SYNC_SAMPLE_STATUS_FUNCTION = """
CREATE FUNCTION sync_sample_status() RETURNS trigger AS $$
DECLARE
    point_status data_status;
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

SYNC_SAMPLE_STATUS_TRIGGER = """
CREATE TRIGGER weather_forecasts_sync_status
BEFORE INSERT OR UPDATE ON weather_forecasts
FOR EACH ROW EXECUTE FUNCTION sync_sample_status()
"""

revision = "10b95aff9951"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "organizations",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(length=100), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_organizations")),
    )
    op.create_table(
        "users",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(length=100), nullable=False),
        sa.Column("email", sa.String(length=255), nullable=False),
        sa.Column("phone", sa.String(length=20), nullable=False),
        sa.Column("password_hash", sa.String(length=255), nullable=False),
        sa.Column(
            "role",
            sa.Enum("client", "technician", "admin", name="user_role"),
            server_default="client",
            nullable=False,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint("phone ~ '^\\+[1-9][0-9]{7,14}$'", name=op.f("ck_users_phone_e164")),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_users")),
        sa.UniqueConstraint("phone", name=op.f("uq_users_phone")),
    )
    op.create_index(
        "uq_users_email_lower", "users", [sa.literal_column("lower(email)")], unique=True
    )
    op.create_table(
        "measurement_points",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("organization_id", sa.Integer(), nullable=True),
        sa.Column("user_id", sa.Integer(), nullable=True),
        sa.Column("name", sa.String(length=100), nullable=False),
        sa.Column("latitude", sa.Numeric(precision=8, scale=6), nullable=False),
        sa.Column("longitude", sa.Numeric(precision=9, scale=6), nullable=False),
        sa.Column(
            "status",
            sa.Enum("active", "testing", "disabled", name="data_status"),
            server_default="active",
            nullable=False,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "latitude BETWEEN -90 AND 90", name=op.f("ck_measurement_points_latitude_range")
        ),
        sa.CheckConstraint(
            "longitude BETWEEN -180 AND 180", name=op.f("ck_measurement_points_longitude_range")
        ),
        sa.CheckConstraint(
            "num_nonnulls(organization_id, user_id) = 1",
            name=op.f("ck_measurement_points_single_owner"),
        ),
        sa.ForeignKeyConstraint(
            ["organization_id"],
            ["organizations.id"],
            name=op.f("fk_measurement_points_organization_id_organizations"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name=op.f("fk_measurement_points_user_id_users"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_measurement_points")),
        sa.UniqueConstraint(
            "organization_id", "name", name=op.f("uq_measurement_points_organization_id_name")
        ),
        sa.UniqueConstraint("user_id", "name", name=op.f("uq_measurement_points_user_id_name")),
    )
    op.create_table(
        "memberships",
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("organization_id", sa.Integer(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["organization_id"],
            ["organizations.id"],
            name=op.f("fk_memberships_organization_id_organizations"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["user_id"], ["users.id"], name=op.f("fk_memberships_user_id_users"), ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("user_id", "organization_id", name=op.f("pk_memberships")),
    )
    op.create_index(
        op.f("ix_memberships_organization_id"), "memberships", ["organization_id"], unique=False
    )
    op.create_table(
        "alerts",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("point_id", sa.Integer(), nullable=False),
        sa.Column(
            "event_type",
            sa.Enum("frost", "rain", "hail", "strong_wind", "heat_wave", name="event_type"),
            nullable=False,
        ),
        sa.Column("threshold", sa.SmallInteger(), nullable=False),
        sa.Column("is_active", sa.Boolean(), server_default="true", nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint("threshold BETWEEN 1 AND 100", name=op.f("ck_alerts_threshold_range")),
        sa.ForeignKeyConstraint(
            ["point_id"],
            ["measurement_points.id"],
            name=op.f("fk_alerts_point_id_measurement_points"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["user_id"], ["users.id"], name=op.f("fk_alerts_user_id_users"), ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_alerts")),
        sa.UniqueConstraint(
            "user_id", "point_id", "event_type", name=op.f("uq_alerts_user_id_point_id_event_type")
        ),
    )
    op.create_index(op.f("ix_alerts_point_id"), "alerts", ["point_id"], unique=False)
    op.create_table(
        "weather_forecasts",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("point_id", sa.Integer(), nullable=False),
        sa.Column("forecast_date", sa.Date(), nullable=False),
        sa.Column(
            "event_type",
            sa.Enum("frost", "rain", "hail", "strong_wind", "heat_wave", name="event_type"),
            nullable=False,
        ),
        sa.Column("probability", sa.SmallInteger(), nullable=False),
        sa.Column(
            "status",
            sa.Enum("active", "testing", "disabled", name="data_status"),
            server_default="active",
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "probability BETWEEN 0 AND 100", name=op.f("ck_weather_forecasts_probability_range")
        ),
        sa.ForeignKeyConstraint(
            ["point_id"],
            ["measurement_points.id"],
            name=op.f("fk_weather_forecasts_point_id_measurement_points"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_weather_forecasts")),
        sa.UniqueConstraint(
            "point_id",
            "forecast_date",
            "event_type",
            name=op.f("uq_weather_forecasts_point_id_forecast_date_event_type"),
        ),
    )
    op.create_table(
        "notifications",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("alert_id", sa.Integer(), nullable=False),
        sa.Column("forecast_date", sa.Date(), nullable=False),
        sa.Column("probability", sa.SmallInteger(), nullable=False),
        sa.Column(
            "status",
            sa.Enum("pending", "sent", "failed", name="notification_status"),
            server_default="pending",
            nullable=False,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("sent_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(
            ["alert_id"],
            ["alerts.id"],
            name=op.f("fk_notifications_alert_id_alerts"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_notifications")),
        sa.UniqueConstraint(
            "alert_id",
            "forecast_date",
            "probability",
            name=op.f("uq_notifications_alert_id_forecast_date_probability"),
        ),
    )
    op.create_index(
        "ix_notifications_pending",
        "notifications",
        ["id"],
        unique=False,
        postgresql_where=sa.text("status = 'pending'"),
    )
    op.execute(SYNC_SAMPLE_STATUS_FUNCTION)
    op.execute(SYNC_SAMPLE_STATUS_TRIGGER)


def downgrade() -> None:
    op.execute("DROP TRIGGER weather_forecasts_sync_status ON weather_forecasts")
    op.execute("DROP FUNCTION sync_sample_status")
    op.drop_index(
        "ix_notifications_pending",
        table_name="notifications",
        postgresql_where=sa.text("status = 'pending'"),
    )
    op.drop_table("notifications")
    op.drop_table("weather_forecasts")
    op.drop_index(op.f("ix_alerts_point_id"), table_name="alerts")
    op.drop_table("alerts")
    op.drop_index(op.f("ix_memberships_organization_id"), table_name="memberships")
    op.drop_table("memberships")
    op.drop_table("measurement_points")
    op.drop_index("uq_users_email_lower", table_name="users")
    op.drop_table("users")
    op.drop_table("organizations")
    op.execute("DROP TYPE notification_status, event_type, data_status, user_role")
