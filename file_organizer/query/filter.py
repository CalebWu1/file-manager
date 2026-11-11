import fnmatch
import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Any

import ollama

from file_organizer.models import (
    ActionOperation,
    ActionType,
    CollisionAction,
    QueryIntent,
    ScannedItem,
)
from file_organizer.planner import PlanBuilder

logger = logging.getLogger(__name__)


class FilterEngine:
    """Evaluates compiled query predicates and semantic checks against directory files."""

    def __init__(
        self,
        ollama_client: Any | None = None,
        model: str = "llama3.2",
        host: str = "http://localhost:11434",
    ):
        self._client = ollama_client
        self.model = model
        self.host = host
        self.planner = PlanBuilder()

    def _semantic_check(self, item: ScannedItem, prompt: str) -> bool:
        """Runs semantic evaluation on item's content peek using Ollama."""
        client = self._client or ollama.Client(host=self.host)
        content = item.content_peek or ""
        messages = [
            {
                "role": "system",
                "content": (
                    "You are a file classifier. Determine if the file content matches the query requirement. "
                    'Respond with JSON: {"matches": true} or {"matches": false}.'
                ),
            },
            {
                "role": "user",
                "content": f"Query requirement: {prompt}\nFile name: {item.filename}\nContent snippet:\n{content}",
            },
        ]
        response = client.chat(
            model=self.model,
            messages=messages,
            format="json",
            options={"temperature": 0.0},
        )
        content = response.get("message", {}).get("content", "{}")
        data = json.loads(content)
        matches_val = data.get("matches", False)
        if isinstance(matches_val, str):
            return matches_val.strip().lower() in ("true", "1", "yes")
        return bool(matches_val)

    def _matches_predicates(self, item: ScannedItem, intent: QueryIntent) -> tuple[bool, str]:
        pred = intent.predicates
        lower_name = item.filename.lower()

        # Check extensions
        if pred.extensions:
            ext_matched = False
            for ext in pred.extensions:
                clean_ext = ext.lower() if ext.startswith(".") else f".{ext.lower()}"
                if lower_name.endswith(clean_ext):
                    ext_matched = True
                    break
            if not ext_matched:
                return False, ""

        # Check name patterns (substring or glob)
        if pred.name_patterns:
            pattern_matched = any(
                p.lower() in lower_name or fnmatch.fnmatch(lower_name, p.lower())
                for p in pred.name_patterns
            )
            if not pattern_matched:
                return False, ""

        # Check size bounds
        if pred.min_size_bytes is not None and item.size_bytes < pred.min_size_bytes:
            return False, ""
        if pred.max_size_bytes is not None and item.size_bytes > pred.max_size_bytes:
            return False, ""

        def _to_aware(dt: datetime | None) -> datetime | None:
            if dt is None:
                return None
            if dt.tzinfo is None or dt.tzinfo.utcoffset(dt) is None:
                return dt.astimezone()
            return dt

        # Check date bounds if provided
        item_mtime = getattr(item, "modified_at", None)
        if item_mtime is None and getattr(item, "modified_time", 0.0):
            try:
                item_mtime = datetime.fromtimestamp(item.modified_time)
            except Exception:
                item_mtime = None

        if item_mtime is not None:
            comp_mtime = _to_aware(item_mtime)
            if pred.modified_after is not None:
                if comp_mtime < _to_aware(pred.modified_after):
                    return False, ""
            if pred.modified_before is not None:
                if comp_mtime > _to_aware(pred.modified_before):
                    return False, ""
        elif pred.modified_after is not None or pred.modified_before is not None:
            return False, ""

        # Check semantic condition if requested
        if pred.needs_semantic_check and pred.semantic_prompt:
            try:
                if not self._semantic_check(item, pred.semantic_prompt):
                    return False, ""
                return True, f"Matched query metadata and semantic check: {pred.semantic_prompt}"
            except Exception as exc:
                logger.warning(f"Semantic check failed/offline ({exc}); retaining item")
                return True, "Matched query metadata filters (semantic check skipped)"

        return True, "Matched query metadata filters"

    def filter_items(
        self,
        items: list[ScannedItem],
        intent: QueryIntent,
        target_dir: Path,
    ) -> list[ActionOperation]:
        target_dir = Path(target_dir)
        matched_ops: list[ActionOperation] = []
        occupied: set[Path] = set()

        for item in items:
            matches, reason = self._matches_predicates(item, intent)
            if not matches:
                continue

            target_path = None
            intended_path = None
            collision_detected = False

            if intent.action == ActionType.MOVE:
                dest_folder = intent.destination_folder or "Organized"
                dest_dir = target_dir / dest_folder
                intended_path = dest_dir / item.filename
                collision_detected = intended_path.exists() or intended_path in occupied
                target_path = (
                    self.planner.resolve_target_path(intended_path, occupied=occupied)
                    if collision_detected
                    else intended_path
                )
                occupied.add(target_path)

            op = ActionOperation(
                source_path=item.path,
                action=intent.action,
                target_path=target_path,
                intended_path=intended_path,
                collision_action=CollisionAction.AUTO_RENAME,
                collision_detected=collision_detected,
                selected=True,
                match_reason=reason,
            )
            matched_ops.append(op)

        return matched_ops
