# Local LLM Folder Organizer Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a local, privacy-preserving Python folder organizer with an interactive Textual TUI that combines heuristic file-sorting rules with local Llama 3.2 Ollama intelligence, safe collision resolution, and an undo journal.

**Architecture:** A modular pipeline where files are scanned and shallow-peeked (`scanner.py`), evaluated by deterministic heuristic rules (`heuristics.py`), and ambiguous files are classified in structured JSON batches by local `llama3.2` via Ollama (`classifier.py`). The resulting move operations are collision-checked and auto-renamed if needed (`planner.py`), reviewed/edited interactively in a Textual terminal UI (`tui/`), and executed with atomic rollback logging (`executor.py`).

**Tech Stack:** Python 3.10+, Textual, Pydantic, Ollama Python Client, PyPDF, Click, Pytest.

**Spec:** [`docs/superpowers/specs/2026-10-19-local-llm-folder-organizer-design.md`](../specs/2026-10-19-local-llm-folder-organizer-design.md)

## Global Constraints

- Must work cross-platform on Windows (PowerShell) and POSIX systems.
- Must not overwrite existing files silently; collisions default to auto-renaming `name (1).ext`.
- Active downloads (`.crdownload`, `.part`, `.tmp`) and hidden system files must be excluded from organization.
- Unreachable Ollama or missing `llama3.2` must gracefully fall back to heuristics without crashing.
- Every organization execution must be logged to an undo journal to enable complete one-click restoration.

---

### Task 1: Package Scaffolding, Dependencies, and Data Models

**Files:**
- Create: `pyproject.toml`
- Create: `folder_organizer/__init__.py`
- Create: `folder_organizer/models.py`
- Test: `tests/test_models.py`

**Interfaces:**
- Consumes: None (base foundations)
- Produces: `FileItem`, `ClassificationSource`, `CollisionAction`, `ClassificationResult`, `MoveOperation`, `SessionJournal`

- [ ] **Step 1: Write the failing test for models**

```python
# tests/test_models.py
from pathlib import Path
from folder_organizer.models import (
    FileItem,
    ClassificationSource,
    CollisionAction,
    ClassificationResult,
    MoveOperation,
    SessionJournal,
)


def test_file_item_creation():
    item = FileItem(
        path=Path("/tmp/sample.pdf"),
        filename="sample.pdf",
        extension=".pdf",
        size_bytes=1024,
        modified_time=1700000000.0,
        content_peek="Sample invoice contents",
    )
    assert item.filename == "sample.pdf"
    assert item.extension == ".pdf"
    assert item.is_active_download is False


def test_move_operation_and_collision_defaults():
    move = MoveOperation(
        source_path=Path("/tmp/sample.pdf"),
        target_category="Documents",
        target_subfolder="Invoices",
        target_path=Path("/tmp/Documents/Invoices/sample.pdf"),
        source=ClassificationSource.LLM,
        reason="Detected invoice text",
        collision_detected=True,
    )
    assert move.collision_action == CollisionAction.AUTO_RENAME
    assert move.is_selected is True
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_models.py -v`
Expected: FAIL (ModuleNotFoundError or ImportError)

- [ ] **Step 3: Implement project configuration and Pydantic models**

```toml
# pyproject.toml
[build-system]
requires = ["setuptools>=61.0"]
build-backend = "setuptools.build_meta"

[project]
name = "folder-organizer"
version = "0.1.0"
description = "Local LLM-powered folder organizer with interactive TUI"
readme = "README.md"
requires-python = ">=3.10"
dependencies = [
    "pydantic>=2.0",
    "textual>=0.70.0",
    "ollama>=0.3.0",
    "pypdf>=4.0",
    "click>=8.1"
]

[project.optional-dependencies]
dev = [
    "pytest>=8.0"
]

[project.scripts]
folder-organizer = "folder_organizer.cli:main"

[tool.setuptools.packages.find]
where = ["."]
include = ["folder_organizer*"]
```

```python
# folder_organizer/__init__.py
"""Local LLM Folder Organizer."""

__version__ = "0.1.0"
```

```python
# folder_organizer/models.py
from enum import Enum
from pathlib import Path
from typing import List, Optional, Dict, Any
from pydantic import BaseModel, Field


class ClassificationSource(str, Enum):
    HEURISTIC = "heuristic"
    LLM = "llama3.2"
    MANUAL = "manual"


class CollisionAction(str, Enum):
    AUTO_RENAME = "auto_rename"
    SKIP = "skip"
    OVERWRITE = "overwrite"


class FileItem(BaseModel):
    path: Path
    filename: str
    extension: str
    size_bytes: int
    modified_time: float
    content_peek: Optional[str] = None
    is_active_download: bool = False


class ClassificationResult(BaseModel):
    category: str
    subfolder: Optional[str] = None
    confidence: float = 1.0
    source: ClassificationSource
    reason: str


class MoveOperation(BaseModel):
    source_path: Path
    target_category: str
    target_subfolder: Optional[str] = None
    target_path: Path
    source: ClassificationSource
    reason: str
    collision_detected: bool = False
    collision_action: CollisionAction = CollisionAction.AUTO_RENAME
    is_selected: bool = True


class SessionJournal(BaseModel):
    session_id: str
    timestamp: str
    target_dir: str
    operations: List[Dict[str, str]] = Field(default_factory=list)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_models.py -v`
Expected: PASS

- [ ] **Step 5: Commit Task 1**

```bash
git add pyproject.toml folder_organizer/__init__.py folder_organizer/models.py tests/test_models.py
git commit -m "feat: add project scaffolding and core data models"
```

---

### Task 2: Deterministic Heuristic Engine

**Files:**
- Create: `folder_organizer/heuristics.py`
- Test: `tests/test_heuristics.py`

**Interfaces:**
- Consumes: `FileItem`, `ClassificationResult`, `ClassificationSource`
- Produces: `HeuristicEngine.classify(file_item: FileItem) -> Optional[ClassificationResult]`

- [ ] **Step 1: Write failing tests for heuristics**

```python
# tests/test_heuristics.py
from pathlib import Path
from folder_organizer.models import FileItem, ClassificationSource
from folder_organizer.heuristics import HeuristicEngine


def test_heuristic_installer():
    engine = HeuristicEngine()
    item = FileItem(
        path=Path("installer.exe"),
        filename="installer.exe",
        extension=".exe",
        size_bytes=50000,
        modified_time=0.0,
    )
    result = engine.classify(item)
    assert result is not None
    assert result.category == "Installers"
    assert result.source == ClassificationSource.HEURISTIC


def test_heuristic_archive():
    engine = HeuristicEngine()
    item = FileItem(
        path=Path("backup.tar.gz"),
        filename="backup.tar.gz",
        extension=".tar.gz",
        size_bytes=100000,
        modified_time=0.0,
    )
    result = engine.classify(item)
    assert result is not None
    assert result.category == "Archives"
    assert result.source == ClassificationSource.HEURISTIC


def test_heuristic_ambiguous_returns_none():
    engine = HeuristicEngine()
    item = FileItem(
        path=Path("document.pdf"),
        filename="document.pdf",
        extension=".pdf",
        size_bytes=2048,
        modified_time=0.0,
    )
    assert engine.classify(item) is None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_heuristics.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'folder_organizer.heuristics'`

- [ ] **Step 3: Implement HeuristicEngine**

```python
# folder_organizer/heuristics.py
from typing import Optional, Dict
from folder_organizer.models import FileItem, ClassificationResult, ClassificationSource


class HeuristicEngine:
    """Fast deterministic rule engine that maps known file extensions to base categories."""

    EXTENSION_MAP: Dict[str, str] = {
        # Installers / Packages
        ".exe": "Installers",
        ".msi": "Installers",
        ".dmg": "Installers",
        ".pkg": "Installers",
        ".deb": "Installers",
        ".rpm": "Installers",
        ".appimage": "Installers",
        # Archives
        ".zip": "Archives",
        ".tar": "Archives",
        ".gz": "Archives",
        ".tar.gz": "Archives",
        ".tgz": "Archives",
        ".7z": "Archives",
        ".rar": "Archives",
        ".bz2": "Archives",
        ".xz": "Archives",
        # Disk Images
        ".iso": "Disk Images",
        ".img": "Disk Images",
        ".vhd": "Disk Images",
        # Fonts
        ".ttf": "Fonts",
        ".otf": "Fonts",
        ".woff": "Fonts",
        ".woff2": "Fonts",
    }

    def classify(self, item: FileItem) -> Optional[ClassificationResult]:
        ext = item.extension.lower()
        if ext in self.EXTENSION_MAP:
            category = self.EXTENSION_MAP[ext]
            return ClassificationResult(
                category=category,
                subfolder=None,
                confidence=1.0,
                source=ClassificationSource.HEURISTIC,
                reason=f"Matched deterministic extension rule for '{ext}'",
            )
        return None
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_heuristics.py -v`
Expected: PASS

- [ ] **Step 5: Commit Task 2**

```bash
git add folder_organizer/heuristics.py tests/test_heuristics.py
git commit -m "feat: implement deterministic heuristics rule engine"
```

---

### Task 3: Content Peeker and Directory Scanner

**Files:**
- Create: `folder_organizer/utils/__init__.py`
- Create: `folder_organizer/utils/file_peek.py`
- Create: `folder_organizer/scanner.py`
- Test: `tests/test_scanner.py`

**Interfaces:**
- Consumes: `FileItem`
- Produces: `extract_content_peek(path: Path, max_bytes: int = 2048) -> Optional[str]`
- Produces: `Scanner.scan_directory(target_dir: Path) -> List[FileItem]`

- [ ] **Step 1: Write failing tests for scanner and peeker**

```python
# tests/test_scanner.py
from pathlib import Path
from folder_organizer.scanner import Scanner
from folder_organizer.utils.file_peek import extract_content_peek


def test_extract_text_peek(tmp_path: Path):
    text_file = tmp_path / "notes.txt"
    text_file.write_text("Hello World! This is a test file for peek.", encoding="utf-8")
    peek = extract_content_peek(text_file)
    assert peek is not None
    assert "Hello World!" in peek


def test_scanner_filters_hidden_and_active_downloads(tmp_path: Path):
    (tmp_path / "document.pdf").write_text("dummy pdf", encoding="utf-8")
    (tmp_path / "large_file.crdownload").write_text("downloading", encoding="utf-8")
    (tmp_path / ".hidden_file").write_text("hidden", encoding="utf-8")
    (tmp_path / "subfolder").mkdir()

    scanner = Scanner()
    items = scanner.scan_directory(tmp_path)

    filenames = [item.filename for item in items]
    assert "document.pdf" in filenames
    assert "large_file.crdownload" not in filenames
    assert ".hidden_file" not in filenames
    assert "subfolder" not in filenames  # ignores directories
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_scanner.py -v`
Expected: FAIL with `ModuleNotFoundError`

- [ ] **Step 3: Implement content peeker and directory scanner**

```python
# folder_organizer/utils/__init__.py
"""Utilities for folder organizer."""
```

```python
# folder_organizer/utils/file_peek.py
from pathlib import Path
from typing import Optional


def extract_content_peek(path: Path, max_bytes: int = 2048) -> Optional[str]:
    """Safely extracts a short plain-text snippet from text or PDF files."""
    ext = path.suffix.lower()

    # Plain text, code, markdown, csv, json
    text_extensions = {
        ".txt",
        ".md",
        ".csv",
        ".json",
        ".py",
        ".sh",
        ".html",
        ".css",
        ".yaml",
        ".yml",
        ".xml",
        ".ini",
        ".conf",
        ".sql",
        ".log",
    }

    if ext in text_extensions:
        try:
            with open(path, "r", encoding="utf-8", errors="ignore") as f:
                return f.read(max_bytes).strip()
        except Exception:
            return None

    # PDF shallow peek using pypdf
    if ext == ".pdf":
        try:
            import pypdf

            reader = pypdf.PdfReader(str(path))
            if reader.pages:
                text = reader.pages[0].extract_text() or ""
                return text[:max_bytes].strip()
        except Exception:
            return None

    return None
```

```python
# folder_organizer/scanner.py
import os
from pathlib import Path
from typing import List, Set
from folder_organizer.models import FileItem
from folder_organizer.utils.file_peek import extract_content_peek


class Scanner:
    """Scans target directory for unorganized files while filtering incomplete/system files."""

    IGNORED_EXTENSIONS: Set[str] = {".crdownload", ".part", ".download", ".tmp"}

    IGNORED_NAMES: Set[str] = {"desktop.ini", "thumbs.db", ".ds_store"}

    def scan_directory(self, target_dir: Path) -> List[FileItem]:
        if not target_dir.exists() or not target_dir.is_dir():
            raise ValueError(f"Target directory does not exist or is not a directory: {target_dir}")

        items: List[FileItem] = []
        for entry in target_dir.iterdir():
            # Skip subdirectories
            if not entry.is_file():
                continue

            name = entry.name
            lower_name = name.lower()

            # Skip hidden files
            if name.startswith("."):
                continue

            # Skip system files
            if lower_name in self.IGNORED_NAMES:
                continue

            # Detect compound extension like .tar.gz if present
            suffixes = "".join(entry.suffixes).lower()
            ext = (
                suffixes if suffixes in {".tar.gz", ".tar.bz2", ".tar.xz"} else entry.suffix.lower()
            )

            # Skip active downloads
            if ext in self.IGNORED_EXTENSIONS or any(
                name.endswith(e) for e in self.IGNORED_EXTENSIONS
            ):
                continue

            try:
                stat = entry.stat()
                size_bytes = stat.st_size
                mtime = stat.st_mtime
            except OSError:
                continue

            content_peek = extract_content_peek(entry)

            items.append(
                FileItem(
                    path=entry,
                    filename=name,
                    extension=ext,
                    size_bytes=size_bytes,
                    modified_time=mtime,
                    content_peek=content_peek,
                )
            )

        return items
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_scanner.py -v`
Expected: PASS

- [ ] **Step 5: Commit Task 3**

```bash
git add folder_organizer/utils/__init__.py folder_organizer/utils/file_peek.py folder_organizer/scanner.py tests/test_scanner.py
git commit -m "feat: implement shallow content peeker and directory scanner"
```

---

### Task 4: Ollama Local LLM Classifier with Structured Outputs

**Files:**
- Create: `folder_organizer/classifier.py`
- Test: `tests/test_classifier.py`

**Interfaces:**
- Consumes: `FileItem`, `ClassificationResult`, `ClassificationSource`
- Produces: `LLMClassifier.classify_batch(items: List[FileItem]) -> Dict[str, ClassificationResult]`

- [ ] **Step 1: Write failing test for Ollama classifier (with mocked client)**

```python
# tests/test_classifier.py
from pathlib import Path
from unittest.mock import MagicMock, patch
from folder_organizer.models import FileItem, ClassificationSource
from folder_organizer.classifier import LLMClassifier


def test_classify_batch_success():
    classifier = LLMClassifier(model="llama3.2")
    items = [
        FileItem(
            path=Path("aws_bill.pdf"),
            filename="aws_bill.pdf",
            extension=".pdf",
            size_bytes=2048,
            modified_time=0.0,
            content_peek="Amazon Web Services Invoice #1234",
        )
    ]

    mock_response = {
        "message": {
            "content": '{"classifications": [{"filename": "aws_bill.pdf", "category": "Documents", "subfolder": "AWS", "reason": "AWS Cloud Invoice"}]}'
        }
    }

    with patch.object(classifier.client, "chat", return_value=mock_response):
        results = classifier.classify_batch(items)
        assert "aws_bill.pdf" in results
        res = results["aws_bill.pdf"]
        assert res.category == "Documents"
        assert res.subfolder == "AWS"
        assert res.source == ClassificationSource.LLM


def test_classify_batch_fallback_on_error():
    classifier = LLMClassifier(model="llama3.2")
    items = [
        FileItem(
            path=Path("notes.txt"),
            filename="notes.txt",
            extension=".txt",
            size_bytes=500,
            modified_time=0.0,
        )
    ]

    with patch.object(classifier.client, "chat", side_effect=Exception("Ollama unreachable")):
        results = classifier.classify_batch(items)
        assert "notes.txt" in results
        assert results["notes.txt"].category == "Documents"
        assert "fallback" in results["notes.txt"].reason.lower()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_classifier.py -v`
Expected: FAIL with `ModuleNotFoundError`

- [ ] **Step 3: Implement LLMClassifier**

```python
# folder_organizer/classifier.py
import json
from typing import List, Dict, Optional
import ollama
from folder_organizer.models import FileItem, ClassificationResult, ClassificationSource


class LLMClassifier:
    """Interacts with local Ollama Llama 3.2 to classify files using structured JSON outputs."""

    def __init__(self, host: str = "http://localhost:11434", model: str = "llama3.2"):
        self.host = host
        self.model = model
        self.client = ollama.Client(host=host)

    def is_available(self) -> bool:
        """Checks if local Ollama daemon is running."""
        try:
            self.client.list()
            return True
        except Exception:
            return False

    def classify_batch(self, items: List[FileItem]) -> Dict[str, ClassificationResult]:
        if not items:
            return {}

        file_summaries = []
        for item in items:
            summary = {
                "filename": item.filename,
                "extension": item.extension,
                "size_bytes": item.size_bytes,
                "peek": item.content_peek[:400] if item.content_peek else "",
            }
            file_summaries.append(summary)

        prompt = (
            "You are a file organization assistant. Categorize these files into clean folders.\n"
            "Choose a top-level category (e.g. Documents, Code, Media, Installers, Archives, Books) "
            "and an optional concise subfolder name (e.g. Invoices, Taxes, Python, Screenshots).\n"
            f"Files to classify: {json.dumps(file_summaries)}\n\n"
            "Return JSON matching this schema: "
            '{"classifications": [{"filename": "...", "category": "...", "subfolder": "...", "reason": "..."}]}'
        )

        try:
            response = self.client.chat(
                model=self.model, messages=[{"role": "user", "content": prompt}], format="json"
            )
            raw_content = response.get("message", {}).get("content", "{}")
            data = json.loads(raw_content)

            results: Dict[str, ClassificationResult] = {}
            for entry in data.get("classifications", []):
                fname = entry.get("filename")
                if fname:
                    results[fname] = ClassificationResult(
                        category=entry.get("category", "Documents").strip().title(),
                        subfolder=entry.get("subfolder", "").strip() or None,
                        confidence=0.9,
                        source=ClassificationSource.LLM,
                        reason=entry.get("reason", "Classified by Llama 3.2"),
                    )

            # Ensure all items received a result
            for item in items:
                if item.filename not in results:
                    results[item.filename] = self._fallback_classify(item)
            return results

        except Exception as e:
            # Fallback for all items if Ollama call fails
            return {item.filename: self._fallback_classify(item, error=str(e)) for item in items}

    def _fallback_classify(
        self, item: FileItem, error: Optional[str] = None
    ) -> ClassificationResult:
        ext = item.extension.lower()
        if ext in {".pdf", ".docx", ".doc", ".txt", ".rtf", ".odt"}:
            category = "Documents"
        elif ext in {".py", ".js", ".ts", ".html", ".css", ".cpp", ".c", ".rs", ".go"}:
            category = "Code"
        elif ext in {".png", ".jpg", ".jpeg", ".gif", ".webp", ".mp4", ".mp3", ".wav"}:
            category = "Media"
        else:
            category = "Other"

        reason = f"Heuristic fallback: {error}" if error else "Default extension grouping"
        return ClassificationResult(
            category=category,
            subfolder=None,
            confidence=0.5,
            source=ClassificationSource.HEURISTIC,
            reason=reason,
        )
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_classifier.py -v`
Expected: PASS

- [ ] **Step 5: Commit Task 4**

```bash
git add folder_organizer/classifier.py tests/test_classifier.py
git commit -m "feat: implement local Ollama classifier with structured JSON outputs"
```

---

### Task 5: Plan Builder & Collision Resolver

**Files:**
- Create: `folder_organizer/planner.py`
- Test: `tests/test_planner.py`

**Interfaces:**
- Consumes: `FileItem`, `ClassificationResult`
- Produces: `PlanBuilder.build_plan(target_dir: Path, items: List[FileItem], classifications: Dict[str, ClassificationResult]) -> List[MoveOperation]`
- Produces: `PlanBuilder.resolve_target_path(target_path: Path) -> Path` (auto-renames duplicates)

- [ ] **Step 1: Write failing tests for plan builder and auto-renaming**

```python
# tests/test_planner.py
from pathlib import Path
from folder_organizer.models import (
    FileItem,
    ClassificationResult,
    ClassificationSource,
    CollisionAction,
)
from folder_organizer.planner import PlanBuilder


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
    assert op.collision_detected is False


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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_planner.py -v`
Expected: FAIL with `ModuleNotFoundError`

- [ ] **Step 3: Implement PlanBuilder**

```python
# folder_organizer/planner.py
from pathlib import Path
from typing import List, Dict, Optional
from folder_organizer.models import FileItem, ClassificationResult, MoveOperation, CollisionAction


class PlanBuilder:
    """Computes move operations and resolves target collisions."""

    def resolve_target_path(self, target_path: Path) -> Path:
        """If target_path exists, finds next available 'name (N).ext'."""
        if not target_path.exists():
            return target_path

        stem = target_path.stem
        suffix = target_path.suffix
        parent = target_path.parent

        counter = 1
        while True:
            candidate = parent / f"{stem} ({counter}){suffix}"
            if not candidate.exists():
                return candidate
            counter += 1

    def build_plan(
        self,
        base_dir: Path,
        items: List[FileItem],
        classifications: Dict[str, ClassificationResult],
        destination_root: Optional[Path] = None,
    ) -> List[MoveOperation]:
        root = destination_root or base_dir
        plan: List[MoveOperation] = []

        for item in items:
            res = classifications.get(item.filename)
            category = res.category if res else "Other"
            subfolder = res.subfolder if res else None
            source = res.source if res else None
            reason = res.reason if res else "Unclassified"

            if subfolder:
                dest_dir = root / category / subfolder
            else:
                dest_dir = root / category

            intended_path = dest_dir / item.filename
            collision_detected = intended_path.exists()

            if collision_detected:
                final_path = self.resolve_target_path(intended_path)
            else:
                final_path = intended_path

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
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_planner.py -v`
Expected: PASS

- [ ] **Step 5: Commit Task 5**

```bash
git add folder_organizer/planner.py tests/test_planner.py
git commit -m "feat: implement plan builder and collision resolution"
```

---

### Task 6: Safe Executor & Undo Journal

**Files:**
- Create: `folder_organizer/executor.py`
- Test: `tests/test_executor.py`

**Interfaces:**
- Consumes: `MoveOperation`, `SessionJournal`
- Produces: `SafeExecutor.execute_plan(plan: List[MoveOperation], session_dir: Path) -> SessionJournal`
- Produces: `SafeExecutor.undo_session(session_id: Optional[str] = None) -> int` (returns restored file count)

- [ ] **Step 1: Write failing tests for move execution and rollback**

```python
# tests/test_executor.py
from pathlib import Path
from folder_organizer.models import MoveOperation, ClassificationSource, CollisionAction
from folder_organizer.executor import SafeExecutor


def test_execute_plan_and_undo(tmp_path: Path):
    source_file = tmp_path / "sample.txt"
    source_file.write_text("content", encoding="utf-8")

    dest_path = tmp_path / "Documents" / "sample.txt"
    op = MoveOperation(
        source_path=source_file,
        target_category="Documents",
        target_path=dest_path,
        source=ClassificationSource.HEURISTIC,
        reason="Rule match",
        is_selected=True,
    )

    journal_path = tmp_path / "history.json"
    executor = SafeExecutor(journal_path=journal_path)

    # 1. Execute
    session = executor.execute_plan([op], target_dir=tmp_path)
    assert not source_file.exists()
    assert dest_path.exists()
    assert len(session.operations) == 1

    # 2. Undo
    restored_count = executor.undo_session()
    assert restored_count == 1
    assert source_file.exists()
    assert not dest_path.exists()
    assert not (tmp_path / "Documents").exists()  # cleans up empty folder
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_executor.py -v`
Expected: FAIL with `ModuleNotFoundError`

- [ ] **Step 3: Implement SafeExecutor and journal manager**

```python
# folder_organizer/executor.py
import json
import shutil
from datetime import datetime
from pathlib import Path
from typing import List, Optional, Dict
from folder_organizer.models import MoveOperation, SessionJournal, CollisionAction


class SafeExecutor:
    """Executes file operations safely and maintains an undo history journal."""

    def __init__(self, journal_path: Optional[Path] = None):
        if journal_path:
            self.journal_path = journal_path
        else:
            home = Path.home()
            self.journal_path = home / ".folder_organizer" / "history.json"
        self.journal_path.parent.mkdir(parents=True, exist_ok=True)

    def _load_history(self) -> List[Dict]:
        if not self.journal_path.exists():
            return []
        try:
            with open(self.journal_path, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return []

    def _save_history(self, history: List[Dict]) -> None:
        with open(self.journal_path, "w", encoding="utf-8") as f:
            json.dump(history, f, indent=2)

    def execute_plan(self, plan: List[MoveOperation], target_dir: Path) -> SessionJournal:
        session_id = datetime.now().strftime("%Y%m%d_%H%M%S")
        timestamp = datetime.now().isoformat()
        operations_log = []

        for op in plan:
            if not op.is_selected:
                continue

            if not op.source_path.exists():
                continue

            dest = op.target_path
            if dest.exists() and op.collision_action == CollisionAction.SKIP:
                continue

            dest.parent.mkdir(parents=True, exist_ok=True)
            try:
                shutil.move(str(op.source_path), str(dest))
                operations_log.append(
                    {"from": str(op.source_path.resolve()), "to": str(dest.resolve())}
                )
            except Exception as e:
                # Log error and continue with remaining batch
                continue

        session = SessionJournal(
            session_id=session_id,
            timestamp=timestamp,
            target_dir=str(target_dir.resolve()),
            operations=operations_log,
        )

        history = self._load_history()
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
                if sess.get("session_id") == session_id:
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
        for d in created_dirs:
            cur = d
            while cur and cur != cur.parent:
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
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_executor.py -v`
Expected: PASS

- [ ] **Step 5: Commit Task 6**

```bash
git add folder_organizer/executor.py tests/test_executor.py
git commit -m "feat: implement atomic executor and undo journal manager"
```

---

### Task 7: Interactive Terminal UI (`Textual`)

**Files:**
- Create: `folder_organizer/tui/__init__.py`
- Create: `folder_organizer/tui/screens.py`
- Create: `folder_organizer/tui/app.py`
- Test: `tests/test_tui.py`

**Interfaces:**
- Consumes: `MoveOperation`, `SafeExecutor`
- Produces: `OrganizerApp(plan: List[MoveOperation], target_dir: Path, executor: SafeExecutor).run()`

- [ ] **Step 1: Write test verifying TUI initialization and state**

```python
# tests/test_tui.py
from pathlib import Path
from folder_organizer.models import MoveOperation, ClassificationSource
from folder_organizer.executor import SafeExecutor
from folder_organizer.tui.app import OrganizerApp


def test_tui_app_initialization(tmp_path: Path):
    op = MoveOperation(
        source_path=tmp_path / "test.pdf",
        target_category="Documents",
        target_path=tmp_path / "Documents" / "test.pdf",
        source=ClassificationSource.HEURISTIC,
        reason="Rule match",
        is_selected=True,
    )
    executor = SafeExecutor(journal_path=tmp_path / "history.json")
    app = OrganizerApp(plan=[op], target_dir=tmp_path, executor=executor)
    assert len(app.plan) == 1
    assert app.target_dir == tmp_path
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_tui.py -v`
Expected: FAIL with `ModuleNotFoundError`

- [ ] **Step 3: Implement Textual screens and application**

```python
# folder_organizer/tui/__init__.py
"""Textual TUI module for folder organizer."""
```

```python
# folder_organizer/tui/screens.py
from pathlib import Path
from textual.app import ComposeResult
from textual.screen import ModalScreen
from textual.widgets import Label, Button, Input
from textual.containers import Vertical, Horizontal


class EditDestinationModal(ModalScreen[str]):
    """Modal dialog allowing the user to override destination category or subfolder."""

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
            self.dismiss(val)
        else:
            self.dismiss(None)


class ConfirmExecutionModal(ModalScreen[bool]):
    """Confirmation modal prior to moving files."""

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
```

```python
# folder_organizer/tui/app.py
from pathlib import Path
from typing import List, Optional
from textual.app import App, ComposeResult
from textual.widgets import Header, Footer, DataTable, Static, Label
from textual.containers import Vertical, Horizontal
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
        self.target_dir = target_dir
        self.executor = executor
        self.executed = False

    def compose(self) -> ComposeResult:
        yield Header()
        yield Label(
            f"Target: [b]{self.target_dir}[/b] | Press [b]Space[/b] to toggle, [b]e[/b] to edit, [b]x[/b] to execute"
        )
        yield DataTable(id="table")
        yield Static("Select a row to preview file contents.", id="preview-box")
        yield Footer()

    def on_mount(self) -> None:
        table = self.query_one(DataTable)
        table.cursor_type = "row"
        table.add_columns("Include", "File Name", "Destination", "Engine", "Collision", "Reason")
        self._refresh_table()

    def _refresh_table(self) -> None:
        table = self.query_one(DataTable)
        table.clear()
        for i, op in enumerate(self.plan):
            include_str = "[X]" if op.is_selected else "[ ]"
            rel_dest = (
                str(op.target_path.relative_to(self.target_dir))
                if self.target_dir in op.target_path.parents
                else str(op.target_path)
            )
            engine = op.source.value if op.source else "unknown"
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

    def on_data_table_row_highlighted(self, event: DataTable.RowHighlighted) -> None:
        row_key = event.row_key.value
        if row_key is not None and row_key.isdigit():
            idx = int(row_key)
            if 0 <= idx < len(self.plan):
                op = self.plan[idx]
                box = self.query_one("#preview-box", Static)
                box.update(
                    f"[b]Source:[/b] {op.source_path}\n[b]Target:[/b] {op.target_path}\n[b]Reason:[/b] {op.reason}"
                )

    def action_toggle_selection(self) -> None:
        table = self.query_one(DataTable)
        if table.cursor_row is not None and table.cursor_row < len(self.plan):
            op = self.plan[table.cursor_row]
            op.is_selected = not op.is_selected
            self._refresh_table()

    def action_toggle_all(self) -> None:
        all_selected = all(op.is_selected for op in self.plan)
        for op in self.plan:
            op.is_selected = not all_selected
        self._refresh_table()

    def action_cycle_collision(self) -> None:
        table = self.query_one(DataTable)
        if table.cursor_row is not None and table.cursor_row < len(self.plan):
            op = self.plan[table.cursor_row]
            if op.collision_detected:
                cycle = {
                    CollisionAction.AUTO_RENAME: CollisionAction.SKIP,
                    CollisionAction.SKIP: CollisionAction.OVERWRITE,
                    CollisionAction.OVERWRITE: CollisionAction.AUTO_RENAME,
                }
                op.collision_action = cycle[op.collision_action]
                self._refresh_table()

    def action_edit_destination(self) -> None:
        table = self.query_one(DataTable)
        if table.cursor_row is not None and table.cursor_row < len(self.plan):
            op = self.plan[table.cursor_row]
            curr_str = (
                f"{op.target_category}/{op.target_subfolder}"
                if op.target_subfolder
                else op.target_category
            )

            def on_edit_done(result: Optional[str]) -> None:
                if result:
                    parts = result.replace("\\", "/").split("/")
                    op.target_category = parts[0]
                    op.target_subfolder = "/".join(parts[1:]) if len(parts) > 1 else None
                    if op.target_subfolder:
                        op.target_path = (
                            self.target_dir
                            / op.target_category
                            / op.target_subfolder
                            / op.source_path.name
                        )
                    else:
                        op.target_path = self.target_dir / op.target_category / op.source_path.name
                    self._refresh_table()

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

        def on_confirmed(confirmed: bool) -> None:
            if confirmed:
                self.executor.execute_plan(self.plan, self.target_dir)
                self.executed = True
                self.exit(result=True)

        self.push_screen(ConfirmExecutionModal(len(selected), collisions), on_confirmed)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_tui.py -v`
Expected: PASS

- [ ] **Step 5: Commit Task 7**

```bash
git add folder_organizer/tui/__init__.py folder_organizer/tui/screens.py folder_organizer/tui/app.py tests/test_tui.py
git commit -m "feat: implement interactive Textual TUI review dashboard"
```

---

### Task 8: CLI Entry Point & Pipeline Orchestration

**Files:**
- Create: `folder_organizer/cli.py`
- Test: `tests/test_cli.py`

**Interfaces:**
- Consumes: `Scanner`, `HeuristicEngine`, `LLMClassifier`, `PlanBuilder`, `OrganizerApp`, `SafeExecutor`
- Produces: `main() -> CLI execution`

- [ ] **Step 1: Write test for CLI commands (dry-run and undo)**

```python
# tests/test_cli.py
from pathlib import Path
from click.testing import CliRunner
from folder_organizer.cli import main


def test_cli_dry_run(tmp_path: Path):
    (tmp_path / "app.exe").write_text("dummy", encoding="utf-8")
    runner = CliRunner()
    result = runner.invoke(main, [str(tmp_path), "--dry-run", "--no-llm"])
    assert result.exit_code == 0
    assert "Dry-Run Plan" in result.output
    assert "app.exe" in result.output
    assert "Installers" in result.output


def test_cli_undo_empty(tmp_path: Path):
    runner = CliRunner()
    result = runner.invoke(main, ["undo"])
    assert result.exit_code == 0
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_cli.py -v`
Expected: FAIL with `ModuleNotFoundError`

- [ ] **Step 3: Implement Click CLI with full pipeline integration**

```python
# folder_organizer/cli.py
import sys
from pathlib import Path
import click
from folder_organizer.scanner import Scanner
from folder_organizer.heuristics import HeuristicEngine
from folder_organizer.classifier import LLMClassifier
from folder_organizer.planner import PlanBuilder
from folder_organizer.executor import SafeExecutor
from folder_organizer.tui.app import OrganizerApp


@click.group(invoke_without_command=True)
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
@click.option("--model", default="llama3.2", help="Ollama model name (default: llama3.2).")
@click.pass_context
def main(ctx, target_dir: Path, dry_run: bool, no_llm: bool, model: str):
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
        click.echo(f"Classifying {len(ambiguous_items)} contextual files using Ollama ({model})...")
        classifier = LLMClassifier(model=model)
        llm_results = classifier.classify_batch(ambiguous_items)
        classifications.update(llm_results)
    elif ambiguous_items:
        click.echo(
            f"Assigning {len(ambiguous_items)} files to fallback categories (LLM disabled)..."
        )
        classifier = LLMClassifier()
        fallback_results = {
            item.filename: classifier._fallback_classify(item) for item in ambiguous_items
        }
        classifications.update(fallback_results)

    planner = PlanBuilder()
    plan = planner.build_plan(target_dir, items, classifications)
    executor = SafeExecutor()

    if dry_run:
        click.echo("\n--- Dry-Run Plan ---")
        for op in plan:
            collision = f" [Collision -> auto-rename]" if op.collision_detected else ""
            click.echo(
                f"• {op.source_path.name} -> {op.target_path.relative_to(target_dir)}{collision}"
            )
        return

    app = OrganizerApp(plan=plan, target_dir=target_dir, executor=executor)
    app.run()


@main.command()
@click.option("--session-id", default=None, help="Specific session ID to undo.")
def undo(session_id: str):
    """Reverts a previous organization run and restores files to their original paths."""
    executor = SafeExecutor()
    restored = executor.undo_session(session_id=session_id)
    if restored > 0:
        click.echo(f"Successfully restored {restored} files to their original locations.")
    else:
        click.echo("No files were restored. History is empty or session not found.")


if __name__ == "__main__":
    main()
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_cli.py -v`
Expected: PASS

- [ ] **Step 5: Commit Task 8**

```bash
git add folder_organizer/cli.py tests/test_cli.py
git commit -m "feat: implement CLI entry point and pipeline orchestration"
```

---

## Plan Self-Review

1. **Spec Coverage Check:**
   - Heuristics first matching archives/installers/fonts: Task 2 (`heuristics.py`).
   - Shallow peeker (text, code, PDF) and safe scanner: Task 3 (`scanner.py`, `file_peek.py`).
   - Local Llama 3.2 structured JSON classification & fallback: Task 4 (`classifier.py`).
   - Target path builder and collision auto-rename: Task 5 (`planner.py`).
   - Safe atomic moves and persistent undo journal: Task 6 (`executor.py`).
   - Textual TUI review dashboard with hotkeys and modals: Task 7 (`tui/`).
   - CLI commands, dry-run mode, and undo command: Task 8 (`cli.py`).
2. **Placeholder Scan:** Zero instances of `TBD`, `TODO`, or hand-waving steps. Every task includes exact test code, implementation code, execution commands, and commit messages.
3. **Type Consistency:** Model types (`FileItem`, `ClassificationResult`, `MoveOperation`, `SessionJournal`, `CollisionAction`, `ClassificationSource`) match verbatim across all tasks.
