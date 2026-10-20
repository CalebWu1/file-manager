import pytest
from pathlib import Path
from folder_organizer.models import MoveOperation, ScannedItem, ClassificationSource, ActionType
from folder_organizer.tui.app import OrganizerApp
from folder_organizer.tui.screens import QueryModal
from textual.widgets import DataTable, Label, Input, Static


@pytest.mark.asyncio
async def test_tui_query_keybinding_opens_modal(tmp_path: Path):
    item = ScannedItem(path=tmp_path / "setup.exe", filename="setup.exe", extension=".exe", size_bytes=10)
    op = MoveOperation(source_path=item.path, target_path=tmp_path / "Software" / "setup.exe")
    app = OrganizerApp(plan=[op], target_dir=tmp_path, no_llm=True)

    async with app.run_test() as pilot:
        await pilot.press("slash")
        # Assert QueryModal is pushed to screen stack
        assert len(app.screen_stack) > 1
        assert isinstance(app.screen, QueryModal)


@pytest.mark.asyncio
async def test_tui_query_modal_dismiss_on_escape(tmp_path: Path):
    item = ScannedItem(path=tmp_path / "setup.exe", filename="setup.exe", extension=".exe", size_bytes=10)
    op = MoveOperation(source_path=item.path, target_path=tmp_path / "Software" / "setup.exe")
    app = OrganizerApp(plan=[op], target_dir=tmp_path, no_llm=True)

    async with app.run_test() as pilot:
        await pilot.press("slash")
        assert isinstance(app.screen, QueryModal)
        await pilot.press("escape")
        assert len(app.screen_stack) == 1
        assert not isinstance(app.screen, QueryModal)
        assert app.active_query is None


@pytest.mark.asyncio
async def test_tui_query_filter_find_action(tmp_path: Path):
    file1 = tmp_path / "setup.exe"
    file2 = tmp_path / "notes.txt"
    file1.write_bytes(b"x" * 100)
    file2.write_bytes(b"hello world")

    op1 = MoveOperation(
        source_path=file1,
        target_category="Software",
        target_path=tmp_path / "Software" / "setup.exe",
        source=ClassificationSource.HEURISTIC,
        reason="Installer",
        is_selected=False,
    )
    op2 = MoveOperation(
        source_path=file2,
        target_category="Documents",
        target_path=tmp_path / "Documents" / "notes.txt",
        source=ClassificationSource.HEURISTIC,
        reason="Text file",
        is_selected=True,
    )

    app = OrganizerApp(plan=[op1, op2], target_dir=tmp_path, no_llm=True)

    async with app.run_test() as pilot:
        table = app.query_one(DataTable)
        assert table.row_count == 2

        # Open query modal and type query
        await pilot.press("slash")
        assert isinstance(app.screen, QueryModal)

        inp = app.screen.query_one("#query-input", Input)
        inp.value = "find all installers"
        await pilot.press("enter")

        # Modal should be dismissed
        assert len(app.screen_stack) == 1
        assert app.active_query == "find all installers"

        # Table should be filtered to only setup.exe
        table = app.query_one(DataTable)
        assert table.row_count == 1
        row = table.get_row("0")
        assert row[1] == "setup.exe"
        assert "[FIND]" in row[3]

        # Active query banner should be visible
        banner = app.query_one("#query-banner", Label)
        assert "find all installers" in str(banner.render())


@pytest.mark.asyncio
async def test_tui_query_filter_trash_action(tmp_path: Path):
    file1 = tmp_path / "installer.msi"
    file2 = tmp_path / "report.pdf"
    file1.write_bytes(b"msi content")
    file2.write_bytes(b"pdf content")

    op1 = MoveOperation(
        source_path=file1,
        target_category="Software",
        target_path=tmp_path / "Software" / "installer.msi",
        source=ClassificationSource.HEURISTIC,
        reason="MSI installer",
        is_selected=False,
    )
    op2 = MoveOperation(
        source_path=file2,
        target_category="Documents",
        target_path=tmp_path / "Documents" / "report.pdf",
        source=ClassificationSource.HEURISTIC,
        reason="Report",
        is_selected=False,
    )

    app = OrganizerApp(plan=[op1, op2], target_dir=tmp_path, no_llm=True)

    async with app.run_test() as pilot:
        await pilot.press("slash")
        inp = app.screen.query_one("#query-input", Input)
        inp.value = "trash installers"
        await pilot.press("enter")

        table = app.query_one(DataTable)
        assert table.row_count == 1
        row = table.get_row("0")
        # Preselected
        assert row[0] == "[X]"
        assert row[1] == "installer.msi"
        # Action badge in destination and/or engine
        assert "[TRASH]" in row[2] or "[TRASH]" in row[3]


@pytest.mark.asyncio
async def test_tui_query_filter_move_action_and_collision(tmp_path: Path):
    file1 = tmp_path / "setup.exe"
    file2 = tmp_path / "report.pdf"
    file1.write_bytes(b"setup content")
    file2.write_bytes(b"pdf content")

    # Create an existing collision target in Software
    software_dir = tmp_path / "Software"
    software_dir.mkdir(parents=True, exist_ok=True)
    (software_dir / "setup.exe").write_bytes(b"existing software")

    op1 = MoveOperation(
        source_path=file1,
        target_category="Unorganized",
        target_path=tmp_path / "Unorganized" / "setup.exe",
        source=ClassificationSource.HEURISTIC,
        reason="Unorganized",
        is_selected=True,
    )
    op2 = MoveOperation(
        source_path=file2,
        target_category="Documents",
        target_path=tmp_path / "Documents" / "report.pdf",
        source=ClassificationSource.HEURISTIC,
        reason="Report",
        is_selected=True,
    )

    app = OrganizerApp(plan=[op1, op2], target_dir=tmp_path, no_llm=True)

    async with app.run_test() as pilot:
        await pilot.press("slash")
        inp = app.screen.query_one("#query-input", Input)
        inp.value = "move installers to Software"
        await pilot.press("enter")

        table = app.query_one(DataTable)
        assert table.row_count == 1
        row = table.get_row("0")
        assert row[1] == "setup.exe"
        assert "[MOVE]" in row[3]
        # Target path should be resolved with collision auto-rename (setup (1).exe)
        assert "setup (1).exe" in row[2]


@pytest.mark.asyncio
async def test_tui_query_clear_filter_on_escape(tmp_path: Path):
    file1 = tmp_path / "setup.exe"
    file2 = tmp_path / "notes.txt"
    file1.write_bytes(b"setup")
    file2.write_bytes(b"notes")

    op1 = MoveOperation(
        source_path=file1,
        target_category="Software",
        target_path=tmp_path / "Software" / "setup.exe",
        source=ClassificationSource.HEURISTIC,
        reason="Installer",
        is_selected=True,
    )
    op2 = MoveOperation(
        source_path=file2,
        target_category="Documents",
        target_path=tmp_path / "Documents" / "notes.txt",
        source=ClassificationSource.HEURISTIC,
        reason="Text",
        is_selected=False,
    )

    app = OrganizerApp(plan=[op1, op2], target_dir=tmp_path, no_llm=True)

    async with app.run_test() as pilot:
        table = app.query_one(DataTable)
        assert table.row_count == 2

        # Filter with query
        await pilot.press("slash")
        inp = app.screen.query_one("#query-input", Input)
        inp.value = "find all installers"
        await pilot.press("enter")

        assert table.row_count == 1
        banner = app.query_one("#query-banner", Label)
        assert "find all installers" in str(banner.render())

        # Press escape on main screen to clear query
        await pilot.press("escape")
        assert app.active_query is None
        assert table.row_count == 2
        # Banner should be cleared
        assert "find all installers" not in str(banner.render())


@pytest.mark.asyncio
async def test_tui_query_edit_destination_converts_trash_to_move(tmp_path: Path):
    from folder_organizer.tui.screens import EditDestinationModal

    file1 = tmp_path / "installer.msi"
    file1.write_bytes(b"msi content")

    op = MoveOperation(
        source_path=file1,
        target_category="Software",
        target_path=tmp_path / "Software" / "installer.msi",
        source=ClassificationSource.HEURISTIC,
        reason="MSI installer",
        is_selected=True,
    )

    app = OrganizerApp(plan=[op], target_dir=tmp_path, no_llm=True)

    async with app.run_test() as pilot:
        # 1. Apply TRASH query
        await pilot.press("slash")
        inp = app.screen.query_one("#query-input", Input)
        inp.value = "trash installers"
        await pilot.press("enter")

        assert app.plan[0].action == ActionType.TRASH
        table = app.query_one(DataTable)
        row = table.get_row("0")
        assert "[TRASH]" in row[2] or "[TRASH]" in row[3]

        # 2. Press 'e' to edit destination
        await pilot.press("e")
        assert isinstance(app.screen, EditDestinationModal)

        dest_inp = app.screen.query_one("#dest-input", Input)
        dest_inp.value = "Archived"
        await pilot.press("enter")

        # 3. Verify modal dismissed and op converted to MOVE
        assert len(app.screen_stack) == 1
        assert app.plan[0].action == ActionType.MOVE
        assert app.plan[0].target_category == "Archived"
        assert app.plan[0].target_path == tmp_path / "Archived" / "installer.msi"

        # 4. Table should show [MOVE] badge and Archived destination, not [TRASH]
        table = app.query_one(DataTable)
        row = table.get_row("0")
        assert "[MOVE]" in row[3]
        assert "Archived" in row[2]
        assert "[TRASH]" not in row[2]
        assert "[TRASH]" not in row[3]


@pytest.mark.asyncio
async def test_tui_query_confirm_execute_persists_query_prompt(tmp_path: Path, monkeypatch):
    file1 = tmp_path / "setup.exe"
    file1.write_bytes(b"setup content")

    op = MoveOperation(
        source_path=file1,
        target_category="Software",
        target_path=tmp_path / "Software" / "setup.exe",
        source=ClassificationSource.HEURISTIC,
        reason="Installer",
        is_selected=True,
    )

    app = OrganizerApp(plan=[op], target_dir=tmp_path, no_llm=True)

    captured_prompt = []
    def mock_execute_action_plan(self, plan, target_dir, query_prompt=None):
        captured_prompt.append(query_prompt)
        return []

    from folder_organizer.executor import SafeExecutor
    monkeypatch.setattr(SafeExecutor, "execute_action_plan", mock_execute_action_plan)

    async with app.run_test() as pilot:
        # Apply query
        await pilot.press("slash")
        inp = app.screen.query_one("#query-input", Input)
        inp.value = "find all installers"
        await pilot.press("enter")

        # Confirm execute
        await pilot.press("x")
        # In confirm modal, press Enter on Execute button
        await pilot.press("enter")

        assert len(captured_prompt) == 1
        assert captured_prompt[0] == "find all installers"


@pytest.mark.asyncio
async def test_tui_query_trash_confirm_execute(tmp_path: Path, monkeypatch):
    from folder_organizer.executor import SafeExecutor

    file1 = tmp_path / "installer.msi"
    file1.write_bytes(b"installer content")

    op = MoveOperation(
        source_path=file1,
        target_path=None,
        action=ActionType.TRASH,
        reason="MSI installer",
        is_selected=True,
    )

    journal_file = tmp_path / "history.json"
    executor = SafeExecutor(journal_path=journal_file)
    app = OrganizerApp(plan=[op], target_dir=tmp_path, executor=executor, no_llm=True)

    trashed_files = []

    def mock_send2trash(path_str):
        trashed_files.append(path_str)

    import send2trash
    monkeypatch.setattr(send2trash, "send2trash", mock_send2trash)

    async with app.run_test() as pilot:
        await pilot.press("x")
        await pilot.press("enter")

        assert app.executed is True
        assert len(trashed_files) == 1
        assert trashed_files[0] == str(file1)

        history = executor._load_history()
        assert len(history) == 1
        assert history[0]["operations"][0]["action"] == "TRASH"


@pytest.mark.asyncio
async def test_tui_query_empty_results_clears_preview(tmp_path: Path):
    file1 = tmp_path / "doc.txt"
    file1.write_bytes(b"some content")
    op = MoveOperation(source_path=file1, target_path=tmp_path / "Docs" / "doc.txt", reason="Text doc")
    app = OrganizerApp(plan=[op], target_dir=tmp_path, no_llm=True)

    async with app.run_test() as pilot:
        preview = app.query_one("#preview-box", Static)
        assert "Source:" in str(preview.render())

        await pilot.press("slash")
        inp = app.screen.query_one("#query-input", Input)
        inp.value = "find all installers"
        await pilot.press("enter")

        assert len(app.plan) == 0
        assert "No files match query." in str(preview.render())
