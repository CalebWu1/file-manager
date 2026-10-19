from pathlib import Path
from unittest.mock import patch, MagicMock
import logging
import pytest
from folder_organizer.models import ActionOperation, ActionType, CollisionAction
from folder_organizer.executor import SafeExecutor


def test_executor_trash_action(tmp_path):
    test_file = tmp_path / "setup.exe"
    test_file.write_bytes(b"content")

    op = ActionOperation(
        source_path=test_file,
        action=ActionType.TRASH,
        selected=True,
    )

    executor = SafeExecutor(journal_path=tmp_path / "history.json")
    with patch("send2trash.send2trash") as mock_trash:
        journal = executor.execute_action_plan([op], target_dir=tmp_path)
        mock_trash.assert_called_once_with(str(test_file))

    assert len(journal) == 1
    assert journal[0].action == ActionType.TRASH
    assert journal[0].source == test_file
    assert journal[0].destination is None


def test_executor_trash_boundary_violation(tmp_path):
    outside_file = tmp_path.parent / "escape.exe"
    outside_file.write_bytes(b"bad")

    op = ActionOperation(
        source_path=outside_file,
        action=ActionType.TRASH,
        selected=True,
    )

    executor = SafeExecutor(journal_path=tmp_path / "history.json")
    with patch("send2trash.send2trash") as mock_trash:
        with pytest.raises(ValueError, match="Attempted path traversal"):
            executor.execute_action_plan([op], target_dir=tmp_path)
        mock_trash.assert_not_called()


def test_executor_move_action(tmp_path):
    src_file = tmp_path / "document.pdf"
    src_file.write_bytes(b"pdf data")
    dest_file = tmp_path / "Documents" / "document.pdf"

    op = ActionOperation(
        source_path=src_file,
        action=ActionType.MOVE,
        target_path=dest_file,
        selected=True,
    )

    executor = SafeExecutor(journal_path=tmp_path / "history.json")
    journal = executor.execute_action_plan([op], target_dir=tmp_path)

    assert not src_file.exists()
    assert dest_file.exists()
    assert len(journal) == 1
    assert journal[0].action == ActionType.MOVE
    assert journal[0].source == src_file
    assert journal[0].destination == dest_file


def test_executor_move_boundary_violation(tmp_path):
    src_file = tmp_path / "file.txt"
    src_file.write_bytes(b"content")
    outside_dest = tmp_path.parent / "outside.txt"

    op = ActionOperation(
        source_path=src_file,
        action=ActionType.MOVE,
        target_path=outside_dest,
        selected=True,
    )

    executor = SafeExecutor(journal_path=tmp_path / "history.json")
    with pytest.raises(ValueError, match="Attempted path traversal"):
        executor.execute_action_plan([op], target_dir=tmp_path)
    assert src_file.exists()


def test_executor_trash_unselected_skipped(tmp_path):
    test_file = tmp_path / "keep.exe"
    test_file.write_bytes(b"stay")

    op = ActionOperation(
        source_path=test_file,
        action=ActionType.TRASH,
        selected=False,
    )

    executor = SafeExecutor(journal_path=tmp_path / "history.json")
    with patch("send2trash.send2trash") as mock_trash:
        journal = executor.execute_action_plan([op], target_dir=tmp_path)
        mock_trash.assert_not_called()

    assert len(journal) == 0
    assert test_file.exists()


def test_executor_trash_nonexistent_skipped(tmp_path):
    missing_file = tmp_path / "ghost.exe"

    op = ActionOperation(
        source_path=missing_file,
        action=ActionType.TRASH,
        selected=True,
    )

    executor = SafeExecutor(journal_path=tmp_path / "history.json")
    with patch("send2trash.send2trash") as mock_trash:
        journal = executor.execute_action_plan([op], target_dir=tmp_path)
        mock_trash.assert_not_called()

    assert len(journal) == 0


def test_executor_trash_error_logged(tmp_path, caplog):
    test_file = tmp_path / "locked.exe"
    test_file.write_bytes(b"locked")

    op = ActionOperation(
        source_path=test_file,
        action=ActionType.TRASH,
        selected=True,
    )

    executor = SafeExecutor(journal_path=tmp_path / "history.json")
    with patch("send2trash.send2trash", side_effect=PermissionError("File locked")):
        with caplog.at_level(logging.WARNING):
            journal = executor.execute_action_plan([op], target_dir=tmp_path)

    assert len(journal) == 0
    assert any("Failed to trash" in record.message for record in caplog.records)


def test_executor_action_plan_persists_to_history(tmp_path):
    test_file = tmp_path / "old.exe"
    test_file.write_bytes(b"old")

    op = ActionOperation(
        source_path=test_file,
        action=ActionType.TRASH,
        selected=True,
    )

    journal_path = tmp_path / "history.json"
    executor = SafeExecutor(journal_path=journal_path)
    with patch("send2trash.send2trash"):
        executor.execute_action_plan([op], target_dir=tmp_path, query_prompt="trash old exe")

    history = executor._load_history()
    assert len(history) == 1
    session = history[0]
    assert session["query_prompt"] == "trash old exe"
    assert len(session["operations"]) == 1
    assert session["operations"][0]["action"] == "TRASH"


def test_executor_action_plan_empty_does_not_persist(tmp_path):
    journal_path = tmp_path / "history.json"
    executor = SafeExecutor(journal_path=journal_path)
    journal = executor.execute_action_plan([], target_dir=tmp_path)

    assert len(journal) == 0
    assert len(executor._load_history()) == 0


def test_undo_session_trash_restoration(tmp_path, caplog):
    test_file = tmp_path / "test.exe"
    test_file.write_bytes(b"test")

    op = ActionOperation(
        source_path=test_file,
        action=ActionType.TRASH,
        selected=True,
    )

    journal_path = tmp_path / "history.json"
    executor = SafeExecutor(journal_path=journal_path)
    with patch("send2trash.send2trash"):
        executor.execute_action_plan([op], target_dir=tmp_path)

    # 1. Test failed restoration logs advisory
    with patch.object(executor, "_restore_recycle_bin_item", return_value=False):
        with caplog.at_level(logging.WARNING):
            restored = executor.undo_session()
            assert restored == 0
            assert any("Could not automatically restore trashed file" in record.message for record in caplog.records)

    # 2. Test successful restoration
    with patch("send2trash.send2trash"):
        executor.execute_action_plan([op], target_dir=tmp_path)

    with patch.object(executor, "_restore_recycle_bin_item", return_value=True):
        restored = executor.undo_session()
        assert restored == 1


def test_undo_session_move_action_from_action_plan(tmp_path):
    src_file = tmp_path / "data.csv"
    src_file.write_bytes(b"col1,col2")
    dest_file = tmp_path / "CSV" / "data.csv"

    op = ActionOperation(
        source_path=src_file,
        action=ActionType.MOVE,
        target_path=dest_file,
        selected=True,
    )

    journal_path = tmp_path / "history.json"
    executor = SafeExecutor(journal_path=journal_path)
    executor.execute_action_plan([op], target_dir=tmp_path)

    assert not src_file.exists()
    assert dest_file.exists()

    restored = executor.undo_session()
    assert restored == 1
    assert src_file.exists()
    assert not dest_file.exists()
