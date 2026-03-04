from bot.constants import SOURCE_UNKNOWN, premium_emoji_html
from bot.services import extract_source, resolve_start_document_paths


def test_extract_source_known() -> None:
    assert extract_source("instagram") == "instagram"
    assert extract_source("YouTube") == "youtube"


def test_extract_source_unknown() -> None:
    assert extract_source("telegram_ads") == SOURCE_UNKNOWN
    assert extract_source(None) == SOURCE_UNKNOWN


def test_premium_emoji_html() -> None:
    assert premium_emoji_html("123", "🙂") == '<tg-emoji emoji-id="123">🙂</tg-emoji>'


def test_resolve_start_document_paths(tmp_path) -> None:
    docs_dir = tmp_path / "docs"
    docs_dir.mkdir()
    (docs_dir / "2.pdf").write_bytes(b"%PDF-1.7")
    (docs_dir / "1.pdf").write_bytes(b"%PDF-1.7")

    settings = type(
        "S",
        (),
        {
            "start_documents_dir": docs_dir,
            "start_terms_path": tmp_path / "terms.pdf",
            "start_privacy_path": tmp_path / "privacy.pdf",
        },
    )()
    paths = resolve_start_document_paths(settings)

    assert [path.name for path in paths] == ["1.pdf", "2.pdf"]
