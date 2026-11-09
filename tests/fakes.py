from app.jobs.notifier import Notice


class RecordingNotifier:
    def __init__(self, failing_points=()):
        self.sent: list[Notice] = []
        self.failing_points = set(failing_points)

    async def send(self, notice: Notice) -> None:
        if notice.point_name in self.failing_points:
            raise ConnectionError("WhatsApp is down")
        self.sent.append(notice)
