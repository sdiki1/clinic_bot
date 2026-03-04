from types import SimpleNamespace

from bot.admin_app import _check_credentials, _is_pdf, _list_start_documents, _sanitize_document_filename


def test_is_pdf_true() -> None:
    assert _is_pdf("guide.pdf", b"%PDF-1.7 content")


def test_is_pdf_false_extension() -> None:
    assert not _is_pdf("guide.txt", b"%PDF-1.7 content")


def test_check_credentials() -> None:
    settings = SimpleNamespace(admin_username="admin", admin_password="secret")
    assert _check_credentials(settings, "admin", "secret")
    assert not _check_credentials(settings, "admin", "wrong")


def test_sanitize_document_filename() -> None:
    assert _sanitize_document_filename("../terms") == "terms.pdf"
    assert _sanitize_document_filename("my-file.PDF") == "my-file.pdf"


def test_list_start_documents(tmp_path) -> None:
    (tmp_path / "b.pdf").write_bytes(b"%PDF-1.7 b")
    (tmp_path / "a.pdf").write_bytes(b"%PDF-1.7 a")
    (tmp_path / "note.txt").write_text("ignore")
    settings = SimpleNamespace(start_documents_dir=tmp_path)
    docs = _list_start_documents(settings)

    assert [doc.name for doc in docs] == ["a.pdf", "b.pdf"]
