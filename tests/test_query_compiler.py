from unittest.mock import MagicMock, patch

from folder_organizer.models import ActionType
from folder_organizer.query.compiler import KeywordFallbackCompiler, QueryCompiler


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


def test_fallback_compiler_max_size_parsing():
    compiler = KeywordFallbackCompiler()
    intent = compiler.compile("find images under 10KB")
    assert intent.action == ActionType.FIND
    assert ".png" in intent.predicates.extensions
    assert intent.predicates.max_size_bytes == 10 * 1024


def test_fallback_compiler_move_variations():
    compiler = KeywordFallbackCompiler()
    intent = compiler.compile("put all archives in Archives")
    assert intent.action == ActionType.MOVE
    assert intent.destination_folder == "Archives"
    assert ".zip" in intent.predicates.extensions

    intent2 = compiler.compile("organize code to SourceCode")
    assert intent2.action == ActionType.MOVE
    assert intent2.destination_folder == "Sourcecode"
    assert ".py" in intent2.predicates.extensions


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
    assert intent.reasoning == "User wants to gather setup files into Installers folder"


def test_ollama_query_compiler_offline_fallback():
    mock_client = MagicMock()
    mock_client.chat.side_effect = ConnectionError("Ollama unreachable")

    compiler = QueryCompiler(client=mock_client)
    intent = compiler.compile("delete all installers")
    # Automatically falls back to KeywordFallbackCompiler
    assert intent.action == ActionType.TRASH
    assert ".exe" in intent.predicates.extensions


def test_ollama_query_compiler_malformed_json_fallback():
    mock_client = MagicMock()
    mock_client.chat.return_value = {
        "message": {
            "content": "Not valid JSON at all"
        }
    }

    compiler = QueryCompiler(client=mock_client)
    intent = compiler.compile("move all installers to Installers")
    assert intent.action == ActionType.MOVE
    assert intent.destination_folder == "Installers"
    assert ".exe" in intent.predicates.extensions


def test_ollama_query_compiler_normalizes_extensions():
    mock_client = MagicMock()
    mock_client.chat.return_value = {
        "message": {
            "content": """{
                "action": "FIND",
                "predicates": {
                    "extensions": ["pdf", ".docx"],
                    "needs_semantic_check": true,
                    "semantic_prompt": "is this a receipt?"
                }
            }"""
        }
    }

    compiler = QueryCompiler(client=mock_client)
    intent = compiler.compile("find receipts")
    assert intent.action == ActionType.FIND
    assert intent.predicates.extensions == [".pdf", ".docx"]
    assert intent.predicates.needs_semantic_check is True
    assert intent.predicates.semantic_prompt == "is this a receipt?"


def test_query_package_exports():
    from folder_organizer.query import KeywordFallbackCompiler as Kwd, QueryCompiler as Qry
    assert Kwd is not None
    assert Qry is not None


def test_ollama_query_compiler_default_client():
    with patch("ollama.Client") as mock_client_cls:
        compiler = QueryCompiler(host="http://custom-host:11434")
        mock_client_cls.assert_called_once_with(host="http://custom-host:11434")
        assert compiler.host == "http://custom-host:11434"
        assert compiler.model == "llama3.2"


def test_ollama_query_compiler_null_predicates():
    mock_client = MagicMock()
    mock_client.chat.return_value = {
        "message": {
            "content": """{
                "action": "FIND",
                "destination_folder": null,
                "predicates": null,
                "reasoning": "Find everything"
            }"""
        }
    }

    compiler = QueryCompiler(client=mock_client)
    intent = compiler.compile("find all files")
    assert intent.action == ActionType.FIND
    assert intent.predicates.extensions == []
    assert intent.predicates.name_patterns == []
    assert intent.reasoning == "Find everything"
