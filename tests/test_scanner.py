from pathlib import Path
import pytest
from folder_organizer.scanner import Scanner
from folder_organizer.utils.file_peek import extract_content_peek

def test_extract_text_peek(tmp_path: Path):
    text_file = tmp_path / "notes.txt"
    text_file.write_text("Hello World! This is a test file for peek.", encoding="utf-8")
    peek = extract_content_peek(text_file)
    assert peek is not None
    assert "Hello World!" in peek

def test_extract_text_peek_max_bytes(tmp_path: Path):
    long_file = tmp_path / "long.md"
    long_file.write_text("A" * 5000, encoding="utf-8")
    peek = extract_content_peek(long_file, max_bytes=100)
    assert peek is not None
    assert len(peek) == 100

def test_extract_unsupported_peek(tmp_path: Path):
    bin_file = tmp_path / "app.exe"
    bin_file.write_bytes(b"\x00\x01\x02\x03")
    assert extract_content_peek(bin_file) is None

def test_extract_pdf_peek(tmp_path: Path):
    import pypdf
    pdf_path = tmp_path / "test.pdf"
    writer = pypdf.PdfWriter()
    writer.add_blank_page(width=72, height=72)
    with open(pdf_path, "wb") as f:
        writer.write(f)
    peek = extract_content_peek(pdf_path)
    # Blank page returns empty string or string; should not error
    assert peek is not None or peek == ""

def test_scanner_filters_hidden_and_active_downloads(tmp_path: Path):
    (tmp_path / "document.pdf").write_text("dummy pdf", encoding="utf-8")
    (tmp_path / "large_file.crdownload").write_text("downloading", encoding="utf-8")
    (tmp_path / "part_file.part").write_text("downloading", encoding="utf-8")
    (tmp_path / "temp.tmp").write_text("downloading", encoding="utf-8")
    (tmp_path / ".hidden_file").write_text("hidden", encoding="utf-8")
    (tmp_path / "subfolder").mkdir()

    scanner = Scanner()
    items = scanner.scan_directory(tmp_path)

    filenames = [item.filename for item in items]
    assert "document.pdf" in filenames
    assert "large_file.crdownload" not in filenames
    assert "part_file.part" not in filenames
    assert "temp.tmp" not in filenames
    assert ".hidden_file" not in filenames
    assert "subfolder" not in filenames  # ignores directories

def test_scanner_system_files_ignored(tmp_path: Path):
    (tmp_path / "desktop.ini").write_text("system", encoding="utf-8")
    (tmp_path / "Thumbs.db").write_text("system", encoding="utf-8")
    (tmp_path / ".DS_Store").write_text("system", encoding="utf-8")
    (tmp_path / "valid.txt").write_text("valid content", encoding="utf-8")

    scanner = Scanner()
    items = scanner.scan_directory(tmp_path)

    filenames = [item.filename for item in items]
    assert filenames == ["valid.txt"]
    assert items[0].content_peek == "valid content"

def test_scanner_tar_gz_compound_extension(tmp_path: Path):
    tar_file = tmp_path / "archive.tar.gz"
    tar_file.write_bytes(b"dummy tar gz")

    scanner = Scanner()
    items = scanner.scan_directory(tmp_path)

    assert len(items) == 1
    assert items[0].extension == ".tar.gz"

def test_scanner_invalid_dir(tmp_path: Path):
    scanner = Scanner()
    with pytest.raises(ValueError, match="does not exist or is not a directory"):
        scanner.scan_directory(tmp_path / "nonexistent")


def test_scanner_active_download_uppercase(tmp_path: Path):
    (tmp_path / "movie.MP4.CRDOWNLOAD").write_bytes(b"downloading...")
    (tmp_path / "real.mp4").write_bytes(b"done")

    scanner = Scanner()
    items = scanner.scan_directory(tmp_path)
    filenames = [item.filename for item in items]
    assert filenames == ["real.mp4"]

