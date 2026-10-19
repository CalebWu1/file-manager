from pathlib import Path
from folder_organizer.models import (
    FileItem,
    ClassificationSource,
    CollisionAction,
    ClassificationResult,
    MoveOperation,
    SessionJournal,
)


def test_file_item_creation():
    item = FileItem(
        path=Path("/tmp/sample.pdf"),
        filename="sample.pdf",
        extension=".pdf",
        size_bytes=1024,
        modified_time=1700000000.0,
        content_peek="Sample invoice contents",
    )
    assert item.filename == "sample.pdf"
    assert item.extension == ".pdf"
    assert item.is_active_download is False


def test_move_operation_and_collision_defaults():
    move = MoveOperation(
        source_path=Path("/tmp/sample.pdf"),
        target_category="Documents",
        target_subfolder="Invoices",
        target_path=Path("/tmp/Documents/Invoices/sample.pdf"),
        source=ClassificationSource.LLM,
        reason="Detected invoice text",
        collision_detected=True,
    )
    assert move.collision_action == CollisionAction.AUTO_RENAME
    assert move.is_selected is True


def test_classification_result_and_session_journal():
    res = ClassificationResult(
        category="Documents",
        subfolder="Invoices",
        confidence=0.95,
        source=ClassificationSource.LLM,
        reason="Detected invoice text",
    )
    assert res.category == "Documents"
    assert res.confidence == 0.95

    journal = SessionJournal(
        session_id="session-123",
        timestamp="2026-10-19T14:00:00",
        target_dir="/tmp/Downloads",
        operations=[{"source": "/tmp/sample.pdf", "target": "/tmp/Documents/sample.pdf"}],
    )
    assert journal.session_id == "session-123"
    assert len(journal.operations) == 1
