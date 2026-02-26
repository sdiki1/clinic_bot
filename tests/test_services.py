from bot.constants import SOURCE_UNKNOWN
from bot.services import extract_source


def test_extract_source_known() -> None:
    assert extract_source("instagram") == "instagram"
    assert extract_source("YouTube") == "youtube"


def test_extract_source_unknown() -> None:
    assert extract_source("telegram_ads") == SOURCE_UNKNOWN
    assert extract_source(None) == SOURCE_UNKNOWN
