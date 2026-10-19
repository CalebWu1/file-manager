from pathlib import Path
from typing import List, Dict, Optional, Set
from folder_organizer.models import (
    FileItem,
    ClassificationResult,
    ClassificationSource,
    MoveOperation,
    CollisionAction,
)


class PlanBuilder:
    """Computes move operations and resolves target collisions."""

    def resolve_target_path(
        self, target_path: Path, occupied: Optional[Set[Path]] = None
    ) -> Path:
        """If target_path exists on disk or is in occupied set, finds next available 'name (N).ext'."""
        is_taken = lambda p: p.exists() or (occupied is not None and p in occupied)
        if not is_taken(target_path):
            return target_path

        stem = target_path.stem
        suffix = target_path.suffix
        parent = target_path.parent

        counter = 1
        while True:
            candidate = parent / f"{stem} ({counter}){suffix}"
            if not is_taken(candidate):
                return candidate
            counter += 1

    def build_plan(
        self,
        base_dir: Optional[Path] = None,
        items: Optional[List[FileItem]] = None,
        classifications: Optional[Dict[str, ClassificationResult]] = None,
        destination_root: Optional[Path] = None,
        target_dir: Optional[Path] = None,
    ) -> List[MoveOperation]:
        effective_base = base_dir or target_dir
        if effective_base is None:
            raise ValueError("base_dir or target_dir must be provided")

        if items is None:
            items = []
        if classifications is None:
            classifications = {}

        root = destination_root or effective_base
        plan: List[MoveOperation] = []
        planned_targets: Set[Path] = set()

        for item in items:
            res = classifications.get(item.filename)
            category = res.category if res else "Other"
            subfolder = res.subfolder if res else None
            source = res.source if res else ClassificationSource.MANUAL
            reason = res.reason if res else "Unclassified"

            if subfolder:
                dest_dir = root / category / subfolder
            else:
                dest_dir = root / category

            intended_path = dest_dir / item.filename
            collision_detected = intended_path.exists() or intended_path in planned_targets

            if collision_detected:
                final_path = self.resolve_target_path(intended_path, occupied=planned_targets)
            else:
                final_path = intended_path

            planned_targets.add(final_path)

            plan.append(
                MoveOperation(
                    source_path=item.path,
                    target_category=category,
                    target_subfolder=subfolder,
                    target_path=final_path,
                    source=source,
                    reason=reason,
                    collision_detected=collision_detected,
                    collision_action=CollisionAction.AUTO_RENAME
                    if collision_detected
                    else CollisionAction.SKIP,
                    is_selected=True,
                )
            )

        return plan
