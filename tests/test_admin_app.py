from types import SimpleNamespace

from bot.admin_app import _check_credentials, _is_pdf


def test_is_pdf_true() -> None:
    assert _is_pdf("guide.pdf", b"%PDF-1.7 content")


def test_is_pdf_false_extension() -> None:
    assert not _is_pdf("guide.txt", b"%PDF-1.7 content")


def test_check_credentials() -> None:
    settings = SimpleNamespace(admin_username="admin", admin_password="secret")
    assert _check_credentials(settings, "admin", "secret")
    assert not _check_credentials(settings, "admin", "wrong")
