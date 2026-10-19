import json
import logging
import os
import platform
import shutil
import subprocess
from datetime import datetime
from pathlib import Path
from typing import List, Optional, Dict, Union, Set
import send2trash
from folder_organizer.models import (
    MoveOperation,
    SessionJournal,
    CollisionAction,
    COMPOUND_EXTENSIONS,
    ActionOperation,
    ActionType,
    JournalEntry,
    HistorySession,
)
from folder_organizer.planner import PlanBuilder

logger = logging.getLogger(__name__)


class SafeExecutor:
    """Executes file operations safely and maintains an undo history journal."""

    def __init__(self, journal_path: Optional[Union[Path, str]] = None):
        if journal_path:
            self.journal_path = Path(journal_path)
        else:
            home = Path.home()
            self.journal_path = home / ".folder_organizer" / "history.json"
        self.journal_path.parent.mkdir(parents=True, exist_ok=True)

    def _load_history(self) -> List[Dict]:
        if not self.journal_path.exists():
            return []
        try:
            with open(self.journal_path, "r", encoding="utf-8") as f:
                data = json.load(f)
                return data if isinstance(data, list) else []
        except Exception:
            return []

    def _save_history(self, history: List[Dict]) -> None:
        temp_file = self.journal_path.with_suffix(f".tmp.{os.getpid()}")
        try:
            with open(temp_file, "w", encoding="utf-8") as f:
                json.dump(history, f, indent=2)
            os.replace(temp_file, self.journal_path)
        except Exception:
            if temp_file.exists():
                try:
                    temp_file.unlink()
                except OSError:
                    pass
            raise

    def execute_plan(
        self,
        plan: List[MoveOperation],
        target_dir: Optional[Union[Path, str]] = None,
        *,
        session_dir: Optional[Union[Path, str]] = None,
    ) -> SessionJournal:
        actual_target = target_dir if target_dir is not None else session_dir
        if actual_target is None:
            raise ValueError("target_dir or session_dir must be provided")

        target_dir_path = Path(actual_target)
        timestamp = datetime.now().isoformat()
        base_id = datetime.now().strftime("%Y%m%d_%H%M%S")

        history = self._load_history()
        existing_ids = {sess.get("session_id") for sess in history if isinstance(sess, dict)}
        session_id = base_id
        counter = 1
        while session_id in existing_ids:
            session_id = f"{base_id}_{counter}"
            counter += 1

        operations_log = []
        executed_targets: Set[Path] = set()

        for op in plan:
            if not op.is_selected:
                continue

            if not op.source_path.exists():
                continue

            dest = op.target_path
            if op.collision_action == CollisionAction.SKIP:
                if dest.exists() or (op.intended_path and op.intended_path.exists()) or op.collision_detected:
                    continue
            elif op.collision_action == CollisionAction.AUTO_RENAME:
                if dest.exists() or dest in executed_targets:
                    dest = PlanBuilder().resolve_target_path(dest, occupied=executed_targets)

            src_resolved = op.source_path.resolve()
            dest_resolved = dest.resolve()

            if src_resolved == dest_resolved:
                continue

            dest.parent.mkdir(parents=True, exist_ok=True)
            try:
                shutil.move(str(op.source_path), str(dest))
                executed_targets.add(dest_resolved)
                operations_log.append({
                    "from": str(src_resolved),
                    "to": str(dest_resolved),
                })
            except Exception as e:
                logger.warning("Failed to move %s to %s: %s", op.source_path, dest, e)
                continue

        session = SessionJournal(
            session_id=session_id,
            timestamp=timestamp,
            target_dir=str(target_dir_path.resolve()),
            operations=operations_log,
        )

        # Only persist to history journal if actual moves were performed
        if operations_log:
            history.append(session.model_dump())
            self._save_history(history)

        return session

    def execute_action_plan(
        self,
        plan: List[ActionOperation],
        target_dir: Union[Path, str],
        query_prompt: Optional[str] = None,
    ) -> List[JournalEntry]:
        """Executes ActionOperations (MOVE, TRASH) safely within the target directory boundary."""
        target_dir_path = Path(target_dir)
        target_dir_resolved = target_dir_path.resolve()

        # Validate directory confinement upfront for all selected operations
        for op in plan:
            if not op.selected:
                continue
            src_resolved = op.source_path.resolve()
            if not src_resolved.is_relative_to(target_dir_resolved):
                raise ValueError(
                    f"Attempted path traversal: source path '{op.source_path}' is outside target directory '{target_dir}'"
                )
            if op.action == ActionType.MOVE and op.target_path is not None:
                dest_resolved = op.target_path.resolve()
                if not dest_resolved.is_relative_to(target_dir_resolved):
                    raise ValueError(
                        f"Attempted path traversal: target path '{op.target_path}' is outside target directory '{target_dir}'"
                    )

        journal_entries: List[JournalEntry] = []
        executed_targets: Set[Path] = set()

        for op in plan:
            if not op.selected:
                continue

            if not op.source_path.exists():
                continue

            if op.action == ActionType.TRASH:
                try:
                    send2trash.send2trash(str(op.source_path))
                    journal_entries.append(
                        JournalEntry(
                            action=ActionType.TRASH,
                            source=op.source_path,
                            destination=None,
                        )
                    )
                except Exception as e:
                    logger.warning("Failed to trash %s: %s", op.source_path, e)
                    continue

            elif op.action == ActionType.MOVE:
                if op.target_path is None:
                    continue

                dest = op.target_path
                if op.collision_action == CollisionAction.SKIP:
                    if dest.exists() or (op.intended_path and op.intended_path.exists()) or op.collision_detected:
                        continue
                elif op.collision_action == CollisionAction.AUTO_RENAME:
                    if dest.exists() or dest in executed_targets:
                        dest = PlanBuilder().resolve_target_path(dest, occupied=executed_targets)

                src_resolved = op.source_path.resolve()
                dest_resolved = dest.resolve()

                if src_resolved == dest_resolved:
                    continue

                try:
                    dest.parent.mkdir(parents=True, exist_ok=True)
                    shutil.move(str(op.source_path), str(dest))
                    executed_targets.add(dest_resolved)
                    journal_entries.append(
                        JournalEntry(
                            action=ActionType.MOVE,
                            source=op.source_path,
                            destination=dest,
                        )
                    )
                except Exception as e:
                    logger.warning("Failed to move %s to %s: %s", op.source_path, dest, e)
                    continue

        # Only persist to history journal if actual operations were performed
        if journal_entries:
            history = self._load_history()
            existing_ids = {sess.get("session_id") for sess in history if isinstance(sess, dict)}
            base_id = datetime.now().strftime("%Y%m%d_%H%M%S")
            session_id = base_id
            counter = 1
            while session_id in existing_ids:
                session_id = f"{base_id}_{counter}"
                counter += 1

            session_entry = {
                "session_id": session_id,
                "timestamp": datetime.now().isoformat(),
                "target_dir": str(target_dir_resolved),
                "query_prompt": query_prompt,
                "operations": [
                    {
                        "action": entry.action.value,
                        "source": str(entry.source.resolve()),
                        "destination": str(entry.destination.resolve()) if entry.destination else None,
                        "from": str(entry.source.resolve()),
                        "to": str(entry.destination.resolve()) if entry.destination else None,
                        "timestamp": entry.timestamp.isoformat(),
                    }
                    for entry in journal_entries
                ],
            }
            history.append(session_entry)
            self._save_history(history)

        return journal_entries

    def _restore_recycle_bin_item(self, orig: Path) -> bool:
        """Attempts to restore a deleted file from the Windows Recycle Bin using PowerShell COM."""
        if platform.system() != "Windows":
            return False
        try:
            filename_escaped = orig.name.replace("'", "''")
            parent_escaped = str(orig.parent).replace("'", "''")
            ps_script = (
                f"$shell = New-Object -ComObject Shell.Application; "
                f"$rb = $shell.Namespace(10); "
                f"$restored = $false; "
                f"foreach ($item in $rb.Items()) {{ "
                f"if ($item.Name -eq '{filename_escaped}') {{ "
                f"$origLoc = $rb.GetDetailsOf($item, 1); "
                f"if (-not '{parent_escaped}' -or $origLoc -eq '{parent_escaped}') {{ "
                f"$restoreVerb = $item.Verbs() | Where-Object {{ $_.Name -replace '&','' -match 'Restore' }} | Select-Object -First 1; "
                f"if ($restoreVerb) {{ $restoreVerb.DoIt(); $restored = $true; break }} "
                f"}} }} }}; "
                f"if ($restored) {{ Write-Output 'RESTORED' }}"
            )
            res = subprocess.run(
                ["powershell", "-NoProfile", "-NonInteractive", "-Command", ps_script],
                capture_output=True,
                text=True,
                timeout=5,
            )
            return "RESTORED" in res.stdout
        except Exception as e:
            logger.warning("PowerShell Recycle Bin restoration check failed for %s: %s", orig, e)
            return False

    def undo_session(self, session_id: Optional[str] = None) -> int:
        raw_history = self._load_history()
        if not raw_history:
            return 0

        # Clean up any empty session entries in history
        history = [
            sess for sess in raw_history
            if isinstance(sess, dict) and len(sess.get("operations", [])) > 0
        ]
        if not history:
            if len(raw_history) != len(history):
                self._save_history([])
            return 0

        target_idx = -1
        if session_id:
            for i, sess in enumerate(history):
                if sess.get("session_id") == session_id:
                    target_idx = i
                    break
        if target_idx == -1 and session_id:
            return 0

        session_data = history.pop(target_idx)
        operations = session_data.get("operations", [])
        restored = 0
        created_dirs = set()
        restored_targets: Set[Path] = set()

        for op in reversed(operations):
            raw_action = op.get("action", ActionType.MOVE.value if isinstance(op.get("action"), str) else ActionType.MOVE)
            action_str = raw_action.value if hasattr(raw_action, "value") else str(raw_action).upper()

            if action_str == ActionType.TRASH.value:
                orig_str = op.get("source") or op.get("from")
                if not orig_str:
                    continue
                orig = Path(orig_str)
                timestamp_str = op.get("timestamp", "unknown time")
                logger.info("Encountered trashed file in undo session: %s (trashed at %s)", orig_str, timestamp_str)

                # Attempt restoration via Windows PowerShell COM if on Windows
                restored_success = False
                if platform.system() == "Windows":
                    restored_success = self._restore_recycle_bin_item(orig)

                if restored_success:
                    restored += 1
                    logger.info("Successfully restored trashed file from Recycle Bin: %s", orig_str)
                else:
                    logger.warning(
                        "Could not automatically restore trashed file '%s' (trashed at %s). "
                        "Please restore manually from your OS Recycle Bin / Trash.",
                        orig_str,
                        timestamp_str,
                    )
            else:
                src_str = op.get("to") or op.get("destination")
                orig_str = op.get("from") or op.get("source")
                if not src_str or not orig_str:
                    continue
                src = Path(src_str)
                orig = Path(orig_str)

                if src.exists():
                    orig.parent.mkdir(parents=True, exist_ok=True)
                    dest_orig = orig
                    if dest_orig.exists() or dest_orig in restored_targets:
                        lower_name = orig.name.lower()
                        comp_ext = next((ext for ext in COMPOUND_EXTENSIONS if lower_name.endswith(ext)), None)
                        if comp_ext:
                            stem = orig.name[:-len(comp_ext)]
                            suffix = orig.name[-len(comp_ext):]
                        else:
                            stem = orig.stem
                            suffix = orig.suffix

                        candidate = orig.parent / f"{stem}_restored{suffix}"
                        counter = 1
                        while candidate.exists() or candidate in restored_targets:
                            candidate = orig.parent / f"{stem}_restored ({counter}){suffix}"
                            counter += 1
                        dest_orig = candidate

                    try:
                        shutil.move(str(src), str(dest_orig))
                        restored_targets.add(dest_orig.resolve())
                        restored += 1
                        created_dirs.add(src.parent)
                    except Exception as e:
                        logger.warning("Failed to restore %s to %s: %s", src, dest_orig, e)
                        continue

        # Clean up empty parent directories created during sorting
        target_dir_str = session_data.get("target_dir")
        target_dir_resolved = Path(target_dir_str).resolve() if target_dir_str else None

        for d in created_dirs:
            cur = d
            while cur and cur != cur.parent:
                if target_dir_resolved:
                    try:
                        if not cur.resolve().is_relative_to(target_dir_resolved) or cur.resolve() == target_dir_resolved:
                            break
                    except AttributeError:
                        try:
                            cur.resolve().relative_to(target_dir_resolved)
                            if cur.resolve() == target_dir_resolved:
                                break
                        except ValueError:
                            break
                try:
                    if cur.exists() and not any(cur.iterdir()):
                        cur.rmdir()
                        cur = cur.parent
                    else:
                        break
                except OSError:
                    break

        self._save_history(history)
        return restored
