from pathlib import Path
from typing import Optional
import click
from rich.console import Console
from rich.table import Table
from folder_organizer.scanner import Scanner
from folder_organizer.heuristics import HeuristicEngine
from folder_organizer.classifier import LLMClassifier
from folder_organizer.planner import PlanBuilder
from folder_organizer.executor import SafeExecutor
from folder_organizer.tui.app import OrganizerApp
from folder_organizer.models import ActionType, ClassificationSource, MoveOperation
from folder_organizer.query.compiler import KeywordFallbackCompiler, QueryCompiler
from folder_organizer.query.filter import FilterEngine


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



class QueryCommand(click.Command):
    """Click Command supporting optional [DIRECTORY] argument before required PROMPT."""

    def parse_args(self, ctx: click.Context, args: list) -> list:
        pos = []
        i = 0
        while i < len(args):
            arg = args[i]
            if arg.startswith("-"):
                matching_param = next(
                    (
                        p
                        for p in self.params
                        if isinstance(p, click.Option)
                        and (arg in p.opts or arg in p.secondary_opts)
                    ),
                    None,
                )
                if matching_param and not matching_param.is_flag and "=" not in arg:
                    i += 2
                else:
                    i += 1
            else:
                pos.append(i)
                i += 1

        if len(pos) == 1:
            args = list(args)
            args.insert(pos[0], ".")

        return super().parse_args(ctx, args)


def _format_size(size_bytes: int) -> str:
    bytes_float = float(size_bytes)
    for unit in ["B", "KB", "MB", "GB", "TB"]:
        if bytes_float < 1024.0 or unit == "TB":
            return f"{bytes_float:.1f} {unit}" if unit != "B" else f"{int(bytes_float)} B"
        bytes_float /= 1024.0
    return f"{bytes_float:.1f} TB"


@main.command(name="query", cls=QueryCommand)
@click.argument(
    "directory",
    type=click.Path(exists=True, file_okay=False, path_type=Path),
    default=".",
)
@click.argument("prompt", type=str)
@click.option(
    "--dry-run",
    is_flag=True,
    help="Preview matches and actions without modifying files.",
)
@click.option(
    "--no-llm",
    is_flag=True,
    help="Force heuristic keyword & regex query compiler.",
)
@click.option(
    "--model",
    default="llama3.2",
    help="Local Ollama model to use.",
)
@click.option(
    "-y",
    "--yes",
    is_flag=True,
    help="Bypass execution confirmation prompt.",
)
@click.option(
    "-i",
    "--interactive",
    is_flag=True,
    help="Open matching results in Textual TUI.",
)
def query_command(
    directory: Path,
    prompt: str,
    dry_run: bool,
    no_llm: bool,
    model: str,
    yes: bool,
    interactive: bool,
) -> None:
    """Find and act on files in DIRECTORY using natural language PROMPT."""
    scanner = Scanner()
    items = scanner.scan_directory(directory)

    if no_llm:
        compiler = KeywordFallbackCompiler()
        intent = compiler.compile(prompt)
    else:
        compiler = QueryCompiler(model=model)
        intent = compiler.compile(prompt)

    filter_engine = FilterEngine(model=model)
    ops = filter_engine.filter_items(items, intent, target_dir=directory)

    if not ops:
        click.echo(f"No files matched query: '{prompt}'")
        return

    if interactive:
        plan_ops = []
        for op in ops:
            plan_ops.append(
                MoveOperation(
                    source_path=op.source_path,
                    target_path=None if op.action == ActionType.TRASH else (op.target_path or (directory / "Organized" / op.source_path.name)),
                    action=op.action,
                    match_reason=op.match_reason,
                )
            )
        executor = SafeExecutor()
        app = OrganizerApp(
            plan=plan_ops,
            target_dir=directory,
            executor=executor,
            no_llm=no_llm,
            model=model,
            active_query=prompt,
            active_intent=intent,
        )
        app.run()
        return

    console = Console()
    table = Table(
        title=f"Query Results \\[DRY RUN\\] ({len(ops)} match{'es' if len(ops) != 1 else ''})"
        if dry_run
        else f"Query Results ({len(ops)} match{'es' if len(ops) != 1 else ''})"
    )
    table.add_column("Filename", style="bold cyan")
    table.add_column("Size", justify="right")
    table.add_column("Action", style="bold")
    table.add_column("Target Path / Recycle Bin")
    table.add_column("Match Reason", style="dim")

    for op in ops:
        try:
            size_str = _format_size(op.source_path.stat().st_size)
        except OSError:
            size_str = "0 B"

        if op.action == ActionType.TRASH:
            dest_str = "Recycle Bin"
            action_style = "[bold red]TRASH[/bold red]"
        elif op.action == ActionType.MOVE:
            if op.target_path:
                try:
                    dest_str = str(op.target_path.relative_to(directory))
                except ValueError:
                    dest_str = str(op.target_path)
            else:
                dest_str = "-"
            if op.collision_detected:
                dest_str += " [Collision -> auto-rename]"
            action_style = "[bold green]MOVE[/bold green]"
        else:
            dest_str = "-"
            action_style = "[bold blue]FIND[/bold blue]"

        table.add_row(
            op.source_path.name,
            size_str,
            action_style,
            dest_str,
            op.match_reason or intent.reasoning or "Matched filter",
        )

    if dry_run:
        click.echo(f"\n[DRY RUN] Found {len(ops)} file(s) matching query: '{prompt}'")
    console.print(table)

    if dry_run:
        return

    if intent.action == ActionType.FIND:
        return

    # For MOVE or TRASH operations: prompt confirmation unless bypassed with -y/--yes
    if not yes:
        if not click.confirm(f"Execute {len(ops)} operation{'s' if len(ops) != 1 else ''}", default=False):
            click.echo("Aborted.")
            return

    executor = SafeExecutor()
    journal = executor.execute_action_plan(
        ops, target_dir=directory, query_prompt=prompt
    )
    click.echo(f"Successfully executed {len(journal)} operations.")


if __name__ == "__main__":
    main()
