# Local LLM Folder Organizer

An intelligent, local file organizer powered by deterministic heuristics and local Llama 3.2 via Ollama, featuring an interactive full-screen Textual TUI and atomic undo support.

## Features

- **Hybrid Pipeline**:
  - **Deterministic Heuristics**: Instantly and reliably sorts common files (installers, archives, fonts, disk images) with zero LLM overhead.
  - **Shallow Peeker**: Safely extracts the first few kilobytes or text snippets from PDFs, code, and documents for contextual understanding.
  - **Local LLM Classification**: Uses local Ollama (`llama3.2` by default) with structured JSON schemas to infer semantic folders and subfolders.
  - **Offline / Graceful Fallback**: Automatically falls back to extension-based rules if Ollama is offline or when running in `--no-llm` mode.
- **Safety First**:
  - **Collision Resolution**: Automatic `(1)`, `(2)` incrementing preserves existing files without unintended overwrites.
  - **Undo Journal**: Every move operation is recorded in a persistent journal (`~/.folder_organizer/history.json`), allowing instant reversion via `folder-organizer undo`.
- **Interactive TUI**:
  - Full-screen dashboard built with Textual.
  - Keyboard shortcuts to toggle items (`Space`, `a`), customize destination paths (`e`), and cycle collision strategies (`c`).
  - Pre-execution confirmation modal displaying exact action counts.
  - Content preview box highlighting snippets of selected files.

## Installation

Ensure Python 3.10+ is installed.

```bash
git clone https://github.com/example/folder-organizer.git
cd folder-organizer
pip install -e .
```

To run with local AI classification, ensure [Ollama](https://ollama.com/) is installed and running:

```bash
ollama run llama3.2
```

## Usage

### Interactive TUI Mode

Organize a target directory (defaults to `~/Downloads` if omitted):

```bash
folder-organizer ~/Downloads
```

### Dry-Run Mode

Preview planned move operations directly in the terminal without opening the TUI or moving any files:

```bash
folder-organizer ~/Downloads --dry-run
```

### Pure Heuristic Mode (No LLM)

Run strictly with deterministic rules and heuristic fallbacks without querying Ollama:

```bash
folder-organizer ~/Downloads --dry-run --no-llm
```

### Custom Model

Specify a custom Ollama model name:

```bash
folder-organizer ~/Downloads --model llama3.1:8b
```

### Undo Last Organization

Revert moves from the most recent session or specify a specific session ID:

```bash
# Undo the most recent session
folder-organizer undo

# Undo a specific session by ID
folder-organizer undo --session-id <session_id>
```

## Keyboard Shortcuts (TUI)

| Key | Action |
| --- | --- |
| `Space` | Toggle include/skip for selected row |
| `a` | Toggle include/skip for all rows |
| `e` | Edit destination folder for selected file |
| `c` | Cycle collision action (AutoRename -> Overwrite -> Skip) |
| `x` | Open confirmation modal & execute moves |
| `q` | Quit without executing |

## Testing

Run the test suite using pytest:

```bash
pytest tests/ -v
```
### Quick Usage

    # 1. Install package in editable development mode
    pip install -e .

    # 2. Preview organization in dry-run mode
    python -m folder_organizer.cli C:\Users\caleb\Downloads --dry-run

    # 3. Launch the full interactive Textual TUI
    folder-organizer C:\Users\caleb\Downloads

    # 4. Undo the last organization session at any time
    folder-organizer undo

    # 5. Run the full automated test suite
    pytest tests/ -v
