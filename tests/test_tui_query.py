import pytest
from pathlib import Path
from folder_organizer.models import MoveOperation, ScannedItem, ClassificationSource, ActionType
from folder_organizer.tui.app import OrganizerApp
from folder_organizer.tui.screens import QueryModal
from textual.widgets import DataTable, Label, Input


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
