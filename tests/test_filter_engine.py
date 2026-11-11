from datetime import datetime, timedelta

from file_organizer.models import ActionType, QueryIntent, QueryPredicates, ScannedItem
from file_organizer.query.filter import FilterEngine


def test_filter_engine_extension_match(tmp_path):
    f1 = tmp_path / "setup.exe"
    f2 = tmp_path / "document.pdf"
    f3 = tmp_path / "installer.msi"
    f1.write_bytes(b"exe")
    f2.write_bytes(b"pdf")
    f3.write_bytes(b"msi")

    items = [
        ScannedItem(path=f1, filename="setup.exe", extension=".exe", size_bytes=3),
        ScannedItem(path=f2, filename="document.pdf", extension=".pdf", size_bytes=3),
        ScannedItem(path=f3, filename="installer.msi", extension=".msi", size_bytes=3),
    ]

    intent = QueryIntent(
        raw_query="find all installers",
        action=ActionType.FIND,
        predicates=QueryPredicates(extensions=[".exe", ".msi"]),
    )

    engine = FilterEngine()
    ops = engine.filter_items(items, intent, target_dir=tmp_path)
    matched_names = {op.source_path.name for op in ops}
    assert matched_names == {"setup.exe", "installer.msi"}
    assert all(op.action == ActionType.FIND for op in ops)


def test_filter_engine_compound_extension(tmp_path):
    f = tmp_path / "backup.tar.gz"
    f.write_bytes(b"archive")
    item = ScannedItem(path=f, filename="backup.tar.gz", extension=".tar.gz", size_bytes=7)

    intent = QueryIntent(
        raw_query="find archives",
        action=ActionType.FIND,
        predicates=QueryPredicates(extensions=[".tar.gz", ".zip"]),
    )

    engine = FilterEngine()
    ops = engine.filter_items([item], intent, target_dir=tmp_path)
    assert len(ops) == 1
    assert ops[0].source_path.name == "backup.tar.gz"


def test_filter_engine_size_threshold(tmp_path):
    f1 = tmp_path / "small.mp4"
    f2 = tmp_path / "large.mp4"
    f1.write_bytes(b"a" * 100)
    f2.write_bytes(b"b" * 2000)

    items = [
        ScannedItem(path=f1, filename="small.mp4", extension=".mp4", size_bytes=100),
        ScannedItem(path=f2, filename="large.mp4", extension=".mp4", size_bytes=2000),
    ]

    intent = QueryIntent(
        raw_query="find videos over 1KB",
        action=ActionType.FIND,
        predicates=QueryPredicates(extensions=[".mp4"], min_size_bytes=1000),
    )

    engine = FilterEngine()
    ops = engine.filter_items(items, intent, target_dir=tmp_path)
    assert len(ops) == 1
    assert ops[0].source_path.name == "large.mp4"


def test_filter_engine_name_pattern_and_max_size(tmp_path):
    f1 = tmp_path / "invoice_2026.pdf"
    f2 = tmp_path / "report_2026.pdf"
    f3 = tmp_path / "invoice_old.pdf"

    items = [
        ScannedItem(path=f1, filename="invoice_2026.pdf", extension=".pdf", size_bytes=500),
        ScannedItem(path=f2, filename="report_2026.pdf", extension=".pdf", size_bytes=500),
        ScannedItem(path=f3, filename="invoice_old.pdf", extension=".pdf", size_bytes=5000),
    ]

    intent = QueryIntent(
        raw_query="find invoices under 1KB",
        action=ActionType.FIND,
        predicates=QueryPredicates(
            name_patterns=["invoice*"],
            max_size_bytes=1000,
        ),
    )

    engine = FilterEngine()
    ops = engine.filter_items(items, intent, target_dir=tmp_path)
    assert len(ops) == 1
    assert ops[0].source_path.name == "invoice_2026.pdf"


def test_filter_engine_date_filtering(tmp_path):
    now = datetime.now()
    old_time = now - timedelta(days=10)
    new_time = now - timedelta(days=1)

    f1 = tmp_path / "old.log"
    f2 = tmp_path / "new.log"

    items = [
        ScannedItem(
            path=f1, filename="old.log", extension=".log", size_bytes=10, modified_at=old_time
        ),
        ScannedItem(
            path=f2, filename="new.log", extension=".log", size_bytes=10, modified_at=new_time
        ),
    ]

    cutoff = now - timedelta(days=5)
    intent = QueryIntent(
        raw_query="find logs modified after 5 days ago",
        action=ActionType.FIND,
        predicates=QueryPredicates(modified_after=cutoff),
    )

    engine = FilterEngine()
    ops = engine.filter_items(items, intent, target_dir=tmp_path)
    assert len(ops) == 1
    assert ops[0].source_path.name == "new.log"


def test_filter_engine_move_action_collision_resolution(tmp_path):
    dest_dir = tmp_path / "Installers"
    dest_dir.mkdir()
    existing_dest = dest_dir / "setup.exe"
    existing_dest.write_bytes(b"existing")

    src = tmp_path / "setup.exe"
    src.write_bytes(b"new")

    item = ScannedItem(path=src, filename="setup.exe", extension=".exe", size_bytes=3)
    intent = QueryIntent(
        raw_query="move installers to Installers",
        action=ActionType.MOVE,
        destination_folder="Installers",
        predicates=QueryPredicates(extensions=[".exe"]),
    )

    engine = FilterEngine()
    ops = engine.filter_items([item], intent, target_dir=tmp_path)
    assert len(ops) == 1
    op = ops[0]
    assert op.action == ActionType.MOVE
    assert op.collision_detected is True
    assert op.intended_path == existing_dest
    assert op.target_path == dest_dir / "setup (1).exe"


def test_filter_engine_trash_action(tmp_path):
    f = tmp_path / "temp.tmp"
    item = ScannedItem(path=f, filename="temp.tmp", extension=".tmp", size_bytes=10)
    intent = QueryIntent(
        raw_query="trash temp files",
        action=ActionType.TRASH,
        predicates=QueryPredicates(extensions=[".tmp"]),
    )

    engine = FilterEngine()
    ops = engine.filter_items([item], intent, target_dir=tmp_path)
    assert len(ops) == 1
    assert ops[0].action == ActionType.TRASH
    assert ops[0].target_path is None


def test_filter_engine_semantic_check_matched(tmp_path):
    from unittest.mock import MagicMock

    mock_client = MagicMock()
    mock_client.chat.side_effect = [
        {"message": {"content": '{"matches": true}'}},
        {"message": {"content": '{"matches": false}'}},
    ]

    f1 = tmp_path / "receipt1.pdf"
    f2 = tmp_path / "recipe2.pdf"
    item1 = ScannedItem(
        path=f1,
        filename="receipt1.pdf",
        extension=".pdf",
        size_bytes=100,
        content_peek="Total: $45.00 Tax",
    )
    item2 = ScannedItem(
        path=f2,
        filename="recipe2.pdf",
        extension=".pdf",
        size_bytes=100,
        content_peek="2 cups flour, 1 egg",
    )

    intent = QueryIntent(
        raw_query="find receipts",
        action=ActionType.FIND,
        predicates=QueryPredicates(
            extensions=[".pdf"],
            needs_semantic_check=True,
            semantic_prompt="is this an expense receipt?",
        ),
    )

    engine = FilterEngine(ollama_client=mock_client)
    ops = engine.filter_items([item1, item2], intent, target_dir=tmp_path)
    assert len(ops) == 1
    assert ops[0].source_path.name == "receipt1.pdf"
    assert "semantic check" in ops[0].match_reason


def test_filter_engine_semantic_check_offline_retains_item(tmp_path):
    from unittest.mock import MagicMock

    mock_client = MagicMock()
    mock_client.chat.side_effect = ConnectionError("Ollama server offline")

    f1 = tmp_path / "doc.pdf"
    item = ScannedItem(
        path=f1,
        filename="doc.pdf",
        extension=".pdf",
        size_bytes=100,
        content_peek="Confidential report",
    )

    intent = QueryIntent(
        raw_query="find reports",
        action=ActionType.FIND,
        predicates=QueryPredicates(
            extensions=[".pdf"],
            needs_semantic_check=True,
            semantic_prompt="is this a report?",
        ),
    )

    engine = FilterEngine(ollama_client=mock_client)
    ops = engine.filter_items([item], intent, target_dir=tmp_path)
    assert len(ops) == 1
    assert ops[0].source_path.name == "doc.pdf"
    assert "semantic check skipped" in ops[0].match_reason


def test_filter_engine_package_export():
    from file_organizer.query import FilterEngine as ExportedFilterEngine

    assert ExportedFilterEngine is not None


def test_filter_engine_semantic_check_string_booleans(tmp_path):
    from unittest.mock import MagicMock

    mock_client = MagicMock()
    mock_client.chat.side_effect = [
        {"message": {"content": '{"matches": "true"}'}},
        {"message": {"content": '{"matches": "false"}'}},
        {"message": {"content": '{"matches": "1"}'}},
        {"message": {"content": '{"matches": "yes"}'}},
    ]

    f1 = tmp_path / "f1.txt"
    f2 = tmp_path / "f2.txt"
    f3 = tmp_path / "f3.txt"
    f4 = tmp_path / "f4.txt"
    items = [
        ScannedItem(
            path=f1, filename="f1.txt", extension=".txt", size_bytes=10, content_peek="hello"
        ),
        ScannedItem(
            path=f2, filename="f2.txt", extension=".txt", size_bytes=10, content_peek="world"
        ),
        ScannedItem(
            path=f3, filename="f3.txt", extension=".txt", size_bytes=10, content_peek="foo"
        ),
        ScannedItem(
            path=f4, filename="f4.txt", extension=".txt", size_bytes=10, content_peek="bar"
        ),
    ]

    intent = QueryIntent(
        raw_query="find matching items",
        action=ActionType.FIND,
        predicates=QueryPredicates(
            extensions=[".txt"],
            needs_semantic_check=True,
            semantic_prompt="check relevance",
        ),
    )

    engine = FilterEngine(ollama_client=mock_client)
    ops = engine.filter_items(items, intent, target_dir=tmp_path)
    matched_names = [op.source_path.name for op in ops]
    assert matched_names == ["f1.txt", "f3.txt", "f4.txt"]


def test_filter_engine_timezone_aware_date_filtering(tmp_path):
    from datetime import timezone

    now_utc = datetime.now(timezone.utc)
    old_time_utc = now_utc - timedelta(days=10)
    new_time_utc = now_utc - timedelta(days=1)

    f1 = tmp_path / "old.log"
    f2 = tmp_path / "new.log"

    items_aware = [
        ScannedItem(
            path=f1, filename="old.log", extension=".log", size_bytes=10, modified_at=old_time_utc
        ),
        ScannedItem(
            path=f2, filename="new.log", extension=".log", size_bytes=10, modified_at=new_time_utc
        ),
    ]

    cutoff_aware = now_utc - timedelta(days=5)
    intent_aware = QueryIntent(
        raw_query="find recent logs",
        action=ActionType.FIND,
        predicates=QueryPredicates(modified_after=cutoff_aware),
    )

    engine = FilterEngine()
    ops = engine.filter_items(items_aware, intent_aware, target_dir=tmp_path)
    assert len(ops) == 1
    assert ops[0].source_path.name == "new.log"

    cutoff_naive = datetime.now() - timedelta(days=5)
    intent_naive_pred = QueryIntent(
        raw_query="find recent logs",
        action=ActionType.FIND,
        predicates=QueryPredicates(modified_after=cutoff_naive),
    )
    ops2 = engine.filter_items(items_aware, intent_naive_pred, target_dir=tmp_path)
    assert len(ops2) == 1
    assert ops2[0].source_path.name == "new.log"

    items_naive = [
        ScannedItem(
            path=f1,
            filename="old.log",
            extension=".log",
            size_bytes=10,
            modified_at=datetime.now() - timedelta(days=10),
        ),
        ScannedItem(
            path=f2,
            filename="new.log",
            extension=".log",
            size_bytes=10,
            modified_at=datetime.now() - timedelta(days=1),
        ),
    ]
    ops3 = engine.filter_items(items_naive, intent_aware, target_dir=tmp_path)
    assert len(ops3) == 1
    assert ops3[0].source_path.name == "new.log"
