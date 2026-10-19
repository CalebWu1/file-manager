import os
from pathlib import Path
from unittest.mock import patch, MagicMock
from click.testing import CliRunner
from folder_organizer.cli import main
from folder_organizer.models import (
    ClassificationResult,
    ClassificationSource,
    MoveOperation,
)
from folder_organizer.executor import SafeExecutor


def test_cli_dry_run(tmp_path: Path):
    (tmp_path / "app.exe").write_text("dummy", encoding="utf-8")
    runner = CliRunner()
    result = runner.invoke(main, [str(tmp_path), "--dry-run", "--no-llm"])
    assert result.exit_code == 0
    assert "Dry-Run Plan" in result.output
    assert "app.exe" in result.output
    assert "Installers" in result.output


def test_cli_dry_run_with_collision(tmp_path: Path):
    # Existing destination file
    dest_dir = tmp_path / "Installers"
    dest_dir.mkdir(parents=True)
    (dest_dir / "setup.exe").write_text("existing", encoding="utf-8")

    # Source file to organize
    (tmp_path / "setup.exe").write_text("new", encoding="utf-8")

    runner = CliRunner()
    result = runner.invoke(main, [str(tmp_path), "--dry-run", "--no-llm"])
    assert result.exit_code == 0
    assert "[Collision -> auto-rename]" in result.output
    assert "setup (1).exe" in result.output


def test_cli_no_unorganized_files(tmp_path: Path):
    # Empty directory
    runner = CliRunner()
    result = runner.invoke(main, [str(tmp_path), "--dry-run", "--no-llm"])
    assert result.exit_code == 0
    assert "No unorganized files found." in result.output


def test_cli_default_target_dir(tmp_path: Path):
    # Mock Path.home to return a directory where Downloads exists with a file
    downloads_dir = tmp_path / "Downloads"
    downloads_dir.mkdir()
    (downloads_dir / "archive.zip").write_text("dummy", encoding="utf-8")

    with patch("folder_organizer.cli.Path.home", return_value=tmp_path):
        runner = CliRunner()
        result = runner.invoke(main, ["--dry-run", "--no-llm"])
        assert result.exit_code == 0
        assert f"Scanning target folder: {downloads_dir}" in result.output
        assert "archive.zip" in result.output
        assert "Archives" in result.output


def test_cli_default_target_dir_fallback_cwd(tmp_path: Path):
    # Mock Path.home so Downloads does not exist
    fake_home = tmp_path / "nonexistent_home"
    with patch("folder_organizer.cli.Path.home", return_value=fake_home), \
         patch("folder_organizer.cli.Path.cwd", return_value=tmp_path):
        (tmp_path / "file.zip").write_text("content", encoding="utf-8")
        runner = CliRunner()
        result = runner.invoke(main, ["--dry-run", "--no-llm"])
        assert result.exit_code == 0
        assert f"Scanning target folder: {tmp_path}" in result.output


def test_cli_llm_mode(tmp_path: Path):
    # Contextual file not matched by heuristics (e.g., .py file)
    (tmp_path / "script.py").write_text("print('hello')", encoding="utf-8")

    mock_llm_result = {
        "script.py": ClassificationResult(
            category="Code",
            subfolder="Python",
            source=ClassificationSource.LLM,
            reason="Python script file",
        )
    }

    with patch("folder_organizer.cli.LLMClassifier.classify_batch", return_value=mock_llm_result) as mock_batch:
        runner = CliRunner()
        result = runner.invoke(main, [str(tmp_path), "--dry-run", "--model", "custom-model"])
        assert result.exit_code == 0
        assert "Classifying 1 contextual files using Ollama (custom-model)..." in result.output
        assert "Code" in result.output
        assert "Python" in result.output
        mock_batch.assert_called_once()


def test_cli_no_llm_fallback(tmp_path: Path):
    # Ambiguous file with --no-llm flag
    (tmp_path / "document.xyz").write_text("unknown data", encoding="utf-8")

    runner = CliRunner()
    result = runner.invoke(main, [str(tmp_path), "--dry-run", "--no-llm"])
    assert result.exit_code == 0
    assert "Assigning 1 files to fallback categories (LLM disabled)..." in result.output
    assert "Other" in result.output


def test_cli_tui_launch(tmp_path: Path):
    (tmp_path / "installer.msi").write_text("dummy", encoding="utf-8")

    with patch("folder_organizer.cli.OrganizerApp.run") as mock_app_run:
        runner = CliRunner()
        result = runner.invoke(main, [str(tmp_path), "--no-llm"])
        assert result.exit_code == 0
        mock_app_run.assert_called_once()


def test_cli_undo_empty(tmp_path: Path):
    with patch("pathlib.Path.home", return_value=tmp_path):
        runner = CliRunner()
        result = runner.invoke(main, ["undo"])
        assert result.exit_code == 0
        assert "No files were restored. History is empty or session not found." in result.output


def test_cli_undo_success(tmp_path: Path):
    journal_file = tmp_path / "history.json"
    executor = SafeExecutor(journal_path=journal_file)

    # Setup a move and execute it
    src_file = tmp_path / "test.txt"
    src_file.write_text("hello", encoding="utf-8")
    target_dir = tmp_path / "Documents"
    target_dir.mkdir()
    dest_file = target_dir / "test.txt"

    op = MoveOperation(
        source_path=src_file,
        target_path=dest_file,
        target_category="Documents",
        source=ClassificationSource.MANUAL,
        reason="Manual move",
        is_selected=True,
    )
    executor.execute_plan([op], target_dir=tmp_path)
    assert dest_file.exists()
    assert not src_file.exists()

    # Invoke undo with custom journal path
    with patch("folder_organizer.cli.SafeExecutor", return_value=executor):
        runner = CliRunner()
        result = runner.invoke(main, ["undo"])
        assert result.exit_code == 0
        assert "Successfully restored 1 files to their original locations." in result.output
        assert src_file.exists()
        assert not dest_file.exists()


def test_cli_undo_specific_session_id(tmp_path: Path):
    journal_file = tmp_path / "history.json"
    executor = SafeExecutor(journal_path=journal_file)

    # Setup a move and execute it
    src_file = tmp_path / "session_test.txt"
    src_file.write_text("session content", encoding="utf-8")
    target_dir = tmp_path / "Notes"
    target_dir.mkdir()
    dest_file = target_dir / "session_test.txt"

    op = MoveOperation(
        source_path=src_file,
        target_path=dest_file,
        target_category="Notes",
        source=ClassificationSource.MANUAL,
        reason="Manual move",
        is_selected=True,
    )
    session = executor.execute_plan([op], target_dir=tmp_path)
    session_id = session.session_id

    with patch("folder_organizer.cli.SafeExecutor", return_value=executor):
        runner = CliRunner()
        result = runner.invoke(main, ["undo", "--session-id", session_id])
        assert result.exit_code == 0
        assert "Successfully restored 1 files to their original locations." in result.output
        assert src_file.exists()
