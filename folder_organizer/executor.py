import json
import shutil
from datetime import datetime
from pathlib import Path
from typing import List, Optional, Dict, Union
from folder_organizer.models import MoveOperation, SessionJournal, CollisionAction


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
        with open(self.journal_path, "w", encoding="utf-8") as f:
            json.dump(history, f, indent=2)

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

        for op in plan:
            if not op.is_selected:
                continue

            if not op.source_path.exists():
                continue

            dest = op.target_path
            if dest.exists() and op.collision_action == CollisionAction.SKIP:
                continue

            src_resolved = op.source_path.resolve()
            dest_resolved = dest.resolve()

            if src_resolved == dest_resolved:
                continue

            dest.parent.mkdir(parents=True, exist_ok=True)
            try:
                shutil.move(str(op.source_path), str(dest))
                operations_log.append({
                    "from": str(src_resolved),
                    "to": str(dest_resolved),
                })
            except Exception:
                # Log error and continue with remaining batch
                continue

        session = SessionJournal(
            session_id=session_id,
            timestamp=timestamp,
            target_dir=str(target_dir_path.resolve()),
            operations=operations_log,
        )

        history.append(session.model_dump())
        self._save_history(history)
        return session

    def undo_session(self, session_id: Optional[str] = None) -> int:
        history = self._load_history()
        if not history:
            return 0

        target_idx = -1
        if session_id:
            for i, sess in enumerate(history):
                if isinstance(sess, dict) and sess.get("session_id") == session_id:
                    target_idx = i
                    break
        if target_idx == -1 and session_id:
            return 0

        session_data = history.pop(target_idx)
        operations = session_data.get("operations", [])
        restored = 0
        created_dirs = set()

        for op in reversed(operations):
            src_str = op["to"]
            orig_str = op["from"]
            src = Path(src_str)
            orig = Path(orig_str)

            if src.exists():
                orig.parent.mkdir(parents=True, exist_ok=True)
                try:
                    shutil.move(str(src), str(orig))
                    restored += 1
                    created_dirs.add(src.parent)
                except Exception:
                    continue

        # Clean up empty parent directories created during sorting
        target_dir_str = session_data.get("target_dir")
        target_dir_resolved = Path(target_dir_str).resolve() if target_dir_str else None

        for d in created_dirs:
            cur = d
            while cur and cur != cur.parent:
                if target_dir_resolved and cur.resolve() == target_dir_resolved:
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
