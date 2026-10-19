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
