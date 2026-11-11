from textual.app import ComposeResult
from textual.containers import Horizontal, Vertical
from textual.screen import ModalScreen
from textual.widgets import Button, Input, Label


class EditDestinationModal(ModalScreen[str | None]):
    """Modal dialog allowing the user to override destination category or subfolder."""

    BINDINGS = [
        ("escape", "cancel", "Cancel"),
    ]

    def __init__(self, filename: str, current_dest: str):
        super().__init__()
        self.filename = filename
        self.current_dest = current_dest

    def compose(self) -> ComposeResult:
        with Vertical(id="edit-dialog"):
            yield Label(f"Edit destination for: [b]{self.filename}[/b]")
            yield Input(value=self.current_dest, id="dest-input")
            with Horizontal():
                yield Button("Save", variant="primary", id="save-btn")
                yield Button("Cancel", variant="default", id="cancel-btn")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "save-btn":
            val = self.query_one("#dest-input", Input).value.strip()
            self.dismiss(val if val else None)
        else:
            self.dismiss(None)

    def on_input_submitted(self, event: Input.Submitted) -> None:
        val = event.value.strip()
        self.dismiss(val if val else None)

    def action_cancel(self) -> None:
        self.dismiss(None)


class ConfirmExecutionModal(ModalScreen[bool]):
    """Confirmation modal prior to moving files."""

    BINDINGS = [
        ("escape", "cancel", "Cancel"),
    ]

    def __init__(self, move_count: int, collision_count: int):
        super().__init__()
        self.move_count = move_count
        self.collision_count = collision_count

    def compose(self) -> ComposeResult:
        with Vertical(id="confirm-dialog"):
            yield Label(f"[b]Ready to organize {self.move_count} files?[/b]")
            if self.collision_count > 0:
                yield Label(
                    f"[yellow]Warning: {self.collision_count} name collisions will be auto-renamed.[/yellow]"
                )
            yield Label("This action can be undone anytime via 'folder-organizer undo'.")
            with Horizontal():
                yield Button("Execute", variant="success", id="confirm-btn")
                yield Button("Back to Review", variant="default", id="back-btn")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        self.dismiss(event.button.id == "confirm-btn")

    def action_cancel(self) -> None:
        self.dismiss(False)


class QueryModal(ModalScreen[str | None]):
    """Modal dialog for natural language query search / filter."""

    BINDINGS = [
        ("escape", "cancel", "Cancel"),
    ]

    def compose(self) -> ComposeResult:
        with Vertical(id="query-dialog"):
            yield Label("[b]Natural Language Query / Filter[/b]")
            yield Input(
                placeholder="Enter query (e.g. 'find all installers' or 'trash old files')... (Esc to cancel)",
                id="query-input",
            )
            with Horizontal():
                yield Button("Submit", variant="primary", id="submit-btn")
                yield Button("Cancel", variant="default", id="cancel-btn")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "submit-btn":
            val = self.query_one("#query-input", Input).value.strip()
            self.dismiss(val if val else None)
        else:
            self.dismiss(None)

    def on_input_submitted(self, event: Input.Submitted) -> None:
        val = event.value.strip()
        self.dismiss(val if val else None)

    def action_cancel(self) -> None:
        self.dismiss(None)
