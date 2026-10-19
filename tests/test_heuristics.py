from pathlib import Path
from folder_organizer.models import FileItem, ClassificationSource
from folder_organizer.heuristics import HeuristicEngine

def test_heuristic_installer():
    engine = HeuristicEngine()
    item = FileItem(
        path=Path("installer.exe"),
        filename="installer.exe",
        extension=".exe",
        size_bytes=50000,
        modified_time=0.0
    )
    result = engine.classify(item)
    assert result is not None
    assert result.category == "Installers"
    assert result.source == ClassificationSource.HEURISTIC
    assert result.subfolder is None
    assert result.confidence == 1.0
    assert "installer.exe" not in result.reason # rule matched extension

def test_heuristic_archive():
    engine = HeuristicEngine()
    item = FileItem(
        path=Path("backup.tar.gz"),
        filename="backup.tar.gz",
        extension=".tar.gz",
        size_bytes=100000,
        modified_time=0.0
    )
    result = engine.classify(item)
    assert result is not None
    assert result.category == "Archives"
    assert result.source == ClassificationSource.HEURISTIC

def test_heuristic_disk_image_and_font():
    engine = HeuristicEngine()
    iso_item = FileItem(
        path=Path("ubuntu.iso"),
        filename="ubuntu.iso",
        extension=".iso",
        size_bytes=2000000000,
        modified_time=0.0
    )
    iso_result = engine.classify(iso_item)
    assert iso_result is not None
    assert iso_result.category == "Disk Images"
    assert iso_result.source == ClassificationSource.HEURISTIC

    font_item = FileItem(
        path=Path("inter.woff2"),
        filename="inter.woff2",
        extension=".woff2",
        size_bytes=45000,
        modified_time=0.0
    )
    font_result = engine.classify(font_item)
    assert font_result is not None
    assert font_result.category == "Fonts"
    assert font_result.source == ClassificationSource.HEURISTIC

def test_heuristic_case_insensitivity():
    engine = HeuristicEngine()
    item = FileItem(
        path=Path("SETUP.EXE"),
        filename="SETUP.EXE",
        extension=".EXE",
        size_bytes=50000,
        modified_time=0.0
    )
    result = engine.classify(item)
    assert result is not None
    assert result.category == "Installers"

def test_heuristic_ambiguous_returns_none():
    engine = HeuristicEngine()
    item = FileItem(
        path=Path("document.pdf"),
        filename="document.pdf",
        extension=".pdf",
        size_bytes=2048,
        modified_time=0.0
    )
    assert engine.classify(item) is None

def test_heuristic_empty_extension_returns_none():
    engine = HeuristicEngine()
    item = FileItem(
        path=Path("README"),
        filename="README",
        extension="",
        size_bytes=100,
        modified_time=0.0
    )
    assert engine.classify(item) is None


def test_heuristic_dot_normalization():
    engine = HeuristicEngine()
    item = FileItem(
        path=Path("archive.zip"),
        filename="archive.zip",
        extension="zip",
        size_bytes=50000,
        modified_time=0.0,
    )
    result = engine.classify(item)
    assert result is not None
    assert result.category == "Archives"

