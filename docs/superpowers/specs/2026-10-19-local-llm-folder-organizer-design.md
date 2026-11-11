# Specification & PRD: Local LLM Folder Organizer (`folder-organizer`)

**Date:** 2026-10-19  
**Status:** Approved  
**Author:** Caleb Wu  

---

## 1. Executive Summary & Purpose

The **Local LLM Folder Organizer** is an intelligent, privacy-preserving desktop utility written in Python. It automatically categorizes and organizes messy local folders (such as `Downloads` or `Desktop`) into clean, structured subdirectories.

The system combines:
1. **Deterministic Heuristics Engine**: Rapidly identifies and sorts common file types (archives, installers, media) without model latency or resource consumption.
2. **Local Llama 3.2 via Ollama**: Intelligently classifies ambiguous files (documents, code, receipts, project assets) and generates semantic subfolders based on filename, metadata, and shallow content previews.
3. **Interactive Terminal UI (`Textual`)**: Presents a full-screen interactive dashboard where users review proposed file movements, inspect reasons, resolve collisions, edit destination folders inline, and confirm operations.
4. **Non-Destructive Safe Execution & Undo**: Protects files with conflict resolution (auto-renaming, skip, prompt), never silently overwriting, and logs all operations in a persistent journal for instant one-click rollback.

---

## 2. User Experience & Workflow

### 2.1 Invocation
Users trigger the application from the command line:
```bash
# Launch interactive TUI for default Downloads folder
folder-organizer

# Launch interactive TUI for a specific folder
folder-organizer ~/Downloads
folder-organizer /path/to/target

# Run in headless dry-run mode (CLI output only)
folder-organizer ~/Downloads --dry-run

# Directly undo the last organization session
folder-organizer undo
```

### 2.2 TUI Review & Confirmation Flow
1. **Scanning**: Scans target folder, skips active downloads and system files, extracts metadata and 1–2 KB text snippets.
2. **Classification**:
   - First passes files to `HeuristicEngine`. Known files are classified immediately.
   - Ambiguous files are batched and classified asynchronously using local `llama3.2` via Ollama.
3. **Review Grid (`Textual` DataTable)**:
   - Displays all candidate files with their source name, size, proposed category/subfolder, classification method (`Heuristic` vs `Llama 3.2`), conflict status, and reasoning.
   - User can:
     - Press `Space` to toggle inclusion of any individual file.
     - Press `e` or click to edit the destination path/subfolder inline.
     - Press `c` to cycle conflict mode (`Auto-rename` $\rightarrow$ `Skip` $\rightarrow$ `Overwrite`).
     - Press `a` to toggle all files.
4. **Execution**:
   - Pressing `x` or `Ctrl+Enter` opens a final confirmation modal summarizing total moves and conflicts.
   - On confirmation, files are moved, progress is displayed, and an undo journal entry is recorded.
5. **Undo**:
   - User can press `u` in TUI or run `folder-organizer undo` in terminal to revert any historical run.

---

## 3. System Architecture & Components

```
folder_organizer/
├── __init__.py
├── cli.py             # Click/Typer CLI entry point
├── config.py          # Configuration loader & default category rules
├── models.py          # Pydantic data schemas
├── scanner.py         # Directory walker & shallow content peeker
├── heuristics.py      # Deterministic extension & MIME rule engine
├── classifier.py      # Ollama client with structured JSON outputs
├── planner.py         # Move planning, collision detection & auto-renaming
├── executor.py        # Safe atomic moves & undo journal manager
├── tui/
│   ├── __init__.py
│   ├── app.py         # Textual App definition & event loop
│   ├── screens.py     # Main review screen, edit modal, undo modal
│   └── widgets.py     # Custom DataTable, status bar & preview dock
└── utils/
    ├── file_peek.py   # Text, markdown, code, and PDF preview extractor
    └── paths.py       # Cross-platform path helpers
```

### 3.1 Data Models (`models.py`)

```python
from enum import Enum
from pathlib import Path
from typing import List, Optional
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
    operations: List[dict]  # list of {"from": str, "to": str}
```

### 3.2 Core Components

#### 1. Scanner (`scanner.py` & `file_peek.py`)
- Traverses the root of the target directory (non-recursive by default to preserve existing subdirectories).
- Skips temporary / incomplete downloads matching:
  - Extensions: `.crdownload`, `.part`, `.download`, `.tmp`, `.~*`
  - System files: `desktop.ini`, `Thumbs.db`, `.DS_Store`, hidden files starting with `.`
- Performs shallow content peek (up to 2,048 bytes):
  - UTF-8 text, Markdown, CSV, JSON, Python, Shell, HTML/CSS.
  - PDF: Uses `pypdf` to extract the first 300 words of page 1.
  - Binaries / Images / Audio / Video: No content read; metadata only.

#### 2. Heuristics Engine (`heuristics.py`)
- Evaluates fast deterministic rules before calling the LLM.
- **Rule Mappings**:
  - `Installers`: `.exe`, `.msi`, `.pkg`, `.deb`, `.rpm`, `.dmg`, `.appimage`
  - `Archives`: `.zip`, `.tar`, `.gz`, `.tgz`, `.7z`, `.rar`, `.bz2`, `.xz`
  - `Disk Images`: `.iso`, `.img`, `.vhd`
  - `Fonts`: `.ttf`, `.otf`, `.woff`, `.woff2`
- Files matching these rules are categorized immediately with `ClassificationSource.HEURISTIC`.
- Documents, spreadsheets, presentations, code scripts, and ambiguous extensions are flagged for contextual LLM classification.

#### 3. LLM Classifier (`classifier.py`)
- Connects to local Ollama instance (`http://localhost:11434`) via `ollama` Python client.
- Targets model `llama3.2` (defaults to `llama3.2:3b` or `llama3.2:latest`, configurable).
- Batches up to 10 files per request.
- Uses Ollama structured JSON schema:
  ```json
  {
    "type": "object",
    "properties": {
      "classifications": {
        "type": "array",
        "items": {
          "type": "object",
          "properties": {
            "filename": {"type": "string"},
            "category": {"type": "string"},
            "subfolder": {"type": "string"},
            "reason": {"type": "string"}
          },
          "required": ["filename", "category", "subfolder", "reason"]
        }
      }
    },
    "required": ["classifications"]
  }
  ```
- **Fallback Behavior**: If Ollama is unreachable or returns an error, the classifier gracefully falls back to generic extension grouping (e.g., `Documents`, `Code`, `Other`) with a non-fatal warning in the UI.

#### 4. Plan Builder & Collision Handler (`planner.py`)
- Takes classified items and determines target paths:
  - Default: `<target_dir>/<category>/<subfolder>/<filename>` (or `<target_dir>/<category>/<filename>` if subfolder is empty).
- Detects if `target_path` already exists on disk.
- If collision detected:
  - Default action: Auto-rename by appending `(1)`, `(2)`, etc. before the extension (e.g. `report (1).pdf`).
  - Allows TUI user to switch action to `Skip` or `Overwrite`.

#### 5. Safe Executor & Undo Journal (`executor.py`)
- **Execution**:
  - Creates necessary destination directories (`mkdir(parents=True, exist_ok=True)`).
  - Moves files via `shutil.move()`.
  - Records each successful move in a session journal.
  - Persists journal to `~/.folder_organizer/history.json`.
- **Undo Operation**:
  - Reads the last session (or a user-chosen `session_id`).
  - Moves each file from its current destination back to its original location.
  - Cleans up any empty parent directories that were created during the sort.
  - Marks the session as reverted in `history.json`.

#### 6. Textual TUI (`tui/`)
- **Header**: Shows current folder, model status, file count, and key command reminders.
- **Main DataTable**:
  - Column 1: `Select` (`[X]` or `[ ]`)
  - Column 2: `Filename`
  - Column 3: `Size`
  - Column 4: `Destination Path`
  - Column 5: `Engine` (`Heuristic` or `Llama 3.2`)
  - Column 6: `Collision` (`OK`, `Rename (1)`, `Skip`)
  - Column 7: `Reason`
- **Inspect Dock**: Displays file path, target path, and syntax-highlighted text preview of the currently selected file.
- **Modals**:
  - `EditDestinationModal`: Text input to change category or subfolder.
  - `ConfirmExecutionModal`: Warning and confirmation before moving files.
  - `UndoModal`: Interactive list of past sessions with revert buttons.

---

## 4. Configuration Schema (`config.py`)

Configuration is stored in `~/.folder_organizer/config.toml` (auto-created on first run with sensible defaults):

```toml
[general]
default_target = "~/Downloads"
auto_rename_on_collision = true
batch_size = 10

[ollama]
host = "http://localhost:11434"
model = "llama3.2:latest"
timeout_seconds = 30

[categories]
# Base categories with descriptions for LLM prompting
Documents = "PDFs, Word docs, spreadsheets, slides, receipts, and invoices"
Code = "Scripts, source code files, configurations, notebooks"
Media = "Photos, artwork, video recordings, audio tracks"
Installers = "Executables, package installers, disk images"
Archives = "Compressed zip, tar, gzip, 7z files"
Books = "ePubs, mobi, textbooks, manuals"

[heuristics]
# Extension to category mappings
".exe" = "Installers"
".msi" = "Installers"
".dmg" = "Installers"
".pkg" = "Installers"
".zip" = "Archives"
".tar.gz" = "Archives"
".7z" = "Archives"
".rar" = "Archives"
".iso" = "Installers"
```

---

## 5. Error Handling & Edge Cases

| Scenario | System Response |
| :--- | :--- |
| **Ollama service is down** | Banner alert in TUI; automatically switches to Heuristic-only mode without crashing. |
| **Model `llama3.2` not pulled** | TUI provides instructions (`ollama run llama3.2`) and allows proceeding in heuristic mode. |
| **File locked by another app** | Catches `PermissionError`/`OSError`, logs error in TUI status, skips file, and continues remaining moves. |
| **File deleted during preview** | Validates file existence before moving; gracefully marks as missing in journal. |
| **File collision on undo** | If original path now has a new file, renames restored file to `name_restored.ext` to avoid data loss. |
| **Active downloads in progress** | Ignored automatically based on extension (`.crdownload`, `.part`, `.tmp`). |

---

## 6. Testing Strategy

All tests are implemented using `pytest` with 100% test independence using temporary directory fixtures (`tmp_path`):

1. **`tests/test_heuristics.py`**:
   - Asserts deterministic mappings for `.exe`, `.zip`, `.tar.gz`, `.iso`, etc.
   - Asserts ambiguous extensions (`.pdf`, `.py`, `.txt`) return `None` (deferred to LLM).
2. **`tests/test_scanner.py`**:
   - Creates a temporary directory with various dummy files, hidden files, and active download extensions.
   - Verifies exclusions of hidden files and `.crdownload`.
   - Tests content peeking for UTF-8 text, markdown, and PDF dummy files.
3. **`tests/test_classifier.py`**:
   - Mocks the Ollama client using `unittest.mock`.
   - Tests structured JSON response parsing into Pydantic models.
   - Tests batching logic and error fallback on network timeout.
4. **`tests/test_planner.py`**:
   - Verifies target path generation.
   - Verifies collision detection and increment logic (`file (1).ext`, `file (2).ext`).
5. **`tests/test_executor_undo.py`**:
   - Executes live moves of mock files in `tmp_path`.
   - Verifies journal write to custom history path.
   - Executes rollback and asserts all original files are restored to their exact source paths and created empty folders are removed.

---

## 7. Dependencies

- `python >= 3.10`
- `textual >= 0.70.0` (Terminal UI)
- `ollama >= 0.3.0` (Ollama Python client)
- `pydantic >= 2.0` (Data validation and structured outputs)
- `pypdf >= 4.0` (Shallow PDF text peek)
- `click >= 8.1` (CLI argument parsing)
- `pytest >= 8.0` (Testing suite)
