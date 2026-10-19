# Natural Language File Query & Action Subsystem Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Implement natural language file querying and batch action capabilities (searching, moving, and safe recycling via `send2trash`) via CLI and Textual TUI.

**Architecture:** Two-tier hybrid pipeline where Llama 3.2 compiles natural language into a structured `QueryIntent` with instant Python predicate matching and optional content peek semantic verification, supported by a deterministic offline fallback compiler, safe `send2trash` execution, and atomic undo journaling.

**Tech Stack:** Python 3.12+, Click, Textual, Ollama (`llama3.2`), Pydantic v2, `send2trash`, Pytest.

**Spec:** `docs/superpowers/specs/2026-10-19-natural-language-query-and-actions-design.md`

## Global Constraints

- Must work cross-platform on Windows (PowerShell) and POSIX systems.
- Zero external network transmission: Ollama queries strictly target `http://localhost:11434`.
- Never use unrecoverable deletion (`os.remove` or `shutil.rmtree`); all deletions route through `send2trash`.
- Directory operations must be strictly confined to the target directory: `Path.resolve().is_relative_to(target_dir.resolve())`.
- Collisions on moves default to auto-renaming: `name (1).ext` (handling compound extensions like `.tar.gz`).
- Every move or trash execution must be logged to `~/.folder_organizer/history.json` for one-click rollback.
- Unreachable Ollama or `--no-llm` mode must fall back seamlessly to `KeywordFallbackCompiler` without crashing.

---

### Task 1: Data Models & Dependency Setup

**Files:**
- Modify: `pyproject.toml`
- Modify: `folder_organizer/models.py`
- Create: `tests/test_query_models.py`

**Interfaces:**
- Consumes: Existing `CollisionAction`, `MoveOperation` from `folder_organizer/models.py`
- Produces: `ActionType`, `QueryPredicates`, `QueryIntent`, `ActionOperation`, updated `JournalEntry`, updated `HistorySession`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_query_models.py
from datetime import datetime
from pathlib import Path
from folder_organizer.models import (
    ActionType,
    QueryPredicates,
    QueryIntent,
    ActionOperation,
    CollisionAction,
    JournalEntry,
    HistorySession,
)

def test_action_type_enum():
    assert ActionType.FIND.value == "FIND"
    assert ActionType.MOVE.value == "MOVE"
    assert ActionType.TRASH.value == "TRASH"

def test_query_predicates_defaults():
    pred = QueryPredicates()
    assert pred.extensions == []
    assert pred.name_patterns == []
    assert pred.min_size_bytes is None
    assert pred.max_size_bytes is None
    assert pred.needs_semantic_check is False
    assert pred.semantic_prompt is None

def test_query_intent_construction():
    intent = QueryIntent(
        raw_query="find all installers",
        action=ActionType.FIND,
        predicates=QueryPredicates(extensions=[".exe", ".msi"]),
        reasoning="Searching for installer files",
    )
    assert intent.action == ActionType.FIND
    assert intent.destination_folder is None
    assert intent.predicates.extensions == [".exe", ".msi"]

def test_action_operation_defaults():
    op = ActionOperation(
        source_path=Path("/tmp/setup.exe"),
        action=ActionType.TRASH,
        match_reason="Matches .exe installer rule",
    )
    assert op.action == ActionType.TRASH
    assert op.target_path is None
    assert op.collision_action == CollisionAction.AUTO_RENAME
    assert op.selected is True

def test_journal_entry_trash_support():
    entry = JournalEntry(
        action=ActionType.TRASH,
        source=Path("/tmp/setup.exe"),
        destination=None,
    )
    assert entry.action == ActionType.TRASH
    assert entry.destination is None
    assert isinstance(entry.timestamp, datetime)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_query_models.py -v`
Expected: FAIL with `ImportError: cannot import name 'ActionType' from 'folder_organizer.models'`

- [ ] **Step 3: Update `pyproject.toml` and implement data models**

In `pyproject.toml`, add `"send2trash>=1.8.0"` to `dependencies`.

In `folder_organizer/models.py`:
```python
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Optional
from pydantic import BaseModel, Field

class ActionType(str, Enum):
    FIND = "FIND"
    MOVE = "MOVE"
    TRASH = "TRASH"

class QueryPredicates(BaseModel):
    extensions: list[str] = Field(default_factory=list)
    name_patterns: list[str] = Field(default_factory=list)
    min_size_bytes: Optional[int] = None
    max_size_bytes: Optional[int] = None
    modified_after: Optional[datetime] = None
    modified_before: Optional[datetime] = None
    needs_semantic_check: bool = False
    semantic_prompt: Optional[str] = None

class QueryIntent(BaseModel):
    raw_query: str
    action: ActionType
    destination_folder: Optional[str] = None
    predicates: QueryPredicates = Field(default_factory=QueryPredicates)
    reasoning: str = ""

class ActionOperation(BaseModel):
    source_path: Path
    action: ActionType
    target_path: Optional[Path] = None
    intended_path: Optional[Path] = None
    collision_action: CollisionAction = CollisionAction.AUTO_RENAME
    collision_detected: bool = False
    selected: bool = True
    match_reason: str = ""

# Update JournalEntry to support ActionType
class JournalEntry(BaseModel):
    action: ActionType = ActionType.MOVE
    source: Path
    destination: Optional[Path] = None
    timestamp: datetime = Field(default_factory=datetime.now)

# Update HistorySession to include query_prompt
class HistorySession(BaseModel):
    session_id: str
    timestamp: datetime
    target_dir: Path
    query_prompt: Optional[str] = None
    operations: list[JournalEntry]
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_query_models.py -v`
Expected: PASS (4 tests passed)
Also run existing model tests: `pytest tests/test_models.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add pyproject.toml folder_organizer/models.py tests/test_query_models.py
git commit -m "feat: add query and action data models and send2trash dependency"
```

---

### Task 2: Heuristic Keyword & Pattern Fallback Compiler

**Files:**
- Create: `folder_organizer/query/__init__.py`
- Create: `folder_organizer/query/compiler.py`
- Create: `tests/test_query_compiler.py`

**Interfaces:**
- Consumes: `ActionType`, `QueryPredicates`, `QueryIntent` from `folder_organizer/models.py`
- Produces: `KeywordFallbackCompiler.compile(prompt: str) -> QueryIntent`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_query_compiler.py
from folder_organizer.models import ActionType
from folder_organizer.query.compiler import KeywordFallbackCompiler

def test_fallback_compiler_installers_find():
    compiler = KeywordFallbackCompiler()
    intent = compiler.compile("find all installers")
    assert intent.action == ActionType.FIND
    assert ".exe" in intent.predicates.extensions
    assert ".msi" in intent.predicates.extensions
    assert intent.destination_folder is None

def test_fallback_compiler_move_installers():
    compiler = KeywordFallbackCompiler()
    intent = compiler.compile("move all installers into Installers")
    assert intent.action == ActionType.MOVE
    assert intent.destination_folder == "Installers"
    assert ".exe" in intent.predicates.extensions

def test_fallback_compiler_trash_installers():
    compiler = KeywordFallbackCompiler()
    intent = compiler.compile("delete all installers")
    assert intent.action == ActionType.TRASH
    assert ".exe" in intent.predicates.extensions

def test_fallback_compiler_size_parsing():
    compiler = KeywordFallbackCompiler()
    intent = compiler.compile("find videos over 500MB")
    assert intent.action == ActionType.FIND
    assert ".mp4" in intent.predicates.extensions
    assert intent.predicates.min_size_bytes == 500 * 1024 * 1024

def test_fallback_compiler_clean_setup():
    compiler = KeywordFallbackCompiler()
    intent = compiler.compile("clean up setup files")
    assert intent.action == ActionType.TRASH
    assert "setup" in intent.predicates.name_patterns or ".exe" in intent.predicates.extensions
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_query_compiler.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'folder_organizer.query'`

- [ ] **Step 3: Write implementation**

Create `folder_organizer/query/__init__.py`:
```python
"""Natural language query compilation and filtering."""
```

Create `folder_organizer/query/compiler.py`:
```python
import re
from typing import Optional
from folder_organizer.models import ActionType, QueryIntent, QueryPredicates

class KeywordFallbackCompiler:
    """Deterministic regex & keyword compiler for offline/fallback queries."""

    KEYWORD_EXTENSIONS = {
        "installer": [".exe", ".msi", ".dmg", ".pkg", ".appinstaller", ".deb", ".rpm"],
        "setup": [".exe", ".msi", ".dmg", ".pkg", ".appinstaller", ".deb", ".rpm"],
        "archive": [".zip", ".tar.gz", ".tar.bz2", ".tar.xz", ".7z", ".rar"],
        "zip": [".zip", ".tar.gz", ".tar.bz2", ".tar.xz", ".7z", ".rar"],
        "video": [".mp4", ".mkv", ".mov", ".avi", ".webm"],
        "movie": [".mp4", ".mkv", ".mov", ".avi", ".webm"],
        "audio": [".mp3", ".wav", ".flac", ".m4a", ".aac"],
        "music": [".mp3", ".wav", ".flac", ".m4a", ".aac"],
        "song": [".mp3", ".wav", ".flac", ".m4a", ".aac"],
        "image": [".png", ".jpg", ".jpeg", ".gif", ".webp", ".svg"],
        "photo": [".png", ".jpg", ".jpeg", ".gif", ".webp", ".svg"],
        "picture": [".png", ".jpg", ".jpeg", ".gif", ".webp", ".svg"],
        "document": [".pdf", ".docx", ".doc", ".txt", ".xlsx", ".csv", ".pptx"],
        "pdf": [".pdf"],
        "code": [".py", ".js", ".ts", ".html", ".css", ".json", ".rs", ".go"],
    }

    SIZE_MULTIPLIERS = {
        "b": 1,
        "kb": 1024,
        "mb": 1024 * 1024,
        "gb": 1024 * 1024 * 1024,
    }

    def compile(self, prompt: str) -> QueryIntent:
        cleaned = prompt.strip()
        lower = cleaned.lower()

        # 1. Parse Action & Destination
        action = ActionType.FIND
        destination_folder: Optional[str] = None

        if re.search(r"\b(delete|trash|remove|clean\s*up)\b", lower):
            action = ActionType.TRASH
        else:
            move_match = re.search(
                r"\b(?:move|put|store|organize)\s+(?:all\s+)?(.*?)\s+(?:in|to|into)\s+([a-zA-Z0-9_\- ]+)",
                lower,
            )
            if move_match:
                action = ActionType.MOVE
                destination_folder = move_match.group(2).strip().title()

        # 2. Parse Extensions from keywords
        extensions: list[str] = []
        name_patterns: list[str] = []
        for kw, exts in self.KEYWORD_EXTENSIONS.items():
            if re.search(rf"\b{kw}s?\b", lower):
                for e in exts:
                    if e not in extensions:
                        extensions.append(e)

        if "setup" in lower:
            name_patterns.append("setup")

        # 3. Parse Size Thresholds
        min_size: Optional[int] = None
        max_size: Optional[int] = None

        min_match = re.search(r"(?:over|larger\s+than|>)\s*(\d+(?:\.\d+)?)\s*(kb|mb|gb|b)", lower)
        if min_match:
            val, unit = float(min_match.group(1)), min_match.group(2).lower()
            min_size = int(val * self.SIZE_MULTIPLIERS[unit])

        max_match = re.search(r"(?:under|smaller\s+than|<)\s*(\d+(?:\.\d+)?)\s*(kb|mb|gb|b)", lower)
        if max_match:
            val, unit = float(max_match.group(1)), max_match.group(2).lower()
            max_size = int(val * self.SIZE_MULTIPLIERS[unit])

        predicates = QueryPredicates(
            extensions=extensions,
            name_patterns=name_patterns,
            min_size_bytes=min_size,
            max_size_bytes=max_size,
        )

        return QueryIntent(
            raw_query=cleaned,
            action=action,
            destination_folder=destination_folder,
            predicates=predicates,
            reasoning=f"Heuristic parse: action={action.value}, extensions={len(extensions)} matched",
        )
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_query_compiler.py -v`
Expected: PASS (5 tests passed)

- [ ] **Step 5: Commit**

```bash
git add folder_organizer/query/__init__.py folder_organizer/query/compiler.py tests/test_query_compiler.py
git commit -m "feat: implement deterministic keyword and pattern fallback query compiler"
```

---

### Task 3: Ollama Structured Query Compiler

**Files:**
- Modify: `folder_organizer/query/compiler.py`
- Modify: `tests/test_query_compiler.py`

**Interfaces:**
- Consumes: `ollama.Client`, `QueryIntent`, `KeywordFallbackCompiler`
- Produces: `QueryCompiler.compile(prompt: str) -> QueryIntent` (with automatic fallback)

- [ ] **Step 1: Write the failing test**

```python
# Add to tests/test_query_compiler.py
from unittest.mock import MagicMock, patch
from folder_organizer.query.compiler import QueryCompiler

def test_ollama_query_compiler_success():
    mock_client = MagicMock()
    mock_client.chat.return_value = {
        "message": {
            "content": """{
                "action": "MOVE",
                "destination_folder": "Installers",
                "predicates": {
                    "extensions": [".exe", ".msi"],
                    "name_patterns": [],
                    "min_size_bytes": null,
                    "max_size_bytes": null,
                    "needs_semantic_check": false,
                    "semantic_prompt": null
                },
                "reasoning": "User wants to gather setup files into Installers folder"
            }"""
        }
    }

    compiler = QueryCompiler(client=mock_client)
    intent = compiler.compile("move all installers into Installers")
    assert intent.action == ActionType.MOVE
    assert intent.destination_folder == "Installers"
    assert intent.predicates.extensions == [".exe", ".msi"]

def test_ollama_query_compiler_offline_fallback():
    mock_client = MagicMock()
    mock_client.chat.side_effect = ConnectionError("Ollama unreachable")

    compiler = QueryCompiler(client=mock_client)
    intent = compiler.compile("delete all installers")
    # Automatically falls back to KeywordFallbackCompiler
    assert intent.action == ActionType.TRASH
    assert ".exe" in intent.predicates.extensions
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_query_compiler.py::test_ollama_query_compiler_success -v`
Expected: FAIL with `ImportError: cannot import name 'QueryCompiler' from 'folder_organizer.query.compiler'`

- [ ] **Step 3: Implement `QueryCompiler`**

In `folder_organizer/query/compiler.py`:
```python
import json
import logging
from typing import Any, Optional
import ollama
from folder_organizer.models import ActionType, QueryIntent, QueryPredicates

logger = logging.getLogger(__name__)

class QueryCompiler:
    """Compiles natural language queries using local Ollama (Llama 3.2) with heuristic fallback."""

    SYSTEM_PROMPT = """You are a file query interpreter for a desktop folder organizer.
Analyze the user's natural language request and extract:
1. "action": "FIND" (just searching/listing), "MOVE" (moving files), or "TRASH" (deleting/recycling files).
2. "destination_folder": string or null (e.g. "Installers", "Receipts", if action is MOVE).
3. "predicates":
   - "extensions": array of lowercase extensions starting with a dot (e.g. [".exe", ".msi"]). Expand terms like "installers" to [".exe", ".msi", ".dmg", ".pkg", ".appinstaller", ".deb", ".rpm"].
   - "name_patterns": array of filename substrings (e.g. ["setup", "install"]).
   - "min_size_bytes": integer or null.
   - "max_size_bytes": integer or null.
   - "needs_semantic_check": boolean (true if query requires verifying content peek text, e.g. "Amazon receipts" or "tax documents").
   - "semantic_prompt": string or null (the verification question if needs_semantic_check is true).
4. "reasoning": brief explanation.

Respond ONLY with valid JSON conforming to this schema. No markdown formatting."""

    def __init__(self, model: str = "llama3.2", host: str = "http://localhost:11434", client: Optional[Any] = None):
        self.model = model
        self.host = host
        self._client = client or ollama.Client(host=host)
        self._fallback = KeywordFallbackCompiler()

    def compile(self, prompt: str) -> QueryIntent:
        try:
            response = self._client.chat(
                model=self.model,
                messages=[
                    {"role": "system", "content": self.SYSTEM_PROMPT},
                    {"role": "user", "content": prompt},
                ],
                format="json",
                options={"temperature": 0.0},
            )
            content = response.get("message", {}).get("content", "{}")
            data = json.loads(content)

            action = ActionType(data.get("action", "FIND").upper())
            dest = data.get("destination_folder")
            pred_data = data.get("predicates", {})

            predicates = QueryPredicates(
                extensions=[e if e.startswith(".") else f".{e}" for e in pred_data.get("extensions", [])],
                name_patterns=pred_data.get("name_patterns", []),
                min_size_bytes=pred_data.get("min_size_bytes"),
                max_size_bytes=pred_data.get("max_size_bytes"),
                needs_semantic_check=bool(pred_data.get("needs_semantic_check", False)),
                semantic_prompt=pred_data.get("semantic_prompt"),
            )

            return QueryIntent(
                raw_query=prompt,
                action=action,
                destination_folder=dest,
                predicates=predicates,
                reasoning=data.get("reasoning", "Parsed by Llama 3.2"),
            )
        except Exception as exc:
            logger.warning(f"Ollama query compilation failed ({exc}); falling back to keyword heuristics")
            return self._fallback.compile(prompt)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_query_compiler.py -v`
Expected: PASS (7 tests passed)

- [ ] **Step 5: Commit**

```bash
git add folder_organizer/query/compiler.py tests/test_query_compiler.py
git commit -m "feat: implement Ollama structured query compiler with graceful fallback"
```

---

### Task 4: Hybrid Filter Engine

**Files:**
- Create: `folder_organizer/query/filter.py`
- Create: `tests/test_filter_engine.py`

**Interfaces:**
- Consumes: `ScannedItem`, `QueryIntent`, `ActionOperation`, `ActionType`
- Produces: `FilterEngine.filter_items(items: list[ScannedItem], intent: QueryIntent) -> list[ActionOperation]`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_filter_engine.py
from pathlib import Path
from folder_organizer.models import ActionType, QueryIntent, QueryPredicates, ScannedItem
from folder_organizer.query.filter import FilterEngine

def test_filter_engine_extension_match(tmp_path):
    f1 = tmp_path / "setup.exe"
    f2 = tmp_path / "document.pdf"
    f3 = tmp_path / "installer.msi"
    f1.write_bytes(b"exe")
    f2.write_bytes(b"pdf")
    f3.write_bytes(b"msi")

    items = [
        ScannedItem(path=f1, filename="setup.exe", extension=".exe", size_bytes=3),
        ScannedItem(path=f2, filename="document.pdf", extension=".pdf", size_bytes=3),
        ScannedItem(path=f3, filename="installer.msi", extension=".msi", size_bytes=3),
    ]

    intent = QueryIntent(
        raw_query="find all installers",
        action=ActionType.FIND,
        predicates=QueryPredicates(extensions=[".exe", ".msi"]),
    )

    engine = FilterEngine()
    ops = engine.filter_items(items, intent, target_dir=tmp_path)
    matched_names = {op.source_path.name for op in ops}
    assert matched_names == {"setup.exe", "installer.msi"}
    assert all(op.action == ActionType.FIND for op in ops)

def test_filter_engine_compound_extension(tmp_path):
    f = tmp_path / "backup.tar.gz"
    f.write_bytes(b"archive")
    item = ScannedItem(path=f, filename="backup.tar.gz", extension=".tar.gz", size_bytes=7)

    intent = QueryIntent(
        raw_query="find archives",
        action=ActionType.FIND,
        predicates=QueryPredicates(extensions=[".tar.gz", ".zip"]),
    )

    engine = FilterEngine()
    ops = engine.filter_items([item], intent, target_dir=tmp_path)
    assert len(ops) == 1
    assert ops[0].source_path.name == "backup.tar.gz"

def test_filter_engine_size_threshold(tmp_path):
    f1 = tmp_path / "small.mp4"
    f2 = tmp_path / "large.mp4"
    f1.write_bytes(b"a" * 100)
    f2.write_bytes(b"b" * 2000)

    items = [
        ScannedItem(path=f1, filename="small.mp4", extension=".mp4", size_bytes=100),
        ScannedItem(path=f2, filename="large.mp4", extension=".mp4", size_bytes=2000),
    ]

    intent = QueryIntent(
        raw_query="find videos over 1KB",
        action=ActionType.FIND,
        predicates=QueryPredicates(extensions=[".mp4"], min_size_bytes=1000),
    )

    engine = FilterEngine()
    ops = engine.filter_items(items, intent, target_dir=tmp_path)
    assert len(ops) == 1
    assert ops[0].source_path.name == "large.mp4"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_filter_engine.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'folder_organizer.query.filter'`

- [ ] **Step 3: Implement `FilterEngine`**

Create `folder_organizer/query/filter.py`:
```python
import fnmatch
from pathlib import Path
from typing import Any, Optional
import ollama
from folder_organizer.models import ActionOperation, ActionType, CollisionAction, QueryIntent, ScannedItem
from folder_organizer.planner import PlanBuilder

class FilterEngine:
    """Evaluates compiled query predicates and semantic checks against directory files."""

    COMPOUND_EXTENSIONS = [".tar.gz", ".tar.bz2", ".tar.xz"]

    def __init__(self, ollama_client: Optional[Any] = None, model: str = "llama3.2"):
        self._client = ollama_client
        self.model = model
        self.planner = PlanBuilder()

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

        # Check date bounds if provided
        if pred.modified_after is not None and item.modified_at < pred.modified_after:
            return False, ""
        if pred.modified_before is not None and item.modified_at > pred.modified_before:
            return False, ""

        return True, "Matched query metadata filters"

    def filter_items(
        self,
        items: list[ScannedItem],
        intent: QueryIntent,
        target_dir: Path,
    ) -> list[ActionOperation]:
        matched_ops: list[ActionOperation] = []

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
                collision_detected = intended_path.exists()
                target_path = (
                    self.planner.resolve_target_path(intended_path)
                    if collision_detected
                    else intended_path
                )

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
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_filter_engine.py -v`
Expected: PASS (3 tests passed)

- [ ] **Step 5: Commit**

```bash
git add folder_organizer/query/filter.py tests/test_filter_engine.py
git commit -m "feat: implement hybrid filter engine with compound extension and size matching"
```

---

### Task 5: Safe Executor & Undo Journal Safe Deletion via `send2trash`

**Files:**
- Modify: `folder_organizer/executor.py`
- Create: `tests/test_executor_trash.py`

**Interfaces:**
- Consumes: `ActionOperation`, `ActionType`, `send2trash`
- Produces: `SafeExecutor.execute_action_plan(plan: list[ActionOperation], target_dir: Path) -> list[JournalEntry]`, enhanced `undo_session`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_executor_trash.py
from pathlib import Path
from unittest.mock import patch
import pytest
from folder_organizer.models import ActionOperation, ActionType
from folder_organizer.executor import SafeExecutor

def test_executor_trash_action(tmp_path):
    test_file = tmp_path / "setup.exe"
    test_file.write_bytes(b"content")

    op = ActionOperation(
        source_path=test_file,
        action=ActionType.TRASH,
        selected=True,
    )

    executor = SafeExecutor()
    with patch("send2trash.send2trash") as mock_trash:
        journal = executor.execute_action_plan([op], target_dir=tmp_path)
        mock_trash.assert_called_once_with(str(test_file))

    assert len(journal) == 1
    assert journal[0].action == ActionType.TRASH
    assert journal[0].source == test_file
    assert journal[0].destination is None

def test_executor_trash_boundary_violation(tmp_path):
    outside_file = tmp_path.parent / "escape.exe"
    outside_file.write_bytes(b"bad")

    op = ActionOperation(
        source_path=outside_file,
        action=ActionType.TRASH,
        selected=True,
    )

    executor = SafeExecutor()
    with patch("send2trash.send2trash") as mock_trash:
        with pytest.raises(ValueError, match="Attempted path traversal"):
            executor.execute_action_plan([op], target_dir=tmp_path)
        mock_trash.assert_not_called()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_executor_trash.py -v`
Expected: FAIL with `AttributeError: 'SafeExecutor' object has no attribute 'execute_action_plan'`

- [ ] **Step 3: Implement safe trash in `SafeExecutor`**

In `folder_organizer/executor.py`:
- Add `import send2trash`
- Implement `execute_action_plan(self, plan: list[ActionOperation], target_dir: Path) -> list[JournalEntry]`:
  - Iterates over `plan` where `op.selected is True`.
  - Asserts `op.source_path.resolve().is_relative_to(target_dir.resolve())`.
  - For `ActionType.MOVE`: validates target boundary, creates parent directory, handles collision action, calls `shutil.move()`, appends `JournalEntry(action=ActionType.MOVE, source=..., destination=...)`.
  - For `ActionType.TRASH`: calls `send2trash.send2trash(str(op.source_path))`, appends `JournalEntry(action=ActionType.TRASH, source=op.source_path, destination=None)`.
  - Persists non-empty session to `history.json` atomically.
- Update `undo_session`:
  - For `MOVE`: moves back, handling `<stem>_restored<suffix>` on collision.
  - For `TRASH`: logs advisory with original file path, checks if Windows PowerShell can restore or advises user.

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_executor_trash.py -v`
Expected: PASS (2 tests passed)
Also run existing executor tests: `pytest tests/test_executor.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add folder_organizer/executor.py tests/test_executor_trash.py
git commit -m "feat: implement safe trash execution via send2trash and journal rollback"
```

---

### Task 6: CLI `query` Subcommand Orchestration

**Files:**
- Modify: `folder_organizer/cli.py`
- Create: `tests/test_cli_query.py`

**Interfaces:**
- Consumes: `QueryCompiler`, `FilterEngine`, `SafeExecutor`, `DirectoryScanner`
- Produces: CLI subcommand `folder-organizer query [DIRECTORY] "<prompt>"`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_cli_query.py
from pathlib import Path
from click.testing import CliRunner
from folder_organizer.cli import main

def test_cli_query_dry_run(tmp_path):
    (tmp_path / "setup.exe").write_bytes(b"installer")
    (tmp_path / "readme.txt").write_bytes(b"text")

    runner = CliRunner()
    result = runner.invoke(
        main,
        ["query", str(tmp_path), "find all installers", "--dry-run", "--no-llm"],
    )
    assert result.exit_code == 0
    assert "setup.exe" in result.output
    assert "DRY RUN" in result.output

def test_cli_query_no_matches(tmp_path):
    (tmp_path / "readme.txt").write_bytes(b"text")

    runner = CliRunner()
    result = runner.invoke(
        main,
        ["query", str(tmp_path), "find videos over 1GB", "--dry-run", "--no-llm"],
    )
    assert result.exit_code == 0
    assert "No files matched query" in result.output
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_cli_query.py -v`
Expected: FAIL with `No such command 'query'`

- [ ] **Step 3: Implement `query` CLI command**

In `folder_organizer/cli.py`:
```python
@main.command(name="query")
@click.argument("directory", type=click.Path(exists=True, file_okay=False, path_type=Path), default=".")
@click.argument("prompt", type=str)
@click.option("--dry-run", is_flag=True, help="Preview matches and actions without modifying files.")
@click.option("--no-llm", is_flag=True, help="Force heuristic keyword & regex query compiler.")
@click.option("--model", default="llama3.2", help="Local Ollama model to use.")
@click.option("-y", "--yes", is_flag=True, help="Bypass execution confirmation prompt.")
@click.option("-i", "--interactive", is_flag=True, help="Open matching results in Textual TUI.")
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
    ...
```
- Orchestrates: `DirectoryScanner` -> `QueryCompiler` (or `KeywordFallbackCompiler` if `no_llm`) -> `FilterEngine`.
- Displays results table with Rich.
- Prompts `Execute N operations [y/N]?` if `action in (MOVE, TRASH)` and not `dry_run` and not `yes`.
- Executes via `SafeExecutor.execute_action_plan`.

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_cli_query.py -v`
Expected: PASS (2 tests passed)
Also run full CLI tests: `pytest tests/test_cli.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add folder_organizer/cli.py tests/test_cli_query.py
git commit -m "feat: implement CLI query command with dry-run and confirmation prompt"
```

---

### Task 7: Interactive Textual TUI Query Modal & Filter

**Files:**
- Modify: `folder_organizer/tui/screens.py`
- Modify: `folder_organizer/tui/app.py`
- Create: `tests/test_tui_query.py`

**Interfaces:**
- Consumes: `QueryCompiler`, `FilterEngine`, `QueryModal`
- Produces: `/` keybinding opening query bar, dynamic DataTable filtering and action re-targeting

- [ ] **Step 1: Write the failing test**

```python
# tests/test_tui_query.py
import pytest
from pathlib import Path
from folder_organizer.models import MoveOperation, ScannedItem
from folder_organizer.tui.app import OrganizerApp

@pytest.mark.asyncio
async def test_tui_query_keybinding_opens_modal(tmp_path):
    item = ScannedItem(path=tmp_path / "setup.exe", filename="setup.exe", extension=".exe", size_bytes=10)
    op = MoveOperation(source_path=item.path, target_path=tmp_path / "Software" / "setup.exe")
    app = OrganizerApp(plan=[op], target_dir=tmp_path, no_llm=True)

    async with app.run_test() as pilot:
        await pilot.press("slash")
        # Assert QueryModal is pushed to screen stack
        assert len(app.screen_stack) > 1
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_tui_query.py -v`
Expected: FAIL (Keybinding "slash" not bound or modal not present)

- [ ] **Step 3: Implement `QueryModal` and `/` keybinding**

In `folder_organizer/tui/screens.py`:
- Create `QueryModal(ModalScreen[Optional[str]])` containing an `Input` widget with placeholder *"Enter query (e.g. 'find all installers' or 'trash old files')... (Esc to cancel)"*.
- Enter returns the string query; Esc dismisses with `None`.

In `folder_organizer/tui/app.py`:
- Add binding: `("slash", "open_query", "Query / Search")`.
- Implement `action_open_query`:
  - Pushes `QueryModal`.
  - On submission: runs `QueryCompiler` + `FilterEngine`, updates `DataTable` rows to show matching files, updates action badges (`[TRASH]`, `[MOVE]`), and displays active query banner.
- Add `Esc` to clear query filter.

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_tui_query.py -v`
Expected: PASS
Also run full TUI test suite: `pytest tests/test_tui.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add folder_organizer/tui/screens.py folder_organizer/tui/app.py tests/test_tui_query.py
git commit -m "feat: implement interactive TUI query modal and real-time DataTable filter"
```
