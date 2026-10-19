from pathlib import Path
import json
import pytest
from folder_organizer.models import MoveOperation, ClassificationSource, CollisionAction
from folder_organizer.executor import SafeExecutor


def test_execute_plan_and_undo(tmp_path: Path):
    source_file = tmp_path / "sample.txt"
    source_file.write_text("content", encoding="utf-8")

    dest_path = tmp_path / "Documents" / "sample.txt"
    op = MoveOperation(
        source_path=source_file,
        target_category="Documents",
        target_path=dest_path,
        source=ClassificationSource.HEURISTIC,
        reason="Rule match",
        is_selected=True,
    )

    journal_path = tmp_path / "history.json"
    executor = SafeExecutor(journal_path=journal_path)

    # 1. Execute
    session = executor.execute_plan([op], target_dir=tmp_path)
    assert not source_file.exists()
    assert dest_path.exists()
    assert len(session.operations) == 1

    # 2. Undo
    restored_count = executor.undo_session()
    assert restored_count == 1
    assert source_file.exists()
    assert not dest_path.exists()
    assert not (tmp_path / "Documents").exists()  # cleans up empty folder


def test_execute_plan_skips_unselected(tmp_path: Path):
    source_file = tmp_path / "keep.txt"
    source_file.write_text("keep this", encoding="utf-8")
    dest_path = tmp_path / "Docs" / "keep.txt"

    op = MoveOperation(
        source_path=source_file,
        target_category="Docs",
        target_path=dest_path,
        source=ClassificationSource.HEURISTIC,
        reason="Rule match",
        is_selected=False,
    )

    journal_path = tmp_path / "history.json"
    executor = SafeExecutor(journal_path=journal_path)

    session = executor.execute_plan([op], target_dir=tmp_path)
    assert source_file.exists()
    assert not dest_path.exists()
    assert len(session.operations) == 0


def test_execute_plan_skips_nonexistent_source(tmp_path: Path):
    source_file = tmp_path / "missing.txt"
    dest_path = tmp_path / "Docs" / "missing.txt"

    op = MoveOperation(
        source_path=source_file,
        target_category="Docs",
        target_path=dest_path,
        source=ClassificationSource.HEURISTIC,
        reason="Rule match",
        is_selected=True,
    )

    journal_path = tmp_path / "history.json"
    executor = SafeExecutor(journal_path=journal_path)

    session = executor.execute_plan([op], target_dir=tmp_path)
    assert len(session.operations) == 0


def test_execute_plan_collision_skip(tmp_path: Path):
    source_file = tmp_path / "doc.txt"
    source_file.write_text("source content", encoding="utf-8")
    dest_dir = tmp_path / "Docs"
    dest_dir.mkdir(parents=True, exist_ok=True)
    dest_path = dest_dir / "doc.txt"
    dest_path.write_text("existing content", encoding="utf-8")

    op = MoveOperation(
        source_path=source_file,
        target_category="Docs",
        target_path=dest_path,
        source=ClassificationSource.HEURISTIC,
        reason="Rule match",
        collision_action=CollisionAction.SKIP,
        is_selected=True,
    )

    journal_path = tmp_path / "history.json"
    executor = SafeExecutor(journal_path=journal_path)

    session = executor.execute_plan([op], target_dir=tmp_path)
    assert source_file.exists()
    assert dest_path.read_text(encoding="utf-8") == "existing content"
    assert len(session.operations) == 0


def test_execute_plan_collision_overwrite(tmp_path: Path):
    source_file = tmp_path / "doc.txt"
    source_file.write_text("new content", encoding="utf-8")
    dest_dir = tmp_path / "Docs"
    dest_dir.mkdir(parents=True, exist_ok=True)
    dest_path = dest_dir / "doc.txt"
    dest_path.write_text("old content", encoding="utf-8")

    op = MoveOperation(
        source_path=source_file,
        target_category="Docs",
        target_path=dest_path,
        source=ClassificationSource.HEURISTIC,
        reason="Rule match",
        collision_action=CollisionAction.OVERWRITE,
        is_selected=True,
    )

    journal_path = tmp_path / "history.json"
    executor = SafeExecutor(journal_path=journal_path)

    session = executor.execute_plan([op], target_dir=tmp_path)
    assert not source_file.exists()
    assert dest_path.read_text(encoding="utf-8") == "new content"
    assert len(session.operations) == 1


def test_undo_session_by_id(tmp_path: Path):
    journal_path = tmp_path / "history.json"
    executor = SafeExecutor(journal_path=journal_path)

    f1 = tmp_path / "file1.txt"
    f1.write_text("1", encoding="utf-8")
    d1 = tmp_path / "Cat1" / "file1.txt"
    op1 = MoveOperation(
        source_path=f1,
        target_category="Cat1",
        target_path=d1,
        source=ClassificationSource.HEURISTIC,
        reason="Rule match",
        is_selected=True,
    )
    sess1 = executor.execute_plan([op1], target_dir=tmp_path)

    f2 = tmp_path / "file2.txt"
    f2.write_text("2", encoding="utf-8")
    d2 = tmp_path / "Cat2" / "file2.txt"
    op2 = MoveOperation(
        source_path=f2,
        target_category="Cat2",
        target_path=d2,
        source=ClassificationSource.HEURISTIC,
        reason="Rule match",
        is_selected=True,
    )
    sess2 = executor.execute_plan([op2], target_dir=tmp_path)

    # Undo sess1 explicitly by session_id
    restored = executor.undo_session(session_id=sess1.session_id)
    assert restored == 1
    assert f1.exists()
    assert not d1.exists()
    # sess2 should still be moved
    assert not f2.exists()
    assert d2.exists()

    # Now undo default (sess2)
    restored2 = executor.undo_session()
    assert restored2 == 1
    assert f2.exists()
    assert not d2.exists()


def test_undo_session_nonexistent_or_empty(tmp_path: Path):
    journal_path = tmp_path / "history.json"
    executor = SafeExecutor(journal_path=journal_path)

    # Empty journal
    assert executor.undo_session() == 0
    assert executor.undo_session(session_id="unknown_id") == 0


def test_undo_session_nested_dirs_cleanup(tmp_path: Path):
    source_file = tmp_path / "invoice.pdf"
    source_file.write_text("invoice", encoding="utf-8")
    dest_path = tmp_path / "Documents" / "Finance" / "2026" / "invoice.pdf"

    op = MoveOperation(
        source_path=source_file,
        target_category="Documents",
        target_subfolder="Finance/2026",
        target_path=dest_path,
        source=ClassificationSource.HEURISTIC,
        reason="Rule match",
        is_selected=True,
    )

    journal_path = tmp_path / "history.json"
    executor = SafeExecutor(journal_path=journal_path)

    executor.execute_plan([op], target_dir=tmp_path)
    assert dest_path.exists()

    restored = executor.undo_session()
    assert restored == 1
    assert source_file.exists()
    assert not (tmp_path / "Documents" / "Finance" / "2026").exists()
    assert not (tmp_path / "Documents" / "Finance").exists()
    assert not (tmp_path / "Documents").exists()
    # tmp_path itself should still exist!
    assert tmp_path.exists()


def test_undo_session_preserves_nonempty_dirs(tmp_path: Path):
    source_file = tmp_path / "doc.txt"
    source_file.write_text("hello", encoding="utf-8")
    dest_path = tmp_path / "Docs" / "doc.txt"

    # Pre-create another file in Docs
    docs_dir = tmp_path / "Docs"
    docs_dir.mkdir(parents=True, exist_ok=True)
    unrelated_file = docs_dir / "other.txt"
    unrelated_file.write_text("stay", encoding="utf-8")

    op = MoveOperation(
        source_path=source_file,
        target_category="Docs",
        target_path=dest_path,
        source=ClassificationSource.HEURISTIC,
        reason="Rule match",
        is_selected=True,
    )

    journal_path = tmp_path / "history.json"
    executor = SafeExecutor(journal_path=journal_path)

    executor.execute_plan([op], target_dir=tmp_path)
    assert dest_path.exists()
    assert unrelated_file.exists()

    restored = executor.undo_session()
    assert restored == 1
    assert source_file.exists()
    assert not dest_path.exists()
    # Docs should still exist because other.txt is in it
    assert docs_dir.exists()
    assert unrelated_file.exists()


def test_undo_session_missing_dest_file(tmp_path: Path):
    source_file = tmp_path / "file.txt"
    source_file.write_text("test", encoding="utf-8")
    dest_path = tmp_path / "Docs" / "file.txt"

    op = MoveOperation(
        source_path=source_file,
        target_category="Docs",
        target_path=dest_path,
        source=ClassificationSource.HEURISTIC,
        reason="Rule match",
        is_selected=True,
    )

    journal_path = tmp_path / "history.json"
    executor = SafeExecutor(journal_path=journal_path)

    executor.execute_plan([op], target_dir=tmp_path)
    # Simulate user deleting the file after move
    dest_path.unlink()

    restored = executor.undo_session()
    assert restored == 0


def test_corrupted_history_file(tmp_path: Path):
    journal_path = tmp_path / "history.json"
    journal_path.write_text("{not valid json", encoding="utf-8")

    executor = SafeExecutor(journal_path=journal_path)
    assert executor._load_history() == []
    assert executor.undo_session() == 0


def test_default_journal_path(monkeypatch, tmp_path: Path):
    fake_home = tmp_path / "fake_home"
    fake_home.mkdir()
    monkeypatch.setattr(Path, "home", lambda: fake_home)

    executor = SafeExecutor()
    expected_path = fake_home / ".folder_organizer" / "history.json"
    assert executor.journal_path == expected_path
    assert expected_path.parent.exists()
