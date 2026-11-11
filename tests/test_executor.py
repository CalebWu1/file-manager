import logging
from pathlib import Path

from file_organizer.executor import SafeExecutor
from file_organizer.models import ClassificationSource, CollisionAction, MoveOperation


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
    assert len(executor._load_history()) == 0


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
    assert len(executor._load_history()) == 0


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
    assert len(executor._load_history()) == 0


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
    assert len(executor._load_history()) == 1


def test_execute_empty_plan_does_not_persist_session(tmp_path: Path):
    journal_path = tmp_path / "history.json"
    executor = SafeExecutor(journal_path=journal_path)

    # 1. Execute an empty plan
    session = executor.execute_plan([], target_dir=tmp_path)
    assert len(session.operations) == 0
    assert len(executor._load_history()) == 0

    # 2. Execute a valid move
    source_file = tmp_path / "real.txt"
    source_file.write_text("data", encoding="utf-8")
    dest_path = tmp_path / "Docs" / "real.txt"
    op = MoveOperation(
        source_path=source_file,
        target_category="Docs",
        target_path=dest_path,
        source=ClassificationSource.HEURISTIC,
        reason="Rule match",
        is_selected=True,
    )
    executor.execute_plan([op], target_dir=tmp_path)
    assert len(executor._load_history()) == 1

    # 3. Execute another empty plan
    executor.execute_plan([], target_dir=tmp_path)
    assert len(executor._load_history()) == 1

    # 4. Undo should restore the real move without being blocked by empty run
    restored = executor.undo_session()
    assert restored == 1
    assert source_file.exists()
    assert not dest_path.exists()
    assert len(executor._load_history()) == 0


def test_undo_session_prunes_empty_sessions_in_history(tmp_path: Path):
    journal_path = tmp_path / "history.json"
    executor = SafeExecutor(journal_path=journal_path)

    # Seed history with an empty session followed by another empty session
    seeded_history = [
        {
            "session_id": "empty_1",
            "timestamp": "2026-01-01",
            "target_dir": str(tmp_path),
            "operations": [],
        },
        {
            "session_id": "empty_2",
            "timestamp": "2026-01-02",
            "target_dir": str(tmp_path),
            "operations": [],
        },
    ]
    executor._save_history(seeded_history)

    # undo_session should prune empty sessions and return 0
    assert executor.undo_session() == 0
    assert executor._load_history() == []

    # Now seed with a real session preceded and followed by empty sessions
    f = tmp_path / "test.txt"
    dest = tmp_path / "Docs" / "test.txt"
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text("hello", encoding="utf-8")

    seeded_history_2 = [
        {
            "session_id": "empty_1",
            "timestamp": "2026-01-01",
            "target_dir": str(tmp_path),
            "operations": [],
        },
        {
            "session_id": "real_1",
            "timestamp": "2026-01-02",
            "target_dir": str(tmp_path),
            "operations": [{"from": str(f.resolve()), "to": str(dest.resolve())}],
        },
        {
            "session_id": "empty_2",
            "timestamp": "2026-01-03",
            "target_dir": str(tmp_path),
            "operations": [],
        },
    ]
    executor._save_history(seeded_history_2)

    # undo_session should locate and undo real_1
    restored = executor.undo_session()
    assert restored == 1
    assert f.exists()
    assert not dest.exists()


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
    executor.execute_plan([op2], target_dir=tmp_path)

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
    expected_path = fake_home / ".file_organizer" / "history.json"
    assert executor.journal_path == expected_path
    assert expected_path.parent.exists()


def test_move_failure_logs_warning(monkeypatch, tmp_path: Path, caplog):
    source_file = tmp_path / "fail.txt"
    source_file.write_text("data", encoding="utf-8")
    dest_path = tmp_path / "Docs" / "fail.txt"

    op = MoveOperation(
        source_path=source_file,
        target_category="Docs",
        target_path=dest_path,
        source=ClassificationSource.HEURISTIC,
        reason="Rule match",
        is_selected=True,
    )

    def mock_move(src, dst):
        raise PermissionError("Access denied simulated")

    import shutil

    monkeypatch.setattr(shutil, "move", mock_move)

    journal_path = tmp_path / "history.json"
    executor = SafeExecutor(journal_path=journal_path)

    with caplog.at_level(logging.WARNING):
        session = executor.execute_plan([op], target_dir=tmp_path)

    assert len(session.operations) == 0
    assert any("Failed to move" in record.message for record in caplog.records)


def test_undo_session_collision_restoration(tmp_path: Path):
    source_file = tmp_path / "notes.txt"
    source_file.write_text("original content", encoding="utf-8")
    dest_path = tmp_path / "Docs" / "notes.txt"

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

    # Now create a new file at original path to simulate a collision during undo
    source_file.write_text("new occupant at original location", encoding="utf-8")

    # Also create notes_restored.txt to test incrementing to (1)
    (tmp_path / "notes_restored.txt").write_text("existing restored", encoding="utf-8")

    restored = executor.undo_session()
    assert restored == 1
    # Original should be untouched
    assert source_file.read_text(encoding="utf-8") == "new occupant at original location"
    # Existing notes_restored.txt should be untouched
    assert (tmp_path / "notes_restored.txt").read_text(encoding="utf-8") == "existing restored"
    # Restored file should be renamed to notes_restored (1).txt
    expected_restored = tmp_path / "notes_restored (1).txt"
    assert expected_restored.exists()
    assert expected_restored.read_text(encoding="utf-8") == "original content"


def test_undo_session_collision_restoration_compound_ext(tmp_path: Path):
    source_file = tmp_path / "archive.tar.gz"
    source_file.write_text("tar content", encoding="utf-8")
    dest_path = tmp_path / "Archives" / "archive.tar.gz"

    op = MoveOperation(
        source_path=source_file,
        target_category="Archives",
        target_path=dest_path,
        source=ClassificationSource.HEURISTIC,
        reason="Archive match",
        is_selected=True,
    )
    journal_path = tmp_path / "history.json"
    executor = SafeExecutor(journal_path=journal_path)
    executor.execute_plan([op], target_dir=tmp_path)
    assert dest_path.exists()

    # Create collision at original location
    source_file.write_text("collision occupant", encoding="utf-8")

    restored = executor.undo_session()
    assert restored == 1
    assert source_file.read_text(encoding="utf-8") == "collision occupant"
    restored_file = tmp_path / "archive_restored.tar.gz"
    assert restored_file.exists()
    assert restored_file.read_text(encoding="utf-8") == "tar content"


def test_execute_plan_defensive_auto_rename_on_collision(tmp_path: Path):
    source_file = tmp_path / "data.csv"
    source_file.write_text("new data", encoding="utf-8")

    dest_dir = tmp_path / "Data"
    dest_dir.mkdir(parents=True, exist_ok=True)
    existing_dest = dest_dir / "data.csv"
    existing_dest.write_text("existing data", encoding="utf-8")

    # Operation has target_path pointing to existing_dest with AUTO_RENAME
    op = MoveOperation(
        source_path=source_file,
        target_category="Data",
        target_path=existing_dest,
        source=ClassificationSource.HEURISTIC,
        reason="Rule match",
        collision_detected=True,
        collision_action=CollisionAction.AUTO_RENAME,
        is_selected=True,
    )
    executor = SafeExecutor(journal_path=tmp_path / "history.json")
    session = executor.execute_plan([op], target_dir=tmp_path)

    assert len(session.operations) == 1
    # Existing data should not be overwritten
    assert existing_dest.read_text(encoding="utf-8") == "existing data"
    # New file should be moved to data (1).csv
    renamed_dest = dest_dir / "data (1).csv"
    assert renamed_dest.exists()
    assert renamed_dest.read_text(encoding="utf-8") == "new data"


def test_execute_plan_defensive_skip_on_collision_with_intended_path(tmp_path: Path):
    source_file = tmp_path / "report.pdf"
    source_file.write_text("report data", encoding="utf-8")

    dest_dir = tmp_path / "Docs"
    dest_dir.mkdir(parents=True, exist_ok=True)
    existing_file = dest_dir / "report.pdf"
    existing_file.write_text("already there", encoding="utf-8")

    op = MoveOperation(
        source_path=source_file,
        target_category="Docs",
        target_path=existing_file,
        intended_path=existing_file,
        source=ClassificationSource.HEURISTIC,
        reason="Rule match",
        collision_detected=True,
        collision_action=CollisionAction.SKIP,
        is_selected=True,
    )
    executor = SafeExecutor(journal_path=tmp_path / "history.json")
    session = executor.execute_plan([op], target_dir=tmp_path)

    # Skipped: nothing moved
    assert len(session.operations) == 0
    assert source_file.exists()
    assert existing_file.read_text(encoding="utf-8") == "already there"
