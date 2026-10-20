from pathlib import Path
from unittest.mock import MagicMock, patch
import pytest
from click.testing import CliRunner
from folder_organizer.cli import main
from folder_organizer.models import ActionType, QueryIntent, QueryPredicates


def test_cli_query_dry_run(tmp_path: Path):
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
    # Ensure dry run did not touch original file
    assert (tmp_path / "setup.exe").exists()


def test_cli_query_no_matches(tmp_path: Path):
    (tmp_path / "readme.txt").write_bytes(b"text")

    runner = CliRunner()
    result = runner.invoke(
        main,
        ["query", str(tmp_path), "find videos over 1GB", "--dry-run", "--no-llm"],
    )
    assert result.exit_code == 0
    assert "No files matched query" in result.output


def test_cli_query_find_action(tmp_path: Path):
    (tmp_path / "setup.exe").write_bytes(b"installer")

    runner = CliRunner()
    # FIND action without --dry-run should display matches without prompt
    result = runner.invoke(
        main,
        ["query", str(tmp_path), "find all installers", "--no-llm"],
    )
    assert result.exit_code == 0
    assert "setup.exe" in result.output
    assert (tmp_path / "setup.exe").exists()


def test_cli_query_move_with_yes(tmp_path: Path):
    (tmp_path / "setup.exe").write_bytes(b"installer")

    runner = CliRunner()
    result = runner.invoke(
        main,
        ["query", str(tmp_path), "move all installers into Software", "--no-llm", "-y"],
    )
    assert result.exit_code == 0
    assert (tmp_path / "Software" / "setup.exe").exists()
    assert not (tmp_path / "setup.exe").exists()


def test_cli_query_move_confirmation_prompt_accepted(tmp_path: Path):
    (tmp_path / "setup.exe").write_bytes(b"installer")

    runner = CliRunner()
    result = runner.invoke(
        main,
        ["query", str(tmp_path), "move all installers into Software", "--no-llm"],
        input="y\n",
    )
    assert result.exit_code == 0
    assert "Execute 1 operations" in result.output
    assert (tmp_path / "Software" / "setup.exe").exists()
    assert not (tmp_path / "setup.exe").exists()


def test_cli_query_move_confirmation_prompt_declined(tmp_path: Path):
    (tmp_path / "setup.exe").write_bytes(b"installer")

    runner = CliRunner()
    result = runner.invoke(
        main,
        ["query", str(tmp_path), "move all installers into Software", "--no-llm"],
        input="n\n",
    )
    assert result.exit_code == 0
    assert "Execute 1 operations" in result.output
    assert "Aborted" in result.output
    assert (tmp_path / "setup.exe").exists()
    assert not (tmp_path / "Software" / "setup.exe").exists()


def test_cli_query_trash_with_confirmation_yes(tmp_path: Path):
    (tmp_path / "setup.exe").write_bytes(b"installer")

    runner = CliRunner()
    with patch("send2trash.send2trash") as mock_trash:
        result = runner.invoke(
            main,
            ["query", str(tmp_path), "delete all installers", "--no-llm"],
            input="y\n",
        )
        assert result.exit_code == 0
        assert "Execute 1 operations" in result.output
        mock_trash.assert_called_once_with(str(tmp_path / "setup.exe"))


def test_cli_query_interactive_flag(tmp_path: Path):
    (tmp_path / "setup.exe").write_bytes(b"installer")

    runner = CliRunner()
    with patch("folder_organizer.tui.app.OrganizerApp.run") as mock_run:
        result = runner.invoke(
            main,
            ["query", str(tmp_path), "find all installers", "--no-llm", "-i"],
        )
        assert result.exit_code == 0
        mock_run.assert_called_once()


def test_cli_query_llm_compiler(tmp_path: Path):
    (tmp_path / "setup.exe").write_bytes(b"installer")

    fake_intent = QueryIntent(
        raw_query="find all installers",
        action=ActionType.FIND,
        destination_folder=None,
        predicates=QueryPredicates(extensions=[".exe"]),
        reasoning="Mocked LLM reasoning",
    )

    runner = CliRunner()
    with patch("folder_organizer.cli.QueryCompiler") as mock_compiler_cls:
        mock_instance = MagicMock()
        mock_instance.compile.return_value = fake_intent
        mock_compiler_cls.return_value = mock_instance

        result = runner.invoke(
            main,
            ["query", str(tmp_path), "find all installers", "--dry-run"],
        )
        assert result.exit_code == 0
        assert "setup.exe" in result.output
        mock_instance.compile.assert_called_once_with("find all installers")


def test_cli_query_omitted_directory_defaults_to_cwd(tmp_path: Path):
    (tmp_path / "setup.exe").write_bytes(b"installer")

    runner = CliRunner()
    with runner.isolated_filesystem(temp_dir=tmp_path):
        (Path.cwd() / "setup.exe").write_bytes(b"installer")
        result = runner.invoke(
            main,
            ["query", "find all installers", "--dry-run", "--no-llm"],
        )
        assert result.exit_code == 0
        assert "setup.exe" in result.output


def test_cli_query_invalid_directory():
    runner = CliRunner()
    result = runner.invoke(
        main,
        ["query", "non_existent_dir_12345", "find all installers", "--dry-run", "--no-llm"],
    )
    assert result.exit_code != 0


def test_cli_query_collision_handling(tmp_path: Path):
    (tmp_path / "setup.exe").write_bytes(b"installer")
    dest_dir = tmp_path / "Software"
    dest_dir.mkdir()
    (dest_dir / "setup.exe").write_bytes(b"existing")

    runner = CliRunner()
    result = runner.invoke(
        main,
        ["query", str(tmp_path), "move all installers into Software", "--no-llm", "-y"],
    )
    assert result.exit_code == 0
    assert (dest_dir / "setup.exe").exists()
    assert (dest_dir / "setup (1).exe").exists()
    assert not (tmp_path / "setup.exe").exists()
