from datetime import date

from app.enums import EventType
from app.jobs.notifier import Notice


def test_the_message_reads_like_a_whatsapp_text():
    notice = Notice("+5493415550000", "La Esperanza", EventType.FROST, date(2030, 6, 1), 80)

    assert notice.message == "Alerta de helada en La Esperanza: 80% de probabilidad para el 01/06."


def test_every_event_has_a_name():
    for event in EventType:
        assert Notice("+5493415550000", "Lote 1", event, date(2030, 6, 1), 80).message
