from bot.constants import SOURCE_UNKNOWN, premium_emoji_html
from bot.services import extract_source


def test_extract_source_known() -> None:
    assert extract_source("instagram") == "instagram"
    assert extract_source("YouTube") == "youtube"


def test_extract_source_unknown() -> None:
    assert extract_source("telegram_ads") == SOURCE_UNKNOWN
    assert extract_source(None) == SOURCE_UNKNOWN


def test_premium_emoji_html() -> None:
    assert premium_emoji_html("123", "🙂") == '<tg-emoji emoji-id="123">🙂</tg-emoji>'
