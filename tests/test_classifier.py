import json
from pathlib import Path
from unittest.mock import patch

from file_organizer.classifier import LLMClassifier
from file_organizer.models import ClassificationSource, FileItem


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
        assert res.confidence == 0.9
        assert res.source == ClassificationSource.LLM
        assert res.reason == "AWS Cloud Invoice"


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
        assert results["notes.txt"].source == ClassificationSource.HEURISTIC
        assert "fallback" in results["notes.txt"].reason.lower()


def test_classify_batch_empty_items():
    classifier = LLMClassifier()
    results = classifier.classify_batch([])
    assert results == {}


def test_is_available():
    classifier = LLMClassifier()
    with patch.object(classifier.client, "list", return_value={"models": []}):
        assert classifier.is_available() is True

    with patch.object(classifier.client, "list", side_effect=Exception("Connection refused")):
        assert classifier.is_available() is False


def test_classify_batch_partial_response_fallback():
    classifier = LLMClassifier()
    items = [
        FileItem(
            path=Path("aws_bill.pdf"),
            filename="aws_bill.pdf",
            extension=".pdf",
            size_bytes=2048,
            modified_time=0.0,
        ),
        FileItem(
            path=Path("script.py"),
            filename="script.py",
            extension=".py",
            size_bytes=100,
            modified_time=0.0,
        ),
    ]

    # LLM only returns classification for aws_bill.pdf
    mock_response = {
        "message": {
            "content": json.dumps(
                {
                    "classifications": [
                        {
                            "filename": "aws_bill.pdf",
                            "category": "Documents",
                            "subfolder": "Cloud",
                            "reason": "AWS Invoice",
                        }
                    ]
                }
            )
        }
    }

    with patch.object(classifier.client, "chat", return_value=mock_response):
        results = classifier.classify_batch(items)
        assert len(results) == 2
        assert results["aws_bill.pdf"].source == ClassificationSource.LLM
        assert results["aws_bill.pdf"].category == "Documents"
        # script.py should be filled by fallback
        assert results["script.py"].source == ClassificationSource.HEURISTIC
        assert results["script.py"].category == "Code"
        assert results["script.py"].subfolder is None


def test_classify_batch_malformed_json_triggers_fallback():
    classifier = LLMClassifier()
    items = [
        FileItem(
            path=Path("photo.png"),
            filename="photo.png",
            extension=".png",
            size_bytes=1024,
            modified_time=0.0,
        )
    ]

    mock_response = {"message": {"content": "Not valid json at all!"}}

    with patch.object(classifier.client, "chat", return_value=mock_response):
        results = classifier.classify_batch(items)
        assert "photo.png" in results
        assert results["photo.png"].source == ClassificationSource.HEURISTIC
        assert results["photo.png"].category == "Media"
        assert "fallback" in results["photo.png"].reason.lower()


def test_classify_batch_peek_truncation():
    classifier = LLMClassifier()
    long_peek = "A" * 600
    items = [
        FileItem(
            path=Path("large.txt"),
            filename="large.txt",
            extension=".txt",
            size_bytes=5000,
            modified_time=0.0,
            content_peek=long_peek,
        )
    ]

    captured_prompt = None

    def fake_chat(model, messages, format):
        nonlocal captured_prompt
        captured_prompt = messages[0]["content"]
        return {"message": {"content": '{"classifications": []}'}}

    with patch.object(classifier.client, "chat", side_effect=fake_chat):
        classifier.classify_batch(items)
        assert captured_prompt is not None
        # Peek in prompt should be truncated to 400 chars
        assert "A" * 400 in captured_prompt
        assert "A" * 401 not in captured_prompt


def test_fallback_classify_categories():
    classifier = LLMClassifier()

    doc_item = FileItem(
        path=Path("doc.docx"),
        filename="doc.docx",
        extension=".docx",
        size_bytes=10,
        modified_time=0.0,
    )
    code_item = FileItem(
        path=Path("app.rs"), filename="app.rs", extension=".rs", size_bytes=10, modified_time=0.0
    )
    media_item = FileItem(
        path=Path("song.mp3"),
        filename="song.mp3",
        extension=".mp3",
        size_bytes=10,
        modified_time=0.0,
    )
    other_item = FileItem(
        path=Path("unknown.xyz"),
        filename="unknown.xyz",
        extension=".xyz",
        size_bytes=10,
        modified_time=0.0,
    )

    assert classifier._fallback_classify(doc_item).category == "Documents"
    assert classifier._fallback_classify(code_item).category == "Code"
    assert classifier._fallback_classify(media_item).category == "Media"
    assert classifier._fallback_classify(other_item).category == "Other"


def test_classify_batch_null_subfolder_and_category():
    classifier = LLMClassifier()
    items = [
        FileItem(
            path=Path("doc.pdf"),
            filename="doc.pdf",
            extension=".pdf",
            size_bytes=100,
            modified_time=0.0,
        )
    ]

    mock_response = {
        "message": {
            "content": json.dumps(
                {
                    "classifications": [
                        {"filename": "doc.pdf", "category": None, "subfolder": None, "reason": None}
                    ]
                }
            )
        }
    }

    with patch.object(classifier.client, "chat", return_value=mock_response):
        results = classifier.classify_batch(items)
        assert results["doc.pdf"].category == "Documents"
        assert results["doc.pdf"].subfolder is None
        assert results["doc.pdf"].reason == "Classified by Llama 3.2"
        assert results["doc.pdf"].source == ClassificationSource.LLM


def test_classify_batch_filters_hallucinated_filenames_and_non_dicts():
    classifier = LLMClassifier()
    real_item = FileItem(
        path=Path("real.pdf"),
        filename="real.pdf",
        extension=".pdf",
        size_bytes=100,
        modified_time=0.0,
    )
    items = [real_item]

    mock_response = {
        "message": {
            "content": json.dumps(
                {
                    "classifications": [
                        "invalid non-dict entry",
                        None,
                        {
                            "filename": "hallucinated.pdf",
                            "category": "Documents",
                            "reason": "Not in items",
                        },
                        {
                            "filename": "real.pdf",
                            "category": "Documents",
                            "subfolder": "Work",
                            "reason": "Real doc",
                        },
                    ]
                }
            )
        }
    }

    with patch.object(classifier.client, "chat", return_value=mock_response):
        results = classifier.classify_batch(items)
        assert len(results) == 1
        assert "real.pdf" in results
        assert "hallucinated.pdf" not in results
        assert results["real.pdf"].subfolder == "Work"
        assert results["real.pdf"].source == ClassificationSource.LLM


def test_classify_batch_handles_non_string_primitives():
    classifier = LLMClassifier()
    item = FileItem(
        path=Path("numbers.pdf"),
        filename="numbers.pdf",
        extension=".pdf",
        size_bytes=100,
        modified_time=0.0,
    )
    mock_response = {
        "message": {
            "content": json.dumps(
                {
                    "classifications": [
                        {
                            "filename": "numbers.pdf",
                            "category": 12345,
                            "subfolder": False,
                            "reason": 999,
                        }
                    ]
                }
            )
        }
    }
    with patch.object(classifier.client, "chat", return_value=mock_response):
        results = classifier.classify_batch([item])
        assert results["numbers.pdf"].category == "12345"
        assert results["numbers.pdf"].subfolder == "False"
        assert results["numbers.pdf"].reason == "999"


def test_classify_batch_chunks_large_inputs():
    classifier = LLMClassifier()
    items = [
        FileItem(
            path=Path(f"file_{i}.pdf"),
            filename=f"file_{i}.pdf",
            extension=".pdf",
            size_bytes=100,
            modified_time=0.0,
        )
        for i in range(25)
    ]

    call_count = 0

    def mock_chat(*args, **kwargs):
        nonlocal call_count
        call_count += 1
        return {"message": {"content": json.dumps({"classifications": []})}}

    with patch.object(classifier.client, "chat", side_effect=mock_chat):
        results = classifier.classify_batch(items, chunk_size=10)
        assert len(results) == 25
        # 25 items with chunk_size 10 produces 3 API calls
        assert call_count == 3
