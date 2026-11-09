from app.jobs.notifier import Notice


class RecordingNotifier:
    """Keeps what it was asked to send; fails for the point names it is told to."""

    def __init__(self, failing_points=()):
        self.sent: list[Notice] = []
        self.failing_points = set(failing_points)

    async def send(self, notice: Notice) -> None:
        if notice.point_name in self.failing_points:
            raise ConnectionError("WhatsApp is down")
        self.sent.append(notice)
