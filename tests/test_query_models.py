from datetime import datetime
from pathlib import Path

from file_organizer.models import (
    ActionOperation,
    ActionType,
    CollisionAction,
    HistorySession,
    JournalEntry,
    QueryIntent,
    QueryPredicates,
)


def test_action_type_enum():
    assert ActionType.FIND.value == "FIND"
    assert ActionType.MOVE.value == "MOVE"
    assert ActionType.TRASH.value == "TRASH"


def test_query_predicates_defaults():
    pred = QueryPredicates()
    assert pred.extensions == []
    assert pred.name_patterns == []
    assert pred.min_size_bytes is None
    assert pred.max_size_bytes is None
    assert pred.needs_semantic_check is False
    assert pred.semantic_prompt is None


def test_query_intent_construction():
    intent = QueryIntent(
        raw_query="find all installers",
        action=ActionType.FIND,
        predicates=QueryPredicates(extensions=[".exe", ".msi"]),
        reasoning="Searching for installer files",
    )
    assert intent.action == ActionType.FIND
    assert intent.destination_folder is None
    assert intent.predicates.extensions == [".exe", ".msi"]


def test_action_operation_defaults():
    op = ActionOperation(
        source_path=Path("/tmp/setup.exe"),
        action=ActionType.TRASH,
        match_reason="Matches .exe installer rule",
    )
    assert op.action == ActionType.TRASH
    assert op.target_path is None
    assert op.collision_action == CollisionAction.AUTO_RENAME
    assert op.selected is True


def test_journal_entry_trash_support():
    entry = JournalEntry(
        action=ActionType.TRASH,
        source=Path("/tmp/setup.exe"),
        destination=None,
    )
    assert entry.action == ActionType.TRASH
    assert entry.destination is None
    assert isinstance(entry.timestamp, datetime)


def test_history_session():
    now = datetime.now()
    session = HistorySession(
        session_id="session-1",
        timestamp=now,
        target_dir=Path("/tmp"),
        query_prompt="find pdfs",
        operations=[],
    )
    assert session.session_id == "session-1"
    assert session.query_prompt == "find pdfs"
    assert session.operations == []
