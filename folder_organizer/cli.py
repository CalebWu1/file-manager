import sys
from pathlib import Path
from typing import Optional
import click
from folder_organizer.scanner import Scanner
from folder_organizer.heuristics import HeuristicEngine
from folder_organizer.classifier import LLMClassifier
from folder_organizer.planner import PlanBuilder
from folder_organizer.executor import SafeExecutor
from folder_organizer.tui.app import OrganizerApp


class OrganizerGroup(click.Group):
    """Click Group that supports both root command arguments/options and subcommands."""

    def parse_args(self, ctx: click.Context, args: list) -> list:
        cmd_name = None
        for arg in args:
            if not arg.startswith("-") and arg in self.commands:
                cmd_name = arg
                break

        if cmd_name:
            orig_params = self.params
            try:
                self.params = [p for p in orig_params if isinstance(p, click.Option)]
                res = super().parse_args(ctx, args)
                ctx.params["target_dir"] = None
                return res
            finally:
                self.params = orig_params
        else:
            ctx.allow_interspersed_args = True
            return super().parse_args(ctx, args)


@click.group(cls=OrganizerGroup, invoke_without_command=True)
@click.argument(
    "target_dir",
    required=False,
    type=click.Path(exists=True, file_okay=False, dir_okay=True, path_type=Path),
)
@click.option(
    "--dry-run",
    is_flag=True,
    help="Print proposed plan to stdout without opening TUI or moving files.",
)
@click.option(
    "--no-llm",
    is_flag=True,
    help="Rely strictly on deterministic heuristic rules without calling Ollama.",
)
@click.option(
    "--model",
    default="llama3.2",
    help="Ollama model name (default: llama3.2).",
)
@click.pass_context
def main(
    ctx: click.Context,
    target_dir: Optional[Path] = None,
    dry_run: bool = False,
    no_llm: bool = False,
    model: str = "llama3.2",
):
    """Local LLM Folder Organizer: Organize local folders with heuristics & Llama 3.2."""
    if ctx.invoked_subcommand is not None:
        return

    if not target_dir:
        # Default to Downloads
        target_dir = Path.home() / "Downloads"
        if not target_dir.exists():
            target_dir = Path.cwd()

    click.echo(f"Scanning target folder: {target_dir}")
    scanner = Scanner()
    items = scanner.scan_directory(target_dir)

    if not items:
        click.echo("No unorganized files found.")
        return

    click.echo(f"Found {len(items)} files. Running heuristic pre-filter...")
    heuristics = HeuristicEngine()
    classifications = {}
    ambiguous_items = []

    for item in items:
        h_res = heuristics.classify(item)
        if h_res:
            classifications[item.filename] = h_res
        else:
            ambiguous_items.append(item)

    if ambiguous_items and not no_llm:
        click.echo(
            f"Classifying {len(ambiguous_items)} contextual files using Ollama ({model})..."
        )
        classifier = LLMClassifier(model=model)
        llm_results = classifier.classify_batch(ambiguous_items)
        classifications.update(llm_results)
    elif ambiguous_items:
        click.echo(
            f"Assigning {len(ambiguous_items)} files to fallback categories (LLM disabled)..."
        )
        classifier = LLMClassifier()
        fallback_results = {
            item.filename: classifier._fallback_classify(item)
            for item in ambiguous_items
        }
        classifications.update(fallback_results)

    planner = PlanBuilder()
    plan = planner.build_plan(target_dir, items, classifications)
    executor = SafeExecutor()

    if dry_run:
        click.echo("\n--- Dry-Run Plan ---")
        for op in plan:
            collision = " [Collision -> auto-rename]" if op.collision_detected else ""
            try:
                dest = op.target_path.relative_to(target_dir)
            except ValueError:
                dest = op.target_path
            click.echo(f"• {op.source_path.name} -> {dest}{collision}")
        return

    app = OrganizerApp(plan=plan, target_dir=target_dir, executor=executor)
    app.run()


@main.command()
@click.option("--session-id", default=None, help="Specific session ID to undo.")
def undo(session_id: Optional[str] = None):
    """Reverts a previous organization run and restores files to their original paths."""
    executor = SafeExecutor()
    restored = executor.undo_session(session_id=session_id)
    if restored > 0:
        click.echo(
            f"Successfully restored {restored} files to their original locations."
        )
    else:
        click.echo("No files were restored. History is empty or session not found.")


if __name__ == "__main__":
    main()
