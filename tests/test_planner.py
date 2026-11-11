from pathlib import Path

from file_organizer.models import (
    ClassificationResult,
    ClassificationSource,
    CollisionAction,
    FileItem,
)
from file_organizer.planner import PlanBuilder


def test_build_plan_without_collision(tmp_path: Path):
    item = FileItem(
        path=tmp_path / "report.pdf",
        filename="report.pdf",
        extension=".pdf",
        size_bytes=1000,
        modified_time=0.0,
    )
    classifications = {
        "report.pdf": ClassificationResult(
            category="Documents",
            subfolder="Reports",
            source=ClassificationSource.LLM,
            reason="Work report",
        )
    }

    builder = PlanBuilder()
    plan = builder.build_plan(tmp_path, [item], classifications)

    assert len(plan) == 1
    op = plan[0]
    assert op.target_path == tmp_path / "Documents" / "Reports" / "report.pdf"
    assert op.target_category == "Documents"
    assert op.target_subfolder == "Reports"
    assert op.source == ClassificationSource.LLM
    assert op.reason == "Work report"
    assert op.collision_detected is False
    assert op.is_selected is True


def test_build_plan_with_collision_auto_renames(tmp_path: Path):
    dest_dir = tmp_path / "Documents"
    dest_dir.mkdir(parents=True)
    existing_file = dest_dir / "report.pdf"
    existing_file.write_text("existing", encoding="utf-8")

    item = FileItem(
        path=tmp_path / "report.pdf",
        filename="report.pdf",
        extension=".pdf",
        size_bytes=1000,
        modified_time=0.0,
    )
    classifications = {
        "report.pdf": ClassificationResult(
            category="Documents",
            subfolder=None,
            source=ClassificationSource.HEURISTIC,
            reason="Document rule",
        )
    }

    builder = PlanBuilder()
    plan = builder.build_plan(tmp_path, [item], classifications)

    assert len(plan) == 1
    op = plan[0]
    assert op.collision_detected is True
    assert op.target_path == dest_dir / "report (1).pdf"
    assert op.collision_action == CollisionAction.AUTO_RENAME


def test_resolve_target_path_multiple_collisions(tmp_path: Path):
    dest_dir = tmp_path / "Documents"
    dest_dir.mkdir(parents=True)
    (dest_dir / "invoice.pdf").write_text("v0", encoding="utf-8")
    (dest_dir / "invoice (1).pdf").write_text("v1", encoding="utf-8")
    (dest_dir / "invoice (2).pdf").write_text("v2", encoding="utf-8")

    builder = PlanBuilder()
    resolved = builder.resolve_target_path(dest_dir / "invoice.pdf")

    assert resolved == dest_dir / "invoice (3).pdf"


def test_resolve_target_path_no_collision(tmp_path: Path):
    dest_dir = tmp_path / "Documents"
    target = dest_dir / "new_file.txt"

    builder = PlanBuilder()
    resolved = builder.resolve_target_path(target)

    assert resolved == target


def test_build_plan_custom_destination_root(tmp_path: Path):
    source_dir = tmp_path / "Downloads"
    dest_root = tmp_path / "Organized"
    source_dir.mkdir()
    dest_root.mkdir()

    item = FileItem(
        path=source_dir / "photo.jpg",
        filename="photo.jpg",
        extension=".jpg",
        size_bytes=2048,
        modified_time=0.0,
    )
    classifications = {
        "photo.jpg": ClassificationResult(
            category="Images",
            subfolder="Vacation",
            source=ClassificationSource.LLM,
            reason="Holiday photo",
        )
    }

    builder = PlanBuilder()
    plan = builder.build_plan(
        base_dir=source_dir,
        items=[item],
        classifications=classifications,
        destination_root=dest_root,
    )

    assert len(plan) == 1
    assert plan[0].target_path == dest_root / "Images" / "Vacation" / "photo.jpg"


def test_build_plan_unclassified_fallback(tmp_path: Path):
    item = FileItem(
        path=tmp_path / "unknown.xyz",
        filename="unknown.xyz",
        extension=".xyz",
        size_bytes=500,
        modified_time=0.0,
    )
    builder = PlanBuilder()
    plan = builder.build_plan(tmp_path, [item], classifications={})

    assert len(plan) == 1
    op = plan[0]
    assert op.target_category == "Other"
    assert op.target_subfolder is None
    assert op.target_path == tmp_path / "Other" / "unknown.xyz"
    assert op.source == ClassificationSource.MANUAL
    assert op.reason == "Unclassified"


def test_build_plan_avoids_in_memory_target_collisions(tmp_path: Path):
    dest_dir = tmp_path / "Documents"
    dest_dir.mkdir(parents=True)
    (dest_dir / "data.csv").write_text("existing", encoding="utf-8")

    item1 = FileItem(
        path=tmp_path / "item1" / "data.csv",
        filename="data.csv",
        extension=".csv",
        size_bytes=100,
        modified_time=0.0,
    )
    item2 = FileItem(
        path=tmp_path / "item2" / "data.csv",
        filename="data.csv",
        extension=".csv",
        size_bytes=200,
        modified_time=0.0,
    )
    classifications = {
        "data.csv": ClassificationResult(
            category="Documents",
            subfolder=None,
            source=ClassificationSource.HEURISTIC,
            reason="CSV data",
        )
    }

    builder = PlanBuilder()
    plan = builder.build_plan(tmp_path, [item1, item2], classifications)

    assert len(plan) == 2
    assert plan[0].target_path == dest_dir / "data (1).csv"
    assert plan[1].target_path == dest_dir / "data (2).csv"


def test_build_plan_empty_items(tmp_path: Path):
    builder = PlanBuilder()
    plan = builder.build_plan(tmp_path, [], {})
    assert plan == []


def test_resolve_target_path_compound_extensions(tmp_path: Path):
    dest_dir = tmp_path / "Archives"
    dest_dir.mkdir(parents=True)
    (dest_dir / "backup.tar.gz").write_text("v0", encoding="utf-8")
    (dest_dir / "backup (1).tar.gz").write_text("v1", encoding="utf-8")
    (dest_dir / "data.tar.bz2").write_text("b0", encoding="utf-8")

    builder = PlanBuilder()
    resolved_gz = builder.resolve_target_path(dest_dir / "backup.tar.gz")
    assert resolved_gz == dest_dir / "backup (2).tar.gz"

    resolved_bz2 = builder.resolve_target_path(dest_dir / "data.tar.bz2")
    assert resolved_bz2 == dest_dir / "data (1).tar.bz2"


def test_build_plan_sets_intended_path(tmp_path: Path):
    dest_dir = tmp_path / "Archives"
    dest_dir.mkdir(parents=True)
    (dest_dir / "archive.tar.gz").write_text("existing", encoding="utf-8")

    item = FileItem(
        path=tmp_path / "archive.tar.gz",
        filename="archive.tar.gz",
        extension=".tar.gz",
        size_bytes=500,
        modified_time=0.0,
    )
    classifications = {
        "archive.tar.gz": ClassificationResult(
            category="Archives",
            subfolder=None,
            source=ClassificationSource.HEURISTIC,
            reason="Archive rule",
        )
    }

    builder = PlanBuilder()
    plan = builder.build_plan(tmp_path, [item], classifications)

    assert len(plan) == 1
    op = plan[0]
    assert op.intended_path == dest_dir / "archive.tar.gz"
    assert op.target_path == dest_dir / "archive (1).tar.gz"
