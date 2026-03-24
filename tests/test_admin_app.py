from types import SimpleNamespace

from bot.admin_app import (
    _build_uploaded_guide_path,
    _check_credentials,
    _delete_managed_guide_file,
    _is_pdf,
    _list_start_documents,
    _sanitize_document_filename,
)


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


def test_build_uploaded_guide_path_handles_filename_collisions(tmp_path) -> None:
    settings = SimpleNamespace(guide_links_dir=tmp_path)
    (tmp_path / "material.pdf").write_bytes(b"%PDF-1.7")
    (tmp_path / "material-1.pdf").write_bytes(b"%PDF-1.7")

    path = _build_uploaded_guide_path(settings, "material.pdf")

    assert path.name == "material-2.pdf"


def test_build_uploaded_guide_path_reuses_current_path(tmp_path) -> None:
    settings = SimpleNamespace(guide_links_dir=tmp_path)
    current = tmp_path / "material.pdf"
    current.write_bytes(b"%PDF-1.7")

    path = _build_uploaded_guide_path(settings, "material.pdf", current_path=current)

    assert path == current


def test_delete_managed_guide_file_deletes_only_in_managed_dir(tmp_path) -> None:
    managed_dir = tmp_path / "managed"
    managed_dir.mkdir()
    outside_dir = tmp_path / "outside"
    outside_dir.mkdir()

    managed_file = managed_dir / "guide.pdf"
    managed_file.write_bytes(b"%PDF-1.7")
    outside_file = outside_dir / "guide.pdf"
    outside_file.write_bytes(b"%PDF-1.7")

    settings = SimpleNamespace(guide_links_dir=managed_dir)
    _delete_managed_guide_file(settings, managed_file)
    _delete_managed_guide_file(settings, outside_file)

    assert not managed_file.exists()
    assert outside_file.exists()
