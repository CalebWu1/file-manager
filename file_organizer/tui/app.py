from pathlib import Path

from textual.app import App, ComposeResult
from textual.css.query import NoMatches
from textual.widgets import DataTable, Footer, Header, Label, Static

from file_organizer.executor import SafeExecutor
from file_organizer.models import (
    ActionOperation,
    ActionType,
    ClassificationSource,
    CollisionAction,
    MoveOperation,
    QueryIntent,
    ScannedItem,
)
from file_organizer.planner import PlanBuilder
from file_organizer.query import FilterEngine, KeywordFallbackCompiler, QueryCompiler
from file_organizer.tui.screens import ConfirmExecutionModal, EditDestinationModal, QueryModal
from file_organizer.utils.file_peek import extract_content_peek


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
    #query-banner {
        background: $accent;
        color: $text;
        padding: 0 1;
    }
    #edit-dialog, #confirm-dialog, #query-dialog {
        padding: 1 2;
        width: 80;
        height: auto;
        border: thick $primary;
        background: $surface;
    }
    """

    BINDINGS = [
        ("slash", "open_query", "Query / Search"),
        ("escape", "clear_query", "Clear Filter"),
        ("space", "toggle_selection", "Toggle Include"),
        ("e", "edit_destination", "Edit Folder"),
        ("c", "cycle_collision", "Cycle Conflict Action"),
        ("a", "toggle_all", "Select All"),
        ("x", "confirm_execute", "Execute Moves"),
        ("q", "quit", "Quit"),
    ]

    def __init__(
        self,
        plan: list[MoveOperation],
        target_dir: Path,
        executor: SafeExecutor | None = None,
        no_llm: bool = False,
        model: str = "llama3.2",
        host: str = "http://localhost:11434",
        scanned_items: list[ScannedItem] | None = None,
        active_query: str | None = None,
        active_intent: QueryIntent | None = None,
    ):
        super().__init__()
        self.plan = plan
        self.original_plan = [op.model_copy(deep=True) for op in plan]
        self.target_dir = Path(target_dir)
        self.executor = executor or SafeExecutor()
        self.executed = False
        self.no_llm = no_llm
        self.model = model
        self.host = host
        self.active_query = active_query
        self.active_intent = active_intent

        if scanned_items is not None:
            self.scanned_items = list(scanned_items)
        else:
            self.scanned_items = []
            for op in self.original_plan:
                p = op.source_path
                size = 0
                mtime = 0.0
                peek = None
                try:
                    if p.exists():
                        st = p.stat()
                        size = st.st_size
                        mtime = st.st_mtime
                        peek = extract_content_peek(p)
                except Exception:
                    pass
                lower_name = p.name.lower()
                ext = ""
                for ce in (".tar.gz", ".tar.bz2", ".tar.xz"):
                    if lower_name.endswith(ce):
                        ext = ce
                        break
                if not ext:
                    ext = p.suffix.lower()
                self.scanned_items.append(
                    ScannedItem(
                        path=p,
                        filename=p.name,
                        extension=ext,
                        size_bytes=size,
                        modified_time=mtime,
                        content_peek=peek,
                    )
                )

    def compose(self) -> ComposeResult:
        yield Header()
        yield Label(
            f"Target: [b]{self.target_dir}[/b] | Press [b]/[/b] to query, [b]Space[/b] to toggle, [b]e[/b] to edit, [b]x[/b] to execute",
            id="status-label",
        )
        yield Label("", id="query-banner")
        yield DataTable(id="table")
        yield Static("Select a row to preview file contents.", id="preview-box")
        yield Footer()

    def on_mount(self) -> None:
        try:
            table = self.query_one(DataTable)
            table.cursor_type = "row"
            table.add_columns(
                "Include", "File Name", "Destination", "Engine", "Collision", "Reason"
            )
            self._refresh_table()
            if self.plan:
                self._update_preview(0)
            elif self.active_query:
                try:
                    box = self.query_one("#preview-box", Static)
                    box.update("No files match query.")
                except NoMatches:
                    pass
            if self.active_query:
                try:
                    banner = self.query_one("#query-banner", Label)
                    banner.update(
                        f"Active Query: [bold yellow]{self.active_query}[/bold yellow] ({len(self.plan)} match{'es' if len(self.plan) != 1 else ''}) | [b]Esc[/b] to clear"
                    )
                except NoMatches:
                    pass
        except NoMatches:
            pass

    def _update_preview(self, idx: int) -> None:
        if 0 <= idx < len(self.plan):
            op = self.plan[idx]
            try:
                box = self.query_one("#preview-box", Static)
                snippet_line = ""
                peek = extract_content_peek(op.source_path, max_bytes=200)
                if peek:
                    first_line = peek.splitlines()[0][:80].strip()
                    if first_line:
                        snippet_line = f"\n[b]Preview:[/b] {first_line}"
                target_disp = op.target_path if op.target_path else "[TRASH] (Recycle Bin)"
                box.update(
                    f"[b]Source:[/b] {op.source_path}\n[b]Target:[/b] {target_disp}\n[b]Reason:[/b] {op.reason}{snippet_line}"
                )
            except NoMatches:
                pass

    def _refresh_table(self) -> None:
        try:
            table = self.query_one(DataTable)
        except NoMatches:
            return
        prev_cursor_row = table.cursor_row
        table.clear()
        for i, op in enumerate(self.plan):
            include_str = "[X]" if op.is_selected else "[ ]"
            op_action = getattr(op, "action", ActionType.MOVE)

            if op_action == ActionType.TRASH:
                rel_dest = "[TRASH]"
                engine = "[TRASH]"
            elif self.active_query is not None and op_action == ActionType.MOVE:
                try:
                    rel_dest = (
                        str(op.target_path.relative_to(self.target_dir)) if op.target_path else "-"
                    )
                except (ValueError, AttributeError):
                    rel_dest = str(op.target_path) if op.target_path else "-"
                engine = "[MOVE]"
            elif self.active_query is not None and op_action == ActionType.FIND:
                try:
                    rel_dest = (
                        str(op.target_path.relative_to(self.target_dir)) if op.target_path else "-"
                    )
                except (ValueError, AttributeError):
                    rel_dest = str(op.target_path) if op.target_path else "-"
                engine = "[FIND]"
            else:
                try:
                    rel_dest = (
                        str(op.target_path.relative_to(self.target_dir)) if op.target_path else "-"
                    )
                except (ValueError, AttributeError):
                    rel_dest = str(op.target_path) if op.target_path else "-"
                engine = op.source.value if getattr(op, "source", None) else "unknown"

            collision_str = op.collision_action.value if op.collision_detected else "None"
            table.add_row(
                include_str,
                op.source_path.name,
                rel_dest,
                engine,
                collision_str,
                op.reason,
                key=str(i),
            )

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
        except NoMatches:
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
        except NoMatches:
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
                base_path = op.intended_path or op.target_path
                if op.collision_action == CollisionAction.AUTO_RENAME:
                    op.target_path = PlanBuilder().resolve_target_path(base_path)
                else:
                    op.target_path = base_path
                self._refresh_table()
                self._update_preview(table.cursor_row)

    def action_edit_destination(self) -> None:
        try:
            table = self.query_one(DataTable)
        except NoMatches:
            return
        if table.cursor_row is not None and 0 <= table.cursor_row < len(self.plan):
            op = self.plan[table.cursor_row]
            curr_str = (
                f"{op.target_category}/{op.target_subfolder}"
                if op.target_subfolder
                else op.target_category
            )

            def on_edit_done(result: str | None) -> None:
                if result:
                    parts = [p.strip() for p in result.replace("\\", "/").split("/") if p.strip()]
                    if parts:
                        op.target_category = parts[0]
                        op.target_subfolder = "/".join(parts[1:]) if len(parts) > 1 else None
                        if op.target_subfolder:
                            intended_path = (
                                self.target_dir
                                / op.target_category
                                / op.target_subfolder
                                / op.source_path.name
                            )
                        else:
                            intended_path = (
                                self.target_dir / op.target_category / op.source_path.name
                            )

                        op.intended_path = intended_path
                        op.collision_detected = intended_path.exists()
                        if op.collision_detected:
                            op.collision_action = CollisionAction.AUTO_RENAME
                            op.target_path = PlanBuilder().resolve_target_path(intended_path)
                        else:
                            op.target_path = intended_path
                        op.action = ActionType.MOVE
                        self._refresh_table()
                        if table.cursor_row is not None:
                            self._update_preview(table.cursor_row)

            self.push_screen(EditDestinationModal(op.source_path.name, curr_str), on_edit_done)

    def action_confirm_execute(self) -> None:
        selected = [op for op in self.plan if op.is_selected]
        if not selected:
            self.notify("No files selected to move!", severity="warning")
            return

        collisions = sum(
            1
            for op in selected
            if op.collision_detected and op.collision_action == CollisionAction.AUTO_RENAME
        )

        def on_confirmed(confirmed: bool | None) -> None:
            if confirmed:
                has_trash = any(getattr(op, "action", None) == ActionType.TRASH for op in selected)
                if has_trash or (self.active_intent is not None) or (self.active_query is not None):
                    action_plan = [
                        ActionOperation(
                            source_path=op.source_path,
                            action=getattr(op, "action", ActionType.MOVE),
                            target_path=op.target_path,
                            intended_path=op.intended_path,
                            collision_action=op.collision_action,
                            collision_detected=op.collision_detected,
                            selected=op.is_selected,
                            match_reason=op.reason,
                        )
                        for op in selected
                    ]
                    self.executor.execute_action_plan(
                        action_plan, self.target_dir, query_prompt=self.active_query
                    )
                else:
                    self.executor.execute_plan(self.plan, self.target_dir)
                self.executed = True
                self.exit(result=True)

        self.push_screen(ConfirmExecutionModal(len(selected), collisions), on_confirmed)

    def action_open_query(self) -> None:
        def on_query_submitted(query_str: str | None) -> None:
            if query_str:
                self.apply_query(query_str)

        self.push_screen(QueryModal(), on_query_submitted)

    def apply_query(self, query_str: str) -> None:
        self.active_query = query_str
        if self.no_llm:
            compiler = KeywordFallbackCompiler()
        else:
            compiler = QueryCompiler(model=self.model, host=self.host)
        intent = compiler.compile(query_str)
        self.active_intent = intent

        engine = FilterEngine(model=self.model, host=self.host)
        action_ops = engine.filter_items(self.scanned_items, intent, self.target_dir)

        action_ops_by_path = {act_op.source_path.resolve(): act_op for act_op in action_ops}

        new_plan: list[MoveOperation] = []
        for op in self.original_plan:
            src_res = op.source_path.resolve()
            if src_res in action_ops_by_path:
                act_op = action_ops_by_path[src_res]
                new_op = op.model_copy(deep=True)
                new_op.action = act_op.action
                new_op.reason = act_op.match_reason or intent.reasoning
                if act_op.action == ActionType.TRASH:
                    new_op.is_selected = True
                    new_op.target_path = None
                    new_op.target_category = "Trash"
                elif act_op.action == ActionType.MOVE:
                    new_op.is_selected = True
                    new_op.target_path = act_op.target_path
                    new_op.intended_path = act_op.intended_path
                    new_op.collision_detected = act_op.collision_detected
                    new_op.collision_action = act_op.collision_action
                    if intent.destination_folder:
                        new_op.target_category = intent.destination_folder
                elif act_op.action == ActionType.FIND:
                    new_op.action = ActionType.FIND
                new_plan.append(new_op)

        original_paths = {op.source_path.resolve() for op in self.original_plan}
        for act_op in action_ops:
            if act_op.source_path.resolve() not in original_paths:
                new_op = MoveOperation(
                    source_path=act_op.source_path,
                    target_category=intent.destination_folder
                    or ("Trash" if act_op.action == ActionType.TRASH else "Organized"),
                    target_path=None
                    if act_op.action == ActionType.TRASH
                    else (act_op.target_path or act_op.source_path),
                    intended_path=act_op.intended_path,
                    source=ClassificationSource.HEURISTIC
                    if self.no_llm
                    else ClassificationSource.LLM,
                    reason=act_op.match_reason or intent.reasoning,
                    collision_detected=act_op.collision_detected,
                    collision_action=act_op.collision_action,
                    is_selected=act_op.selected,
                    action=act_op.action,
                )
                new_plan.append(new_op)

        self.plan = new_plan

        try:
            banner = self.query_one("#query-banner", Label)
            banner.update(
                f"Active Query: [bold yellow]{self.active_query}[/bold yellow] ({len(self.plan)} match{'es' if len(self.plan) != 1 else ''}) | [b]Esc[/b] to clear"
            )
        except NoMatches:
            pass

        self._refresh_table()
        if self.plan:
            self._update_preview(0)
        else:
            try:
                box = self.query_one("#preview-box", Static)
                box.update("No files match query.")
            except NoMatches:
                pass

    def action_clear_query(self) -> None:
        if self.active_query is not None:
            self.clear_query()

    def clear_query(self) -> None:
        self.active_query = None
        self.active_intent = None
        self.plan = [op.model_copy(deep=True) for op in self.original_plan]
        try:
            banner = self.query_one("#query-banner", Label)
            banner.update("")
        except NoMatches:
            pass
        self._refresh_table()
        if self.plan:
            self._update_preview(0)
