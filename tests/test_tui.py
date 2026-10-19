import pytest
from pathlib import Path
from unittest.mock import MagicMock
from folder_organizer.models import MoveOperation, ClassificationSource, CollisionAction
from folder_organizer.executor import SafeExecutor
from folder_organizer.tui.app import OrganizerApp
from folder_organizer.tui.screens import EditDestinationModal, ConfirmExecutionModal
from textual.app import App
from textual.widgets import DataTable, Static, Input, Button


def test_tui_app_initialization(tmp_path: Path):
    op = MoveOperation(
        source_path=tmp_path / "test.pdf",
        target_category="Documents",
        target_path=tmp_path / "Documents" / "test.pdf",
        source=ClassificationSource.HEURISTIC,
        reason="Rule match",
        is_selected=True,
    )
    executor = SafeExecutor(journal_path=tmp_path / "history.json")
    app = OrganizerApp(plan=[op], target_dir=tmp_path, executor=executor)
    assert len(app.plan) == 1
    assert app.target_dir == tmp_path
    assert app.executor == executor
    assert app.executed is False


@pytest.mark.asyncio
async def test_tui_app_mount_and_table_display(tmp_path: Path):
    op1 = MoveOperation(
        source_path=tmp_path / "test1.pdf",
        target_category="Documents",
        target_path=tmp_path / "Documents" / "test1.pdf",
        source=ClassificationSource.HEURISTIC,
        reason="PDF rule",
        is_selected=True,
    )
    op2 = MoveOperation(
        source_path=tmp_path / "photo.png",
        target_category="Images",
        target_path=tmp_path / "Images" / "photo.png",
        source=ClassificationSource.LLM,
        reason="Detected screenshot",
        is_selected=False,
        collision_detected=True,
        collision_action=CollisionAction.AUTO_RENAME,
    )
    executor = SafeExecutor(journal_path=tmp_path / "history.json")
    app = OrganizerApp(plan=[op1, op2], target_dir=tmp_path, executor=executor)

    async with app.run_test() as pilot:
        table = app.query_one(DataTable)
        assert table.row_count == 2
        # Check row 0 contents
        row0 = table.get_row("0")
        assert row0[0] == "[X]"
        assert row0[1] == "test1.pdf"
        assert "Documents" in row0[2]
        assert row0[3] == ClassificationSource.HEURISTIC.value
        assert row0[4] == "None"

        # Check row 1 contents
        row1 = table.get_row("1")
        assert row1[0] == "[ ]"
        assert row1[1] == "photo.png"
        assert row1[3] == ClassificationSource.LLM.value
        assert row1[4] == CollisionAction.AUTO_RENAME.value

        # Check preview box
        preview = app.query_one("#preview-box", Static)
        assert "test1.pdf" in str(preview.render())


@pytest.mark.asyncio
async def test_tui_action_toggle_selection(tmp_path: Path):
    op = MoveOperation(
        source_path=tmp_path / "test.pdf",
        target_category="Documents",
        target_path=tmp_path / "Documents" / "test.pdf",
        source=ClassificationSource.HEURISTIC,
        reason="Rule match",
        is_selected=True,
    )
    executor = SafeExecutor(journal_path=tmp_path / "history.json")
    app = OrganizerApp(plan=[op], target_dir=tmp_path, executor=executor)

    async with app.run_test() as pilot:
        assert app.plan[0].is_selected is True
        # Toggle off
        app.action_toggle_selection()
        assert app.plan[0].is_selected is False
        table = app.query_one(DataTable)
        assert table.get_row("0")[0] == "[ ]"

        # Toggle on
        app.action_toggle_selection()
        assert app.plan[0].is_selected is True
        assert table.get_row("0")[0] == "[X]"


@pytest.mark.asyncio
async def test_tui_action_toggle_all(tmp_path: Path):
    op1 = MoveOperation(
        source_path=tmp_path / "file1.txt",
        target_category="Documents",
        target_path=tmp_path / "Documents" / "file1.txt",
        source=ClassificationSource.HEURISTIC,
        reason="Text file",
        is_selected=True,
    )
    op2 = MoveOperation(
        source_path=tmp_path / "file2.txt",
        target_category="Documents",
        target_path=tmp_path / "Documents" / "file2.txt",
        source=ClassificationSource.HEURISTIC,
        reason="Text file",
        is_selected=False,
    )
    executor = SafeExecutor(journal_path=tmp_path / "history.json")
    app = OrganizerApp(plan=[op1, op2], target_dir=tmp_path, executor=executor)

    async with app.run_test() as pilot:
        # Not all are selected -> action_toggle_all should select all
        app.action_toggle_all()
        assert app.plan[0].is_selected is True
        assert app.plan[1].is_selected is True

        # Now all are selected -> action_toggle_all should deselect all
        app.action_toggle_all()
        assert app.plan[0].is_selected is False
        assert app.plan[1].is_selected is False


@pytest.mark.asyncio
async def test_tui_action_cycle_collision(tmp_path: Path):
    op1 = MoveOperation(
        source_path=tmp_path / "file1.txt",
        target_category="Documents",
        target_path=tmp_path / "Documents" / "file1.txt",
        source=ClassificationSource.HEURISTIC,
        reason="Text file",
        collision_detected=True,
        collision_action=CollisionAction.AUTO_RENAME,
    )
    op2 = MoveOperation(
        source_path=tmp_path / "file2.txt",
        target_category="Documents",
        target_path=tmp_path / "Documents" / "file2.txt",
        source=ClassificationSource.HEURISTIC,
        reason="Text file",
        collision_detected=False,
        collision_action=CollisionAction.AUTO_RENAME,
    )
    executor = SafeExecutor(journal_path=tmp_path / "history.json")
    app = OrganizerApp(plan=[op1, op2], target_dir=tmp_path, executor=executor)

    async with app.run_test() as pilot:
        # On row 0 (op1 with collision)
        assert app.plan[0].collision_action == CollisionAction.AUTO_RENAME
        app.action_cycle_collision()
        assert app.plan[0].collision_action == CollisionAction.SKIP
        app.action_cycle_collision()
        assert app.plan[0].collision_action == CollisionAction.OVERWRITE
        app.action_cycle_collision()
        assert app.plan[0].collision_action == CollisionAction.AUTO_RENAME

        # Move to row 1 (op2 without collision)
        table = app.query_one(DataTable)
        table.move_cursor(row=1)
        app.action_cycle_collision()
        # Should remain unchanged because collision_detected is False
        assert app.plan[1].collision_action == CollisionAction.AUTO_RENAME


@pytest.mark.asyncio
async def test_tui_row_highlighted_updates_preview(tmp_path: Path):
    op1 = MoveOperation(
        source_path=tmp_path / "file1.txt",
        target_category="Documents",
        target_path=tmp_path / "Documents" / "file1.txt",
        source=ClassificationSource.HEURISTIC,
        reason="Reason One",
    )
    op2 = MoveOperation(
        source_path=tmp_path / "file2.txt",
        target_category="Images",
        target_path=tmp_path / "Images" / "file2.txt",
        source=ClassificationSource.LLM,
        reason="Reason Two",
    )
    executor = SafeExecutor(journal_path=tmp_path / "history.json")
    app = OrganizerApp(plan=[op1, op2], target_dir=tmp_path, executor=executor)

    async with app.run_test() as pilot:
        table = app.query_one(DataTable)
        preview = app.query_one("#preview-box", Static)

        # Move cursor to row 1
        table.move_cursor(row=1)
        await pilot.pause()
        assert "Reason Two" in str(preview.render())
        assert "file2.txt" in str(preview.render())


@pytest.mark.asyncio
async def test_edit_destination_modal():
    modal = EditDestinationModal("test.pdf", "Documents/Work")

    class SimpleApp(App):
        def compose(self):
            yield Button("Open", id="open-btn")

    app = SimpleApp()

    async with app.run_test() as pilot:
        results = []

        def cb(res):
            results.append(res)

        app.push_screen(modal, cb)
        await pilot.pause()

        # Check input value
        input_widget = modal.query_one("#dest-input", Input)
        assert input_widget.value == "Documents/Work"

        # Change value and click Save
        input_widget.value = "Archives/2026"
        save_btn = modal.query_one("#save-btn", Button)
        await pilot.click(save_btn)
        await pilot.pause()

        assert results == ["Archives/2026"]


@pytest.mark.asyncio
async def test_edit_destination_modal_cancel():
    modal = EditDestinationModal("test.pdf", "Documents")

    class SimpleApp(App):
        def compose(self):
            yield Button("Open", id="open-btn")

    app = SimpleApp()

    async with app.run_test() as pilot:
        results = []

        def cb(res):
            results.append(res)

        app.push_screen(modal, cb)
        await pilot.pause()

        cancel_btn = modal.query_one("#cancel-btn", Button)
        await pilot.click(cancel_btn)
        await pilot.pause()

        assert results == [None]


@pytest.mark.asyncio
async def test_confirm_execution_modal():
    modal = ConfirmExecutionModal(move_count=3, collision_count=1)

    class SimpleApp(App):
        def compose(self):
            yield Button("Open", id="open-btn")

    app = SimpleApp()

    async with app.run_test() as pilot:
        results = []

        def cb(res):
            results.append(res)

        app.push_screen(modal, cb)
        await pilot.pause()

        confirm_btn = modal.query_one("#confirm-btn", Button)
        await pilot.click(confirm_btn)
        await pilot.pause()

        assert results == [True]


@pytest.mark.asyncio
async def test_confirm_execution_modal_back():
    modal = ConfirmExecutionModal(move_count=3, collision_count=0)

    class SimpleApp(App):
        def compose(self):
            yield Button("Open", id="open-btn")

    app = SimpleApp()

    async with app.run_test() as pilot:
        results = []

        def cb(res):
            results.append(res)

        app.push_screen(modal, cb)
        await pilot.pause()

        back_btn = modal.query_one("#back-btn", Button)
        await pilot.click(back_btn)
        await pilot.pause()

        assert results == [False]


@pytest.mark.asyncio
async def test_tui_action_confirm_execute_no_selection(tmp_path: Path):
    op = MoveOperation(
        source_path=tmp_path / "test.pdf",
        target_category="Documents",
        target_path=tmp_path / "Documents" / "test.pdf",
        source=ClassificationSource.HEURISTIC,
        reason="Rule match",
        is_selected=False,
    )
    executor = MagicMock()
    app = OrganizerApp(plan=[op], target_dir=tmp_path, executor=executor)

    async with app.run_test() as pilot:
        app.action_confirm_execute()
        await pilot.pause()
        # No screen should be pushed
        assert not isinstance(app.screen, ConfirmExecutionModal)
        executor.execute_plan.assert_not_called()
        assert app.executed is False


@pytest.mark.asyncio
async def test_tui_action_confirm_execute_confirmed(tmp_path: Path):
    op = MoveOperation(
        source_path=tmp_path / "test.pdf",
        target_category="Documents",
        target_path=tmp_path / "Documents" / "test.pdf",
        source=ClassificationSource.HEURISTIC,
        reason="Rule match",
        is_selected=True,
    )
    executor = MagicMock()
    app = OrganizerApp(plan=[op], target_dir=tmp_path, executor=executor)

    async with app.run_test() as pilot:
        app.action_confirm_execute()
        await pilot.pause()
        assert isinstance(app.screen, ConfirmExecutionModal)
        confirm_btn = app.screen.query_one("#confirm-btn", Button)
        await pilot.click(confirm_btn)
        await pilot.pause()

        executor.execute_plan.assert_called_once_with([op], tmp_path)
        assert app.executed is True


@pytest.mark.asyncio
async def test_tui_action_edit_destination_flow(tmp_path: Path):
    op = MoveOperation(
        source_path=tmp_path / "invoice.pdf",
        target_category="Documents",
        target_path=tmp_path / "Documents" / "invoice.pdf",
        source=ClassificationSource.HEURISTIC,
        reason="Rule match",
        is_selected=True,
    )
    executor = MagicMock()
    app = OrganizerApp(plan=[op], target_dir=tmp_path, executor=executor)

    async with app.run_test() as pilot:
        app.action_edit_destination()
        await pilot.pause()
        assert isinstance(app.screen, EditDestinationModal)

        input_widget = app.screen.query_one("#dest-input", Input)
        input_widget.value = "Finance/2026/Q1"
        save_btn = app.screen.query_one("#save-btn", Button)
        await pilot.click(save_btn)
        await pilot.pause()

        assert app.plan[0].target_category == "Finance"
        assert app.plan[0].target_subfolder == "2026/Q1"
        assert app.plan[0].target_path == tmp_path / "Finance" / "2026/Q1" / "invoice.pdf"

        table = app.query_one(DataTable)
        assert "Finance" in table.get_row("0")[2]


@pytest.mark.asyncio
async def test_tui_action_edit_destination_cancelled(tmp_path: Path):
    op = MoveOperation(
        source_path=tmp_path / "invoice.pdf",
        target_category="Documents",
        target_path=tmp_path / "Documents" / "invoice.pdf",
        source=ClassificationSource.HEURISTIC,
        reason="Rule match",
        is_selected=True,
    )
    executor = MagicMock()
    app = OrganizerApp(plan=[op], target_dir=tmp_path, executor=executor)

    async with app.run_test() as pilot:
        app.action_edit_destination()
        await pilot.pause()
        assert isinstance(app.screen, EditDestinationModal)

        cancel_btn = app.screen.query_one("#cancel-btn", Button)
        await pilot.click(cancel_btn)
        await pilot.pause()

        assert app.plan[0].target_category == "Documents"
        assert app.plan[0].target_path == tmp_path / "Documents" / "invoice.pdf"


@pytest.mark.asyncio
async def test_tui_action_confirm_execute_rejected(tmp_path: Path):
    op = MoveOperation(
        source_path=tmp_path / "test.pdf",
        target_category="Documents",
        target_path=tmp_path / "Documents" / "test.pdf",
        source=ClassificationSource.HEURISTIC,
        reason="Rule match",
        is_selected=True,
    )
    executor = MagicMock()
    app = OrganizerApp(plan=[op], target_dir=tmp_path, executor=executor)

    async with app.run_test() as pilot:
        app.action_confirm_execute()
        await pilot.pause()
        assert isinstance(app.screen, ConfirmExecutionModal)

        back_btn = app.screen.query_one("#back-btn", Button)
        await pilot.click(back_btn)
        await pilot.pause()

        executor.execute_plan.assert_not_called()
        assert app.executed is False


@pytest.mark.asyncio
async def test_edit_destination_modal_input_submit():
    modal = EditDestinationModal("test.pdf", "Documents/Work")

    class SimpleApp(App):
        def compose(self):
            yield Button("Open", id="open-btn")

    app = SimpleApp()

    async with app.run_test() as pilot:
        results = []

        def cb(res):
            results.append(res)

        app.push_screen(modal, cb)
        await pilot.pause()

        input_widget = modal.query_one("#dest-input", Input)
        input_widget.value = "NewFolder"
        modal.on_input_submitted(Input.Submitted(input_widget, "NewFolder"))
        await pilot.pause()

        assert results == ["NewFolder"]


@pytest.mark.asyncio
async def test_edit_destination_modal_escape():
    modal = EditDestinationModal("test.pdf", "Documents/Work")

    class SimpleApp(App):
        def compose(self):
            yield Button("Open", id="open-btn")

    app = SimpleApp()

    async with app.run_test() as pilot:
        results = []

        def cb(res):
            results.append(res)

        app.push_screen(modal, cb)
        await pilot.pause()

        modal.action_cancel()
        await pilot.pause()

        assert results == [None]


@pytest.mark.asyncio
async def test_confirm_execution_modal_escape():
    modal = ConfirmExecutionModal(move_count=1, collision_count=0)

    class SimpleApp(App):
        def compose(self):
            yield Button("Open", id="open-btn")

    app = SimpleApp()

    async with app.run_test() as pilot:
        results = []

        def cb(res):
            results.append(res)

        app.push_screen(modal, cb)
        await pilot.pause()

        modal.action_cancel()
        await pilot.pause()

        assert results == [False]


@pytest.mark.asyncio
async def test_tui_empty_plan(tmp_path: Path):
    executor = MagicMock()
    app = OrganizerApp(plan=[], target_dir=tmp_path, executor=executor)

    async with app.run_test() as pilot:
        table = app.query_one(DataTable)
        assert table.row_count == 0

        # These actions should be no-ops and not crash
        app.action_toggle_selection()
        app.action_toggle_all()
        app.action_cycle_collision()
        app.action_edit_destination()
        app.action_confirm_execute()
        await pilot.pause()

        assert app.executed is False
        executor.execute_plan.assert_not_called()


@pytest.mark.asyncio
async def test_tui_target_path_outside_target_dir(tmp_path: Path):
    outside_dir = tmp_path.parent / "outside_category"
    op = MoveOperation(
        source_path=tmp_path / "test.pdf",
        target_category="Outside",
        target_path=outside_dir / "test.pdf",
        source=ClassificationSource.HEURISTIC,
        reason="Outside match",
        is_selected=True,
    )
    executor = MagicMock()
    app = OrganizerApp(plan=[op], target_dir=tmp_path, executor=executor)

    async with app.run_test() as pilot:
        table = app.query_one(DataTable)
        row = table.get_row("0")
        assert str(outside_dir / "test.pdf") == row[2]
