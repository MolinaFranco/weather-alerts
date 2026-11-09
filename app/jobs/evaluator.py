from datetime import date

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

# Any constant works; it only has to be the same for every worker.
EVALUATION_LOCK = 7_201_001

# Notices go out only on rises, so the highest one is the last one sent. Notices that never
# reached the user don't count, and neither do those below the alert's current threshold,
# so raising the threshold re-arms the alert.
# `notified` is computed once up front: probing notifications per candidate row degrades
# badly when the planner thinks the table is empty, as it does right after a deploy.
EVALUATE_ALERTS = text("""
    WITH notified AS MATERIALIZED (
        SELECT notification.alert_id,
               notification.forecast_date,
               max(notification.probability) AS max_probability
        FROM notifications AS notification
        JOIN alerts AS alert ON alert.id = notification.alert_id
        WHERE notification.forecast_date >= :today
          AND notification.status IN ('pending', 'sent')
          AND notification.probability >= alert.threshold
        GROUP BY notification.alert_id, notification.forecast_date
    )
    INSERT INTO notifications (alert_id, forecast_date, probability)
    SELECT alert.id, forecast.forecast_date, forecast.probability
    FROM alerts AS alert
    JOIN measurement_points AS point ON point.id = alert.point_id
    JOIN weather_forecasts AS forecast
      ON forecast.point_id = alert.point_id AND forecast.event_type = alert.event_type
    LEFT JOIN notified
      ON notified.alert_id = alert.id AND notified.forecast_date = forecast.forecast_date
    WHERE alert.is_active
      AND point.status = 'active'
      AND forecast.status = 'active'
      AND forecast.forecast_date >= :today
      AND forecast.probability >= alert.threshold
      AND (notified.max_probability IS NULL
           OR forecast.probability >= notified.max_probability + :step)
    ON CONFLICT (alert_id, forecast_date, probability) DO NOTHING
""")


async def evaluate(session: AsyncSession, today: date, renotify_step: int) -> int:
    """Queue the notices that are due and return how many. Does not commit."""
    # Two overlapping runs could each miss the other's uncommitted notices and send two
    # messages for one rise. The query covers every alert anyway, so they take turns.
    await session.execute(text("SELECT pg_advisory_xact_lock(:key)"), {"key": EVALUATION_LOCK})
    result = await session.execute(EVALUATE_ALERTS, {"today": today, "step": renotify_step})
    return result.rowcount
