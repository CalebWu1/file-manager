from pathlib import Path
from typing import List, Optional
from textual.app import App, ComposeResult
from textual.widgets import Header, Footer, DataTable, Static, Label
from folder_organizer.models import MoveOperation, CollisionAction
from folder_organizer.executor import SafeExecutor
from folder_organizer.tui.screens import EditDestinationModal, ConfirmExecutionModal


class OrganizerApp(App):
    """Full-screen interactive review dashboard."""

    CSS = """
    DataTable {
        height: 1fr;
        border: solid green;
    }
    #preview-box {
        height: 6;
        border: solid cyan;
        padding: 0 1;
    }
    #edit-dialog, #confirm-dialog {
        padding: 1 2;
        width: 60;
        height: auto;
        border: thick $primary;
        background: $surface;
    }
    """

    BINDINGS = [
        ("space", "toggle_selection", "Toggle Include"),
        ("e", "edit_destination", "Edit Folder"),
        ("c", "cycle_collision", "Cycle Conflict Action"),
        ("a", "toggle_all", "Select All"),
        ("x", "confirm_execute", "Execute Moves"),
        ("q", "quit", "Quit"),
    ]

    def __init__(self, plan: List[MoveOperation], target_dir: Path, executor: SafeExecutor):
        super().__init__()
        self.plan = plan
        self.target_dir = Path(target_dir)
        self.executor = executor
        self.executed = False

    def compose(self) -> ComposeResult:
        yield Header()
        yield Label(f"Target: [b]{self.target_dir}[/b] | Press [b]Space[/b] to toggle, [b]e[/b] to edit, [b]x[/b] to execute")
        yield DataTable(id="table")
        yield Static("Select a row to preview file contents.", id="preview-box")
        yield Footer()

    def on_mount(self) -> None:
        try:
            table = self.query_one(DataTable)
            table.cursor_type = "row"
            table.add_columns("Include", "File Name", "Destination", "Engine", "Collision", "Reason")
            self._refresh_table()
            if self.plan:
                self._update_preview(0)
        except Exception:
            pass

    def _update_preview(self, idx: int) -> None:
        if 0 <= idx < len(self.plan):
            op = self.plan[idx]
            try:
                box = self.query_one("#preview-box", Static)
                box.update(f"[b]Source:[/b] {op.source_path}\n[b]Target:[/b] {op.target_path}\n[b]Reason:[/b] {op.reason}")
            except Exception:
                pass

    def _refresh_table(self) -> None:
        try:
            table = self.query_one(DataTable)
        except Exception:
            return
        prev_cursor_row = table.cursor_row
        table.clear()
        for i, op in enumerate(self.plan):
            include_str = "[X]" if op.is_selected else "[ ]"
            try:
                rel_dest = str(op.target_path.relative_to(self.target_dir))
            except ValueError:
                rel_dest = str(op.target_path)
            engine = op.source.value if op.source else "unknown"
            collision_str = op.collision_action.value if op.collision_detected else "None"
            table.add_row(include_str, op.source_path.name, rel_dest, engine, collision_str, op.reason, key=str(i))
        if prev_cursor_row is not None and prev_cursor_row < len(self.plan):
            table.move_cursor(row=prev_cursor_row)

    def on_data_table_row_highlighted(self, event: DataTable.RowHighlighted) -> None:
        row_key = event.row_key.value
        if row_key is not None and str(row_key).isdigit():
            idx = int(row_key)
            self._update_preview(idx)

    def action_toggle_selection(self) -> None:
        try:
            table = self.query_one(DataTable)
        except Exception:
            return
        if table.cursor_row is not None and 0 <= table.cursor_row < len(self.plan):
            op = self.plan[table.cursor_row]
            op.is_selected = not op.is_selected
            self._refresh_table()

    def action_toggle_all(self) -> None:
        if not self.plan:
            return
        all_selected = all(op.is_selected for op in self.plan)
        for op in self.plan:
            op.is_selected = not all_selected
        self._refresh_table()

    def action_cycle_collision(self) -> None:
        try:
            table = self.query_one(DataTable)
        except Exception:
            return
        if table.cursor_row is not None and 0 <= table.cursor_row < len(self.plan):
            op = self.plan[table.cursor_row]
            if op.collision_detected:
                cycle = {
                    CollisionAction.AUTO_RENAME: CollisionAction.SKIP,
                    CollisionAction.SKIP: CollisionAction.OVERWRITE,
                    CollisionAction.OVERWRITE: CollisionAction.AUTO_RENAME,
                }
                op.collision_action = cycle.get(op.collision_action, CollisionAction.AUTO_RENAME)
                self._refresh_table()

    def action_edit_destination(self) -> None:
        try:
            table = self.query_one(DataTable)
        except Exception:
            return
        if table.cursor_row is not None and 0 <= table.cursor_row < len(self.plan):
            op = self.plan[table.cursor_row]
            curr_str = f"{op.target_category}/{op.target_subfolder}" if op.target_subfolder else op.target_category

            def on_edit_done(result: Optional[str]) -> None:
                if result:
                    parts = [p.strip() for p in result.replace("\\", "/").split("/") if p.strip()]
                    if parts:
                        op.target_category = parts[0]
                        op.target_subfolder = "/".join(parts[1:]) if len(parts) > 1 else None
                        if op.target_subfolder:
                            op.target_path = self.target_dir / op.target_category / op.target_subfolder / op.source_path.name
                        else:
                            op.target_path = self.target_dir / op.target_category / op.source_path.name
                        self._refresh_table()

            self.push_screen(EditDestinationModal(op.source_path.name, curr_str), on_edit_done)

    def action_confirm_execute(self) -> None:
        selected = [op for op in self.plan if op.is_selected]
        if not selected:
            self.notify("No files selected to move!", severity="warning")
            return

        collisions = sum(1 for op in selected if op.collision_detected and op.collision_action == CollisionAction.AUTO_RENAME)

        def on_confirmed(confirmed: Optional[bool]) -> None:
            if confirmed:
                self.executor.execute_plan(self.plan, self.target_dir)
                self.executed = True
                self.exit(result=True)

        self.push_screen(ConfirmExecutionModal(len(selected), collisions), on_confirmed)
