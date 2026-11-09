from datetime import date, datetime
from zoneinfo import ZoneInfo

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

# Only active samples of active points count. A notice is due when the probability reaches
# the threshold for the first time, or when it rises at least `step` over the highest one
# already notified for that alert and day. Re-running it, even concurrently, is harmless:
# a repeated (alert, day, probability) hits the unique constraint and is skipped.
EVALUATE_ALERTS = text("""
    INSERT INTO notifications (alert_id, forecast_date, probability)
    SELECT alert.id, forecast.forecast_date, forecast.probability
    FROM alerts AS alert
    JOIN measurement_points AS point ON point.id = alert.point_id
    JOIN weather_forecasts AS forecast
      ON forecast.point_id = alert.point_id AND forecast.event_type = alert.event_type
    LEFT JOIN LATERAL (
        SELECT max(notice.probability) AS probability
        FROM notifications AS notice
        WHERE notice.alert_id = alert.id AND notice.forecast_date = forecast.forecast_date
    ) AS last_notice ON true
    WHERE alert.is_active
      AND point.status = 'active'
      AND forecast.status = 'active'
      AND forecast.forecast_date >= :today
      AND forecast.probability >= alert.threshold
      AND (last_notice.probability IS NULL
           OR forecast.probability >= last_notice.probability + :step)
    ON CONFLICT DO NOTHING
""")


def local_today(timezone: str) -> date:
    return datetime.now(ZoneInfo(timezone)).date()


async def evaluate(session: AsyncSession, today: date, renotify_step: int) -> int:
    """Create pending notifications for every alert whose threshold is crossed.

    Returns how many were created. The caller owns the transaction.
    """
    result = await session.execute(EVALUATE_ALERTS, {"today": today, "step": renotify_step})
    return result.rowcount
