import pytest
from pydantic import ValidationError

from app.config import Settings


def test_an_unknown_timezone_stops_the_app_from_starting():
    with pytest.raises(ValidationError, match="unknown timezone"):
        Settings(database_url="postgresql+asyncpg://x", timezone="Mars/Base")
